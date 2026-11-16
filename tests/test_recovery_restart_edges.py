from typing import TYPE_CHECKING
from uuid import uuid4

from execution.facts import Transport
from execution.ledger import Ledger
from execution.models import Cancel
from execution.virtual import VirtualDispatcher

if TYPE_CHECKING:
    from tests.conftest import Scenario


def test_partial_fill_during_cancel_recovery_survives_restarts_without_resend(
    scenario: Scenario,
) -> None:
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    scenario.dispatcher.calls.clear()
    cancel = scenario.book.submit(
        Cancel(
            key="cancel-crash-with-partial-fill",
            symbol="005930",
            side="SELL",
            config_version=1,
            target=sell.order_id,
            link_version=scenario.book.order(sell.order_id).link_version,
            cancel_qty=100,
        )
    ).request
    _ = scenario.book.ingest(
        Transport(event_id=uuid4(), request_id=cancel.request_id, state="SENDING")
    )
    _ = scenario.fill(sell, (30, 70))

    first_ledger = Ledger(scenario.book.storage.path, scenario.book.storage.lease)
    first_dispatcher = VirtualDispatcher(first_ledger)
    assert first_dispatcher.recover() == (cancel.request_id,)
    assert first_ledger.transport(cancel.request_id) == "UNKNOWN"
    assert not first_dispatcher.send(cancel.request_id)
    first_position = first_ledger.portfolio("005930")
    assert (first_position.managed, first_position.reserved) == (70, 70)
    assert first_position.reconciliation_required
    assert first_dispatcher.calls == []

    second_ledger = Ledger(scenario.book.storage.path, scenario.book.storage.lease)
    second_dispatcher = VirtualDispatcher(second_ledger)
    assert second_dispatcher.recover() == (cancel.request_id,)
    assert second_ledger.transport(cancel.request_id) == "RECONCILING"
    assert not second_dispatcher.send(cancel.request_id)
    facts_after_transition = second_ledger.snapshot().facts
    assert second_dispatcher.recover() == (cancel.request_id,)
    assert second_ledger.snapshot().facts == facts_after_transition
    second_position = second_ledger.portfolio("005930")
    assert (second_position.managed, second_position.reserved) == (70, 70)
    assert second_dispatcher.calls == []
