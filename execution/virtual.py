"""Single virtual dispatcher, with durable claim-before-send and no network."""

from uuid import UUID, uuid4, uuid5

from typing_extensions import assert_never

from execution.facts import Ack, Fact, SendFailed, StopLossTriggered, Transport
from execution.freshness import applied_version, check_freshness
from execution.ledger import Ledger
from execution.models import Amend, Cancel, LedgerError, New, Request
from execution.outcomes import request_state, status
from execution.projection import portfolio
from execution.storage import Entry


class VirtualDispatcher:
    """Collect simulated calls; the mutable list is the observable test surface."""

    def __init__(self, ledger: Ledger) -> None:
        """Use the supplied journal without opening any brokerage connection."""
        self.ledger: Ledger = ledger
        self.calls: list[Request] = []
        self.ledger.on_fact_ingested(self._drain_liquidation)

    def send(self, request_id: UUID) -> bool:
        """Claim an uncalled intention atomically, then simulate submission."""
        with self.ledger.storage.lease.operation():
            store = self.ledger.storage
            with store.transaction() as connection:
                journal = store.read(connection)
                request = next(
                    (r for r in journal.requests if r.request_id == request_id), None
                )
                if (
                    request is None
                    or request.decision != "ACCEPTED"
                    or request_state(journal, request) != "INTENT_PERSISTED"
                    or status(journal, request).positive_evidence
                ):
                    return False
                store.lease.require_ready()
                check_freshness(journal, request.command, self.ledger.clock())
                match request.command:
                    case New(side="BUY"):
                        position = portfolio(journal, request.command.symbol)
                        if position.entry_stopped or position.reconciliation_required:
                            return False
                    case New() | Amend() | Cancel():
                        pass
                    case _:
                        assert_never(request.command)
                fact = Transport(
                    event_id=uuid4(), request_id=request_id, state="SENDING"
                )
                store.append(
                    connection,
                    Entry("fact", str(fact.event_id), fact.model_dump_json()),
                )
            self.calls.append(request)
            _ = self.ledger.ingest(
                Transport(event_id=uuid4(), request_id=request_id, state="SENT")
            )
            return True

    def acknowledge(self, request: Request) -> None:
        """Generate an explicit virtual acknowledgement without effect confirmation."""
        _ = self.ledger.ingest(
            Ack(
                event_id=uuid4(),
                request_id=request.request_id,
                broker_order_no=f"virtual-{request.request_id}",
            )
        )

    def recover(self) -> tuple[UUID, ...]:
        """Record unresolved requests for reconciliation; never resend them."""
        store = self.ledger.storage
        unresolved: list[UUID] = []
        with store.transaction() as connection:
            journal = store.read(connection)
            for request in journal.requests:
                if request.decision != "ACCEPTED":
                    continue
                state = request_state(journal, request)
                if status(journal, request).unresolved:
                    unresolved.append(request.request_id)
                    fact = Transport(
                        event_id=uuid4(),
                        request_id=request.request_id,
                        state="UNKNOWN" if state == "SENDING" else "RECONCILING",
                    )
                    store.append(
                        connection,
                        Entry("fact", str(fact.event_id), fact.model_dump_json()),
                    )
        return tuple(unresolved)

    def process(self, fact: Fact) -> None:
        """Apply a virtual fact, then drain safely available liquidation obligations."""
        _ = self.ledger.ingest(fact)

    def _send_liquidation(self, request: Request) -> None:
        """Send one persisted liquidation or retire a proven stale unsent intent."""
        try:
            sent = self.send(request.request_id)
        except LedgerError as error:
            if error.code != "STALE_CONFIG_VERSION":
                raise
            _ = self.ledger.ingest(
                SendFailed(
                    event_id=uuid5(request.request_id, "stale-config-before-send"),
                    request_id=request.request_id,
                    proof="NOT_INVOKED",
                    reason="STALE_CONFIG_BEFORE_SEND",
                )
            )
            return
        if sent:
            self.acknowledge(request)

    def _drain_liquidation(self, _fact: Fact) -> None:
        """Drain safely available liquidation after every newly committed fact."""
        journal = self.ledger.snapshot()
        symbols = {control.symbol for control in journal.controls} | {
            item.symbol for item in journal.facts if isinstance(item, StopLossTriggered)
        }
        for symbol in sorted(symbols):
            position = self.ledger.portfolio(symbol)
            pending = [
                request
                for request in journal.requests
                if isinstance(request.command, New)
                and request.command.side == "SELL"
                and request.command.symbol == symbol
                and request.command.key.startswith("liquidation:")
                and request_state(journal, request) == "INTENT_PERSISTED"
            ]
            if pending:
                if position.reconciliation_required or position.sell_uncertain:
                    continue
                for request in pending:
                    self._send_liquidation(request)
                continue
            if position.liquidating and position.available > 0:
                command = New(
                    key=f"liquidation:{symbol}:{len(journal.facts)}",
                    symbol=symbol,
                    side="SELL",
                    config_version=applied_version(journal, symbol),
                    qty=position.available,
                    order_type="MARKET",
                    session="REGULAR",
                    validity="DAY",
                )
                request = self.ledger.submit(command).request
                self._send_liquidation(request)
