"""Read-only freshness of the last accepted virtual stop quote."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from contracts.stop_evaluation import ObserveAt
from execution.storage import Journal

if TYPE_CHECKING:
    from execution.models import StopQuoteCheckpoint


@dataclass(frozen=True, slots=True)
class VirtualQuoteStatus:
    """A checkpoint is evidence of an old input, not a live feed or open market."""

    symbol: str
    freshness: Literal["NO_QUOTE", "FRESH", "STALE", "CLOCK_UNCERTAIN"]
    received_at: datetime | None
    evaluated_at: datetime | None
    connection: Literal["UNVERIFIED"] = "UNVERIFIED"
    exchange_session: Literal["UNVERIFIED"] = "UNVERIFIED"


def virtual_quote_status(
    journal: Journal, symbol: str, timing: ObserveAt
) -> VirtualQuoteStatus:
    """Classify checkpoint age without changing the journal or authorizing a sell."""
    checkpoint: StopQuoteCheckpoint | None = next(
        (item for item in journal.stop_quotes if item.symbol == symbol), None
    )
    if checkpoint is None:
        return VirtualQuoteStatus(symbol, "NO_QUOTE", None, None)
    age = timing.now - checkpoint.received_at
    if age.total_seconds() < 0 or timing.now < checkpoint.evaluated_at:
        freshness = "CLOCK_UNCERTAIN"
    elif age.total_seconds() > timing.max_quote_age_seconds:
        freshness = "STALE"
    else:
        freshness = "FRESH"
    return VirtualQuoteStatus(
        symbol, freshness, checkpoint.received_at, checkpoint.evaluated_at
    )
