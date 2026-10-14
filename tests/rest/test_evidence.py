"""Two complete account reads cannot certify four-query broker reconciliation."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from adapters.kiwoom_rest_evidence import (
    ObservedQuery,
    PaperReadScope,
    RestReadBatch,
    observe_query,
)
from adapters.kiwoom_rest_readonly import RestPage, RestQuery

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)
SCOPE = PaperReadScope("PAPER-PC", "PAPER-APP")
BODY = {"qry_tp": "2", "dmst_stex_tp": "KRX"}


class Transport:
    def fetch_page(
        self, _query: RestQuery, _body: dict[str, str], _marker: str, _key: str
    ) -> RestPage:
        return RestPage(
            {"return_code": 0, "acnt_evlt_remn_indv_tot": [], "oso": []}, "N", ""
        )


def observation() -> ObservedQuery:
    return observe_query(
        Transport(),
        SCOPE,
        RestQuery.POSITIONS,
        BODY,
        max_pages=1,
        revision=lambda: 7,
        now=lambda: NOW,
    )


def test_complete_read_is_not_account_approval() -> None:
    query = observation()
    assert query.consistent
    batch = RestReadBatch(SCOPE, (query,))
    assert batch.missing_sections == frozenset({"orders", "fills", "open_orders"})
    assert batch.review_reason == "MISSING_QUERY_SECTIONS"
    assert not batch.can_reconcile


def test_revision_change_prevents_snapshot_consistency() -> None:
    revisions = iter([7, 8])
    query = observe_query(
        Transport(),
        SCOPE,
        RestQuery.POSITIONS,
        BODY,
        max_pages=1,
        revision=lambda: next(revisions),
        now=lambda: NOW,
    )
    assert not query.consistent
    assert RestReadBatch(SCOPE, (query,)).review_reason == "QUERY_INTERVAL_UNCONFIRMED"


def test_scope_mismatch_and_duplicate_queries_are_visible() -> None:
    query = observation()
    assert (
        RestReadBatch(PaperReadScope("OTHER", "APP"), (query,)).review_reason
        == "SCOPE_MISMATCH"
    )
    assert (
        RestReadBatch(SCOPE, (query, query)).review_reason == "DUPLICATE_QUERY_SECTION"
    )


def test_reversed_time_is_not_complete() -> None:
    query = replace(observation(), finished_at=NOW - timedelta(seconds=1))
    assert not query.consistent


@pytest.mark.parametrize("revision", [True, -1])
def test_invalid_revision_prevents_transport(revision: int) -> None:
    with pytest.raises(ValueError, match="OBSERVATION_BOUNDARY_INVALID"):
        observe_query(
            Transport(),
            SCOPE,
            RestQuery.POSITIONS,
            BODY,
            max_pages=1,
            revision=lambda: revision,
            now=lambda: NOW,
        )


def test_empty_batch_is_not_zero_positions() -> None:
    assert RestReadBatch(SCOPE, ()).review_reason == "NO_QUERY_EVIDENCE"


@pytest.mark.parametrize("alias", ["", "with space", "가명"])
def test_bad_scope_alias_rejected(alias: str) -> None:
    with pytest.raises(ValueError, match="READ_SCOPE_INVALID"):
        PaperReadScope(alias, "APP")


def test_two_queries_still_require_order_and_fill_evidence() -> None:
    first = observation()
    second = observe_query(
        Transport(),
        SCOPE,
        RestQuery.UNFILLED,
        {"all_stk_tp": "0", "trde_tp": "0", "stex_tp": "0"},
        max_pages=1,
        revision=lambda: 7,
        now=lambda: NOW,
    )
    batch = RestReadBatch(SCOPE, (first, second))
    assert batch.missing_sections == frozenset({"orders", "fills"})
    assert not batch.can_reconcile
    moved = replace(second, revision_at_start=8, revision_at_finish=8)
    assert (
        RestReadBatch(SCOPE, (first, moved)).review_reason == "EVENT_REVISION_CHANGED"
    )
    overlapping = replace(first, finished_at=NOW + timedelta(seconds=1))
    assert (
        RestReadBatch(SCOPE, (overlapping, second)).review_reason
        == "QUERY_INTERVAL_OVERLAP"
    )
