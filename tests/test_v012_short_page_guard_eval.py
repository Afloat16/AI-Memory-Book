"""Independent checks using the retained short-page allocation counterexample."""
import copy
import json
import unittest
from unittest.mock import patch

from benchmarks import v012_short_page_guard_eval as evaluation


class ShortPageGuardEvaluationTests(unittest.TestCase):
    def fixture(self):
        evaluation.binding()
        original = json.loads((evaluation.ROOT / evaluation.ORIGINAL).read_text())
        row = copy.deepcopy(original["regressions"][0])
        response = row["control"]
        pages = {h["id"]: row["original_pages"][h["id"]] for h in response["results"]}
        return {"short_record_chars": row["short_record_chars"], "budget_chars": row["budget_chars"],
                "response": response, "original_pages": pages,
                "control_current_present": True, "current_present": True}

    def test_original_counterexamples_have_independently_verified_current_source(self):
        controls, failures = evaluation.controls()
        self.assertEqual(len(controls), 482)
        self.assertEqual(sum(controls.values()), 434)
        self.assertEqual(len(failures), 34)

    def test_complete_matrix_and_producer_claims_are_checked(self):
        row = self.fixture()
        key = (row["short_record_chars"], row["budget_chars"])
        with patch.object(evaluation, "controls", return_value=({key: True}, {key})):
            summary = evaluation.validate_rows([row])
            self.assertEqual(summary["lost_recorded_controls"], [])
            self.assertEqual(summary["original_regressions_recovered"], 1)
            for values in ([], [row, row]):
                with self.assertRaises(ValueError):
                    evaluation.validate_rows(values)
            for field in ("current_present", "control_current_present"):
                changed = copy.deepcopy(row)
                changed[field] = False
                with self.assertRaises(ValueError):
                    evaluation.validate_rows([changed])

    def test_a_budget_or_scope_failure_cannot_count_as_guard_success(self):
        for kind in ("budget", "scope", "offset", "context", "original"):
            row = self.fixture()
            if kind == "budget":
                row["response"]["budget_chars"] += 1
            elif kind == "scope":
                row["response"]["results"][0]["source_refs"][0]["project"] = "trainer-copy"
            elif kind == "offset":
                row["response"]["results"][0]["source_refs"][0]["start"] += 1
            elif kind == "context":
                row["response"]["context"] += "\nsteps are now 2"
                row["response"]["context_chars"] = len(row["response"]["context"])
            else:
                page = next(iter(row["original_pages"].values()))
                page["content"] = page["content"].replace("now 2", "now 8")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                evaluation.observed(row["response"], row["original_pages"], row["short_record_chars"], row["budget_chars"])

    def test_independent_review_metadata_counterexamples_are_rejected(self):
        for kind in ("span", "missing_refs", "full_turn", "full_message", "full_offset", "snippet_message", "date"):
            row = self.fixture()
            hit = row["response"]["results"][0]
            page = row["original_pages"][hit["id"]]
            if kind == "span":
                hit["excerpt_spans"] = [[999999, 1000000]]
            elif kind == "missing_refs":
                page["source_refs"] = []
            elif kind == "full_turn":
                page["source_refs"][0]["turn_index"] = 999999
            elif kind == "full_message":
                page["source_refs"][0]["message_indices"] = [999999]
            elif kind == "full_offset":
                page["source_refs"][0]["start"] = 999999
            elif kind == "snippet_message":
                hit["source_refs"][0]["message_indices"] = [999999]
            else:
                prior = hit["created_at"]
                hit["created_at"] = page["created_at"] = "2099-01-01T00:00:00+00:00"
                row["response"]["context"] = row["response"]["context"].replace(prior, hit["created_at"])
                row["response"]["context_chars"] = len(row["response"]["context"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                evaluation.observed(row["response"], row["original_pages"], row["short_record_chars"], row["budget_chars"])


if __name__ == "__main__":
    unittest.main()
