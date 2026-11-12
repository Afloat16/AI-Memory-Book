"""Hosted cancellation preserves audit records without replay or index leakage."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import run_hosted_validation as hosted


class HostedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "checkout"
        self.root.mkdir()
        self.old_cwd = Path.cwd()
        self.stage = "answers-locomo"
        self.report = "benchmarks/results/frozen.json"
        self.patches = [
            patch.object(hosted, "ROOT", self.root),
            patch.object(hosted, "choices", return_value=[self.stage]),
            patch.object(hosted, "public_paths", return_value=[self.report]),
            patch.object(hosted, "git", return_value="a" * 40),
            patch.object(hosted, "environment", return_value={"packages": []}),
            patch.dict(os.environ, {"GITHUB_ACTIONS": "false",
                                    "MEMORY_VALIDATION_DEADLINE_UNIX": "",
                                    "GITHUB_RUN_ID": "1234", "GITHUB_RUN_ATTEMPT": "2",
                                    "GITHUB_REPOSITORY": "example/fixture"}),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.restore)

    def restore(self):
        os.chdir(self.old_cwd)
        hosted._DEADLINE, hosted._LOCK_FD = None, None
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def marker(self):
        return json.loads(hosted.marker_path(self.stage).read_bytes())

    def test_running_intent_precedes_prepare_and_keyboard_interrupt_is_preserved(self):
        def prepare(_stage):
            self.assertEqual(self.marker()["status"], "running")
            raise KeyboardInterrupt("PRIVATE_SOURCE_AND_SECRET")
        with patch.object(hosted, "prepare", side_effect=prepare):
            code = hosted.main(["--stage", self.stage])
        self.assertEqual(code, 130)
        self.assertEqual(self.marker()["status"], "interrupted")
        self.assertEqual(self.marker()["interruption"], "KeyboardInterrupt")
        self.assertNotIn("PRIVATE_SOURCE_AND_SECRET", hosted.marker_path(self.stage).read_text())
        reports = hosted.diagnostic_paths(self.stage)
        self.assertEqual(len(reports), 1)
        diagnostic = json.loads(reports[0].read_bytes())
        self.assertEqual(diagnostic["status"], "partial_diagnostic_not_completion")
        self.assertFalse(diagnostic["sufficient_for_resume"])
        self.assertEqual(diagnostic["model_calls_made_by_exporter"], 0)

    @unittest.skipUnless(os.name == "posix", "POSIX controlled SIGTERM")
    def test_sigterm_records_interrupted_and_restores_signal_handlers(self):
        before = signal.getsignal(signal.SIGTERM)
        with patch.object(hosted, "prepare", side_effect=lambda _: os.kill(os.getpid(), signal.SIGTERM)):
            code = hosted.main(["--stage", self.stage])
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertEqual(self.marker()["status"], "interrupted")
        self.assertEqual(self.marker()["interruption"], "signal_SIGTERM")
        self.assertIs(signal.getsignal(signal.SIGTERM), before)

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX in-process execution timer")
    def test_deadline_covers_in_process_preparation_and_keeps_original_phase_contract(self):
        with patch.object(hosted, "prepare", side_effect=lambda _: time.sleep(.2)):
            code = hosted.main(["--stage", self.stage, "--wall-time-seconds", ".03"])
        self.assertEqual(code, 124)
        marker = self.marker()
        self.assertEqual(marker["status"], "interrupted")
        self.assertEqual(marker["interruption"], "execution_deadline")
        self.assertEqual(marker["execution_deadline"]["registered_answer_generate_timeout_seconds"], 28800)

    def test_expired_command_deadline_never_starts_a_child(self):
        hosted._DEADLINE = time.monotonic() - 1
        with patch.object(hosted.subprocess, "Popen") as child:
            with self.assertRaises(hosted.ValidationInterrupted) as raised:
                hosted.run(["would-call-model"])
        self.assertEqual(raised.exception.reason, "execution_deadline")
        child.assert_not_called()
        with patch.dict(os.environ, {"MEMORY_VALIDATION_DEADLINE_UNIX": "nan"}):
            with self.assertRaises(ValueError):
                hosted.execution_budget(None)

    def test_always_cleanup_is_idempotent_and_never_executes_models(self):
        hosted.atomic(hosted.marker_path(self.stage), {
            "schema_version": 2, "stage": self.stage, "status": "running",
            "error_message": "PRIVATE_ERROR", "question": "PRIVATE_QUESTION"})
        with patch.object(hosted, "prepare") as prepare, patch.object(hosted, "run") as run:
            self.assertEqual(hosted.main(["--stage", self.stage, "--finalize"]), 0)
            first = hosted.marker_path(self.stage).read_bytes()
            self.assertEqual(hosted.main(["--stage", self.stage, "--finalize"]), 0)
        prepare.assert_not_called()
        run.assert_not_called()
        self.assertEqual(hosted.marker_path(self.stage).read_bytes(), first)
        self.assertEqual(len(hosted.diagnostic_paths(self.stage)), 1)
        self.assertEqual(self.marker()["status"], "interrupted")
        self.assertEqual(self.marker()["interruption"], "cleanup_after_unfinished_runner")
        self.assertNotIn("PRIVATE_", first.decode())


    def test_legacy_marker_drops_private_packages_and_hashes_command_text(self):
        secret = "PRIVATE_TOKEN_EXACT_VALUE"
        legacy = {
            "stage": self.stage, "status": "running",
            "argv": ["server", "--prompt", "PRIVATE_PROMPT", "--token", secret],
            "environment": {
                "python": "3.12.1", "source": "PRIVATE_SOURCE",
                "platform": secret, "packages": [
                    "private @ https://user:" + secret + "@example.invalid/package",
                    ["safe-package", "1.2.3"], ["suspicious", secret]]},
            "phase_exit_codes": {"prepare": 0, "source": "PRIVATE_SOURCE"},
            "execution_deadline": {"seconds_available_at_runner_start": 123,
                                   "scope": "PRIVATE_PROMPT", "model": "PRIVATE_MODEL"}}
        marker = hosted.marker_path(self.stage)
        hosted.atomic(marker, legacy)
        with patch.dict(os.environ, {"TEST_API_KEY": secret}):
            hosted.finalize(self.stage)
            first = marker.read_bytes()
            hosted.finalize(self.stage)
        self.assertEqual(first, marker.read_bytes())
        value = json.loads(first)
        self.assertNotIn("PRIVATE_", first.decode())
        self.assertNotIn("example.invalid", first.decode())
        self.assertNotIn("argv", value)
        self.assertEqual(len(value["argv_sha256"]), 64)
        self.assertEqual(len(value["environment_omissions_sha256"]), 64)
        self.assertEqual(value["environment"], {"python": "3.12.1", "packages": [["safe-package", "1.2.3"]]})
        self.assertEqual(value["phase_exit_codes"], {"prepare": 0})
        self.assertNotIn("model", value["execution_deadline"])

    def test_existing_attempt_is_not_replayed_or_overwritten(self):
        marker = hosted.marker_path(self.stage)
        hosted.atomic(marker, {"stage": self.stage, "status": "interrupted"})
        before = marker.read_bytes()
        with patch.object(hosted, "prepare") as prepare:
            with self.assertRaises(ValueError):
                hosted.main(["--stage", self.stage])
        prepare.assert_not_called()
        self.assertEqual(marker.read_bytes(), before)

    def test_startup_publication_precedes_work_and_failures_never_publish_error_text(self):
        events = []
        def publish(stage, marker, paths):
            events.append(("publish", self.marker()["status"]))
        def prepare(stage):
            events.append(("prepare", self.marker()["status"]))
            raise RuntimeError("PRIVATE_SERVER_ERROR_WITH_CREDENTIAL")
        with patch.object(hosted, "prepare", side_effect=prepare), \
                patch.object(hosted, "publish", side_effect=publish):
            self.assertEqual(hosted.main(["--stage", self.stage, "--publish"]), 1)
        self.assertEqual(events, [("publish", "running"), ("prepare", "running"), ("publish", "failed")])
        self.assertEqual(self.marker()["error_type"], "RuntimeError")
        self.assertNotIn("PRIVATE_SERVER_ERROR", hosted.marker_path(self.stage).read_text())

    def test_publication_rejects_private_paths_and_symlinks(self):
        marker = hosted.marker_path(self.stage)
        hosted.atomic(marker, {"stage": self.stage, "status": "interrupted"})
        with self.assertRaises(ValueError):
            hosted.safe_public_files(self.stage, marker, [".artifacts/raw-answer.jsonl"])
        if os.name != "nt":
            private = self.root / ".artifacts/raw-answer.jsonl"
            private.parent.mkdir(parents=True, exist_ok=True)
            private.write_text("PRIVATE_SOURCE")
            public = self.root / self.report
            public.parent.mkdir(parents=True)
            public.symlink_to(private)
            with self.assertRaises(ValueError):
                hosted.safe_public_files(self.stage, marker)

    @unittest.skipUnless(shutil.which("git"), "Git publication integration")
    def test_git_publication_is_repeatable_and_excludes_the_real_index(self):
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, text=True,
                                           stderr=subprocess.PIPE).strip()
        origin = Path(self.directory.name) / "origin.git"
        git("init", "--bare", str(origin))
        git("init", "-b", "main")
        git("config", "user.name", "test")
        git("config", "user.email", "test@example.invalid")
        (self.root / ".gitignore").write_text(".artifacts/\n")
        git("add", ".gitignore")
        git("commit", "-m", "fixture source")
        git("remote", "add", "origin", str(origin))
        original_head = git("rev-parse", "HEAD")
        private = self.root / ".artifacts/private.txt"
        private.parent.mkdir()
        private.write_text("PRIVATE_SOURCE_AND_SECRET")
        git("add", "-f", str(private))
        original_index = git("ls-files", "--stage")
        report = self.root / self.report
        report.parent.mkdir(parents=True)
        report.write_text('{"status":"partial"}\n')
        marker = hosted.marker_path(self.stage)
        hosted.atomic(marker, {"stage": self.stage, "status": "interrupted"})
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
            first = hosted.publish(self.stage, marker, [self.report])
            repeat = hosted.publish(self.stage, marker, [self.report])
            self.assertEqual(repeat, first)
            self.assertNotIn(".artifacts/private.txt", git("ls-tree", "-r", "--name-only", first))
            self.assertIn(self.report, git("ls-tree", "-r", "--name-only", first))
            self.assertEqual(git("show", first + ":" + self.report), '{"status":"partial"}')
            report.write_text('{"status":"partial","observed_attempts":1}\n')
            newer = hosted.publish(self.stage, marker, [self.report])
        self.assertNotEqual(newer, first)
        self.assertEqual(git("rev-parse", newer + "^"), first)
        self.assertEqual(git("rev-parse", "HEAD"), original_head)
        self.assertEqual(git("ls-files", "--stage"), original_index)
        branch = "refs/heads/validation/20261112-" + self.stage + "-1234-2"
        self.assertTrue(git("ls-remote", "--heads", "origin", branch).startswith(newer))


if __name__ == "__main__":
    unittest.main()
