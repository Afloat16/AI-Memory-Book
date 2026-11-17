"""Integrity tests for the development diagnostic, not benchmark score targets."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.engineering_workflow import (
    BACKENDS, PROJECTS, POLICIES, configured_algorithm, executable_checks,
    original_turn, recent_history, retrieve, run, score, select_policy,
    source_errors, visible_sources, workload,
)


class EngineeringWorkflowTests(unittest.TestCase):
    def test_chronology_labels_exist_only_in_the_visible_source_version(self):
        visible = {}
        revisions = []
        for step in workload(0):
            for session in step["sessions"]:
                visible[(session["project"], session["session_id"])] = session
            sources = visible_sources(visible)
            for case in step["cases"]:
                for expected in case["required"] + case["stale"]:
                    self.assertIn(expected["quote"], sources[(case["project"], expected["session_id"], 0)])
                if case["category"] == "source_replacement":
                    text = sources[(case["project"], "active-config", 0)]
                    self.assertNotIn("=64.", text)
                self.assertLessEqual(max(int(session["created_at"][5:7]) for session in visible.values()), step["checkpoint"])
            revisions.append(len(visible))
        self.assertEqual(len({case["id"] for step in workload(0) for case in step["cases"]}), 80)
        self.assertEqual(len(PROJECTS), 8)
        self.assertEqual(revisions[4], revisions[3])  # replacement, not an append

    def test_retrieval_api_never_receives_gold_or_future_source_records(self):
        class Spy:
            def recall(self, *args, **kwargs):
                self.call = (args, kwargs)
                return {"context": "", "results": []}
        spy = Spy()
        retrieve(spy, "book", "current tie_policy", "ranking-online", 900, {})
        self.assertEqual(spy.call, (("current tie_policy",), {
            "project": "ranking-online", "budget_chars": 900,
            "limit": 5, "strategy": "book", "use_cache": False}))

    def test_recent_history_budget_and_provenance_for_truncated_sources(self):
        session = workload(0)[0]["sessions"][0]
        sessions = {(session["project"], session["session_id"]): session}
        for cap in (1, 80, 160, 2000):
            response = recent_history(sessions, session["project"], cap)
            self.assertLessEqual(len(response["context"]), cap)
            self.assertEqual(source_errors(response, visible_sources(sessions), session["project"]), [])

    def test_valid_citation_cannot_launder_fabricated_or_cross_project_text(self):
        session = workload(0)[0]["sessions"][0]
        sessions = {(session["project"], session["session_id"]): session}
        sources = visible_sources(sessions)
        response = recent_history(sessions, session["project"], 2000)
        self.assertEqual(source_errors(response, sources, session["project"]), [])
        response["results"][0]["text"] += " FABRICATED POLICY"
        response["context"] += " FABRICATED POLICY"
        self.assertTrue(source_errors(response, sources, session["project"]))
        response = recent_history(sessions, session["project"], 2000)
        self.assertTrue(source_errors(response, sources, "different-project"))
        self.assertTrue(source_errors(response, {}, session["project"]))

    def test_gold_must_survive_budgeting_and_cite_its_original_source(self):
        step = workload(0)[0]
        session, case = step["sessions"][0], step["cases"][0]
        sessions = {(session["project"], session["session_id"]): session}
        response = recent_history(sessions, session["project"], 2000)
        self.assertTrue(score(case, response, visible_sources(sessions), 2000)["complete_evidence"])
        response["context"] = ""
        self.assertFalse(score(case, response, visible_sources(sessions), 2000)["complete_evidence"])
        response = recent_history(sessions, session["project"], 2000)
        response["results"][0]["source_refs"][0]["session_id"] = "unseen-future"
        self.assertFalse(score(case, response, visible_sources(sessions), 2000)["complete_evidence"])

    def test_fixed_consumer_has_executable_distinguishing_cases_for_each_policy(self):
        for family, (_, policies) in POLICIES.items():
            for expected in policies:
                self.assertTrue(executable_checks(family, expected, expected)["all_passed"])
                for wrong in policies:
                    if wrong != expected:
                        self.assertFalse(executable_checks(family, wrong, expected)["all_passed"])
                self.assertFalse(executable_checks(family, None, expected)["all_passed"])
        self.assertEqual(configured_algorithm("attention", "zeros", ([1000., 999.], [True, False])), [1., 0.])

    def test_consumer_distinguishes_current_and_historical_without_using_gold(self):
        hits = [{"text": "tie_policy=stable_input", "created_at": "2026-01-01"},
                {"text": "tie_policy=id_ascending", "created_at": "2026-03-01"}]
        response = {"results": hits, "context": "\n".join(hit["text"] for hit in hits)}
        self.assertEqual(select_policy("ranking", "current policy", response), "id_ascending")
        self.assertEqual(select_policy("ranking", "original policy", response), "stable_input")
        response["context"] = hits[0]["text"]
        self.assertEqual(select_policy("ranking", "current policy", response), "stable_input")

    def test_small_run_preserves_raw_samples_and_reports_integrity_not_performance_gate(self):
        small = workload(0)[:1]
        small[0]["sessions"] = small[0]["sessions"][:2]
        small[0]["cases"] = small[0]["cases"][:2]
        with tempfile.TemporaryDirectory() as directory, patch("benchmarks.engineering_workflow.workload", return_value=small):
            report = run(directory, budgets=(1200,), repeats=2, noise_per_step=0)
            self.assertEqual(report["status"], "completed")
            self.assertEqual({cell["backend"] for cell in report["summary"]}, set(BACKENDS))
            self.assertEqual(report["evidence_level"], "synthetic_development_proxy")
            raw = [json.loads(line) for line in (Path(directory) / "raw.jsonl").read_text().splitlines()]
            self.assertEqual(len(raw), 8)
            self.assertTrue(all(len(row["latency_ms"]) == 2 for row in raw))
            self.assertIn("store.py", report["runtime"]["files"])
            with self.assertRaisesRegex(ValueError, "fresh directory"):
                run(directory)


if __name__ == "__main__":
    unittest.main()
