"""Deterministic Windows paper-adapter boundary without external transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


Outcome = Literal["ACK", "REJECT", "TIMEOUT", "PARTIAL"]
ObservationState = Literal["ACKED", "REJECTED", "UNKNOWN", "PARTIALLY_FILLED"]


@dataclass(frozen=True)
class WindowsAdapterConfig:
    target_os: str
    environment: str

    def __post_init__(self) -> None:
        if self.target_os != "WINDOWS" or self.environment != "PAPER":
            raise ValueError("WINDOWS_PAPER_ONLY")


@dataclass(frozen=True)
class AdapterRequest:
    operation_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.operation_id, str)
            or not isinstance(self.symbol, str)
            or not self.operation_id
            or not self.symbol
        ):
            raise ValueError("ADAPTER_REQUEST_INVALID")
        if not isinstance(self.side, str) or self.side not in {"BUY", "SELL"}:
            raise ValueError("ADAPTER_REQUEST_INVALID")
        if isinstance(self.qty, bool) or not isinstance(self.qty, int) or self.qty <= 0:
            raise ValueError("ADAPTER_REQUEST_INVALID")


@dataclass(frozen=True)
class AdapterObservation:
    operation_id: str
    state: ObservationState
    filled_qty: int = 0
    broker_order_id: str | None = None


class ScriptedWindowsPaperAdapter:
    """A deterministic paper adapter; no OS, network, broker, or account calls."""

    def __init__(
        self,
        config: WindowsAdapterConfig,
        *,
        quotes: Mapping[str, Mapping[str, str]] | None = None,
        outcomes: Mapping[str, Outcome] | None = None,
    ) -> None:
        self.config = config
        self._quotes = {symbol: dict(value) for symbol, value in (quotes or {}).items()}
        self._outcomes = dict(outcomes or {})
        self._observations: dict[str, AdapterObservation] = {}
        self._transport_calls: list[str] = []

    @property
    def transport_calls(self) -> tuple[str, ...]:
        return tuple(self._transport_calls)

    def quote(self, symbol: str) -> dict[str, str]:
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("QUOTE_REQUEST_INVALID")
        quote = self._quotes.get(symbol)
        if quote is None:
            raise ValueError("QUOTE_NOT_FOUND")
        return {"symbol": symbol, **quote}

    def submit(self, request: AdapterRequest) -> AdapterObservation:
        if not isinstance(request, AdapterRequest):
            raise ValueError("ADAPTER_REQUEST_INVALID")
        previous = self._observations.get(request.operation_id)
        if previous is not None:
            if previous.state == "UNKNOWN":
                raise ValueError("RETRY_BLOCKED_UNKNOWN")
            return previous

        outcome = self._outcomes.get(request.operation_id, "ACK")
        if outcome not in {"ACK", "REJECT", "TIMEOUT", "PARTIAL"}:
            raise ValueError("ADAPTER_OUTCOME_INVALID")
        if outcome == "PARTIAL" and request.qty < 2:
            raise ValueError("ADAPTER_PARTIAL_INVALID")

        self._transport_calls.append(request.operation_id)
        if outcome == "ACK":
            observation = AdapterObservation(
                request.operation_id,
                "ACKED",
                broker_order_id=f"paper-{request.operation_id}",
            )
        elif outcome == "REJECT":
            observation = AdapterObservation(request.operation_id, "REJECTED")
        elif outcome == "TIMEOUT":
            observation = AdapterObservation(request.operation_id, "UNKNOWN")
        elif outcome == "PARTIAL":
            observation = AdapterObservation(
                request.operation_id,
                "PARTIALLY_FILLED",
                filled_qty=request.qty // 2,
                broker_order_id=f"paper-{request.operation_id}",
            )
        else:
            raise ValueError("ADAPTER_OUTCOME_INVALID")
        self._observations[request.operation_id] = observation
        return observation
