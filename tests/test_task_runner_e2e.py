import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts" / "run-task.ps1"
SAFETY = ROOT / "scripts" / "safety-check.ps1"
GITIGNORE = ROOT / ".gitignore"


def run(repo, *args, check=True, env=None):
    return subprocess.run(
        args,
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
        env=env,
    )


def git(repo, *args):
    return run(repo, "git", *args).stdout


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "docs" / "agent-handoff").mkdir(parents=True)
    (repo / "scripts" / "run-task.ps1").write_text(RUNNER.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "scripts" / "safety-check.ps1").write_text(SAFETY.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / ".gitignore").write_text(GITIGNORE.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "tracked.py").write_text("baseline = 1\n", encoding="utf-8")
    write_opencode_stub(repo)
    git(repo, "init", "-b", "work")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "runner acceptance")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    return repo


def write_opencode_stub(repo):
    (repo / "opencode.cmd").write_text('@echo off\r\npython "%~dp0opencode_stub.py" "%3"\r\n', encoding="utf-8")
    stub_lines = (
        "import os",
        "import sys",
        "from pathlib import Path",
        "",
        'root = Path(os.environ["OPENCODE_STUB_ROOT"])',
        'task = os.environ["OPENCODE_STUB_TASK"]',
        "agent = sys.argv[1]",
        'mode = os.environ.get("OPENCODE_STUB_MODE", "pass")',
        'handoff = root / "docs" / "agent-handoff"',
        "",
        'if agent == "analyzer":',
        '    (handoff / f"{task}-SPEC.md").write_text("spec\\n", encoding="utf-8")',
        "    raise SystemExit(0)",
        'if agent == "implementer":',
        '    content = "RUN_MODE = \'live\'\\ndef test_runner_scope(): pass\\n" if mode == "unsafe" else "def test_runner_scope(): pass\\n"',
        '    (root / "tests" / "test_runner_scope.py").write_text(content, encoding="utf-8")',
        '    (handoff / f"{task}-IMPLEMENTATION.md").write_text("implementation\\n", encoding="utf-8")',
        "    raise SystemExit(0)",
        'if agent == "tester":',
        '    (handoff / f"{task}-TEST.md").write_text("tests passed\\n", encoding="utf-8")',
        "    raise SystemExit(0)",
        'if agent != "reviewer":',
        "    raise SystemExit(2)",
        'manifest = handoff / f"{task}-SCOPE-MANIFEST.md"',
        'manifest_text = manifest.read_text(encoding="utf-8")',
        'review_block = manifest_text.split("## reviewPaths", 1)[1].split("## untrackedTests", 1)[0]',
        'if "tests/test_runner_scope.py" not in review_block or "TASK-009-reviewer.log" in review_block:',
            "    raise SystemExit(4)",
        'if "test_runner_scope" not in (root / "tests" / "test_runner_scope.py").read_text(encoding="utf-8"):',
        "    raise SystemExit(5)",
        'if mode == "tamper":',
        '    with manifest.open("a", encoding="utf-8") as stream:',
        '        stream.write("# tampered\\n")',
        'if mode != "omit":',
        '    (handoff / f"{task}-REVIEW.md").write_text("PASS\\n", encoding="utf-8")',
    )
    (repo / "opencode_stub.py").write_text(
        "\n".join(stub_lines) + "\n",
        encoding="utf-8",
    )


def run_runner(repo, mode="pass"):
    env = os.environ.copy()
    env["PATH"] = f"{repo}{os.pathsep}{env['PATH']}"
    env["OPENCODE_STUB_TASK"] = "TASK-777"
    env["OPENCODE_STUB_MODE"] = mode
    env["OPENCODE_STUB_ROOT"] = str(repo)
    return run(
        repo,
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RUNNER),
        "-TaskId",
        "TASK-777",
        "-Goal",
        "scope acceptance",
        "-RepoRoot",
        str(repo),
        check=False,
        env=env,
    )


def test_runner_records_baseline_before_stages_and_delivers_exact_scope(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tracked.py").write_text("baseline = 2\n", encoding="utf-8")
    old_log = repo / "docs" / "agent-handoff" / "TASK-009-reviewer.log"
    old_log.write_text("old evidence\n", encoding="utf-8")

    result = run_runner(repo)

    assert result.returncode == 0 and "TASK_COMPLETE" in result.stdout
    baseline = json.loads((repo / "docs" / "agent-handoff" / "TASK-777-BASELINE.json").read_text(encoding="utf-8"))
    manifest = (repo / "docs" / "agent-handoff" / "TASK-777-SCOPE-MANIFEST.md").read_text(encoding="utf-8")
    status = git(repo, "status", "--short", "--untracked-files=all")
    assert "tracked.py" in baseline["baselinePaths"]
    assert "docs/agent-handoff/TASK-009-reviewer.log" not in baseline["baselinePaths"]
    assert "tests/test_runner_scope.py" in manifest
    assert "TASK-777-SCOPE-MANIFEST.md" in status
    assert "TASK-777-REVIEW.md" in status
    assert "TASK-777-BASELINE.json" not in status
    assert "TASK-009-reviewer.log" not in status
    for agent in ("analyzer", "implementer", "tester", "reviewer"):
        log_path = repo / "docs" / "agent-handoff" / f"TASK-777-{agent}.log"
        assert log_path.exists()
        assert log_path.name not in status
    assert old_log.exists()
    assert (repo / "docs" / "agent-handoff" / "TASK-777-REVIEW.md").read_text(encoding="utf-8") == "PASS\n"


@pytest.mark.parametrize("mode,expected", [
    ("tamper", "changed during review"),
    ("omit", "without required handoff"),
    ("unsafe", "Post safety check failed"),
])
def test_runner_blocks_manifest_tampering_and_missing_review_delivery(tmp_path, mode, expected):
    repo = make_repo(tmp_path)

    result = run_runner(repo, mode)

    assert result.returncode != 0
    assert expected in result.stderr


def test_safety_includes_changes_committed_after_baseline(tmp_path):
    repo = make_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD").strip()
    baseline_path = repo / "baseline.json"
    baseline_path.write_text(json.dumps({
        "taskId": "TASK-777", "baselineHead": head, "baselineStatus": [],
        "baselinePaths": [], "baselineHashes": {}, "branch": "work",
        "recordedAt": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")
    changed = repo / "tests" / "test_committed_scope.py"
    changed.write_text("def test_committed_scope(): pass\n", encoding="utf-8")
    git(repo, "add", "tests/test_committed_scope.py")
    git(repo, "commit", "-m", "mid-task change")
    scope = tmp_path / "scope.md"
    scope.write_text(
        f"# scope\n\n- task_id: TASK-777\n- base_head: {head}\n\n"
        "## Baseline paths excluded from this task\n\n## reviewPaths\n"
        "- tests/test_committed_scope.py\n\n## untrackedTests\n\n## Review rule\n- exact\n",
        encoding="utf-8",
    )

    result = run(
        repo, "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SAFETY),
        "-Mode", "post", "-BaselinePath", str(baseline_path), "-ScopePath", str(scope), check=False,
    )

    assert result.returncode == 0 and "SAFETY_OK mode=post" in result.stdout


@pytest.mark.parametrize("baseline_name,content", [("missing.json", None), ("malformed.json", "{")])
def test_safety_blocks_missing_or_malformed_baseline(tmp_path, baseline_name, content):
    repo = make_repo(tmp_path)
    baseline_path = repo / baseline_name
    if content is not None:
        baseline_path.write_text(content, encoding="utf-8")

    result = run(
        repo, "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SAFETY),
        "-Mode", "pre", "-BaselinePath", str(baseline_path), check=False,
    )

    assert result.returncode != 0
    assert "Baseline metadata" in result.stderr or "Invalid baseline metadata" in result.stderr
