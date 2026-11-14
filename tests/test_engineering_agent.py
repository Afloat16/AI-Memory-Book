"""Preparation and artificial CLI-event fixtures; no model-quality results."""

from __future__ import annotations

import copy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks import engineering_agent as agent


def specification():
    return {"schema_version": 1, "episode_id": "fixture", "window_id": "w1",
            "project": "project-a", "visible_until": "2026-01-01T00:00:00Z",
            "workspace_files": ["app.py", "tests/test_visible.py"],
            "conditions": [{"id": "no_memory", "memory_policy": "none", "implementation_sha256": None},
                           {"id": "book", "memory_policy": "book", "implementation_sha256": "1" * 64}],
            "model": {"id": "unexecuted-fixture", "cli_version": "fixture-only"},
            "budgets": {"wall_seconds": 60, "model_calls": 2, "tool_calls": 4,
                        "input_tokens": 1000, "output_tokens": 100},
            "tool_policy": {"network": "disabled", "tools": ["read", "edit", "visible-test"]},
            "prompt": "Artificial plumbing fixture, not a measured engineering task."}


class EngineeringPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.snapshot = self.root / "snapshot"
        self.snapshot.mkdir()
        (self.snapshot / "tests").mkdir()
        (self.snapshot / "app.py").write_text("VALUE = 1\n")
        (self.snapshot / "tests/test_visible.py").write_text("# visible fixture\n")
        (self.snapshot / "unlisted-gold.txt").write_text("must not be copied\n")
        (self.snapshot / ".git").mkdir()
        (self.snapshot / ".git/future-version").write_text("not visible\n")
        self.spec = self.root / "spec.json"
        self.spec.write_bytes(agent.json_bytes(specification()))
        self.output = self.root / "prepared"

    def prepare(self):
        return agent.prepare(self.snapshot, self.spec, self.output)

    def test_preparation_copies_only_allowlist_into_independent_workspaces(self):
        with patch.object(agent.subprocess, "run") as command:
            report = self.prepare()
            checked = agent.inspect(self.output)
        command.assert_not_called()
        self.assertEqual(report["actual_model_calls"], 0)
        self.assertEqual(checked["status"], "blocked")
        left = self.output / report["workspaces"]["no_memory"]
        right = self.output / report["workspaces"]["book"]
        self.assertFalse((left / "unlisted-gold.txt").exists())
        self.assertFalse((left / ".git").exists())
        self.assertFalse(os.path.samefile(left / "app.py", right / "app.py"))
        (left / "app.py").write_text("changed\n")
        self.assertEqual((right / "app.py").read_text(), "VALUE = 1\n")
        with self.assertRaisesRegex(ValueError, "workspace changed"):
            agent.inspect(self.output)

    def test_escape_git_history_duplicate_conditions_and_overlap_are_rejected(self):
        for name in ("../unlisted-gold.txt", ".git/future-version", "/absolute", "tests/../app.py",
                     "tests\\file.py", "C:/outside.py", "C:outside.py", "."):
            spec = specification()
            spec["workspace_files"] = [name]
            with self.subTest(name=name), self.assertRaises(ValueError):
                agent.validate_spec(spec)
        spec = specification()
        spec["conditions"].append(copy.deepcopy(spec["conditions"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            agent.validate_spec(spec)
        with self.assertRaisesRegex(ValueError, "nonoverlapping"):
            agent.prepare(self.snapshot, self.spec, self.snapshot / "output")
        self.assertFalse((self.snapshot / "output").exists())

    def test_source_symlink_and_extra_workspace_symlink_are_rejected(self):
        link = self.snapshot / "link.py"
        try:
            link.symlink_to(self.snapshot / "app.py")
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this platform")
        spec = specification()
        spec["workspace_files"] = ["link.py"]
        self.spec.write_bytes(agent.json_bytes(spec))
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.prepare()
        self.spec.write_bytes(agent.json_bytes(specification()))
        report = self.prepare()
        workspace = self.output / report["workspaces"]["book"]
        (workspace / "outside").symlink_to(self.snapshot, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            agent.inspect(self.output)

    def test_existing_preparation_and_changed_evaluator_are_rejected(self):
        self.prepare()
        original = (self.output / "prepared.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual((self.output / "prepared.json").read_bytes(), original)
        with patch.object(agent, "evaluator_hashes", return_value={"changed": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "evaluator changed"):
                agent.inspect(self.output)

    def test_duplicate_json_key_cannot_change_registered_prompt(self):
        self.spec.write_bytes(agent.json_bytes(specification())[:-1] + b',"prompt":"replacement"}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_auth_check_retains_no_command_output_and_does_not_infer_access_from_presence(self):
        with patch.object(agent.shutil, "which", return_value="codex"), patch.object(
                agent.subprocess, "run", return_value=SimpleNamespace(
                    returncode=1, stdout=b"fixture-secret-must-not-be-recorded", stderr=b"Not logged in")) as command:
            status = agent.authentication_status()
        self.assertEqual(status, {"status": "unavailable", "exit_code": 1})
        self.assertEqual(command.call_args.args[0], ["codex", "login", "status"])
        self.assertNotIn("fixture-secret", json.dumps(status))

    def test_run_stays_blocked_even_with_authentication_and_user_supplied_sandbox_claim(self):
        spec = specification()
        spec["tool_policy"]["sandbox_verified"] = True
        self.spec.write_bytes(agent.json_bytes(spec))
        self.prepare()
        with patch.object(agent, "authentication_status", return_value={"status": "available", "exit_code": 0}), patch.object(
                agent.subprocess, "Popen") as launch:
            result = agent.run(self.output)
        launch.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("hidden_test_isolation_not_verified", result["blockers"])
        self.assertEqual(result["actual_model_calls"], 0)
        self.assertFalse(result["quality_evidence"])
        self.assertFalse((self.output / "attempts").exists())

    def test_cli_reports_blocked_separately_from_quality_failure(self):
        self.prepare()
        with patch.object(agent, "authentication_status", return_value={"status": "unavailable", "exit_code": 1}), patch(
                "sys.stdout", new_callable=StringIO) as output:
            exit_code = agent.main(["run", "--prepared", str(self.output)])
        self.assertEqual(exit_code, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "blocked")
        self.assertNotIn("task_score", report)

    def test_capture_intent_precedes_callback_and_never_authenticates_fixture_events(self):
        self.prepare()
        payload = b'{"type":"turn.completed","usage":{"input_tokens":8,"output_tokens":2}}\n'
        attempt = self.output / "attempts/book/one"
        def events():
            intent = json.loads((attempt / "ledger.jsonl").read_text())
            self.assertEqual(intent["kind"], "capture_intent")
            return iter([payload])
        result = agent.capture_cli_events(self.output, "book", "one", events)
        self.assertEqual((attempt / "stdout.jsonl").read_bytes(), payload)
        self.assertEqual(result["status"], "captured_unverified")
        self.assertFalse(result["quality_evidence"])
        self.assertIsNone(result["actual_model_calls"])
        self.assertIsNone(result["complete_model_usage"])
        self.assertEqual(result["reported_usage_events"][0]["reported_counts"]["input_tokens"], 8)
        with self.assertRaises(FileExistsError):
            agent.capture_cli_events(self.output, "book", "one", lambda: self.fail("must not replay"))

    def test_interrupt_keeps_original_bytes_and_never_reinvokes_callback(self):
        self.prepare()
        payload = b'{"type":"turn.started"}\n'
        def events():
            yield payload
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            agent.capture_cli_events(self.output, "book", "interrupted", events)
        attempt = self.output / "attempts/book/interrupted"
        self.assertEqual((attempt / "stdout.jsonl").read_bytes(), payload)
        rows = [json.loads(line) for line in (attempt / "ledger.jsonl").read_bytes().splitlines()]
        self.assertEqual(rows[-1]["kind"], "capture_interrupted")
        with self.assertRaises(FileExistsError):
            agent.capture_cli_events(self.output, "book", "interrupted", lambda: self.fail("must not replay"))
        self.assertFalse((attempt / "capture.json").exists())

    def test_malformed_and_partial_events_keep_raw_bytes_and_unknown_usage(self):
        self.prepare()
        lines = [b'{"type":"turn.completed"}\n', b'{"type":"x","type":"y"}\n', b'{"type":"partial"}']
        result = agent.capture_cli_events(self.output, "book", "bad", lambda: iter(lines))
        self.assertEqual(result["status"], "invalid_events")
        self.assertEqual(result["invalid_events"], 2)
        self.assertEqual(result["reported_usage_events"], [])
        self.assertIsNone(result["complete_model_usage"])
        self.assertEqual((self.output / "attempts/book/bad/stdout.jsonl").read_bytes(), b"".join(lines))


if __name__ == "__main__":
    unittest.main()
