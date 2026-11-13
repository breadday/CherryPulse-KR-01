"""The active runtime must not load the retired Kiwoom COM scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("script", "replacement"),
    [
        ("verify_kiwoom_com.py", "no REST equivalent"),
        ("verify_kiwoom_connection.py", "tools.probe_kiwoom_rest"),
        ("verify_kiwoom_readonly.py", "tools.probe_kiwoom_rest"),
        ("tools/inspect_kiwoom_realtime.py", "tools.probe_kiwoom_ws"),
    ],
)
@pytest.mark.parametrize("mode", ["normal", "isolated"])
def test_com_script_fails_closed_with_rest_guidance(
    script: str, replacement: str, mode: str
) -> None:
    """Each COM entrypoint fails closed in regular and isolated Python mode."""
    command = [sys.executable]
    if mode == "isolated":
        command.append("-I")
    command.append(str(ROOT / script))
    result = subprocess.run(  # noqa: S603 -- Fixed local interpreter and script table.
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    assert result.returncode == 2
    assert "COM_RETIRED_REST_ONLY" in result.stderr
    assert replacement in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


@pytest.mark.parametrize("mode", ["normal", "isolated"])
def test_retired_com_modules_are_import_safe(mode: str) -> None:
    """Importing a retired entrypoint must not load PyQt or the COM control."""
    command = [sys.executable]
    if mode == "isolated":
        command.append("-I")
    import_check = (
        "import sys; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "import verify_kiwoom_com, verify_kiwoom_connection, verify_kiwoom_readonly; "
        "import tools.inspect_kiwoom_realtime; "
        "assert not any(name == 'PyQt5' or name.startswith('PyQt5.') "
        "for name in sys.modules)"
    )
    result = subprocess.run(  # noqa: S603 -- Fixed local interpreter and script table.
        [*command, "-c", import_check],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
