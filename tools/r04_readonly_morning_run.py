"""Scheduled R04 read-only probe. It never constructs an order or cancel request."""

# ruff: noqa: INP001 -- Standalone module invoked with python -m.

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KST = timezone(timedelta(hours=9))
QUERY_IDS = ("kt00018", "ka10075", "kt00007", "kt00009", "ka10076")
MAX_COUNT = 1_000_000
MAX_REASON_LENGTH = 64
SHA1_HEX_LENGTH = 40
WEEKEND_DAY_START = 5
MARKET_OPEN = (9, 0)
MARKET_CLOSE = (15, 20)


def market_gate(now: datetime) -> str:
    """Never claim live-session evidence outside weekday market hours."""
    if now.utcoffset() is None:
        return "CLOCK_UNCERTAIN"
    local = now.astimezone(KST)
    if local.weekday() >= WEEKEND_DAY_START:
        return "WEEKEND"
    start = local.replace(hour=9, minute=0, second=0, microsecond=0)
    end = local.replace(hour=15, minute=20, second=0, microsecond=0)
    if local < start:
        return "BEFORE_OPEN"
    if local > end:
        return "AFTER_CLOSE"
    return "MARKET_OPEN"


def _safe_reason(value: object) -> str | None:
    if (
        isinstance(value, str)
        and 0 < len(value) <= MAX_REASON_LENGTH
        and all(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in value)
    ):
        return value
    return None


def sanitize_rest_report(value: object) -> dict[str, object]:
    """Keep only query IDs, completeness, bounded reason, pages and row counts."""
    report = cast("dict[str, object]", value) if isinstance(value, dict) else {}
    raw_queries = report.get("queries")
    queries: list[dict[str, object]] = []
    if isinstance(raw_queries, list):
        for query in raw_queries:
            if not isinstance(query, dict):
                continue
            api_id = query.get("api_id")
            complete = query.get("complete")
            reason = _safe_reason(query.get("reason"))
            pages = query.get("pages")
            rows = query.get("observed_rows")
            if (
                api_id in QUERY_IDS
                and type(complete) is bool
                and reason is not None
                and type(pages) is int
                and 0 <= pages <= MAX_COUNT
                and type(rows) is int
                and 0 <= rows <= MAX_COUNT
            ):
                queries.append(
                    {
                        "api_id": api_id,
                        "complete": complete,
                        "reason": reason,
                        "pages": pages,
                        "observed_rows": rows,
                    }
                )
    return {
        "queries": queries,
        "orders_enabled": False,
        "account_reconciled": False,
    }


def sanitize_ws_report(value: object) -> dict[str, object]:
    """Keep fixed WebSocket evidence fields and discard raw payloads."""
    report = cast("dict[str, object]", value) if isinstance(value, dict) else {}
    safe: dict[str, object] = {
        "orders_enabled": False,
        "account_reconciled": False,
    }
    reason = _safe_reason(report.get("reason"))
    if reason is not None:
        safe["reason"] = reason
    for name in ("connections", "quotes_observed", "malformed_frames"):
        count = report.get(name)
        if type(count) is int and 0 <= count <= MAX_COUNT:
            safe[name] = count
    for name in ("fresh_before_close", "quote_saved"):
        flag = report.get(name)
        if type(flag) is bool:
            safe[name] = flag
    for name, allowed in {
        "failure_stage": {"TOKEN", "PACING", "CONNECT", "PROTOCOL", "CLOSE", "SETUP"},
        "failure_kind": {
            "TIMEOUT",
            "DEPENDENCY_ERROR",
            "OS_ERROR",
            "VALUE_ERROR",
            "RUNTIME_ERROR",
            "OTHER",
            "CLOSE_ERROR",
        },
    }.items():
        value = report.get(name)
        if isinstance(value, str) and value in allowed:
            safe[name] = value
    return safe


def fixed_commands(
    python_exe: str, symbol: str = "005930"
) -> tuple[list[str], list[str]]:
    """Return the only permitted subprocesses: REST reads and quote capture."""
    return (
        [
            python_exe,
            "-m",
            "tools.probe_kiwoom_rest",
            "--execute-read-only",
            "--max-pages",
            "3",
            "--include-history",
        ],
        [
            python_exe,
            "-m",
            "tools.probe_kiwoom_ws",
            symbol,
            "--seconds",
            "30",
            "--execute-read-only",
        ],
    )


def _run(command: list[str]) -> tuple[int, str]:
    """Capture output in memory only; never persist stdout/stderr verbatim."""
    try:
        completed = subprocess.run(  # noqa: S603 -- command comes from fixed_commands or _commit.
            command,
            cwd=ROOT,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, json.dumps({"reason": type(exc).__name__.upper()})
    return completed.returncode, completed.stdout


def _parse_json(output: str) -> object:
    try:
        return json.loads(output)
    except ValueError, TypeError:
        return {}


def _commit() -> str | None:
    code, output = _run(["git", "rev-parse", "--verify", "HEAD"])
    value = output.strip()
    valid_sha = len(value) == SHA1_HEX_LENGTH and all(
        char in "0123456789abcdef" for char in value
    )
    return value if code == 0 and valid_sha else None


def _atomic_write(destination: Path, document: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def run(now: datetime | None = None) -> tuple[int, dict[str, object]]:
    """Run bounded read-only checks during market hours and save sanitized evidence."""
    started = now or datetime.now(UTC)
    local_started = (
        started.astimezone(KST) if started.utcoffset() is not None else started
    )
    gate = market_gate(started)
    record: dict[str, object] = {
        "schema_version": 1,
        "run_at_kst": local_started.isoformat(),
        "commit": _commit(),
        "market_gate": gate,
        "orders_enabled": False,
        "steps": [],
    }
    exit_code = 0
    if gate != "MARKET_OPEN":
        record["status"] = "SKIPPED_OUTSIDE_MARKET"
        exit_code = 0
    else:
        rest_command, ws_command = fixed_commands(sys.executable)
        rest_code, rest_output = _run(rest_command)
        rest_report = sanitize_rest_report(_parse_json(rest_output))
        ws_code, ws_output = _run(ws_command)
        ws_report = sanitize_ws_report(_parse_json(ws_output))
        queries = rest_report["queries"]
        rest_ok = (
            rest_code == 0
            and isinstance(queries, list)
            and len(queries) == len(QUERY_IDS)
        )
        quote_count = ws_report.get("quotes_observed")
        ws_ok = (
            ws_code == 0
            and isinstance(quote_count, int)
            and quote_count > 0
            and ws_report.get("fresh_before_close") is True
        )
        record["steps"] = [
            {
                "step": "READ_ONLY_ACCOUNT",
                "exit_code": rest_code,
                "report": rest_report,
            },
            {"step": "READ_ONLY_WEBSOCKET", "exit_code": ws_code, "report": ws_report},
        ]
        record["status"] = "PASS" if rest_ok and ws_ok else "INCOMPLETE"
        exit_code = 0 if rest_ok and ws_ok else 1
    filename = f"r04-readonly-{local_started:%Y%m%d}.json"
    _atomic_write(RESULTS / filename, record)
    return exit_code, record


def main() -> int:
    """CLI entry point for Task Scheduler; no command-line order controls exist."""
    code, record = run()
    _ = sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
