"""Pure quantity projection from unique durable facts."""

from dataclasses import dataclass
from uuid import UUID

from typing_extensions import assert_never

from execution.facts import (
    Amended,
    Cancelled,
    Discrepancy,
    Fill,
    QuarantinedFill,
    QuarantineReleased,
    Reconciled,
    StopLossTriggered,
)
from execution.models import Amend, Cancel, LedgerError, New
from execution.outcomes import effect_settled, request_state, status
from execution.storage import Journal


@dataclass(frozen=True, slots=True)
class Order:
    """Quantities preserve contradictory evidence instead of balancing it away."""

    order_id: UUID
    original: int
    delta: int
    filled: int
    cancelled: int
    active: int | None
    reserved: int
    gap: int | None
    acknowledged: bool
    terminal_cancel: bool
    reconciliation_required: bool
    link_version: int
    rejected: bool
    submission_failed: bool

    @property
    def lifecycle(self) -> str:
        """Keep terminal cancellation independent of delayed acceptance."""
        if self.rejected:
            return "REJECTED"
        if self.terminal_cancel:
            return "CANCELLED"
        if (
            self.active == 0
            and self.filled == self.original + self.delta
            and self.cancelled == 0
        ):
            return "FILLED"
        if self.filled > 0:
            return "PARTIALLY_FILLED"
        return "OPEN" if self.acknowledged else "PENDING"


@dataclass(frozen=True, slots=True)
class Portfolio:
    """Actual ownership, reservation and obligations are independent quantities."""

    managed: int
    reserved: int
    protected: int
    liquidation: int
    entry_stopped: bool
    liquidating: bool
    reconciliation_required: bool
    sell_uncertain: bool

    @property
    def available(self) -> int:
        """Prevent additional selling while relevant evidence is unsafe."""
        if self.reconciliation_required or self.sell_uncertain:
            return 0
        return max(0, self.managed - self.reserved)


def order(journal: Journal, order_id: UUID) -> Order:
    """Aggregate execution facts independently of arrival order."""
    initial = next(
        (
            r
            for r in journal.requests
            if r.order_id == order_id and isinstance(r.command, New)
        ),
        None,
    )
    if initial is None or not isinstance(initial.command, New):
        raise LedgerError("ORDER_NOT_FOUND")
    fills = [f for f in journal.facts if isinstance(f, Fill) and f.order_id == order_id]
    cancels = [
        f for f in journal.facts if isinstance(f, Cancelled) and f.order_id == order_id
    ]
    changes = [
        f for f in journal.facts if isinstance(f, Amended) and f.order_id == order_id
    ]
    observations = [*fills, *cancels, *changes]
    filled = sum(f.qty for f in fills)
    cancelled = sum(f.qty for f in cancels)
    delta = sum(f.qty_delta for f in changes)
    active: int | None = None
    outcome = status(journal, initial)
    void = (outcome.failed or outcome.rejected) and not outcome.positive_evidence
    acknowledged = outcome.transport == "ACKED"
    if observations:
        active = max(observations, key=lambda f: f.evidence_version).remaining
    elif acknowledged:
        active = initial.command.qty
    terminal_cancel = any(f.remaining == 0 for f in cancels)
    if terminal_cancel:
        active = 0
    exposure = initial.command.qty + delta - filled - cancelled
    if void:
        active = 0
    gap = None if active is None or void else exposure - active
    conflict = any(
        a.evidence_version == b.evidence_version and a.remaining != b.remaining
        for a in observations
        for b in observations
    )
    conflict |= any(
        cancelled.remaining == 0
        and observation.evidence_version > cancelled.evidence_version
        and observation.remaining > 0
        for cancelled in cancels
        for observation in observations
    )
    match initial.command.side:
        case "SELL":
            reserved = 0 if void else max(0, exposure)
        case "BUY":
            reserved = 0
        case _:
            assert_never(initial.command.side)
    return Order(
        order_id,
        initial.command.qty,
        delta,
        filled,
        cancelled,
        active,
        reserved,
        gap,
        acknowledged,
        terminal_cancel,
        gap not in (None, 0) or conflict or outcome.conflict or exposure < 0,
        1 + len(changes),
        outcome.rejected,
        outcome.failed,
    )


def portfolio(journal: Journal, symbol: str) -> Portfolio:
    """Derive protection and liquidation from holdings, never order submission."""
    managed = sum(a.qty for a in journal.allocations if a.symbol == symbol)
    reserved = 0
    resolved = {
        f.discrepancy_id
        for f in journal.facts
        if isinstance(f, Reconciled) and f.symbol == symbol
    }
    discrepancy = any(
        isinstance(f, Discrepancy) and f.symbol == symbol and f.event_id not in resolved
        for f in journal.facts
    )
    released = {
        f.quarantine_id for f in journal.facts if isinstance(f, QuarantineReleased)
    }
    discrepancy |= any(
        isinstance(f, QuarantinedFill)
        and f.symbol == symbol
        and f.event_id not in released
        for f in journal.facts
    )
    uncertain = False
    for request in journal.requests:
        if request.command.symbol != symbol:
            continue
        discrepancy |= status(journal, request).conflict
        match request.command:
            case New():
                snapshot = order(journal, request.order_id)
                reserved += snapshot.reserved
                discrepancy |= snapshot.reconciliation_required
                match request.command.side:
                    case "BUY":
                        managed += snapshot.filled
                    case "SELL":
                        managed -= snapshot.filled
                    case _:
                        assert_never(request.command.side)
            case Amend() | Cancel():
                pass
            case _:
                assert_never(request.command)
        if request.decision == "ACCEPTED" and request.command.side == "SELL":
            uncertain |= request_state(journal, request) in (
                "SENDING",
                "SENT",
                "UNKNOWN",
                "RECONCILING",
            )
            match request.command:
                case Amend() | Cancel():
                    uncertain |= not effect_settled(journal, request)
                case New():
                    pass
                case _:
                    assert_never(request.command)
    controls = [c for c in journal.controls if c.symbol == symbol]
    stop_loss_triggered = any(
        isinstance(fact, StopLossTriggered) and fact.symbol == symbol
        for fact in journal.facts
    )
    stopped = bool(controls and controls[-1].entry_stopped) or stop_loss_triggered
    liquidating = bool(controls and controls[-1].liquidating) or stop_loss_triggered
    return Portfolio(
        managed,
        reserved,
        max(0, managed),
        max(0, managed) if liquidating else 0,
        stopped,
        liquidating,
        discrepancy or uncertain or managed < 0 or reserved > managed,
        uncertain,
    )
