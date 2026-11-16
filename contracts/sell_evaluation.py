"""Pure general-sell observations and manual proposal checks; no order I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from contracts.stop_evaluation import (
        ManagedPosition,
        ObserveAt,
        ProtectionExposure,
        Quote,
    )

ProfitMilestone = Literal["PLUS_5_PERCENT", "PLUS_10_PERCENT"]
SellQuantityMode = Literal["FULL", "HALF"]
SellOrderKind = Literal["LIMIT", "MARKET"]


@dataclass(frozen=True, slots=True)
class ProfitTargetObservation:
    """Price-move observation only; it cannot create or submit a sell order."""

    status: Literal["TARGET_REACHED", "BELOW_TARGET", "UNAVAILABLE"]
    reason: str
    price_return_percent: Decimal | None = None
    reached: tuple[ProfitMilestone, ...] = ()


@dataclass(frozen=True, slots=True)
class ManualSellProposal:
    """Validated manual intent data; never an order command or send permission."""

    status: Literal["READY", "BLOCKED"]
    reason: str
    qty: int = 0
    order_kind: SellOrderKind | None = None
    limit_price: Decimal | None = None
    expires_at: datetime | None = None


def _fresh_quote_reason(
    *, symbol: str, quote: Quote | None, timing: ObserveAt
) -> str | None:
    """Require a fresh last-trade quote for this managed symbol."""
    if quote is None or quote.symbol != symbol:
        return "QUOTE_MISSING_OR_WRONG_SYMBOL"
    age = timing.now - quote.received_at
    if age < timedelta(0) or age > timedelta(seconds=timing.max_quote_age_seconds):
        return "QUOTE_NOT_FRESH"
    return None


def observe_profit_targets(
    position: ManagedPosition,
    quote: Quote | None,
    timing: ObserveAt,
) -> ProfitTargetObservation:
    """Observe +5%/+10% gross price movement without triggering a sale."""
    if position.confirmed_qty == 0:
        return ProfitTargetObservation(
            status="UNAVAILABLE", reason="NO_MANAGED_POSITION"
        )
    if position.average_cost is None:
        return ProfitTargetObservation(
            status="UNAVAILABLE", reason="AVERAGE_COST_MISSING"
        )
    quote_error = _fresh_quote_reason(
        symbol=position.symbol, quote=quote, timing=timing
    )
    if quote_error is not None or quote is None:
        return ProfitTargetObservation(
            status="UNAVAILABLE",
            reason=quote_error or "QUOTE_UNAVAILABLE",
        )

    price_return = (quote.price / position.average_cost - Decimal(1)) * Decimal(100)
    reached_levels: list[ProfitMilestone] = []
    thresholds: tuple[tuple[ProfitMilestone, Decimal], ...] = (
        ("PLUS_5_PERCENT", Decimal(5)),
        ("PLUS_10_PERCENT", Decimal(10)),
    )
    for name, threshold in thresholds:
        if price_return >= threshold:
            reached_levels.append(name)
    reached = tuple(reached_levels)
    return ProfitTargetObservation(
        status="TARGET_REACHED" if reached else "BELOW_TARGET",
        reason="PRICE_TARGET_REACHED" if reached else "BELOW_FIRST_TARGET",
        price_return_percent=price_return,
        reached=reached,
    )


def _blocked(reason: str) -> ManualSellProposal:
    """Every rejected manual sell shares one sanitized BLOCKED shape."""
    return ManualSellProposal(status="BLOCKED", reason=reason)


def _manual_submission_reason(
    *,
    submitted_by_user: bool,
    quantity_mode: SellQuantityMode,
    order_kind: SellOrderKind,
    stop_priority_due: bool,
) -> str | None:
    """Reject anything without an explicit, valid user sell choice first."""
    if not submitted_by_user:
        return "MANUAL_SUBMISSION_REQUIRED"
    if quantity_mode not in ("FULL", "HALF"):
        return "QUANTITY_MODE_UNSUPPORTED"
    if order_kind not in ("LIMIT", "MARKET"):
        return "ORDER_KIND_UNSUPPORTED"
    if stop_priority_due:
        return "STOP_HAS_PRIORITY"
    return None


def _position_evidence_reason(
    position: ManagedPosition, exposure: ProtectionExposure
) -> str | None:
    """Confirm holding equality and unreserved, reconciled sell evidence."""
    if position.confirmed_qty <= 0:
        return "NO_MANAGED_POSITION"
    if exposure.managed_qty != position.confirmed_qty:
        return "POSITION_EVIDENCE_MISMATCH"
    if exposure.reserved_sell_qty > exposure.managed_qty:
        return "SELL_RESERVATION_EXCEEDS_HOLDING"
    if exposure.reconciliation_required or exposure.sell_uncertain:
        return "SELL_EVIDENCE_UNRESOLVED"
    if exposure.reserved_sell_qty:
        return "SELL_ALREADY_RESERVED"
    return None


def _session_window_reason(
    *, timing: ObserveAt, session_start: datetime, session_end: datetime
) -> str | None:
    """Require one aware same-day session containing the observation time."""
    if session_start.utcoffset() is None or session_end.utcoffset() is None:
        return "SESSION_TIMEZONE_REQUIRED"
    local_day = timing.now.astimezone(session_start.tzinfo).date()
    if session_start.date() != session_end.date() or session_start.date() != local_day:
        return "SAME_DAY_SESSION_REQUIRED"
    if session_start >= session_end:
        return "INVALID_SESSION_RANGE"
    if timing.now < session_start:
        return "SESSION_NOT_STARTED"
    if timing.now >= session_end:
        return "SESSION_EXPIRED"
    return None


def _half_sell_qty(position: ManagedPosition) -> int | None:
    """Wholeness check for HALF mode; None means the proposal must stay blocked."""
    if position.confirmed_qty % 2:
        return None
    return position.confirmed_qty // 2


def propose_manual_general_sell(  # noqa: PLR0913 - safety inputs stay explicit.
    *,
    position: ManagedPosition,
    exposure: ProtectionExposure,
    quote: Quote | None,
    timing: ObserveAt,
    session_start: datetime,
    session_end: datetime,
    submitted_by_user: bool,
    quantity_mode: SellQuantityMode = "FULL",
    order_kind: SellOrderKind = "LIMIT",
    market_confirmed: bool = False,
    stop_priority_due: bool = False,
) -> ManualSellProposal:
    """Validate one explicit manual sell choice without constructing a command."""
    reason = _manual_submission_reason(
        submitted_by_user=submitted_by_user,
        quantity_mode=quantity_mode,
        order_kind=order_kind,
        stop_priority_due=stop_priority_due,
    ) or _position_evidence_reason(position, exposure)
    if reason is None:
        reason = _session_window_reason(
            timing=timing, session_start=session_start, session_end=session_end
        )
    if reason is None and order_kind == "MARKET" and not market_confirmed:
        reason = "MARKET_CONFIRMATION_REQUIRED"
    if reason is None:
        quote_error = _fresh_quote_reason(
            symbol=position.symbol, quote=quote, timing=timing
        )
        if quote_error is not None or quote is None:
            reason = quote_error or "QUOTE_UNAVAILABLE"

    if quantity_mode == "FULL":
        qty = position.confirmed_qty
    else:
        qty = _half_sell_qty(position) if reason is None else None
        if qty is None and reason is None:
            reason = "HALF_QTY_NOT_WHOLE"
    if reason is not None:
        return _blocked(reason)
    return ManualSellProposal(
        status="READY",
        reason="EXPLICIT_MANUAL_SELL_VALIDATED",
        qty=qty,
        order_kind=order_kind,
        limit_price=quote.price if order_kind == "LIMIT" else None,
        expires_at=session_end,
    )
