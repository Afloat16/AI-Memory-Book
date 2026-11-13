"""Bounded Q2 union-repair fixtures: invented bytes only, no model or corpus."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import round5_q2_hosted_recovery_v2 as q2


class Q2UnionRecoveryTests(unittest.TestCase):
    @contextmanager
    def inventory(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw = {"import_only.py": b"# invented import dependency\n",
                   "registry_only.py": b"# invented explicit registry member\n"}
            for path, content in raw.items():
                (root / path).write_bytes(content)
            expected = {path: hashlib.sha1(("blob " + str(len(content)) + "\0").encode()
                        + content).hexdigest() for path, content in raw.items()}
            scope = {"original_files": {"old_evaluator_sha256": {
                "registry_only.py": hashlib.sha256(raw["registry_only.py"]).hexdigest()}},
                "strict_union_repair": {
                    "original_import_closure": ["import_only.py"],
                    "expected_union_git_blobs": expected,
                    "expected_counts": {"original_closure": 1, "explicit_registry": 1, "union": 2},
                    "scope_only_paths": ["registry_only.py"]}}
            with patch.object(q2, "ROOT", root), \
                    patch.object(q2.legacy, "helper_closure", return_value={"import_only.py"}), \
                    patch.object(q2, "blob", side_effect=lambda ref, path: raw[path]) as historical:
                yield root, raw, scope, historical

    def test_union_includes_actual_registry_only_and_import_only_bytes(self):
        with self.inventory() as (_, raw, scope, historical):
            files, proof = q2.registered_helper_union(scope)
            self.assertEqual(files, {name: hashlib.sha256(content).hexdigest()
                                    for name, content in raw.items()})
            self.assertEqual(proof["counts"], {"original_closure": 1, "explicit_registry": 1, "union": 2})
            self.assertEqual(proof["scope_only_paths"], ["registry_only.py"])
            self.assertTrue(proof["files"]["registry_only.py"]["in_explicit_registry"])
            self.assertFalse(proof["files"]["registry_only.py"]["in_import_closure"])
            self.assertTrue(proof["files"]["import_only.py"]["in_import_closure"])
            self.assertFalse(proof["files"]["import_only.py"]["in_explicit_registry"])
            self.assertEqual({call.args for call in historical.call_args_list},
                             {(q2.REFERENCE, path) for path in raw})
            self.assertEqual(proof["retrieval_calls"], 0)

    def test_missing_registry_only_file_is_not_replaced_with_expected_hash(self):
        with self.inventory() as (root, _, scope, _):
            (root / "registry_only.py").unlink()
            with self.assertRaisesRegex(ValueError, "Missing or symlink.*registry_only.py"):
                q2.registered_helper_union(scope)

    def test_registry_only_symlink_is_rejected_even_when_target_bytes_match(self):
        with self.inventory() as (root, raw, scope, _):
            path = root / "registry_only.py"
            path.unlink()
            target = root / "invented-target"
            target.write_bytes(raw["registry_only.py"])
            path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "Missing or symlink.*registry_only.py"):
                q2.registered_helper_union(scope)

    def test_registry_only_actual_or_historical_byte_changes_are_rejected(self):
        for side in ("actual", "historical"):
            with self.subTest(side=side), self.inventory() as (root, raw, scope, _):
                if side == "actual":
                    (root / "registry_only.py").write_bytes(b"# changed invented actual bytes\n")
                else:
                    raw["registry_only.py"] = b"# changed invented historical bytes\n"
                with self.assertRaisesRegex(ValueError, "Historical helper/input bytes changed: registry_only.py"):
                    q2.registered_helper_union(scope)

    def test_registry_only_registered_sha_mismatch_fails_after_git_byte_match(self):
        with self.inventory() as (_, _, scope, historical):
            scope["original_files"]["old_evaluator_sha256"]["registry_only.py"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "Preparation evaluator identity changed: registry_only.py"):
                q2.registered_helper_union(scope)
            self.assertIn((q2.REFERENCE, "registry_only.py"), {call.args for call in historical.call_args_list})

    def test_missing_import_only_dependency_remains_a_failure(self):
        with self.inventory() as (root, _, scope, _):
            (root / "import_only.py").unlink()
            with self.assertRaisesRegex(ValueError, "Missing or symlink.*import_only.py"):
                q2.registered_helper_union(scope)

    def test_frozen_union_cannot_omit_either_source_of_membership(self):
        for omitted in ("import_only.py", "registry_only.py"):
            with self.subTest(omitted=omitted), self.inventory() as (_, _, scope, historical):
                del scope["strict_union_repair"]["expected_union_git_blobs"][omitted]
                with self.assertRaisesRegex(ValueError, "Frozen union membership changed"):
                    q2.registered_helper_union(scope)
                historical.assert_not_called()

    def test_registry_check_does_not_enter_saved_rows_assets_or_measurement(self):
        proof = {"status": "invented-source-only", "retrieval_calls": 0}
        with ExitStack() as stack:
            preflight = stack.enter_context(patch.object(q2, "source_preflight", return_value=({}, {}, proof)))
            forbidden = [stack.enter_context(patch.object(q2, name)) for name in
                         ("historical_metadata", "assets", "prepare_snapshots", "worker", "publish")]
            self.assertEqual(q2.check_registry(), proof)
            preflight.assert_called_once_with()
            for call in forbidden:
                call.assert_not_called()

    def test_missing_candidate_still_precedes_namespace_or_source_work(self):
        with tempfile.TemporaryDirectory() as name, ExitStack() as stack:
            stack.enter_context(patch.object(q2, "SOURCE_BINDING", Path(name) / "missing.json"))
            forbidden = [stack.enter_context(patch.object(q2, key)) for key in
                         ("remote_head", "static_preflight", "source_preflight", "fetch", "assets", "publish")]
            with self.assertRaises(FileNotFoundError):
                q2.run()
            for call in forbidden:
                call.assert_not_called()

    def test_registered_second_namespace_controls_workflow_and_preclaim_gate(self):
        scope = q2.read(q2.SCOPE)
        self.assertEqual(q2.ATTEMPT, scope["attempt"])
        self.assertEqual(q2.BRANCH, scope["durability"]["result_branch"])
        self.assertEqual(q2.PUBLIC.relative_to(q2.ROOT).as_posix() + "/", scope["durability"]["output"])
        self.assertEqual(q2.STATE.relative_to(q2.ROOT).as_posix() + "/", scope["durability"]["state"])
        workflow = (q2.ROOT / ".github/workflows/round5-q2-recovery-hosted-v2.yml").read_text()
        self.assertEqual(workflow.count("ci/v033-q2-recovery-hosted-2"), 2)
        self.assertNotIn("v033-q2-recovery-hosted-1", workflow)
        for suffix, accepted in (("1", False), ("2", True)):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as name, ExitStack() as stack:
                stack.enter_context(patch.object(q2, "PUBLIC", Path(name) / "public"))
                stack.enter_context(patch.object(q2, "STATE", Path(name) / "state"))
                stack.enter_context(patch.object(q2, "candidate_binding", return_value={}))
                stack.enter_context(patch.dict(q2.os.environ, {
                    "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/ci/v033-q2-recovery-hosted-" + suffix}))
                remote = stack.enter_context(patch.object(q2, "remote_head", return_value=None))
                preflight = stack.enter_context(patch.object(q2, "static_preflight",
                                                             side_effect=RuntimeError("source-only sentinel")))
                forbidden = [stack.enter_context(patch.object(q2, key)) for key in ("assets", "publish")]
                with self.assertRaisesRegex(RuntimeError if accepted else ValueError,
                                            "source-only sentinel" if accepted else "registered first"):
                    q2.run()
                if accepted:
                    remote.assert_called_once_with()
                    preflight.assert_called_once_with()
                else:
                    remote.assert_not_called()
                    preflight.assert_not_called()
                for call in forbidden:
                    call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
