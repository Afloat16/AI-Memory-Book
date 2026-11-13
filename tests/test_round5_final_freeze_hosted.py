"""Artificial checks for the source-free hosted freeze controller."""
import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import round5_final_freeze_hosted as freeze


def selection():
    evidence = [{"commit": "1" * 40, "path": "benchmarks/reports/invented/evidence.json",
                 "sha256": "2" * 64}]
    return {"schema_version": 1, "status": "selected-after-development-before-final-evaluation",
        "baseline": dict(freeze.BASELINE),
        "candidate": {"commit": "3" * 40, "runtime_sha256": "4" * 64},
        "candidate_files_sha256": {"src/memory_book/store.py": "5" * 64},
        "development_evidence": evidence, "independent_source_review": copy.deepcopy(evidence),
        "fresh_metadata_selected": False, "fresh_content_decoded": False,
        "formal_measurement_started": False}


class FinalFreezeTests(unittest.TestCase):
    def test_complete_selection_is_required(self):
        value = selection()
        self.assertIs(freeze.validate_selection(value), value)
        for key in ("candidate", "candidate_files_sha256", "development_evidence",
                    "independent_source_review", "status"):
            with self.subTest(key=key):
                changed = copy.deepcopy(value)
                changed.pop(key)
                with self.assertRaises(ValueError):
                    freeze.validate_selection(changed)

    def test_published_baseline_cannot_change(self):
        value = selection()
        value["baseline"]["commit"] = "0" * 40
        with self.assertRaises(ValueError):
            freeze.validate_selection(value)

    def test_selection_must_precede_fresh_and_formal_execution(self):
        for key in ("fresh_metadata_selected", "fresh_content_decoded", "formal_measurement_started"):
            for invalid in (True, 0, None, "false"):
                with self.subTest(key=key, invalid=invalid):
                    value = selection()
                    value[key] = invalid
                    with self.assertRaises(ValueError):
                        freeze.validate_selection(value)

    def test_source_inventory_rejects_traversal_or_invalid_hash(self):
        for name, checksum in (("src/memory_book/../private", "5" * 64),
                               ("other/store.py", "5" * 64),
                               ("src/memory_book/store.py", "z" * 64)):
            with self.subTest(name=name, checksum=checksum):
                value = selection()
                value["candidate_files_sha256"] = {name: checksum}
                with self.assertRaises(ValueError):
                    freeze.validate_selection(value)

    def test_evidence_must_be_immutable_public_report(self):
        for field, invalid in (("commit", "main"), ("sha256", "short"),
                               ("path", "benchmarks/reports/../private"),
                               ("path", ".artifacts/book.db")):
            with self.subTest(field=field):
                value = selection()
                value["development_evidence"][0][field] = invalid
                with self.assertRaises(ValueError):
                    freeze.validate_selection(value)

    def test_remote_ref_is_exact_and_single(self):
        head = "a" * 40
        self.assertIsNone(freeze.parse_remote(""))
        self.assertEqual(freeze.parse_remote(head + "\trefs/heads/" + freeze.BRANCH + "\n"), head)
        for invalid in (head, head + "\trefs/heads/other", head + " refs/heads/" + freeze.BRANCH + " extra"):
            with self.subTest(invalid=invalid), self.assertRaises(freeze.PublicationError):
                freeze.parse_remote(invalid)

    def test_publication_path_allowlist_is_narrow(self):
        self.assertTrue(freeze.allowed(freeze.relative(freeze.PUBLIC) + "/intent.json"))
        self.assertTrue(freeze.allowed(freeze.relative(freeze.CERTIFICATE)))
        self.assertTrue(freeze.allowed(freeze.relative(freeze.BINDING)))
        for path in ("src/memory_book/store.py", ".artifacts/book.db",
                     "benchmarks/reports/other/report.json"):
            self.assertFalse(freeze.allowed(path))

    def test_missing_selection_precedes_claim_source_and_publication(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": freeze.TRIGGER}):
            with patch.object(freeze, "read", side_effect=FileNotFoundError("selection")):
                with patch.object(freeze, "remote_head") as remote, patch.object(freeze, "publish") as publish:
                    with patch.object(freeze, "prepare_source") as prepare:
                        with self.assertRaises(FileNotFoundError):
                            freeze.run()
        remote.assert_not_called()
        publish.assert_not_called()
        prepare.assert_not_called()

    def test_failed_stage_retains_published_exit_head(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            with patch.object(freeze, "PUBLIC", public):
                with patch.object(freeze, "publish", side_effect=["a" * 40, "b" * 40]) as publish:
                    with patch.object(freeze.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
                        with self.assertRaises(freeze.StageError) as caught:
                            freeze.command_stage("fixture", ["invented-command"], "c" * 40)
            self.assertEqual(caught.exception.published_head, "b" * 40)
            result = json.loads((public / "fixture.exit.json").read_bytes())
            self.assertEqual(result["returncode"], 1)
            self.assertEqual(result["retrieval_calls_executed"], 0)
            self.assertEqual(publish.call_count, 2)

    def test_successful_stage_is_published_once_before_and_after(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            with patch.object(freeze, "PUBLIC", public):
                with patch.object(freeze, "publish", side_effect=["a" * 40, "b" * 40]) as publish:
                    with patch.object(freeze.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                        head = freeze.command_stage("fixture", ["invented-command"], "c" * 40)
            self.assertEqual(head, "b" * 40)
            self.assertEqual(publish.call_count, 2)
            self.assertEqual(run.call_count, 1)


    def test_post_intent_receipt_failures_keep_latest_published_head(self):
        for phase in ("copy", "hash", "save"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                public = root / "public"
                raw = root / ".artifacts/round5-interface-certificate/invented"
                raw.mkdir(parents=True)
                observation = raw / "baseline.json"
                observation.write_text('{"invented": true}\n', encoding="utf-8")
                artifact = root / "certificate.json"
                artifact.write_text("{}\n", encoding="utf-8")
                failure = OSError("invented " + phase + " receipt failure")
                original_save = freeze.save

                def fail_exit(path, value):
                    if path.name == "interface.exit.json":
                        raise failure
                    return original_save(path, value)

                with ExitStack() as stack:
                    stack.enter_context(patch.object(freeze, "ROOT", root))
                    stack.enter_context(patch.object(freeze, "PUBLIC", public))
                    publish = stack.enter_context(patch.object(freeze, "publish", return_value="a" * 40))
                    run = stack.enter_context(patch.object(freeze.subprocess, "run",
                        return_value=SimpleNamespace(returncode=0)))
                    if phase == "copy":
                        stack.enter_context(patch.object(freeze.shutil, "copytree", side_effect=failure))
                    elif phase == "hash":
                        stack.enter_context(patch.object(freeze, "sha", side_effect=failure))
                    else:
                        stack.enter_context(patch.object(freeze, "save", side_effect=fail_exit))
                    with self.assertRaises(freeze.StageError) as caught:
                        freeze.command_stage("interface", ["invented-command"], "c" * 40, (artifact,))
                self.assertEqual(caught.exception.published_head, "a" * 40)
                self.assertIs(caught.exception.__cause__, failure)
                self.assertIn(str(failure), str(caught.exception))
                self.assertEqual(publish.call_count, 1)
                self.assertEqual(run.call_count, 1)
                self.assertTrue((public / "interface.intent.json").is_file())
                self.assertTrue((public / "interface.log").is_file())
                self.assertTrue(observation.is_file())

    def test_publication_failure_is_not_wrapped_or_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failure = freeze.PublicationError("invented ambiguous push")
            with patch.object(freeze, "ROOT", root), patch.object(freeze, "PUBLIC", root / "public"):
                with patch.object(freeze, "publish", side_effect=["a" * 40, failure]) as publish:
                    with patch.object(freeze.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                        with self.assertRaises(freeze.PublicationError) as caught:
                            freeze.command_stage("fixture", ["invented-command"], "c" * 40)
            self.assertIs(caught.exception, failure)
            self.assertEqual(publish.call_count, 2)
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
