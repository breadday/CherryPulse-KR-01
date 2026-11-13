"""Retired COM/TR probe; use the scoped REST read-only probe instead."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Direct operators to the documented REST queries without TR equivalence."""
    retire_com_script = import_module("tools.com_retired").retire_com_script
    return retire_com_script(
        "verify_kiwoom_readonly.py",
        "python -m tools.probe_kiwoom_rest (offline by default; use the approved "
        "REST query checklist; legacy TRs do not map one-to-one)",
    )


if __name__ == "__main__":
    raise SystemExit(main())
