"""Observe stops without creating a trade from incomplete market evidence."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from contracts.settings import StopRule
from contracts.stop_evaluation import (
    ConfirmedBuyFill,
    ManagedPosition,
    ObserveAt,
    ProtectionExposure,
    Quote,
    average_buy_cost,
    evaluate_stop,
    protection_candidate,
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


def test_fixed_price_needs_no_cost_but_percentage_needs_confirmed_cost() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    position = ManagedPosition(symbol="005930", confirmed_qty=2)
    quote = Quote(symbol="005930", price="9700", received_at=now)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    fixed = evaluate_stop(
        position, quote, StopRule(kind="PRICE_AT_OR_BELOW", threshold="9800"), timing
    )
    percent = evaluate_stop(
        position, quote, StopRule(kind="AVERAGE_COST_DROP", threshold="0.02"), timing
    )
    assert fixed.status == "TRIGGERED"
    assert (percent.status, percent.reason) == ("UNAVAILABLE", "AVERAGE_COST_MISSING")


def test_nonfinite_market_inputs_are_rejected() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        _ = ManagedPosition(symbol="005930", confirmed_qty=1, average_cost="Infinity")
    with pytest.raises(ValidationError):
        _ = Quote(symbol="005930", price="NaN", received_at=now)


def test_partial_fill_protection_and_existing_sell_reservation() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    rule = StopRule(kind="AVERAGE_COST_DROP", threshold="0.02")
    quote = Quote(symbol="005930", price="9700", received_at=now)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    for owned, reserved, expected in ((4, 0, 4), (4, 4, 0), (7, 4, 3)):
        position = ManagedPosition(
            symbol="005930", confirmed_qty=owned, average_cost="10000"
        )
        observed = evaluate_stop(
            position,
            quote,
            rule,
            timing,
        )
        result = protection_candidate(
            observed,
            position,
            ProtectionExposure(
                managed_qty=owned,
                reserved_sell_qty=reserved,
                reconciliation_required=False,
                sell_uncertain=False,
            ),
        )
        assert result.unreserved_qty == expected
        assert result.status == ("CANDIDATE" if expected else "NONE")


@pytest.mark.parametrize(
    ("reconciliation_required", "sell_uncertain"),
    [(True, False), (False, True), (True, True)],
)
def test_unknown_sell_or_restart_reconciliation_blocks_new_candidate(
    *, reconciliation_required: bool, sell_uncertain: bool
) -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    position = ManagedPosition(symbol="005930", confirmed_qty=4, average_cost="10000")
    observation = evaluate_stop(
        position,
        Quote(symbol="005930", price="9000", received_at=now),
        StopRule(kind="PRICE_AT_OR_BELOW", threshold="9500"),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    decision = protection_candidate(
        observation,
        position,
        ProtectionExposure(
            managed_qty=4,
            reserved_sell_qty=0,
            reconciliation_required=reconciliation_required,
            sell_uncertain=sell_uncertain,
        ),
    )
    assert (decision.status, decision.unreserved_qty) == ("BLOCKED", 0)


def test_mismatched_position_and_ledger_quantities_are_blocked() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    position = ManagedPosition(symbol="005930", confirmed_qty=4, average_cost="10000")
    observation = evaluate_stop(
        position,
        Quote(symbol="005930", price="9000", received_at=now),
        StopRule(kind="PRICE_AT_OR_BELOW", threshold="9500"),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    candidate = protection_candidate(
        observation,
        position,
        ProtectionExposure(
            managed_qty=7,
            reserved_sell_qty=0,
            reconciliation_required=False,
            sell_uncertain=False,
        ),
    )
    assert (candidate.status, candidate.reason) == (
        "BLOCKED",
        "POSITION_EVIDENCE_MISMATCH",
    )


def test_confirmed_buy_cost_is_weighted_and_ignores_fees() -> None:
    fills = (
        ConfirmedBuyFill(qty=2, price="10000"),
        ConfirmedBuyFill(qty=1, price="9700"),
    )
    assert average_buy_cost(fills) == 9900
    with pytest.raises(ValueError, match="CONFIRMED_BUY_FILLS_REQUIRED"):
        _ = average_buy_cost(())
    with pytest.raises(ValidationError):
        _ = ConfirmedBuyFill(qty=1, price="Infinity")
    with pytest.raises(ValidationError):
        _ = Quote(
            symbol="005930",
            source="BID",
            price="9700",
            received_at=datetime.now(timezone.utc),
        )
