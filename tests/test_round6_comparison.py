"""Artificial inputs and fake controller flows; no fresh data, model or scoring."""
import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round6_comparison as c
from scripts import round6_comparison_controller as controller
from scripts import round6_comparison_data as data


class RoundSixComparisonTests(unittest.TestCase):
    def plan(self):
        return json.loads(c.PLAN.read_bytes())

    def environment(self, phase="run"):
        return {"GITHUB_REPOSITORY": c.REPOSITORY,
            "GITHUB_REF": c.TRIGGER if phase == "run" else c.FREEZE_TRIGGER,
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_NAME": "push",
            "GITHUB_SHA": "a" * 40, "ORT_DISABLE_TELEMETRY": "1"}

    def binding(self):
        return {"optional_semantic": False, "optional_project_statistics": False,
                "baseline": {"commit": "b" * 40}, "candidate": {"commit": "c" * 40}}

    def test_registered_matrix_is_complete_and_q2_cannot_be_silently_added(self):
        plan = self.plan()
        self.assertEqual(c.validate_plan(plan), plan)
        self.assertEqual(len(c.stages(self.binding())), 8)
        for change in ({"optional_semantic": True}, {"optional_project_statistics": True}):
            with self.assertRaises(ValueError):
                c.stages({**self.binding(), **change})
        for key, value in (("quality_cells", 41), ("retrieval_and_search_calls", 6911),
                           ("query_shuffle_seed", 1), ("optional_semantic", True)):
            changed = copy.deepcopy(plan)
            changed["independent_validation"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.validate_plan(changed)
        changed = copy.deepcopy(plan)
        changed["independent_validation"]["native"]["token_budgets"] = [1024]
        with self.assertRaises(ValueError):
            c.validate_plan(changed)

    def test_no_future_candidate_identity_is_invented(self):
        plan = self.plan()
        plan["candidate"].update(commit=None, runtime_sha256=None)
        with self.assertRaisesRegex(ValueError, "Declare and commit"):
            c.requested_candidate(plan)
        plan["candidate"].update(commit="c" * 40, runtime_sha256="d" * 64)
        self.assertEqual(c.requested_candidate(plan), {"commit": "c" * 40, "source_sha256": "d" * 64})
        plan["candidate"]["runtime_sha256"] = c.BASELINE["source_sha256"]
        with self.assertRaisesRegex(ValueError, "changed runtime"):
            c.requested_candidate(plan)

    def test_only_eight_new_modes_use_immutable_parameterized_measurement_helpers(self):
        self.assertIs(c.native, c.legacy.native)
        self.assertIs(c.component, c.legacy.component)
        self.assertIs(c.export, c.legacy.export)
        self.assertIsNot(c.frozen_inputs, c.legacy.frozen_inputs)
        self.assertNotEqual(c.BASELINE, c.legacy.BASELINE)
        self.assertEqual(c.legacy.VERSION, "round4-native-component-comparison-1")
        with self.assertRaisesRegex(ValueError, "another comparison"):
            c.verify_report({"stage": "candidate-semantic-native", "evaluator": c.VERSION,
                             "protocol": c.PROTOCOL}, self.plan(), self.binding(), ["artificial"])

    def historical_manifests(self):
        ids = [f"artificial-old-{i:04}" for i in range(896)]
        return [{"selected_ids": ids[:128]}, {"selected_ids": ids[128:384]},
                {"selected_ids": ids[384:640]}, {"selected_ids": ids[640:]}]

    def test_all_896_historical_ids_are_excluded_before_selection(self):
        histories = self.historical_manifests()
        excluded = data.exclusion_ids(histories)
        eligible = [f"artificial-new-{i:04}" for i in range(300)]
        ids = excluded + eligible
        selected = data.select_ids(ids, excluded, c.PREFIX, 256)
        self.assertEqual(len(selected), 256)
        self.assertTrue(set(selected) <= set(eligible))
        self.assertFalse(set(selected) & set(excluded))
        self.assertEqual(selected, data.select_ids(list(reversed(ids)), list(reversed(excluded)), c.PREFIX, 256))
        histories[-1]["selected_ids"][0] = histories[0]["selected_ids"][0]
        with self.assertRaisesRegex(ValueError, "896 distinct"):
            data.exclusion_ids(histories)

    def test_selection_rejects_duplicates_missing_old_ids_and_small_populations(self):
        for ids, excluded, count in ((["a", "a", "b"], ["b"], 1), (["a", "b"], ["b", "b"], 1),
                                      (["a", "b"], ["c"], 1), (["a", "b"], ["a"], 2)):
            with self.subTest(ids=ids, excluded=excluded), self.assertRaises(ValueError):
                data.select_ids(ids, excluded, "artificial/", count)
        with patch.object(data, "sha", return_value="equal-hash"):
            self.assertEqual(data.select_ids(["c", "a", "b"], [], "artificial/", 2), ["a", "b"])

    def test_source_freeze_failure_prevents_reading_any_fresh_source(self):
        with patch.object(c, "frozen_inputs", side_effect=ValueError("uncommitted binding")), \
                patch.object(data, "selected_dataset") as selected:
            with self.assertRaisesRegex(ValueError, "uncommitted"):
                data.freeze(Path("never-read.parquet"))
            selected.assert_not_called()

    def test_manifest_must_be_committed_before_data_loading(self):
        with patch.object(data, "registered_inputs", return_value=object()), \
                patch.object(c, "require_committed", side_effect=ValueError("uncommitted manifest")), \
                patch.object(data, "selected_dataset") as selected:
            with self.assertRaisesRegex(ValueError, "uncommitted manifest"):
                data.load(Path("never-read.parquet"))
            selected.assert_not_called()

    def test_only_authorized_first_push_can_prepare_or_score(self):
        for phase in ("run", "freeze"):
            good = self.environment(phase)
            with patch.dict(os.environ, good, clear=True):
                self.assertEqual(controller.actions_identity(phase), "123-1")
            for field, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_REPOSITORY", "another/repo"),
                                 ("GITHUB_REF", "refs/heads/main"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                                 ("ORT_DISABLE_TELEMETRY", "0")):
                with self.subTest(phase=phase, field=field), \
                        patch.dict(os.environ, {**good, field: value}, clear=True):
                    with self.assertRaises(ValueError):
                        controller.actions_identity(phase)

    def test_null_candidate_stops_freeze_before_asset_or_question_access(self):
        plan = self.plan()
        plan["candidate"].update(commit=None, runtime_sha256=None)
        with patch.dict(os.environ, self.environment("freeze"), clear=True), \
                patch.object(controller, "authorized_origin"), patch.object(controller, "git", return_value="a" * 40), \
                patch.object(c, "registered_plan", return_value=plan), \
                patch.object(controller, "prepare_assets") as assets, patch.object(data, "freeze") as selection:
            with self.assertRaisesRegex(ValueError, "Declare and commit"):
                controller.freeze(SimpleNamespace())
            assets.assert_not_called()
            selection.assert_not_called()

    def test_scored_worker_requires_claim_before_selected_source(self):
        args = SimpleNamespace(binding=Path("unused-binding"), manifest=Path("unused-manifest"), execution_claim=None)
        with patch.dict(os.environ, self.environment(), clear=True), \
                patch.object(c, "frozen_inputs", return_value=({}, {})), \
                patch.object(c, "git", return_value=("a" * 40 + "\n").encode()), \
                patch.object(data, "load") as load:
            with self.assertRaisesRegex(ValueError, "Missing exact execution claim"):
                c.worker(args)
            load.assert_not_called()

    def test_worker_cannot_replay_a_claim_into_alternate_paths(self):
        run_id = "123-1"
        private = c.ROOT / ".artifacts/round6-comparison" / run_id
        args = SimpleNamespace(stage="candidate-native", state=private / "states/candidate-native",
            output=c.ROOT / "benchmarks/results/round6-comparison-123-1/candidate-native",
            bundle=private / "frozen-pages.json", frozen_db=private / "states/export/frozen.db",
            data=private / "private/hotpot-dev-distractor.parquet", cache=private / "cache", source=private / "candidate/src")
        c.require_worker_paths(args, run_id)
        args.state = private / "states/second-attempt"
        with self.assertRaisesRegex(ValueError, "canonical state"):
            c.require_worker_paths(args, run_id)

    def run_fake_flow(self, root, interrupted=False):
        binding = self.binding()
        declaration = {"protocol": c.PROTOCOL}
        binding_path, manifest_path, plan_path = root / "binding.json", root / "manifest.json", root / "plan.json"
        binding_path.write_text(json.dumps(binding))
        manifest = {"binding_sha256": c.file_sha(binding_path)}
        manifest_path.write_text(json.dumps(manifest))
        plan_path.write_text("{}")
        args = SimpleNamespace(binding=binding_path, manifest=manifest_path, wall_time_seconds=1000)
        published, commands = [], []

        def publish(checkpoint, *_):
            published.append(json.loads(checkpoint.read_bytes()))
            return str(len(published)).zfill(40)

        def execute(command, _timeout, _log):
            commands.append(command)
            stage = command[command.index("--stage") + 1]
            running = published[-1]["stages"][stage]
            self.assertEqual(running["status"], "running")
            self.assertNotIn("execution_intent", running)
            self.assertEqual(command, [*running["argv"], "--execution-intent", str(len(published)).zfill(40)])
            state = Path(command[command.index("--state") + 1])
            prefix = Path(command[command.index("--output") + 1])
            state.mkdir(parents=True)
            (state / "attempts.jsonl").write_text('{"event":"started","id":"artificial-controller-only"}\n')
            if interrupted:
                raise TimeoutError("artificial interruption")
            if len(commands) > 1:
                previous = c.stages(binding)[len(commands) - 2]
                self.assertEqual(published[-1]["stages"][previous]["status"], "completed")
                self.assertEqual(len(published[-1]["stages"][previous]["outputs"]), 3)
            prefix.parent.mkdir(parents=True, exist_ok=True)
            c.public_paths(prefix)[0].write_bytes(gzip.compress(json.dumps({"stage": stage}).encode(), mtime=0))
            c.public_paths(prefix)[1].write_text("{}")
            return 0

        def assess(checkpoint_path, *_):
            checkpoint = json.loads(checkpoint_path.read_bytes())
            directory = root / checkpoint["result_directory"]
            (directory / "assessment.json").write_text('{"status":"complete-verified"}')
            (directory / "report.md").write_text("Artificial controller flow only; no retrieval or scoring.")
            return {"status": "complete-verified"}

        with patch.dict(os.environ, self.environment(), clear=True), patch.object(controller, "ROOT", root), \
                patch.object(c, "ROOT", root), patch.object(c, "PLAN", plan_path), \
                patch.object(c, "frozen_inputs", return_value=(declaration, binding)), \
                patch.object(data, "committed_manifest", return_value=(None, manifest)), \
                patch.object(c, "host_record", return_value={"id": "artificial-host"}), \
                patch.object(controller, "git", return_value="a" * 40), \
                patch.object(controller, "claim", return_value=("d" * 40, root / "benchmarks/reports/claim.json")), \
                patch.object(controller, "snapshot"), patch.object(controller, "publish", side_effect=publish), \
                patch.object(controller, "prepare", return_value=(root / "unused.parquet", root / "cache")), \
                patch.object(controller, "execute", side_effect=execute), patch.object(c, "assess", side_effect=assess) as audit:
            code = controller.run(args)
        return code, published, commands, audit

    def test_every_stage_is_durable_before_next_and_source_mapping_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            code, published, commands, audit = self.run_fake_flow(Path(temporary))
        self.assertEqual(code, 0)
        self.assertEqual(len(commands), 8)
        self.assertEqual(published[-1]["status"], "complete-verified")
        self.assertEqual(len(published[-1]["assessment_outputs"]), 2)
        audit.assert_called_once()
        for command in commands:
            stage = command[command.index("--stage") + 1]
            if stage == "export" or stage.startswith("baseline-"):
                self.assertTrue(command[command.index("--source") + 1].endswith("/baseline/src"))
            elif stage.startswith("candidate-"):
                self.assertTrue(command[command.index("--source") + 1].endswith("/candidate/src"))
            else:
                self.assertNotIn("--source", command)
            self.assertNotIn("--model-dir", command)

    def test_interruption_keeps_incomplete_ledger_and_prevents_later_scoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, published, commands, audit = self.run_fake_flow(root, interrupted=True)
            self.assertEqual(code, 2)
            self.assertEqual(len(commands), 1)
            audit.assert_not_called()
            checkpoint = published[-1]
            self.assertEqual(checkpoint["status"], "failed-incomplete")
            record = checkpoint["stages"]["export"]
            self.assertEqual(record["status"], "interrupted")
            output = next(iter(record["outputs"]))
            self.assertEqual(gzip.decompress((root / output).read_bytes()),
                             b'{"event":"started","id":"artificial-controller-only"}\n')

    def test_partial_raw_ledger_is_not_repaired_or_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            state.mkdir()
            raw = b'{"event":"started","id":"artificial"}\n{"event":"fin'
            (state / "attempts.jsonl").write_bytes(raw)
            prefix = Path(temporary) / "public/candidate-native"
            c.save_ledger(state, prefix)
            self.assertEqual(gzip.decompress(c.public_paths(prefix)[2].read_bytes()), raw)
            (state / "attempts.jsonl").write_bytes(raw + b"changed")
            with self.assertRaisesRegex(ValueError, "Never replace"):
                c.save_ledger(state, prefix)


if __name__ == "__main__":
    unittest.main()
