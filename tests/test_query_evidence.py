from typing import Literal

import pytest
from typing_extensions import assert_never

from execution.facts import Reconciled
from execution.models import LedgerError
from execution.query_evidence import QueryPages
from tests.conftest import Scenario
from tests.query_fixtures import complete_query
from tests.test_reconciliation import discrepancy, review

Condition = Literal[
    "missing", "duplicate", "error", "changed", "unfinished", "complete"
]


def with_query(
    payload: str, revision: int, *, condition: Condition = "complete"
) -> str:
    evidence = complete_query(revision, 100)
    match condition:
        case "missing":
            evidence = evidence.model_copy(
                update={
                    "fills": QueryPages(
                        expected_pages=2, received_pages=(1,), finished=True
                    )
                }
            )
        case "duplicate":
            evidence = evidence.model_copy(
                update={
                    "fills": QueryPages(
                        expected_pages=2, received_pages=(1, 1), finished=True
                    )
                }
            )
        case "error":
            evidence = evidence.model_copy(
                update={
                    "balances": QueryPages(
                        expected_pages=1,
                        received_pages=(1,),
                        finished=True,
                        error="QUERY_FAILED",
                    )
                }
            )
        case "changed":
            evidence = evidence.model_copy(update={"revision_at_start": revision - 1})
        case "unfinished":
            evidence = evidence.model_copy(
                update={
                    "orders": QueryPages(
                        expected_pages=1, received_pages=(1,), finished=False
                    )
                }
            )
        case "complete":
            pass
        case _:
            assert_never(condition)
    return (
        Reconciled.model_validate_json(payload)
        .model_copy(
            update={"query": evidence},
        )
        .model_dump_json()
    )


@pytest.mark.parametrize(
    "condition", ["missing", "duplicate", "error", "changed", "unfinished"]
)
def test_incomplete_query_cannot_resolve_discrepancy(
    scenario: Scenario, condition: Condition
) -> None:
    # Given
    scenario.allocate(100)
    target = discrepancy(scenario)
    before = scenario.book.snapshot()
    payload = with_query(review(scenario, target), before.revision, condition=condition)
    # When / Then
    with pytest.raises(LedgerError, match="QUERY_EVIDENCE_INCOMPLETE"):
        _ = scenario.book.ingest_json(payload)
    assert scenario.book.snapshot() == before


def test_complete_query_can_resolve_discrepancy(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    target = discrepancy(scenario)
    payload = with_query(review(scenario, target), scenario.book.snapshot().revision)
    # When
    assert scenario.book.ingest_json(payload)
    # Then
    assert not scenario.book.portfolio("005930").reconciliation_required
