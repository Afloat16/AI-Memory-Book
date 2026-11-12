"""Failure publication tests; no model, network or external mutation."""
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_round2_anchor as runner


class AnchorHostedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.root_patch = patch.object(runner, "ROOT", self.root)
        self.root_patch.start()
        self.git_patch = patch.object(runner.host, "publication_command",
                                      return_value=SimpleNamespace(stdout="a" * 40, returncode=0))
        self.git_patch.start()
        self.stage = "regression-authored36"

    def tearDown(self):
        self.git_patch.stop()
        self.root_patch.stop()
        self.temporary.cleanup()

    def test_public_paths_are_explicit_and_exclude_private_state_and_other_cohorts(self):
        prefix, marker, state = runner.paths(self.stage)
        marker.parent.mkdir(parents=True)
        marker.write_text("{}")
        prefix.parent.mkdir(parents=True)
        Path(str(prefix) + ".md").write_text("public metrics")
        Path(str(prefix) + ".private.json").write_text("PRIVATE")
        state.mkdir(parents=True)
        (state / "memory.db").write_text("PRIVATE SOURCE")
        selected = runner.public_paths(self.stage)
        self.assertEqual(len(selected), 2)
        self.assertFalse(any("private" in path or ".artifacts" in path for path in selected))
        with self.assertRaises(ValueError):
            runner.paths("../../unregistered")

    def test_existing_attempt_is_not_automatically_replayed(self):
        _, marker, _ = runner.paths(self.stage)
        marker.parent.mkdir(parents=True)
        marker.write_text("{}")
        with patch.object(runner.host, "run") as run:
            with self.assertRaisesRegex(ValueError, "never automatically replays"):
                runner.evaluate(self.stage, False)
            run.assert_not_called()

    def test_controlled_deadline_remains_interrupted(self):
        with patch.object(runner.host, "interrupt_handlers", return_value=nullcontext()), \
             patch.object(runner.host, "execution_timer", return_value=nullcontext()), \
             patch.object(runner.host, "cleanup_signals", return_value=nullcontext()), \
             patch.object(runner.host, "run", side_effect=runner.host.ValidationInterrupted("execution_deadline")):
            self.assertEqual(runner.evaluate(self.stage, False), 124)
        _, marker, _ = runner.paths(self.stage)
        record = json.loads(marker.read_text())
        self.assertEqual(record["status"], "interrupted")
        self.assertEqual(record["interruption_reason"], "execution_deadline")
        self.assertNotIn("completed_samples", record)

    def test_cleanup_exports_existing_ledger_without_running_or_importing_model(self):
        prefix, marker, state = runner.paths(self.stage)
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({**runner.marker_base(self.stage), "status": "running"}))
        with patch.object(runner, "export_checkpoint", return_value={}) as export, \
             patch.object(runner.host, "run") as run:
            runner.finalize(self.stage, False)
            export.assert_called_once_with(state, prefix, "interrupted_unknown")
            run.assert_not_called()
        self.assertEqual(json.loads(marker.read_text())["status"], "interrupted_unknown")

    def test_cleanup_rejects_another_run_marker(self):
        _, marker, _ = runner.paths(self.stage)
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({**runner.marker_base(self.stage), "status": "running", "run_id": "other"}))
        with self.assertRaisesRegex(ValueError, "another cohort/source"):
            runner.finalize(self.stage, False)


if __name__ == "__main__":
    unittest.main()
