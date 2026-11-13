"""Retired COM/ActiveX probe; the active project runtime is REST-only."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Explain that local OCX creation has no REST equivalent and stop."""
    retire_com_script = import_module("tools.com_retired").retire_com_script
    return retire_com_script(
        "verify_kiwoom_com.py",
        "no REST equivalent for local OCX creation; do not run a COM probe",
    )


if __name__ == "__main__":
    raise SystemExit(main())
