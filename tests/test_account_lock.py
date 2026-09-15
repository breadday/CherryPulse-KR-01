from pathlib import Path
from uuid import uuid4

import pytest

from execution import ownership
from execution.models import LedgerError, Scope


def test_same_account_excludes_another_execution_scope(tmp_path: Path) -> None:
    # Given
    first = Scope(account_id="LOCK_TEST", environment="PAPER", execution_scope=uuid4())
    second = Scope(account_id="LOCK_TEST", environment="PAPER", execution_scope=uuid4())
    # When / Then
    with (
        ownership.account_lock(tmp_path, first),
        pytest.raises(LedgerError, match="ACCOUNT_LOCK_BUSY_READ_ONLY"),
        ownership.account_lock(tmp_path, second),
    ):
        pytest.fail("competing session acquired the account")


def test_lock_can_be_reacquired_but_starts_unreconciled(tmp_path: Path) -> None:
    # Given
    scope = Scope(account_id="LOCK_TEST", environment="PAPER", execution_scope=uuid4())
    with ownership.account_lock(tmp_path, scope) as initial:
        assert not initial.ready
    # When
    with ownership.account_lock(tmp_path, scope) as next_session:
        # Then
        assert not next_session.ready
        with pytest.raises(LedgerError, match="ACCOUNT_LOCK_NOT_OWNED"):
            initial.require_ready()


def test_unacquired_lease_is_never_ready() -> None:
    # Given
    scope = Scope(account_id="LOCK_TEST", environment="PAPER", execution_scope=uuid4())
    lease = ownership.AccountLease(scope)
    # When / Then
    with pytest.raises(LedgerError, match="ACCOUNT_LOCK_NOT_OWNED"):
        lease.approve_virtual_review()
    assert not lease.ready
