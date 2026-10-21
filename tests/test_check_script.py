"""Regression tests for the repository progress checker."""

import subprocess
import sys
from pathlib import Path


def test_checker_does_not_treat_its_own_guard_strings_as_back_imports() -> None:
    """The checker must not report its own literal scan patterns as imports."""
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "check.py"],
        cwd=root,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        text=True,
    )

    assert "check.py 에서 back import 중!" not in result.stdout
