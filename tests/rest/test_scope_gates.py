"""A REST scope proposal must never self-activate an execution scope."""

from datetime import datetime, timezone

import pytest

import adapters.kiwoom_rest_scope as scope_module
from adapters.kiwoom_rest_evidence import PaperReadScope
from adapters.kiwoom_rest_scope import (
    IdentityGates,
    OperatorApproval,
    RestScopeProposal,
    activation_steps,
)

SCOPE = PaperReadScope("PAPER-PC", "PAPER-APP")
NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def test_default_proposal_is_blocked_on_q01() -> None:
    proposal = RestScopeProposal(SCOPE)
    assert proposal.review_reason == "Q01_ORDER_IDENTITY_UNCONFIRMED"
    assert not proposal.can_activate


def test_each_gate_has_its_own_reason() -> None:
    assert (
        RestScopeProposal(
            SCOPE, gates=IdentityGates(q01_order_identity=True)
        ).review_reason
        == "Q02_FILL_IDENTITY_UNCONFIRMED"
    )
    assert (
        RestScopeProposal(
            SCOPE,
            gates=IdentityGates(q01_order_identity=True, q02_fill_identity=True),
        ).review_reason
        == "Q08_PRE_ACK_LINKAGE_UNCONFIRMED"
    )
    assert (
        RestScopeProposal(
            SCOPE,
            gates=IdentityGates(
                q01_order_identity=True,
                q02_fill_identity=True,
                q08_pre_ack_linkage=True,
            ),
        ).review_reason
        == "LIVE_PAPER_EVIDENCE_MISSING"
    )


def test_gates_without_approval_still_blocked() -> None:
    proposal = RestScopeProposal(
        SCOPE,
        gates=IdentityGates(
            q01_order_identity=True,
            q02_fill_identity=True,
            q08_pre_ack_linkage=True,
            live_paper_evidence=True,
        ),
    )
    assert proposal.review_reason == "OPERATOR_APPROVAL_MISSING"
    assert not proposal.can_activate


def test_full_gates_with_approval_is_explicit() -> None:
    proposal = RestScopeProposal(
        SCOPE,
        gates=IdentityGates(
            q01_order_identity=True,
            q02_fill_identity=True,
            q08_pre_ack_linkage=True,
            live_paper_evidence=True,
        ),
        approval=OperatorApproval("operator", NOW),
    )
    assert proposal.review_reason == "READY_FOR_MANUAL_ACTIVATION"
    assert proposal.can_activate
    steps = activation_steps()
    assert len(steps) == 3
    assert "manual" in steps[2]


def test_scope_module_never_touches_execution() -> None:
    assert not hasattr(scope_module, "to_execution_scope")
    assert "execution" not in dir(scope_module)


@pytest.mark.parametrize("approver", ["", "   "])
def test_anonymous_approval_rejected(approver: str) -> None:
    with pytest.raises(ValueError, match="APPROVAL_ANONYMOUS"):
        OperatorApproval(approver, NOW)


def test_naive_approval_time_rejected() -> None:
    with pytest.raises(ValueError, match="APPROVAL_TIME_NAIVE"):
        OperatorApproval("operator", datetime(2026, 10, 14))  # noqa: DTZ001 -- Intentionally naive to test rejection.
