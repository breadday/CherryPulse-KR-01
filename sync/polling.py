"""Pure D08 polling timing and response classification; no network I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

POLL_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 3
INITIAL_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 5 * 60
BACKOFF_CAP_FAILURE_COUNT = 7

HTTP_STATUS_SUCCESS_MIN = 200
HTTP_STATUS_SUCCESS_MAX_EXCLUSIVE = 300
HTTP_STATUS_CLIENT_ERROR_MIN = 400
HTTP_STATUS_CLIENT_ERROR_MAX_EXCLUSIVE = 500
HTTP_STATUS_SERVER_ERROR_MIN = 500
HTTP_STATUS_SERVER_ERROR_MAX_EXCLUSIVE = 600

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
    if consecutive_failures >= BACKOFF_CAP_FAILURE_COUNT:
        return MAX_BACKOFF_SECONDS
    return INITIAL_BACKOFF_SECONDS * (1 << (consecutive_failures - 1))


OutcomeClass = Literal["SUCCESS", "RETRYABLE", "CLIENT_ERROR", "UNEXPECTED_RESPONSE"]

_HTTP_STATUS_BANDS: tuple[tuple[int, int, OutcomeClass], ...] = (
    (HTTP_STATUS_SUCCESS_MIN, HTTP_STATUS_SUCCESS_MAX_EXCLUSIVE, "SUCCESS"),
    (
        HTTP_STATUS_CLIENT_ERROR_MIN,
        HTTP_STATUS_CLIENT_ERROR_MAX_EXCLUSIVE,
        "CLIENT_ERROR",
    ),
    (
        HTTP_STATUS_SERVER_ERROR_MIN,
        HTTP_STATUS_SERVER_ERROR_MAX_EXCLUSIVE,
        "RETRYABLE",
    ),
)

_STRING_OUTCOME_CLASS: dict[str, OutcomeClass] = {
    "SUCCESS": "SUCCESS",
    "NETWORK_ERROR": "RETRYABLE",
    "TIMEOUT": "RETRYABLE",
}


def _classify_poll_outcome(outcome: PollOutcome | int) -> OutcomeClass:
    """Group declared poll outcomes and numeric statuses with no I/O."""
    if isinstance(outcome, int):
        for low, high, kind in _HTTP_STATUS_BANDS:
            if low <= outcome < high:
                return kind
        return "UNEXPECTED_RESPONSE"
    classified = _STRING_OUTCOME_CLASS.get(outcome)
    if classified is not None:
        return classified
    return "UNEXPECTED_RESPONSE"


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

    classified = _classify_poll_outcome(outcome)
    if classified == "SUCCESS":
        return PollingState(
            status="NORMAL",
            consecutive_failures=0,
            next_attempt_at=occurred_at + timedelta(seconds=POLL_INTERVAL_SECONDS),
            last_success_at=occurred_at,
        )

    if classified == "CLIENT_ERROR":
        return PollingState(
            status="OPERATOR_REVIEW",
            consecutive_failures=state.consecutive_failures,
            last_success_at=state.last_success_at,
            operator_reason=f"HTTP_{outcome}",
        )

    if classified == "RETRYABLE":
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
