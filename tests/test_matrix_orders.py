from uuid import uuid4

import pytest

from execution.facts import Discrepancy, Fill
from execution.models import Amend, Cancel, Control, LedgerError, New
from tests.conftest import Scenario


def test_t01_partial_cancellations_when_amendment_reduces_quantity(
    scenario: Scenario,
) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    prior = scenario.book.submit(
        Amend(
            key="initial-price-change",
            symbol="005930",
            side="SELL",
            config_version=1,
            target=sell.order_id,
            link_version=1,
            price="10100",
        )
    ).request
    assert scenario.dispatcher.send(prior.request_id)
    scenario.amended(prior, (0, 100))
    scenario.dispatcher.calls.clear()
    # When
    change = scenario.amend(sell, -20)
    scenario.amended(change, (-20, 80))
    first = scenario.cancel(sell, 30)
    _ = scenario.cancelled(first, (30, 50))
    second = scenario.cancel(sell, 50)
    _ = scenario.cancelled(second, (50, 0))
    # Then
    order = scenario.book.order(sell.order_id)
    assert (
        order.original,
        order.delta,
        order.filled,
        order.cancelled,
        order.active,
    ) == (100, -20, 0, 80, 0)
    assert scenario.book.portfolio("005930").reserved == 0
    assert scenario.counts() == (0, 1, 2)
    scenario.replay()


def test_t02_buy_protection_when_cancel_result_is_unknown(scenario: Scenario) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    _ = scenario.fill(buy, (20, 80))
    scenario.book.control(
        Control(symbol="005930", entry_stopped=True, liquidating=False)
    )
    scenario.dispatcher.calls.clear()
    cancel = scenario.cancel(buy, 80)
    scenario.unknown(cancel)
    # When
    _ = scenario.fill(buy, (30, 50))
    _ = scenario.book.ingest(
        Discrepancy(event_id=uuid4(), symbol="005930", reason="INCOMPLETE_QUERY")
    )
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.protected, position.reserved) == (50, 50, 0)
    assert scenario.book.order(buy.order_id).active == 50
    assert scenario.book.transport(cancel.request_id) == "UNKNOWN"
    assert position.reconciliation_required
    assert scenario.counts() == (0, 0, 1)
    scenario.replay()


def test_t03_terminal_order_when_ack_arrives_after_fills(scenario: Scenario) -> None:
    # Given
    command = New(
        key="early-fill",
        symbol="005930",
        side="BUY",
        qty=100,
        config_version=1,
        order_type="MARKET",
        session="REGULAR",
        validity="DAY",
    )
    buy = scenario.book.submit(command).request
    _ = scenario.dispatcher.send(buy.request_id)
    scenario.dispatcher.calls.clear()
    # When
    first = scenario.fill(buy, (40, 60))
    assert not scenario.book.ingest(first)
    _ = scenario.fill(buy, (60, 0))
    scenario.dispatcher.acknowledge(buy)
    scenario.dispatcher.acknowledge(buy)
    # Then
    assert scenario.book.order(buy.order_id).lifecycle == "FILLED"
    assert scenario.book.portfolio("005930").managed == 100
    assert scenario.counts() == (0, 0, 0)
    scenario.replay()


def test_t04_reservation_when_cancel_is_unconfirmed(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    scenario.dispatcher.calls.clear()
    cancel = scenario.cancel(sell, 100)
    scenario.unknown(cancel)
    assert scenario.book.portfolio("005930").reserved == 100
    # When
    _ = scenario.cancelled(cancel, (100, 0))
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (100, 0)
    assert scenario.counts() == (0, 0, 1)
    scenario.replay()


def test_t07_increase_when_amendment_is_unsupported(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    scenario.dispatcher.calls.clear()
    # When
    change = scenario.amend(sell, 20)
    # Then
    assert change.decision == "REJECTED_UNSUPPORTED"
    assert scenario.book.portfolio("005930").reserved == 100
    assert scenario.book.order(sell.order_id).delta == 0
    assert scenario.counts() == (0, 0, 0)
    scenario.replay()


@pytest.mark.parametrize("cancel_first", [True, False])
def test_t08_convergence_when_cancel_and_fill_arrive_in_reverse(
    scenario: Scenario, *, cancel_first: bool
) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    scenario.dispatcher.calls.clear()
    cancel = scenario.cancel(sell, 100)
    scenario.version = 1
    late = Fill(
        event_id=uuid4(),
        order_id=sell.order_id,
        qty=30,
        remaining=70,
        evidence_version=1,
    )
    # When
    if cancel_first:
        _ = scenario.cancelled(cancel, (70, 0))
        assert scenario.book.portfolio("005930").reserved == 30
        assert scenario.book.order(sell.order_id).gap == 30
        _ = scenario.book.ingest(late)
    else:
        _ = scenario.book.ingest(late)
        _ = scenario.cancelled(cancel, (70, 0))
    scenario.dispatcher.acknowledge(cancel)
    # Then
    order = scenario.book.order(sell.order_id)
    assert (order.filled, order.cancelled, order.active, order.gap) == (30, 70, 0, 0)
    assert order.lifecycle == "CANCELLED"
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (70, 0)
    assert not position.reconciliation_required
    assert scenario.counts() == (0, 0, 1)
    scenario.replay()


def test_t09_idempotency_when_reservation_consumes_available_quantity(
    scenario: Scenario,
) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    changed = New.model_validate_json(
        sell.command.model_dump_json().replace('"qty":100', '"qty":80')
    )
    # When
    with pytest.raises(LedgerError, match="CONFLICT_IDEMPOTENCY_MISMATCH"):
        _ = scenario.book.submit(changed)
    replay = scenario.book.submit(sell.command)
    # Then
    assert replay.request == sell
    assert not replay.created
    assert scenario.book.portfolio("005930").reserved == 100
    assert scenario.counts() == (1, 0, 0)
    scenario.replay()


def test_t10_key_conflict_when_target_also_fails_quantity_validation(
    scenario: Scenario,
) -> None:
    # Given
    scenario.allocate(100)
    first = scenario.new("SELL", 60)
    second = scenario.new("SELL", 40)
    scenario.dispatcher.calls.clear()
    cancel = scenario.cancel(first, 60)
    _ = scenario.cancelled(cancel, (60, 0))
    command = Cancel(
        key=cancel.command.key,
        symbol="005930",
        side="SELL",
        config_version=1,
        target=second.order_id,
        link_version=1,
        cancel_qty=60,
    )
    # When
    with pytest.raises(LedgerError, match="CONFLICT_IDEMPOTENCY_MISMATCH"):
        _ = scenario.book.submit(command)
    # Then
    assert scenario.book.portfolio("005930").reserved == 40
    assert scenario.counts() == (0, 0, 1)
    scenario.replay()


def test_t11_fill_when_sell_cancel_is_unknown(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    scenario.dispatcher.calls.clear()
    cancel = scenario.cancel(sell, 100)
    scenario.unknown(cancel)
    # When
    fill = scenario.fill(sell, (30, 70))
    assert not scenario.book.ingest(fill)
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (70, 70)
    assert scenario.book.transport(cancel.request_id) == "UNKNOWN"
    assert scenario.counts() == (0, 0, 1)
    scenario.replay()


def test_terminal_conflict_when_newer_evidence_claims_active_quantity(
    scenario: Scenario,
) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    cancel = scenario.cancel(sell, 100)
    _ = scenario.cancelled(cancel, (70, 0))
    # When: balanced quantities conflict with newer activity evidence.
    _ = scenario.fill(sell, (30, 70))
    # Then
    snapshot = scenario.book.order(sell.order_id)
    assert snapshot.lifecycle == "CANCELLED"
    assert snapshot.gap == 0
    assert snapshot.reconciliation_required
