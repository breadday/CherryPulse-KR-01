"""Transactional facade for simulator requests, evidence and ownership."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from typing_extensions import assert_never

from contracts.settings import StopRule
from contracts.stop_evaluation import (
    ManagedPosition,
    ObserveAt,
    ProtectionDecision,
    ProtectionExposure,
    Quote,
    StopObservation,
    evaluate_stop,
    protection_candidate,
)
from execution.facts import FACT, Discrepancy, Fact, Fill, QuarantinedFill, SendFailed
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
    StopLatch,
    StopQuoteCheckpoint,
    StopRuleAssignment,
    StopSellObligation,
    VirtualStopBinding,
)
from execution.outcomes import request_state, status
from execution.ownership import AccountLease
from execution.projection import (
    Order,
    Portfolio,
    StopCostBasis,
    buy_order_average_cost,
    confirmed_stop_cost_basis,
    confirmed_stop_holdings,
    order,
    portfolio,
)
from execution.quote_status import VirtualQuoteStatus, virtual_quote_status
from execution.stop_obligations import StopObligationView, stop_obligation_views
from execution.storage import Entry, Journal, Storage
from execution.validation import check_command, check_fact


@dataclass(frozen=True, slots=True)
class Submission:
    """Replays return the original request without another reservation."""

    request: Request
    created: bool


@dataclass(frozen=True, slots=True)
class VirtualStopInputResult:
    """Persisted input decision, explicitly separate from send eligibility."""

    accepted: bool
    observation: StopObservation
    latch: StopLatch | None


def _check_virtual_stop_link(journal: Journal, command: OrderCommand) -> None:
    """Require durable latch evidence for explicitly tagged virtual stop sells."""
    if not isinstance(command, New):
        return
    if command.key.startswith("virtual-stop:") and command.stop_latch_version is None:
        raise LedgerError("STOP_LATCH_LINK_REQUIRED")
    if command.stop_latch_version is None:
        return
    if not command.key.startswith("virtual-stop:"):
        raise LedgerError("STOP_LATCH_KEY_REQUIRED")
    if not any(
        latch.symbol == command.symbol
        and latch.rule_version == command.stop_latch_version
        for latch in journal.stop_latches
    ):
        raise LedgerError("STOP_LATCH_LINK_NOT_FOUND")


def _quote_rejection_reason(
    journal: Journal, symbol: str, quote: Quote, timing: ObserveAt
) -> str | None:
    """Reject unsafe quote ordering before it can affect virtual stop state."""
    reason: str | None = None
    if quote.symbol != symbol:
        reason = "QUOTE_MISSING_OR_WRONG_SYMBOL"
    else:
        age = timing.now - quote.received_at
        if (
            age.total_seconds() < 0
            or age.total_seconds() > timing.max_quote_age_seconds
        ):
            reason = "QUOTE_NOT_FRESH"
        else:
            previous = next(
                (
                    item
                    for item in reversed(journal.stop_quotes)
                    if item.symbol == symbol
                ),
                None,
            )
            if previous is not None and timing.now < previous.evaluated_at:
                reason = "EVALUATION_TIME_REVERSED"
            elif previous is not None and quote.received_at == previous.received_at:
                reason = "QUOTE_DUPLICATE"
            elif previous is not None and quote.received_at < previous.received_at:
                reason = "QUOTE_OUT_OF_ORDER"
            elif any(item.symbol == symbol for item in journal.stop_latches):
                reason = "STOP_ALREADY_LATCHED"
    return reason


def _evaluate_virtual_quote(
    journal: Journal, symbol: str, quote: Quote, timing: ObserveAt
) -> tuple[StopObservation, VirtualStopBinding | None]:
    """Evaluate a quote only against the assigned rule and confirmed exposure."""
    position = portfolio(journal, symbol)
    if position.reconciliation_required or position.sell_uncertain:
        return (
            StopObservation(status="UNAVAILABLE", reason="SELL_EVIDENCE_UNRESOLVED"),
            None,
        )
    if position.available == 0:
        return (
            StopObservation(
                status="UNAVAILABLE", reason="NO_UNRESERVED_MANAGED_POSITION"
            ),
            None,
        )
    basis = confirmed_stop_cost_basis(journal, symbol)
    holdings = confirmed_stop_holdings(journal, symbol)
    if basis is not None:
        rule_version = basis.rule_version
        managed = ManagedPosition(
            symbol=symbol,
            confirmed_qty=basis.qty,
            average_cost=str(basis.average_cost),
        )
    elif holdings is not None:
        rule_version = holdings.rule_version
        managed = ManagedPosition(symbol=symbol, confirmed_qty=holdings.qty)
    else:
        return (
            StopObservation(
                status="UNAVAILABLE", reason="STOP_RULE_EVIDENCE_INCOMPLETE"
            ),
            None,
        )
    binding = next(
        (
            item
            for item in journal.stop_bindings
            if item.symbol == symbol and item.version == rule_version
        ),
        None,
    )
    if binding is None:
        return (
            StopObservation(
                status="UNAVAILABLE", reason="STOP_RULE_EVIDENCE_INCOMPLETE"
            ),
            None,
        )
    return (
        evaluate_stop(
            managed,
            quote,
            StopRule(kind=binding.rule_kind, threshold=binding.threshold),
            timing,
        ),
        binding,
    )


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

    def apply_virtual_stop_config(
        self, binding: VirtualStopBinding, *, expected_version: int
    ) -> None:
        """Atomically record simulator revision and inert stop rule for replay."""
        config = AppliedConfig(symbol=binding.symbol, version=binding.version)
        with self.storage.transaction() as connection:
            self.storage.lease.require_ready()
            journal = self.storage.read(connection)
            if applied_version(journal, binding.symbol) != expected_version:
                raise LedgerError("STALE_CONFIG_VERSION")
            if binding.version <= expected_version:
                raise LedgerError("CONFIG_VERSION_MUST_ADVANCE")
            self.storage.append(
                connection,
                Entry("config", str(uuid4()), config.model_dump_json()),
            )
            self.storage.append(
                connection,
                Entry(
                    "stop_binding",
                    f"{binding.symbol}:{binding.version}",
                    binding.model_dump_json(),
                ),
            )

    def virtual_stop_binding(self, symbol: str) -> VirtualStopBinding | None:
        """Read the last bound rule without activating monitoring or orders."""
        journal = self.snapshot()
        version = applied_version(journal, symbol)
        return next(
            (
                binding
                for binding in reversed(journal.stop_bindings)
                if binding.symbol == symbol and binding.version == version
            ),
            None,
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
            if (
                isinstance(command, New)
                and command.side == "BUY"
                and any(
                    latch.symbol == command.symbol for latch in journal.stop_latches
                )
            ):
                raise LedgerError("ENTRY_STOP_LATCHED")
            _check_virtual_stop_link(journal, command)
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
            if isinstance(command, New) and command.stop_latch_version is not None:
                obligation = StopSellObligation(
                    request_id=request.request_id,
                    order_id=request.order_id,
                    symbol=command.symbol,
                    qty=command.qty,
                    rule_version=command.stop_latch_version,
                )
                self.storage.append(
                    connection,
                    Entry(
                        "stop_sell_obligation",
                        str(request.request_id),
                        obligation.model_dump_json(),
                    ),
                )
            return Submission(request, created=True)

    def ingest_json(self, payload: str) -> bool:
        """Parse one normalized virtual fact at the ingress boundary."""
        return self.ingest(FACT.validate_json(payload))

    def ingest(self, fact: Fact) -> bool:
        """Commit deduplication, quantity effects and outbox as one operation."""
        with self.storage.transaction() as connection:
            journal = self.storage.read(connection)
            for existing in journal.facts:
                if existing.event_id == fact.event_id:
                    if existing != fact:
                        raise LedgerError("CONFLICT_EVENT_ID_MISMATCH")
                    return False
            check_fact(journal, fact)
            self.storage.append(
                connection,
                Entry(
                    "fact", str(fact.event_id), fact.model_dump_json(exclude_none=True)
                ),
            )
            if isinstance(fact, Fill):
                buy = next(
                    (
                        r
                        for r in journal.requests
                        if r.order_id == fact.order_id
                        and isinstance(r.command, New)
                        and r.command.side == "BUY"
                    ),
                    None,
                )
                if buy is not None:
                    binding = next(
                        (
                            b
                            for b in journal.stop_bindings
                            if b.symbol == buy.command.symbol
                            and b.version == buy.command.config_version
                        ),
                        None,
                    )
                    if binding is not None:
                        assignment = StopRuleAssignment(
                            fill_event_id=fact.event_id,
                            symbol=buy.command.symbol,
                            qty=fact.qty,
                            rule_version=binding.version,
                        )
                        self.storage.append(
                            connection,
                            Entry(
                                "stop_assignment",
                                str(fact.event_id),
                                assignment.model_dump_json(),
                            ),
                        )
            return True

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

    def buy_order_average_cost(self, order_id: UUID) -> Decimal | None:
        """Read exact buy cost, or report missing execution prices as unknown."""
        return buy_order_average_cost(self.snapshot(), order_id)

    def confirmed_stop_cost_basis(self, symbol: str) -> StopCostBasis | None:
        """Read a conservative cost basis for assigned and unsold buy fills."""
        return confirmed_stop_cost_basis(self.snapshot(), symbol)

    def observe_virtual_cost_stop(
        self, symbol: str, quote: Quote | None, timing: ObserveAt
    ) -> StopObservation:
        """Evaluate an assigned percentage rule without creating an order."""
        return self._observe_virtual_cost_stop(self.snapshot(), symbol, quote, timing)

    def process_virtual_stop_quote(
        self, symbol: str, quote: Quote, timing: ObserveAt
    ) -> VirtualStopInputResult:
        """Validate, order, evaluate and latch one quote in a single SQLite write.

        This is a virtual inspection path only. It does not reserve, submit, or
        establish that the exchange session is open.
        """
        with self.storage.transaction() as connection:
            self.storage.lease.require_ready()
            journal = self.storage.read(connection)
            rejection = _quote_rejection_reason(journal, symbol, quote, timing)
            if rejection is not None:
                latch = next(
                    (item for item in journal.stop_latches if item.symbol == symbol),
                    None,
                )
                return VirtualStopInputResult(
                    accepted=False,
                    observation=StopObservation(status="UNAVAILABLE", reason=rejection),
                    latch=latch if rejection == "STOP_ALREADY_LATCHED" else None,
                )
            observation, binding = _evaluate_virtual_quote(
                journal, symbol, quote, timing
            )

            checkpoint = StopQuoteCheckpoint(
                symbol=symbol,
                price=str(quote.price),
                received_at=quote.received_at,
                evaluated_at=timing.now,
            )
            self.storage.checkpoint_stop_quote(connection, checkpoint)
            latch = None
            if observation.status == "TRIGGERED" and binding is not None:
                latch = StopLatch(
                    symbol=symbol,
                    rule_version=binding.version,
                    rule_kind=binding.rule_kind,
                    quote_price=str(quote.price),
                    quote_received_at=quote.received_at,
                )
                self.storage.append(
                    connection,
                    Entry("stop_latch", symbol, latch.model_dump_json()),
                )
            return VirtualStopInputResult(
                accepted=True, observation=observation, latch=latch
            )

    def virtual_quote_status(
        self, symbol: str, timing: ObserveAt
    ) -> VirtualQuoteStatus:
        """Read checkpoint freshness; no connection or session claim is made."""
        return virtual_quote_status(self.snapshot(), symbol, timing)

    @staticmethod
    def _observe_virtual_cost_stop(
        journal: Journal, symbol: str, quote: Quote | None, timing: ObserveAt
    ) -> StopObservation:
        """Evaluate one journal revision without an order-side effect."""
        basis = confirmed_stop_cost_basis(journal, symbol)
        if basis is None:
            return StopObservation(
                status="UNAVAILABLE", reason="COST_EVIDENCE_INCOMPLETE"
            )
        binding = next(
            (
                b
                for b in journal.stop_bindings
                if b.symbol == symbol and b.version == basis.rule_version
            ),
            None,
        )
        if binding is None or binding.rule_kind != "AVERAGE_COST_DROP":
            return StopObservation(
                status="UNAVAILABLE", reason="COST_RULE_NOT_ASSIGNED"
            )
        return evaluate_stop(
            ManagedPosition(
                symbol=symbol,
                confirmed_qty=basis.qty,
                average_cost=str(basis.average_cost),
            ),
            quote,
            StopRule(kind=binding.rule_kind, threshold=binding.threshold),
            timing,
        )

    def virtual_cost_stop_candidate(
        self, symbol: str, quote: Quote | None, timing: ObserveAt
    ) -> ProtectionDecision:
        """Read one virtual revision and calculate a non-authorizing sell candidate."""
        journal = self.snapshot()
        if not self.storage.lease.ready:
            return ProtectionDecision(
                status="BLOCKED", reason="SESSION_RECONCILIATION_REQUIRED"
            )
        position = portfolio(journal, symbol)
        if position.reconciliation_required or position.sell_uncertain:
            return ProtectionDecision(
                status="BLOCKED", reason="SELL_EVIDENCE_UNRESOLVED"
            )
        basis = confirmed_stop_cost_basis(journal, symbol)
        if basis is None:
            return ProtectionDecision(
                status="BLOCKED", reason="COST_EVIDENCE_INCOMPLETE"
            )
        observation = self._observe_virtual_cost_stop(journal, symbol, quote, timing)
        return protection_candidate(
            observation,
            ManagedPosition(
                symbol=symbol,
                confirmed_qty=basis.qty,
                average_cost=str(basis.average_cost),
            ),
            ProtectionExposure(
                managed_qty=position.managed,
                reserved_sell_qty=position.reserved,
                reconciliation_required=position.reconciliation_required,
                sell_uncertain=position.sell_uncertain,
            ),
        )

    def virtual_price_stop_candidate(
        self, symbol: str, quote: Quote | None, timing: ObserveAt
    ) -> ProtectionDecision:
        """Observe a fixed price stop from assigned shares without order I/O."""
        journal = self.snapshot()
        if not self.storage.lease.ready:
            return ProtectionDecision(
                status="BLOCKED", reason="SESSION_RECONCILIATION_REQUIRED"
            )
        position = portfolio(journal, symbol)
        if position.reconciliation_required or position.sell_uncertain:
            return ProtectionDecision(
                status="BLOCKED", reason="SELL_EVIDENCE_UNRESOLVED"
            )
        holdings = confirmed_stop_holdings(journal, symbol)
        if holdings is None:
            return ProtectionDecision(
                status="BLOCKED", reason="RULE_EVIDENCE_INCOMPLETE"
            )
        binding = next(
            (
                b
                for b in journal.stop_bindings
                if b.symbol == symbol and b.version == holdings.rule_version
            ),
            None,
        )
        if binding is None or binding.rule_kind != "PRICE_AT_OR_BELOW":
            return ProtectionDecision(
                status="BLOCKED", reason="PRICE_RULE_NOT_ASSIGNED"
            )
        managed = ManagedPosition(symbol=symbol, confirmed_qty=holdings.qty)
        observation = evaluate_stop(
            managed,
            quote,
            StopRule(kind=binding.rule_kind, threshold=binding.threshold),
            timing,
        )
        return protection_candidate(
            observation,
            managed,
            ProtectionExposure(
                managed_qty=position.managed,
                reserved_sell_qty=position.reserved,
                reconciliation_required=position.reconciliation_required,
                sell_uncertain=position.sell_uncertain,
            ),
        )

    def latch_virtual_price_stop(
        self, symbol: str, quote: Quote | None, timing: ObserveAt
    ) -> StopLatch | None:
        """Atomically retain one triggered fixed stop; never submit an order."""
        with self.storage.transaction() as connection:
            self.storage.lease.require_ready()
            journal = self.storage.read(connection)
            existing = next(
                (latch for latch in journal.stop_latches if latch.symbol == symbol),
                None,
            )
            if existing is not None:
                return existing if existing.rule_kind == "PRICE_AT_OR_BELOW" else None
            position = portfolio(journal, symbol)
            holdings = confirmed_stop_holdings(journal, symbol)
            if (
                quote is None
                or holdings is None
                or position.reconciliation_required
                or position.sell_uncertain
                or position.available == 0
            ):
                return None
            binding = next(
                (
                    b
                    for b in journal.stop_bindings
                    if b.symbol == symbol and b.version == holdings.rule_version
                ),
                None,
            )
            if binding is None or binding.rule_kind != "PRICE_AT_OR_BELOW":
                return None
            observation = evaluate_stop(
                ManagedPosition(symbol=symbol, confirmed_qty=holdings.qty),
                quote,
                StopRule(kind=binding.rule_kind, threshold=binding.threshold),
                timing,
            )
            if observation.status != "TRIGGERED":
                return None
            latch = StopLatch(
                symbol=symbol,
                rule_version=binding.version,
                rule_kind=binding.rule_kind,
                quote_price=str(quote.price),
                quote_received_at=quote.received_at,
            )
            self.storage.append(
                connection,
                Entry("stop_latch", symbol, latch.model_dump_json()),
            )
            return latch

    def latch_virtual_cost_stop(
        self, symbol: str, quote: Quote | None, timing: ObserveAt
    ) -> StopLatch | None:
        """Retain a proven cost stop without inferring missing fill prices."""
        with self.storage.transaction() as connection:
            self.storage.lease.require_ready()
            journal = self.storage.read(connection)
            existing = next(
                (latch for latch in journal.stop_latches if latch.symbol == symbol),
                None,
            )
            if existing is not None:
                return existing if existing.rule_kind == "AVERAGE_COST_DROP" else None
            position = portfolio(journal, symbol)
            basis = confirmed_stop_cost_basis(journal, symbol)
            if (
                quote is None
                or basis is None
                or position.reconciliation_required
                or position.sell_uncertain
                or position.available == 0
            ):
                return None
            binding = next(
                (
                    b
                    for b in journal.stop_bindings
                    if b.symbol == symbol and b.version == basis.rule_version
                ),
                None,
            )
            if binding is None or binding.rule_kind != "AVERAGE_COST_DROP":
                return None
            observation = evaluate_stop(
                ManagedPosition(
                    symbol=symbol,
                    confirmed_qty=basis.qty,
                    average_cost=str(basis.average_cost),
                ),
                quote,
                StopRule(kind=binding.rule_kind, threshold=binding.threshold),
                timing,
            )
            if observation.status != "TRIGGERED":
                return None
            latch = StopLatch(
                symbol=symbol,
                rule_version=binding.version,
                rule_kind=binding.rule_kind,
                quote_price=str(quote.price),
                quote_received_at=quote.received_at,
            )
            self.storage.append(
                connection, Entry("stop_latch", symbol, latch.model_dump_json())
            )
            return latch

    def virtual_latched_stop_candidate(self, symbol: str) -> ProtectionDecision:
        """Project a retained stop over later fills without using a stale quote."""
        journal = self.snapshot()
        latch = next(
            (item for item in journal.stop_latches if item.symbol == symbol), None
        )
        if latch is None:
            return ProtectionDecision(status="NONE", reason="STOP_NOT_LATCHED")
        if not self.storage.lease.ready:
            return ProtectionDecision(
                status="BLOCKED", reason="SESSION_RECONCILIATION_REQUIRED"
            )
        position = portfolio(journal, symbol)
        if position.reconciliation_required or position.sell_uncertain:
            return ProtectionDecision(
                status="BLOCKED", reason="SELL_EVIDENCE_UNRESOLVED"
            )
        if position.available == 0:
            return ProtectionDecision(
                status="NONE",
                reason="NO_MANAGED_POSITION"
                if position.managed == 0
                else "SHARES_ALREADY_RESERVED_OR_SOLD",
            )
        holdings = confirmed_stop_holdings(journal, symbol)
        if holdings is None or holdings.rule_version != latch.rule_version:
            return ProtectionDecision(
                status="BLOCKED", reason="RULE_EVIDENCE_INCOMPLETE"
            )
        return ProtectionDecision(
            status="CANDIDATE",
            reason="LATCHED_UNRESERVED_SHARES",
            unreserved_qty=position.available,
        )

    def portfolio(self, symbol: str) -> Portfolio:
        """Return managed shares and outstanding reservation exposure."""
        return portfolio(self.snapshot(), symbol)

    def virtual_stop_obligations(self, symbol: str) -> tuple[StopObligationView, ...]:
        """Return immutable stop sell progress without issuing or retrying orders."""
        return stop_obligation_views(self.snapshot(), symbol)

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
