from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from execution.ledger import Ledger
from execution.models import LedgerError, New
from execution.ownership import AccountLease
from execution.virtual import VirtualDispatcher


def command(now: datetime) -> New:
    return New.model_validate(
        {
            "key": "fresh",
            "symbol": "005930",
            "side": "BUY",
            "qty": 10,
            "config_version": 1,
            "order_type": "MARKET",
            "session": "REGULAR",
            "validity": "DAY",
            "expires_at": now.isoformat(),
        }
    )


def test_expired_command_rejected_without_journal_write(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    book = Ledger(tmp_path / "ledger.sqlite3", lease, clock=lambda: now)
    book.approve_virtual_reconciliation(0)
    before = book.snapshot()
    with pytest.raises(LedgerError, match="COMMAND_EXPIRED"):
        _ = book.submit(command(now))
    assert book.snapshot() == before


def test_expired_persisted_request_is_not_sent_or_extended(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    book = Ledger(tmp_path / "ledger.sqlite3", lease, clock=lambda: now)
    book.approve_virtual_reconciliation(0)
    intention = command(now + timedelta(seconds=1))
    request = book.submit(intention).request
    restored = Ledger(
        book.storage.path, lease, clock=lambda: now + timedelta(seconds=1)
    )
    dispatcher = VirtualDispatcher(restored)
    before = restored.snapshot()
    with pytest.raises(LedgerError, match="COMMAND_EXPIRED"):
        _ = dispatcher.send(request.request_id)
    assert dispatcher.calls == []
    assert restored.snapshot() == before
    assert restored.submit(intention).request == request


def test_configuration_change_blocks_old_pending_request(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    book = Ledger(tmp_path / "ledger.sqlite3", lease, clock=lambda: now)
    book.approve_virtual_reconciliation(0)
    request = book.submit(command(now + timedelta(minutes=1))).request
    book.apply_config("005930", expected_version=1, version=2)
    dispatcher = VirtualDispatcher(book)
    with pytest.raises(LedgerError, match="STALE_CONFIG_VERSION"):
        _ = dispatcher.send(request.request_id)
    assert dispatcher.calls == []
    updated = command(now + timedelta(minutes=1)).model_copy(
        update={"key": "new-version", "config_version": 2},
    )
    assert book.submit(updated).created


def test_config_update_rejects_stale_expected_version(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    book = Ledger(tmp_path / "ledger.sqlite3", lease)
    book.approve_virtual_reconciliation(0)
    book.apply_config("005930", expected_version=1, version=2)
    before = book.snapshot()
    with pytest.raises(LedgerError, match="STALE_CONFIG_VERSION"):
        book.apply_config("005930", expected_version=1, version=3)
    assert book.snapshot() == before


def test_new_request_rejected_when_config_is_stale_after_reload(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    book = Ledger(tmp_path / "ledger.sqlite3", lease, clock=lambda: now)
    book.approve_virtual_reconciliation(0)
    book.apply_config("005930", expected_version=1, version=2)
    restored = Ledger(book.storage.path, lease, clock=lambda: now)
    before = restored.snapshot()
    with pytest.raises(LedgerError, match="STALE_CONFIG_VERSION"):
        _ = restored.submit(command(now + timedelta(minutes=1)))
    assert restored.snapshot() == before


def test_replay_cannot_extend_original_deadline(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    book = Ledger(tmp_path / "ledger.sqlite3", lease, clock=lambda: now)
    book.approve_virtual_reconciliation(0)
    _ = book.submit(command(now + timedelta(seconds=1)))
    before = book.snapshot()
    with pytest.raises(LedgerError, match="CONFLICT_IDEMPOTENCY_MISMATCH"):
        _ = book.submit(command(now + timedelta(minutes=1)))
    assert book.snapshot() == before


def test_fresh_request_can_be_sent_before_deadline(
    tmp_path: Path,
    lease: AccountLease,
) -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    book = Ledger(tmp_path / "ledger.sqlite3", lease, clock=lambda: now)
    book.approve_virtual_reconciliation(0)
    request = book.submit(command(now + timedelta(microseconds=1))).request
    dispatcher = VirtualDispatcher(book)
    assert dispatcher.send(request.request_id)
    assert dispatcher.calls == [request]
