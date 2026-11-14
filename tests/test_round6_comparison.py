"""Artificial inputs and fake controller flows; no fresh data, model or scoring."""
import copy
from contextlib import ExitStack
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round6_comparison as c
from scripts import round6_comparison_controller as controller
from scripts import round6_comparison_data as data
from scripts.smoke_round2_components import fixture


class ArtificialCounter:
    version = "0.12.0"

    def __init__(self, name):
        self.name = name

    def count(self, text):
        return len(text)


class ArtificialHybrid:
    """Two invented pages, fixed artificial durations, no binary or inference."""
    def __init__(self, bundle, empty=False):
        self.documents = {doc["project"]: doc for doc in bundle["documents"]}
        self.empty, self.searches, self.reads, self.closed = empty, [], [], False
        lock = json.loads((c.ROOT / c.UPSTREAM_LOCKS["ai-memory"]).read_bytes())
        self.metadata = {"commit": lock["commit"], "binary_sha256": lock["binary_sha256"],
            "embedding_provider": "local", "embedding_model": {"files": lock["embedding_model"]["files"]}}

    def search(self, query, project, limit):
        self.searches.append((project, limit))
        doc = self.documents[project]
        rows = [] if self.empty else [{"id": "metadata-" + project, "project": project, "workspace": "benchmark"},
                                     {"id": "native-" + doc["id"], "project": project, "workspace": "benchmark"}]
        elapsed = 2.0 if project.endswith("a") else 20.0
        return {"search_ms": elapsed, "bridge_ms": elapsed,
                "hit_ids": [] if self.empty else [None, doc["id"]], "results": rows,
                "native_payload": {"content": rows}, "native_text": "artificial snippet and metadata"}

    def read(self, identity):
        self.reads.append(identity)
        doc = next(doc for doc in self.documents.values() if doc["id"] == identity)
        return {"result": {"body": doc["text"], "truncated": False}, "native_text": doc["text"],
                "native_payload": {"text": doc["text"], "id": identity},
                "read_ms": 10.0 if identity.endswith("a") else 1.0}

    def close(self):
        self.closed = True


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

    def test_receipt_requires_all_six_assets_and_rejects_model_or_question_drift(self):
        sources = {"baseline": c.BASELINE, "candidate": {"commit": "c" * 40, "source_sha256": "d" * 64}}
        locks = {name: c.file_sha(c.ROOT / path) for name, path in c.UPSTREAM_LOCKS.items()}
        receipt = {"schema_version": 1, "status": "all-assets-verified-before-selection", "sources": sources,
            "packages": c.PACKAGES, "upstream_locks_sha256": locks, "model": c.model_identity(),
            "optional_semantic": False, "question_content_read": False, "measurement_calls": 0,
            "language_runtimes": {"python": "3.12.16", "node": c.NODE},
            "preparation": {name: {"status": "completed"} for name in
                ("baseline_source", "candidate_source", "reference_tokenizers", "ai_memory_binary_and_models",
                 "claude_mem_sources_and_bun", "billion_kernel_sources")}}
        c.verify_asset_receipt(receipt, sources, locks)
        for key, value in (("question_content_read", True), ("measurement_calls", 1),
                           ("optional_semantic", True), ("model", {})):
            changed = copy.deepcopy(receipt)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.verify_asset_receipt(changed, sources, locks)
        for action in ("remove", "fail", "later-parquet"):
            changed = copy.deepcopy(receipt)
            if action == "remove":
                changed["preparation"].pop("ai_memory_binary_and_models")
            elif action == "fail":
                changed["preparation"]["ai_memory_binary_and_models"]["status"] = "failed"
            else:
                changed["preparation"]["verified_parquet_download"] = {"status": "completed"}
            with self.subTest(action=action), self.assertRaises(ValueError):
                c.verify_asset_receipt(changed, sources, locks)

    def artificial_component(self, directory, empty=False):
        dataset, bundle = fixture()
        engine = ArtificialHybrid(bundle, empty=empty)
        report = {"stage": "ai-memory-hybrid", "evaluator": c.VERSION, "protocol": c.PROTOCOL,
                  "timing_rows": [], "configurations": []}
        path = Path(directory) / "attempts.jsonl"
        ledger = c.reused.Ledger(path)
        binding = {**self.binding(), "upstream_locks": c.UPSTREAM_LOCKS}
        with patch.object(c.legacy, "TokenCounter", ArtificialCounter), \
                patch.object(c.legacy, "component_engine", return_value=(engine, None)), \
                patch.object(c.legacy, "registered_plan", side_effect=AssertionError("old plan must not execute")), \
                patch.object(c.legacy, "frozen_inputs", side_effect=AssertionError("old freeze must not execute")), \
                patch.object(c.legacy.time, "perf_counter_ns", side_effect=range(1000, 1000000, 1000)):
            c.component(SimpleNamespace(stage="ai-memory-hybrid"), self.plan(), binding, dataset, bundle,
                        report, ledger, SimpleNamespace(set_phase=lambda _: None))
        ledger.close()
        report.update(status="completed", resources={"sampling_interval_ms": 20, "samples": {"setup": 1, "queries": 1},
            "sampled_process_tree_peak_rss_bytes": {"setup": 1024, "queries": 2048}},
            ledger_sha256=c.file_sha(path), attempts_started=ledger.started, attempts_finished=ledger.finished,
            attempt_states=[json.loads(line) for line in path.read_text().splitlines()])
        c.verify_report(report, self.plan(), binding, [case.id for case in dataset.queries])
        return report, engine, binding, [case.id for case in dataset.queries]

    def test_new_plan_preserves_metadata_slots_separate_reads_and_all_projections(self):
        with tempfile.TemporaryDirectory() as temporary:
            report, engine, binding, ids = self.artificial_component(temporary)
            self.assertEqual(len(engine.searches), 6)
            self.assertEqual(len(engine.reads), 2)
            self.assertTrue(engine.closed)
            self.assertEqual(len(report["configurations"]), 6)
            self.assertTrue(all(row["native_hit_ids"][0] is None for row in report["timing_rows"]))
            self.assertEqual(report["native_costs"]["unmapped_native_hits"], 2)
            self.assertEqual(report["first_pass_search_plus_all_reads_latency"], c.legacy.latency_summary([12.0, 21.0]))
            self.assertNotEqual(report["first_pass_search_plus_all_reads_latency"]["p95_ms"],
                c.legacy.latency_summary([2.0, 20.0])["p95_ms"] + c.legacy.latency_summary([10.0, 1.0])["p95_ms"])
            changed = copy.deepcopy(report)
            changed["timing_rows"][0]["read_calls"] = 0
            with self.assertRaises(ValueError):
                c.verify_report(changed, self.plan(), binding, ids)
            changed = copy.deepcopy(report)
            changed["configurations"][0]["packing_samples"][0]["row_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                c.verify_report(changed, self.plan(), binding, ids)
            changed = copy.deepcopy(report)
            changed["attempt_states"].pop()
            with self.assertRaises(ValueError):
                c.verify_report(changed, self.plan(), binding, ids)

    def test_empty_results_and_adverse_comparisons_are_not_omitted(self):
        with tempfile.TemporaryDirectory() as before_dir, tempfile.TemporaryDirectory() as after_dir:
            before, _, _, _ = self.artificial_component(before_dir)
            after, engine, _, _ = self.artificial_component(after_dir, empty=True)
        self.assertEqual(len(engine.searches), 6)
        self.assertEqual(engine.reads, [])
        self.assertTrue(all(row["metrics"]["complete_evidence_rate"] == 0 for row in after["configurations"]))
        changes = c.comparisons(before, after)
        self.assertEqual(len(changes), 6)
        self.assertTrue(all(len(row["complete_question_losses"]) == 2
                            and row["complete_question_gains"] == [] for row in changes))

    def test_actual_git_claim_cannot_repeat_or_publish_private_staged_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, remote = Path(temporary) / "repo", Path(temporary) / "remote.git"
            root.mkdir()

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()

            git("init", "--bare", str(remote))
            git("init")
            git("config", "user.name", "Artificial fixture")
            git("config", "user.email", "fixture@example.invalid")
            (root / "README").write_text("Artificial local Git only")
            git("add", "README")
            git("commit", "-m", "fixture")
            source = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote))
            binding, manifest = root / "binding.json", root / "manifest.json"
            binding.write_text("artificial binding")
            manifest.write_text("artificial manifest")
            (root / "unrelated-staged.txt").write_text("must never enter a checkpoint")
            git("add", "unrelated-staged.txt")
            with patch.object(controller, "ROOT", root), patch.object(c, "ROOT", root), \
                    patch.object(controller, "actions_identity", return_value="123-1"), \
                    patch.object(controller, "authorized_origin"):
                claim, _ = controller.claim(binding, source, "123-1", manifest)
                self.assertEqual(git("rev-parse", "HEAD"), source)
                c.verify_claim(claim, binding, manifest, source, "123-1", published=True)
                with self.assertRaisesRegex(ValueError, "already has an execution claim"):
                    controller.claim(binding, source, "123-1", manifest)
                with self.assertRaisesRegex(ValueError, "identity differs"):
                    c.verify_claim(claim, binding, manifest, source, "124-1")
                checkpoint = root / "benchmarks/reports/round6-comparison-123-1-checkpoint.json"
                checkpoint.write_text("{}")
                results = root / "benchmarks/results/round6-comparison-123-1"
                results.mkdir(parents=True)
                for path in c.public_paths(results / "export"):
                    path.write_bytes(b"artificial source-free evidence")
                (results / "private-source.txt").write_text("must not be published")
                committed = controller.publish(checkpoint, results, self.binding(), claim, "123-1")
                names = set(git("ls-tree", "-r", "--name-only", committed).splitlines())
                self.assertNotIn("unrelated-staged.txt", names)
                self.assertNotIn(str((results / "private-source.txt").relative_to(root)), names)
                self.assertIn("unrelated-staged.txt", git("diff", "--cached", "--name-only"))
                with self.assertRaisesRegex(ValueError, "Another writer advanced"):
                    controller.publish(checkpoint, results, self.binding(), claim, "123-1")

    def test_actual_git_binding_and_manifest_commits_are_separate_and_ordered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, remote = Path(temporary) / "repo", Path(temporary) / "remote.git"
            root.mkdir()

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()

            git("init", "--bare", str(remote))
            git("init")
            git("config", "user.name", "Artificial fixture")
            git("config", "user.email", "fixture@example.invalid")
            prior = self.historical_manifests()
            hashes = {}
            for name, value in zip(c.PRIOR_MANIFESTS, prior, strict=True):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))
                hashes[name] = c.file_sha(path)
            plan_path = root / "benchmarks/experiments/plan.json"
            plan_path.write_text("{}")
            git("add", "benchmarks")
            git("commit", "-m", "artificial historical inputs and evaluator")
            evaluator = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote))
            binding_path = root / "benchmarks/experiments/binding.json"
            manifest_path = root / "benchmarks/experiments/manifest.json"
            binding = {**self.binding(), "evaluator_commit": evaluator, "evaluator_files": hashes}
            binding_path.write_text(json.dumps(binding))

            def frozen(path):
                c.require_committed(path)
                return {}, binding

            with patch.object(c, "ROOT", root), patch.object(controller, "ROOT", root), \
                    patch.object(c, "PLAN", plan_path), patch.object(c, "BINDING", binding_path), \
                    patch.object(c, "MANIFEST", manifest_path), patch.object(c, "BASELINE", {"commit": evaluator}), \
                    patch.object(c, "frozen_inputs", side_effect=frozen):
                binding_commit = controller.commit_and_publish([binding_path], "fixture-freeze", evaluator, "bind")
                inputs = data.registered_inputs(binding_path)
                self.assertEqual(inputs.binding_commit, binding_commit)
                self.assertNotEqual(binding_commit, evaluator)
                self.assertEqual(git("rev-parse", "HEAD"), binding_commit)
                ids = [f"artificial-fresh-{index}" for index in range(256)]
                value = {"binding_sha256": c.file_sha(binding_path), "plan_sha256": c.file_sha(plan_path),
                    "binding_commit": binding_commit, "evaluator_commit": evaluator,
                    "sources": {key: binding[key] for key in ("baseline", "candidate")},
                    "prior_manifest_sha256": hashes, "excluded_prior_queries": 896,
                    "prior_selection_overlap": 0, "expected_queries": 256, "unique_selected_ids": 256,
                    "selected_ids": ids, "selected_ids_sha256": c.reused.digest(ids)}
                manifest_path.write_text(json.dumps(value))
                with self.assertRaises(subprocess.CalledProcessError):
                    data.committed_manifest(binding_path, manifest_path)
                manifest_commit = controller.commit_and_publish([manifest_path], "fixture-freeze", binding_commit, "IDs")
                self.assertEqual(data.committed_manifest(binding_path, manifest_path)[1], value)
                self.assertNotEqual(manifest_commit, binding_commit)
                self.assertEqual(git("rev-parse", "HEAD"), manifest_commit)
                self.assertEqual(git("merge-base", binding_commit, manifest_commit), binding_commit)
                with patch.object(c, "frozen_inputs", return_value=({}, {**binding, "evaluator_commit": binding_commit})):
                    with self.assertRaisesRegex(ValueError, "separate binding commit"):
                        data.registered_inputs(binding_path)

    def test_freeze_publishes_six_asset_receipt_before_binding_and_id_selection(self):
        plan = self.plan()
        plan["candidate"].update(commit="c" * 40, runtime_sha256="d" * 64)
        sources = {"baseline": c.BASELINE, "candidate": c.requested_candidate(plan)}
        model = c.model_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "benchmarks/experiments/plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan))
            binding, manifest = plan_path.with_name("binding.json"), plan_path.with_name("manifest.json")
            (root / "benchmarks/hotpot_manifest.json").write_text(json.dumps({"source_url": "unused",
                "upstream_sha256": "unused", "upstream_bytes": 0}))
            for name in c.UPSTREAM_LOCKS.values():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("artificial locked asset identity")
            head, events, published = ["a" * 40], [], {}
            receipt_path = root / "benchmarks/reports/round6-comparison-freeze-123-1/asset-verification.json"

            def git(*args, **kwargs):
                if args[:2] == ("rev-parse", "HEAD"):
                    return head[0]
                if args[:2] == ("update-ref", "HEAD"):
                    self.assertEqual(head[0], args[3])
                    head[0] = args[2]
                return ""

            def publish(paths, branch, parent, message):
                self.assertEqual(parent, head[0])
                head[0] = f"{len(events) + 10:040x}"
                for path in paths:
                    published[path] = (head[0], path.read_bytes())
                events.append(("commit", tuple(path.name for path in paths)))
                return head[0]

            def assets(cache, tokenizers, measured):
                for name in ("reference_tokenizers", "ai_memory_binary_and_models",
                             "claude_mem_sources_and_bun", "billion_kernel_sources"):
                    measured(name, lambda: None, cache / name)

            def bind(args):
                self.assertEqual(args.evaluator_commit, published[receipt_path][0])
                self.assertEqual(len(json.loads(published[receipt_path][1])["preparation"]), 6)
                events.append(("bind",))
                binding.write_text("artificial frozen binding")

            def download(url, path, *unused):
                self.assertIn(binding, published)
                events.append(("parquet",))
                path.write_bytes(b"artificial placeholder; never parsed")

            def select(*args):
                self.assertEqual(receipt_path.read_bytes(), published[receipt_path][1])
                self.assertEqual(len(json.loads(receipt_path.read_bytes())["preparation"]), 6)
                progress = json.loads(receipt_path.with_name("completion.json").read_bytes())
                self.assertEqual(len(progress["stages"]), 7)
                self.assertEqual(progress["stages"]["verified_parquet_download"]["status"], "completed")
                events.append(("select",))
                value = {"expected_queries": 256, "excluded_prior_queries": 896,
                    "prior_selection_overlap": 0, "selected_ids_sha256": "e" * 64}
                manifest.write_text(json.dumps(value))
                return value

            def load(*args):
                self.assertIn(manifest, published)
                self.assertNotEqual(published[manifest][0], published[binding][0])
                self.assertEqual(receipt_path.read_bytes(), published[receipt_path][1])
                events.append(("validate-committed-manifest",))

            with ExitStack() as stack:
                for replacement in (
                    patch.object(controller, "ROOT", root), patch.object(c, "ROOT", root),
                    patch.object(c, "PLAN", plan_path), patch.object(c, "BINDING", binding),
                    patch.object(c, "MANIFEST", manifest), patch.object(c, "registered_plan", return_value=plan),
                    patch.object(c, "runtime_hash", side_effect=lambda commit: next(v["source_sha256"] for v in sources.values() if v["commit"] == commit)),
                    patch.object(c, "source_identity", side_effect=lambda path: sources[path.parent.name]),
                    patch.object(c, "model_identity", return_value=model), patch.object(c, "bind", side_effect=bind),
                    patch.object(c, "frozen_inputs"), patch.object(controller, "authorized_origin"),
                    patch.object(controller, "git", side_effect=git), patch.object(controller, "commit_and_publish", side_effect=publish),
                    patch.object(controller, "freeze_claim", return_value=("b" * 40, root / "benchmarks/reports/claim.json")),
                    patch.object(controller, "snapshot"), patch.object(controller, "prepare_assets", side_effect=assets),
                    patch.object(controller, "checked_download", side_effect=download),
                    patch.object(data, "freeze", side_effect=select), patch.object(data, "load", side_effect=load),
                    patch.object(controller.importlib.metadata, "version", side_effect=lambda name: c.PACKAGES[name]),
                    patch.object(controller.subprocess, "check_output", return_value=c.NODE.encode()),
                    patch.object(controller.sys, "version_info", (3, 12)), patch.object(controller.sys, "version", "3.12.16 artificial"),
                    patch.object(controller.time, "perf_counter_ns", side_effect=range(1000, 1000000, 1000)),
                    patch.dict(os.environ, self.environment("freeze"), clear=True)):
                    stack.enter_context(replacement)
                self.assertEqual(controller.freeze(SimpleNamespace()), 0)
            labels = [row[0] for row in events]
            self.assertLess(labels.index("bind"), labels.index("parquet"))
            self.assertLess(labels.index("parquet"), labels.index("select"))
            self.assertLess(labels.index("select"), labels.index("validate-committed-manifest"))

    def test_markdown_retains_every_adverse_cell_and_only_current_boundaries(self):
        with tempfile.TemporaryDirectory() as before_dir, tempfile.TemporaryDirectory() as after_dir:
            before, _, _, _ = self.artificial_component(before_dir)
            after, _, _, _ = self.artificial_component(after_dir, empty=True)
        reports = {"export": {}}
        for stage in (*c.NATIVE, *c.COMPONENTS):
            report = copy.deepcopy(after if stage.startswith("candidate-") else before)
            for row in report["configurations"]:
                row["latency"] = {"p50_ms": 1.0, "p95_ms": 2.0}
            reports[stage] = report
        changes = c.comparisons(before, after)
        assessment = {"validation": {"passed": True}, "run_id": "artificial-only", "native_calls": 3072,
            "component_search_calls": 3840, "default_payload_equivalence": {"passed": True},
            "sources": {"baseline": c.BASELINE, "candidate": {"commit": "c" * 40, "source_sha256": "d" * 64}},
            "upstream_identities": c.upstream_identities(), "binding_sha256": "e" * 64,
            "selected_ids_sha256": "f" * 64, "competitor_changes": {name: changes for name in
                ("claude-mem-fts", "ai-memory-hybrid", "billion-context")},
            "quality_cells": 42, "retrieval_and_search_calls": 6912, "ai_memory_page_read_calls": 2}
        rendered = c.markdown(assessment, reports)
        self.assertIn("excludes all 896 IDs", rendered)
        self.assertIn("Q2 is excluded", rendered)
        self.assertNotIn("640 IDs", rendered)
        self.assertNotIn("Round four", rendered)
        self.assertNotIn("index-vector digests match", rendered)
        self.assertEqual(rendered.count("| -100.0000 | 0 | 2 |"), 18)
        self.assertIn("no whole-product speed ratio follows", rendered)
        self.assertIn("10%/15%/10%", rendered)


if __name__ == "__main__":
    unittest.main()
