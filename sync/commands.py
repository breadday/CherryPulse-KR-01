"""Local command-sync boundary without cloud, auth, or account side effects."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Mapping


_IDENTIFIER_PATTERN = r"^[!-~]+$"


@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str
    account_id: str
    expected_version: int
    next_version: int
    payload: Mapping[str, object]
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        import re

        if not isinstance(self.command_id, str) or re.fullmatch(_IDENTIFIER_PATTERN, self.command_id) is None:
            raise ValueError("INVALID_COMMAND_ID")
        if not isinstance(self.account_id, str) or re.fullmatch(_IDENTIFIER_PATTERN, self.account_id) is None:
            raise ValueError("INVALID_ACCOUNT_ID")
        if isinstance(self.expected_version, bool) or not isinstance(self.expected_version, int):
            raise ValueError("INVALID_EXPECTED_VERSION")
        if self.expected_version < 0:
            raise ValueError("INVALID_EXPECTED_VERSION")
        if isinstance(self.next_version, bool) or not isinstance(self.next_version, int):
            raise ValueError("INVALID_NEXT_VERSION")
        if self.next_version <= self.expected_version:
            raise ValueError("INVALID_NEXT_VERSION")
        if not isinstance(self.issued_at, datetime) or not isinstance(self.expires_at, datetime):
            raise ValueError("COMMAND_TIMEZONE_REQUIRED")
        try:
            issued_offset = self.issued_at.utcoffset()
            expires_offset = self.expires_at.utcoffset()
        except (AttributeError, TypeError, ValueError):
            raise ValueError("COMMAND_TIMEZONE_REQUIRED") from None
        if issued_offset is None or expires_offset is None:
            raise ValueError("COMMAND_TIMEZONE_REQUIRED")
        if self.expires_at <= self.issued_at:
            raise ValueError("COMMAND_EXPIRY_INVALID")
        if not isinstance(self.payload, Mapping):
            raise ValueError("COMMAND_PAYLOAD_INVALID")


class CommandInbox:
    """In-memory receiver model for versioned command delivery tests."""

    def __init__(self, *, current_version: int, clock: Callable[[], datetime] | None = None) -> None:
        if isinstance(current_version, bool) or not isinstance(current_version, int) or current_version < 0:
            raise ValueError("INVALID_CURRENT_VERSION")
        self._current_version = current_version
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._commands: dict[str, CommandEnvelope] = {}
        self._history: list[CommandEnvelope] = []
        self._lock = RLock()

    def receive(self, command: CommandEnvelope) -> str:
        with self._lock:
            if not isinstance(command, CommandEnvelope):
                raise ValueError("COMMAND_INVALID")
            previous = self._commands.get(command.command_id)
            if previous is not None:
                if previous == command:
                    return "DUPLICATE"
                raise ValueError("COMMAND_ID_CONFLICT")
            now = self._clock()
            if not isinstance(now, datetime):
                raise ValueError("CLOCK_TIMEZONE_REQUIRED")
            try:
                clock_offset = now.utcoffset()
            except (AttributeError, TypeError, ValueError):
                raise ValueError("CLOCK_TIMEZONE_REQUIRED") from None
            if clock_offset is None:
                raise ValueError("CLOCK_TIMEZONE_REQUIRED")
            if command.expires_at <= now:
                raise ValueError("COMMAND_EXPIRED")
            if command.expected_version != self._current_version:
                raise ValueError("STALE_COMMAND_VERSION")
            stored = deepcopy(command)
            self._commands[command.command_id] = stored
            self._history.append(stored)
            self._current_version = command.next_version
            return "ACCEPTED"

    def history(self) -> tuple[CommandEnvelope, ...]:
        with self._lock:
            return tuple(deepcopy(command) for command in self._history)
