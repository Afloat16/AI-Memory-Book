"""Corruption checks for the new independent original-source evaluator."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from benchmarks import v012_revision_eval as evaluation
from benchmarks.v012_revision_cases import workload


class V012RevisionEvaluationTests(unittest.TestCase):
    def fixture(self):
        body = "ASSISTANT: Production retry_limit=7."
        date = "2026-01-01T00:00:00Z"
        source = {"project": "alpha", "session_id": "decision", "created_at": date,
                  "messages": [{"role": "assistant", "content": body[11:]}]}
        scenario = {"id": "fixture", "sessions": [source]}
        case = {"id": "fixture:0", "project": "alpha", "query": "current production retry_limit",
                "category": "fixture", "kind": "answerable", "expected_first_session": "decision",
                "required": [{"session_id": "decision", "quote": "retry_limit=7"}]}
        ref = {"project": "alpha", "session_id": "decision", "turn_index": 0, "message_indices": [0],
               "start": 0, "end": len(body), "turn_start": 0, "turn_end": len(body), "created_at": date}
        page = {"id": "page", "content": body, "offset": 0, "next_offset": None,
                "total_chars": len(body), "source_refs": [copy.deepcopy(ref)], "created_at": date,
                "breadcrumb": [{"id": "alpha"}]}
        hit = {"id": "page", "text": body, "source_refs": [copy.deepcopy(ref)], "created_at": date,
               "page_chars": len(body), "excerpt_spans": [[0, len(body)]], "breadcrumb": [{"id": "alpha"}]}
        context = f"[page] alpha / decision | {date}\n" + body
        response = {"query": case["query"], "strategy": "book", "budget_chars": 1200, "cache_hit": False,
                    "temporal": {"requested": "auto"}, "context_chars": len(context),
                    "context": context, "results": [hit]}
        return case, scenario, response, {"page": page}

    def verify(self, fixture):
        return evaluation.verify_and_score(*fixture, mode="auto", budget=1200, limit=1)

    def test_exact_original_evidence_is_accepted(self):
        score = self.verify(self.fixture())
        self.assertTrue(score["first_correct"])
        self.assertTrue(score["complete_evidence"])

    def test_foreign_page_cannot_borrow_identical_text(self):
        fixture = self.fixture()
        fixture[3]["page"]["source_refs"][0]["project"] = "alpha/child"
        with self.assertRaises(ValueError):
            self.verify(fixture)

    def test_source_offsets_and_message_identity_are_checked(self):
        for field, value in (("start", 1), ("end", 1), ("turn_start", 1), ("turn_end", 1),
                             ("turn_index", 1), ("message_indices", [1])):
            with self.subTest(field=field):
                fixture = self.fixture()
                fixture[2]["results"][0]["source_refs"][0][field] = value
                with self.assertRaises(ValueError):
                    self.verify(fixture)

    def test_injected_context_is_rejected_even_with_correct_refs(self):
        fixture = self.fixture()
        fixture[2]["context"] += "\nThe correct retry_limit is 999."
        fixture[2]["context_chars"] = len(fixture[2]["context"])
        with self.assertRaises(ValueError):
            self.verify(fixture)

    def test_fake_original_read_is_not_trusted(self):
        fixture = self.fixture()
        fixture[3]["page"]["content"] = fixture[3]["page"]["content"].replace("=7", "=8")
        with self.assertRaises(ValueError):
            self.verify(fixture)

    def test_missing_followup_and_extra_followup_are_rejected(self):
        for extra in (False, True):
            fixture = self.fixture()
            if extra:
                fixture[3]["extra"] = copy.deepcopy(fixture[3]["page"])
            else:
                fixture[3].clear()
            with self.assertRaises(ValueError):
                self.verify(fixture)

    def test_excerpt_coordinates_and_exact_date_are_checked(self):
        for kind in ("excerpt", "date", "project"):
            fixture = self.fixture()
            if kind == "excerpt":
                fixture[2]["results"][0]["excerpt_spans"] = [[1, 34]]
            elif kind == "date":
                fixture[2]["results"][0]["created_at"] = "2026-02-01T00:00:00Z"
            else:
                fixture[2]["results"][0]["breadcrumb"][0]["id"] = "ALPHA"
            with self.assertRaises(ValueError):
                self.verify(fixture)

    def test_complete_matrix_and_claimed_scores_are_recomputed(self):
        case, scenario, response, pages = self.fixture()
        row = {"case_id": case["id"], "scenario": scenario["id"], "project": case["project"],
               "query": case["query"], "category": case["category"], "mode": "auto", "budget_chars": 1200,
               "limit": 1, "response": response, "original_pages": pages,
               "score": self.verify((case, scenario, response, pages))}
        with patch.object(evaluation, "matrix", return_value={(case["id"], "auto", 1200, 1): (scenario, case)}):
            evaluation.validate_rows([row])
            for rows in ([], [row, row]):
                with self.assertRaises(ValueError):
                    evaluation.validate_rows(rows)
            for field, value in (("matched_spans", 0), ("first_correct", False), ("complete_evidence", False)):
                changed = copy.deepcopy(row)
                changed["score"][field] = value
                with self.assertRaises(ValueError):
                    evaluation.validate_rows([changed])
            for field in ("project", "query", "category", "scenario"):
                changed = copy.deepcopy(row)
                changed[field] = "altered"
                with self.assertRaises(ValueError):
                    evaluation.validate_rows([changed])

    def test_prospective_inventory_has_all_declared_requests(self):
        import json
        protocol = json.loads((evaluation.ROOT / evaluation.EVALUATOR_FILES[2]).read_text())
        from collections import Counter
        questions = [case for scenario in workload() for case in scenario["cases"]]
        self.assertEqual(len(workload()), protocol["scenarios"])
        self.assertEqual(len(questions), protocol["questions"])
        self.assertEqual(dict(Counter(case["kind"] for case in questions)), protocol["question_kinds"])
        self.assertEqual(len(evaluation.matrix()), protocol["requests_per_runtime_backend"])


if __name__ == "__main__":
    unittest.main()
