"""Documented order/fill history query spec; identity mapping stays unverified.

API IDs, TR names, required/optional inputs, and row-table keys below are
confirmed against the official Kiwoom REST API guide TR list and its account
examples (``ka10076`` 체결요청, ``kt00007`` 계좌별주문체결내역상세요청,
``kt00009`` 계좌별주문체결현황요청, all ``POST /api/dostk/acnt``). The
identifier columns named here (order numbers, original order numbers, fill
numbers, timestamps) are column-name observations only: Q01/Q02/Q08 uniqueness
and linkage semantics remain UNCONFIRMED until real paper-account evidence
exists. Nothing here enables order submission or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass

HISTORY_ENDPOINT = "/api/dostk/acnt"
GUIDE_URL = "https://openapi.kiwoom.com/m/guide/apiguide?jobTpCode=03"


@dataclass(frozen=True, slots=True)
class HistoryQuerySpec:
    """One history TR with spec-level inputs; live identity unconfirmed."""

    api_id: str
    tr_name: str
    section: str
    required_inputs: frozenset[str]
    optional_inputs: frozenset[str]
    row_key: str
    identity_columns: tuple[str, ...]
    identity_confirmed: bool = False


HISTORY_QUERIES: tuple[HistoryQuerySpec, ...] = (
    HistoryQuerySpec(
        "kt00007",
        "계좌별주문체결내역상세요청",
        "orders",
        frozenset({"qry_tp", "stk_bond_tp", "sell_tp", "dmst_stex_tp"}),
        frozenset({"ord_dt", "stk_cd", "fr_ord_no"}),
        "acnt_ord_cntr_prps_dtl",
        ("ord_no", "ori_ord", "ord_tm", "cntr_qty", "ord_remnq", "mdfy_cncl"),
    ),
    HistoryQuerySpec(
        "kt00009",
        "계좌별주문체결현황요청",
        "orders",
        frozenset({"stk_bond_tp", "mrkt_tp", "sell_tp", "qry_tp", "dmst_stex_tp"}),
        frozenset({"ord_dt", "stk_cd", "fr_ord_no"}),
        "acnt_ord_cntr_prst_array",
        ("ord_no", "orig_ord_no", "cntr_no", "cntr_tm", "cntr_qty"),
    ),
    HistoryQuerySpec(
        "ka10076",
        "체결요청",
        "fills",
        frozenset({"qry_tp", "sell_tp", "stex_tp"}),
        frozenset({"stk_cd", "ord_no"}),
        "cntr",
        ("ord_no", "orig_ord_no", "ord_tm", "cntr_pric", "cntr_qty", "oso_qty"),
    ),
)


def history_api_ids() -> frozenset[str]:
    """Return documented history API IDs without opening any transport."""
    return frozenset(spec.api_id for spec in HISTORY_QUERIES)


def is_history_query(api_id: object) -> bool:
    """Check membership for strings only; never coerce other types."""
    return isinstance(api_id, str) and api_id in history_api_ids()


def history_sections() -> frozenset[str]:
    """Return evidence sections history queries could cover once confirmed."""
    return frozenset(spec.section for spec in HISTORY_QUERIES)
