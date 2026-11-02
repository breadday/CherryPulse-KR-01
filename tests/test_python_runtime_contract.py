"""Active runtime policy for the REST-only development environment."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_targets_python_315_rest_environment_without_activex_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = project["project"]["requires-python"]
    dependencies = project["project"]["dependencies"]
    ruff_target = project["tool"]["ruff"]["target-version"]
    typecheck_target = project["tool"]["basedpyright"]["pythonVersion"]

    assert runtime == ">=3.15,<3.16"
    assert ruff_target == "py315"
    assert typecheck_target == "3.15"
    assert not any(item.lower().startswith("pyqt") for item in dependencies)


def test_rest_ci_uses_python_315_for_both_platform_jobs() -> None:
    workflow = (ROOT / ".github/workflows/rest-migration.yml").read_text(
        encoding="utf-8"
    )
    versions = re.findall(r"python-version:\s*['\"]?([^'\"\s]+)", workflow)

    assert versions == ["3.15", "3.15"]


def test_morning_runner_uses_the_project_rest_environment() -> None:
    runner = (ROOT / "scripts/r045-morning-run.cmd").read_text(encoding="utf-8")

    assert r".venv-rest\Scripts\python.exe" in runner
    assert "-m tools.r045_morning_run" in runner
    assert "py -" not in runner
