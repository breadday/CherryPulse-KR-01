import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_runner_records_baseline_before_stages_and_uses_scope_manifest():
    text = read("scripts/run-task.ps1")
    assert "baselineStatus" in text
    assert "baselineHead" in text
    assert "Write-AtomicJson $baselinePath" in text
    assert "-BaselinePath $baselinePath" in text
    assert "reviewPaths" in text
    assert "git diff main" not in text
    assert "baselineHashes" in text
    assert "refusing to overwrite" in text
    assert "-ScopePath $manifestPath" in text
    assert '$TaskId-SCOPE-MANIFEST.md' in text
    assert '$TaskId-SCOPE-MANIFEST.json' not in text
    assert "git add --all" not in text
    assert "git commit --only" in text


def test_runner_does_not_expose_all_untracked_files():
    text = read("scripts/run-task.ps1")
    assert "git add --intent-to-add" not in text
    assert r"\.log$" in text
    assert "broker/kiwoom_broker.py" in text
    assert "docs/agent-handoff/README.md" in text
    assert "return $p -match '^tests?/.*" in text
    assert r"\.tsx|\.jsx|\.toml|\.yaml|\.yml" not in text
    assert "[regex]::Escape($TaskId)" in text
    assert "reviewArtifactPath" in text
    assert "(SPEC|SCOPE-MANIFEST|IMPLEMENTATION|TEST)" in text
    assert "|REVIEW" not in text
    assert "git ls-files --others --exclude-standard" in text


def test_safety_check_is_path_scoped_and_blocks_new_forbidden_files():
    text = read("scripts/safety-check.ps1")
    assert "[string]$BaselinePath" in text
    assert "[string]$ScopePath" in text
    assert '"diff", "--check", $baseline.baselineHead, "--"' in text
    assert "-match '(^|/)broker/'" in text
    assert "RUN_MODE\\s*=\\s*[^\\r\\n]*\\blive\\b" in text
    assert "File-Hash" in text
    assert "untracked review path" in text
    assert "Load-Scope" in text


def test_reviewer_and_handoff_require_exact_current_task_scope():
    reviewer = read(".opencode/agents/reviewer.md")
    handoff = read("docs/agent-handoff/README.md")
    assert '"git rev-parse *": allow' in reviewer
    assert '"python *": allow' in reviewer
    assert "SCOPE-MANIFEST.json" not in reviewer
    assert "review only paths listed under reviewPaths" in reviewer
    assert "ignore handoff .log files" in reviewer
    assert "intent-to-add" in reviewer
    assert "reviewPaths" in handoff


POWERSHELL = "powershell"
RUNNER = "scripts/run-task.ps1"
SAFETY = "scripts/safety-check.ps1"


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True,
        encoding="utf-8", errors="replace"
    ).stdout


def ps(repo, script, *args, check=True, env=None):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        cwd=repo,
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
        check=check,
        env=env,
    )


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs" / "agent-handoff").mkdir(parents=True)
    for name in (RUNNER, SAFETY):
        (repo / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "tracked.py").write_text("baseline = 1\n", encoding="utf-8")
    (repo / "tests" / "existing_test.py").write_text("def test_existing(): pass\n", encoding="utf-8")
    git(repo, "init", "-b", "work")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "scope acceptance")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    return repo


def manifest(task, head, review, excluded=(), untracked=()):
    lines = [
        f"# {task} review scope manifest", "", f"- task_id: {task}",
        f"- base_head: {head}", "", "## Baseline paths excluded from this task",
        *[f"- {p}" for p in excluded], "", "## reviewPaths",
        *[f"- {p}" for p in review], "", "## untrackedTests",
        *[f"- {p}" for p in untracked], "", "## Review rule", "- exact scope",
    ]
    return "\n".join(lines) + "\n"


def baseline(repo, task="TASK-010"):
    head = git(repo, "rev-parse", "HEAD").strip()
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    paths = []
    for line in status:
        path = line[3:].split(" -> ")[-1].strip('"')
        paths.append(path.replace("\\", "/"))
    hashes = {path: git(repo, "hash-object", "--", path).strip() for path in sorted(set(paths))}
    data = {
        "taskId": task, "baselineHead": head, "baselineStatus": status,
        "baselinePaths": sorted(set(paths)), "baselineHashes": hashes,
        "branch": git(repo, "branch", "--show-current").strip(),
        "recordedAt": "2026-01-01T00:00:00Z",
    }
    path = repo / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, head


def run_safety(repo, mode, baseline_path, scope_path, check=True):
    return ps(repo, ROOT / SAFETY, "-Mode", mode, "-BaselinePath", str(baseline_path),
              "-ScopePath", str(scope_path), check=check)


def test_acceptance_runner_uses_real_git_scope_and_delivers_untracked_test(tmp_path):
    repo = make_repo(tmp_path)
    # Baseline deliberately contains all three index states, an old handoff, and a log.
    (repo / RUNNER).write_text("# staged baseline change\n" + (repo / RUNNER).read_text(encoding="utf-8"), encoding="utf-8")
    git(repo, "add", RUNNER)
    (repo / "tests" / "existing_test.py").write_text("def test_existing(): return 1\n", encoding="utf-8")
    (repo / "tests" / "baseline_test.py").write_text("def test_old(): pass\n", encoding="utf-8")
    (repo / "docs" / "agent-handoff" / "TASK-009-SPEC.md").write_text("old\n", encoding="utf-8")
    (repo / "docs" / "agent-handoff" / "old.log").write_text("old  \n", encoding="utf-8")
    git(repo, "add", "tests/baseline_test.py", "docs/agent-handoff/TASK-009-SPEC.md")
    git(repo, "reset", "tests/baseline_test.py", "docs/agent-handoff/TASK-009-SPEC.md")
    baseline_path, head = baseline(repo)
    handoff = repo / "docs" / "agent-handoff"
    (repo / RUNNER).write_text("# task change\n" + (repo / RUNNER).read_text(encoding="utf-8"), encoding="utf-8")
    git(repo, "add", RUNNER)  # staged source
    (repo / SAFETY).write_text("# task change\n" + (repo / SAFETY).read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "tests" / "test_scope.py").write_text("def test_scope(): pass\n", encoding="utf-8")
    (handoff / "TASK-010-IMPLEMENTATION.md").write_text("implementation\n", encoding="utf-8")
    review = [RUNNER, SAFETY, "tests/test_scope.py", "docs/agent-handoff/TASK-010-IMPLEMENTATION.md"]
    scope = tmp_path / "scope.md"
    scope.write_text(manifest("TASK-010", head, review, excluded=["docs/agent-handoff/old.log"], untracked=["tests/test_scope.py"]), encoding="utf-8")
    result = run_safety(repo, "post", "baseline.json", scope)
    prompt = "\n".join(f"{path}\n{(repo / path).read_text(encoding='utf-8')}" for path in review)
    assert result.returncode == 0 and "SAFETY_OK mode=post" in result.stdout
    assert "tests/test_scope.py" in prompt and "def test_scope(): pass" in prompt
    assert "baseline.json" not in prompt and "docs/agent-handoff/old.log" not in prompt
    assert "docs/agent-handoff/old.log" in scope.read_text(encoding="utf-8")
    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "scripts/run-task.ps1" in baseline_data["baselinePaths"]
    assert "tests/existing_test.py" in baseline_data["baselinePaths"]
    assert "tests/existing_test.py" not in review


@pytest.mark.parametrize("bad_path,content", [
    (".env.local", "TOKEN=not-a-secret\n"),
    ("broker/kiwoom.py", "transport = True\n"),
    ("broker/other_transport.py", "transport = True\n"),
    ("other.py", "value = 1\n"),
])
def test_acceptance_forbidden_or_out_of_scope_path_is_blocked(tmp_path, bad_path, content):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    path = repo / bad_path; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
    scope = tmp_path / "scope.md"
    scope.write_text(manifest("TASK-010", head, [bad_path]), encoding="utf-8")
    result = run_safety(repo, "pre", "baseline.json", scope, check=False)
    assert result.returncode != 0
    assert "Forbidden" in result.stderr or "Live" in result.stderr or "outside" in result.stderr


def test_acceptance_live_enablement_and_stale_manifest_are_blocked(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    (repo / "config.py").write_text("RUN_MODE = 'live'\n", encoding="utf-8")
    scope = tmp_path / "scope.md"; scope.write_text(manifest("TASK-010", head, ["tests/test_other.py"]), encoding="utf-8")
    result = run_safety(repo, "pre", "baseline.json", scope, check=False)
    assert result.returncode != 0 and "Live" in result.stderr
    (repo / "config.py").write_text("RUN_MODE = 'paper'\n", encoding="utf-8")
    result = run_safety(repo, "post", "baseline.json", scope, check=False)
    assert result.returncode != 0 and "stale" in result.stderr.lower()


def test_acceptance_intent_to_add_live_enablement_is_blocked(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    (repo / "config.py").write_text("RUN_MODE = 'live'\n", encoding="utf-8")
    git(repo, "add", "--intent-to-add", "config.py")
    scope = tmp_path / "scope.md"; scope.write_text(manifest("TASK-010", head, ["config.py"]), encoding="utf-8")
    result = run_safety(repo, "pre", "baseline.json", scope, check=False)
    assert result.returncode != 0 and "Live" in result.stderr


def test_acceptance_live_assignment_in_test_file_is_blocked_without_fixture_false_positive(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    path = repo / "tests" / "test_live_config.py"
    path.write_text("RUN_MODE = 'live'\n", encoding="utf-8")
    scope = tmp_path / "scope.md"
    scope.write_text(manifest("TASK-010", head, ["tests/test_live_config.py"], untracked=["tests/test_live_config.py"]), encoding="utf-8")
    result = run_safety(repo, "pre", "baseline.json", scope, check=False)
    assert result.returncode != 0 and "Live" in result.stderr


def test_acceptance_intent_to_add_trailing_whitespace_is_blocked(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    path = repo / "tests" / "test_scope.py"
    path.write_text("def test_scope(): pass  \n", encoding="utf-8")
    git(repo, "add", "--intent-to-add", "tests/test_scope.py")
    scope = tmp_path / "scope.md"
    scope.write_text(manifest("TASK-010", head, ["tests/test_scope.py"], untracked=["tests/test_scope.py"]), encoding="utf-8")
    result = run_safety(repo, "post", "baseline.json", scope, check=False)
    assert result.returncode != 0
    assert "Whitespace" in result.stderr or "diff --check" in result.stderr


@pytest.mark.parametrize("setup", ["protected", "detached"])
def test_acceptance_protected_and_detached_branches_are_blocked(tmp_path, setup):
    repo = make_repo(tmp_path)
    if setup == "protected": git(repo, "branch", "main") ; git(repo, "switch", "main")
    else: git(repo, "checkout", "--detach", "HEAD")
    baseline_path, head = baseline(repo); scope = tmp_path / "scope.md"; scope.write_text(manifest("TASK-010", head, []), encoding="utf-8")
    result = run_safety(repo, "pre", "baseline.json", scope, check=False)
    assert result.returncode != 0 and ("protected" in result.stderr.lower() or "detached" in result.stderr.lower())


def test_acceptance_scope_change_after_reviewer_blocks_post_validation(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    (repo / "tests" / "test_scope.py").write_text("def test_scope(): pass\n", encoding="utf-8")
    scope = tmp_path / "scope.md"; scope.write_text(manifest("TASK-010", head, ["tests/test_scope.py"], untracked=["tests/test_scope.py"]), encoding="utf-8")
    # The reviewer has returned, then a new source file appears: post validation must fail closed.
    run_safety(repo, "post", "baseline.json", scope, check=False)
    (repo / "new_source.py").write_text("x = 1\n", encoding="utf-8")
    result = run_safety(repo, "post", "baseline.json", scope, check=False)
    assert result.returncode != 0


def test_acceptance_untracked_test_cannot_be_omitted_from_manifest_section(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    (repo / "tests" / "test_scope.py").write_text("def test_scope(): pass\n", encoding="utf-8")
    scope = tmp_path / "scope.md"
    scope.write_text(manifest("TASK-010", head, ["tests/test_scope.py"]), encoding="utf-8")

    result = run_safety(repo, "post", "baseline.json", scope, check=False)

    assert result.returncode != 0 and "untrackedTests" in result.stderr


def test_acceptance_out_of_scope_source_cannot_be_hidden_as_excluded(tmp_path):
    repo = make_repo(tmp_path); baseline_path, head = baseline(repo)
    (repo / "tests" / "test_scope.py").write_text("def test_scope(): pass\n", encoding="utf-8")
    (repo / "other.py").write_text("value = 1\n", encoding="utf-8")
    scope = tmp_path / "scope.md"
    scope.write_text(manifest(
        "TASK-010", head, ["tests/test_scope.py"],
        excluded=["other.py"], untracked=["tests/test_scope.py"],
    ), encoding="utf-8")

    result = run_safety(repo, "post", "baseline.json", scope, check=False)

    assert result.returncode != 0 and "excluded" in result.stderr
