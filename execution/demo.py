"""Self-contained virtual cancellation demonstration using a temporary database."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from execution.facts import Cancelled, Fill, Transport
from execution.ledger import Ledger
from execution.models import Allocation, Boundary, Cancel, New, Scope
from execution.ownership import account_lock
from execution.virtual import VirtualDispatcher


class DemoResult(Boundary):
    """Machine-readable observations from the real local journal."""

    managed: int
    reserved: int
    cancel_unknown_reserved: int
    cancel_confirmed_reserved: int
    lifecycle: str
    virtual_calls: int
    replay_changes: int


def run() -> DemoResult:
    """Drive cancel UNKNOWN, early cancellation, late fill and restart replay."""
    with TemporaryDirectory(prefix="cherrypulse-virtual-") as directory:
        path = Path(directory) / "demo.sqlite3"
        scope = Scope(
            account_id="VIRTUAL_DEMO", environment="PAPER", execution_scope=uuid4()
        )
        with account_lock(Path(directory) / "locks", scope) as lease:
            book = Ledger(path, lease)
            book.approve_virtual_reconciliation(0)
            dispatcher = VirtualDispatcher(book)
            book.allocate(Allocation(symbol="005930", qty=100))
            sell = book.submit(
                New(
                    key="demo-sell",
                    symbol="005930",
                    side="SELL",
                    qty=100,
                    config_version=1,
                    order_type="MARKET",
                    session="REGULAR",
                    validity="DAY",
                )
            ).request
            _ = dispatcher.send(sell.request_id)
            dispatcher.acknowledge(sell)
            cancellation = book.submit(
                Cancel(
                    key="demo-cancel",
                    symbol="005930",
                    side="SELL",
                    config_version=1,
                    target=sell.order_id,
                    link_version=1,
                    cancel_qty=100,
                )
            ).request
            _ = dispatcher.send(cancellation.request_id)
            _ = book.ingest(
                Transport(
                    event_id=uuid4(),
                    request_id=cancellation.request_id,
                    state="UNKNOWN",
                )
            )
            unknown_reserved = book.portfolio("005930").reserved
            _ = book.ingest(
                Cancelled(
                    event_id=uuid4(),
                    request_id=cancellation.request_id,
                    order_id=sell.order_id,
                    qty=70,
                    remaining=0,
                    evidence_version=2,
                )
            )
            confirmed_reserved = book.portfolio("005930").reserved
            late = Fill(
                event_id=uuid4(),
                order_id=sell.order_id,
                qty=30,
                remaining=70,
                evidence_version=1,
            )
            _ = book.ingest(late)
            restored = Ledger(path, lease)
            replay_changes = int(restored.ingest(late)) + int(
                restored.submit(sell.command).created
            )
            position = restored.portfolio("005930")
            return DemoResult(
                managed=position.managed,
                reserved=position.reserved,
                cancel_unknown_reserved=unknown_reserved,
                cancel_confirmed_reserved=confirmed_reserved,
                lifecycle=restored.order(sell.order_id).lifecycle,
                virtual_calls=len(dispatcher.calls),
                replay_changes=replay_changes,
            )
