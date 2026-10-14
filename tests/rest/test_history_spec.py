"""History TR identities stay documented-only until field evidence exists."""

import pytest

from adapters.kiwoom_rest_evidence import PaperReadScope, RestReadBatch, observe_query
from adapters.kiwoom_rest_history_spec import (
    GUIDE_URL,
    HISTORY_ENDPOINT,
    HISTORY_QUERIES,
    history_api_ids,
    history_sections,
    is_history_query,
)
from adapters.kiwoom_rest_readonly import RestPage, RestQuery, capture_query


class Transport:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def fetch_page(
        self, _query: RestQuery, _body: dict[str, str], _marker: str, _key: str
    ) -> RestPage:
        self.calls.append((_query, _marker, _key))
        return RestPage(
            {"return_code": 0, "acnt_evlt_remn_indv_tot": [], "oso": []}, "N", ""
        )


def test_spec_matches_official_guide_identities() -> None:
    assert HISTORY_ENDPOINT == "/api/dostk/acnt"
    assert GUIDE_URL.startswith("https://openapi.kiwoom.com/")
    assert [(spec.api_id, spec.section) for spec in HISTORY_QUERIES] == [
        ("kt00007", "orders"),
        ("kt00009", "orders"),
        ("ka10076", "fills"),
    ]
    assert history_sections() == frozenset({"orders", "fills"})
    assert all(not spec.inputs_confirmed for spec in HISTORY_QUERIES)
    assert all(not spec.outputs_confirmed for spec in HISTORY_QUERIES)


def test_history_ids_are_not_transport_queries() -> None:
    allowed = {query.value for query in RestQuery}
    assert history_api_ids().isdisjoint(allowed)
    assert is_history_query("kt00007")
    assert is_history_query("ka10076")
    assert not is_history_query("kt00018")
    assert not is_history_query(None)
    assert not is_history_query(0)


@pytest.mark.parametrize("api_id", sorted(history_api_ids()))
def test_history_ids_never_reach_transport(api_id: str) -> None:
    transport = Transport()
    with pytest.raises(TypeError, match="QUERY_NOT_READ_ONLY"):
        capture_query(transport, api_id, {}, max_pages=1)  # type: ignore[arg-type]
    assert transport.calls == []


def test_documented_history_does_not_complete_evidence() -> None:
    scope = PaperReadScope("PAPER-PC", "PAPER-APP")
    query = observe_query(
        transport=Transport(),
        scope=scope,
        query=RestQuery.POSITIONS,
        body={"qry_tp": "2", "dmst_stex_tp": "KRX"},
        max_pages=1,
        revision=lambda: 7,
    )
    batch = RestReadBatch(scope, (query,))
    assert history_sections() <= batch.missing_sections
    assert not batch.can_reconcile
