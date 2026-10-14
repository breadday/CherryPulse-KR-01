"""Explicit opt-in paper-only account probe; never sends orders or prints rows."""

# ruff: noqa: INP001 -- Standalone tool with python -m invocation.

from __future__ import annotations

import argparse
import json
import os
import sys

from adapters.kiwoom_rest_auth import (
    PaperCredentials,
    PaperTokenCache,
    PaperTokenIssuer,
    RequestPacer,
)
from adapters.kiwoom_rest_readonly import ROW_KEYS, RestQuery, capture_query
from adapters.kiwoom_rest_transport import PaperReadOnlyTransport


def main(argv: list[str] | None = None) -> int:
    """Default to an offline description; require opt-in before reading secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-read-only", action="store_true")
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
        specs = {
            RestQuery.POSITIONS: {"qry_tp": "2", "dmst_stex_tp": "KRX"},
            RestQuery.UNFILLED: {"all_stk_tp": "0", "trde_tp": "0", "stex_tp": "0"},
        }
        captures = [
            capture_query(transport, query, body, max_pages=args.max_pages)
            for query, body in specs.items()
        ]
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
    report = {
        "mode": "PAPER",
        "orders_enabled": False,
        "account_reconciled": False,
        "queries": [
            {
                "api_id": capture.query.value,
                "complete": capture.complete,
                "reason": capture.reason,
                "pages": len(capture.pages),
                "observed_rows": sum(
                    len(page.payload.get(ROW_KEYS[capture.query], []))
                    for page in capture.pages
                    if isinstance(page.payload.get(ROW_KEYS[capture.query]), list)
                ),
            }
            for capture in captures
        ],
    }
    _ = sys.stdout.write(json.dumps(report) + "\n")
    return 0 if all(capture.complete for capture in captures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
