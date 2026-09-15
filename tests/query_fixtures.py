from datetime import datetime, timedelta, timezone
from uuid import uuid4

from execution.query_evidence import QueryEvidence, QueryPages


def complete_query(revision: int, qty: int) -> QueryEvidence:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    page = QueryPages(expected_pages=1, received_pages=(1,), finished=True)
    return QueryEvidence(
        query_id=uuid4(),
        started_at=now,
        finished_at=now + timedelta(seconds=1),
        revision_at_start=revision,
        revision_at_finish=revision,
        observed_managed=qty,
        orders=page,
        fills=page,
        open_orders=page,
        balances=page,
    )
