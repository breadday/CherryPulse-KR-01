import json
from uuid import UUID, uuid4

import pytest

from execution.facts import Discrepancy
from execution.models import LedgerError
from tests.conftest import Scenario
from tests.query_fixtures import complete_query


def discrepancy(scenario: Scenario) -> UUID:
    event_id = uuid4()
    _ = scenario.book.ingest(
        Discrepancy(event_id=event_id, symbol="005930", reason="VIRTUAL_QUERY_MISMATCH")
    )
    return event_id


def review(scenario: Scenario, target: UUID, *, qty: int = 100) -> str:
    return json.dumps(
        {
            "kind": "RECONCILED",
            "event_id": str(uuid4()),
            "discrepancy_id": str(target),
            "symbol": "005930",
            "observed_managed": qty,
            "reviewed_revision": scenario.book.snapshot().revision,
            "proof_reference": "virtual-review-001",
            "source": "VIRTUAL_COMPLETE_REVIEW",
            "query": complete_query(scenario.book.snapshot().revision, qty).model_dump(
                mode="json"
            ),
        }
    )


def test_complete_review_resolves_only_named_discrepancy(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    first = discrepancy(scenario)
    second = discrepancy(scenario)
    # When
    assert scenario.book.ingest_json(review(scenario, first))
    # Then
    assert scenario.book.portfolio("005930").reconciliation_required
    final = review(scenario, second)
    assert scenario.book.ingest_json(final)
    assert not scenario.book.portfolio("005930").reconciliation_required
    assert scenario.book.portfolio("005930").managed == 100
    assert not scenario.book.ingest_json(final)


def test_review_cannot_adjust_management_quantity(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    target = discrepancy(scenario)
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="RECONCILIATION_QUANTITY_MISMATCH"):
        _ = scenario.book.ingest_json(review(scenario, target, qty=90))
    assert scenario.book.snapshot() == before


def test_review_rejects_changed_journal(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    target = discrepancy(scenario)
    payload = review(scenario, target)
    scenario.liquidate()
    # When / Then
    with pytest.raises(LedgerError, match="STALE_RECONCILIATION_REVIEW"):
        _ = scenario.book.ingest_json(payload)
    assert scenario.book.portfolio("005930").reconciliation_required


def test_review_cannot_hide_unresolved_order(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    cancel = scenario.cancel(sell, 100)
    scenario.unknown(cancel)
    target = discrepancy(scenario)
    # When / Then
    with pytest.raises(LedgerError, match="RECONCILIATION_ORDER_UNRESOLVED"):
        _ = scenario.book.ingest_json(review(scenario, target))
    assert scenario.book.portfolio("005930").reserved == 100


def test_review_requires_existing_discrepancy(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    # When / Then
    with pytest.raises(LedgerError, match="DISCREPANCY_NOT_FOUND"):
        _ = scenario.book.ingest_json(review(scenario, uuid4()))


def test_startup_review_includes_symbol_with_only_discrepancy(
    scenario: Scenario,
) -> None:
    # Given
    _ = discrepancy(scenario)
    revision = scenario.book.snapshot().revision
    # When / Then
    with pytest.raises(LedgerError, match="SESSION_RECONCILIATION_REQUIRED"):
        scenario.book.approve_virtual_reconciliation(revision)


def test_second_resolution_cannot_replace_original_evidence(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    target = discrepancy(scenario)
    assert scenario.book.ingest_json(review(scenario, target))
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="DISCREPANCY_ALREADY_RESOLVED"):
        _ = scenario.book.ingest_json(review(scenario, target))
    assert scenario.book.snapshot() == before


def test_review_cannot_hide_conflicting_order_quantities(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    _ = scenario.fill(sell, (30, 80))
    target = discrepancy(scenario)
    # When / Then
    with pytest.raises(LedgerError, match="RECONCILIATION_ORDER_UNRESOLVED"):
        _ = scenario.book.ingest_json(review(scenario, target, qty=70))
    assert scenario.book.order(sell.order_id).reconciliation_required
