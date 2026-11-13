"""Artificial saved-result rejection tests; no retrieval or model execution."""
import copy
import gzip
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round5_compatibility as evaluation


def bound():
    return {"ids": ["invented-one", "invented-two"],
            "sources": {"baseline": {"commit": "a" * 40, "runtime_sha256": "b" * 64},
                        "candidate": {"commit": "c" * 40, "runtime_sha256": "d" * 64}}}


def fixture(kind="char", label="baseline", repetition=0, elapsed=1.0):
    frozen = bound()
    rows, ledger = [], []
    for number, config in enumerate(evaluation.configurations(kind)):
        identities = list(frozen["ids"])
        random.Random(51256 + 1009 * repetition + number).shuffle(identities)
        for identity in identities:
            row = {"query_id": identity, "configuration": config, "payload_sha256": "1" * 64,
                   "context_sha256": "2" * 64, "reference_tokens": {name: 9 for name in evaluation.ENCODINGS},
                   "context_chars": 36, "result_count": 1,
                   "errors": {name: 0 for name in evaluation.ERRORS},
                   "elapsed_ms": elapsed if kind == "char" else None}
            rows.append(row)
            ledger.extend([{"state": "started", "query_id": identity, "configuration": config},
                           {"state": "finished", **row}])
    report = {"version": evaluation.VERSION, "status": "completed", "kind": kind, "label": label,
              "round": repetition, "source": frozen["sources"][label], "dataset_sha256": evaluation.DATA_HASH,
              "started": len(rows), "finished": len(rows), "expected_calls": len(rows), "rows": rows,
              "originals_unchanged": True, "index_unchanged": True, "recall_cache_rows": 0,
              "started_monotonic_ns": 10, "finished_monotonic_ns": 20}
    return frozen, report, ledger


class SavedWorkerTests(unittest.TestCase):
    def test_registered_addendum_is_required_and_cannot_be_replaced(self):
        plan = (evaluation.ROOT / evaluation.PLAN).read_bytes()
        addendum = (evaluation.ROOT / evaluation.ADDENDUM).read_bytes()
        expected = {evaluation.PLAN_COMMIT + ":" + evaluation.PLAN: plan,
                    evaluation.ADDENDUM_COMMIT + ":" + evaluation.ADDENDUM: addendum,
                    evaluation.C_SCOPE_COMMIT + ":" + evaluation.C_SCOPE:
                        (evaluation.ROOT / evaluation.C_SCOPE).read_bytes(),
                    evaluation.D_SCOPE_COMMIT + ":" + evaluation.D_SCOPE:
                        (evaluation.ROOT / evaluation.D_SCOPE).read_bytes()}
        with patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]):
            evaluation.registered()
        expected[evaluation.ADDENDUM_COMMIT + ":" + evaluation.ADDENDUM] = b"{}\n"
        with patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]), \
                self.assertRaisesRegex(ValueError, "addendum changed"):
            evaluation.registered()

    def test_canonical_row_scope_is_required_and_cannot_be_replaced(self):
        expected = {commit + ":" + path: (evaluation.ROOT / path).read_bytes()
                    for commit, path in ((evaluation.PLAN_COMMIT, evaluation.PLAN),
                                         (evaluation.ADDENDUM_COMMIT, evaluation.ADDENDUM),
                                         (evaluation.C_SCOPE_COMMIT, evaluation.C_SCOPE),
                                         (evaluation.D_SCOPE_COMMIT, evaluation.D_SCOPE))}
        with patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]):
            evaluation.registered()
        expected[evaluation.C_SCOPE_COMMIT + ":" + evaluation.C_SCOPE] = b"{}\n"
        with patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]), \
                self.assertRaisesRegex(ValueError, "canonical-row scope changed"):
            evaluation.registered()

    def test_derived_map_scope_requires_exact_registered_commit_bytes(self):
        expected = {commit + ":" + path: (evaluation.ROOT / path).read_bytes()
                    for commit, path in ((evaluation.PLAN_COMMIT, evaluation.PLAN),
                                         (evaluation.ADDENDUM_COMMIT, evaluation.ADDENDUM),
                                         (evaluation.C_SCOPE_COMMIT, evaluation.C_SCOPE),
                                         (evaluation.D_SCOPE_COMMIT, evaluation.D_SCOPE))}
        with patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]):
            evaluation.registered()
        expected[evaluation.D_SCOPE_COMMIT + ":" + evaluation.D_SCOPE] = b"{}\n"
        with patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]), \
                self.assertRaisesRegex(ValueError, "derived-map scope changed"):
            evaluation.registered()

    def test_derived_map_scope_requires_the_fixed_digest_even_if_git_agrees(self):
        expected = {commit + ":" + path: (evaluation.ROOT / path).read_bytes()
                    for commit, path in ((evaluation.PLAN_COMMIT, evaluation.PLAN),
                                         (evaluation.ADDENDUM_COMMIT, evaluation.ADDENDUM),
                                         (evaluation.C_SCOPE_COMMIT, evaluation.C_SCOPE),
                                         (evaluation.D_SCOPE_COMMIT, evaluation.D_SCOPE))}
        read_bytes = Path.read_bytes
        changed = expected[evaluation.D_SCOPE_COMMIT + ":" + evaluation.D_SCOPE] + b"\n"
        expected[evaluation.D_SCOPE_COMMIT + ":" + evaluation.D_SCOPE] = changed

        def altered(path):
            return changed if path == evaluation.ROOT / evaluation.D_SCOPE else read_bytes(path)

        with patch.object(Path, "read_bytes", altered), \
                patch.object(evaluation, "git", side_effect=lambda _, name: expected[name]), \
                self.assertRaisesRegex(ValueError, "Derived-map scope hash"):
            evaluation.registered()

    def test_binding_rejects_missing_or_changed_derived_map_registration(self):
        base = {"version": evaluation.VERSION, "plan_commit": evaluation.PLAN_COMMIT, "files": {},
                "addendum_commit": evaluation.ADDENDUM_COMMIT,
                "addendum_sha256": evaluation.sha((evaluation.ROOT / evaluation.ADDENDUM).read_bytes()),
                "canonical_scope_commit": evaluation.C_SCOPE_COMMIT,
                "canonical_scope_sha256": evaluation.sha((evaluation.ROOT / evaluation.C_SCOPE).read_bytes()),
                "derived_scope_commit": evaluation.D_SCOPE_COMMIT,
                "derived_scope_sha256": evaluation.D_SCOPE_SHA256}
        for field, value in (("derived_scope_commit", None), ("derived_scope_commit", "0" * 40),
                             ("derived_scope_sha256", None), ("derived_scope_sha256", "0" * 64)):
            changed = copy.deepcopy(base)
            if value is None:
                changed.pop(field)
            else:
                changed[field] = value
            with self.subTest(field=field, value=value), \
                    patch.object(evaluation, "registered"), patch.object(evaluation, "registry", return_value={}), \
                    patch.object(evaluation, "read", return_value=changed), \
                    self.assertRaisesRegex(ValueError, "derived-map scope binding changed"):
                evaluation.binding(Path("invented-unused-binding.json"))

    def test_valid_character_and_token_rows(self):
        for kind in ("char", "tokens"):
            frozen, report, ledger = fixture(kind)
            evaluation.verify_worker(report, frozen, ledger)

    def test_missing_or_duplicate_query_rejected(self):
        for mutation in ("missing", "duplicate", "reorder"):
            frozen, report, ledger = fixture()
            if mutation == "missing":
                report["rows"].pop()
            elif mutation == "duplicate":
                report["rows"][1] = copy.deepcopy(report["rows"][0])
            else:
                report["rows"].reverse()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_incomplete_attempt_and_wrong_source_rejected(self):
        for key, value in (("status", "running"), ("finished", 1), ("source", {})):
            frozen, report, ledger = fixture()
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_ledger_order_and_payload_rejected(self):
        for mutation in ("order", "payload", "unfinished"):
            frozen, report, ledger = fixture()
            if mutation == "order":
                ledger.reverse()
            elif mutation == "payload":
                ledger[1] = {**ledger[1], "payload_sha256": "3" * 64}
            else:
                ledger.pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_every_recorded_invariant_is_enforced(self):
        for error in evaluation.ERRORS:
            frozen, report, ledger = fixture()
            report["rows"][0]["errors"][error] = 1
            with self.subTest(error=error), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_mutated_sources_indexes_or_cache_rejected(self):
        for key, value in (("originals_unchanged", False), ("index_unchanged", False), ("recall_cache_rows", 1)):
            frozen, report, ledger = fixture()
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_nonfinite_zero_and_wrong_boundary_timing_rejected(self):
        for kind, value in (("char", float("inf")), ("char", float("nan")), ("char", 0),
                            ("char", None), ("tokens", 1.0)):
            frozen, report, ledger = fixture(kind)
            report["rows"][0]["elapsed_ms"] = value
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_reference_count_digest_and_lifetime_validation(self):
        for mutation in ("count", "hash", "lifetime"):
            frozen, report, ledger = fixture()
            if mutation == "count":
                report["rows"][0]["reference_tokens"]["cl100k_base"] = -1
            elif mutation == "hash":
                report["rows"][0]["payload_sha256"] = "not-a-digest"
            else:
                report["finished_monotonic_ns"] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)

    def test_zero_error_flags_cannot_hide_saved_budget_or_result_overflow(self):
        for field in ("tokens", "chars", "results"):
            frozen, report, ledger = fixture("tokens")
            row = report["rows"][0]
            if field == "tokens":
                row["reference_tokens"][row["configuration"]["tokenizer"]] = 513
            elif field == "chars":
                row["context_chars"] = 8001
            else:
                row["result_count"] = 6
            ledger[1] = {"state": "finished", **row}
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluation.verify_worker(report, frozen, ledger)


class MatrixAuditTests(unittest.TestCase):
    def run_audit(self, location, candidate_ms=1.0, mutation=None):
        location = Path(location)
        binding = location / "binding.json"
        binding.write_text("{}\n")
        intent = location / "intent.json"
        intent.write_text("{}\n")
        frozen = bound()
        execution = {"host": {"boot": "invented-boot"}}
        for index, item in enumerate(evaluation.schedule()):
            _, report, ledger = fixture(item["kind"], item["label"], item["round"],
                                       candidate_ms if item["label"] == "candidate" else 1.0)
            report.update(binding_sha256=evaluation.sha(binding.read_bytes()),
                          intent_sha256=evaluation.sha(intent.read_bytes()), host=execution["host"],
                          started_monotonic_ns=100 * index + 10, finished_monotonic_ns=100 * index + 20)
            if mutation == "order" and index == 3:
                report["started_monotonic_ns"] = 1
            if mutation == "host" and index == 3:
                report["host"] = {"boot": "replacement-boot"}
            if mutation == "payload" and index == 3:
                report["rows"][0]["payload_sha256"] = "4" * 64
                ledger[1]["payload_sha256"] = "4" * 64
            path = location / evaluation.filename(item)
            ledger_path = path.with_name(path.name + ".attempts.jsonl")
            ledger_path.write_bytes(b"".join(evaluation.raw(event) for event in ledger))
            report["ledger_sha256"] = evaluation.sha(ledger_path.read_bytes())
            evaluation.save(path, report)
        args = SimpleNamespace(binding=binding, intent=intent, reports=location, output=location / "audit.json")
        with patch.object(evaluation, "binding", return_value=frozen), \
                patch.object(evaluation, "execution_intent", return_value=execution):
            status = evaluation.audit(args)
        return status, evaluation.read(args.output)

    def test_valid_matrix_is_accepted(self):
        with tempfile.TemporaryDirectory() as location:
            status, report = self.run_audit(location)
        self.assertEqual(status, 0)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["workers"], 10)
        self.assertEqual(report["retrieval_calls_during_audit"], 0)

    def test_character_regression_preserved_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as location:
            status, report = self.run_audit(location, candidate_ms=1.1)
        self.assertEqual(status, 1)
        self.assertFalse(report["accepted"])
        self.assertAlmostEqual(report["character_diagnostic"]["candidate_change_percent"]["p95_ms"], 10)

    def test_changed_boot_order_or_paired_output_rejected(self):
        for mutation in ("host", "order", "payload"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as location, self.assertRaises(ValueError):
                self.run_audit(location, mutation=mutation)

    def test_schedule_retains_all_four_abba_rounds(self):
        char = [item for item in evaluation.schedule() if item["kind"] == "char"]
        self.assertEqual([item["label"] for item in char],
                         ["baseline", "candidate", "candidate", "baseline", "candidate", "baseline", "baseline", "candidate"])
        self.assertEqual(len({evaluation.filename(item) for item in evaluation.schedule()}), 10)


if __name__ == "__main__":
    unittest.main()
