"""Fixed-run collection rejects changed identities, arbitrary code and partial data."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import collect_final_validation as collector


def run_record():
    return {**collector.TARGET, "conclusion": "failure",
            "repository": {"full_name": collector.REPOSITORY, "id": collector.REPOSITORY_ID},
            "head_repository": {"full_name": collector.REPOSITORY, "id": collector.REPOSITORY_ID}}


def event():
    return {"action": "completed", "repository": run_record()["repository"],
            "workflow_run": run_record()}


def environment():
    return {"GITHUB_REPOSITORY": collector.REPOSITORY, "GITHUB_EVENT_NAME": "workflow_run",
            "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "901", "GITHUB_RUN_ATTEMPT": "1",
            "FINALIZER_DEPENDENCIES_STATUS": "success", "FINALIZER_TEST_STATUS": "success"}


class FixedRunIdentityTests(unittest.TestCase):
    def test_failed_completed_run_is_valid_input_not_a_quality_pass(self):
        self.assertEqual(collector.event_identity(event(), environment())["conclusion"], "failure")
        for key, value in (("id", 123), ("run_attempt", 2), ("run_attempt", True),
                           ("head_sha", "f" * 40), ("status", "in_progress"),
                           ("workflow_id", 123), ("head_branch", "main")):
            changed = event()
            changed["workflow_run"][key] = value
            with self.assertRaises(collector.CollectionError):
                collector.event_identity(changed, environment())
        changed = event()
        changed["workflow_run"]["head_repository"]["full_name"] = "fork/untrusted"
        with self.assertRaises(collector.CollectionError):
            collector.event_identity(changed, environment())

    def test_only_registered_dispatch_and_kick_can_backfill_the_missed_event(self):
        for kind, ref in (("workflow_dispatch", "refs/heads/main"), ("push", collector.KICK_REF)):
            payload = {"repository": run_record()["repository"], "ref": ref}
            self.assertIsNone(collector.event_identity(payload, {
                **environment(), "GITHUB_EVENT_NAME": kind, "GITHUB_REF": ref}))
        with self.assertRaises(collector.CollectionError):
            collector.event_identity(event(), {**environment(), "GITHUB_REF": "refs/heads/untrusted"})
        with self.assertRaises(collector.CollectionError):
            collector.event_identity({"repository": run_record()["repository"],
                                      "ref": collector.KICK_REF, "deleted": True},
                                     {**environment(), "GITHUB_EVENT_NAME": "push",
                                      "GITHUB_REF": collector.KICK_REF})

    def test_dependency_failure_saves_audit_without_collection_or_aggregation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "event.json"
            payload.write_text(json.dumps(event()), encoding="utf-8")
            saved = []
            with patch.object(collector, "ROOT", root), \
                    patch.object(collector, "checked_out_main", return_value="a" * 40), \
                    patch.object(collector, "read_attempt", return_value=collector.identity(run_record())), \
                    patch.object(collector, "collect_stage") as collect, \
                    patch.object(collector.subprocess, "run") as execute, \
                    patch.object(collector, "publish", side_effect=lambda r, s, files: saved.append(set(files))), \
                    patch.dict(os.environ, {**environment(), "GITHUB_EVENT_PATH": str(payload),
                                            "FINALIZER_DEPENDENCIES_STATUS": "failure"}):
                self.assertEqual(collector.main(["--publish"]), 1)
            collect.assert_not_called()
            execute.assert_not_called()
            self.assertEqual(saved, [{collector.AUDIT}])
            audit = json.loads((root / collector.AUDIT).read_bytes())
            self.assertEqual(audit["status"], "failed")
            self.assertEqual(audit["reason"], "trusted_dependency_or_test_gate_failed")

    def test_strict_failure_never_publishes_leftover_assessments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "event.json"
            payload.write_text(json.dumps(event()), encoding="utf-8")
            def collected(_root, stage):
                return {"stage": stage, "imported_sha256": {name: "a" * 64 for name in
                        (*collector.BODIES[stage], collector.marker_path(stage))}}
            def failed(*args, **kwargs):
                collector.aggregate.atomic(root / collector.aggregate.AUDIT, {"status": "failed"})
                return subprocess.CompletedProcess(args[0], 1)
            saved = []
            with patch.object(collector, "ROOT", root), \
                    patch.object(collector, "checked_out_main", return_value="a" * 40), \
                    patch.object(collector, "read_attempt", return_value=collector.identity(run_record())), \
                    patch.object(collector, "collect_stage", side_effect=collected), \
                    patch.object(collector.subprocess, "run", side_effect=failed) as execute, \
                    patch.object(collector, "publish", side_effect=lambda r, s, files: saved.append(set(files))), \
                    patch.dict(os.environ, {**environment(), "GITHUB_EVENT_PATH": str(payload)}):
                self.assertEqual(collector.main(["--publish"]), 1)
            self.assertEqual(execute.call_count, 1)
            argv = execute.call_args.args[0]
            self.assertEqual(argv[1], str(root / "scripts/aggregate_hosted_validation.py"))
            self.assertNotIn("--publish", argv)
            self.assertTrue(set(collector.aggregate.OUTPUTS).isdisjoint(saved[0]))
            self.assertIn(collector.aggregate.AUDIT, saved[0])
            self.assertIn(collector.AUDIT, saved[0])
            self.assertEqual(len(saved[0]), 10)


@unittest.skipUnless(shutil.which("git"), "Git fixture integration")
class PublicBlobCollectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "work"
        self.root.mkdir()
        self.origin = Path(self.directory.name) / "origin.git"
        self.git("init", "--bare", str(self.origin))
        self.git("init", "-b", "main")
        self.git("config", "user.name", "fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        (self.root / ".gitignore").write_text(".artifacts/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "trusted source")
        self.base = self.git("rev-parse", "HEAD")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-u", "origin", "main")
        self.patch = patch.dict(collector.TARGET, {"head_sha": self.base})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.stage = "answers-hotpotqa"

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True,
                                       stderr=subprocess.PIPE).strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def publication(self, *, corrupt=False, extra_code=False, failed=False):
        self.git("checkout", "-b", "result-fixture", self.base)
        bodies = collector.BODIES[self.stage]
        if self.stage == "workflow-transfer36":
            bodies += collector.WORKFLOW_DERIVED
        data = {name: ("public:" + name).encode() for name in bodies}
        marker = {"schema_version": 1, "stage": self.stage, "source_commit": self.base,
                  "status": "failed" if failed else "completed", "missing_outputs": [],
                  "exit_code": 2 if failed else 0,
                  "public_output_sha256": {name: hashlib.sha256(value).hexdigest()
                                           for name, value in data.items()}}
        if corrupt:
            marker["public_output_sha256"][bodies[0]] = "0" * 64
        for name, value in data.items():
            self.write(name, value)
        self.write(collector.marker_path(self.stage), json.dumps(marker).encode())
        if extra_code:
            self.write("scripts/untrusted.py", b"raise RuntimeError('never execute')\n")
        self.git("add", ".")
        self.git("commit", "-m", "published public fixture")
        commit = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "HEAD:" + collector.source_branch(self.stage))
        self.git("checkout", "main")
        return commit, data

    def test_collects_exact_bytes_and_records_the_original_commit(self):
        commit, data = self.publication()
        result = collector.collect_stage(self.root, self.stage)
        self.assertEqual(result["result_commit"], commit)
        self.assertEqual(result["measurement_source_commit"], self.base)
        for name, value in data.items():
            self.assertEqual((self.root / name).read_bytes(), value)
        self.assertEqual(collector.collect_stage(self.root, self.stage), result)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_hash_mismatch_is_rejected_before_any_stage_file_is_written(self):
        self.publication(corrupt=True)
        with self.assertRaisesRegex(collector.CollectionError, "published_hash_mismatch"):
            collector.collect_stage(self.root, self.stage)
        for name in (*collector.BODIES[self.stage], collector.marker_path(self.stage)):
            self.assertFalse((self.root / name).exists())

    def test_arbitrary_code_in_result_branch_is_never_imported(self):
        self.publication(extra_code=True)
        with self.assertRaisesRegex(collector.CollectionError, "unregistered_changes"):
            collector.collect_stage(self.root, self.stage)
        self.assertFalse((self.root / "scripts/untrusted.py").exists())

    def test_conflicting_existing_input_is_not_overwritten(self):
        self.publication()
        name = collector.BODIES[self.stage][0]
        self.write(name, b"existing immutable bytes")
        with self.assertRaisesRegex(collector.CollectionError, "existing_canonical_input_differs"):
            collector.collect_stage(self.root, self.stage)
        self.assertEqual((self.root / name).read_bytes(), b"existing immutable bytes")

    def test_workflow_failed_attempt_is_collected_without_importing_derived_reports(self):
        self.stage = "workflow-transfer36"
        _, data = self.publication(failed=True)
        result = collector.collect_stage(self.root, self.stage)
        self.assertEqual(result["original_status"], "failed")
        self.assertEqual(set(result["public_output_sha256"]), set(data))
        self.assertEqual(len(result["imported_sha256"]), 2)
        for name in collector.WORKFLOW_DERIVED:
            self.assertFalse((self.root / name).exists())

    def test_missing_branch_fails_without_writing_inputs(self):
        with self.assertRaises(collector.CollectionError):
            collector.collect_stage(self.root, self.stage)
        self.assertFalse((self.root / "benchmarks").exists())

    def test_publisher_uses_separate_index_and_never_moves_main_or_overwrites_branch(self):
        self.publication()
        result = collector.collect_stage(self.root, self.stage)
        private = ".artifacts/private.txt"
        self.write(private, b"PRIVATE_UNREGISTERED_BYTES")
        self.git("add", "-f", private)
        before = self.git("ls-files", "--stage")
        collector.aggregate.atomic(self.root / collector.AUDIT, {"status": "failed"})
        selected = {collector.AUDIT, *result["imported_sha256"]}
        with patch.dict(os.environ, environment()):
            branch = collector.publish(self.root, self.base, selected)
            with self.assertRaisesRegex(collector.CollectionError, "publication_branch_exists"):
                collector.publish(self.root, self.base, selected)
        commit = self.git("ls-remote", "--heads", "origin", "refs/heads/" + branch).split()[0]
        files = self.git("ls-tree", "-r", "--name-only", commit).splitlines()
        self.assertNotIn(private, files)
        self.assertIn(collector.AUDIT, files)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), self.base)
        self.assertEqual(self.git("ls-files", "--stage"), before)

    def test_nonregular_git_blob_is_rejected(self):
        self.publication()
        commit = self.git("rev-parse", "result-fixture")
        name = collector.BODIES[self.stage][0]
        result = subprocess.CompletedProcess([], 0, b"120000 blob " + b"a" * 40
                                             + b"\t" + name.encode() + b"\0", b"")
        with patch.object(collector, "git", return_value=result):
            with self.assertRaisesRegex(collector.CollectionError, "not_a_regular_blob"):
                collector.blob(self.root, commit, name)


if __name__ == "__main__":
    unittest.main()
