"""Read-only query interval evidence, separated from virtual reconciliation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import pairwise
from typing import TYPE_CHECKING

from adapters.kiwoom_rest_readonly import (
    ReadOnlyTransport,
    RestCapture,
    RestQuery,
    capture_query,
)

if TYPE_CHECKING:
    from collections.abc import Callable

REQUIRED_SECTIONS = frozenset({"orders", "fills", "open_orders", "balances"})
QUERY_SECTIONS = {
    RestQuery.POSITIONS: "balances",
    RestQuery.UNFILLED: "open_orders",
    RestQuery.ORDER_DETAIL: "orders",
    RestQuery.ORDER_STATUS: "orders",
    RestQuery.FILLS: "fills",
}


@dataclass(frozen=True, slots=True)
class PaperReadScope:
    """Non-secret aliases, not a proof that the app belongs to the claimed account."""

    account_alias: str
    app_alias: str

    def __post_init__(self) -> None:
        """Keep scope aliases explicit and unrelated to virtual execution scopes."""
        if any(
            re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", alias) is None
            for alias in (self.account_alias, self.app_alias)
        ):
            raise ValueError("READ_SCOPE_INVALID")


@dataclass(frozen=True, slots=True)
class ObservedQuery:
    """Preserve time and local event revision boundaries around one query."""

    scope: PaperReadScope
    capture: RestCapture
    started_at: datetime
    finished_at: datetime
    revision_at_start: int
    revision_at_finish: int

    @property
    def consistent(self) -> bool:
        """A complete interval still does not prove broker/account reconciliation."""
        return (
            self.capture.complete
            and self.started_at.utcoffset() is not None
            and self.finished_at.utcoffset() is not None
            and self.started_at <= self.finished_at
            and valid_revision(self.revision_at_start)
            and valid_revision(self.revision_at_finish)
            and self.revision_at_start == self.revision_at_finish
        )


def valid_revision(value: int) -> bool:
    """Reject bool/negative revisions without coercion."""
    return type(value) is int and value >= 0


def observe_query(  # noqa: PLR0913 -- Explicit scope and observation boundary injection.
    transport: ReadOnlyTransport,
    scope: PaperReadScope,
    query: RestQuery,
    body: dict[str, str],
    *,
    max_pages: int,
    revision: Callable[[], int],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ObservedQuery:
    """Capture metadata without importing, approving, or mutating a ledger."""
    first_revision, started = revision(), now()
    if not valid_revision(first_revision) or started.utcoffset() is None:
        raise ValueError("OBSERVATION_BOUNDARY_INVALID")
    capture = capture_query(transport, query, body, max_pages=max_pages)
    finished, last_revision = now(), revision()
    return ObservedQuery(
        scope, capture, started, finished, first_revision, last_revision
    )


@dataclass(frozen=True, slots=True)
class RestReadBatch:
    """Keep queries from one app/account alias together without enabling trading."""

    scope: PaperReadScope
    queries: tuple[ObservedQuery, ...]

    @property
    def missing_sections(self) -> frozenset[str]:
        """Never invent orders/fills evidence from balances or open orders."""
        observed = {QUERY_SECTIONS[query.capture.query] for query in self.queries}
        return REQUIRED_SECTIONS - observed

    @property
    def review_reason(self) -> str:
        """Expose the first missing boundary rather than treating empty as success."""
        if not self.queries:
            return "NO_QUERY_EVIDENCE"
        if any(query.scope != self.scope for query in self.queries):
            return "SCOPE_MISMATCH"
        if len({query.capture.query for query in self.queries}) != len(self.queries):
            return "DUPLICATE_QUERY_SECTION"
        if not all(query.consistent for query in self.queries):
            return "QUERY_INTERVAL_UNCONFIRMED"
        return self._interval_reason()

    def _interval_reason(self) -> str:
        """Check batch interval and coverage after each individual query passes."""
        ordered = sorted(self.queries, key=lambda query: query.started_at)
        if any(
            left.finished_at > right.started_at for left, right in pairwise(ordered)
        ):
            return "QUERY_INTERVAL_OVERLAP"
        revisions = {query.revision_at_start for query in self.queries}
        if len(revisions) != 1:
            return "EVENT_REVISION_CHANGED"
        if self.missing_sections:
            return "MISSING_QUERY_SECTIONS"
        return "BROKER_IDENTITY_MAPPING_UNVERIFIED"

    @property
    def can_reconcile(self) -> bool:
        """Real ledger approval remains unavailable until identity mappings exist."""
        return False
