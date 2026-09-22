"""Safe local paper-verification primitives with no broker or network access."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import re
from typing import Mapping


_PLAIN_PRICE_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: str
    observed_at: str


@dataclass(frozen=True)
class PaperOrderRequest:
    symbol: str
    side: str
    quantity: int
    limit_price: str


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    symbol: str
    side: str
    quantity: int
    limit_price: Decimal
    filled_quantity: int
    cancelled_quantity: int
    average_fill_price: Decimal | None
    state: str

    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity - self.cancelled_quantity


class RawEventLog:
    """Append-only raw event log with event-id deduplication and exact replay."""

    def __init__(self) -> None:
        self._events: list[dict[str, object]] = []
        self._event_ids: set[str] = set()
        self._events_by_id: dict[str, dict[str, object]] = {}

    def append(self, event: Mapping[str, object]) -> bool:
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("INVALID_EVENT_ID")
        copied = deepcopy(dict(event))
        if event_id in self._event_ids:
            if self._events_by_id[event_id] == copied:
                return False
            raise ValueError("EVENT_ID_CONFLICT")
        self._events.append(copied)
        self._event_ids.add(event_id)
        self._events_by_id[event_id] = copied
        return True

    def replay(self) -> tuple[dict[str, object], ...]:
        return tuple(deepcopy(event) for event in self._events)


class ReadOnlyQuoteGateway:
    """Quote-only boundary; it cannot submit, cancel, or fill orders."""

    def __init__(self, *, quotes: Mapping[str, Quote]) -> None:
        self._quotes = dict(quotes)

    def get_quote(self, symbol: str) -> Quote:
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("INVALID_SYMBOL")
        try:
            return self._quotes[symbol]
        except KeyError as error:
            raise ValueError("QUOTE_NOT_FOUND") from error

    def submit_order(self, request: PaperOrderRequest) -> None:
        del request
        raise ValueError("PAPER_READ_ONLY")


class PaperBroker:
    """Deterministic local paper broker for order/fill/cancel verification only."""

    def __init__(self) -> None:
        self.event_log = RawEventLog()
        self._orders: dict[str, PaperOrder] = {}
        self._next_order_number = 1

    def submit(self, request: PaperOrderRequest) -> str:
        self._validate_request(request)
        order_id = f"PAPER-{self._next_order_number:06d}"
        self._next_order_number += 1
        self._orders[order_id] = PaperOrder(
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            limit_price=self._positive_decimal(request.limit_price, "INVALID_LIMIT_PRICE"),
            filled_quantity=0,
            cancelled_quantity=0,
            average_fill_price=None,
            state="OPEN",
        )
        self.event_log.append(
            {
                "event_id": f"{order_id}:SUBMITTED",
                "kind": "ORDER_SUBMITTED",
                "order_id": order_id,
                "symbol": request.symbol,
                "quantity": request.quantity,
            }
        )
        return order_id

    def fill(self, order_id: str, *, quantity: int, price: str) -> None:
        order = self.order(order_id)
        fill_price = self._positive_decimal(price, "INVALID_FILL_PRICE")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("FILL_QUANTITY_INVALID")
        if quantity <= 0 or quantity > order.remaining_quantity:
            raise ValueError("FILL_QUANTITY_INVALID")
        if (order.side == "BUY" and fill_price > order.limit_price) or (
            order.side == "SELL" and fill_price < order.limit_price
        ):
            raise ValueError("FILL_PRICE_OUTSIDE_LIMIT")
        prior_value = (order.average_fill_price or Decimal("0")) * order.filled_quantity
        average = (prior_value + fill_price * quantity) / (order.filled_quantity + quantity)
        filled = order.filled_quantity + quantity
        state = "FILLED" if order.remaining_quantity == quantity else "PARTIALLY_FILLED"
        self._orders[order_id] = replace(
            order,
            filled_quantity=filled,
            average_fill_price=average,
            state=state,
        )
        self.event_log.append(
            {
                "event_id": f"{order_id}:FILL:{filled}",
                "kind": "FILL",
                "order_id": order_id,
                "quantity": quantity,
                "price": price,
            }
        )

    def cancel(self, order_id: str) -> None:
        order = self.order(order_id)
        remaining = order.remaining_quantity
        if remaining == 0:
            return
        self._orders[order_id] = replace(
            order,
            cancelled_quantity=order.cancelled_quantity + remaining,
            state="CANCELLED",
        )
        self.event_log.append(
            {
                "event_id": f"{order_id}:CANCELLED",
                "kind": "ORDER_CANCELLED",
                "order_id": order_id,
                "quantity": remaining,
            }
        )

    def order(self, order_id: str) -> PaperOrder:
        try:
            return self._orders[order_id]
        except KeyError as error:
            raise ValueError("ORDER_NOT_FOUND") from error

    @staticmethod
    def _positive_decimal(value: str, code: str) -> Decimal:
        if not isinstance(value, str) or _PLAIN_PRICE_PATTERN.fullmatch(value) is None:
            raise ValueError(code)
        try:
            numeric = Decimal(value)
        except (InvalidOperation, TypeError) as error:
            raise ValueError(code) from error
        if not numeric.is_finite() or numeric <= 0:
            raise ValueError(code)
        return numeric

    @classmethod
    def _validate_request(cls, request: PaperOrderRequest) -> None:
        if (
            not isinstance(request.symbol, str)
            or not request.symbol
            or not isinstance(request.side, str)
            or request.side not in {"BUY", "SELL"}
            or isinstance(request.quantity, bool)
            or not isinstance(request.quantity, int)
            or request.quantity <= 0
        ):
            raise ValueError("PAPER_ORDER_REQUEST_INVALID")
        cls._positive_decimal(request.limit_price, "INVALID_LIMIT_PRICE")
