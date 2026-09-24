"""Observe stops without creating a trade from incomplete market evidence."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from contracts.settings import StopRule
from contracts.stop_evaluation import (
    ManagedPosition,
    ObserveAt,
    Quote,
    evaluate_stop,
)


def test_both_configurable_stop_rules_use_exact_decimal_thresholds() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    position = ManagedPosition(symbol="005930", confirmed_qty=3, average_cost="10000")
    quote = Quote(symbol="005930", price="9799", received_at=now)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    percent = StopRule(kind="AVERAGE_COST_DROP", threshold="0.02")
    absolute = StopRule(kind="PRICE_AT_OR_BELOW", threshold="9800")
    assert evaluate_stop(position, quote, percent, timing).status == "TRIGGERED"
    assert evaluate_stop(position, quote, absolute, timing).threshold_price == 9800
    assert (
        evaluate_stop(
            position,
            quote,
            StopRule(kind="PRICE_AT_OR_BELOW", threshold="9700"),
            timing,
        ).status
        == "NOT_TRIGGERED"
    )


def test_missing_stale_future_or_wrong_symbol_quote_cannot_trigger() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    position = ManagedPosition(symbol="005930", confirmed_qty=1, average_cost="10000")
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    rule = StopRule(kind="PRICE_AT_OR_BELOW", threshold="9800")
    assert evaluate_stop(position, None, rule, timing).status == "UNAVAILABLE"
    for quote in (
        Quote(symbol="000660", price="9000", received_at=now),
        Quote(symbol="005930", price="9000", received_at=now - timedelta(seconds=3)),
        Quote(symbol="005930", price="9000", received_at=now + timedelta(seconds=1)),
    ):
        assert evaluate_stop(position, quote, rule, timing).status == "UNAVAILABLE"


def test_no_confirmed_shares_cannot_trigger() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    position = ManagedPosition(symbol="005930", confirmed_qty=0, average_cost="10000")
    quote = Quote(symbol="005930", price="9000", received_at=now)
    result = evaluate_stop(
        position,
        quote,
        StopRule(kind="PRICE_AT_OR_BELOW", threshold="9800"),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    assert result.reason == "NO_MANAGED_POSITION"


def test_nonfinite_market_inputs_are_rejected() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        _ = ManagedPosition(symbol="005930", confirmed_qty=1, average_cost="Infinity")
    with pytest.raises(ValidationError):
        _ = Quote(symbol="005930", price="NaN", received_at=now)
