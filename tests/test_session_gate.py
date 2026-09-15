from pathlib import Path
from uuid import uuid4

import pytest

from execution.ledger import Ledger
from execution.models import Allocation, Control, LedgerError, Scope
from execution.ownership import account_lock


def test_busy_session_never_creates_a_ledger(tmp_path: Path) -> None:
    # Given
    scope = Scope(
        account_id="SESSION_TEST", environment="PAPER", execution_scope=uuid4()
    )
    path = tmp_path / "blocked.sqlite3"
    # When
    with (
        account_lock(tmp_path / "locks", scope),
        pytest.raises(LedgerError, match="ACCOUNT_LOCK_BUSY_READ_ONLY"),
        account_lock(tmp_path / "locks", scope) as lease,
    ):
        _ = Ledger(path, lease)
    # Then
    assert not path.exists()


def test_writes_blocked_until_current_review_is_approved(tmp_path: Path) -> None:
    # Given
    scope = Scope(
        account_id="SESSION_TEST", environment="PAPER", execution_scope=uuid4()
    )
    with account_lock(tmp_path / "locks", scope) as lease:
        book = Ledger(tmp_path / "ledger.sqlite3", lease)
        # When / Then
        with pytest.raises(LedgerError, match="SESSION_RECONCILIATION_REQUIRED"):
            book.allocate(Allocation(symbol="005930", qty=100))
        book.approve_virtual_reconciliation(book.snapshot().revision)
        book.allocate(Allocation(symbol="005930", qty=100))
        assert book.portfolio("005930").managed == 100


def test_closed_lease_cannot_mutate_existing_ledger(tmp_path: Path) -> None:
    # Given
    scope = Scope(
        account_id="SESSION_TEST", environment="PAPER", execution_scope=uuid4()
    )
    with account_lock(tmp_path / "locks", scope) as lease:
        book = Ledger(tmp_path / "ledger.sqlite3", lease)
        book.approve_virtual_reconciliation(0)
    # When / Then
    with pytest.raises(LedgerError, match="ACCOUNT_LOCK_NOT_OWNED"):
        book.control(Control(symbol="005930", entry_stopped=True, liquidating=False))


def test_stale_review_cannot_reopen_a_new_session(tmp_path: Path) -> None:
    # Given
    scope = Scope(
        account_id="SESSION_TEST", environment="PAPER", execution_scope=uuid4()
    )
    path = tmp_path / "ledger.sqlite3"
    with account_lock(tmp_path / "locks", scope) as lease:
        book = Ledger(path, lease)
        book.approve_virtual_reconciliation(0)
        book.allocate(Allocation(symbol="005930", qty=100))
    # When / Then
    with account_lock(tmp_path / "locks", scope) as new_lease:
        restored = Ledger(path, new_lease)
        with pytest.raises(LedgerError, match="STALE_RECONCILIATION_REVIEW"):
            restored.approve_virtual_reconciliation(0)
        assert not new_lease.ready


def test_active_lease_cannot_switch_ledger_files(tmp_path: Path) -> None:
    # Given
    scope = Scope(
        account_id="SESSION_TEST", environment="PAPER", execution_scope=uuid4()
    )
    with account_lock(tmp_path / "locks", scope) as lease:
        book = Ledger(tmp_path / "one.sqlite3", lease)
        book.approve_virtual_reconciliation(0)
        # When / Then
        with pytest.raises(LedgerError, match="ACCOUNT_LEDGER_ALREADY_BOUND"):
            _ = Ledger(tmp_path / "two.sqlite3", lease)
        assert not (tmp_path / "two.sqlite3").exists()
