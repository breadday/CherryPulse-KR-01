import json
from typing import Literal
from uuid import uuid4

import pytest

from execution.facts import Transport
from execution.models import LedgerError, New, Request
from tests.conftest import Scenario


def pending_sell(scenario: Scenario) -> Request:
    scenario.allocate(100)
    return scenario.book.submit(
        New(
            key="pending-sell",
            symbol="005930",
            side="SELL",
            config_version=1,
            qty=100,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request


def failure_payload(
    request: Request, kind: Literal["SEND_FAILED", "REJECTED", "EFFECT_REJECTED"]
) -> str:
    fields = {
        "event_id": str(uuid4()),
        "request_id": str(request.request_id),
        "kind": kind,
        "reason": "VIRTUAL_EVIDENCE",
    }
    if kind == "SEND_FAILED":
        fields["proof"] = "NOT_INVOKED"
    return json.dumps(fields)


def test_reservation_released_when_send_was_proven_not_invoked(
    scenario: Scenario,
) -> None:
    # Given
    request = pending_sell(scenario)
    payload = failure_payload(request, "SEND_FAILED")
    # When
    assert scenario.book.ingest_json(payload)
    # Then
    assert scenario.book.transport(request.request_id) == "SEND_FAILED"
    assert scenario.book.portfolio("005930").reserved == 0
    assert scenario.book.portfolio("005930").managed == 100
    assert not scenario.book.ingest_json(payload)
    assert not scenario.dispatcher.send(request.request_id)


def test_new_order_rejected_when_broker_rejection_is_correlated(
    scenario: Scenario,
) -> None:
    # Given
    request = pending_sell(scenario)
    assert scenario.dispatcher.send(request.request_id)
    # When
    assert scenario.book.ingest_json(failure_payload(request, "REJECTED"))
    # Then
    order = scenario.book.order(request.order_id)
    assert order.lifecycle == "REJECTED"
    assert (order.filled, order.cancelled, order.reserved) == (0, 0, 0)
    assert order.gap is None
    assert not order.reconciliation_required


@pytest.mark.parametrize("kind", ["REJECTED", "EFFECT_REJECTED"])
def test_cancel_rejection_keeps_original_reservation(
    scenario: Scenario, kind: Literal["REJECTED", "EFFECT_REJECTED"]
) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    cancel = scenario.cancel(sell, 100)
    # When
    assert scenario.book.ingest_json(failure_payload(cancel, kind))
    # Then
    assert scenario.book.portfolio("005930").reserved == 100
    assert scenario.book.order(sell.order_id).lifecycle == "OPEN"
    replacement = scenario.cancel(sell, 100)
    assert replacement.request_id != cancel.request_id


def test_unknown_request_cannot_claim_not_invoked(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    assert scenario.dispatcher.send(request.request_id)
    scenario.unknown(request)
    # When / Then
    with pytest.raises(LedgerError, match="UNSENT_PROOF_INVALID"):
        _ = scenario.book.ingest_json(failure_payload(request, "SEND_FAILED"))
    assert scenario.book.portfolio("005930").reserved == 100


def test_verified_unsent_after_claim_releases_reservation(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    _ = scenario.book.ingest(
        Transport(event_id=uuid4(), request_id=request.request_id, state="SENDING")
    )
    payload = failure_payload(request, "SEND_FAILED").replace(
        "NOT_INVOKED", "VERIFIED_UNSENT"
    )
    # When
    assert scenario.book.ingest_json(payload)
    # Then
    assert scenario.book.portfolio("005930").reserved == 0
    assert scenario.dispatcher.recover() == ()


def test_late_fill_after_rejection_is_preserved_and_flagged(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    assert scenario.dispatcher.send(request.request_id)
    assert scenario.book.ingest_json(failure_payload(request, "REJECTED"))
    # When
    _ = scenario.fill(request, (30, 70))
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (70, 70)
    assert position.reconciliation_required
    assert scenario.book.order(request.order_id).cancelled == 0


def test_recovery_includes_terminal_request_with_conflicting_fill(
    scenario: Scenario,
) -> None:
    # Given
    request = pending_sell(scenario)
    assert scenario.dispatcher.send(request.request_id)
    assert scenario.book.ingest_json(failure_payload(request, "REJECTED"))
    _ = scenario.fill(request, (30, 70))
    # When
    unresolved = scenario.dispatcher.recover()
    # Then
    assert request.request_id in unresolved
    assert scenario.book.portfolio("005930").reconciliation_required


def test_rejected_amendment_does_not_reduce_reserved_quantity(
    scenario: Scenario,
) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    amendment = scenario.amend(sell, -20)
    # When
    assert scenario.book.ingest_json(failure_payload(amendment, "EFFECT_REJECTED"))
    # Then
    assert scenario.book.order(sell.order_id).delta == 0
    assert scenario.book.portfolio("005930").reserved == 100
    assert scenario.dispatcher.recover() == ()
