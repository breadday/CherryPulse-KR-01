# ruff: noqa: INP001 -- Standalone CLI probe in the tools namespace.

"""Retired COM quote probe; use the REST WebSocket probe for active checks."""

from __future__ import annotations

import re
import sys
from datetime import datetime, time
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def seconds_until_start_at(value: str, now: datetime) -> tuple[datetime, float]:
    """Validate a same-day local start value without loading the retired COM stack."""
    match = re.fullmatch(r"([01][0-9]|2[0-3]):([0-5][0-9])", value)
    if match is None or now.tzinfo is None:
        raise ValueError("start time must be local HH:MM")  # noqa: TRY003 -- CLI validation message.
    target = datetime.combine(
        now.date(), time(int(match[1]), int(match[2])), tzinfo=now.tzinfo
    )
    delay = (target - now).total_seconds()
    if not 0 < delay <= 8 * 60 * 60:
        raise ValueError("start time must be later today and within eight hours")  # noqa: TRY003 -- CLI validation message.
    return target, delay


def main() -> int:
    """Direct operators to the offline-by-default REST WebSocket probe."""
    retire_com_script = import_module("tools.com_retired").retire_com_script
    return retire_com_script(
        "tools/inspect_kiwoom_realtime.py",
        "python -m tools.probe_kiwoom_ws <symbol> --seconds 30 (offline by default)",
    )


if __name__ == "__main__":
    raise SystemExit(main())
