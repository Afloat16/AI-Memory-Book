"""Completion guards for the reporting-only hosted aggregation entry point."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import aggregate_hosted_validation as aggregate


class HostedAggregationTests(unittest.TestCase):
    def test_inventory_requires_full_cohorts_and_authentication_files(self):
        paths, hosted = aggregate.requirements(aggregate.ROOT)
        self.assertEqual(len(hosted), 12)
        self.assertIn("benchmarks/results/native-completion-regression-public1015.json.gz", paths)
        self.assertIn("benchmarks/results/semantic-final-external-hotpot128.json.gz", paths)
        self.assertIn("benchmarks/results/local-answer-final-hotpotqa.json.gz", paths)
        self.assertIn("benchmarks/results/full-workflow-transfer36.json", paths)
        self.assertIn(aggregate.CLAUDE_MARKER, paths)
        self.assertIn("benchmarks/reports/hosted-native-regression-public1015-checkpoint.json", paths)

    def test_missing_results_fail_before_a_summarizer_can_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in (aggregate.NATIVE, aggregate.SEMANTIC, aggregate.HOSTED):
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((aggregate.ROOT / name).read_bytes())
            with patch.object(aggregate.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "Missing required cohort evidence"):
                    aggregate.preflight(root)
            run.assert_not_called()

    def test_actual_retained_stage_has_matching_hashes_and_registered_command(self):
        manifest = aggregate.read(aggregate.ROOT, aggregate.NATIVE)
        aggregate.verify_checkpoint(aggregate.ROOT, aggregate.OLD_CHECKPOINTS[0],
                                    manifest["stages"][0])

    def test_running_checkpoint_cannot_authenticate_completed_files(self):
        manifest = aggregate.read(aggregate.ROOT, aggregate.NATIVE)
        checkpoint = copy.deepcopy(aggregate.read(aggregate.ROOT, aggregate.OLD_CHECKPOINTS[0]))
        checkpoint["stages"][manifest["stages"][0]["id"]]["status"] = "running"
        with patch.object(aggregate, "read", return_value=checkpoint):
            with self.assertRaisesRegex(ValueError, "Incomplete or inconsistent"):
                aggregate.verify_checkpoint(aggregate.ROOT, aggregate.OLD_CHECKPOINTS[0],
                                            manifest["stages"][0])

    def test_publisher_requires_the_dedicated_trigger_branch(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                                    "GITHUB_REF": "refs/heads/ci/final-aggregation-tools"}, clear=True):
            with patch.object(aggregate.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "dedicated Actions branch"):
                    aggregate.publish(aggregate.ROOT, False)
            run.assert_not_called()

    def test_failed_snapshot_can_only_stage_its_failure_audit(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                                    "GITHUB_REF": "refs/heads/ci/aggregate-memory-validation"}, clear=True):
            with patch.object(aggregate.subprocess, "run") as run:
                aggregate.publish(aggregate.ROOT, False)
            staged = [call.args[0] for call in run.call_args_list if call.args[0][1] == "add"]
        self.assertEqual(staged, [["git", "add", "--", aggregate.AUDIT]])


if __name__ == "__main__":
    unittest.main()
