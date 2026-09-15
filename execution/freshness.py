"""Local simulator configuration and absolute command deadline checks."""

from datetime import datetime, timezone

from execution.models import LedgerError, OrderCommand
from execution.storage import Journal


def utc_now() -> datetime:
    """Supply an aware real clock unless a deterministic test clock is injected."""
    return datetime.now(timezone.utc)


def applied_version(journal: Journal, symbol: str) -> int:
    """Use simulator baseline version one until an explicit revision is accepted."""
    versions = [c.version for c in journal.configs if c.symbol == symbol]
    return versions[-1] if versions else 1


def check_freshness(journal: Journal, command: OrderCommand, now: datetime) -> None:
    """Check mutable applicability without extending an intention on replay."""
    if now.utcoffset() is None:
        raise LedgerError("CLOCK_TIMEZONE_REQUIRED")
    if command.expires_at is not None and now >= command.expires_at:
        raise LedgerError("COMMAND_EXPIRED")
    if command.config_version != applied_version(journal, command.symbol):
        raise LedgerError("STALE_CONFIG_VERSION")
