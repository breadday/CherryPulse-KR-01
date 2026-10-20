"""Tests for the offline REST migration verifier command list.

The verifier is a runner: these tests pin which commands it may execute so a
future edit cannot silently drop or reorder the fixed offline checks.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "tools" / "verify_rest_migration.py"

spec = importlib.util.spec_from_file_location("verify_rest_migration", VERIFIER)
if spec is None or spec.loader is None:  # pragma: no cover - malformed install
    raise RuntimeError(str(VERIFIER))
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_verifier_defines_six_fixed_checks() -> None:
    """The runner must keep the six documented offline checks."""
    assert len(module.CHECKS) == 6
    joined = [" ".join(check) for check in module.CHECKS]
    assert any("pytest" in item for item in joined)
    assert any("ruff check" in item for item in joined)
    assert any("ruff format" in item for item in joined)
    assert any("basedpyright" in item for item in joined)
    assert any("node --test" in item for item in joined)
    assert any("git diff --check" in item for item in joined)


def test_typecheck_uses_documented_node_entrypoint_when_tools_present() -> None:
    """With .tools/typecheck installed, run node index.js per docs.

    The 32-bit engine Python cannot build basedpyright's nodejs-wheel
    dependency; docs/DEVELOPMENT-ENVIRONMENT.md pins the node CLI path.
    """
    local_entry = ROOT / ".tools" / "typecheck" / "basedpyright" / "index.js"
    command = module.typecheck_command()
    if local_entry.is_file():
        assert command[0] == "node"
        assert command[1] == str(local_entry)
    else:  # pragma: no cover - environment without .tools
        assert command[:3] == [sys.executable, "-m", "basedpyright"]


def test_typecheck_falls_back_to_module_form_without_local_tools() -> None:
    """CI installs basedpyright via pip and has no .tools: use -m there."""
    missing_entry = ROOT / ".tools" / "typecheck" / "missing" / "index.js"
    command = module.typecheck_command(local_entry=missing_entry)
    assert command[:3] == [sys.executable, "-m", "basedpyright"]


def test_typecheck_targets_rest_adapter_files() -> None:
    """Type checks must cover every kiwoom_rest adapter file."""
    command = module.typecheck_command()
    adapters = sorted((ROOT / "adapters").glob("kiwoom_rest*.py"))
    for adapter in adapters:
        assert str(adapter.relative_to(ROOT)) in command


def test_saved_report_schema_stays_backward_compatible() -> None:
    """Reports keep schema_version 1 and the fixed offline scope fields."""
    report = module.build_report(
        checked_at="2026-10-20T00:00:00+00:00",
        python="test-python",
        results=[{"command": ["x"], "exit_code": 0, "stdout": "", "stderr": ""}],
    )
    assert report["schema_version"] == 1
    assert report["scope"] == "offline REST boundary and board only"
    assert report["broker_verified"] is False
    assert report["passed"] is True
    assert json.dumps(report)  # fully serializable
