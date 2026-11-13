"""Retired COM connection probe; use the REST read-only probe instead."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Direct operators to the offline-by-default REST read-only probe."""
    retire_com_script = import_module("tools.com_retired").retire_com_script
    return retire_com_script(
        "verify_kiwoom_connection.py",
        "python -m tools.probe_kiwoom_rest (offline by default)",
    )


if __name__ == "__main__":
    raise SystemExit(main())
