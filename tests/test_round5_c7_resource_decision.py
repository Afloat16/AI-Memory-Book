"""A documented resource decision cannot replace numerical or identity gates.

Only small metadata fixtures and saved reports are read. No product, tokenizer,
SDK, retrieval, or performance workload is executed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts import finish_round5_c7_release_docs as validator


def fixture():
    context = {"original_result_commit": "a" * 40, "report_sha256": "b" * 64,
        "summary_sha256": "c" * 64, "sources": {
            "baseline": {"commit": "d" * 40, "runtime_sha256": "e" * 64},
            "candidate": {"commit": "f" * 40, "runtime_sha256": "0" * 64}},
        "binding_sha256": "1" * 64, "original_plan_sha256": "2" * 64}
    triggers = [
        {"cohort": "synthetic61", "metric": "runtime_import_ms",
         "baseline": {"samples": 4, "mean": 27.89452125},
         "candidate": {"samples": 4, "mean": 31.09176525}, "mean_change_percent": 11.461906699689294},
        {"cohort": "public1015", "metric": "runtime_import_ms",
         "baseline": {"samples": 4, "mean": 27.76485525},
         "candidate": {"samples": 4, "mean": 30.75521}, "mean_change_percent": 10.770287556244341},
        {"cohort": "public1015", "metric": "native_open_ms",
         "baseline": {"samples": 4, "mean": 23.82188725},
         "candidate": {"samples": 4, "mean": 28.92236675}, "mean_change_percent": 21.410895981803456}]
    acceptance = {"numeric_gate_passed": True, "accepted": False,
        "regressions_above_five_percent": [], "resource_review": triggers}
    reviews, records = {}, []
    for number, path in enumerate(sorted(validator.RESOURCE_REVIEW_PATHS)):
        review = {"reviewer": f"independent-{number}",
            "recommendation": "accept_disclosed_startup_tradeoff",
            "original_automatic_accepted": False, "numeric_gate_passed": True,
            "no_new_measurements": True,
            **{key: context[key] for key in ("original_result_commit", "report_sha256", "summary_sha256", "sources")},
            "reviewed_trigger_keys": [{key: row[key] for key in ("cohort", "metric")} for row in triggers]}
        raw = json.dumps(review, sort_keys=True).encode()
        reviews[path] = raw
        records.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest()})
    decision = {"schema_version": 1, "status": "approved_after_independent_resource_review",
        "release_accepted": True, "original_automatic_accepted": False, "numeric_gate_passed": True,
        "thresholds_changed": False, "raw_reports_changed": False, "measurements_repeated": False,
        **context, "triggered_resources": copy.deepcopy(triggers), "independent_reviews": records,
        "rationale": ["Accept the disclosed absolute setup cost for persistent connections."],
        "limitations": ["No subphase causal attribution or universal speed claim."]}
    return decision, reviews, acceptance, context


class ResourceDecisionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.decision, self.reviews, self.acceptance, self.context = fixture()

    def validate(self):
        return validator.validate_resource_decision(self.decision, self.reviews, self.acceptance, self.context)

    def change_review(self, mutate):
        path = sorted(self.reviews)[0]
        review = json.loads(self.reviews[path])
        mutate(review)
        raw = json.dumps(review, sort_keys=True).encode()
        self.reviews[path] = raw
        next(r for r in self.decision["independent_reviews"] if r["path"] == path)["sha256"] = hashlib.sha256(raw).hexdigest()

    def test_two_bound_reviews_accept_only_the_resource_decision_without_mutation(self):
        before = copy.deepcopy((self.decision, self.reviews, self.acceptance, self.context))
        self.assertIs(self.validate(), self.decision)
        self.assertEqual((self.decision, self.reviews, self.acceptance, self.context), before)
        self.assertIs(self.acceptance["accepted"], False)

    def test_numerical_failure_or_latency_regression_cannot_be_overridden(self):
        for field, value in (("numeric_gate_passed", False),
                ("regressions_above_five_percent", [{"metric": "p95", "change_percent": 6}])):
            with self.subTest(field=field):
                self.setUp()
                self.acceptance[field] = value
                with self.assertRaisesRegex(ValueError, "numerical failure"):
                    self.validate()

    def test_changed_raw_verdict_is_rejected_in_acceptance_decision_and_reviews(self):
        self.acceptance["accepted"] = True
        with self.assertRaises(ValueError):
            self.validate()
        self.setUp()
        self.decision["original_automatic_accepted"] = True
        with self.assertRaises(ValueError):
            self.validate()
        self.setUp()
        self.change_review(lambda r: r.update(original_automatic_accepted=True))
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_explicit_approval_or_policy_change_is_rejected(self):
        for field, value in (("status", "pending"), ("release_accepted", False),
                ("numeric_gate_passed", False), ("thresholds_changed", True),
                ("raw_reports_changed", True), ("measurements_repeated", True)):
            with self.subTest(field=field):
                self.setUp()
                self.decision[field] = value
                with self.assertRaises(ValueError):
                    self.validate()

    def test_wrong_report_source_binding_plan_or_result_decision_is_rejected(self):
        for field in self.context:
            with self.subTest(field=field):
                self.setUp()
                self.decision[field] = "another-identity"
                with self.assertRaisesRegex(ValueError, "another source, binding or original result"):
                    self.validate()

    def test_changed_review_identity_is_rejected_even_with_new_matching_checksum(self):
        for field in ("original_result_commit", "report_sha256", "summary_sha256", "sources"):
            with self.subTest(field=field):
                self.setUp()
                self.change_review(lambda r, key=field: r.update({key: "another-identity"}))
                with self.assertRaisesRegex(ValueError, "another original result"):
                    self.validate()

    def test_one_missing_or_duplicated_independent_review_is_rejected(self):
        for kind in ("missing-record", "missing-bytes", "duplicate-path"):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == "missing-record":
                    self.decision["independent_reviews"].pop()
                elif kind == "missing-bytes":
                    self.reviews.pop(sorted(self.reviews)[0])
                else:
                    self.decision["independent_reviews"][1] = copy.deepcopy(self.decision["independent_reviews"][0])
                with self.assertRaisesRegex(ValueError, "Both separately recorded"):
                    self.validate()

    def test_changed_review_bytes_are_rejected(self):
        self.reviews[sorted(self.reviews)[0]] += b"\n"
        with self.assertRaisesRegex(ValueError, "review bytes changed"):
            self.validate()

    def test_review_must_accept_the_tradeoff_without_new_measurement(self):
        for field, value in (("recommendation", "reject"), ("numeric_gate_passed", False), ("no_new_measurements", False)):
            with self.subTest(field=field):
                self.setUp()
                self.change_review(lambda r, k=field, v=value: r.update({k: v}))
                with self.assertRaisesRegex(ValueError, "does not accept"):
                    self.validate()

    def test_omitted_duplicated_or_modified_trigger_samples_are_rejected(self):
        for kind in ("drop-decision", "changed-sample", "drop-review", "duplicate-review-key"):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == "drop-decision":
                    self.decision["triggered_resources"].pop()
                elif kind == "changed-sample":
                    self.decision["triggered_resources"][0]["candidate"]["mean"] = 0
                elif kind == "drop-review":
                    self.change_review(lambda r: r["reviewed_trigger_keys"].pop())
                else:
                    self.change_review(lambda r: r["reviewed_trigger_keys"].__setitem__(2, copy.deepcopy(r["reviewed_trigger_keys"][0])))
                with self.assertRaises(ValueError):
                    self.validate()

    def test_no_unexplained_or_unqualified_approval(self):
        for field in ("rationale", "limitations"):
            with self.subTest(field=field):
                self.setUp()
                self.decision[field] = []
                with self.assertRaisesRegex(ValueError, "explicit reasons and evidence limits"):
                    self.validate()

    def test_both_disclosures_preserve_failed_raw_verdict_and_absolute_costs(self):
        evidence = {"resource_decision": self.decision, "g": self.acceptance}
        for language in ("en", "zh"):
            with self.subTest(language=language):
                text = validator.resource_disclosure(evidence, "resource-review.md", language)
                for expected in ("accepted:false", "3.197", "2.990", "5.100", "21.4109%", "resource-review.md"):
                    self.assertIn(expected, text)
                self.assertNotIn("no resource exception", text.lower())


class RecordedResourceDecisionTests(unittest.TestCase):
    def test_recorded_decision_binds_both_original_reviews_and_original_report(self):
        root = Path(__file__).resolve().parents[1]
        prefix = root / "benchmarks/reports/round5-c7-performance-43563390252-1"
        report_raw = (prefix / "report.json.gz").read_bytes()
        summary_raw = (prefix / "report.summary.json").read_bytes()
        summary = json.loads(summary_raw)
        decision = json.loads((root / validator.RESOURCE_DECISION_PATH).read_bytes())
        reviews = {path: (root / path).read_bytes() for path in validator.RESOURCE_REVIEW_PATHS}
        context = {"original_result_commit": "03838687f7d8d5995c2afa4c22ff5c30e7b12750",
            "report_sha256": hashlib.sha256(report_raw).hexdigest(),
            "summary_sha256": hashlib.sha256(summary_raw).hexdigest(),
            "sources": summary["run"]["binding"]["sources"],
            "binding_sha256": summary["run"]["binding_sha256"],
            "original_plan_sha256": summary["run"]["plan_sha256"]}
        validated = validator.validate_resource_decision(decision, reviews, summary["acceptance"], context)
        self.assertIs(validated, decision)
        self.assertIs(summary["acceptance"]["accepted"], False)
        self.assertIs(summary["acceptance"]["numeric_gate_passed"], True)


if __name__ == "__main__":
    unittest.main()
