"""Offline auto-development tests: real Git/apply/test processes, AI/GitHub doubles."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import autodev
import executor

MODULE = '''LABELS = {"WAITING": "대기 중", "RUNNING": "개발 중", "TEST_FAILED": "검증 실패", "PR_CREATED": "PR 작성 완료", "UNKNOWN": "확인 필요"}
def describe(code: str) -> str:
    if not isinstance(code, str):
        raise TypeError("code must be a string")
    return LABELS.get(code, LABELS["UNKNOWN"])
'''
TESTS = '''import unittest
from status_text import describe
class StatusTests(unittest.TestCase):
    def test_label(self):
        self.assertEqual(describe("RUNNING"), "개발 중")
    def test_unknown(self):
        self.assertEqual(describe("other"), "확인 필요")
    def test_invalid(self):
        with self.assertRaises(TypeError):
            describe(None)
'''


class AutodevTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = executor.Journal(self.root / "state")
        self.addCleanup(self.journal.close)
        self.task = {"version": 3, "target": "AI5", "action": "develop", "project": "inbox-lab",
                     "expected_head": "a" * 40, "instruction": "상태 안내 함수를 구현해줘."}
        self.issue = {"number": 1000, "state": "open", "title": "[hermes-task] development",
                      "user": {"login": "breadday"}, "body": json.dumps(self.task)}
        self.changes = dict(zip(autodev.FILES, (MODULE, TESTS, "# 상태 안내\n")))

    def workspace(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        subprocess.run(["git", "init", "--quiet", str(workspace)], check=True, capture_output=True,
                       env=autodev.git_env())
        return workspace

    def complete_report(self):
        return autodev.report(self.task, "PR_CREATED", "PUBLISHED", True,
                              pull_request_url="https://github.com/breadday/CherryPulse-KR-01/pull/100")

    def test_task_contract_rejects_commands_and_other_projects(self):
        self.assertEqual(autodev.parse_task(self.issue, "AI5"), self.task)
        for changes in ({"target": "ZENBOOK"}, {"project": "kiwoom-trader"}, {"action": "execute"},
                        {"version": True}, {"expected_head": "main"}, {"instruction": ""},
                        {"command": "powershell"}):
            issue = dict(self.issue, body=json.dumps(dict(self.task, **changes)))
            self.assertIsNone(autodev.parse_task(issue, "AI5"))
        self.assertIsNone(autodev.parse_task(dict(self.issue, user={"login": "other"}), "AI5"))

    def test_patch_validates_scope_and_contents(self):
        value = {"files": [{"path": p, "content": c} for p, c in self.changes.items()]}
        self.assertEqual(autodev.validate_patch(value), self.changes)
        for path in ("../private.py", "execution/virtual.py", ".github/workflows/run.yml"):
            changed = {"files": [dict(item) for item in value["files"]]}
            changed["files"][0]["path"] = path
            with self.assertRaises(ValueError):
                autodev.validate_patch(changed)
        with self.assertRaises(ValueError):
            autodev.validate_patch({"files": value["files"][:2]})

    def test_pure_function_contract_rejects_dynamic_and_external_access(self):
        for source in ("import os", "open('secret')", "eval('1')", "getattr({}, 'x')",
                       "x = __builtins__", "x = ().__class__", "import subprocess",
                       "while True: pass", "@str\ndef describe(x): return x"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                autodev.validate_python(autodev.FILES[0], source)

    def test_real_apply_tests_and_report_pipeline(self):
        workspace = self.workspace()
        with patch.object(autodev, "prepare", return_value=workspace), \
                patch.object(autodev, "generate", return_value=self.changes) as generate, \
                patch.object(autodev, "publish", return_value=self.complete_report()) as publish:
            result = autodev.develop(self.issue, self.task, "fake", self.journal)
            self.assertEqual(autodev.develop(self.issue, self.task, "fake", self.journal), result)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(publish.call_args.args[0]["counts"], [3, 3])
        self.assertEqual(result["code"], "PR_CREATED")
        self.assertTrue((self.journal.root / "handoff-AI5-1000.json").exists())
        self.assertEqual((workspace / autodev.FILES[0]).read_text(encoding="utf-8"), MODULE)

    def test_fixed_acceptance_catches_a_false_positive_model_test(self):
        workspace = self.workspace()
        changes = dict(self.changes)
        changes[autodev.FILES[0]] = 'def describe(code):\n    return "wrong"\n'
        changes[autodev.FILES[1]] = 'import unittest\nclass Tests(unittest.TestCase):\n    def test_noop(self):\n        self.assertEqual(1, 1)\n'
        with patch.object(autodev, "prepare", return_value=workspace), \
                patch.object(autodev, "generate", return_value=changes), \
                patch.object(autodev, "publish") as publish:
            result = autodev.develop(self.issue, self.task, "fake", self.journal)
        publish.assert_not_called()
        self.assertEqual(result["code"], "TESTS_FAILED")
        self.assertEqual(result["stage"], "TEST")
        self.assertTrue((workspace / autodev.FILES[0]).exists())

    def test_interrupted_claim_does_not_generate_again(self):
        self.journal.claim(self.issue, self.task)
        with patch.object(autodev, "prepare") as prepare:
            result = autodev.develop(self.issue, self.task, "fake", self.journal)
        prepare.assert_not_called()
        self.assertEqual(result["code"], "INTERRUPTED_NO_RETRY")

    def test_changed_issue_does_not_reuse_old_work(self):
        self.journal.claim(self.issue, self.task)
        with patch.object(autodev, "prepare") as prepare:
            result = autodev.develop(self.issue, dict(self.task, instruction="changed"), "fake", self.journal)
        prepare.assert_not_called()
        self.assertEqual(result["code"], "TASK_CHANGED_NO_RETRY")

    def test_publish_transport_retry_uses_checkpoint_without_ai(self):
        workspace = self.workspace()
        with patch.object(autodev, "prepare", return_value=workspace), \
                patch.object(autodev, "generate", return_value=self.changes) as generate, \
                patch.object(autodev, "publish", side_effect=[RuntimeError("lost"), self.complete_report()]):
            first = autodev.develop(self.issue, self.task, "fake", self.journal)
            restart = executor.Journal(self.journal.root)
            try:
                second = autodev.develop(self.issue, self.task, "fake", restart)
            finally:
                restart.close()
        self.assertEqual(first["code"], "PUBLISH_PENDING")
        self.assertEqual(second["code"], "PR_CREATED")
        self.assertEqual(generate.call_count, 1)

    def test_existing_workspace_is_never_overwritten(self):
        location = self.journal.root / "workspaces/AI5-1000"
        location.mkdir(parents=True)
        (location / "keep").write_text("user data", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "WORKSPACE_EXISTS"):
            autodev.prepare(self.task, self.issue, self.journal.root)
        self.assertEqual((location / "keep").read_text(encoding="utf-8"), "user data")

    def test_base_commit_mismatch_blocks_generation(self):
        with patch.object(autodev, "checked_run", side_effect=["", "b" * 40]):
            with self.assertRaisesRegex(ValueError, "BASE_MISMATCH"):
                autodev.prepare(self.task, self.issue, self.journal.root)

    def test_dry_run_never_claims_or_calls_model(self):
        with patch.object(autodev.receiver, "api", side_effect=[{"login": "breadday"}, [[self.issue]], [[]]]), \
                patch.object(autodev, "develop") as develop:
            self.assertEqual(autodev.poll("AI5", "fake", self.journal, True), 1)
        develop.assert_not_called()

    def test_deterministic_commit_and_existing_pr_are_reused(self):
        calls = []
        branches = {}
        prs = []

        def fake_api(path, payload=None):
            calls.append((path, payload))
            if path.startswith("git/commits/"):
                return {"tree": {"sha": "base-tree"}}
            if path == "git/trees":
                return {"sha": "new-tree"}
            if path == "git/commits":
                return {"sha": hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
            if path.startswith("git/ref/"):
                if not branches:
                    raise RuntimeError("missing")
                return {"object": {"sha": branches["sha"]}}
            if path == "git/refs":
                branches["sha"] = payload["sha"]
                return {"object": {"sha": branches["sha"]}}
            if path.startswith("pulls?"):
                return prs
            if path == "pulls":
                prs.append({"number": 100})
                return prs[0]
            raise AssertionError(path)

        ready = {"changes": self.changes, "counts": [3, 3], "date": "2026-11-17T00:00:00+00:00"}
        with patch.object(autodev, "api", side_effect=fake_api):
            first = autodev.publish(ready, self.task, self.issue)
            second = autodev.publish(ready, self.task, self.issue)
        self.assertEqual(first, second)
        self.assertEqual(sum(path == "pulls" for path, _ in calls), 1)
        self.assertEqual(sum(path == "git/refs" for path, _ in calls), 1)
        self.assertEqual(first["tests_passed"], [3, 3])

    def test_branch_conflict_is_never_force_updated(self):
        with patch.object(autodev, "api", side_effect=[{"tree": {"sha": "tree"}},
                {"sha": "newtree"}, {"sha": "a" * 40}, {"object": {"sha": "b" * 40}}]) as api:
            with self.assertRaisesRegex(ValueError, "BRANCH_CONFLICT"):
                autodev.publish({"changes": self.changes, "counts": [3, 3], "date": "date"}, self.task, self.issue)
        self.assertEqual(api.call_count, 4)

    def test_missing_auth_reports_no_model_invocation(self):
        workspace = self.workspace()
        with patch.object(autodev, "prepare", return_value=workspace), \
                patch.object(autodev, "generate", side_effect=ValueError("CHATGPT_LOGIN_REQUIRED")):
            result = autodev.develop(self.issue, self.task, "fake", self.journal)
        self.assertEqual(result["code"], "CHATGPT_LOGIN_REQUIRED")
        self.assertFalse(result["llm_called"])

    def test_final_comment_prevents_reexecution(self):
        tag = f"<!-- hermes-dev-v3:1000:{executor.digest(self.task)[:16]}:done -->"
        with patch.object(autodev.receiver, "api", side_effect=[{"login": "breadday"}, [[self.issue]],
                [[{"user": {"login": "breadday"}, "body": tag}]]]), \
                patch.object(autodev, "develop") as develop:
            self.assertEqual(autodev.poll("AI5", "fake", self.journal), 0)
        develop.assert_not_called()

    def test_pending_comment_does_not_block_saved_publication_retry(self):
        pending = autodev.report(self.task, "PUBLISH_PENDING", "PUBLISH", True)
        with patch.object(autodev.receiver, "api", side_effect=[{"login": "breadday"}, [[self.issue]], [[]], {}]) as api, \
                patch.object(autodev, "develop", return_value=pending):
            self.assertEqual(autodev.poll("AI5", "fake", self.journal), 1)
            body = api.call_args.args[1]["body"]
            self.assertIn(":pending -->", body)
            self.assertNotIn(":done -->", body)
        with patch.object(autodev.receiver, "api", side_effect=[{"login": "breadday"}, [[self.issue]],
                [[{"user": {"login": "breadday"}, "body": body}]], {}]) as api, \
                patch.object(autodev, "develop", return_value=self.complete_report()) as develop:
            self.assertEqual(autodev.poll("AI5", "fake", self.journal), 1)
            self.assertIn(":done -->", api.call_args.args[1]["body"])
        self.assertEqual(develop.call_count, 1)

    def capture_generation(self, text):
        def capture(argv, cwd, env, **kwargs):
            if text is not None:
                (cwd / "answer.json").write_bytes(text.encode("utf-8"))
            return subprocess.CompletedProcess(argv, 0, "", "")
        return capture

    def test_python_rejection_reason_and_location_are_specific(self):
        for source, reason in (("import os", "IMPORT_CONTRACT"),
                               ("x = ().__class__", "FORBIDDEN_ATTRIBUTE"),
                               ("open('private')", "CALL_CONTRACT"),
                               ("x = __builtins__", "FORBIDDEN_NAME"),
                               ("def broken(:", "PYTHON_SYNTAX")):
            with self.subTest(source=source):
                with self.assertRaises(autodev.PatchRejected) as caught:
                    autodev.validate_python(autodev.FILES[0], source)
                self.assertEqual(caught.exception.fields,
                                 {"rejection_reason": reason, "file_index": 0, "line": 1})
                self.assertEqual(str(caught.exception), "PATCH_REJECTED")

    def test_response_shape_and_path_have_distinct_reasons(self):
        for value, reason in (({}, "INVALID_RESPONSE_SHAPE"), ({"files": []}, "FILE_COUNT"),
                              ({"files": [{"path": "secret", "content": "x"}] * 3}, "PATH_NOT_ALLOWED")):
            with self.subTest(reason=reason), self.assertRaises(autodev.PatchRejected) as caught:
                autodev.validate_patch(value)
            self.assertEqual(caught.exception.fields["rejection_reason"], reason)

    def test_rejected_generation_is_preserved_and_reported_without_source(self):
        workspace = self.workspace()
        changes = dict(self.changes)
        changes[autodev.FILES[0]] = "import os  # PRIVATE_GENERATION_CONTENT\n"
        raw = json.dumps({"files": [{"path": p, "content": c} for p, c in changes.items()]})
        with patch.object(autodev, "prepare", return_value=workspace), \
                patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.capture_generation(raw)):
            result = autodev.develop(self.issue, self.task, "fake", self.journal)
        self.assertEqual(result["code"], "PATCH_REJECTED")
        self.assertEqual(result["rejection_reason"], "IMPORT_CONTRACT")
        self.assertEqual(result["stage"], "GENERATE")
        self.assertNotIn("PRIVATE_GENERATION_CONTENT", json.dumps(result))
        directory = self.journal.root / "generation-diagnostics"
        self.assertEqual((directory / "workspace.response.json").read_text(encoding="utf-8"), raw)
        metadata = json.loads((directory / "workspace.diagnostic.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["response_sha256"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(metadata["rejection_reason"], "IMPORT_CONTRACT")
        self.assertFalse((workspace / autodev.FILES[0]).exists())

    def test_invalid_json_is_preserved_with_reason(self):
        workspace = self.workspace()
        with patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.capture_generation("not json")):
            with self.assertRaises(autodev.PatchRejected) as caught:
                autodev.generate(self.task, workspace, "fake", self.journal.root)
        self.assertEqual(caught.exception.fields["rejection_reason"], "INVALID_JSON")
        self.assertEqual((self.journal.root / "generation-diagnostics/workspace.response.json").read_text(), "not json")

    def test_missing_response_is_diagnosed(self):
        workspace = self.workspace()
        with patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.capture_generation(None)):
            with self.assertRaises(autodev.PatchRejected) as caught:
                autodev.generate(self.task, workspace, "fake", self.journal.root)
        self.assertEqual(caught.exception.fields["rejection_reason"], "RESPONSE_MISSING")
        self.assertTrue((self.journal.root / "generation-diagnostics/workspace.diagnostic.json").exists())

    def test_oversized_response_has_metadata_without_unbounded_copy(self):
        workspace = self.workspace()
        with patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.capture_generation("x" * 200001)):
            with self.assertRaises(autodev.PatchRejected) as caught:
                autodev.generate(self.task, workspace, "fake", self.journal.root)
        self.assertEqual(caught.exception.fields["rejection_reason"], "RESPONSE_TOO_LARGE")
        self.assertFalse((self.journal.root / "generation-diagnostics/workspace.response.json").exists())

    def test_accepted_generation_records_hash_and_matches_validator(self):
        workspace = self.workspace()
        raw = json.dumps({"files": [{"path": p, "content": c} for p, c in self.changes.items()]})
        with patch.object(executor, "preflight"), \
                patch.object(executor, "run_capture", side_effect=self.capture_generation(raw)):
            changes = autodev.generate(self.task, workspace, "fake", self.journal.root)
        self.assertEqual(changes, self.changes)
        metadata = json.loads((self.journal.root / "generation-diagnostics/workspace.diagnostic.json").read_text())
        self.assertEqual(metadata["code"], "PATCH_ACCEPTED")
        self.assertEqual(metadata["task_hash"], executor.digest(self.task))


if __name__ == "__main__":
    unittest.main()
