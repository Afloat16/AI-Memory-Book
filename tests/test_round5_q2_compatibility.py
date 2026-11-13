"""Artificial saved-result/guard fixtures; no Book, retrieval or inference."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from scripts import round5_q2_compatibility as q


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def saved_report(binding, worker, *, historical=False):
    expected = q.expected_report(binding, worker, historical=historical)
    rows = []
    for budget in q.BUDGETS:
        for identity in binding["cohorts"][worker["cohort"]]["query_ids"]:
            key = [worker["cohort"], worker["encoder"], budget, identity]
            rows.append({"query_id": identity, "budget_tokens": budget,
                         "payload_sha256": q.digest(key + ["payload"]),
                         "context_sha256": q.digest(key + ["context"]),
                         "errors": {name: 0 for name in q.ERRORS}})
    report = {**expected, "status": "completed", "attempts_started": len(rows),
              "attempts_finished": len(rows), "rows": rows}
    return report, regenerate_ledger(report)


def regenerate_ledger(report):
    lines = []
    for row in report["rows"]:
        lines += [{"state": "started", "query_id": row["query_id"], "budget_tokens": row["budget_tokens"]},
                  {"state": "finished", **row}]
    raw = b"".join(encoded(line) + b"\n" for line in lines)
    report["ledger_sha256"] = hashlib.sha256(raw).hexdigest()
    return raw


def store(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def save_worker(binding, worker, report, ledger):
    store(q.local(worker["report"]), gzip.compress(encoded(report), mtime=0))
    store(q.local(worker["ledger"]), ledger)
    original = {cohort: q.expected_database(binding, cohort) for cohort in q.COHORTS}
    receipt = {"status": "completed", "returncode": 0, "worker": worker,
        "before": q.expected_database(binding, worker["cohort"]),
        "after": q.expected_database(binding, worker["cohort"]),
        "originals_before": original, "originals_after": original,
        "binding_sha256": "e" * 64,
        "intent_sha256": q.file_sha(q.control_path(binding, "execution-intent.json")),
        "artifacts": q.report_artifacts(worker)}
    store(q.local(worker["receipt"]), encoded(receipt))


def fixture():
    binding = {"sources": {"baseline": {"runtime_sha256": q.BASELINE_SHA, "source": "fake-baseline"},
                            "candidate": {"runtime_sha256": "b" * 64, "source": "fake-candidate"}},
        "old_evaluator_files": {q.HELPER: "a" * 64}, "model": {"fixture": "no actual model"},
        "cohorts": {}, "state_root": ".artifacts/round5-q2-fixture",
        "results_root": "benchmarks/reports/round5-q2-fixture", "model_dir": ".artifacts/fake-model",
        "parquet": {"path": ".artifacts/fake.parquet"}, "python_executable": "/fake/python",
        "old_c2": {}}
    for cohort, (count, fingerprint) in q.COHORTS.items():
        binding["cohorts"][cohort] = {"dataset_sha256": fingerprint,
            "query_ids": [cohort + "-fixture-" + str(index) for index in range(count)],
            "preparation": q.OLD + "/" + cohort + "-preparation.json", "preparation_sha256": "c" * 64,
            "originals_sha256": "d" * 64, "vectors": {"fixture_vector_sha256": "f" * 64}}
    binding["workers"] = q.schedule(binding)
    store(q.control_path(binding, "execution-intent.json"), encoded({"binding_sha256": "e" * 64}))
    pinned = {}
    for worker in binding["workers"]:
        q.local(worker["state"]).mkdir(parents=True)
        report, ledger = saved_report(binding, worker)
        save_worker(binding, worker, report, ledger)
        if worker["label"] == "baseline":
            old_report, old_ledger = saved_report(binding, worker, historical=True)
            name = f"{worker['cohort']}-candidate-{worker['encoder']}.json.gz"
            ledger_name = name + ".attempts.jsonl.gz"
            store(q.local(q.OLD + "/" + name), gzip.compress(encoded(old_report), mtime=0))
            store(q.local(q.OLD + "/" + ledger_name), gzip.compress(old_ledger, mtime=0))
            report_sha = q.file_sha(q.local(q.OLD + "/" + name))
            ledger_sha = q.file_sha(q.local(q.OLD + "/" + ledger_name))
            raw_sha = hashlib.sha256(old_ledger).hexdigest()
            pinned.update({name: report_sha, ledger_name: ledger_sha, name + ".attempts.jsonl": raw_sha})
            binding["old_c2"][worker["cohort"] + "/" + worker["encoder"]] = {
                "report": q.OLD + "/" + name, "report_sha256": report_sha,
                "ledger": q.OLD + "/" + ledger_name, "ledger_sha256": ledger_sha,
                "ledger_raw_sha256": raw_sha}
    store(q.local(q.OLD + "/paired-audit.json"), encoded({"file_sha256": pinned}))
    return binding


class SavedResultAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="round5-q2-fixture-", dir=q.ROOT / ".artifacts")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.patch = mock.patch.object(q, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.binding = fixture()
        self.worker = self.binding["workers"][0]
        self.report, self.ledger = saved_report(self.binding, self.worker)
        self.expected = q.expected_report(self.binding, self.worker)
        self.ids = self.binding["cohorts"]["authored36"]["query_ids"]

    def check_report(self, report=None, ledger=None):
        return q.audit_report(report if report is not None else self.report,
                              ledger if ledger is not None else self.ledger, self.expected, self.ids)

    def test_complete_1968_call_984_pair_3936_event_matrix(self):
        with mock.patch.object(q, "committed") as committed:
            artifacts = q.audit_prefix(self.binding, 8)
        self.assertEqual(len(artifacts), 8)
        self.assertEqual(committed.call_count, 24)
        self.assertEqual(sum(worker["expected_calls"] for worker in self.binding["workers"]), 1968)
        self.assertEqual(sum(len(q.local(worker["ledger"]).read_bytes().splitlines())
                             for worker in self.binding["workers"]), 3936)
        q.check_layout(self.binding)

    def test_every_identity_and_setting_is_audited(self):
        for key, value in {"runtime_sha256": "0" * 64, "preparation_sha256": "0" * 64,
                           "evaluator_files": {}, "model": {}, "ort_disable_telemetry": "0",
                           "dataset_sha256": "0" * 64, "label": "candidate",
                           "originals_sha256": "0" * 64, "vectors": {},
                           "configured_generative_model_calls": 1}.items():
            with self.subTest(field=key):
                report = copy.deepcopy(self.report)
                report[key] = value
                with self.assertRaises(ValueError):
                    self.check_report(report)
        for key, value in {"semantic": 1, "coverage": True, "budget_chars": 9000,
                           "token_budgets": [512], "tokenizer": "o200k_base", "limit": 6,
                           "cache_size": 1, "use_cache": True, "repetitions": 2}.items():
            with self.subTest(setting=key):
                report = copy.deepcopy(self.report)
                report["settings"][key] = value
                with self.assertRaises(ValueError):
                    self.check_report(report)

    def test_missing_duplicate_and_reordered_rows_fail(self):
        variants = [self.report["rows"][:-1], self.report["rows"] + [self.report["rows"][-1]],
                    [self.report["rows"][1], self.report["rows"][0], *self.report["rows"][2:]],
                    [self.report["rows"][0], self.report["rows"][0], *self.report["rows"][2:]]]
        for rows in variants:
            report = copy.deepcopy(self.report)
            report["rows"] = rows
            ledger = regenerate_ledger(report)
            with self.assertRaises(ValueError):
                self.check_report(report, ledger)

    def test_rehashed_unmatched_or_extra_ledger_event_fails(self):
        lines = self.ledger.splitlines()
        variants = [b"\n".join([lines[1], lines[0], *lines[2:]]) + b"\n",
                    self.ledger + lines[-1] + b"\n", self.ledger[:-1],
                    self.ledger.replace(b'"state":"finished"', b'"state":"started"', 1)]
        for ledger in variants:
            report = copy.deepcopy(self.report)
            report["ledger_sha256"] = hashlib.sha256(ledger).hexdigest()
            with self.assertRaises(ValueError):
                self.check_report(report, ledger)

    def test_raw_ledger_checksum_must_match(self):
        with self.assertRaisesRegex(ValueError, "Raw ledger SHA"):
            self.check_report(ledger=self.ledger + b"\n")

    def test_error_types_and_digest_shapes_fail_closed(self):
        for value in (1, False, 0.0, "0"):
            report = copy.deepcopy(self.report)
            report["rows"][0]["errors"]["token"] = value
            with self.assertRaises(ValueError):
                self.check_report(report, regenerate_ledger(report))
        for key, value in (("payload_sha256", "not-a-digest"), ("context_sha256", None), ("budget_tokens", 512.0)):
            report = copy.deepcopy(self.report)
            report["rows"][0][key] = value
            with self.assertRaises(ValueError):
                self.check_report(report, regenerate_ledger(report))

    def test_partial_completion_and_unknown_fields_fail(self):
        for key, value in (("status", "failed-incomplete"), ("attempts_started", 109),
                           ("attempts_finished", 107), ("expected_calls", 108.0), ("extra", "ignored")):
            report = copy.deepcopy(self.report)
            report[key] = value
            with self.assertRaises(ValueError):
                self.check_report(report)

    def test_candidate_mismatch_is_not_hidden_by_rehashing(self):
        worker = self.binding["workers"][1]
        report, ledger = saved_report(self.binding, worker)
        report["rows"][0]["payload_sha256"] = "0" * 64
        ledger = regenerate_ledger(report)
        save_worker(self.binding, worker, report, ledger)
        with self.assertRaisesRegex(ValueError, "equality"):
            q.audit_prefix(self.binding, 2, require_commit=False)

    def test_baseline_must_equal_old_c2_even_when_pair_matches(self):
        for worker in self.binding["workers"][:2]:
            report, ledger = saved_report(self.binding, worker)
            report["rows"][0]["context_sha256"] = "0" * 64
            save_worker(self.binding, worker, report, regenerate_ledger(report))
        with self.assertRaisesRegex(ValueError, "equality"):
            q.audit_prefix(self.binding, 2, require_commit=False)

    def test_old_c2_cannot_silently_rebind_to_different_files(self):
        old = self.binding["old_c2"]["authored36/cl100k_base"]
        old["report_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "frozen audit"):
            q.audit_prefix(self.binding, 1, require_commit=False)

    def test_receipt_binding_originals_and_status_are_checked(self):
        path = q.local(self.worker["receipt"])
        original = q.read_json(path)
        for key, value in (("binding_sha256", "0" * 64), ("status", "running"),
                           ("originals_after", {}), ("returncode", False), ("artifacts", {})):
            receipt = copy.deepcopy(original)
            receipt[key] = value
            store(path, encoded(receipt))
            with self.assertRaisesRegex(ValueError, "receipt"):
                q.audit_worker(self.binding, self.worker, require_commit=False)

    def test_missing_prior_receipt_and_unexpected_artifacts_fail(self):
        q.local(self.worker["receipt"]).unlink()
        with self.assertRaises(FileNotFoundError):
            q.audit_prefix(self.binding, 2, require_commit=False)
        store(q.control_path(self.binding, "unregistered-attempt.json"), b"{}")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            q.check_layout(self.binding)

    def test_existing_worker_is_rejected_before_runner_or_database(self):
        args = SimpleNamespace(binding=self.root / "binding.json", index=1)
        with mock.patch.object(q, "load_binding", return_value=self.binding), \
             mock.patch.object(q, "load_intent"), mock.patch.object(q, "execute") as runner, \
             mock.patch.object(q, "check_database") as database:
            with self.assertRaisesRegex(ValueError, "never replay"):
                q.worker(args)
        runner.assert_not_called()
        database.assert_not_called()

    def test_uncommitted_prefix_is_rejected_before_runner(self):
        args = SimpleNamespace(binding=self.root / "binding.json", index=2)
        with mock.patch.object(q, "load_binding", return_value=self.binding), \
             mock.patch.object(q, "load_intent"), \
             mock.patch.object(q, "committed", side_effect=ValueError("not committed")), \
             mock.patch.object(q, "execute") as runner:
            with self.assertRaisesRegex(ValueError, "not committed"):
                q.worker(args)
        runner.assert_not_called()

    def test_failed_fake_runner_is_durable_and_cannot_retry(self):
        for work in self.binding["workers"]:
            for key in ("report", "ledger", "receipt"):
                q.local(work[key]).unlink()
        args = SimpleNamespace(binding=self.root / "binding.json", index=1)
        store(args.binding, b"fixture binding, not a registered run")
        identity = q.expected_database(self.binding, "authored36")
        with mock.patch.object(q, "load_binding", return_value=self.binding), \
             mock.patch.object(q, "load_intent"), mock.patch.object(q, "execute", return_value=2) as runner, \
             mock.patch.object(q, "check_database", return_value=identity), \
             mock.patch.object(q, "check_originals", return_value={}):
            with self.assertRaisesRegex(ValueError, "worker failed"):
                q.worker(args)
            receipt = q.read_json(q.local(self.worker["receipt"]))
            self.assertEqual(receipt["status"], "failed-incomplete")
            self.assertEqual(receipt["returncode"], 2)
            with self.assertRaisesRegex(ValueError, "never replay"):
                q.worker(args)
        self.assertEqual(runner.call_count, 1)
        self.assertTrue(q.local(self.worker["state"]).joinpath("stdout.log").exists())

    def test_prepare_refuses_existing_state_without_backup(self):
        with mock.patch.object(q, "load_binding", return_value=self.binding), \
             mock.patch.object(q, "backup_database") as backup:
            with self.assertRaisesRegex(ValueError, "Never repeat preparation"):
                q.prepare(SimpleNamespace(binding=self.root / "binding.json"))
        backup.assert_not_called()


class ParserAndBackupTests(unittest.TestCase):
    def test_strict_json_rejects_duplicates_and_nonfinite_values(self):
        for raw in (b'{"state":"started","state":"finished"}', b'{"value":NaN}', b'{"value":Infinity}'):
            with self.assertRaises(ValueError):
                q.parse_json(raw)

    def test_fake_backup_reads_wal_and_closes_both_connections(self):
        with tempfile.TemporaryDirectory(prefix="round5-q2-backup-fixture-", dir=q.ROOT / ".artifacts") as name:
            source = Path(name) / "fake-original.db"
            target = Path(name) / "fresh" / "baseline.db"
            src, dst = mock.Mock(), mock.Mock()
            with mock.patch.object(q.sqlite3, "connect", side_effect=[src, dst]) as connect:
                q.backup_database(source, target)
            self.assertEqual(connect.call_args_list[0], mock.call(source.resolve().as_uri() + "?mode=ro", uri=True))
            self.assertNotIn("immutable", connect.call_args_list[0].args[0])
            src.execute.assert_called_once_with("PRAGMA query_only=ON")
            src.backup.assert_called_once_with(dst, pages=128)
            dst.commit.assert_called_once_with()
            src.close.assert_called_once_with()
            dst.close.assert_called_once_with()
            with mock.patch.object(q.sqlite3, "connect") as connect:
                with self.assertRaises(FileExistsError):
                    q.backup_database(source, target)
            connect.assert_not_called()

    def test_fake_backup_failure_keeps_target_and_closes_connections(self):
        with tempfile.TemporaryDirectory(prefix="round5-q2-backup-fixture-", dir=q.ROOT / ".artifacts") as name:
            target = Path(name) / "candidate.db"
            src, dst = mock.Mock(), mock.Mock()
            src.backup.side_effect = RuntimeError("artificial backup failure")
            with mock.patch.object(q.sqlite3, "connect", side_effect=[src, dst]):
                with self.assertRaisesRegex(RuntimeError, "artificial"):
                    q.backup_database(Path(name) / "fake-original.db", target)
            self.assertTrue(target.exists())
            src.close.assert_called_once_with()
            dst.close.assert_called_once_with()
            dst.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
