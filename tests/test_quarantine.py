import json
import sqlite3
from contextlib import closing
from uuid import UUID, uuid4

import pytest

from execution.facts import Ack
from execution.models import LedgerError
from execution.quarantine import reprocess
from tests.conftest import Scenario


def payload(event_id: UUID, broker_no: str) -> str:
    return json.dumps(
        {
            "kind": "QUARANTINED_FILL",
            "event_id": str(event_id),
            "broker_order_no": broker_no,
            "symbol": "005930",
            "qty": 30,
            "remaining": 70,
            "evidence_version": 1,
            "source": "VIRTUAL",
        }
    )


def test_quarantined_fill_has_no_quantity_effect(scenario: Scenario) -> None:
    # Given / When
    assert scenario.book.ingest_json(payload(uuid4(), "unknown"))
    # Then
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (0, 0)
    assert position.reconciliation_required
    with pytest.raises(LedgerError, match="SESSION_RECONCILIATION_REQUIRED"):
        scenario.book.approve_virtual_reconciliation(scenario.book.snapshot().revision)


def test_reprocess_links_exact_order_once(scenario: Scenario) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    event_id = uuid4()
    original = payload(event_id, f"virtual-{buy.request_id}")
    assert scenario.book.ingest_json(original)
    revision = scenario.book.snapshot().revision
    # When
    assert reprocess(
        scenario.book,
        event_id,
        proof_reference="virtual-ack",
        expected_revision=revision,
    )
    # Then
    assert scenario.book.portfolio("005930").managed == 30
    assert not scenario.book.portfolio("005930").reconciliation_required
    assert not reprocess(
        scenario.book,
        event_id,
        proof_reference="virtual-ack",
        expected_revision=revision,
    )
    assert not scenario.book.ingest_json(original)


def test_reprocess_refuses_unlinked_order(scenario: Scenario) -> None:
    # Given
    event_id = uuid4()
    assert scenario.book.ingest_json(payload(event_id, "unknown"))
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="QUARANTINE_LINK_NOT_UNIQUE"):
        _ = reprocess(
            scenario.book,
            event_id,
            proof_reference="review",
            expected_revision=before.revision,
        )
    assert scenario.book.snapshot() == before


def test_reprocess_refuses_ambiguous_broker_number(scenario: Scenario) -> None:
    # Given
    first = scenario.new("BUY", 100)
    second = scenario.new("BUY", 100)
    broker_no = f"virtual-{first.request_id}"
    _ = scenario.book.ingest(
        Ack(event_id=uuid4(), request_id=second.request_id, broker_order_no=broker_no)
    )
    event_id = uuid4()
    assert scenario.book.ingest_json(payload(event_id, broker_no))
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="QUARANTINE_LINK_NOT_UNIQUE"):
        _ = reprocess(
            scenario.book,
            event_id,
            proof_reference="review",
            expected_revision=before.revision,
        )
    assert scenario.book.snapshot() == before


def test_reprocess_refuses_stale_review(scenario: Scenario) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    event_id = uuid4()
    assert scenario.book.ingest_json(payload(event_id, f"virtual-{buy.request_id}"))
    revision = scenario.book.snapshot().revision
    scenario.liquidate()
    # When / Then
    with pytest.raises(LedgerError, match="STALE_QUARANTINE_REVIEW"):
        _ = reprocess(
            scenario.book,
            event_id,
            proof_reference="review",
            expected_revision=revision,
        )
    assert scenario.book.portfolio("005930").managed == 0


def test_fill_rolls_back_when_release_publication_fails(scenario: Scenario) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    event_id = uuid4()
    assert scenario.book.ingest_json(payload(event_id, f"virtual-{buy.request_id}"))
    before = scenario.book.snapshot()
    with closing(sqlite3.connect(scenario.book.storage.path)) as connection, connection:
        _ = connection.execute("""CREATE TRIGGER fail_release BEFORE INSERT ON outbox
            WHEN NEW.payload LIKE '%QUARANTINE_RELEASED%'
            BEGIN SELECT RAISE(ABORT, 'release publication failed'); END""")
    # When / Then
    with pytest.raises(sqlite3.IntegrityError, match="release publication failed"):
        _ = reprocess(
            scenario.book,
            event_id,
            proof_reference="review",
            expected_revision=before.revision,
        )
    assert scenario.book.snapshot() == before
    assert scenario.book.portfolio("005930").managed == 0
