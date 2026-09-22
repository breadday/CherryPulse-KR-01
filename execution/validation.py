"""Business checks performed after normalized idempotency comparison."""

from uuid import UUID

from typing_extensions import assert_never

from execution.facts import (
    Ack,
    Amended,
    Cancelled,
    Discrepancy,
    EffectRejected,
    Fact,
    Fill,
    QuarantinedFill,
    QuarantineReleased,
    Reconciled,
    Rejected,
    SendFailed,
    StopLossTriggered,
    Transport,
)
from execution.freshness import applied_version
from execution.linkage import check_release
from execution.models import Amend, Cancel, LedgerError, New, OrderCommand, Request
from execution.outcomes import effect_confirmed, effect_settled, status
from execution.projection import order, portfolio
from execution.storage import Journal


def _check_new(journal: Journal, command: New) -> None:
    position = portfolio(journal, command.symbol)
    match command.side:
        case "BUY":
            if position.entry_stopped or position.reconciliation_required:
                raise LedgerError("ENTRY_BLOCKED")
        case "SELL":
            if command.qty > position.available:
                raise LedgerError("SELL_QUANTITY_UNAVAILABLE")
        case _:
            assert_never(command.side)


def _check_change(journal: Journal, command: Amend | Cancel) -> None:
    target = next((r for r in journal.requests if r.order_id == command.target), None)
    if target is None:
        raise LedgerError("ORDER_NOT_FOUND")
    if target.command.symbol != command.symbol or target.command.side != command.side:
        raise LedgerError("TARGET_OWNERSHIP_MISMATCH")
    snapshot = order(journal, command.target)
    if command.link_version != snapshot.link_version:
        raise LedgerError("STALE_LINK_VERSION")
    if (
        snapshot.active is None
        or snapshot.active <= 0
        or snapshot.reconciliation_required
    ):
        raise LedgerError("TARGET_QUANTITY_UNCONFIRMED")
    pending = any(
        isinstance(r.command, (Amend, Cancel))
        and r.order_id == command.target
        and r.decision == "ACCEPTED"
        and not effect_settled(journal, r)
        for r in journal.requests
    )
    if pending:
        raise LedgerError("CHANGE_ALREADY_PENDING")
    match command:
        case Amend():
            if command.qty_delta < -snapshot.active:
                raise LedgerError("AMEND_QUANTITY_EXCEEDS_ACTIVE")
        case Cancel():
            if command.cancel_qty > snapshot.active:
                raise LedgerError("CANCEL_QUANTITY_EXCEEDS_ACTIVE")
        case _:
            assert_never(command)


def check_command(journal: Journal, command: OrderCommand) -> None:
    """Validate ownership, current linkage and locally proven quantity."""
    match command:
        case New():
            _check_new(journal, command)
        case Amend() | Cancel():
            _check_change(journal, command)
        case _:
            assert_never(command)


def _request(journal: Journal, request_id: UUID) -> Request:
    request = next((r for r in journal.requests if r.request_id == request_id), None)
    if request is None or request.decision != "ACCEPTED":
        raise LedgerError("REQUEST_NOT_FOUND_OR_UNSUPPORTED")
    return request


def _check_effect(journal: Journal, fact: Amended | Cancelled) -> None:
    request = _request(journal, fact.request_id)
    match fact:
        case Amended():
            match request.command:
                case Amend():
                    if (
                        request.order_id != fact.order_id
                        or request.command.qty_delta != fact.qty_delta
                    ):
                        raise LedgerError("AMEND_CORRELATION_MISMATCH")
                case New() | Cancel():
                    raise LedgerError("AMEND_CORRELATION_MISMATCH")
                case _:
                    assert_never(request.command)
        case Cancelled():
            match request.command:
                case Cancel():
                    if (
                        request.order_id != fact.order_id
                        or fact.qty > request.command.cancel_qty
                    ):
                        raise LedgerError("CANCEL_CORRELATION_MISMATCH")
                case New() | Amend():
                    raise LedgerError("CANCEL_CORRELATION_MISMATCH")
                case _:
                    assert_never(request.command)
        case _:
            assert_never(fact)
    if effect_confirmed(journal, request):
        raise LedgerError("EFFECT_ALREADY_CONFIRMED")


def _check_stop_loss_trigger(journal: Journal, fact: StopLossTriggered) -> None:
    """Reject a trigger evaluated against a superseded configuration."""
    if fact.config_version != applied_version(journal, fact.symbol):
        raise LedgerError("STALE_CONFIG_VERSION")


def check_fact(journal: Journal, fact: Fact) -> None:
    """Require exact correlation, preserving contradictory quantity evidence."""
    match fact:
        case Fill():
            _ = order(journal, fact.order_id)
        case StopLossTriggered():
            _check_stop_loss_trigger(journal, fact)
        case Ack() | Transport():
            _ = _request(journal, fact.request_id)
        case Amended() | Cancelled():
            _check_effect(journal, fact)
        case SendFailed():
            _check_unsent(journal, fact)
        case Rejected() | EffectRejected():
            _check_rejection(journal, fact)
        case Discrepancy() | QuarantinedFill():
            pass
        case QuarantineReleased():
            check_release(journal, fact)
        case Reconciled():
            _check_reconciliation(journal, fact)
        case _:
            assert_never(fact)


def _check_unsent(journal: Journal, fact: SendFailed) -> None:
    request = _request(journal, fact.request_id)
    current = status(journal, request)
    if current.positive_evidence:
        raise LedgerError("UNSENT_PROOF_INVALID")
    match fact.proof:
        case "NOT_INVOKED":
            valid = current.transport == "INTENT_PERSISTED"
        case "VERIFIED_UNSENT":
            valid = current.transport in ("SENDING", "UNKNOWN", "RECONCILING")
        case _:
            assert_never(fact.proof)
    if not valid:
        raise LedgerError("UNSENT_PROOF_INVALID")


def _check_reconciliation(journal: Journal, fact: Reconciled) -> None:
    target = next(
        (
            f
            for f in journal.facts
            if isinstance(f, Discrepancy)
            and f.event_id == fact.discrepancy_id
            and f.symbol == fact.symbol
        ),
        None,
    )
    if target is None:
        raise LedgerError("DISCREPANCY_NOT_FOUND")
    if any(
        isinstance(f, Reconciled) and f.discrepancy_id == fact.discrepancy_id
        for f in journal.facts
    ):
        raise LedgerError("DISCREPANCY_ALREADY_RESOLVED")
    if journal.revision != fact.reviewed_revision:
        raise LedgerError("STALE_RECONCILIATION_REVIEW")
    if (
        not fact.query.complete
        or fact.query.revision_at_finish != fact.reviewed_revision
    ):
        raise LedgerError("QUERY_EVIDENCE_INCOMPLETE")
    if fact.query.observed_managed != fact.observed_managed:
        raise LedgerError("QUERY_QUANTITY_MISMATCH")
    related = [r for r in journal.requests if r.command.symbol == fact.symbol]
    if any(
        status(journal, r).unresolved
        or order(journal, r.order_id).reconciliation_required
        for r in related
    ):
        raise LedgerError("RECONCILIATION_ORDER_UNRESOLVED")
    if portfolio(journal, fact.symbol).managed != fact.observed_managed:
        raise LedgerError("RECONCILIATION_QUANTITY_MISMATCH")


def _check_rejection(journal: Journal, fact: Rejected | EffectRejected) -> None:
    request = _request(journal, fact.request_id)
    if status(journal, request).transport == "INTENT_PERSISTED":
        raise LedgerError("REJECTION_BEFORE_INVOCATION")
    if isinstance(fact, EffectRejected) and not isinstance(
        request.command, (Amend, Cancel)
    ):
        raise LedgerError("EFFECT_REJECTION_REQUIRES_CHANGE")
