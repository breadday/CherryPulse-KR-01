"""Pure D08 polling timing and response classification; no network I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

POLL_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 3
INITIAL_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 5 * 60

PollStatus = Literal["NORMAL", "RETRY_WAIT", "OPERATOR_REVIEW"]
PollOutcome = Literal["SUCCESS", "NETWORK_ERROR", "TIMEOUT"]


@dataclass(frozen=True, slots=True)
class PollingState:
    """Durable-caller state needed to resume one engine polling schedule."""

    status: PollStatus = "NORMAL"
    consecutive_failures: int = 0
    next_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    operator_reason: str | None = None


def _require_aware(value: datetime) -> None:
    """Reject naive clocks so persisted retry deadlines are unambiguous."""
    if value.utcoffset() is None:
        raise ValueError("POLL_CLOCK_TIMEZONE_REQUIRED")


def retry_delay_seconds(consecutive_failures: int) -> int:
    """Return 5, 10, 20... seconds, capped at five minutes."""
    if consecutive_failures < 1:
        raise ValueError("POLL_FAILURE_COUNT_MUST_BE_POSITIVE")
    if consecutive_failures >= 7:
        return MAX_BACKOFF_SECONDS
    return INITIAL_BACKOFF_SECONDS * (2 ** (consecutive_failures - 1))


def record_poll_outcome(
    state: PollingState,
    outcome: PollOutcome | int,
    occurred_at: datetime,
    *,
    operator_review_resolved: bool = False,
) -> PollingState:
    """Apply D08 response policy without making a request or applying commands."""
    _require_aware(occurred_at)
    if state.status == "OPERATOR_REVIEW" and not operator_review_resolved:
        return state

    if outcome == "SUCCESS" or (isinstance(outcome, int) and 200 <= outcome < 300):
        return PollingState(
            status="NORMAL",
            consecutive_failures=0,
            next_attempt_at=occurred_at + timedelta(seconds=POLL_INTERVAL_SECONDS),
            last_success_at=occurred_at,
        )

    if isinstance(outcome, int) and 400 <= outcome < 500:
        return PollingState(
            status="OPERATOR_REVIEW",
            consecutive_failures=state.consecutive_failures,
            last_success_at=state.last_success_at,
            operator_reason=f"HTTP_{outcome}",
        )

    retryable = outcome in ("NETWORK_ERROR", "TIMEOUT") or (
        isinstance(outcome, int) and 500 <= outcome < 600
    )
    if retryable:
        failures = state.consecutive_failures + 1
        delay = retry_delay_seconds(failures)
        return PollingState(
            status="RETRY_WAIT",
            consecutive_failures=failures,
            next_attempt_at=occurred_at + timedelta(seconds=delay),
            last_success_at=state.last_success_at,
        )

    return PollingState(
        status="OPERATOR_REVIEW",
        consecutive_failures=state.consecutive_failures,
        last_success_at=state.last_success_at,
        operator_reason="UNEXPECTED_RESPONSE",
    )
