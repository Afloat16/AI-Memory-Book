"""Preparation safety tests use temporary Git and invented data; no downloads."""
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


if __name__ == "__main__":
    unittest.main()
