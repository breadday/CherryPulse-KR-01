"""Pure D08 polling timing and response classification."""

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from sync.polling import (
    BACKOFF_CAP_FAILURE_COUNT,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    POLL_INTERVAL_SECONDS,
    PollingState,
    PollOutcome,
    record_poll_outcome,
    retry_delay_seconds,
)

NOW = datetime(2026, 10, 29, tzinfo=UTC)


def test_retry_delay_doubles_until_cap() -> None:
    expected = [INITIAL_BACKOFF_SECONDS * (1 << count) for count in range(6)]
    for failures, delay in enumerate(expected, start=1):
        assert retry_delay_seconds(failures) == delay
    assert retry_delay_seconds(BACKOFF_CAP_FAILURE_COUNT) == MAX_BACKOFF_SECONDS
    assert retry_delay_seconds(BACKOFF_CAP_FAILURE_COUNT + 3) == MAX_BACKOFF_SECONDS


def test_retry_delay_requires_positive_failure_count() -> None:
    with pytest.raises(ValueError, match="POLL_FAILURE_COUNT_MUST_BE_POSITIVE"):
        _ = retry_delay_seconds(0)
    with pytest.raises(ValueError, match="POLL_FAILURE_COUNT_MUST_BE_POSITIVE"):
        _ = retry_delay_seconds(-1)


def test_success_outcomes_reset_schedule() -> None:
    for outcome in ("SUCCESS", 200, 204, 299):
        state = record_poll_outcome(
            PollingState(status="RETRY_WAIT", consecutive_failures=3),
            outcome,
            NOW,
        )
        assert state.status == "NORMAL"
        assert state.consecutive_failures == 0
        assert state.next_attempt_at == NOW + timedelta(seconds=POLL_INTERVAL_SECONDS)
        assert state.last_success_at == NOW


def test_client_error_requires_operator_review() -> None:
    state = record_poll_outcome(PollingState(), 400, NOW)
    assert state.status == "OPERATOR_REVIEW"
    assert state.operator_reason == "HTTP_400"
    assert state.consecutive_failures == 0
    assert state.next_attempt_at is None
    blocked = record_poll_outcome(state, "SUCCESS", NOW)
    assert blocked is state


def test_resolved_operator_review_accepts_success() -> None:
    state = record_poll_outcome(
        PollingState(status="OPERATOR_REVIEW", operator_reason="HTTP_404"),
        "SUCCESS",
        NOW,
        operator_review_resolved=True,
    )
    assert state.status == "NORMAL"
    assert state.operator_reason is None
    assert state.last_success_at == NOW


@pytest.mark.parametrize("outcome", [500, 503, 599])
def test_numeric_server_error_schedules_backoff(outcome: int) -> None:
    state = record_poll_outcome(PollingState(), outcome, NOW)
    assert state.status == "RETRY_WAIT"
    assert state.next_attempt_at == NOW + timedelta(seconds=INITIAL_BACKOFF_SECONDS)
    assert state.consecutive_failures == 1
    again = record_poll_outcome(state, outcome, NOW + timedelta(seconds=60))
    assert again.consecutive_failures == 2
    assert again.next_attempt_at == NOW + timedelta(seconds=60 + 2 * 5)


def test_string_outcomes_are_not_numeric_statuses() -> None:
    for outcome in ("NETWORK_ERROR", "TIMEOUT"):
        state = record_poll_outcome(PollingState(), outcome, NOW)
        assert state.status == "RETRY_WAIT"
        assert state.next_attempt_at == NOW + timedelta(seconds=INITIAL_BACKOFF_SECONDS)
    bogus: PollOutcome = cast("PollOutcome", cast("object", "503"))
    reviewed = record_poll_outcome(PollingState(consecutive_failures=2), bogus, NOW)
    assert reviewed.status == "OPERATOR_REVIEW"
    assert reviewed.operator_reason == "UNEXPECTED_RESPONSE"
    assert reviewed.consecutive_failures == 2
    reused = record_poll_outcome(reviewed, bogus, NOW)
    assert reused is reviewed


def test_unclassified_int_statuses_require_operator_review() -> None:
    for outcome in (100, 300, 399, 600, 799):
        state = record_poll_outcome(PollingState(), outcome, NOW)
        assert state.status == "OPERATOR_REVIEW"
        assert state.operator_reason == "UNEXPECTED_RESPONSE"


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="POLL_CLOCK_TIMEZONE_REQUIRED"):
        _ = record_poll_outcome(PollingState(), "SUCCESS", NOW.replace(tzinfo=None))
