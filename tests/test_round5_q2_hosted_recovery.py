"""Invented Q2 protocol fixtures only: no corpus, model, inference or retrieval."""
from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round5_q2_hosted_recovery as q2


class Q2RecoveryTests(unittest.TestCase):
    def preparation(self):
        vectors = {"sha256": "a" * 64, "rows": 2, "vector_bytes": 3072,
                   "revision": 2, "model_fingerprint": "b" * 64, "boundary": "invented complete boundary"}
        scope = {"sources": {"historical_builder": {"runtime_sha256": "c" * 64}},
                 "original_files": {"old_evaluator_sha256": {"invented.py": "d" * 64}},
                 "model": {"invented_model": True},
                 "dependencies": {"onnxruntime": "invented-1", "tokenizers": "invented-2", "numpy": "invented-3"}}
        registered = {"dataset_sha256": "e" * 64, "queries": 2, "historical_vectors": vectors,
                      "historical_originals_sha256": "f" * 64}
        value = {"source_sha256": "c" * 64, "dataset_sha256": "e" * 64, "queries": 2,
                 "evaluator_files": scope["original_files"]["old_evaluator_sha256"],
                 "ort_disable_telemetry": "1", "model": scope["model"], "vectors": vectors,
                 "originals_sha256": "0" * 64, "semantic_index": {"inference_threads": 1,
                    "model_fingerprint": "b" * 64, "runtime": scope["dependencies"]}}
        actual = {"originals_sha256": "0" * 64, "vectors": vectors, "cache_rows": 0}
        return scope, registered, value, actual

    def test_missing_candidate_fails_before_claim_fetch_or_assets(self):
        with tempfile.TemporaryDirectory() as name:
            with patch.object(q2, "SOURCE_BINDING", Path(name) / "missing.json"), \
                    patch.object(q2, "remote_head") as remote, \
                    patch.object(q2, "static_preflight") as preflight, \
                    patch.object(q2, "assets") as assets, patch.object(q2, "publish") as publish:
                with self.assertRaises(FileNotFoundError):
                    q2.run()
                for function in (remote, preflight, assets, publish):
                    function.assert_not_called()

    def test_candidate_requires_exact_safe_complete_inventory(self):
        value = {"candidate": "Invented", "status": "frozen-before-q2-recovery",
                 "commit": "a" * 40, "runtime_sha256": "b" * 64,
                 "files_sha256": {"src/memory_book/__init__.py": "c" * 64}}
        self.assertEqual(q2.validate_candidate(value)["commit"], "a" * 40)
        for change in ({"status": "pending"}, {"commit": "main"}, {"runtime_sha256": None},
                       {"files_sha256": {}}, {"files_sha256": {"src/memory_book/../../outside.py": "d" * 64}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                q2.validate_candidate({**value, **change})

    def test_new_originals_are_separate_but_entire_vectors_must_match(self):
        scope, registered, value, actual = self.preparation()
        self.assertNotEqual(value["originals_sha256"], registered["historical_originals_sha256"])
        q2.validate_preparation(value, actual, registered, scope)
        changes = {"sha256": "1" * 64, "rows": 3, "vector_bytes": 3073,
                   "revision": True, "model_fingerprint": "2" * 64, "boundary": "different"}
        for field, changed in changes.items():
            for target in ("preparation", "database"):
                with self.subTest(field=field, target=target):
                    damaged, observed = copy.deepcopy(value), copy.deepcopy(actual)
                    (damaged if target == "preparation" else observed)["vectors"][field] = changed
                    with self.assertRaises(ValueError):
                        q2.validate_preparation(damaged, observed, registered, scope)

    def test_originals_cache_and_runtime_cannot_drift(self):
        scope, registered, value, actual = self.preparation()
        for changed in ({"originals_sha256": "f" * 64}, {"cache_rows": 1}, {"cache_rows": False}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                q2.validate_preparation(value, {**actual, **changed}, registered, scope)
        damaged = copy.deepcopy(value)
        damaged["semantic_index"]["inference_threads"] = True
        with self.assertRaises(ValueError):
            q2.validate_preparation(damaged, actual, registered, scope)

    def saved_report(self):
        ids = ["invented-b", "invented-a"]
        binding = {"sources": {"baseline": {"runtime_sha256": "a" * 64}},
                   "cohorts": {"invented": {"query_ids": ids, "dataset_sha256": "b" * 64,
                       "preparation_sha256": "c" * 64, "originals_sha256": "d" * 64,
                       "vectors": {"sha256": "e" * 64}}},
                   "old_evaluator_files": {"invented.py": "f" * 64}, "model": {"invented": True}}
        entry = {"cohort": "invented", "encoder": "cl100k_base", "label": "baseline"}
        expected = q2.legacy.expected_report(binding, entry)
        rows = [{"query_id": identity, "budget_tokens": budget, "payload_sha256": "1" * 64,
                 "context_sha256": "2" * 64, "errors": {key: 0 for key in q2.legacy.ERRORS}}
                for budget in q2.legacy.BUDGETS for identity in ids]
        events = []
        for row in rows:
            events.extend(({"state": "started", "query_id": row["query_id"], "budget_tokens": row["budget_tokens"]},
                           {"state": "finished", **row}))
        ledger = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
        report = {**expected, "status": "completed", "attempts_started": 6, "attempts_finished": 6,
                  "rows": rows, "ledger_sha256": hashlib.sha256(ledger).hexdigest()}
        return report, ledger, expected, ids

    def test_original_auditor_rejects_missing_reordered_or_invalid_calls(self):
        report, ledger, expected, ids = self.saved_report()
        rows = q2.legacy.audit_report(report, ledger, expected, ids)
        q2.legacy.equal_payloads(rows, copy.deepcopy(rows))
        for change in ("missing", "order", "source", "error"):
            with self.subTest(change=change):
                damaged = copy.deepcopy(report)
                if change == "missing":
                    damaged["rows"].pop()
                elif change == "order":
                    damaged["rows"].reverse()
                elif change == "source":
                    damaged["runtime_sha256"] = "9" * 64
                else:
                    damaged["rows"][0]["errors"]["token"] = False
                with self.assertRaises(ValueError):
                    q2.legacy.audit_report(damaged, ledger, expected, ids)
        with self.assertRaises(ValueError):
            q2.legacy.audit_report(report, ledger[:-1], expected, ids)
        changed = copy.deepcopy(rows)
        changed[0]["payload_sha256"] = "3" * 64
        with self.assertRaises(ValueError):
            q2.legacy.equal_payloads(rows, changed)

    def test_schedule_has_one_fixed_eight_worker_matrix(self):
        workers = q2.schedule()
        self.assertEqual(len(workers), len({row["id"] for row in workers}))
        self.assertEqual(len(workers), 8)
        self.assertEqual([row["label"] for row in workers], ["baseline", "candidate"] * 4)
        self.assertEqual(sum({"authored36": 36, "hotpot128": 128}[row["cohort"]] * 3 for row in workers), 1968)
        self.assertEqual([row["index"] for row in workers], list(range(1, 9)))

    def test_partial_ledger_compression_preserves_exact_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            public = Path(name)
            ledger = public / "invented.json.gz.attempts.jsonl"
            raw = b'{"state":"started","query_id":"invented","budget_tokens":512}\n'
            ledger.write_bytes(raw)
            with patch.object(q2, "PUBLIC", public):
                q2.compress_ledgers()
                compressed = ledger.with_name(ledger.name + ".gz")
                self.assertEqual(gzip.decompress(compressed.read_bytes()), raw)
                q2.compress_ledgers()
                ledger.write_bytes(raw + b"changed")
                with self.assertRaises(ValueError):
                    q2.compress_ledgers()

    def test_download_is_bounded_and_partial_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "invented.bin"
            raw = b"invented asset"
            with patch.object(q2.urllib.request, "urlopen", return_value=io.BytesIO(raw)) as network:
                with self.assertRaises(ValueError):
                    q2.download(target, "https://invalid.example/never-contacted", len(raw), "0" * 64)
                self.assertFalse(target.exists())
                self.assertEqual(target.with_name(target.name + ".partial").read_bytes(), raw)
                with self.assertRaises(ValueError):
                    q2.download(target, "https://invalid.example/never-contacted", len(raw), hashlib.sha256(raw).hexdigest())
                self.assertEqual(network.call_count, 1)

    def test_failed_stage_keeps_partial_log_and_one_exit_without_retry(self):
        with tempfile.TemporaryDirectory() as name:
            public = Path(name)
            with patch.object(q2, "PUBLIC", public), \
                    patch.object(q2.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as process, \
                    patch.object(q2, "publish") as publish:
                with self.assertRaisesRegex(ValueError, "did not complete"):
                    q2.run_stage("invented", ["never-executed"], 1)
                self.assertEqual(process.call_count, 1)
                self.assertEqual(publish.call_count, 1)
                self.assertTrue((public / "invented.log.partial").exists())
                self.assertEqual(q2.read(public / "invented.exit.json")["returncode"], 7)

    def test_sparse_worktree_preserves_exact_source_git_provenance(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            package = root / "src/memory_book"
            package.mkdir(parents=True)
            raw = b"VALUE = 1\n"
            (package / "__init__.py").write_bytes(raw)
            (root / ".gitignore").write_text(".artifacts/\n")
            unrelated = root / "benchmarks/reports/invented.txt"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("invented non-corpus object\n")
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)
            git("init", "--quiet")
            git("add", ".")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "invented sparse provenance")
            commit = git("rev-parse", "HEAD").decode().strip()
            identity = {"commit": commit,
                        "runtime_sha256": hashlib.sha256(b"__init__.py\0" + raw + b"\0").hexdigest(),
                        "files_sha256": {"src/memory_book/__init__.py": hashlib.sha256(raw).hexdigest()}}
            with patch.object(q2, "ROOT", root), patch.object(q2, "STATE", root / ".artifacts/test"), \
                    patch.object(q2.legacy, "ROOT", root), patch.object(q2, "fetch") as network:
                source = q2.export_source("candidate", identity)
                q2.verify_source(source)
                directory = (root / source["source"]).parent
                self.assertFalse((directory / "benchmarks/reports/invented.txt").exists())
                self.assertEqual(network.call_count, 1)
                (directory / "src/memory_book/unexpected.pyc").write_bytes(b"invented")
                with self.assertRaisesRegex(ValueError, "inventory changed"):
                    q2.verify_source(source)


if __name__ == "__main__":
    unittest.main()
