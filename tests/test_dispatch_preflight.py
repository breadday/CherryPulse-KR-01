from typing import Literal
from uuid import uuid4

import pytest

from execution.facts import Discrepancy, Fill
from execution.models import Control, New, Request
from tests.conftest import Scenario


def pending(scenario: Scenario, side: Literal["BUY", "SELL"]) -> Request:
    return scenario.book.submit(
        New(
            key=str(uuid4()),
            symbol="005930",
            side=side,
            qty=100,
            config_version=1,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request


@pytest.mark.parametrize("liquidating", [False, True])
def test_buy_not_sent_when_entry_stops_after_intention(
    scenario: Scenario,
    *,
    liquidating: bool,
) -> None:
    # Given
    request = pending(scenario, "BUY")
    scenario.book.control(
        Control(
            symbol="005930",
            entry_stopped=True,
            liquidating=liquidating,
        )
    )
    before = scenario.book.snapshot()
    # When
    sent = scenario.dispatcher.send(request.request_id)
    # Then
    assert not sent
    assert scenario.dispatcher.calls == []
    assert scenario.book.snapshot() == before


def test_buy_not_sent_when_discrepancy_arrives_after_intention(
    scenario: Scenario,
) -> None:
    # Given
    request = pending(scenario, "BUY")
    _ = scenario.book.ingest(
        Discrepancy(
            event_id=uuid4(),
            symbol="005930",
            reason="quantity-mismatch",
        )
    )
    # When
    sent = scenario.dispatcher.send(request.request_id)
    # Then
    assert not sent
    assert scenario.dispatcher.calls == []


def test_order_not_resent_when_fill_precedes_transport_evidence(
    scenario: Scenario,
) -> None:
    # Given
    request = pending(scenario, "BUY")
    _ = scenario.book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=request.order_id,
            qty=30,
            remaining=70,
            evidence_version=1,
        )
    )
    # When
    sent = scenario.dispatcher.send(request.request_id)
    # Then
    assert not sent
    assert scenario.dispatcher.calls == []
    assert scenario.book.portfolio("005930").managed == 30


def test_recovery_requires_review_when_fill_has_no_transport_evidence(
    scenario: Scenario,
) -> None:
    # Given
    request = pending(scenario, "BUY")
    _ = scenario.book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=request.order_id,
            qty=30,
            remaining=70,
            evidence_version=1,
        )
    )
    # When
    unresolved = scenario.dispatcher.recover()
    # Then
    assert unresolved == (request.request_id,)
    assert scenario.book.transport(request.request_id) == "RECONCILING"


def test_sell_can_be_sent_when_only_new_buy_is_stopped(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    request = pending(scenario, "SELL")
    scenario.liquidate()
    # When
    sent = scenario.dispatcher.send(request.request_id)
    # Then
    assert sent
    assert scenario.dispatcher.calls == [request]
    assert scenario.book.portfolio("005930").reserved == 100
