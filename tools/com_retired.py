"""Fail-closed guidance for retired Kiwoom COM/ActiveX command-line probes."""

# ruff: noqa: INP001 -- Standalone helper imported by CLI scripts.

from __future__ import annotations

import sys


def retire_com_script(script: str, replacement: str) -> int:
    """Explain the REST-only replacement without loading COM or using network."""
    _ = sys.stderr.write(
        f"COM_RETIRED_REST_ONLY: {script} is disabled. "
        "The active runtime is 64-bit Python 3.15 with REST/HTTP and WebSocket.\n"
        f"Replacement: {replacement}\n"
        "No broker request was made. REST/WebSocket probes are offline by default; "
        "network execution requires explicit --execute-read-only and "
        "separate approval.\n"
    )
    return 2
