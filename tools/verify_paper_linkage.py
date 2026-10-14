"""Explicit opt-in paper linkage check; reports booleans, never identifiers.

Reads the three history queries plus unfilled orders over the fixed mock
host, compares order-number sets across them in memory, and prints counts
with consistency booleans only. Raw order numbers, timestamps, accounts,
keys, and tokens never appear in the report.
"""

# ruff: noqa: INP001 -- Standalone tool with python -m invocation.

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import cast

from adapters.kiwoom_rest_auth import (
    PaperCredentials,
    PaperTokenCache,
    PaperTokenIssuer,
    RequestPacer,
)
from adapters.kiwoom_rest_readonly import ROW_KEYS, RestQuery, capture_query
from adapters.kiwoom_rest_transport import PaperReadOnlyTransport

LINKAGE_QUERIES = (
    (
        RestQuery.ORDER_DETAIL,
        {"qry_tp": "1", "stk_bond_tp": "0", "sell_tp": "0", "dmst_stex_tp": "%"},
    ),
    (
        RestQuery.ORDER_STATUS,
        {
            "stk_bond_tp": "0",
            "mrkt_tp": "0",
            "sell_tp": "0",
            "qry_tp": "0",
            "dmst_stex_tp": "KRX",
        },
    ),
    (RestQuery.FILLS, {"qry_tp": "0", "sell_tp": "0", "stex_tp": "0"}),
    (RestQuery.UNFILLED, {"all_stk_tp": "0", "trde_tp": "0", "stex_tp": "0"}),
)
ORIG_KEYS = ("ori_ord", "orig_ord_no")


def _rows(payload: object, row_key: str) -> list[dict[str, object]]:
    """Extract row dicts defensively; malformed tables yield no rows."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get(row_key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _numbers(rows: list[dict[str, object]], key: str) -> set[str]:
    """Collect non-empty string identifiers without ever printing them."""
    found: set[str] = set()
    for row in rows:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            found.add(value.strip())
    return found


def main(argv: list[str] | None = None) -> int:
    """Default to an offline description; require opt-in before reading secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-read-only", action="store_true")
    parser.add_argument("--symbol", default="005930")
    parser.add_argument("--max-pages", type=int, default=3)
    args = parser.parse_args(argv)
    if not 1 <= args.max_pages <= 10:  # noqa: PLR2004 -- Bound total runtime.
        parser.error("max-pages must be between 1 and 10")
    if not args.execute_read_only:
        _ = sys.stdout.write(
            json.dumps(
                {
                    "mode": "PAPER",
                    "network": False,
                    "orders_enabled": False,
                    "reason": "EXECUTION_NOT_REQUESTED",
                }
            )
            + "\n"
        )
        return 0
    try:
        credentials = PaperCredentials(
            os.environ.get("CHERRYPULSE_PAPER_APP_KEY", ""),
            os.environ.get("CHERRYPULSE_PAPER_APP_SECRET", ""),
        )
        pacer = RequestPacer()
        issuer = PaperTokenIssuer(pacer)
        cache = PaperTokenCache(credentials, issuer.issue)
        transport = PaperReadOnlyTransport(cache.get, timeout=10, pacer=pacer)
        snapshots: dict[str, dict[str, object]] = {}
        for query, body in LINKAGE_QUERIES:
            capture = capture_query(transport, query, body, max_pages=args.max_pages)
            if not capture.complete:
                _ = sys.stdout.write(
                    json.dumps(
                        {
                            "mode": "PAPER",
                            "network": True,
                            "orders_enabled": False,
                            "account_reconciled": False,
                            "reason": capture.reason,
                            "failing_query": query.value,
                        }
                    )
                    + "\n"
                )
                return 1
            table = [
                row
                for page in capture.pages
                for row in _rows(page.payload, ROW_KEYS[query])
                if str(row.get("stk_cd", args.symbol)) == args.symbol
            ]
            numbers = _numbers(table, "ord_no")
            snapshots[query.value] = {
                "rows": len(table),
                "distinct_orders": len(numbers),
                "orig_present": any(
                    isinstance(row.get(key), str) and cast("str", row.get(key)).strip()
                    for row in table
                    for key in ORIG_KEYS
                ),
                "fill_numbers": len(_numbers(table, "cntr_no")),
                "numbers": numbers,
            }
        order_sets = [
            cast("set[str]", snapshots[query.value]["numbers"])
            for query, _ in LINKAGE_QUERIES
            if cast("int", snapshots[query.value]["distinct_orders"]) > 0
        ]
        seen = len(order_sets) >= 2  # noqa: PLR2004 -- Cross-query linkage needs at least two evidence sets.
        sets_equal = seen and all(group == order_sets[0] for group in order_sets[1:])
        orig_clean = not any(
            snapshots[query.value]["orig_present"] for query, _ in LINKAGE_QUERIES
        )
        consistent = seen and sets_equal and orig_clean
        _ = sys.stdout.write(
            json.dumps(
                {
                    "mode": "PAPER",
                    "network": True,
                    "orders_enabled": False,
                    "account_reconciled": False,
                    "symbol": args.symbol,
                    "row_counts": {
                        query_id: snapshots[query_id]["rows"] for query_id in snapshots
                    },
                    "distinct_order_counts": {
                        query_id: snapshots[query_id]["distinct_orders"]
                        for query_id in snapshots
                    },
                    "order_seen_in_multiple": seen,
                    "order_sets_equal": sets_equal,
                    "orig_link_clean": orig_clean,
                    "fills_seen": cast("int", snapshots["ka10076"]["rows"]) > 0,
                    "fill_numbers_seen": any(
                        cast("int", snapshots[query_id]["fill_numbers"]) > 0
                        for query_id in snapshots
                    ),
                    "reason": "LINKAGE_CONSISTENT"
                    if consistent
                    else "LINKAGE_UNCONFIRMED",
                }
            )
            + "\n"
        )
    except Exception:  # noqa: BLE001 -- Do not echo credentials or auth exception context.
        _ = sys.stdout.write(
            json.dumps(
                {
                    "mode": "PAPER",
                    "orders_enabled": False,
                    "reason": "SETUP_OR_AUTH_UNCONFIRMED",
                }
            )
            + "\n"
        )
        return 1
    else:
        return 0 if consistent else 1


if __name__ == "__main__":
    raise SystemExit(main())
