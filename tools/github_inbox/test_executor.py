"""Offline contract and crash/retry tests; no real AI, network or broker access."""
import json
from pathlib import Path
import subprocess
import tempfile
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


if __name__ == "__main__":
    unittest.main()
