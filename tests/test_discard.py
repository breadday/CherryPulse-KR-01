import pytest

from execution.models import Cancel, LedgerError
from tests.conftest import Scenario
from tests.test_request_outcomes import pending_sell


def test_discard_releases_only_unsent_reservation(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    revision = scenario.book.snapshot().revision
    # When
    created = scenario.book.discard(
        request.request_id, reason="USER_WITHDRAWN", expected_revision=revision
    )
    # Then
    assert created
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.reserved) == (100, 0)
    assert scenario.book.order(request.order_id).cancelled == 0
    assert not scenario.dispatcher.send(request.request_id)
    assert not scenario.book.discard(
        request.request_id, reason="USER_WITHDRAWN", expected_revision=revision
    )
    assert scenario.book.snapshot().revision == revision + 1


def test_discard_rejects_changed_reason_on_replay(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    revision = scenario.book.snapshot().revision
    _ = scenario.book.discard(
        request.request_id, reason="USER_WITHDRAWN", expected_revision=revision
    )
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="CONFLICT_EVENT_ID_MISMATCH"):
        _ = scenario.book.discard(
            request.request_id, reason="EXPIRED", expected_revision=revision
        )
    assert scenario.book.snapshot() == before


def test_discard_rejects_stale_review(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    revision = scenario.book.snapshot().revision
    scenario.liquidate()
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="STALE_DISCARD_REVIEW"):
        _ = scenario.book.discard(
            request.request_id, reason="USER_WITHDRAWN", expected_revision=revision
        )
    assert scenario.book.snapshot() == before


def test_discard_cannot_erase_sent_request(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    assert scenario.dispatcher.send(request.request_id)
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="UNSENT_PROOF_INVALID"):
        _ = scenario.book.discard(
            request.request_id,
            reason="USER_WITHDRAWN",
            expected_revision=before.revision,
        )
    assert scenario.book.snapshot() == before
    assert scenario.book.portfolio("005930").reserved == 100


def test_discard_cannot_erase_early_fill(scenario: Scenario) -> None:
    # Given
    request = pending_sell(scenario)
    _ = scenario.fill(request, (30, 70))
    before = scenario.book.snapshot()
    # When / Then
    with pytest.raises(LedgerError, match="UNSENT_PROOF_INVALID"):
        _ = scenario.book.discard(
            request.request_id,
            reason="USER_WITHDRAWN",
            expected_revision=before.revision,
        )
    assert scenario.book.snapshot() == before
    assert scenario.book.portfolio("005930").reserved == 70


def test_discarding_unsent_cancel_preserves_original_sell(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    cancel = scenario.book.submit(
        Cancel(
            key="unsent-cancel",
            symbol="005930",
            side="SELL",
            config_version=1,
            target=sell.order_id,
            link_version=1,
            cancel_qty=100,
        )
    ).request
    revision = scenario.book.snapshot().revision
    # When
    assert scenario.book.discard(
        cancel.request_id, reason="USER_WITHDRAWN", expected_revision=revision
    )
    # Then
    assert scenario.book.portfolio("005930").reserved == 100
    assert scenario.book.order(sell.order_id).cancelled == 0
    assert not scenario.dispatcher.send(cancel.request_id)
