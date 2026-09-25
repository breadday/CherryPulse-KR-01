"""Single virtual dispatcher, with durable claim-before-send and no network."""

from typing import Literal
from uuid import UUID, uuid4

from typing_extensions import assert_never

from execution.facts import Ack, Fact, Transport
from execution.freshness import applied_version, check_freshness
from execution.ledger import Ledger
from execution.models import Amend, Cancel, LedgerError, New, Request
from execution.outcomes import request_state, status
from execution.projection import portfolio
from execution.stop_obligations import stop_obligation_views
from execution.storage import Entry


class VirtualDispatcher:
    """Collect simulated calls; the mutable list is the observable test surface."""

    def __init__(self, ledger: Ledger) -> None:
        """Use the supplied journal without opening any brokerage connection."""
        self.ledger: Ledger = ledger
        self.calls: list[Request] = []

    def send(
        self,
        request_id: UUID,
        *,
        stop_session: Literal["REGULAR", "CLOSED"] | None = None,
    ) -> bool:
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
                if request.command.key.startswith("virtual-stop:") and (
                    stop_session != "REGULAR"
                    or not isinstance(request.command, New)
                    or request.command.stop_latch_version is None
                ):
                    return False
                if request.command.key.startswith("virtual-stop:"):
                    obligations = stop_obligation_views(journal, request.command.symbol)
                    current = [
                        view for view in obligations if view.request_id == request_id
                    ]
                    if (
                        len(current) != 1
                        or current[0].state != "PENDING"
                        or any(
                            view.state in ("REVIEW_REQUIRED", "BLOCKED_EVIDENCE")
                            for view in obligations
                        )
                    ):
                        return False
                store.lease.require_ready()
                check_freshness(journal, request.command, self.ledger.clock())
                match request.command:
                    case New(side="BUY"):
                        position = portfolio(journal, request.command.symbol)
                        if (
                            position.entry_stopped
                            or position.reconciliation_required
                            or any(
                                latch.symbol == request.command.symbol
                                for latch in journal.stop_latches
                            )
                        ):
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

    def drain_virtual_stop(
        self, symbol: str, *, session: Literal["REGULAR", "CLOSED"]
    ) -> Request | None:
        """Create one simulated market sell from a latched stop in regular session."""
        if session != "REGULAR":
            return None
        journal = self.ledger.snapshot()
        latch = next(
            (item for item in journal.stop_latches if item.symbol == symbol), None
        )
        if (
            latch is None
            or portfolio(journal, symbol).liquidating
            or any(
                obligation.state in ("REVIEW_REQUIRED", "BLOCKED_EVIDENCE")
                for obligation in self.ledger.virtual_stop_obligations(symbol)
            )
        ):
            return None
        if any(
            request.command.symbol == symbol
            and request.command.side == "SELL"
            and (status(journal, request).failed or status(journal, request).rejected)
            for request in journal.requests
        ):
            return None
        candidate = self.ledger.virtual_latched_stop_candidate(symbol)
        if candidate.status != "CANDIDATE":
            return None
        command = New(
            key=f"virtual-stop:{symbol}:{journal.revision}",
            symbol=symbol,
            side="SELL",
            config_version=applied_version(journal, symbol),
            qty=candidate.unreserved_qty,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
            stop_latch_version=latch.rule_version,
        )
        try:
            request = self.ledger.submit(command).request
        except LedgerError as error:
            if error.code in ("SELL_QUANTITY_UNAVAILABLE", "STALE_CONFIG_VERSION"):
                return None
            raise
        if self.send(request.request_id, stop_session=session):
            self.acknowledge(request)
        return request

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
        journal = self.ledger.snapshot()
        for symbol in sorted({control.symbol for control in journal.controls}):
            position = self.ledger.portfolio(symbol)
            failed_sell = any(
                r.command.symbol == symbol
                and r.command.side == "SELL"
                and (status(journal, r).failed or status(journal, r).rejected)
                for r in journal.requests
            )
            if position.liquidating and position.available > 0 and not failed_sell:
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
                if self.send(request.request_id):
                    self.acknowledge(request)
