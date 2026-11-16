"""Unit contracts for grouped release-cell control, without building an app."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import build_native_release_cell as cell


class NativeReleaseCellTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_actual_success_count_and_skip_lines_are_parsed(self):
        text = ("test_one (tests.Example) ... skipped 'optional tokenizer'\n"
                "test_two (tests.Example) ... skipped 'optional tokenizer'\n"
                "Ran 144 tests in 1.234s\n\nOK (skipped=2)\n")
        result = cell.test_summary(text)
        self.assertEqual((result["tests_run"], result["skipped"]), (144, 2))
        self.assertTrue(result["successful_summary"])
        self.assertEqual(len(result["skipped_test_lines"]), 2)

    def test_missing_summary_does_not_claim_tests_or_skips(self):
        result = cell.test_summary("interpreter failed before unittest started\n")
        self.assertIsNone(result["tests_run"])
        self.assertIsNone(result["skipped"])
        self.assertFalse(result["successful_summary"])

    def test_failure_and_ansi_crlf_are_not_reported_as_success(self):
        result = cell.test_summary(
            "\x1b[31mRan 144 tests in 2.000s\x1b[0m\r\n\r\n"
            "FAILED (failures=1, skipped=3)\r\n")
        self.assertEqual((result["tests_run"], result["skipped"]), (144, 3))
        self.assertFalse(result["successful_summary"])

    def test_count_is_observed_not_replaced_with_expected_144(self):
        result = cell.test_summary("Ran 2 tests in 0.010s\n\nOK\n")
        self.assertEqual(result["tests_run"], 2)
        self.assertEqual(result["skipped"], 0)

    def test_failed_command_retains_actual_exit_and_output(self):
        report = {"commands": [], "tests": None}
        path, log = self.root / "validation.json", self.root / "test.log"
        completed = subprocess.CompletedProcess(["python"], 7, stdout="out\n", stderr="err\n")
        with mock.patch.object(cell.subprocess, "run", return_value=completed), \
                contextlib.redirect_stdout(io.StringIO()):
            result, output = cell.run_command(["python"], "test", log, report, path, {},
                                               check=False)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(output, "out\nerr\n")
        self.assertEqual(log.read_text(), output)
        saved = json.loads(path.read_text())
        self.assertEqual(saved["commands"][0]["returncode"], 7)
        self.assertEqual(saved["commands"][0]["log_sha256"], cell.digest(log))
        self.assertIsNone(saved["tests"])

    def test_launch_failure_preserves_error_without_fabricating_exit(self):
        report = {"commands": [], "tests": None}
        path, log = self.root / "validation.json", self.root / "build.log"
        with mock.patch.object(cell.subprocess, "run", side_effect=OSError("missing interpreter")):
            with self.assertRaises(OSError):
                cell.run_command(["missing"], "compile", log, report, path, {})
        saved = json.loads(path.read_text())
        self.assertIsNone(saved["commands"][0]["returncode"])
        self.assertIn("missing interpreter", log.read_text())
        self.assertIsNone(saved["tests"])

    def test_cleanup_preserves_evidence_and_refuses_tracked_build_inputs(self):
        build = self.root / "build"
        build.mkdir()
        (build / "tracked.txt").write_text("retain")
        with mock.patch.object(cell.native_release.legacy, "git", return_value=b"build/tracked.txt\n"):
            with self.assertRaisesRegex(RuntimeError, "tracked"):
                cell.clean_generated(self.root)
        self.assertTrue((build / "tracked.txt").exists())

    def test_cleanup_removes_only_generated_products(self):
        (self.root / "build").mkdir()
        (self.root / "build" / "cache").write_text("old ABI")
        package = self.root / "src" / "memory_book"
        package.mkdir(parents=True)
        (package / "_native.old.so").write_bytes(b"old ABI")
        (package / "text.py").write_text("source")
        (self.root / "src" / "ai_memory_book.egg-info").mkdir()
        evidence = self.root / ".artifacts" / "native-cell-evidence"
        evidence.mkdir(parents=True)
        (evidence / "previous.log").write_text("retain")
        with mock.patch.object(cell.native_release.legacy, "git", return_value=b""):
            removed = cell.clean_generated(self.root)
        self.assertEqual(set(removed), {"build", "src/ai_memory_book.egg-info",
                                        "src/memory_book/_native.old.so"})
        self.assertEqual((package / "text.py").read_text(), "source")
        self.assertEqual((evidence / "previous.log").read_text(), "retain")

    def test_wrong_interpreter_fails_before_commands_and_receipt(self):
        expected = "3.10" if sys.version_info[:2] != (3, 10) else "3.11"
        with mock.patch.object(cell, "ROOT", self.root), \
                mock.patch.object(cell, "run_command") as run, \
                contextlib.redirect_stderr(io.StringIO()):
            result = cell.main(["--expected-python", expected, "--target", "linux_x86_64"])
        self.assertEqual(result, 1)
        run.assert_not_called()
        report = json.loads(next(self.root.rglob("validation.json")).read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIsNone(report["tests"])
        self.assertIsNone(report["receipt"])

    def test_failed_installed_tests_never_create_receipt(self):
        expected = ".".join(map(str, sys.version_info[:2]))
        tag = "cp" + expected.replace(".", "")
        filename = "ai_memory_book-0.9.0-" + tag + "-" + tag + "-manylinux_2_17_x86_64.whl"
        phases = []

        def fake_run(argv, phase, log, report, report_path, env, *, check=True):
            phases.append(phase)
            if phase == "compile-wheel":
                directory = Path(argv[argv.index("--wheel-dir") + 1])
                (directory / filename).write_bytes(b"unit-test placeholder, never installed")
            if phase == "repair-wheel":
                directory = Path(argv[argv.index("--wheel-dir") + 1])
                shutil.copyfile(Path(argv[-1]), directory / filename)
            output = ("Ran 144 tests in 0.001s\n\nFAILED (failures=1)\n"
                      if phase == "installed-native-tests" else "mock command\n")
            log.write_text(output)
            code = 1 if phase == "installed-native-tests" else 0
            return subprocess.CompletedProcess(argv, code, stdout=output, stderr=""), output

        env = {"NATIVE_CELL_PYTHON": sys.executable, "MEMORY_BOOK_BUILD_NATIVE": "1",
               "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}
        identity = {"version": "0.9.0", "commit": "a" * 40, "tree": "b" * 40}
        with mock.patch.object(cell, "ROOT", self.root), \
                mock.patch.object(cell.sys, "platform", "linux"), \
                mock.patch.object(cell.native_release, "_host_target", return_value="linux_x86_64"), \
                mock.patch.object(cell.native_release, "_portable_identity", return_value=(identity, {}, {})), \
                mock.patch.object(cell, "clean_generated", return_value=[]), \
                mock.patch.object(cell, "run_command", side_effect=fake_run), \
                mock.patch.dict(os.environ, env), contextlib.redirect_stderr(io.StringIO()):
            result = cell.main(["--expected-python", expected, "--target", "linux_x86_64"])
        self.assertEqual(result, 1)
        self.assertIn("installed-native-tests", phases)
        self.assertNotIn("installed-native-smoke-and-receipt", phases)
        report = json.loads(next(self.root.rglob("validation.json")).read_text())
        self.assertEqual(report["tests"]["tests_run"], 144)
        self.assertEqual(report["tests"]["returncode"], 1)
        self.assertIsNone(report["receipt"])
        self.assertFalse(list(self.root.rglob("*.receipt.json")))


if __name__ == "__main__":
    unittest.main()
