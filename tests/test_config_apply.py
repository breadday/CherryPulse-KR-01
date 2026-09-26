"""D01 desired, accepted and local-applied settings remain distinct."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from contracts.inbox import ConfigInbox, ConfigInboxError
from contracts.settings import Actor, ConfigCommand, Pattern, Settings, StopRule
from execution.config_apply import ConfigApplyCoordinator
from execution.facts import Fill
from execution.ledger import Ledger
from execution.models import LedgerError, New, VirtualStopBinding
from execution.ownership import AccountLease
from execution.projection import confirmed_stop_holdings

AUTH_CONTEXT = object()
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


class FakeConfigAuthenticator:
    """Explicit test-only stand-in; production authentication is not configured."""

    def authenticate(self, command: ConfigCommand, context: object) -> Actor | None:
        if context is not AUTH_CONTEXT:
            return None
        settings = command.settings
        return Actor(
            actor_id="test-authenticated-owner",
            account_id=settings.account_id,
            environment=settings.environment,
            permissions=frozenset({"CONFIG_WRITE"}),
        )


def make_command(version: int, expected_version: int) -> ConfigCommand:
    """Create one inert desired stop command with matching pattern revision."""
    settings = Settings(
        account_id="DEMO",
        environment="PAPER",
        symbol="005930",
        version=version,
        stop_pattern=Pattern(
            pattern_id=uuid4(),
            version=version,
            name=f"손절 v{version}",
            side="SELL",
            stop=StopRule(kind="PRICE_AT_OR_BELOW", threshold=str(9800 - version)),
        ),
    )
    return ConfigCommand(
        command_id=uuid4(),
        idempotency_key=f"desired-{version}-{uuid4()}",
        expected_version=expected_version,
        expires_at=NOW + timedelta(minutes=5),
        settings=settings,
    )


def make_inbox(path: Path) -> ConfigInbox:
    """Create an inbox whose verifier exists only in this test process."""
    return ConfigInbox(path, authenticator=FakeConfigAuthenticator())


def receive(inbox: ConfigInbox, command: ConfigCommand) -> None:
    assert inbox.receive(command, NOW, auth_context=AUTH_CONTEXT).state == "ACCEPTED"


def prepare_ledger(path: Path, lease: AccountLease) -> Ledger:
    """Initialize only an isolated virtual ledger and approve its empty review."""
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(book.snapshot().revision)
    return book


def test_unconfigured_authentication_fails_closed_without_persisting_desired(
    tmp_path: Path,
) -> None:
    path = tmp_path / "untrusted-inbox.sqlite3"
    inbox = ConfigInbox(path)
    command = make_command(version=1, expected_version=0)

    result = inbox.receive(command, NOW, auth_context=AUTH_CONTEXT)

    assert (result.state, result.reason) == (
        "REJECTED",
        "CONFIG_AUTHENTICATION_UNAVAILABLE",
    )
    with sqlite3.connect(inbox.path) as connection:
        count = connection.execute("SELECT count(*) FROM config_commands").fetchone()[0]
    assert count == 0


def test_acceptance_is_not_local_application_and_applied_replay_is_idempotent(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger_path = tmp_path / "execution.sqlite3"
    command = make_command(version=1, expected_version=0)
    receive(inbox, command)
    assert inbox.application(command.command_id).state == "NOT_APPLIED"

    ledger = prepare_ledger(ledger_path, lease)
    coordinator = ConfigApplyCoordinator(inbox, ledger)
    first = coordinator.apply(command.command_id)
    assert (first.state, first.applied_version, first.reason) == ("APPLIED", 1, None)
    journal = ledger.snapshot()
    assert len(journal.configs) == 1
    assert journal.configs[0].command_id == command.command_id
    assert (
        journal.configs[0].command_digest
        == inbox.application(command.command_id).digest
    )
    assert journal.stop_bindings[0].version == 1
    assert journal.controls == ()
    assert journal.requests == ()
    assert inbox.application(command.command_id).state == "APPLIED"

    revision = journal.revision
    reopened_inbox = make_inbox(inbox.path)
    reopened_ledger = Ledger(ledger_path, lease)
    replay = ConfigApplyCoordinator(reopened_inbox, reopened_ledger).apply(
        command.command_id
    )
    assert replay.state == "APPLIED"
    assert reopened_ledger.snapshot().revision == revision


def test_restart_resumes_after_ledger_commit_before_inbox_ack(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger_path = tmp_path / "execution.sqlite3"
    command = make_command(version=1, expected_version=0)
    receive(inbox, command)
    application = inbox.begin_apply(command.command_id)
    assert application.state == "APPLYING"

    # Simulate process loss after the local DB commit and before inbox acknowledgement.
    ledger = prepare_ledger(ledger_path, lease)
    _ = ledger.apply_inbox_config(command, command_digest=application.digest)
    assert inbox.application(command.command_id).state == "APPLYING"

    restarted = ConfigApplyCoordinator(
        make_inbox(inbox.path), Ledger(ledger_path, lease)
    )
    results = restarted.resume_applying()
    assert len(results) == 1
    assert (results[0].state, results[0].applied_version) == ("APPLIED", 1)
    assert len(restarted.ledger.snapshot().configs) == 1
    assert len(restarted.ledger.snapshot().stop_bindings) == 1


def test_restart_resumes_after_apply_claim_before_ledger_commit(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger_path = tmp_path / "execution.sqlite3"
    command = make_command(version=1, expected_version=0)
    receive(inbox, command)
    assert inbox.begin_apply(command.command_id).state == "APPLYING"

    restarted = ConfigApplyCoordinator(
        make_inbox(inbox.path), prepare_ledger(ledger_path, lease)
    )
    results = restarted.resume_applying()

    assert len(results) == 1
    assert (results[0].state, results[0].applied_version) == ("APPLIED", 1)
    assert len(restarted.ledger.snapshot().configs) == 1


def test_accepted_but_not_started_command_resumes_only_after_ledger_review(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger_path = tmp_path / "execution.sqlite3"
    command = make_command(version=1, expected_version=0)
    receive(inbox, command)
    unrestored_ledger = Ledger(ledger_path, lease)
    coordinator = ConfigApplyCoordinator(inbox, unrestored_ledger)

    with pytest.raises(LedgerError, match="SESSION_RECONCILIATION_REQUIRED"):
        _ = coordinator.apply(command.command_id)
    assert inbox.application(command.command_id).state == "NOT_APPLIED"

    reviewed_ledger = prepare_ledger(ledger_path, lease)
    restarted = ConfigApplyCoordinator(make_inbox(inbox.path), reviewed_ledger)
    results = restarted.resume_pending()
    assert len(results) == 1
    assert (results[0].state, results[0].applied_version) == ("APPLIED", 1)


def test_reverse_accepted_command_is_blocked_then_explicitly_retryable(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger = prepare_ledger(tmp_path / "execution.sqlite3", lease)
    older = make_command(version=1, expected_version=0)
    newer = make_command(version=2, expected_version=1)
    receive(inbox, older)
    receive(inbox, newer)
    coordinator = ConfigApplyCoordinator(inbox, ledger)

    reversed_attempt = coordinator.apply(newer.command_id)
    assert (reversed_attempt.state, reversed_attempt.reason) == (
        "APPLY_BLOCKED",
        "STALE_CONFIG_VERSION",
    )
    assert ledger.snapshot().configs == ()
    assert coordinator.apply(older.command_id).state == "APPLIED"
    assert coordinator.apply(newer.command_id).state == "APPLY_BLOCKED"
    retried = coordinator.apply(newer.command_id, retry_blocked=True)
    assert (retried.state, retried.applied_version) == ("APPLIED", 2)
    assert [config.version for config in ledger.snapshot().configs] == [1, 2]


def test_version_conflict_keeps_prior_applied_config_and_rule(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger = prepare_ledger(tmp_path / "execution.sqlite3", lease)
    prior = VirtualStopBinding(
        symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9700"
    )
    ledger.apply_virtual_stop_config(prior, expected_version=1)
    command = make_command(version=1, expected_version=0)
    receive(inbox, command)
    before = ledger.snapshot()

    result = ConfigApplyCoordinator(inbox, ledger).apply(command.command_id)

    assert (result.state, result.reason) == (
        "APPLY_BLOCKED",
        "STALE_CONFIG_VERSION",
    )
    assert ledger.snapshot() == before
    assert ledger.virtual_stop_binding("005930") == prior


def test_new_setting_does_not_rewrite_rule_assigned_to_existing_holding(
    tmp_path: Path, lease: AccountLease
) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    ledger = prepare_ledger(tmp_path / "execution.sqlite3", lease)
    first = make_command(version=1, expected_version=0)
    receive(inbox, first)
    coordinator = ConfigApplyCoordinator(inbox, ledger)
    assert coordinator.apply(first.command_id).state == "APPLIED"

    buy = ledger.submit(
        New(
            key="buy-under-v1",
            symbol="005930",
            side="BUY",
            config_version=1,
            qty=2,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    fill = Fill(
        event_id=uuid4(),
        order_id=buy.order_id,
        qty=2,
        remaining=0,
        evidence_version=1,
    )
    assert ledger.ingest(fill)
    assignments_before = ledger.snapshot().stop_assignments
    assert confirmed_stop_holdings(ledger.snapshot(), "005930").rule_version == 1

    second = first.model_copy(
        update={
            "command_id": uuid4(),
            "idempotency_key": "settings-revision-2",
            "expected_version": 1,
            "expires_at": NOW + timedelta(minutes=10),
            "settings": first.settings.model_copy(update={"version": 2}),
        }
    )
    assert second.settings.version == 2
    assert second.settings.stop_pattern.version == 1
    receive(inbox, second)
    assert coordinator.apply(second.command_id).state == "APPLIED"

    journal = ledger.snapshot()
    assert journal.stop_assignments == assignments_before
    assert confirmed_stop_holdings(journal, "005930").rule_version == 1
    assert {binding.version for binding in journal.stop_bindings} == {1, 2}
    assert ledger.virtual_stop_binding("005930").version == 2


def test_inbox_and_execution_ledger_must_remain_distinct_files(
    tmp_path: Path, lease: AccountLease
) -> None:
    shared_path = tmp_path / "shared.sqlite3"
    ledger = prepare_ledger(shared_path, lease)
    inbox = make_inbox(shared_path)
    with pytest.raises(ValueError, match="CONFIG_STORES_MUST_BE_SEPARATE"):
        _ = ConfigApplyCoordinator(inbox, ledger)


def test_missing_or_wrong_auth_context_cannot_be_accepted(tmp_path: Path) -> None:
    inbox = make_inbox(tmp_path / "desired.sqlite3")
    command = make_command(version=1, expected_version=0)

    missing = inbox.receive(command, NOW)
    invalid = inbox.receive(command, NOW, auth_context=object())

    assert missing.reason == "CONFIG_AUTHENTICATION_EVIDENCE_REQUIRED"
    assert invalid.reason == "CONFIG_AUTHENTICATION_FAILED"
    with pytest.raises(ConfigInboxError, match="CONFIG_COMMAND_NOT_FOUND"):
        _ = inbox.application(command.command_id)
