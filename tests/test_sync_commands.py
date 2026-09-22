from datetime import datetime, timedelta, tzinfo, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from sync.commands import CommandEnvelope, CommandInbox


NOW = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)


def envelope(
    *, command_id: str = "cmd-1", expected_version: int = 3, next_version: int = 4, payload=None, expires_at=None
):
    return CommandEnvelope(
        command_id=command_id,
        account_id="paper-account",
        expected_version=expected_version,
        next_version=next_version,
        payload={"kind": "APPLY_CONFIG", "value": payload or {"version": 4}},
        issued_at=NOW - timedelta(seconds=1),
        expires_at=expires_at or NOW + timedelta(minutes=1),
    )


def test_command_inbox_accepts_exact_command_once_and_deduplicates_replay() -> None:
    current_time = [NOW]
    inbox = CommandInbox(current_version=3, clock=lambda: current_time[0])
    command = envelope()

    assert inbox.receive(command) == "ACCEPTED"
    current_time[0] = command.expires_at + timedelta(seconds=1)
    assert inbox.receive(command) == "DUPLICATE"
    assert inbox.history() == (command,)


def test_command_inbox_advances_version_after_acceptance() -> None:
    inbox = CommandInbox(current_version=3, clock=lambda: NOW)

    assert inbox.receive(envelope()) == "ACCEPTED"
    assert inbox.receive(envelope(command_id="cmd-2", expected_version=4, next_version=5)) == "ACCEPTED"
    with pytest.raises(ValueError, match="STALE_COMMAND_VERSION"):
        inbox.receive(envelope(command_id="cmd-3", expected_version=3, next_version=4))


def test_command_inbox_rejects_stale_version_without_recording() -> None:
    inbox = CommandInbox(current_version=4, clock=lambda: NOW)

    with pytest.raises(ValueError, match="STALE_COMMAND_VERSION"):
        inbox.receive(envelope(expected_version=3))

    assert inbox.history() == ()


def test_command_inbox_rejects_expired_command_without_recording() -> None:
    inbox = CommandInbox(current_version=3, clock=lambda: NOW)
    expired = envelope(expires_at=NOW - timedelta(microseconds=500_000))

    with pytest.raises(ValueError, match="COMMAND_EXPIRED"):
        inbox.receive(expired)

    assert inbox.history() == ()


def test_command_inbox_rejects_conflicting_reuse_of_command_id() -> None:
    inbox = CommandInbox(current_version=3, clock=lambda: NOW)
    assert inbox.receive(envelope()) == "ACCEPTED"

    with pytest.raises(ValueError, match="COMMAND_ID_CONFLICT"):
        inbox.receive(envelope(payload={"version": 5}))


def test_command_inbox_is_atomic_for_concurrent_replay() -> None:
    inbox = CommandInbox(current_version=3, clock=lambda: NOW)
    command = envelope()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(inbox.receive, [command, command]))

    assert sorted(results) == ["ACCEPTED", "DUPLICATE"]
    assert inbox.history() == (command,)


def test_command_envelope_rejects_malformed_types_with_value_error() -> None:
    with pytest.raises(ValueError, match="INVALID_COMMAND_ID"):
        CommandEnvelope(123, "paper-account", 3, 4, {"kind": "X"}, NOW, NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="COMMAND_TIMEZONE_REQUIRED"):
        CommandEnvelope("cmd-1", "paper-account", 3, 4, {"kind": "X"}, "now", NOW)  # type: ignore[arg-type]


class _InvalidOffset(tzinfo):
    def utcoffset(self, dt):
        return None


def test_command_inbox_rejects_clock_without_usable_timezone() -> None:
    invalid_now = datetime(2026, 9, 22, 15, 0, tzinfo=_InvalidOffset())
    inbox = CommandInbox(current_version=3, clock=lambda: invalid_now)

    with pytest.raises(ValueError, match="CLOCK_TIMEZONE_REQUIRED"):
        inbox.receive(envelope())


def test_command_inbox_rejects_non_envelope_runtime_input() -> None:
    inbox = CommandInbox(current_version=3, clock=lambda: NOW)

    with pytest.raises(ValueError, match="COMMAND_INVALID"):
        inbox.receive(object())  # type: ignore[arg-type]
