"""REST scope activation gates; never produces an execution Scope.

A REST scope proposal names a paper account alias and app alias for future
live verification. Activation additionally requires Q01/Q02/Q08 identity
evidence from a real paper account plus an explicit operator approval that
lives outside this module. ``execution.models.Scope`` stays virtual-only:
this module does not import it and exposes no converter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    from adapters.kiwoom_rest_evidence import PaperReadScope

RestEnvironment = Literal["PAPER"]


@dataclass(frozen=True, slots=True)
class IdentityGates:
    """Live-evidence preconditions; all default to unconfirmed."""

    q01_order_identity: bool = False
    q02_fill_identity: bool = False
    q08_pre_ack_linkage: bool = False
    live_paper_evidence: bool = False

    @property
    def satisfied(self) -> bool:
        """Every gate must be confirmed; bools are never coerced."""
        return (
            self.q01_order_identity is True
            and self.q02_fill_identity is True
            and self.q08_pre_ack_linkage is True
            and self.live_paper_evidence is True
        )


@dataclass(frozen=True, slots=True)
class OperatorApproval:
    """Explicit human approval recorded outside any automated path."""

    approved_by: str
    approved_at: datetime

    def __post_init__(self) -> None:
        """Reject empty approvers and timezone-naive timestamps."""
        if not self.approved_by.strip():
            raise ValueError("APPROVAL_ANONYMOUS")
        if self.approved_at.utcoffset() is None:
            raise ValueError("APPROVAL_TIME_NAIVE")


@dataclass(frozen=True, slots=True)
class RestScopeProposal:
    """A named paper scope awaiting live evidence and human approval."""

    scope: PaperReadScope
    environment: RestEnvironment = "PAPER"
    gates: IdentityGates = IdentityGates()
    approval: OperatorApproval | None = None

    @property
    def review_reason(self) -> str:
        """Expose the first missing precondition instead of silent refusal."""
        if not self.gates.q01_order_identity:
            return "Q01_ORDER_IDENTITY_UNCONFIRMED"
        if not self.gates.q02_fill_identity:
            return "Q02_FILL_IDENTITY_UNCONFIRMED"
        if not self.gates.q08_pre_ack_linkage:
            return "Q08_PRE_ACK_LINKAGE_UNCONFIRMED"
        if not self.gates.live_paper_evidence:
            return "LIVE_PAPER_EVIDENCE_MISSING"
        if self.approval is None:
            return "OPERATOR_APPROVAL_MISSING"
        return "READY_FOR_MANUAL_ACTIVATION"

    @property
    def can_activate(self) -> bool:
        """Software never self-activates; manual wiring stays a separate step."""
        return self.gates.satisfied and self.approval is not None


def activation_steps() -> tuple[str, ...]:
    """List the manual steps that code alone must not perform."""
    return (
        "Confirm Q01/Q02/Q08 identity evidence from a real paper account.",
        "Record an explicit operator approval with name and time.",
        "Wire the approved scope to execution in a separate manual change.",
    )
