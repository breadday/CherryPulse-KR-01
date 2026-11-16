"""Offline transport contract tests; no subprocesses or network calls."""
import unittest
from unittest.mock import patch

import receiver


class InboxTests(unittest.TestCase):
    def issue(self, body='{"version":1,"target":"AI5","action":"ping"}'):
        return {"number": 7, "state": "open", "title": "[hermes-task] test",
                "user": {"login": "breadday"}, "body": body}

    def test_valid_ping(self):
        self.assertEqual(receiver.parse_task(self.issue(), "AI5")["action"], "ping")

    def test_wrong_machine_ignored(self):
        self.assertIsNone(receiver.parse_task(self.issue(), "ZENBOOK"))

    def test_other_author_ignored(self):
        issue = self.issue()
        issue["user"]["login"] = "someone-else"
        self.assertIsNone(receiver.parse_task(issue, "AI5"))

    def test_arbitrary_command_ignored(self):
        for body in (
            '{"version":1,"target":"AI5","action":"execute"}',
            '{"version":1,"target":"AI5","action":"ping","command":"delete"}',
            "run arbitrary command",
            "[]",
            '{"version":true,"target":"AI5","action":"ping"}',
        ):
            with self.subTest(body=body):
                self.assertIsNone(receiver.parse_task(self.issue(body), "AI5"))

    def test_closed_and_pull_request_ignored(self):
        issue = self.issue()
        issue["state"] = "closed"
        self.assertIsNone(receiver.parse_task(issue, "AI5"))
        issue = self.issue()
        issue["pull_request"] = {"url": "https://github.com/example"}
        self.assertIsNone(receiver.parse_task(issue, "AI5"))

    def test_duplicate_comment_requires_owner(self):
        tag = "<!-- test -->"
        self.assertFalse(receiver.already_reported(
            [{"user": {"login": "other"}, "body": tag}], tag))
        self.assertTrue(receiver.already_reported(
            [{"user": {"login": "breadday"}, "body": tag}], tag))

    def test_ping_never_reads_project_and_reports_once(self):
        issue = self.issue()
        with patch.object(receiver, "api", side_effect=[
            {"login": "breadday"}, [[issue]], [[]], {"id": 1},
        ]) as api, patch.object(receiver, "project_status") as status:
            self.assertEqual(receiver.poll("AI5"), 1)
            status.assert_not_called()
            self.assertIn("llm_called", api.call_args.args[1]["body"])

    def test_existing_report_is_skipped(self):
        issue = self.issue()
        tag = receiver.marker(issue, receiver.parse_task(issue, "AI5"))
        with patch.object(receiver, "api", side_effect=[
            {"login": "breadday"}, [[issue]],
            [[{"user": {"login": "breadday"}, "body": tag}]],
        ]) as api:
            self.assertEqual(receiver.poll("AI5"), 0)
            self.assertEqual(api.call_count, 3)

    def test_dry_run_never_posts(self):
        with patch.object(receiver, "api", side_effect=[
            {"login": "breadday"}, [[self.issue()]], [[]],
        ]) as api:
            self.assertEqual(receiver.poll("AI5", dry_run=True), 1)
            self.assertEqual(api.call_count, 3)

    def test_status_not_configured(self):
        self.assertEqual(receiver.project_status(None), {"status": "NOT_CONFIGURED"})


if __name__ == "__main__":
    unittest.main()
