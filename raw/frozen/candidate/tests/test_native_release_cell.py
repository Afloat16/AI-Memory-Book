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


OPTIONAL_SKIP_LINES = (
    "test_token_caps_keep_complete_payload_counts_and_source_spans "
    "(tests.test_native_backend.NativeMemoryBookEquivalenceTests) ... skipped 'Install .[tokens]'",
    "test_both_token_encoders_keep_exact_budgets_and_source_refs "
    "(tests.test_native_ranking_backend.NativeStoreEquivalenceTests) ... skipped 'Install .[tokens]'",
    "test_available_shared_gil_subinterpreters_keep_main_module_working "
    "(tests.test_native_segmentation_backend.NativeSegmentationModuleStateTests) "
    "... skipped '_xxsubinterpreters is not available in this Python build'",
)


def successful_output(skips=()):
    ending = f"OK (skipped={len(skips)})" if skips else "OK"
    return "\n".join((*skips, "Ran 144 tests in 0.001s", "", ending, ""))


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

    def test_optional_skips_accept_both_supported_unittest_identifier_formats(self):
        for line in OPTIONAL_SKIP_LINES:
            method = line.split(" ", 1)[0]
            qualified = line.replace(") ... skipped", "." + method + ") ... skipped", 1)
            for variant in (line, qualified):
                with self.subTest(line=variant):
                    cell.validate_test_result(cell.test_summary(successful_output([variant])), 0)

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

    def run_cell_with_test_result(self, test_output, test_returncode):
        root = Path(tempfile.mkdtemp(dir=self.root))
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
            if phase == "installed-native-smoke-and-receipt":
                receipt = Path(argv[argv.index("--output") + 1])
                receipt.write_text(json.dumps({"wheel": {"native_sha256": "c" * 64},
                                               "runtime_smoke": {"backend": "native"}}))
            output = test_output if phase == "installed-native-tests" else "mock command\n"
            log.write_text(output)
            code = test_returncode if phase == "installed-native-tests" else 0
            return subprocess.CompletedProcess(argv, code, stdout=output, stderr=""), output

        env = {"NATIVE_CELL_PYTHON": sys.executable, "MEMORY_BOOK_BUILD_NATIVE": "1",
               "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}
        identity = {"version": "0.9.0", "commit": "a" * 40, "tree": "b" * 40}
        with mock.patch.object(cell, "ROOT", root), \
                mock.patch.object(cell.sys, "platform", "linux"), \
                mock.patch.object(cell.native_release, "_host_target", return_value="linux_x86_64"), \
                mock.patch.object(cell.native_release, "_portable_identity", return_value=(identity, {}, {})), \
                mock.patch.object(cell.native_release, "validate_receipt"), \
                mock.patch.object(cell, "clean_generated", return_value=[]), \
                mock.patch.object(cell, "run_command", side_effect=fake_run), \
                mock.patch.dict(os.environ, env), contextlib.redirect_stderr(io.StringIO()):
            result = cell.main(["--expected-python", expected, "--target", "linux_x86_64"])
        report = json.loads(next(root.rglob("validation.json")).read_text())
        return result, report, phases, root

    def assert_no_receipt(self, output, returncode=0):
        result, report, phases, root = self.run_cell_with_test_result(output, returncode)
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "failed")
        self.assertIn("installed-native-tests", phases)
        self.assertNotIn("installed-native-smoke-and-receipt", phases)
        self.assertEqual(report["tests"]["returncode"], returncode)
        self.assertEqual((next(root.rglob("validation.json")).parent / "test.log").read_text(), output)
        self.assertIsNone(report["receipt"])
        self.assertFalse(list(root.rglob("*.receipt.json")))
        self.assertFalse((root / ".artifacts" / "native-wheels").exists())
        return report

    def test_failed_installed_tests_never_create_receipt(self):
        report = self.assert_no_receipt("Ran 144 tests in 0.001s\n\nFAILED (failures=1)\n", 1)
        self.assertEqual(report["tests"]["tests_run"], 144)

    def test_unexpected_skips_or_inconsistent_outcomes_never_create_receipt(self):
        cases = {
            "all tests skipped": "Ran 144 tests in 0.001s\n\nOK (skipped=144)\n",
            "native availability skip": successful_output([
                "test_native (tests.NativeTests) ... skipped 'Native extension is not installed'"]),
            "changed optional reason": successful_output([
                OPTIONAL_SKIP_LINES[0].replace("Install .[tokens]", "Native extension is not installed")]),
            "duplicate optional skip": successful_output([OPTIONAL_SKIP_LINES[0]] * 2),
            "missing skip line": successful_output(OPTIONAL_SKIP_LINES[:2]).replace(
                OPTIONAL_SKIP_LINES[1] + "\n", ""),
            "unreported skip line": OPTIONAL_SKIP_LINES[0] + "\n" + successful_output(),
            "expected failures": "Ran 144 tests in 0.001s\n\nOK (expected failures=144)\n",
            "unexpected successes": "Ran 144 tests in 0.001s\n\nOK (unexpected successes=1)\n",
            "duplicate test count": "Ran 144 tests in 0.001s\n" + successful_output(),
            "duplicate outcome": successful_output() + "OK\n",
            "hidden failure": "FAIL: test_native (tests.NativeTests)\n" + successful_output(),
            "sanitizer failure": "ERROR: AddressSanitizer: heap-use-after-free\n" + successful_output(),
            "incomplete run": "Ran 143 tests in 0.001s\n\nOK\n",
            "missing outcome": "Ran 144 tests in 0.001s\n",
        }
        for name, output in cases.items():
            with self.subTest(case=name):
                self.assert_no_receipt(output)

    def test_successful_tests_create_receipt_only_with_the_allowed_optional_skips(self):
        for skips in ((), OPTIONAL_SKIP_LINES[:2], OPTIONAL_SKIP_LINES):
            with self.subTest(skipped=len(skips)):
                result, report, phases, root = self.run_cell_with_test_result(successful_output(skips), 0)
                self.assertEqual(result, 0)
                self.assertEqual(report["status"], "passed")
                self.assertEqual(report["tests"]["skipped"], len(skips))
                self.assertIn("installed-native-smoke-and-receipt", phases)
                artifacts = root / ".artifacts" / "native-wheels"
                self.assertEqual(len(list(artifacts.glob("*.whl"))), 1)
                self.assertEqual(len(list(artifacts.glob("*.receipt.json"))), 1)


if __name__ == "__main__":
    unittest.main()
