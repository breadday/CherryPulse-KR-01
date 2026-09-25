"""Read-only progress of durable virtual stop sell obligations."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from execution.facts import Rejected, SendFailed
from execution.models import New
from execution.outcomes import status
from execution.projection import order, portfolio
from execution.storage import Journal


@dataclass(frozen=True, slots=True)
class StopObligationView:
    """Evidence for one protected slice; no permission to retry a sell."""

    request_id: UUID
    order_id: UUID
    initial_qty: int
    filled_qty: int
    unfilled_qty: int
    reserved_qty: int
    state: Literal["FULFILLED", "BLOCKED_EVIDENCE", "REVIEW_REQUIRED", "PENDING"]
    failure_reason: str | None = None

    @property
    def next_action(self) -> Literal["NONE", "QUERY_BROKER", "REVIEW_AND_ALERT"]:
        """Expose an operator action, never a permission to resend."""
        if self.state == "FULFILLED":
            return "NONE"
        if self.state == "REVIEW_REQUIRED":
            return "REVIEW_AND_ALERT"
        return "QUERY_BROKER"


def stop_obligation_views(
    journal: Journal, symbol: str
) -> tuple[StopObligationView, ...]:
    """Project confirmed fills and uncertainty without inventing a new request."""
    requests = {r.request_id: r for r in journal.requests}
    position = portfolio(journal, symbol)
    views: list[StopObligationView] = []
    for obligation in journal.stop_sell_obligations:
        if obligation.symbol != symbol:
            continue
        request = requests.get(obligation.request_id)
        if request is None or not isinstance(request.command, New):
            views.append(
                StopObligationView(
                    obligation.request_id,
                    obligation.order_id,
                    obligation.qty,
                    0,
                    obligation.qty,
                    0,
                    "BLOCKED_EVIDENCE",
                )
            )
            continue
        snapshot = order(journal, obligation.order_id)
        outcome = status(journal, request)
        consistent = (
            request.order_id == obligation.order_id
            and request.command.symbol == symbol
            and request.command.side == "SELL"
            and request.command.qty == obligation.qty
            and request.command.stop_latch_version == obligation.rule_version
            and snapshot.original == obligation.qty
            and snapshot.filled <= obligation.qty
        )
        if (
            not consistent
            or snapshot.reconciliation_required
            or outcome.conflict
            or position.reconciliation_required
            or position.sell_uncertain
        ):
            state = "BLOCKED_EVIDENCE"
        elif snapshot.filled == obligation.qty:
            state = "FULFILLED"
        elif (
            snapshot.rejected or snapshot.submission_failed or snapshot.terminal_cancel
        ):
            state = "REVIEW_REQUIRED"
        elif outcome.transport in ("UNKNOWN", "RECONCILING"):
            state = "BLOCKED_EVIDENCE"
        else:
            state = "PENDING"
        reasons = [
            fact.reason
            for fact in journal.facts
            if isinstance(fact, (Rejected, SendFailed))
            and fact.request_id == obligation.request_id
        ]
        views.append(
            StopObligationView(
                obligation.request_id,
                obligation.order_id,
                obligation.qty,
                snapshot.filled,
                max(0, obligation.qty - snapshot.filled),
                snapshot.reserved,
                state,
                reasons[-1] if state == "REVIEW_REQUIRED" and reasons else None,
            )
        )
    return tuple(views)
