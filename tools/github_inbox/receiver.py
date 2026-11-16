"""GitHub inbox transport probe. No LLM, shell tasks, broker calls or project writes."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

REPO = "breadday/CherryPulse-KR-01"
OWNER = "breadday"
PREFIX = "[hermes-task]"
TARGETS = {"AI5": "BREADDAY_AI5", "ZENBOOK": "ZENBOOK"}


def command(args, payload=None):
    env = os.environ.copy()
    env.update(GH_PROMPT_DISABLED="1", GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        args, input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=45, env=env,
        shell=False,
    )
    if result.returncode:
        # Do not copy stderr, credentials or arbitrary command output into issues.
        raise RuntimeError("command failed: " + args[0])
    return result.stdout


def api(path, payload=None, paginate=False):
    args = ["gh", "api", "--hostname", "github.com", path]
    if paginate:
        args += ["--paginate", "--slurp"]
    if payload is not None:
        args += ["--method", "POST", "--input", "-"]
    return json.loads(command(args, None if payload is None else json.dumps(payload)))


def parse_task(issue, target):
    if issue.get("pull_request") or issue.get("state") != "open":
        return None
    if issue.get("user", {}).get("login") != OWNER:
        return None
    if not issue.get("title", "").startswith(PREFIX):
        return None
    try:
        task = json.loads(issue.get("body") or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(task, dict):
        return None
    if set(task) != {"version", "target", "action"}:
        return None
    if type(task["version"]) is not int or task["version"] != 1:
        return None
    if task["target"] != target or task["action"] not in ("ping", "status"):
        return None
    return task


def marker(issue, task):
    digest = hashlib.sha256(
        json.dumps(task, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return "<!-- hermes-inbox-v1:" + str(issue["number"]) + ":" + digest + " -->"


def already_reported(comments, tag):
    return any(
        c.get("user", {}).get("login") == OWNER and tag in c.get("body", "")
        for c in comments
    )


def project_status(project):
    if project is None:
        return {"status": "NOT_CONFIGURED"}
    root = Path(project).resolve(strict=True)
    git = ["git", "--no-optional-locks", "-C", str(root)]
    top = Path(command(git + ["rev-parse", "--show-toplevel"]).strip()).resolve()
    if top != root:
        raise ValueError("project must be repository root")
    remote = command(git + ["remote", "get-url", "origin"]).strip()
    # Only this public repository may be reported. Reject embedded credentials.
    if remote not in (
        "https://github.com/" + REPO + ".git",
        "https://github.com/" + REPO,
        "git@github.com:" + REPO + ".git",
    ):
        raise ValueError("project origin not allowed")
    head = command(git + ["rev-parse", "HEAD"]).strip()
    raw = command(git + ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    records = raw.split("\0")
    count = 0
    index = 0
    while index < len(records):
        record = records[index]
        if record:
            count += 1
            if record[0] in "RC" or record[1] in "RC":
                index += 1
        index += 1
    # Do not publish local paths, branch names, filenames, diffs or private repo data.
    return {"status": "READ_ONLY", "head": head, "changed_entries": count}


def poll(target, project=None, dry_run=False):
    login = api("user")["login"]
    if login != OWNER:
        raise ValueError("GitHub login must match queue owner")
    pages = api("repos/" + REPO + "/issues?state=open&per_page=100", paginate=True)
    handled = 0
    for issue in (item for page in pages for item in page):
        task = parse_task(issue, target)
        if task is None:
            continue
        tag = marker(issue, task)
        endpoint = "repos/" + REPO + "/issues/" + str(issue["number"]) + "/comments"
        comments = [c for page in api(endpoint + "?per_page=100", paginate=True) for c in page]
        if already_reported(comments, tag):
            continue
        report = {"target": target, "action": task["action"], "transport": "OK",
                  "llm_called": False, "orders_called": False}
        if task["action"] == "status":
            try:
                report["project"] = project_status(project)
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
                report["project"] = {"status": "CHECK_FAILED"}
        if dry_run:
            print("DRY_RUN issue #" + str(issue["number"]) + " " + task["action"])
        else:
            api(endpoint, {"body": tag + "\n\nTransport probe result:\n\n"
                           + "```json\n" + json.dumps(report, indent=2)
                           + "\n```"})
            print("REPORTED issue #" + str(issue["number"]))
        handled += 1
    return handled


@contextlib.contextmanager
def single_instance(target):
    directory = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "HermesGitHubInbox"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (target + ".lock")).open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--project", help="Optional local root of CherryPulse clone")
    parser.add_argument("--watch", action="store_true", help="Poll every 60 seconds")
    parser.add_argument("--dry-run", action="store_true", help="Read queue without posting")
    args = parser.parse_args()
    if platform.node().upper() != TARGETS[args.target]:
        parser.error("PC does not match target; no queue access performed")
    with single_instance(args.target):
        while True:
            try:
                poll(args.target, args.project, args.dry_run)
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
                print("INBOX_ERROR " + type(error).__name__, flush=True)
                if not args.watch:
                    raise SystemExit(1) from None
            if not args.watch:
                break
            time.sleep(60)


if __name__ == "__main__":
    main()
