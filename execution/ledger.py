"""Transactional facade for simulator requests, evidence and ownership."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from typing_extensions import assert_never

from execution.facts import FACT, Discrepancy, Fact, QuarantinedFill, SendFailed
from execution.freshness import applied_version, check_freshness, utc_now
from execution.models import (
    COMMAND,
    Allocation,
    Amend,
    AppliedConfig,
    Cancel,
    Control,
    LedgerError,
    New,
    OrderCommand,
    Request,
)
from execution.outcomes import request_state, status
from execution.ownership import AccountLease
from execution.projection import Order, Portfolio, order, portfolio
from execution.storage import Entry, Journal, Storage
from execution.validation import check_command, check_fact


@dataclass(frozen=True, slots=True)
class Submission:
    """Replays return the original request without another reservation."""

    request: Request
    created: bool


class Ledger:
    """Each mutation is one durable transaction; no broker I/O is available."""

    def __init__(
        self,
        path: Path,
        lease: AccountLease,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Bind the local journal to a validated simulator scope."""
        self.storage: Storage = Storage(path, lease)
        self.clock: Callable[[], datetime] = clock
        self._fact_handlers: list[Callable[[Fact], None]] = []

    def on_fact_ingested(self, handler: Callable[[Fact], None]) -> None:
        """Register an in-process handler that runs after a new fact commits."""
        self._fact_handlers.append(handler)

    def snapshot(self) -> Journal:
        """Read a consistent view, including all facts after restart."""
        with self.storage.transaction() as connection:
            return self.storage.read(connection)

    def allocate(self, allocation: Allocation) -> None:
        """Record initial ownership once, before any orders for the symbol."""
        with self.storage.transaction() as connection:
            journal = self.storage.read(connection)
            existing = next(
                (a for a in journal.allocations if a.symbol == allocation.symbol), None
            )
            if existing == allocation:
                return
            self.storage.lease.require_ready()
            if existing is not None or any(
                r.command.symbol == allocation.symbol for r in journal.requests
            ):
                raise LedgerError("ALLOCATION_ALREADY_STARTED")
            self.storage.append(
                connection,
                Entry(
                    "allocation",
                    allocation.symbol,
                    allocation.model_dump_json(exclude_none=True),
                ),
            )

    def control(self, control: Control) -> None:
        """Persist local simulation switches, without synthesizing orders."""
        with self.storage.transaction() as connection:
            self.storage.lease.require_ready()
            self.storage.append(
                connection,
                Entry(
                    "control", str(uuid4()), control.model_dump_json(exclude_none=True)
                ),
            )

    def apply_config(self, symbol: str, *, expected_version: int, version: int) -> None:
        """Compare and append a newer simulator configuration atomically."""
        config = AppliedConfig(symbol=symbol, version=version)
        with self.storage.transaction() as connection:
            self.storage.lease.require_ready()
            journal = self.storage.read(connection)
            if applied_version(journal, symbol) != expected_version:
                raise LedgerError("STALE_CONFIG_VERSION")
            if version <= expected_version:
                raise LedgerError("CONFIG_VERSION_MUST_ADVANCE")
            self.storage.append(
                connection,
                Entry("config", str(uuid4()), config.model_dump_json()),
            )

    def submit_json(self, payload: str) -> Submission:
        """Parse untrusted command JSON before touching the database."""
        return self.submit(COMMAND.validate_json(payload))

    def submit(self, command: OrderCommand) -> Submission:
        """Compare replay content before changing-state business validation."""
        payload = command.model_dump_json(exclude_none=True)
        with self.storage.transaction() as connection:
            journal = self.storage.read(connection)
            for existing in journal.requests:
                if existing.command.key == command.key:
                    if existing.command.model_dump_json(exclude_none=True) != payload:
                        raise LedgerError("CONFLICT_IDEMPOTENCY_MISMATCH")
                    return Submission(existing, created=False)
            self.storage.lease.require_ready()
            check_freshness(journal, command, self.clock())
            check_command(journal, command)
            match command:
                case New():
                    order_id = uuid4()
                    decision = "ACCEPTED"
                case Amend():
                    order_id = command.target
                    decision = (
                        "REJECTED_UNSUPPORTED" if command.qty_delta > 0 else "ACCEPTED"
                    )
                case Cancel():
                    order_id = command.target
                    decision = "ACCEPTED"
                case _:
                    assert_never(command)
            request = Request(
                request_id=uuid4(),
                order_id=order_id,
                command=command,
                decision=decision,
                digest=sha256(payload.encode()).hexdigest(),
            )
            self.storage.append(
                connection,
                Entry(
                    "request", command.key, request.model_dump_json(exclude_none=True)
                ),
            )
            return Submission(request, created=True)

    def ingest_json(self, payload: str) -> bool:
        """Parse one normalized virtual fact at the ingress boundary."""
        return self.ingest(FACT.validate_json(payload))

    def ingest(self, fact: Fact) -> bool:
        """Commit a fact once, then retry registered handlers on exact replay."""
        created = True
        with self.storage.transaction() as connection:
            journal = self.storage.read(connection)
            existing = next(
                (item for item in journal.facts if item.event_id == fact.event_id), None
            )
            if existing is not None:
                if existing != fact:
                    raise LedgerError("CONFLICT_EVENT_ID_MISMATCH")
                created = False
            else:
                check_fact(journal, fact)
                self.storage.append(
                    connection,
                    Entry(
                        "fact",
                        str(fact.event_id),
                        fact.model_dump_json(exclude_none=True),
                    ),
                )
        for handler in tuple(self._fact_handlers):
            handler(fact)
        return created

    def discard(self, request_id: UUID, *, reason: str, expected_revision: int) -> bool:
        """Retire a reviewed uncalled intention without cancelling a broker order."""
        fact = SendFailed(
            event_id=uuid5(request_id, "local-discard"),
            request_id=request_id,
            proof="NOT_INVOKED",
            reason=reason,
        )
        with self.storage.transaction() as connection:
            journal = self.storage.read(connection)
            for existing in journal.facts:
                if existing.event_id == fact.event_id:
                    if existing != fact:
                        raise LedgerError("CONFLICT_EVENT_ID_MISMATCH")
                    return False
            self.storage.lease.require_ready()
            if journal.revision != expected_revision:
                raise LedgerError("STALE_DISCARD_REVIEW")
            check_fact(journal, fact)
            self.storage.append(
                connection,
                Entry("fact", str(fact.event_id), fact.model_dump_json()),
            )
            return True

    def order(self, order_id: UUID) -> Order:
        """Return evidence-based quantities and independent reconciliation state."""
        return order(self.snapshot(), order_id)

    def portfolio(self, symbol: str) -> Portfolio:
        """Return managed shares and outstanding reservation exposure."""
        return portfolio(self.snapshot(), symbol)

    def transport(self, request_id: UUID) -> str:
        """Return the persisted request transport projection."""
        journal = self.snapshot()
        request = next(
            (r for r in journal.requests if r.request_id == request_id), None
        )
        if request is None:
            raise LedgerError("REQUEST_NOT_FOUND")
        return request_state(journal, request)

    def approve_virtual_reconciliation(self, expected_revision: int) -> None:
        """Approve current virtual journal evidence."""
        with self.storage.transaction() as connection:
            journal = self.storage.read(connection)
            if journal.revision != expected_revision:
                raise LedgerError("STALE_RECONCILIATION_REVIEW")
            symbols = (
                {r.command.symbol for r in journal.requests}
                | {a.symbol for a in journal.allocations}
                | {
                    f.symbol
                    for f in journal.facts
                    if isinstance(f, (Discrepancy, QuarantinedFill))
                }
            )
            if any(status(journal, r).unresolved for r in journal.requests) or any(
                portfolio(journal, symbol).reconciliation_required for symbol in symbols
            ):
                raise LedgerError("SESSION_RECONCILIATION_REQUIRED")
            self.storage.lease.approve_virtual_review()
