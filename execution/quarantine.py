"""Atomic virtual quarantine reprocessing with retained source evidence."""

from uuid import UUID, uuid5

from execution.facts import QuarantineReleased
from execution.ledger import Ledger
from execution.linkage import linked_fill
from execution.models import LedgerError
from execution.storage import Entry
from execution.validation import check_fact


def reprocess(
    ledger: Ledger, quarantine_id: UUID, *, proof_reference: str, expected_revision: int
) -> bool:
    """Commit derived fill and release together after reviewing exact linkage."""
    release = QuarantineReleased(
        event_id=uuid5(quarantine_id, "release"),
        quarantine_id=quarantine_id,
        fill_id=uuid5(quarantine_id, "linked-fill"),
        proof_reference=proof_reference,
    )
    store = ledger.storage
    with store.transaction() as connection:
        journal = store.read(connection)
        for existing in journal.facts:
            if existing.event_id == release.event_id:
                if existing != release:
                    raise LedgerError("CONFLICT_EVENT_ID_MISMATCH")
                return False
        if journal.revision != expected_revision:
            raise LedgerError("STALE_QUARANTINE_REVIEW")
        fill = linked_fill(journal, quarantine_id)
        existing = next((f for f in journal.facts if f.event_id == fill.event_id), None)
        if existing is not None and existing != fill:
            raise LedgerError("CONFLICT_EVENT_ID_MISMATCH")
        if existing is None:
            check_fact(journal, fill)
            store.append(
                connection, Entry("fact", str(fill.event_id), fill.model_dump_json())
            )
        check_fact(store.read(connection), release)
        store.append(
            connection, Entry("fact", str(release.event_id), release.model_dump_json())
        )
        return True
