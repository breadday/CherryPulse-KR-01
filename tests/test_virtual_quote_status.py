"""Checkpoint freshness does not prove live connectivity or exchange hours."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from contracts.stop_evaluation import ObserveAt
from execution.ledger import Ledger
from execution.models import StopQuoteCheckpoint
from execution.ownership import AccountLease


def test_quote_status_is_read_only_and_does_not_infer_connection(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "status.sqlite3"
    book = Ledger(path, lease)
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    missing = book.virtual_quote_status("005930", timing)
    assert (missing.freshness, missing.connection, missing.exchange_session) == (
        "NO_QUOTE",
        "UNVERIFIED",
        "UNVERIFIED",
    )

    received = now - timedelta(seconds=1)
    with book.storage.transaction() as connection:
        book.storage.checkpoint_stop_quote(
            connection,
            StopQuoteCheckpoint(
                symbol="005930",
                price="9700",
                received_at=received,
                evaluated_at=now,
            ),
        )
    revision = book.snapshot().revision
    restored = Ledger(path, lease)
    fresh = restored.virtual_quote_status("005930", timing)
    assert (fresh.freshness, fresh.received_at, fresh.evaluated_at) == (
        "FRESH",
        received,
        now,
    )
    assert (fresh.connection, fresh.exchange_session) == ("UNVERIFIED", "UNVERIFIED")
    assert restored.virtual_quote_status("000660", timing).freshness == "NO_QUOTE"
    assert (
        restored.virtual_quote_status(
            "005930", ObserveAt(now=now + timedelta(seconds=2), max_quote_age_seconds=2)
        ).freshness
        == "STALE"
    )
    assert (
        restored.virtual_quote_status(
            "005930",
            ObserveAt(now=now - timedelta(milliseconds=500), max_quote_age_seconds=2),
        ).freshness
        == "CLOCK_UNCERTAIN"
    )
    assert restored.snapshot().revision == revision
