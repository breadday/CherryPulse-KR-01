"""D01 desired settings cannot silently become active trading instructions."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.inbox import CommandConflictError, ConfigInbox
from contracts.settings import Actor, ConfigCommand, Pattern, Settings, StopRule, decide


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
    """Simulate claims received from an authenticated adapter."""
    return Actor(
        actor_id="owner",
        account_id="DEMO",
        environment="PAPER",
        permissions=frozenset({"CONFIG_WRITE"}),
    )


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
    inbox = ConfigInbox(path)
    accepted = inbox.receive(request, actor(), now)
    assert accepted.state == "ACCEPTED"
    assert (
        ConfigInbox(path).receive(
            request, actor(), request.expires_at + timedelta(days=1)
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
    assert ConfigInbox(path).receive(newer, actor(), now).state == "ACCEPTED"
    stale = newer.model_copy(
        update={"command_id": uuid4(), "idempotency_key": "setting-3"}
    )
    assert inbox.receive(stale, actor(), now).reason == "STALE_CONFIG_VERSION"


def test_inbox_rejects_changed_identity_and_unauthorized_replay(tmp_path: Path) -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    request = command(now)
    inbox = ConfigInbox(tmp_path / "desired-settings.sqlite3")
    assert inbox.receive(request, actor(), now).state == "ACCEPTED"
    with pytest.raises(CommandConflictError, match="CONFLICT_CONFIG_COMMAND_IDENTITY"):
        _ = inbox.receive(
            request.model_copy(update={"command_id": uuid4()}), actor(), now
        )
    unauthorized = actor().model_copy(update={"permissions": frozenset()})
    assert inbox.receive(request, unauthorized, now).reason == "CONFIG_UNAUTHORIZED"
