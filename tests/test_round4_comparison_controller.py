"""Fake-flow and local bare-Git tests; no source cohort, model or remote calls."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round4_comparison as c
from scripts import run_round4_comparison as controller
from scripts import freeze_round4_validation as preparation


class RoundFourControllerTests(unittest.TestCase):
    def environment(self):
        return {"GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book", "GITHUB_REF": controller.TRIGGER,
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_NAME": "push",
            "GITHUB_SHA": "a" * 40, "ORT_DISABLE_TELEMETRY": "1"}

    def test_only_authorized_first_push_attempt_can_run(self):
        good = self.environment()
        with patch.dict(os.environ, good, clear=True):
            self.assertEqual(controller.actions_identity(), "123-1")
        for field, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_REPOSITORY", "another/repo"),
                             ("GITHUB_REF", "refs/heads/main"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                             ("ORT_DISABLE_TELEMETRY", "0")):
            with self.subTest(field=field), patch.dict(os.environ, {**good, field: value}, clear=True):
                with self.assertRaises(ValueError):
                    controller.actions_identity()

    def run_fake_flow(self, root, *, interrupted):
        binding = {"optional_project_statistics": False,
            "baseline": {"commit": "b" * 40}, "candidate": {"commit": "c" * 40}}
        declaration = {"protocol": "fixture"}
        binding_path, manifest_path, plan_path = root / "binding.json", root / "manifest.json", root / "plan.json"
        binding_path.write_text(json.dumps(binding))
        manifest_path.write_text(json.dumps({"binding_sha256": c.file_sha(binding_path)}))
        plan_path.write_text("{}")
        args = SimpleNamespace(binding=binding_path, manifest=manifest_path, wall_time_seconds=1000)
        published, commands = [], []
        def publish(checkpoint_path, _results, _binding, _parent, _run):
            published.append(json.loads(checkpoint_path.read_bytes()))
            return str(len(published)).zfill(40)
        def execute(command, _timeout, _log):
            commands.append(command)
            stage = command[command.index("--stage") + 1]
            intent = str(len(published)).zfill(40)
            running = published[-1]["stages"][stage]
            self.assertEqual(running["status"], "running")
            self.assertNotIn("execution_intent", running)
            self.assertEqual(command, [*running["argv"], "--execution-intent", intent])
            state = Path(command[command.index("--state") + 1])
            prefix = Path(command[command.index("--output") + 1])
            state.mkdir(parents=True)
            (state / "attempts.jsonl").write_text('{"event":"started","id":"invented"}\n')
            if interrupted:
                raise TimeoutError("fabricated process termination")
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
            result_dir = root / checkpoint["result_directory"]
            (result_dir / "assessment.json").write_text('{"status":"complete-verified"}')
            (result_dir / "report.md").write_text("invented controller flow only")
            return {"status": "complete-verified"}
        with patch.dict(os.environ, self.environment(), clear=True), patch.object(controller, "ROOT", root), \
                patch.object(c, "ROOT", root), patch.object(c, "PLAN", plan_path), \
                patch.object(c, "frozen_inputs", return_value=(declaration, binding)), \
                patch("scripts.round4_data.registered_inputs"), patch.object(c, "require_committed"), \
                patch.object(c, "host_record", return_value={"id": "host-fixture"}), \
                patch.object(controller, "git", return_value="a" * 40), \
                patch.object(controller, "claim", return_value=("d" * 40, root / "benchmarks/reports/claim.json")), \
                patch.object(controller, "snapshot"), patch.object(controller, "publish", side_effect=publish), \
                patch.object(controller, "prepare", return_value=(root / "unused.parquet", root / "cache", root / "model")), \
                patch.object(controller, "execute", side_effect=execute), patch.object(c, "assess", side_effect=assess) as audit:
            code = controller.run(args)
        return code, published, commands, audit

    def test_timeout_preserves_partial_ledger_and_stops_later_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, published, commands, audit = self.run_fake_flow(root, interrupted=True)
            self.assertEqual(code, 2)
            self.assertEqual(len(commands), 1)
            audit.assert_not_called()
            checkpoint = published[-1]
            self.assertEqual(checkpoint["status"], "failed-incomplete")
            self.assertEqual(checkpoint["stages"]["export"]["status"], "interrupted")
            output = next(iter(checkpoint["stages"]["export"]["outputs"]))
            self.assertTrue(output.endswith(".attempts.jsonl.gz"))
            self.assertEqual(gzip.decompress((root / output).read_bytes()), b'{"event":"started","id":"invented"}\n')

    def test_every_worker_is_durable_before_next_and_exact_source_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            code, published, commands, audit = self.run_fake_flow(Path(directory), interrupted=False)
            self.assertEqual(code, 0)
            self.assertEqual(len(commands), 10)
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
                self.assertEqual(command[command.index("--execution-claim") + 1], "d" * 40)
                self.assertEqual(published[-1]["stages"][stage]["execution_intent"],
                                 command[command.index("--execution-intent") + 1])

    def test_git_claim_and_publication_exclude_unrelated_staged_or_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root, remote = Path(directory) / "repo", Path(directory) / "remote.git"
            root.mkdir()
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            git("init", "--bare", str(remote))
            git("init")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (root / "README").write_text("fixture input")
            git("add", "README")
            git("commit", "-m", "input")
            source = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote))
            binding_path, manifest = root / "binding.json", root / "manifest.json"
            binding_path.write_text("fixture binding")
            manifest.write_text("fixture manifest")
            (root / "user-staged.txt").write_text("must stay out of publication")
            git("add", "user-staged.txt")
            with patch.object(controller, "ROOT", root), patch.object(c, "ROOT", root), \
                    patch.object(controller, "actions_identity", return_value="123-1"), \
                    patch.object(controller, "authorized_origin"):
                claim, _ = controller.claim(binding_path, source, "123-1", manifest)
                self.assertEqual(git("rev-parse", "HEAD"), source)
                record = c.verify_claim(claim, binding_path, manifest, source, "123-1", published=True)
                self.assertEqual(record["status"], "claimed-before-preparation")
                with self.assertRaisesRegex(ValueError, "identity differs"):
                    c.verify_claim(claim, binding_path, manifest, source, "another-run")
                manifest.write_text("changed manifest")
                with self.assertRaisesRegex(ValueError, "identity differs"):
                    c.verify_claim(claim, binding_path, manifest, source, "123-1")
                manifest.write_text("fixture manifest")
                with self.assertRaisesRegex(ValueError, "already has an execution claim"):
                    controller.claim(binding_path, source, "123-1", manifest)
                with patch.object(controller, "actions_identity", return_value="124-1"):
                    with self.assertRaisesRegex(ValueError, "already has an execution claim"):
                        controller.claim(binding_path, source, "124-1", manifest)
                cp = root / "benchmarks/reports/round4-comparison-123-1-checkpoint.json"
                cp.write_text("{}")
                result = root / "benchmarks/results/round4-comparison-123-1"
                result.mkdir(parents=True)
                for path in c.public_paths(result / "export"):
                    path.write_bytes(b"source-free fixture")
                (result / "private-source.txt").write_text("not an allowed output")
                (result / "not-a-stage.json.gz").write_bytes(b"not allowed")
                commit = controller.publish(cp, result, {"optional_project_statistics": False}, claim, "123-1")
                names = set(git("ls-tree", "-r", "--name-only", commit).splitlines())
                self.assertNotIn("user-staged.txt", names)
                self.assertNotIn(str((result / "private-source.txt").relative_to(root)), names)
                self.assertNotIn(str((result / "not-a-stage.json.gz").relative_to(root)), names)
                self.assertTrue(all(str(path.relative_to(root)) in names for path in c.public_paths(result / "export")))
                self.assertIn("user-staged.txt", git("diff", "--cached", "--name-only"))
                with self.assertRaisesRegex(ValueError, "Another writer advanced"):
                    controller.publish(cp, result, {"optional_project_statistics": False}, claim, "123-1")

    def test_ledger_preserves_incomplete_last_line_without_inventing_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            state.mkdir()
            raw = b'{"event":"started","id":"invented"}\n{"event":"fin'
            (state / "attempts.jsonl").write_bytes(raw)
            prefix = Path(directory) / "public" / "candidate-native"
            info = c.save_ledger(state, prefix)
            self.assertEqual(gzip.decompress(c.public_paths(prefix)[2].read_bytes()), raw)
            self.assertEqual(info["raw_sha256"], c.sha(raw))
            (state / "attempts.jsonl").write_bytes(raw + b"more")
            with self.assertRaisesRegex(ValueError, "Never replace"):
                c.save_ledger(state, prefix)

    def test_scored_worker_requires_claim_before_reading_selected_source(self):
        args = SimpleNamespace(binding=Path("unused-binding"), manifest=Path("unused-manifest"),
                               execution_claim=None)
        with patch.dict(os.environ, self.environment(), clear=True), \
                patch.object(c, "frozen_inputs", return_value=({}, {})), \
                patch.object(c, "git", return_value=("a" * 40 + "\n").encode()), \
                patch("scripts.round4_data.load") as load:
            with self.assertRaisesRegex(ValueError, "Missing exact execution claim"):
                c.worker(args)
            load.assert_not_called()

    def worker_args(self, root, stage="candidate-native"):
        private = root / ".artifacts/round4-comparison/123-1"
        return SimpleNamespace(stage=stage,
            binding=root / "benchmarks/experiments/round4-validation-binding.json",
            manifest=root / "benchmarks/experiments/round4-hotpot256-manifest.json",
            state=private / "states" / stage,
            output=root / "benchmarks/results/round4-comparison-123-1" / stage,
            bundle=private / "frozen-pages.json", frozen_db=private / "states/export/frozen.db",
            data=private / "private/hotpot-dev-distractor.parquet", cache=private / "cache",
            model_dir=private / "semantic-model", source=private / "candidate/src",
            host_id="host-fixture", execution_claim="d" * 40, execution_intent="e" * 40)

    def intent(self, args):
        binding = {"optional_project_statistics": False}
        order = c.stages(binding)
        value = {"schema_version": 1, "protocol": "fixture", "run_id": "123-1",
            "source_commit": "a" * 40, "claim_commit": args.execution_claim,
            "host": {"id": args.host_id}, "plan_sha256": "1" * 64,
            "binding_sha256": "2" * 64, "cohort_manifest_sha256": "3" * 64,
            "result_directory": "benchmarks/results/round4-comparison-123-1",
            "status": "running", "stages": {}}
        for stage in order[:order.index(args.stage)]:
            value["stages"][stage] = {"status": "completed", "exit_code": 0}
        value["stages"][args.stage] = {"status": "running", "argv": c.worker_command(args)}
        return value, binding

    def test_fresh_alternate_worker_paths_cannot_reuse_a_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for field in ("state", "output", "bundle", "frozen_db", "data", "cache", "model_dir", "source"):
                args = self.worker_args(root)
                setattr(args, field, root / "alternate" / (args.stage if field == "output" else field))
                with self.subTest(field=field), patch.dict(os.environ, self.environment(), clear=True), \
                        patch.object(c, "ROOT", root), \
                        patch.object(c, "frozen_inputs", return_value=({"protocol": "fixture"},
                            {"optional_project_statistics": False})), \
                        patch.object(c, "git", return_value=("a" * 40 + "\n").encode()), \
                        patch.object(c, "verify_claim"), patch.object(c, "verify_intent") as intent, \
                        patch.object(c, "verify_model") as model, patch("scripts.round4_data.load") as load:
                    with self.assertRaisesRegex(ValueError, "canonical " + field):
                        c.worker(args)
                    intent.assert_not_called()
                    model.assert_not_called()
                    load.assert_not_called()

    def test_running_stage_intent_has_exact_order_arguments_and_published_tip(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.worker_args(Path(directory))
            original, binding = self.intent(args)
            record = copy.deepcopy(original)
            remote = "e" * 40
            calls = []

            def git(*values):
                calls.append(values)
                if values[0] == "show":
                    return json.dumps(record).encode()
                if values[0] == "merge-base":
                    self.assertEqual(values, ("merge-base", "--is-ancestor", "d" * 40, "e" * 40))
                    return b""
                if values[0] == "ls-remote":
                    return (remote + "\trefs/heads/validation/round4-comparison-123-1\n").encode()
                raise AssertionError("Unexpected Git read")

            with patch.object(c, "git", side_effect=git):
                self.assertEqual(c.verify_intent("e" * 40, original, args.stage, binding,
                    argv=c.worker_command(args), published=True), original)
                for change in (
                    lambda value: value.update(claim_commit="f" * 40),
                    lambda value: value.update(status="complete-verified"),
                    lambda value: value["stages"].pop("baseline-native"),
                    lambda value: value["stages"]["export"].update(status="failed", exit_code=2),
                    lambda value: value["stages"][args.stage].update(status="completed", exit_code=0),
                    lambda value: value["stages"][args.stage]["argv"].append("--altered"),
                ):
                    record = copy.deepcopy(original)
                    change(record)
                    with self.assertRaises(ValueError):
                        c.verify_intent("e" * 40, original, args.stage, binding,
                            argv=c.worker_command(args), published=True)
                record = copy.deepcopy(original)
                remote = "f" * 40
                with self.assertRaisesRegex(ValueError, "current published checkpoint"):
                    c.verify_intent("e" * 40, original, args.stage, binding,
                        argv=c.worker_command(args), published=True)
                calls.clear()
                c.verify_intent("e" * 40, original, args.stage, binding,
                    argv=c.worker_command(args), published=False)
                self.assertFalse(any(call[0] == "ls-remote" for call in calls))

    def test_missing_or_stale_intent_stops_worker_before_private_data_or_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.worker_args(root)
            plan = root / "plan.json"
            for path in (plan, args.binding, args.manifest):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}")
            record, binding = self.intent(args)
            record.update(plan_sha256=c.file_sha(plan), binding_sha256=c.file_sha(args.binding),
                          cohort_manifest_sha256=c.file_sha(args.manifest))

            def git(*values):
                if values[0] == "rev-parse":
                    return ("a" * 40 + "\n").encode()
                if values[0] == "show":
                    return json.dumps(record).encode()
                if values[0] == "merge-base":
                    return b""
                if values[0] == "ls-remote":
                    return ("f" * 40 + "\trefs/heads/validation/round4-comparison-123-1\n").encode()
                raise AssertionError("Unexpected Git read")

            with patch.dict(os.environ, self.environment(), clear=True), patch.object(c, "ROOT", root), \
                    patch.object(c, "PLAN", plan), \
                    patch.object(c, "frozen_inputs", return_value=({"protocol": "fixture"}, binding)), \
                    patch.object(c, "git", side_effect=git), patch.object(c, "verify_claim"), \
                    patch.object(c, "verify_model") as model, patch("scripts.round4_data.load") as load:
                args.execution_intent = None
                with self.assertRaisesRegex(ValueError, "Missing exact running-stage intent"):
                    c.worker(args)
                args.execution_intent = "e" * 40
                with self.assertRaisesRegex(ValueError, "current published checkpoint"):
                    c.worker(args)
                model.assert_not_called()
                load.assert_not_called()
                self.assertFalse(args.state.exists())

    def test_preparation_requires_exact_candidate_and_forbids_declared_override(self):
        plan = json.loads(preparation.PLAN.read_bytes())
        pending = {**plan, "candidate_commit": None, "candidate_runtime_sha256": None}
        missing = SimpleNamespace(candidate_commit=None, candidate_runtime_sha256=None)
        with self.assertRaisesRegex(ValueError, "exact accepted candidate"):
            preparation.requested_sources(pending, missing)
        explicit = SimpleNamespace(candidate_commit="b" * 40, candidate_runtime_sha256="c" * 64)
        resolved = preparation.requested_sources(pending, explicit)
        self.assertEqual(resolved["candidate_commit"], explicit.candidate_commit)
        self.assertEqual(resolved["candidate_runtime_sha256"], explicit.candidate_runtime_sha256)
        self.assertEqual(preparation.requested_sources(resolved, missing), resolved)
        with self.assertRaisesRegex(ValueError, "CLI candidate differs"):
            preparation.requested_sources(resolved,
                SimpleNamespace(candidate_commit="d" * 40, candidate_runtime_sha256="c" * 64))


if __name__ == "__main__":
    unittest.main()
