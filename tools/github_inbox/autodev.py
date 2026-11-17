"""Owner-directed lab development: isolated clone, fixed tests, GitHub draft PR.

The model generates bounded file contents without tools. Only the host publishes.
This first development profile can change three public lab files, not trading code.
"""
import argparse
import ast
import builtins
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

import executor
import receiver

BASE_BRANCH = "feat/github-inbox-autodev"
FILES = (
    "tools/github_inbox/lab/status_text.py",
    "tools/github_inbox/lab/test_status_text.py",
    "docs/orchestration/STATUS-TEXT.md",
)
LABELS = {"WAITING": "대기 중", "RUNNING": "개발 중", "TEST_FAILED": "검증 실패",
          "PR_CREATED": "PR 작성 완료", "UNKNOWN": "확인 필요"}
PATCH_SCHEMA = {
    "type": "object",
    "properties": {"files": {"type": "array", "items": {
        "type": "object", "properties": {
            "path": {"type": "string", "enum": list(FILES)},
            "content": {"type": "string"}},
        "required": ["path", "content"], "additionalProperties": False}}},
    "required": ["files"], "additionalProperties": False,
}
PUBLIC_CODES = {"PR_CREATED", "PUBLISH_PENDING", "INTERRUPTED_NO_RETRY", "TASK_CHANGED_NO_RETRY",
                "TESTS_FAILED", "PATCH_REJECTED", "DEVELOPMENT_BLOCKED", "CODEX_FAILED",
                "CODEX_TIMEOUT", "CHATGPT_LOGIN_REQUIRED", "CODEX_CAPABILITY_MISSING",
                "NATIVE_CODEX_REQUIRED", "BASE_MISMATCH", "WORKSPACE_EXISTS", "BRANCH_CONFLICT"}


def parse_task(issue, target):
    if (issue.get("state") != "open" or issue.get("pull_request")
            or issue.get("user", {}).get("login") != receiver.OWNER
            or not issue.get("title", "").startswith(receiver.PREFIX)):
        return None
    try:
        task = json.loads(issue.get("body") or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(task, dict) or set(task) != {
        "version", "target", "action", "project", "expected_head", "instruction",
    }:
        return None
    if (type(task["version"]) is not int or task["version"] != 3
            or task["target"] != target or task["target"] != "AI5"
            or task["action"] != "develop" or task["project"] != "inbox-lab"
            or not isinstance(task["expected_head"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", task["expected_head"])
            or not isinstance(task["instruction"], str)
            or not 1 <= len(task["instruction"].strip()) <= 4000):
        return None
    return task


def report(task, code, stage, called=False, **fields):
    return {"target": task["target"], "action": "develop", "code": code,
            "stage": stage, "llm_called": called, "orders_called": False, **fields}


def checked_run(argv, cwd, env, timeout=60):
    result = executor.run_capture(argv, cwd, env, timeout=timeout)
    if result.returncode:
        raise RuntimeError("LOCAL_COMMAND_FAILED")
    return result.stdout.rstrip("\r\n")


def git_env():
    env = executor.codex_environment()
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", PYTHONUTF8="1")
    return env


def prepare(task, issue, root):
    workspace = root / "workspaces" / (task["target"] + "-" + str(issue["number"]))
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if workspace.exists():
        raise ValueError("WORKSPACE_EXISTS")
    env = git_env()
    checked_run(["git", "clone", "--single-branch", "--branch", BASE_BRANCH,
                 "https://github.com/" + receiver.REPO + ".git", str(workspace)], root, env, 120)
    head = checked_run(["git", "rev-parse", "HEAD"], workspace, env)
    if head != task["expected_head"]:
        raise ValueError("BASE_MISMATCH")
    return workspace


def validate_patch(value):
    if not isinstance(value, dict) or set(value) != {"files"} or not isinstance(value["files"], list):
        raise ValueError("PATCH_REJECTED")
    if len(value["files"]) != len(FILES):
        raise ValueError("PATCH_REJECTED")
    changes = {}
    for item in value["files"]:
        if (not isinstance(item, dict) or set(item) != {"path", "content"}
                or not isinstance(item["path"], str) or item["path"] not in FILES
                or item["path"] in changes or not isinstance(item["content"], str)
                or not 1 <= len(item["content"].encode("utf-8")) <= 24000
                or "\x00" in item["content"]
                or re.search(r"-----BEGIN .*PRIVATE KEY|\b(?:ghp_|github_pat_|sk-)[A-Za-z0-9_\-]{20,}", item["content"])):
            raise ValueError("PATCH_REJECTED")
        changes[item["path"]] = item["content"].replace("\r\n", "\n")
        if item["path"].endswith(".py"):
            validate_python(item["path"], changes[item["path"]])
    if sum(len(text.encode("utf-8")) for text in changes.values()) > 60000:
        raise ValueError("PATCH_REJECTED")
    return changes


def validate_python(path, content):
    """Narrow syntax contract for this pure-function lab, not a general Python sandbox."""
    try:
        tree = ast.parse(content)
    except SyntaxError as error:
        raise ValueError("PATCH_REJECTED") from error
    tests = path.endswith("test_status_text.py")
    allowed_calls = {"isinstance", "TypeError", "len", "str", "describe"}
    allowed_attrs = {"get", "assertEqual", "assertRaises", "subTest", "TestCase", "main", "describe"}
    forbidden_nodes = (ast.Lambda, ast.Try, ast.While, ast.Global, ast.Nonlocal,
                       ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom, ast.Delete)
    for node in ast.walk(tree):
        if isinstance(node, forbidden_nodes):
            raise ValueError("PATCH_REJECTED")
        if isinstance(node, ast.Name):
            if (node.id.startswith("__") and node.id != "__name__") or (
                    node.id in vars(builtins) and node.id not in allowed_calls | {"__name__"}):
                raise ValueError("PATCH_REJECTED")
        if isinstance(node, ast.Attribute) and node.attr not in allowed_attrs:
            raise ValueError("PATCH_REJECTED")
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.decorator_list:
            raise ValueError("PATCH_REJECTED")
        if isinstance(node, ast.ClassDef) and (not tests or node.keywords):
            raise ValueError("PATCH_REJECTED")
        if isinstance(node, ast.Import):
            if not tests or any(alias.name not in {"unittest", "status_text"} or alias.asname for alias in node.names):
                raise ValueError("PATCH_REJECTED")
        if isinstance(node, ast.ImportFrom):
            if (not tests or node.level or node.module != "status_text"
                    or any(alias.name != "describe" or alias.asname for alias in node.names)):
                raise ValueError("PATCH_REJECTED")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in allowed_calls:
                    raise ValueError("PATCH_REJECTED")
            elif not isinstance(node.func, ast.Attribute) or node.func.attr not in allowed_attrs - {"TestCase"}:
                raise ValueError("PATCH_REJECTED")
            elif node.func.attr == "main" and (node.args or node.keywords):
                raise ValueError("PATCH_REJECTED")


def generate(task, workspace, codex, root):
    env = executor.codex_environment()
    current = {path: (workspace / path).read_text(encoding="utf-8")
               if (workspace / path).is_file() else None for path in FILES}
    with tempfile.TemporaryDirectory(prefix="dev-generation-", dir=root) as directory:
        work = Path(directory)
        (work / "schema.json").write_text(json.dumps(PATCH_SCHEMA), encoding="utf-8")
        executor.preflight(codex, work, env)
        prompt = (
            "공개 저장소의 작은 개발 작업을 수행할 변경 파일 전체 내용을 JSON으로 작성하라. "
            "도구/셸/네트워크를 호출하지 마라. 제공된 세 경로만 변경한다. 외부 의존성, I/O, "
            "브로커, 인증, subprocess, 파일/네트워크 접근 없이 순수 함수와 unittest를 작성한다. "
            "status_text.py의 describe(code)는 아래 문자열 매핑을 반환한다. 미지정 문자열은 "
            "UNKNOWN의 값, 문자열이 아니면 TypeError다. test_status_text.py는 unittest로 이를 "
            "검증한다. STATUS-TEXT.md는 함수 사용법과 한계를 한국어로 설명한다. "
            "구현에는 import 없이 dict.get, isinstance, TypeError만 사용한다. 테스트는 "
            "import unittest와 from status_text import describe, unittest.TestCase, "
            "self.assertEqual/assertRaises/subTest만 사용한다. 데코레이터/동적 실행은 쓰지 않는다. "
            "코드 실행/테스트 성공을 주장하지 마라. 전체 파일 내용을 반환한다.\n"
            + json.dumps({"instruction": task["instruction"], "labels": LABELS,
                          "current_files": current}, ensure_ascii=False)
        )
        result = executor.run_capture(executor.exec_argv(codex, work), work, env,
                                      timeout=600, payload=prompt)
        if result.returncode:
            raise ValueError("CODEX_FAILED")
        answer = work / "answer.json"
        if answer.stat().st_size > 200000:
            raise ValueError("PATCH_REJECTED")
        return validate_patch(json.loads(answer.read_text(encoding="utf-8")))


def apply_patch(workspace, changes):
    for path, content in changes.items():
        destination = workspace / path
        if any(parent.is_symlink() for parent in (destination, *destination.parents)):
            raise ValueError("PATCH_REJECTED")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")


def run_tests(workspace, log_root):
    env = git_env()
    lab = workspace / "tools/github_inbox/lab"
    commands = [
        [sys.executable, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover",
         "-s", str(lab), "-p", "test_*.py", "-v"],
        [sys.executable, "-I", "-B", "-X", "utf8",
         str(Path(__file__).with_name("autodev_acceptance.py")), str(lab)],
    ]
    counts = []
    for index, argv in enumerate(commands):
        result = executor.run_capture(argv, workspace, env, timeout=60)
        (log_root / f"test-{index}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        match = re.search(r"Ran (\d+) tests? in ", result.stdout + result.stderr)
        if result.returncode or not match or int(match[1]) < 1:
            raise ValueError("TESTS_FAILED")
        counts.append(int(match[1]))
    # Detect edits to files outside the three permitted paths, including untracked files.
    status = checked_run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], workspace, env)
    changed = {entry[3:] for entry in status.split("\0") if entry}
    if not changed.issubset(set(FILES)):
        raise ValueError("PATCH_REJECTED")
    return counts


def api(path, payload=None):
    return receiver.api("repos/" + receiver.REPO + "/" + path, payload)


def publish(ready, task, issue):
    """Only deterministic Git objects/unique branch+PR operations; never invoke AI."""
    base = api("git/commits/" + task["expected_head"])
    tree = api("git/trees", {"base_tree": base["tree"]["sha"], "tree": [
        {"path": path, "mode": "100644", "type": "blob", "content": content}
        for path, content in ready["changes"].items()]})
    identity = {"name": receiver.OWNER,
                "email": "34202276+breadday@users.noreply.github.com", "date": ready["date"]}
    commit = api("git/commits", {"message": f"feat(lab): 자동 개발 작업 #{issue['number']} 상태 안내 구현",
                                "tree": tree["sha"], "parents": [task["expected_head"]],
                                "author": identity, "committer": identity})
    branch = f"orchestration/{task['target']}-issue-{issue['number']}"
    try:
        existing = api("git/ref/heads/" + branch)
    except RuntimeError:
        existing = api("git/refs", {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
    if existing["object"]["sha"] != commit["sha"]:
        raise ValueError("BRANCH_CONFLICT")
    prs = api(f"pulls?state=all&head={receiver.OWNER}:{branch}&base={BASE_BRANCH}")
    if prs:
        pr = prs[0]
    else:
        pr = api("pulls", {"title": f"자동 개발 #{issue['number']}: 상태 코드 한글 안내",
                           "base": BASE_BRANCH, "head": branch, "draft": True,
                           "body": "GitHub 작업지시에 따라 전용 개발 폴더에 상태 안내 함수를 구현했습니다.\n\n"
                           + "변경: " + ", ".join(FILES) + "\n\n"
                           + f"실행기 검증: 생성 unittest {ready['counts'][0]}건, 고정 인수 검사 {ready['counts'][1]}건 통과. "
                           + "모델의 성공 주장 대신 실행기의 종료 코드로 확인했습니다.\n\n"
                           + f"지시: #{issue['number']}. main 병합·배포·주문은 별도 단계입니다."})
    number = pr["number"]
    if type(number) is not int or not re.fullmatch(r"[0-9a-f]{40}", commit["sha"]):
        raise RuntimeError("INVALID_PUBLISH_RESPONSE")
    return report(task, "PR_CREATED", "PUBLISHED", True, commit=commit["sha"],
                  pull_request_url=f"https://github.com/{receiver.REPO}/pull/{number}",
                  files_changed=list(FILES), tests_passed=ready["counts"])


def develop(issue, task, codex, journal):
    journal.db.execute("""CREATE TABLE IF NOT EXISTS dev_ready (
        target TEXT, issue INTEGER, task_hash TEXT, payload TEXT,
        PRIMARY KEY (target, issue))""")
    journal.db.commit()
    saved = journal.claim(issue, task)
    row = journal.db.execute("SELECT task_hash, payload FROM dev_ready WHERE target=? AND issue=?",
                             (task["target"], issue["number"])).fetchone()
    if saved is not None:
        if saved["code"] == "TASK_CHANGED_NO_RETRY":
            return report(task, "TASK_CHANGED_NO_RETRY", "CLAIM", True)
        if saved["code"] not in ("INTERRUPTED_NO_RETRY", "PUBLISH_PENDING"):
            return saved
        if row is None:
            return report(task, "INTERRUPTED_NO_RETRY", "CLAIM", True)
    stage = "PREPARE"
    called = False
    try:
        if row is None:
            workspace = prepare(task, issue, journal.root)
            log_root = journal.root / ("development-" + task["target"] + "-" + str(issue["number"]))
            log_root.mkdir(exist_ok=False)
            stage = "GENERATE"
            called = True  # Conservative invocation-attempt indicator, not a billing receipt.
            changes = generate(task, workspace, codex, journal.root)
            stage = "APPLY"
            apply_patch(workspace, changes)
            stage = "TEST"
            counts = run_tests(workspace, log_root)
            # Tests may mutate allowed files: publish only the exact tested content.
            tested = {path: (workspace / path).read_text(encoding="utf-8") for path in FILES}
            if tested != changes:
                raise ValueError("PATCH_REJECTED")
            ready = {"changes": changes, "counts": counts,
                     "date": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with journal.db:
                journal.db.execute("INSERT INTO dev_ready VALUES (?, ?, ?, ?)",
                                   (task["target"], issue["number"], executor.digest(task), json.dumps(ready)))
        else:
            if row[0] != executor.digest(task):
                raise ValueError("TASK_CHANGED_NO_RETRY")
            ready = json.loads(row[1])
        stage = "PUBLISH"
        called = True
        result = publish(ready, task, issue)
    except subprocess.TimeoutExpired:
        result = report(task, "CODEX_TIMEOUT" if stage == "GENERATE" else "DEVELOPMENT_BLOCKED", stage, called)
    except (ValueError, OSError, RuntimeError) as error:
        code = str(error) if isinstance(error, ValueError) and str(error) in PUBLIC_CODES else (
            "PUBLISH_PENDING" if stage == "PUBLISH" else "DEVELOPMENT_BLOCKED")
        if code in {"CHATGPT_LOGIN_REQUIRED", "CODEX_CAPABILITY_MISSING", "NATIVE_CODEX_REQUIRED"}:
            called = False
        result = report(task, code, stage, called)
    journal.finish(issue, task, result)
    # Fixed fields only: full test output remains local; no free-text model output is uploaded.
    handoff = journal.root / f"handoff-{task['target']}-{issue['number']}.json"
    handoff.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def poll(target, codex, journal, dry_run=False):
    if receiver.api("user")["login"] != receiver.OWNER:
        raise ValueError("OWNER_REQUIRED")
    pages = receiver.api("repos/" + receiver.REPO + "/issues?state=open&per_page=100", paginate=True)
    for issue in (item for page in pages for item in page):
        task = parse_task(issue, target)
        if task is None:
            continue
        prefix = f"<!-- hermes-dev-v3:{issue['number']}:{executor.digest(task)[:16]}:"
        endpoint = f"repos/{receiver.REPO}/issues/{issue['number']}/comments"
        comments = [c for page in receiver.api(endpoint + "?per_page=100", paginate=True) for c in page]
        if receiver.already_reported(comments, prefix + "done -->"):
            continue
        if dry_run:
            print(f"DRY_RUN develop #{issue['number']}", flush=True)
            return 1
        result = develop(issue, task, codex, journal)
        suffix = "pending -->" if result["code"] == "PUBLISH_PENDING" else "done -->"
        tag = prefix + suffix
        if not receiver.already_reported(comments, tag):
            receiver.api(endpoint, {"body": tag + "\n\n```json\n" + json.dumps(result, indent=2) + "\n```"})
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["AI5"], required=True)
    parser.add_argument("--project", required=True, help="Installed inbox clone for v1/v2")
    parser.add_argument("--codex", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--enable-development", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    if platform.node().upper() != receiver.TARGETS[args.target]:
        parser.error("PC_TARGET_MISMATCH")
    if not args.enable_development and not args.dry_run:
        parser.error("DEVELOPMENT_OPT_IN_REQUIRED")
    root = Path(args.state_dir).resolve()
    project = Path(args.project).resolve(strict=True)
    if project == root or project in root.parents:
        parser.error("STATE_MUST_BE_OUTSIDE_PROJECT")
    with receiver.single_instance(args.target):
        journal = executor.Journal(root)
        try:
            while True:
                try:
                    receiver.poll(args.target, str(project), args.dry_run)
                    executor.poll_reviews(args.target, project, args.codex, journal, args.dry_run)
                    poll(args.target, args.codex, journal, args.dry_run)
                except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
                    print("ORCHESTRATOR_TRANSPORT_ERROR", flush=True)
                    if not args.watch:
                        raise SystemExit(1) from None
                if not args.watch:
                    break
                time.sleep(60)
        finally:
            journal.close()


if __name__ == "__main__":
    main()
