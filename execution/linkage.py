"""Exact simulator acknowledgement linkage; never infer by price or symbol alone."""

from uuid import UUID, uuid5

from execution.facts import Ack, Fill, QuarantinedFill, QuarantineReleased
from execution.models import LedgerError, New
from execution.storage import Journal


def linked_fill(journal: Journal, quarantine_id: UUID) -> Fill:
    """Require one exact acknowledged logical order for quarantined source fields."""
    source = next(
        (
            f
            for f in journal.facts
            if isinstance(f, QuarantinedFill) and f.event_id == quarantine_id
        ),
        None,
    )
    if source is None:
        raise LedgerError("QUARANTINE_NOT_FOUND")
    requests = {
        f.request_id
        for f in journal.facts
        if isinstance(f, Ack) and f.broker_order_no == source.broker_order_no
    }
    targets = {
        r.order_id
        for r in journal.requests
        if r.request_id in requests and r.decision == "ACCEPTED"
    }
    if len(targets) != 1:
        raise LedgerError("QUARANTINE_LINK_NOT_UNIQUE")
    order_id = next(iter(targets))
    original = next(
        r
        for r in journal.requests
        if r.order_id == order_id and isinstance(r.command, New)
    )
    if original.command.symbol != source.symbol:
        raise LedgerError("QUARANTINE_SYMBOL_MISMATCH")
    return Fill(
        event_id=uuid5(quarantine_id, "linked-fill"),
        order_id=order_id,
        qty=source.qty,
        remaining=source.remaining,
        evidence_version=source.evidence_version,
    )


def check_release(journal: Journal, release: QuarantineReleased) -> None:
    """Require exactly derived fill evidence before clearing quarantine blocking."""
    fill = linked_fill(journal, release.quarantine_id)
    if release.fill_id != fill.event_id or fill not in journal.facts:
        raise LedgerError("QUARANTINE_FILL_NOT_COMMITTED")
    if any(
        isinstance(f, QuarantineReleased) and f.quarantine_id == release.quarantine_id
        for f in journal.facts
    ):
        raise LedgerError("QUARANTINE_ALREADY_RELEASED")
