from uuid import uuid4

import pytest

from execution.facts import Discrepancy, Fill
from tests.conftest import Scenario


def test_t05_more_shares_when_buy_fill_arrives_during_liquidation(
    scenario: Scenario,
) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    _ = scenario.fill(buy, (40, 60))
    first_sell = scenario.new("SELL", 40)
    scenario.liquidate()
    scenario.dispatcher.calls.clear()
    cancel = scenario.cancel(buy, 60)
    # When
    late = Fill(
        event_id=uuid4(),
        order_id=buy.order_id,
        qty=20,
        remaining=40,
        evidence_version=2,
    )
    scenario.dispatcher.process(late)
    _ = scenario.cancelled(cancel, (40, 0))
    _ = scenario.fill(first_sell, (40, 0))
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved, position.liquidation) == (20, 20, 20)
    assert scenario.counts() == (1, 0, 1)
    scenario.replay()


def test_t06_ownership_unchanged_when_balance_discrepancy_repeats(
    scenario: Scenario,
) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    _ = scenario.fill(buy, (100, 0))
    scenario.dispatcher.calls.clear()
    # When: repeated incomplete evidence, with no invented correction or clock expiry.
    for _ in range(3):
        _ = scenario.book.ingest(
            Discrepancy(
                event_id=uuid4(), symbol="005930", reason="BALANCE_70_VS_MANAGED_100"
            )
        )
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (100, 0)
    assert position.reconciliation_required
    assert scenario.counts() == (0, 0, 0)
    scenario.replay()


@pytest.mark.parametrize("branch", ["A", "C", "D"])
def test_t12_late_buy_when_prior_liquidation_has_finished(
    scenario: Scenario, branch: str
) -> None:
    # Given
    buy = scenario.new("BUY", 120)
    _ = scenario.fill(buy, (80, 40))
    sold_qty = 60 if branch == "C" else 80
    prior_sell = scenario.new("SELL", sold_qty)
    _ = scenario.fill(prior_sell, (sold_qty, 0))
    if branch == "C":
        unresolved_sell = scenario.new("SELL", 20)
        unknown_cancel = scenario.cancel(unresolved_sell, 20)
        scenario.unknown(unknown_cancel)
    scenario.liquidate()
    scenario.dispatcher.calls.clear()
    buy_cancel = scenario.cancel(buy, 40)
    scenario.version = 4
    _ = scenario.cancelled(buy_cancel, (40 if branch == "D" else 20, 0))
    late = Fill(
        event_id=uuid4(),
        order_id=buy.order_id,
        qty=20,
        remaining=20,
        evidence_version=3,
    )
    # When
    scenario.dispatcher.process(late)
    scenario.dispatcher.process(late)
    # Then
    position = scenario.book.portfolio("005930")
    expected = {"A": (20, 20, 0, 1), "C": (40, 20, 0, 0), "D": (20, 0, -20, 0)}[branch]
    assert (
        position.managed,
        position.reserved,
        scenario.book.order(buy.order_id).gap,
        scenario.counts()[0],
    ) == expected
    assert position.liquidation == position.managed
    assert position.protected == position.managed
    assert scenario.counts()[1:] == (0, 1)
    if branch == "D":
        assert scenario.book.order(buy.order_id).cancelled == 40
        assert position.reconciliation_required
    if branch == "C":
        assert position.sell_uncertain
        assert position.reconciliation_required
    scenario.replay()
