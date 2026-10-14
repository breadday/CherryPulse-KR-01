"""Documented order/fill history query spec; not a transport allowlist.

API IDs and TR names below are confirmed against the official Kiwoom REST API
guide TR list (domestic-stock account section): ``kt00007``
계좌별주문체결내역상세요청, ``kt00009`` 계좌별주문체결현황요청, ``ka10076``
체결요청, all ``POST /api/dostk/acnt``. Required inputs, output rows, page
headers, and Q01/Q02/Q08 identity semantics remain UNCONFIRMED until real
paper-account evidence exists. Nothing here enables transport calls, order
submission, fill recording, or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass

HISTORY_ENDPOINT = "/api/dostk/acnt"
GUIDE_URL = "https://openapi.kiwoom.com/m/guide/apiguide?jobTpCode=03"


@dataclass(frozen=True, slots=True)
class HistoryQuerySpec:
    """One history TR identity without confirmed field mappings."""

    api_id: str
    tr_name: str
    section: str
    inputs_confirmed: bool = False
    outputs_confirmed: bool = False


HISTORY_QUERIES: tuple[HistoryQuerySpec, ...] = (
    HistoryQuerySpec("kt00007", "계좌별주문체결내역상세요청", "orders"),
    HistoryQuerySpec("kt00009", "계좌별주문체결현황요청", "orders"),
    HistoryQuerySpec("ka10076", "체결요청", "fills"),
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
