"""Preparation safety tests use temporary Git and invented data; no downloads."""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_round3_freeze as freeze


class RoundThreeFreezeTests(unittest.TestCase):
    def environment(self):
        return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": freeze.REPOSITORY,
            "GITHUB_REF": freeze.TRIGGER, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40, "ORT_DISABLE_TELEMETRY": "1"}

    def test_identity_fails_closed_and_second_attempt_is_forbidden(self):
        good = self.environment()
        with patch.dict(os.environ, good, clear=True):
            self.assertEqual(freeze.actions_identity(), "123-1")
        for key, value in (("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "other/repo"),
                           ("GITHUB_REF", "refs/heads/main"), ("GITHUB_RUN_ATTEMPT", "2"),
                           ("GITHUB_EVENT_NAME", "workflow_dispatch"), ("GITHUB_SHA", "main"),
                           ("GITHUB_RUN_ID", "../123"), ("ORT_DISABLE_TELEMETRY", "0")):
            with self.subTest(key=key), patch.dict(os.environ, {**good, key: value}, clear=True):
                with self.assertRaises(ValueError):
                    freeze.actions_identity()

    def test_existing_binding_or_manifest_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "binding.json", Path(directory) / "manifest.json"
            for path in (first, second):
                path.write_text("original")
                with self.assertRaisesRegex(ValueError, "no implicit replay"):
                    freeze.require_absent([first, second])
                self.assertEqual(path.read_text(), "original")
                path.unlink()
            second.symlink_to(Path(directory) / "missing-target")
            with self.assertRaises(ValueError):
                freeze.require_absent([second])

    def test_selection_requires_remote_and_committed_binding(self):
        binding = Path("unused-binding.json")
        with patch.object(freeze, "git", return_value="b" * 40), \
                patch.object(freeze, "remote_head", return_value="a" * 40), \
                patch.object(freeze.comparison, "require_committed") as committed, \
                patch.object(freeze.round3_data, "registered_inputs") as data:
            with self.assertRaisesRegex(ValueError, "confirm the binding remotely"):
                freeze.require_durable_binding(binding, "b" * 40, "123-1", "fixture")
            committed.assert_not_called()
            data.assert_not_called()
        with patch.object(freeze, "git", return_value="b" * 40), \
                patch.object(freeze, "remote_head", return_value="b" * 40), \
                patch.object(freeze.comparison, "require_committed", side_effect=ValueError("uncommitted")), \
                patch.object(freeze.round3_data, "registered_inputs") as data:
            with self.assertRaisesRegex(ValueError, "uncommitted"):
                freeze.require_durable_binding(binding, "b" * 40, "123-1", "fixture")
            data.assert_not_called()

    def test_helpers_never_inherit_publication_credentials(self):
        with patch.dict(os.environ, {"GH_TOKEN": "fixture-secret", "GITHUB_TOKEN": "another-fixture",
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_VALUE_0": "secret-header"}), \
                patch.object(freeze.subprocess, "run") as call:
            call.return_value.returncode = 0
            freeze.helper(["scripts/prepare_semantic_model.py", "--output", "unused"])
            env = call.call_args.kwargs["env"]
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("GITHUB_TOKEN", env)
            self.assertFalse(any(key.startswith("GIT_CONFIG_") for key in env))
            self.assertNotIn("fixture-secret", str(call.call_args.args))

    def test_recovery_inventory_and_rejected_gate_are_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "fixture.json.gz"
            data.write_bytes(b"invented public evidence")
            proof = {"status": "recovered-and-audited", "replayed_calls": 0, "frozen_audit_passed": True,
                "original_gzip_prefix_exact": True, "original_json_prefix_exact": True,
                "validation": {"passed": True, "workers": 8, "calls": 8082},
                "screening": {"qualified": False, "status": "rejected_loss_or_no_gain"},
                "files": {data.name: {"bytes": data.stat().st_size, "sha256": freeze.comparison.file_sha(data)}}}
            path = root / "recovery-proof.json"
            path.write_text(json.dumps(proof))
            files, decision = freeze.quality_disposition(root)
            self.assertEqual(set(files), {data, path})
            self.assertFalse(decision["qualified"])
            proof["screening"]["qualified"] = True
            path.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                freeze.quality_disposition(root)
            proof["screening"]["qualified"] = False
            path.write_text(json.dumps(proof))
            data.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                freeze.quality_disposition(root)

    def test_claim_cannot_repeat_and_publication_preserves_unrelated_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root, remote = Path(directory) / "repo", Path(directory) / "remote.git"
            root.mkdir()
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            git("init", "--bare", str(remote))
            git("init")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (root / "README").write_text("fixture")
            git("add", "README")
            git("commit", "-m", "fixture input")
            source = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote))
            (root / "unrelated.txt").write_text("never publish")
            git("add", "unrelated.txt")
            with patch.object(freeze, "ROOT", root), patch.object(freeze, "authorized_origin"), \
                    patch.object(freeze, "actions_identity", return_value="123-1"):
                parent = freeze.claim(source, "123-1", "fixture", "d" * 64)
                self.assertNotIn("unrelated.txt", git("ls-tree", "-r", "--name-only", parent))
                with self.assertRaisesRegex(ValueError, "already has a freeze claim"):
                    freeze.claim(source, "123-1", "fixture", "d" * 64)
                checkpoint = root / "benchmarks/reports/round3-freeze-123-1-checkpoint.json"
                checkpoint.write_text("{}")
                binding = root / "benchmarks/experiments/binding.json"
                binding.parent.mkdir(parents=True)
                binding.write_text("{}")
                commit = freeze.publish(checkpoint, [binding], parent, "123-1", "fixture")
                self.assertEqual(git("rev-parse", "HEAD"), commit)
                self.assertEqual(git("show", "HEAD:benchmarks/experiments/binding.json"), "{}")
                self.assertNotIn("unrelated.txt", git("ls-tree", "-r", "--name-only", commit))
                self.assertEqual((root / "unrelated.txt").read_text(), "never publish")
                with self.assertRaisesRegex(ValueError, "Another writer"):
                    freeze.publish(checkpoint, [binding], parent, "123-1", "fixture")

    def test_helper_failure_exposes_only_fixed_component_and_exit(self):
        with patch.object(freeze.subprocess, "run") as call, patch("sys.stderr", new_callable=io.StringIO) as output:
            call.return_value.returncode = 7
            call.return_value.stderr = b"private source and credential material"
            call.return_value.stdout = b"private model output"
            with self.assertRaises(ValueError):
                freeze.helper(["scripts/prepare_semantic_model.py", "--output", "private-argument"])
            diagnostic = json.loads(output.getvalue())
            self.assertEqual(diagnostic["helper"], "prepare_semantic_model.py")
            self.assertEqual(diagnostic["exit_code"], 7)
            self.assertNotIn("private", output.getvalue())
        with patch.object(freeze.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(["private-command"], 5, stderr=b"private-response")), \
                patch("sys.stderr", new_callable=io.StringIO) as output:
            with self.assertRaises(RuntimeError):
                freeze.helper(["scripts/prepare_semantic_model.py"], timeout=5)
            self.assertEqual(json.loads(output.getvalue())["status"], "timeout")
            self.assertNotIn("private", output.getvalue())

    def test_bootstrap_and_binding_are_published_before_selection_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / "benchmarks/experiments/round3-validation-binding.json"
            manifest = root / "benchmarks/experiments/round3-hotpot256-manifest.json"
            inventory = root / "benchmarks/experiments/round3-quality-recovery.json"
            plan = root / "plan.json"
            plan.write_text("{}")
            quality = root / freeze.QUALITY
            proof = quality / "recovery-proof.json"
            published, events = [], []
            current = ["a" * 40]
            def git(*args, **_):
                if args == ("rev-parse", "HEAD"):
                    return current[0]
                if args == ("rev-parse", "--show-toplevel"):
                    return str(root)
                if args == ("status", "--porcelain", "--untracked-files=no"):
                    return ""
                self.fail("Unexpected Git operation in artificial preparation flow")
            def committed(path):
                self.assertTrue(published)
                self.assertIn(path.relative_to(root).as_posix(), published[-1]["outputs_sha256"])
            def publish(checkpoint, outputs, parent, run, token):
                value = json.loads(checkpoint.read_bytes())
                self.assertEqual(set(value["outputs_sha256"]),
                                 {path.relative_to(root).as_posix() for path in outputs})
                published.append(value)
                current[0] = str(len(published)).zfill(40)
                return current[0]
            def helper(arguments, **_):
                component = arguments[0]
                if component == "scripts/bootstrap_round3_quality_manifest.py":
                    events.append("bootstrap")
                    inventory.parent.mkdir(parents=True)
                    inventory.write_text('{"fixture":"inventory"}')
                elif component == "-m":
                    committed(inventory)
                    events.append("quality-fixtures")
                elif component == "scripts/recover_round3_quality.py":
                    committed(inventory)
                    quality.mkdir(parents=True)
                    proof.write_text('{"fixture":"recovered-public-evidence"}')
                    events.append("recovery")
                elif component == "scripts/prepare_semantic_model.py":
                    committed(proof)
                    events.append("model-bytes")
                elif component == "scripts/round3_comparison.py":
                    committed(inventory)
                    committed(proof)
                    events.append("bind")
                    binding.write_text('{"fixture":"binding"}')
                else:
                    self.fail("Unexpected helper; no scoring or inference is allowed")
            def durable(path, parent, run, token):
                self.assertEqual(current[0], parent)
                committed(path)
                events.append("durable-binding")
            def download(_url, path, _hash, _bytes):
                committed(binding)
                events.append("parquet")
                path.parent.mkdir(parents=True)
                path.write_bytes(b"artificial, unscored input")
            def select(_data, frozen_binding, path):
                committed(frozen_binding)
                events.append("select")
                path.write_text('{"fixture":"selection"}')
            with patch.dict(os.environ, {**self.environment(), "GH_TOKEN": "fixture-token"}, clear=True), \
                    patch.object(freeze, "ROOT", root), patch.object(freeze.comparison, "BINDING", binding), \
                    patch.object(freeze.comparison, "MANIFEST", manifest), patch.object(freeze.comparison, "PLAN", plan), \
                    patch.object(freeze, "git", side_effect=git), patch.object(freeze, "authorized_origin"), \
                    patch.object(freeze, "remote_head", return_value=None), patch.object(freeze, "claim", return_value="c" * 40), \
                    patch.object(freeze.comparison, "registered_plan", return_value={"protocol": "fixture"}), \
                    patch.object(freeze, "publish", side_effect=publish), patch.object(freeze, "helper", side_effect=helper), \
                    patch.object(freeze, "quality_disposition", return_value=([proof], {"qualified": False})), \
                    patch.object(freeze, "snapshot"), patch.object(freeze.comparison, "verify_model"), \
                    patch.object(freeze.comparison, "model_identity", return_value={}), \
                    patch.object(freeze, "require_durable_binding", side_effect=durable), \
                    patch.object(freeze.round3_data, "baseline_bytes", return_value=json.dumps({
                        "source_url": "fixture://unused", "upstream_sha256": "fixture", "upstream_bytes": 0}).encode()), \
                    patch.object(freeze, "checked_download", side_effect=download), \
                    patch.object(freeze.round3_data, "freeze", side_effect=select), \
                    patch.object(freeze.comparison, "require_committed", side_effect=committed):
                self.assertEqual(freeze.run(), 0)
            self.assertEqual(events, ["bootstrap", "quality-fixtures", "recovery", "model-bytes", "bind",
                                     "durable-binding", "parquet", "durable-binding", "select"])
            self.assertEqual(published[-1]["status"], "frozen-ready-for-comparison")
            self.assertEqual(published[-1]["retrieval_calls"], 0)
            self.assertEqual(published[-1]["model_inference_calls"], 0)
            self.assertEqual(published[-1]["answer_calls"], 0)


if __name__ == "__main__":
    unittest.main()
