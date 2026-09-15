"""Virtual multi-query completeness metadata, separate from broker I/O."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from execution.models import Boundary, Key, PositiveQty, Quantity


class QueryPages(Boundary):
    """Keep page identities, terminal response status and explicit failure."""

    expected_pages: PositiveQty
    received_pages: tuple[PositiveQty, ...]
    finished: bool = Field(strict=True)
    error: Key | None = None

    @property
    def complete(self) -> bool:
        """Require each page exactly once and a successful terminal response."""
        return (
            self.finished
            and self.error is None
            and len(self.received_pages) == self.expected_pages
            and len(set(self.received_pages)) == self.expected_pages
            and all(page <= self.expected_pages for page in self.received_pages)
        )


class QueryEvidence(Boundary):
    """Correlate four virtual queries to one stable local event boundary."""

    query_id: UUID
    started_at: AwareDatetime
    finished_at: AwareDatetime
    revision_at_start: Quantity
    revision_at_finish: Quantity
    observed_managed: Quantity
    orders: QueryPages
    fills: QueryPages
    open_orders: QueryPages
    balances: QueryPages

    @property
    def complete(self) -> bool:
        """Reject query errors, missing pages, reversed time and intervening events."""
        return (
            self.finished_at >= self.started_at
            and self.revision_at_start == self.revision_at_finish
            and all(
                section.complete
                for section in (
                    self.orders,
                    self.fills,
                    self.open_orders,
                    self.balances,
                )
            )
        )
