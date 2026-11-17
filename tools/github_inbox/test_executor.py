"""Offline contract and crash/retry tests; no real AI, network or broker access."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import executor


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = executor.Journal(self.temp.name)
        self.addCleanup(self.journal.close)
        self.task = {"version": 2, "target": "AI5", "action": "review",
                     "project": "cherrypulse-inbox", "expected_head": "a" * 40,
                     "instruction": "수신기에서 다음 개발 작업을 검토하라."}
        self.issue = {"number": 24, "state": "open", "title": "[hermes-task] review",
                      "user": {"login": "breadday"}, "body": json.dumps(self.task)}
        self.answer = {"verdict": "READY", "next_step": "VERIFY_LOCAL_RUNTIME",
                       "evidence": [executor.SOURCES[0]], "analysis": "LOCAL_ONLY_TEXT"}

    def execute(self):
        return executor.execute(self.issue, self.task, "project", "codex", self.journal)

    def fake_codex(self, argv, cwd, env, **kwargs):
        self.assertIn("--sandbox", argv)
        self.assertIn("read-only", argv)
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("features.shell_tool=false", argv)
        self.assertIn("features.apps=false", argv)
        self.assertIn("features.multi_agent=false", argv)
        self.assertEqual(argv[-1], "-")
        self.assertNotIn(self.task["instruction"], argv)
        self.assertEqual(kwargs["timeout"], 600)
        self.assertIn(self.task["instruction"], kwargs["payload"])
        (cwd / "answer.json").write_text(json.dumps(self.answer), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "ignored private output", "ignored error")

    def test_valid_review_and_malicious_inputs(self):
        self.assertEqual(executor.parse_review(self.issue, "AI5"), self.task)
        for changes in ({"action": "execute"}, {"project": "kiwoom-trader"},
                        {"expected_head": "HEAD:secret"}, {"instruction": " "},
                        {"instruction": "x" * 4001}, {"version": True},
                        {"command": "powershell"}, {"expected_head": []}):
            with self.subTest(changes=changes):
                issue = dict(self.issue, body=json.dumps(dict(self.task, **changes)))
                self.assertIsNone(executor.parse_review(issue, "AI5"))
        self.assertIsNone(executor.parse_review(self.issue, "ZENBOOK"))
        self.assertIsNone(executor.parse_review(dict(self.issue, state="closed"), "AI5"))
        self.assertIsNone(executor.parse_review(dict(self.issue, pull_request={"url": "x"}), "AI5"))
        self.assertIsNone(executor.parse_review(dict(self.issue, user={"login": "other"}), "AI5"))

    def test_success_and_second_poll_do_not_invoke_twice(self):
        with patch.object(executor, "snapshot", return_value={"public": "data"}), \
                patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.fake_codex) as run:
            first = self.execute()
            second = self.execute()
        self.assertEqual(first, second)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(first["code"], "REVIEW_COMPLETED")
        self.assertTrue(first["llm_called"])
        self.assertNotIn("analysis", first)
        self.assertNotIn("LOCAL_ONLY_TEXT", json.dumps(first))
        self.assertTrue((Path(self.temp.name) / "review-AI5-24.json").exists())

    def test_crash_after_claim_never_reinvokes(self):
        self.journal.claim(self.issue, self.task)
        # A second connection models a newly started process, not in-memory state.
        restart = executor.Journal(self.temp.name)
        try:
            with patch.object(executor, "snapshot") as source:
                report = executor.execute(self.issue, self.task, "project", "codex", restart)
            source.assert_not_called()
            self.assertEqual(report["code"], "INTERRUPTED_NO_RETRY")
        finally:
            restart.close()

    def test_edited_issue_never_reinvokes(self):
        self.journal.claim(self.issue, self.task)
        changed = dict(self.task, instruction="different request")
        with patch.object(executor, "snapshot") as source:
            report = executor.execute(self.issue, changed, "project", "codex", self.journal)
        source.assert_not_called()
        self.assertEqual(report["code"], "TASK_CHANGED_NO_RETRY")

    def test_timeout_is_terminal(self):
        with patch.object(executor, "snapshot", return_value={}), \
                patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=subprocess.TimeoutExpired("codex", 600)) as run:
            first = self.execute()
            self.assertEqual(self.execute(), first)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(first["code"], "TIMEOUT_NO_RETRY")

    def test_missing_login_blocks_before_ai(self):
        with patch.object(executor, "snapshot", return_value={}), \
                patch.object(executor, "preflight", side_effect=ValueError("CHATGPT_LOGIN_REQUIRED")), \
                patch.object(executor, "run_capture") as run:
            result = self.execute()
        run.assert_not_called()
        self.assertFalse(result["llm_called"])
        self.assertEqual(result["code"], "CHATGPT_LOGIN_REQUIRED")

    def test_snapshot_mismatch_blocks_before_ai(self):
        with patch.object(executor.receiver, "project_status", return_value={"head": "b" * 40}), \
                patch.object(executor, "preflight") as check:
            result = self.execute()
        check.assert_not_called()
        self.assertFalse(result["llm_called"])

    def test_snapshot_reads_only_committed_allowlist(self):
        with patch.object(executor.receiver, "project_status", return_value={"head": "a" * 40}), \
                patch.object(executor.receiver, "command", return_value="public source") as command:
            files = executor.snapshot(self.temp.name, "a" * 40)
        self.assertEqual(set(files), set(executor.SOURCES))
        for call in command.call_args_list:
            self.assertEqual(call.args[0][-2], "show")
            self.assertTrue(call.args[0][-1].startswith("a" * 40 + ":"))

    def test_api_and_broker_credentials_not_inherited(self):
        with patch.dict(executor.os.environ, {"PATH": "/bin", "OPENAI_API_KEY": "secret",
                        "CODEX_API_KEY": "secret", "GH_TOKEN": "secret", "KIWOOM_APP_KEY": "secret",
                        "CODEX_MODEL_PROVIDER": "other"}, clear=True):
            self.assertEqual(executor.codex_environment(), {"PATH": "/bin"})

    def test_preflight_requires_exact_chatgpt_mode(self):
        binary = Path(self.temp.name) / "codex.exe"
        binary.touch()
        capabilities = "--ignore-user-config --strict-config --ephemeral --output-schema"
        for message in ("Logged in using an API key", "Logged in using ChatGPT\nsecret", "unknown"):
            with self.subTest(message=message), patch.object(executor, "run_capture", side_effect=[
                subprocess.CompletedProcess([], 0, capabilities, ""),
                subprocess.CompletedProcess([], 0, "", message),
            ]):
                with self.assertRaises(ValueError):
                    executor.preflight(binary, self.temp.name, {})
        with patch.object(executor, "run_capture", side_effect=[
            subprocess.CompletedProcess([], 0, capabilities, ""),
            subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT\n"),
        ]):
            executor.preflight(binary, self.temp.name, {})

    def test_missing_capabilities_fail_closed(self):
        binary = Path(self.temp.name) / "codex.exe"
        binary.touch()
        with patch.object(executor, "run_capture", return_value=subprocess.CompletedProcess([], 0, "old cli", "")):
            with self.assertRaises(ValueError):
                executor.preflight(binary, self.temp.name, {})

    def test_result_rejects_unexpected_public_fields(self):
        for changes in ({"evidence": ["C:/private/secret"]}, {"verdict": "private output"},
                        {"next_step": "run order"}, {"extra": "secret"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                executor.validate_answer(dict(self.answer, **changes))

    def test_failed_post_reuses_saved_result(self):
        # First POST fails after completion; next poll republishes without an AI call.
        with patch.object(executor, "snapshot", return_value={}), \
                patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.fake_codex) as run:
            for fail in (True, False):
                responses = [{"login": "breadday"}, [[self.issue]], [[]],
                             RuntimeError("connection lost") if fail else {"id": 1}]
                with patch.object(executor.receiver, "api", side_effect=responses):
                    if fail:
                        with self.assertRaises(RuntimeError):
                            executor.poll_reviews("AI5", "project", "codex", self.journal)
                    else:
                        self.assertEqual(executor.poll_reviews("AI5", "project", "codex", self.journal), 1)
        self.assertEqual(run.call_count, 1)

    def test_dry_run_does_not_claim_or_call_ai(self):
        with patch.object(executor.receiver, "api", side_effect=[
                {"login": "breadday"}, [[self.issue]], [[]]]) as api, \
                patch.object(executor, "execute") as execute:
            self.assertEqual(executor.poll_reviews("AI5", "project", "codex", self.journal, True), 1)
        execute.assert_not_called()
        self.assertEqual(api.call_count, 3)
        self.assertEqual(self.journal.db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)

    def test_wrong_login_never_reads_queue(self):
        with patch.object(executor.receiver, "api", return_value={"login": "other"}) as api:
            with self.assertRaises(ValueError):
                executor.poll_reviews("AI5", "project", "codex", self.journal)
        self.assertEqual(api.call_count, 1)

    def test_completed_comment_prevents_run_even_without_journal(self):
        tag = executor.tag_for(self.issue, self.task)
        with patch.object(executor.receiver, "api", side_effect=[{"login": "breadday"}, [[self.issue]],
                [[{"user": {"login": "breadday"}, "body": tag}]]]), \
                patch.object(executor, "execute") as execute:
            self.assertEqual(executor.poll_reviews("AI5", "project", "codex", self.journal), 0)
        execute.assert_not_called()


class ProcessRecoveryTests(unittest.TestCase):
    """Real processes/SQLite/OS locks; only AI and GitHub are local doubles."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def start(self, mode):
        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()),
             "--process-fixture", str(self.root), mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", shell=False,
        )

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

        self.addCleanup(cleanup)
        return process

    def run_child(self, mode, expected_code=0):
        process = self.start(mode)
        stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, expected_code, stdout + stderr)

    def wait_ready(self, process, mode):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if (self.root / (mode + ".ready")).exists():
                return
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=5)
                self.fail("Fixture exited before ready: " + stdout + stderr)
            time.sleep(0.02)
        self.fail("Fixture readiness timeout")

    def lines(self, filename):
        path = self.root / filename
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def report(self):
        body = json.loads(self.lines("posts.jsonl")[-1])["body"]
        return json.loads(body.split("```json\n", 1)[1].split("\n```", 1)[0])

    def test_killed_after_claim_restarts_without_ai(self):
        child = self.start("hold-after-claim")
        self.wait_ready(child, "hold-after-claim")
        child.kill()  # SIGKILL on POSIX, TerminateProcess on Windows; no DB close.
        child.communicate(timeout=10)
        self.assertNotEqual(child.returncode, 0)
        self.run_child("normal")
        self.assertEqual(self.lines("ai-calls.jsonl"), [])
        self.assertEqual(self.report()["code"], "INTERRUPTED_NO_RETRY")
        with closing(sqlite3.connect(self.root / "state" / "review-journal.sqlite3")) as database:
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(database.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_restart_after_failed_post_reuses_durable_result(self):
        self.run_child("fail-post", expected_code=2)
        with closing(sqlite3.connect(self.root / "state" / "review-journal.sqlite3")) as database:
            saved = json.loads(database.execute("SELECT report FROM jobs").fetchone()[0])
        self.assertEqual(saved["code"], "REVIEW_COMPLETED")
        self.run_child("normal")
        self.run_child("normal")
        self.assertEqual(len(self.lines("ai-calls.jsonl")), 1)
        self.assertEqual(len(self.lines("posts.jsonl")), 2)
        self.assertEqual(self.report(), saved)

    def test_killed_after_ai_invocation_does_not_invoke_again(self):
        child = self.start("hold-after-ai")
        self.wait_ready(child, "hold-after-ai")
        child.kill()
        child.communicate(timeout=10)
        self.run_child("normal")
        self.assertEqual(len(self.lines("ai-calls.jsonl")), 1)
        self.assertEqual(self.report()["code"], "INTERRUPTED_NO_RETRY")

    def test_killed_before_post_reuses_saved_result(self):
        child = self.start("hold-before-post")
        self.wait_ready(child, "hold-before-post")
        child.kill()
        child.communicate(timeout=10)
        self.run_child("normal")
        self.assertEqual(len(self.lines("ai-calls.jsonl")), 1)
        self.assertEqual(len(self.lines("posts.jsonl")), 1)
        self.assertEqual(self.report()["code"], "REVIEW_COMPLETED")

    def test_accepted_post_with_lost_response_is_found_on_restart(self):
        self.run_child("lose-post-response", expected_code=2)
        self.run_child("normal")
        self.assertEqual(len(self.lines("ai-calls.jsonl")), 1)
        self.assertEqual(len(self.lines("posts.jsonl")), 1)
        self.assertEqual(self.report()["code"], "REVIEW_COMPLETED")

    def test_changed_body_after_restart_never_calls_ai_again(self):
        self.run_child("normal")
        self.run_child("changed-body")
        self.run_child("changed-body")
        self.assertEqual(len(self.lines("ai-calls.jsonl")), 1)
        self.assertEqual(len(self.lines("posts.jsonl")), 2)
        self.assertEqual(self.report()["code"], "TASK_CHANGED_NO_RETRY")

    def test_process_lock_rejects_second_owner_and_releases_after_kill(self):
        child = self.start("hold-lock")
        self.wait_ready(child, "hold-lock")
        self.run_child("probe-lock", expected_code=3)
        child.kill()
        child.communicate(timeout=10)
        self.run_child("probe-lock")


def process_fixture(directory, mode):
    """Child entrypoint used only by tests; never invokes a real CLI or network."""
    root = Path(directory)

    def append(filename, value):
        with (root / filename).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def hold_ready():
        append(mode + ".ready", "ready")
        sys.stdin.readline()  # Parent keeps stdin open until forcibly killing this child.
        raise RuntimeError("Fixture must be killed by parent")

    if mode in ("hold-lock", "probe-lock"):
        # Isolate the real OS file lock from the installed AI5 receiver's lock.
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "locks")}):
            try:
                with executor.receiver.single_instance("AI5"):
                    if mode == "hold-lock":
                        hold_ready()
            except OSError:
                return 3
        return 0

    task = {"version": 2, "target": "AI5", "action": "review",
            "project": "cherrypulse-inbox", "expected_head": "a" * 40,
            "instruction": "changed" if mode == "changed-body" else "review public fixture"}
    issue = {"number": 100, "state": "open", "title": "[hermes-task] process fixture",
             "user": {"login": "breadday"}, "body": json.dumps(task)}

    def fake_ai(argv, cwd, env, **kwargs):
        append("ai-calls.jsonl", {"invoked": True})
        if mode == "hold-after-ai":
            hold_ready()
        answer = {"verdict": "READY", "next_step": "VERIFY_LOCAL_RUNTIME",
                  "evidence": [executor.SOURCES[0]], "analysis": "SYNTHETIC_LOCAL_ANALYSIS"}
        (cwd / "answer.json").write_text(json.dumps(answer), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_api(path, payload=None, paginate=False):
        if path == "user":
            return {"login": "breadday"}
        if "/comments" not in path:
            return [[issue]]
        if payload is None:
            accepted = root / "accepted.jsonl"
            comments = [json.loads(line) for line in accepted.read_text(encoding="utf-8").splitlines()] if accepted.exists() else []
            return [comments]
        if mode == "hold-before-post":
            hold_ready()
        append("posts.jsonl", payload)
        if mode != "fail-post":
            append("accepted.jsonl", {"user": {"login": "breadday"}, "body": payload["body"]})
        if mode in ("fail-post", "lose-post-response"):
            raise RuntimeError("SIMULATED_TRANSPORT_FAILURE")
        return {"id": 1}

    journal = executor.Journal(root / "state")
    original_claim = journal.claim

    def claim(issue, task):
        result = original_claim(issue, task)  # Real SQLite commit completed before readiness.
        if mode == "hold-after-claim" and result is None:
            hold_ready()
        return result

    try:
        with patch.object(journal, "claim", side_effect=claim), \
                patch.object(executor, "snapshot", return_value={"public": "fixture"}), \
                patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=fake_ai), \
                patch.object(executor.receiver, "api", side_effect=fake_api):
            executor.poll_reviews("AI5", "unused", "unused", journal)
    except RuntimeError:
        return 2
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--process-fixture":
        raise SystemExit(process_fixture(sys.argv[2], sys.argv[3]))
    unittest.main()
