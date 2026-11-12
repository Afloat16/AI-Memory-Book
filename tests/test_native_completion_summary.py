"""Verify native aggregation against actual retained evidence, including interruption."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.summarize_native_completion import ROOT, checked_report, load_checkpoints


class NativeCompletionSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / "benchmarks/native-completion-manifest.json").read_text())
        cls.stage = next(stage for stage in manifest["stages"]
                         if stage["id"] == "development-synthetic61")
        cls.checkpoints = load_checkpoints([ROOT / "benchmarks/reports/native-completion-checkpoint.json"])

    def test_retained_complete_stage_has_matching_raw_summary_checkpoint(self):
        report, hashes, provenance = checked_report(self.stage, ROOT, self.checkpoints)
        self.assertTrue(report["validation"]["passed"])
        self.assertEqual(len(hashes), 3)
        self.assertEqual(len(report["engines"][1]["configurations"]), 12)
        self.assertEqual(len(provenance), 1)

    def test_running_checkpoint_cannot_be_promoted_to_complete(self):
        checkpoints = copy.deepcopy(self.checkpoints)
        checkpoints[0][1]["stages"][self.stage["id"]]["status"] = "running"
        with self.assertRaisesRegex(ValueError, "No completed checkpoint"):
            checked_report(self.stage, ROOT, checkpoints)

    def test_copied_pass_field_cannot_hide_a_changed_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for name in self.stage["outputs"]:
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            summary_path = next(base / name for name in self.stage["outputs"]
                                if name.endswith(".summary.json"))
            summary = json.loads(summary_path.read_text())
            summary["engines"][1]["configurations"][0]["metrics"]["complete_evidence_rate"] = 1.0
            summary_path.write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "Full report and summary disagree"):
                checked_report(self.stage, base, self.checkpoints)

    def test_changed_registered_budget_is_rejected(self):
        stage, checkpoints = copy.deepcopy(self.stage), copy.deepcopy(self.checkpoints)
        stage["argv"][stage["argv"].index("--budget-chars") + 1] = "3000"
        record = checkpoints[0][1]["stages"][stage["id"]]
        record["argv"] = [record["argv"][0], *stage["argv"][1:]]
        with self.assertRaisesRegex(ValueError, "Engine configuration differs"):
            checked_report(stage, ROOT, checkpoints)


if __name__ == "__main__":
    unittest.main()
