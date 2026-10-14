"""Read-only WebSocket protocol state; quotes never become execution facts."""

# pyright: reportUnnecessaryIsInstance=false
# Runtime frame validation is required even for typed callers.

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import cast


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    """Received price evidence without an inferred exchange day or session."""

    symbol: str
    price: int
    exchange_clock: str
    received_at: datetime
    generation: int


class QuoteStreamState:
    """Require login, registration, and a fresh quote in the current connection."""

    def __init__(self, symbols: tuple[str, ...]) -> None:
        """Accept a small explicit KRX symbol set for the read-only probe."""
        if (
            not symbols
            or len(symbols) > 10  # noqa: PLR2004 -- Probe cap, not a broker limit.
            or len(set(symbols)) != len(symbols)
            or any(re.fullmatch(r"[0-9]{6}", symbol) is None for symbol in symbols)
        ):
            raise ValueError("SYMBOLS_INVALID")
        self.symbols: tuple[str, ...] = symbols
        self.generation: int = 0
        self.connected: bool = False
        self.logged_in: bool = False
        self.registered: bool = False
        self.last_quotes: dict[str, QuoteObservation] = {}
        self.reason: str = "DISCONNECTED"
        self._last_frame_at: datetime | None = None

    def begin(self) -> None:
        """Forget freshness when a new physical connection is established."""
        self.generation += 1
        self.connected = True
        self.logged_in = False
        self.registered = False
        self.last_quotes.clear()
        self._last_frame_at = None
        self.reason = "LOGIN_PENDING"

    def disconnect(self) -> None:
        """Never retain an old price as usable after disconnect."""
        self.connected = False
        self.logged_in = False
        self.registered = False
        self.last_quotes.clear()
        self.reason = "DISCONNECTED"

    def registration(self) -> dict[str, object]:
        """Create a 0B-only subscription after a proven login ACK."""
        if not self.connected or not self.logged_in:
            raise ValueError("LOGIN_UNCONFIRMED")
        return {
            "trnm": "REG",
            "grp_no": "1",
            "refresh": "1",
            "data": [{"item": list(self.symbols), "type": ["0B"]}],
        }

    def consume(
        self, frame: object, received_at: datetime
    ) -> tuple[QuoteObservation, ...]:
        """Classify strict protocol evidence without evaluating any strategy."""
        if not self.connected:
            self.reason = "DISCONNECTED"
            return ()
        if received_at.utcoffset() is None or (
            self._last_frame_at is not None and received_at < self._last_frame_at
        ):
            self.last_quotes.clear()
            self.reason = "CLOCK_UNCERTAIN"
            return ()
        self._last_frame_at = received_at
        if not isinstance(frame, dict) or not isinstance(
            cast("dict[str, object]", frame).get("trnm"), str
        ):
            self.reason = "FRAME_INVALID"
            return ()
        message = cast("dict[str, object]", frame)
        kind = message.get("trnm")
        if kind in {"PING", "LOGIN", "REG"}:
            if kind != "PING":
                self._ack(message)
            return ()
        if kind != "REAL" or not self.logged_in or not self.registered:
            self.reason = "STREAM_UNCONFIRMED"
            return ()
        return self._consume_quotes(message.get("data"), received_at)

    def _ack(self, frame: dict[str, object]) -> None:
        """Missing/boolean success codes cannot authenticate or register."""
        code = frame.get("return_code")
        success = type(code) in (str, int) and code in (0, "0")
        if frame.get("trnm") == "LOGIN":
            self.logged_in = success
            self.registered = False
            self.last_quotes.clear()
            self.reason = "REGISTRATION_PENDING" if success else "LOGIN_REJECTED"
        else:
            self.registered = self.logged_in and success
            self.last_quotes.clear()
            self.reason = "NO_QUOTE" if self.registered else "REGISTRATION_REJECTED"

    def _consume_quotes(
        self, data: object, received_at: datetime
    ) -> tuple[QuoteObservation, ...]:
        """Keep valid enrolled 0B observations and reject other event types."""
        if not isinstance(data, list) or not data:
            self.reason = "REAL_DATA_INVALID"
            return ()
        observations: list[QuoteObservation] = []
        for item in cast("list[object]", data):
            quote = parse_quote(item, self.symbols, received_at, self.generation)
            if quote is not None:
                observations.append(quote)
                self.last_quotes[quote.symbol] = quote
        self.reason = "QUOTE_OBSERVED" if observations else "REAL_DATA_INVALID"
        return tuple(observations)

    def usable(self, symbol: str, now: datetime, *, max_age_seconds: float) -> bool:
        """Freshness alone is not proof of market session or permission to trade."""
        quote = self.last_quotes.get(symbol)
        if (
            not self.connected
            or not self.registered
            or quote is None
            or now.utcoffset() is None
            or not math.isfinite(max_age_seconds)
            or max_age_seconds <= 0
        ):
            return False
        return 0 <= (now - quote.received_at).total_seconds() <= max_age_seconds


def parse_quote(
    item: object, symbols: tuple[str, ...], received_at: datetime, generation: int
) -> QuoteObservation | None:
    """Normalize FID10/20 only; never assign an execution ID or trading day."""
    if not isinstance(item, dict):
        return None
    row = cast("dict[str, object]", item)
    symbol = row.get("item")
    values = row.get("values")
    if row.get("type") != "0B" or symbol not in symbols or not isinstance(values, dict):
        return None
    fields = cast("dict[str, object]", values)
    price, clock = fields.get("10"), fields.get("20")
    if (
        not isinstance(price, str)
        or re.fullmatch(r"[+-]?[0-9]+", price) is None
        or not isinstance(clock, str)
        or re.fullmatch(r"[0-9]{6}", clock) is None
    ):
        return None
    try:
        _ = datetime.strptime(clock, "%H%M%S").time()  # noqa: DTZ007 -- Clock only, no exchange date inferred.
        normalized = abs(int(price))
    except ValueError:
        return None
    if normalized == 0:
        return None
    return QuoteObservation(
        cast("str", symbol), normalized, clock, received_at, generation
    )
