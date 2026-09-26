"""D01 desired settings cannot silently become active trading instructions."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.inbox import CommandConflictError, ConfigInbox
from contracts.settings import (
    Actor,
    ConfigCommand,
    Pattern,
    Settings,
    StopRule,
    decide,
    digest,
)

AUTH_CONTEXT = "verified-test-context"


def command(now: datetime) -> ConfigCommand:
    """Create an inert desired stop rule for the virtual account."""
    return ConfigCommand(
        command_id=uuid4(),
        idempotency_key="setting-1",
        expected_version=0,
        expires_at=now + timedelta(minutes=1),
        settings=Settings(
            account_id="DEMO",
            environment="PAPER",
            symbol="005930",
            version=1,
            stop_pattern=Pattern(
                pattern_id=uuid4(),
                version=1,
                name="가격 손절 예시",
                side="SELL",
                stop=StopRule(kind="PRICE_AT_OR_BELOW", threshold="10000"),
            ),
        ),
    )


def actor() -> Actor:
    """Claims returned by the test-only authentication adapter."""
    return Actor(
        actor_id="owner",
        account_id="DEMO",
        environment="PAPER",
        permissions=frozenset({"CONFIG_WRITE"}),
    )


class FakeConfigAuthenticator:
    """Test seam only; production has no configured identity provider."""

    def __init__(self, verified_actor: Actor | None = None) -> None:
        self.verified_actor = verified_actor or actor()

    def authenticate(self, request: ConfigCommand, context: object) -> Actor | None:
        _ = request
        return self.verified_actor if context == AUTH_CONTEXT else None


def inbox(path: Path) -> ConfigInbox:
    """Create an inbox with a deliberately test-only verifier."""
    return ConfigInbox(path, authenticator=FakeConfigAuthenticator())


def test_desired_settings_acceptance_is_only_a_pure_decision() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    request = command(now)
    result = decide(request, actor(), current_version=0, now=now)
    assert result.state == "ACCEPTED"
    assert result.digest == decide(request, actor(), current_version=0, now=now).digest
    assert request.settings.monitoring_enabled is False
    assert request.settings.entry_enabled is False


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"account_id": "OTHER"}, "CONFIG_UNAUTHORIZED"),
        ({"permissions": frozenset()}, "CONFIG_UNAUTHORIZED"),
        ({"environment": "LIVE"}, "CONFIG_UNAUTHORIZED"),
    ],
)
def test_wrong_scope_or_permission_is_rejected(
    change: dict[str, object], reason: str
) -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    result = decide(
        command(now), actor().model_copy(update=change), current_version=0, now=now
    )
    assert (result.state, result.reason) == ("REJECTED", reason)


def test_expired_and_stale_commands_are_rejected() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    request = command(now)
    assert (
        decide(request, actor(), current_version=0, now=request.expires_at).reason
        == "COMMAND_EXPIRED"
    )
    assert (
        decide(request, actor(), current_version=1, now=now).reason
        == "STALE_CONFIG_VERSION"
    )


def test_rule_rejects_missing_policy_activation_and_invalid_fraction() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    desired = command(now).settings
    with pytest.raises(ValidationError, match="PATTERN_EXECUTION_NOT_SPECIFIED"):
        _ = Settings.model_validate(
            {**desired.model_dump(mode="json"), "monitoring_enabled": True}
        )
    with pytest.raises(ValidationError, match="INVALID_STOP_THRESHOLD"):
        _ = StopRule(kind="AVERAGE_COST_DROP", threshold="1.1")
    with pytest.raises(ValidationError, match="DECIMAL_STRING_REQUIRED"):
        _ = StopRule.model_validate({"kind": "PRICE_AT_OR_BELOW", "threshold": 9800.0})


def test_inbox_replays_after_restart_without_advancing_version(tmp_path: Path) -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    request = command(now)
    path = tmp_path / "desired-settings.sqlite3"
    settings_inbox = inbox(path)
    accepted = settings_inbox.receive(request, now, auth_context=AUTH_CONTEXT)
    assert accepted.state == "ACCEPTED"
    assert (
        inbox(path).receive(
            request,
            request.expires_at + timedelta(days=1),
            auth_context=AUTH_CONTEXT,
        )
        == accepted
    )
    newer = request.model_copy(
        update={
            "command_id": uuid4(),
            "idempotency_key": "setting-2",
            "expected_version": 1,
            "expires_at": now + timedelta(minutes=2),
            "settings": request.settings.model_copy(update={"version": 2}),
        }
    )
    assert (
        inbox(path).receive(newer, now, auth_context=AUTH_CONTEXT).state == "ACCEPTED"
    )
    stale = newer.model_copy(
        update={"command_id": uuid4(), "idempotency_key": "setting-3"}
    )
    assert (
        settings_inbox.receive(stale, now, auth_context=AUTH_CONTEXT).reason
        == "STALE_CONFIG_VERSION"
    )


def test_inbox_rejects_changed_identity_and_unauthorized_replay(tmp_path: Path) -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    request = command(now)
    settings_inbox = inbox(tmp_path / "desired-settings.sqlite3")
    assert (
        settings_inbox.receive(request, now, auth_context=AUTH_CONTEXT).state
        == "ACCEPTED"
    )
    with pytest.raises(CommandConflictError, match="CONFLICT_CONFIG_COMMAND_IDENTITY"):
        _ = settings_inbox.receive(
            request.model_copy(update={"command_id": uuid4()}),
            now,
            auth_context=AUTH_CONTEXT,
        )
    unauthorized_inbox = ConfigInbox(
        tmp_path / "unauthorized-settings.sqlite3",
        authenticator=FakeConfigAuthenticator(
            actor().model_copy(update={"permissions": frozenset()})
        ),
    )
    assert (
        unauthorized_inbox.receive(request, now, auth_context=AUTH_CONTEXT).reason
        == "CONFIG_UNAUTHORIZED"
    )


def test_inbox_rejects_command_id_reused_for_another_symbol(tmp_path: Path) -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    request = command(now)
    settings_inbox = inbox(tmp_path / "desired-settings.sqlite3")
    assert (
        settings_inbox.receive(request, now, auth_context=AUTH_CONTEXT).state
        == "ACCEPTED"
    )
    other = request.model_copy(
        update={
            "idempotency_key": "another-symbol",
            "settings": request.settings.model_copy(update={"symbol": "000660"}),
        }
    )
    with pytest.raises(CommandConflictError, match="CONFLICT_CONFIG_COMMAND_IDENTITY"):
        _ = settings_inbox.receive(other, now, auth_context=AUTH_CONTEXT)
    assert (
        settings_inbox.receive(request, now, auth_context=AUTH_CONTEXT).state
        == "ACCEPTED"
    )


def test_legacy_actor_claim_acceptance_is_blocked_during_apply_state_migration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-inbox.sqlite3"
    request = command(datetime(2026, 9, 24, tzinfo=timezone.utc))
    with sqlite3.connect(path) as connection:
        _ = connection.execute(
            """CREATE TABLE config_commands (
              account_id TEXT NOT NULL, environment TEXT NOT NULL,
              symbol TEXT NOT NULL, idempotency_key TEXT NOT NULL,
              command_id TEXT NOT NULL, payload TEXT NOT NULL,
              digest TEXT NOT NULL, decision TEXT NOT NULL,
              reason TEXT NOT NULL, accepted_version INTEGER,
              actor_id TEXT NOT NULL,
              PRIMARY KEY (account_id, environment, symbol, idempotency_key),
              UNIQUE (account_id, environment, command_id))"""
        )
        _ = connection.execute(
            """INSERT INTO config_commands VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request.settings.account_id,
                request.settings.environment,
                request.settings.symbol,
                request.idempotency_key,
                str(request.command_id),
                request.model_dump_json(),
                digest(request),
                "ACCEPTED",
                "ACCEPTED",
                request.settings.version,
                "legacy-actor-claim",
            ),
        )

    migrated = inbox(path).application(request.command_id)
    assert (migrated.state, migrated.reason) == (
        "APPLY_BLOCKED",
        "LEGACY_AUTHENTICATION_UNVERIFIED",
    )
    assert inbox(path).begin_apply(request.command_id, retry_blocked=True).state == (
        "APPLY_BLOCKED"
    )
    replacement_now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    replacement = command(replacement_now).model_copy(
        update={"command_id": uuid4(), "idempotency_key": "replacement-after-migration"}
    )
    assert (
        inbox(path)
        .receive(
            replacement,
            replacement_now,
            auth_context=AUTH_CONTEXT,
        )
        .state
        == "ACCEPTED"
    )
