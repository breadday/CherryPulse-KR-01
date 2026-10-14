"""History TR spec must match the read-only boundary without proving identity."""

import pytest

from adapters.kiwoom_rest_evidence import PaperReadScope, RestReadBatch, observe_query
from adapters.kiwoom_rest_history_spec import (
    GUIDE_URL,
    HISTORY_ENDPOINT,
    HISTORY_QUERIES,
    history_sections,
    is_history_query,
)
from adapters.kiwoom_rest_readonly import (
    OPTIONAL_INPUT_KEYS,
    REQUIRED_INPUT_KEYS,
    ROW_KEYS,
    RestPage,
    RestQuery,
    capture_query,
)

FULL_BODIES = {
    RestQuery.ORDER_DETAIL: {
        "qry_tp": "1",
        "stk_bond_tp": "0",
        "sell_tp": "0",
        "dmst_stex_tp": "%",
    },
    RestQuery.ORDER_STATUS: {
        "stk_bond_tp": "0",
        "mrkt_tp": "0",
        "sell_tp": "0",
        "qry_tp": "0",
        "dmst_stex_tp": "KRX",
    },
    RestQuery.FILLS: {"qry_tp": "0", "sell_tp": "0", "stex_tp": "0"},
}


class Transport:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def fetch_page(
        self, query: RestQuery, body: dict[str, str], marker: str, key: str
    ) -> RestPage:
        self.calls.append((query, body, marker, key))
        return RestPage({"return_code": 0, ROW_KEYS[query]: []}, "N", "")


def test_spec_matches_official_guide_identities() -> None:
    assert HISTORY_ENDPOINT == "/api/dostk/acnt"
    assert GUIDE_URL.startswith("https://openapi.kiwoom.com/")
    assert [(spec.api_id, spec.section) for spec in HISTORY_QUERIES] == [
        ("kt00007", "orders"),
        ("kt00009", "orders"),
        ("ka10076", "fills"),
    ]
    assert history_sections() == frozenset({"orders", "fills"})
    assert all(not spec.identity_confirmed for spec in HISTORY_QUERIES)


def test_spec_inputs_match_readonly_boundary() -> None:
    by_id = {query.value: query for query in RestQuery}
    for spec in HISTORY_QUERIES:
        query = by_id[spec.api_id]
        assert spec.required_inputs == REQUIRED_INPUT_KEYS[query]
        assert spec.optional_inputs == OPTIONAL_INPUT_KEYS[query]
        assert spec.row_key == ROW_KEYS[query]
    assert is_history_query("kt00007")
    assert is_history_query("ka10076")
    assert not is_history_query("kt00018")
    assert not is_history_query(None)
    assert not is_history_query(0)


def test_history_queries_capture_offline() -> None:
    for query, body in FULL_BODIES.items():
        transport = Transport()
        capture = capture_query(transport, query, dict(body), max_pages=1)
        assert capture.complete
        assert transport.calls[0][1] is not body


@pytest.mark.parametrize(
    ("query", "body"),
    [
        (RestQuery.ORDER_DETAIL, {"qry_tp": "1"}),
        (
            RestQuery.ORDER_DETAIL,
            {
                "qry_tp": "1",
                "stk_bond_tp": "0",
                "sell_tp": "0",
                "dmst_stex_tp": "%",
                "ord_no": "1",
            },
        ),
        (RestQuery.ORDER_STATUS, {"qry_tp": "0"}),
        (RestQuery.FILLS, {"qry_tp": "0", "sell_tp": "0"}),
        (
            RestQuery.FILLS,
            {"qry_tp": "0", "sell_tp": "0", "stex_tp": "0", "fr_ord_no": "1"},
        ),
    ],
)
def test_history_input_violations_never_reach_transport(
    query: RestQuery, body: dict[str, str]
) -> None:
    transport = Transport()
    with pytest.raises(ValueError, match="QUERY_INPUT_INVALID"):
        capture_query(transport, query, body, max_pages=1)
    assert transport.calls == []


def test_full_history_batch_still_needs_identity_mapping() -> None:
    scope = PaperReadScope("PAPER-PC", "PAPER-APP")
    bodies: dict[RestQuery, dict[str, str]] = {
        RestQuery.POSITIONS: {"qry_tp": "2", "dmst_stex_tp": "KRX"},
        RestQuery.UNFILLED: {"all_stk_tp": "0", "trde_tp": "0", "stex_tp": "0"},
        **FULL_BODIES,
    }
    queries = tuple(
        observe_query(
            transport=Transport(),
            scope=scope,
            query=query,
            body=body,
            max_pages=1,
            revision=lambda: 7,
        )
        for query, body in bodies.items()
    )
    batch = RestReadBatch(scope, queries)
    assert batch.missing_sections == frozenset()
    assert batch.review_reason == "BROKER_IDENTITY_MAPPING_UNVERIFIED"
    assert not batch.can_reconcile
