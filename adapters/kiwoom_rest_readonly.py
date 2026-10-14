"""Independent read-only REST evidence boundary; no network or ledger mutation.

A transport is injected explicitly. This module never imports a third-party SDK,
credentials, or the execution engine. Completion is query evidence, not account
reconciliation or permission to trade.
"""

# pyright: reportUnnecessaryIsInstance=false, reportUnreachable=false
# Runtime validation deliberately checks untrusted injected responses.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, cast


class RestQuery(str, Enum):
    """Allowed account queries; callers cannot supply arbitrary API paths."""

    POSITIONS = "kt00018"
    UNFILLED = "ka10075"
    ORDER_DETAIL = "kt00007"
    ORDER_STATUS = "kt00009"
    FILLS = "ka10076"


@dataclass(frozen=True, slots=True)
class RestPage:
    """Transport response without authorization headers or credentials."""

    payload: dict[str, object]
    cont_yn: str
    next_key: str


class ReadOnlyTransport(Protocol):
    """Explicit injection point for a future audited transport binding."""

    def fetch_page(
        self,
        query: RestQuery,
        body: dict[str, str],
        cont_yn: str,
        next_key: str,
    ) -> RestPage:
        """Fetch one whitelisted read-only account page without automatic retry."""
        ...


@dataclass(frozen=True, slots=True)
class RestCapture:
    """Partial rows remain evidence and must never be treated as complete."""

    query: RestQuery
    pages: tuple[RestPage, ...]
    complete: bool
    reason: str


ROW_KEYS = {
    RestQuery.POSITIONS: "acnt_evlt_remn_indv_tot",
    RestQuery.UNFILLED: "oso",
    RestQuery.ORDER_DETAIL: "acnt_ord_cntr_prps_dtl",
    RestQuery.ORDER_STATUS: "acnt_ord_cntr_prst_array",
    RestQuery.FILLS: "cntr",
}
REQUIRED_INPUT_KEYS = {
    RestQuery.POSITIONS: frozenset({"qry_tp", "dmst_stex_tp"}),
    RestQuery.UNFILLED: frozenset({"all_stk_tp", "trde_tp", "stex_tp"}),
    RestQuery.ORDER_DETAIL: frozenset(
        {"qry_tp", "stk_bond_tp", "sell_tp", "dmst_stex_tp"}
    ),
    RestQuery.ORDER_STATUS: frozenset(
        {"stk_bond_tp", "mrkt_tp", "sell_tp", "qry_tp", "dmst_stex_tp"}
    ),
    RestQuery.FILLS: frozenset({"qry_tp", "sell_tp", "stex_tp"}),
}
OPTIONAL_INPUT_KEYS: dict[RestQuery, frozenset[str]] = {
    RestQuery.POSITIONS: frozenset(),
    RestQuery.UNFILLED: frozenset({"stk_cd"}),
    RestQuery.ORDER_DETAIL: frozenset({"ord_dt", "stk_cd", "fr_ord_no"}),
    RestQuery.ORDER_STATUS: frozenset({"ord_dt", "stk_cd", "fr_ord_no"}),
    RestQuery.FILLS: frozenset({"stk_cd", "ord_no"}),
}
# Backwards-compatible alias; new code prefers the required/optional split.
INPUT_KEYS = REQUIRED_INPUT_KEYS


def page_error(query: RestQuery, page: RestPage) -> str | None:
    """Reject missing success codes, malformed rows, and ambiguous cursors."""
    if not isinstance(page.payload, dict) or not isinstance(page.next_key, str):
        return "RESPONSE_INVALID"
    code = page.payload.get("return_code")
    if type(code) not in (int, str) or code not in (0, "0"):
        return "API_SUCCESS_UNCONFIRMED"
    rows = page.payload.get(ROW_KEYS[query])
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) for row in cast("list[object]", rows)
    ):
        return "ROWS_INVALID"
    if not isinstance(page.cont_yn, str) or page.cont_yn not in {"Y", "N"}:
        return "CONTINUATION_UNCONFIRMED"
    if page.cont_yn == "Y" and not page.next_key:
        return "CURSOR_MISSING"
    return None


def validate_query(query: RestQuery, body: dict[str, str], max_pages: int) -> None:
    """Validate all query inputs before any transport invocation."""
    if not isinstance(query, RestQuery):
        raise TypeError("QUERY_NOT_READ_ONLY")
    if type(max_pages) is not int or max_pages <= 0:
        raise ValueError("PAGE_LIMIT_INVALID")
    required = REQUIRED_INPUT_KEYS[query]
    allowed = required | OPTIONAL_INPUT_KEYS[query]
    if not required <= body.keys() or not body.keys() <= allowed:
        raise ValueError("QUERY_INPUT_INVALID")
    if any(not isinstance(value, str) or not value for value in body.values()):
        raise ValueError("QUERY_INPUT_INVALID")


def capture_query(
    transport: ReadOnlyTransport,
    query: RestQuery,
    body: dict[str, str],
    *,
    max_pages: int,
) -> RestCapture:
    """Bound pagination; preserve partial evidence and never retry exceptions."""
    validate_query(query, body, max_pages)
    pages: list[RestPage] = []
    cursors: set[str] = set()
    marker, cursor = "N", ""
    for _ in range(max_pages):
        try:
            page = transport.fetch_page(query, dict(body), marker, cursor)
        except Exception:  # noqa: BLE001 -- No raw exception may leak a credential.
            return RestCapture(
                query, tuple(pages), complete=False, reason="TRANSPORT_UNCONFIRMED"
            )
        if not isinstance(page, RestPage):
            return RestCapture(
                query, tuple(pages), complete=False, reason="RESPONSE_INVALID"
            )
        pages.append(page)
        reason = page_error(query, page)
        if reason:
            return RestCapture(query, tuple(pages), complete=False, reason=reason)
        if page.cont_yn == "N":
            return RestCapture(
                query, tuple(pages), complete=True, reason="QUERY_COMPLETE_ONLY"
            )
        if page.next_key in cursors:
            return RestCapture(
                query, tuple(pages), complete=False, reason="CURSOR_REPEATED"
            )
        cursors.add(page.next_key)
        marker, cursor = "Y", page.next_key
    return RestCapture(query, tuple(pages), complete=False, reason="PAGE_LIMIT_REACHED")
