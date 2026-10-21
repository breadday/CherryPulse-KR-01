"""Explicit paper-only bounded WebSocket quote probe without orders or row logs."""

# ruff: noqa: INP001 -- Standalone tool invoked with python -m.

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from adapters.kiwoom_rest_auth import (
    PaperTokenCache,
    PaperTokenIssuer,
    RequestPacer,
    paper_credentials_from_env,
)
from adapters.kiwoom_rest_stream import QuoteStreamState
from adapters.kiwoom_rest_ws import capture_stream


def main(argv: list[str] | None = None) -> int:
    """Describe offline by default, validating symbol/time before loading keys."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--execute-read-only", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 120:  # noqa: PLR2004 -- Bound the diagnostic session.
        parser.error("seconds must be between 1 and 120")
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
    if args.symbol is None:
        parser.error("symbol is required for execution")
    try:
        _ = QuoteStreamState((args.symbol,))
        credentials = paper_credentials_from_env()
        pacer = RequestPacer()
        cache = PaperTokenCache(credentials, PaperTokenIssuer(pacer).issue)
        result = capture_stream(
            cache.get, (args.symbol,), seconds=args.seconds, pacer=pacer
        )
    except Exception:  # noqa: BLE001 -- Never print keys, token, or raw broker failures.
        _ = sys.stdout.write(
            json.dumps(
                {
                    "mode": "PAPER",
                    "orders_enabled": False,
                    "reason": "SETUP_OR_STREAM_UNCONFIRMED",
                }
            )
            + "\n"
        )
        return 1
    report = asdict(result)
    report["mode"] = "PAPER"
    report["connected_after_capture"] = False
    _ = sys.stdout.write(json.dumps(report) + "\n")
    return 0 if result.quotes_observed > 0 and result.fresh_before_close else 1


if __name__ == "__main__":
    raise SystemExit(main())
