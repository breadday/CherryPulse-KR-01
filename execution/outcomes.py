"""Request transport and effect projections with contradictory evidence retained."""

from dataclasses import dataclass

from execution.facts import (
    Ack,
    Amended,
    Cancelled,
    EffectRejected,
    Fill,
    Rejected,
    SendFailed,
    Transport,
)
from execution.models import Amend, Cancel, Request
from execution.storage import Journal


@dataclass(frozen=True, slots=True)
class RequestStatus:
    """Negative request outcomes do not erase accepted or executed facts."""

    transport: str
    effect: str | None
    conflict: bool
    positive_evidence: bool
    failed: bool
    rejected: bool

    @property
    def unresolved(self) -> bool:
        """Include unresolved effects after terminal transport acknowledgement."""
        return (
            self.conflict
            or (self.transport == "INTENT_PERSISTED" and self.positive_evidence)
            or self.transport
            in (
                "SENDING",
                "SENT",
                "UNKNOWN",
                "RECONCILING",
            )
            or (self.transport == "ACKED" and self.effect in ("PENDING", "UNKNOWN"))
        )

    @property
    def effect_settled(self) -> bool:
        """Allow a new change intention only when the prior effect is resolved."""
        return not self.conflict and self.effect in ("CONFIRMED", "REJECTED")


def status(journal: Journal, request: Request) -> RequestStatus:
    """Project all unique facts without letting late transport undo a terminal fact."""
    facts = [
        f
        for f in journal.facts
        if isinstance(
            f,
            (Ack, Amended, Cancelled, EffectRejected, Rejected, SendFailed, Transport),
        )
        and f.request_id == request.request_id
    ]
    accepted = any(
        isinstance(f, (Ack, Amended, Cancelled, EffectRejected)) for f in facts
    )
    confirmed = any(isinstance(f, (Amended, Cancelled)) for f in facts)
    effect_rejected = any(isinstance(f, EffectRejected) for f in facts)
    failed = any(isinstance(f, SendFailed) for f in facts)
    rejected = any(isinstance(f, Rejected) for f in facts)
    changed = isinstance(request.command, (Amend, Cancel))
    executed = not changed and any(
        isinstance(f, Fill) and f.order_id == request.order_id for f in journal.facts
    )
    observed = [f.state for f in facts if isinstance(f, Transport)]
    transport = observed[-1] if observed else "INTENT_PERSISTED"
    if accepted:
        transport = "ACKED"
    elif rejected:
        transport = "REJECTED_BY_BROKER"
    elif failed:
        transport = "SEND_FAILED"
    effect: str | None = None
    if changed:
        if confirmed:
            effect = "CONFIRMED"
        elif failed or rejected or effect_rejected:
            effect = "REJECTED"
        else:
            effect = "UNKNOWN" if transport in ("UNKNOWN", "RECONCILING") else "PENDING"
    conflict = (
        ((failed or rejected) and (accepted or executed))
        or (failed and rejected)
        or (confirmed and effect_rejected)
    )
    return RequestStatus(
        transport, effect, conflict, accepted or executed, failed, rejected
    )


def request_state(journal: Journal, request: Request) -> str:
    """Return transport status for existing ledger and dispatcher callers."""
    return status(journal, request).transport


def effect_confirmed(journal: Journal, request: Request) -> bool:
    """Distinguish confirmed quantity effects from rejected or pending requests."""
    return status(journal, request).effect == "CONFIRMED"


def effect_settled(journal: Journal, request: Request) -> bool:
    """Treat proven failure and rejection as settled without quantity effects."""
    return status(journal, request).effect_settled
