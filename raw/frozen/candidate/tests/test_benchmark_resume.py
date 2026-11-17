"""Exercise resumable measurements using real, inexpensive subprocess stages."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks.resume import run


WORKER = '''\
import json
from pathlib import Path
import sys
import time
output = Path(sys.argv[1])
counter = Path(str(output) + ".calls")
counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
if Path(str(output) + ".block").exists():
    Path(str(output) + ".ready").touch()
    while Path(str(output) + ".block").exists():
        time.sleep(0.01)
if Path(str(output) + ".fail").exists():
    raise SystemExit(7)
if Path(str(output) + ".mutate").exists():
    Path("source.txt").write_text("changed source")
if Path(str(output) + ".keep").exists():
    raise SystemExit(0)
if Path(str(output) + ".invalid").exists():
    output.write_text("incomplete JSON")
else:
    output.write_text(json.dumps({"validation": {"passed": not Path(str(output) + ".bad").exists()}}))
'''


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "source.txt").write_text("frozen source")
        (self.root / "dataset.json").write_text("[]")
        (self.root / "worker.py").write_text(WORKER)
        self.manifest = self.root / "manifest.json"
        self.checkpoint = self.root / "checkpoint.json"
        self.spec = {"version": 1, "cwd": ".",
                     "inputs": [{"path": "source.txt"}, {"path": "dataset.json"},
                                {"path": ".", "pattern": "*.py"}],
                     "stages": [self.stage("first"), self.stage("second"), self.stage("last")]}
        self.write_manifest()

    def stage(self, name):
        return {"id": name, "argv": ["{python}", "worker.py", name + ".json"],
                "outputs": [name + ".json"]}

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.spec))

    def run_stages(self):
        with redirect_stdout(io.StringIO()):
            return run(self.manifest, self.checkpoint)

    def calls(self, name):
        path = self.root / (name + ".json.calls")
        return int(path.read_text()) if path.exists() else 0

    def test_failure_resumes_after_checked_prefix_without_duplicate_measurements(self):
        failure = self.root / "second.json.fail"
        failure.touch()
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_stages()
        state = json.loads(self.checkpoint.read_text())
        self.assertEqual(state["stages"]["first"]["status"], "completed")
        self.assertEqual(state["stages"]["second"]["status"], "failed")
        self.assertNotIn("last", state["stages"])
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 1, 0])
        failure.unlink()
        self.run_stages()
        self.run_stages()
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 2, 1])

    def test_changed_source_dataset_or_command_cannot_reuse_checkpoint(self):
        self.run_stages()
        for name in ("source.txt", "dataset.json", "worker.py", "manifest.json"):
            path = self.root / name
            original = path.read_text()
            path.write_text(original + "\n")
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "identity changed"):
                self.run_stages()
            path.write_text(original)
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 1, 1])

    def test_missing_or_corrupt_completed_report_invalidates_downstream_stages(self):
        self.run_stages()
        (self.root / "second.json").write_text('{"tampered": true}')
        self.run_stages()
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 2, 2])
        (self.root / "second.json").unlink()
        self.run_stages()
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 3, 3])

    def test_source_change_during_stage_stops_before_success_or_next_stage(self):
        (self.root / "first.json.mutate").touch()
        with self.assertRaisesRegex(RuntimeError, "changed during stage"):
            self.run_stages()
        state = json.loads(self.checkpoint.read_text())
        self.assertEqual(state["stages"]["first"]["status"], "failed")
        self.assertEqual(self.calls("second"), 0)
        with self.assertRaisesRegex(RuntimeError, "identity changed"):
            self.run_stages()

    def test_invalid_json_and_report_failure_never_become_completed(self):
        invalid = self.root / "first.json.invalid"
        invalid.touch()
        with self.assertRaises(ValueError):
            self.run_stages()
        invalid.unlink()
        (self.root / "first.json.bad").touch()
        with self.assertRaisesRegex(ValueError, "validation failed"):
            self.run_stages()
        state = json.loads(self.checkpoint.read_text())
        self.assertEqual(state["stages"]["first"]["status"], "failed")
        self.assertEqual(self.calls("second"), 0)

    def test_zero_exit_cannot_reuse_stale_preexisting_report(self):
        (self.root / "first.json").write_text("{}")
        (self.root / "first.json.keep").touch()
        with self.assertRaisesRegex(ValueError, "pre-existing report unchanged"):
            self.run_stages()
        self.assertEqual(self.calls("second"), 0)

    def test_argv_metacharacters_are_literal_filename_not_shell(self):
        name = "literal ; echo injected"
        self.spec["stages"] = [self.stage(name)]
        self.write_manifest()
        self.run_stages()
        self.assertTrue((self.root / (name + ".json")).is_file())
        self.assertFalse((self.root / "injected").exists())

    def test_new_source_file_is_detected_even_when_existing_files_are_unchanged(self):
        self.run_stages()
        (self.root / "new_module.py").write_text("NEW = True")
        with self.assertRaisesRegex(RuntimeError, "identity changed"):
            self.run_stages()

    def test_dependency_version_change_invalidates_completed_checkpoint(self):
        distribution = SimpleNamespace(metadata={"Name": "mcp"}, version="fixture-1")
        with patch("benchmarks.resume.importlib.metadata.distributions", return_value=[distribution]):
            self.run_stages()
            distribution.version = "fixture-2"
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                self.run_stages()
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 1, 1])

    def test_duplicate_distribution_paths_do_not_change_checkpoint_identity(self):
        first = SimpleNamespace(metadata={"Name": "Some_Package"}, version="1.0")
        duplicate = SimpleNamespace(metadata={"Name": "some-package"}, version="1.0")
        with patch("benchmarks.resume.importlib.metadata.distributions", return_value=[first]):
            self.run_stages()
        with patch("benchmarks.resume.importlib.metadata.distributions", return_value=[duplicate, first, first]):
            self.run_stages()
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 1, 1])
        conflicting = SimpleNamespace(metadata={"Name": "some.package"}, version="2.0")
        with patch("benchmarks.resume.importlib.metadata.distributions", return_value=[first, conflicting]):
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                self.run_stages()

    def test_runtime_command_output_and_sqlite_version_are_frozen(self):
        version = self.root / "runtime-version.txt"
        version.write_text("runtime-1")
        self.spec["runtime_commands"] = [[
            "{python}", "-c", "from pathlib import Path; print(Path('runtime-version.txt').read_text())"]]
        self.write_manifest()
        self.run_stages()
        identity = json.loads(self.checkpoint.read_text())["identity"]["runtime"]
        self.assertEqual(identity["commands"][0]["stdout"], "runtime-1\n")
        version.write_text("runtime-2")
        with self.assertRaisesRegex(RuntimeError, "identity changed"):
            self.run_stages()
        version.write_text("runtime-1")
        with patch("benchmarks.resume.sqlite3.sqlite_version", "changed-sqlite"):
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                self.run_stages()

    def test_runtime_command_timeout_stops_before_measurements(self):
        self.spec["runtime_commands"] = [["{python}", "-c", "import time; time.sleep(30)"]]
        self.write_manifest()
        with patch("benchmarks.resume.RUNTIME_COMMAND_TIMEOUT", 0.05):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_stages()
        self.assertEqual(self.calls("first"), 0)

    @unittest.skipIf(os.name == "nt", "POSIX descendant process-group cleanup")
    def test_failed_leader_does_not_leave_sigterm_ignoring_grandchild(self):
        (self.root / "grandchild.py").write_text(
            "import signal, time\nfrom pathlib import Path\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "while True:\n"
            "    with Path('heartbeat').open('a') as stream: stream.write('x')\n"
            "    time.sleep(0.01)\n")
        (self.root / "leader.py").write_text(
            "import subprocess, sys, time\nfrom pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, 'grandchild.py'], close_fds=True)\n"
            "Path('grandchild.pid').write_text(str(child.pid))\n"
            "while not Path('heartbeat').exists(): time.sleep(0.01)\n"
            "raise SystemExit(9)\n")
        self.spec["stages"][0]["argv"] = ["{python}", "leader.py"]
        self.write_manifest()
        try:
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_stages()
            heartbeat = (self.root / "heartbeat").read_bytes()
            time.sleep(0.1)
            self.assertEqual((self.root / "heartbeat").read_bytes(), heartbeat)
            self.assertEqual(self.calls("second"), 0)
        finally:
            pid = self.root / "grandchild.pid"
            if pid.exists():
                try:
                    os.kill(int(pid.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @unittest.skipIf(os.name == "nt", "POSIX SIGTERM and process-group cleanup")
    def test_sigterm_checkpoints_failure_and_resume_keeps_completed_prefix(self):
        block = self.root / "second.json.block"
        block.touch()
        process = subprocess.Popen(
            [sys.executable, "-m", "benchmarks.resume", "--manifest", str(self.manifest),
             "--checkpoint", str(self.checkpoint)], cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "second.json.ready").exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    self.fail(f"Runner stopped before test barrier: {process.communicate()}")
                time.sleep(0.01)
            self.assertTrue((self.root / "second.json.ready").exists())
            process.terminate()
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 130)
            state = json.loads(self.checkpoint.read_text())
            self.assertEqual(state["stages"]["second"]["status"], "failed")
            self.assertFalse((self.root / "second.json").exists())
        finally:
            block.unlink(missing_ok=True)
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        self.run_stages()
        self.assertEqual([self.calls(name) for name in ("first", "second", "last")], [1, 2, 1])


if __name__ == "__main__":
    unittest.main()
