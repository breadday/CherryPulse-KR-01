import subprocess
import sys
from pathlib import Path

from pydantic import TypeAdapter


def test_virtual_demo_when_run_as_module() -> None:
    # Given: the actual module entry point, using only its own temporary database.
    command = [sys.executable, "-m", "execution"]
    # When
    result = subprocess.run(  # noqa: S603 - fixed local interpreter/module, no input shell.
        command,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    # Then
    assert result.returncode == 0, result.stderr
    summary = TypeAdapter(dict[str, int | str]).validate_json(result.stdout)
    assert summary["managed"] == 70
    assert summary["reserved"] == 0
    assert summary["cancel_unknown_reserved"] == 100
    assert summary["cancel_confirmed_reserved"] == 30
    assert summary["lifecycle"] == "CANCELLED"
    assert summary["virtual_calls"] == 2
    assert summary["replay_changes"] == 0
