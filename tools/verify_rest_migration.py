"""Run fixed offline checks and atomically save evidence for the next AI.

This is a verification runner, not a self-running AI developer. It never calls
Kiwoom, reads credentials, opens an operating ledger, or sends orders.
"""

# ruff: noqa: INP001 -- Standalone verifier, matching existing tools layout.

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TYPECHECK_ENTRY = ROOT / ".tools" / "typecheck" / "basedpyright" / "index.js"
ENGINE_PYTHON = Path(os.environ.get("CHERRYPULSE_ENGINE_PYTHON", sys.executable))
FILES = [
    *[
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "adapters").glob("kiwoom_rest*.py"))
    ],
    *[
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "tests" / "rest").glob("*.py"))
    ],
    "tools/verify_rest_migration.py",
    "tools/probe_kiwoom_rest.py",
    "tools/probe_kiwoom_ws.py",
]


def typecheck_command(
    *, local_entry: Path = LOCAL_TYPECHECK_ENTRY, python: Path = ENGINE_PYTHON
) -> list[str]:
    """Build the basedpyright check command for this environment.

    The 32-bit engine Python cannot build basedpyright's nodejs-wheel
    dependency, so docs/DEVELOPMENT-ENVIRONMENT.md pins the node CLI
    entrypoint installed under .tools/typecheck. CI installs basedpyright
    via pip instead and has no .tools directory: fall back to ``-m`` there.
    """
    adapters = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "adapters").glob("kiwoom_rest*.py"))
    ]
    if local_entry.is_file():
        return ["node", str(local_entry), "--pythonpath", str(python), *adapters]
    return [sys.executable, "-m", "basedpyright", *adapters]


def build_report(
    *, checked_at: str, python: str, results: list[dict[str, object]]
) -> dict[str, object]:
    """Assemble the schema-version-1 verification report payload."""
    return {
        "schema_version": 1,
        "checked_at": checked_at,
        "python": python,
        "checks": results,
        "scope": "offline REST boundary and board only",
        "broker_verified": False,
        "windows_engine_verified": False,
        "passed": all(item["exit_code"] == 0 for item in results),
    }


CHECKS = [
    [sys.executable, "-m", "pytest", "--confcutdir=tests/rest", "tests/rest", "-q"],
    [sys.executable, "-m", "ruff", "check", *FILES],
    [sys.executable, "-m", "ruff", "format", "--check", *FILES],
    typecheck_command(),
    [
        "node",
        "--test",
        "web/board/board.test.js",
        "web/board/buy-preview.test.js",
        "web/board/log-view.test.js",
    ],
    ["git", "diff", "--check"],
]


def main() -> int:
    """Keep failures visible and leave a report even when a tool is unavailable."""
    results: list[dict[str, object]] = []
    for command in CHECKS:
        try:
            result = subprocess.run(  # noqa: S603 -- Fixed offline command list.
                command,
                cwd=ROOT,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=120,
            )
            item = {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            item = {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": type(exc).__name__,
            }
        results.append(item)
    report = build_report(
        checked_at=datetime.now(timezone.utc).isoformat(),
        python=sys.version,
        results=results,
    )
    destination = ROOT / "results" / "rest-migration-verification.json"
    destination.parent.mkdir(exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    _ = temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _ = temporary.replace(destination)
    _ = sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
