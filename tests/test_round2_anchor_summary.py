import copy
import tempfile
import unittest

from scripts import summarize_round2_anchor as summary


class AnchorSummaryTests(unittest.TestCase):
    def test_partial_reports_and_wrong_run_are_not_completed_results(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                summary.collect(directory)
            report = summary.collect(directory, allow_partial=True)
            self.assertEqual(report["status"], "partial")
            markdown = summary.markdown(report)
            self.assertIn("**partial**", markdown)
            lines = markdown.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("|") and set(line) <= set("|:-"):
                    self.assertEqual(line.count("|"), lines[index - 1].count("|"))
        with self.assertRaisesRegex(ValueError, "fixed successful"):
            summary.validate_marker({"stage": "fixture", "status": "completed", "run_id": summary.RUN_ID,
                                     "run_attempt": "2", "source_commit": summary.SOURCE_COMMIT}, "fixture")

    def test_cross_run_differences_remain_visible_instead_of_being_imputed(self):
        prior = {"configurations": [{"budget_tokens": 512, "modes": [
            {"mode": mode, "query_results": [{"id": "q", "context_sha256": "a", "evidence_ranks": [None], "complete": False}]}
            for mode in summary.MODES[:3]]}]}
        current = copy.deepcopy(prior)
        current["configurations"][0]["modes"][1]["query_results"][0].update(context_sha256="b", evidence_ranks=[1], complete=True)
        current["configurations"][0]["modes"].append({"mode": summary.MODES[3], "query_results": []})
        result = summary.control_reproduction(current, prior)
        self.assertEqual(result[0]["modes"][0]["changed_context_ids"], [])
        self.assertEqual(result[0]["modes"][1]["changed_context_ids"], ["q"])
        self.assertEqual(result[0]["modes"][1]["changed_evidence_ids"], ["q"])
        self.assertEqual(result[0]["modes"][1]["changed_annotation_presence_ids"], ["q"])
        self.assertEqual(result[0]["modes"][1]["complete_question_gains"], ["q"])
        current["configurations"][0]["modes"][0]["query_results"][0]["id"] = "other"
        with self.assertRaisesRegex(ValueError, "query sets"):
            summary.control_reproduction(current, prior)


if __name__ == "__main__":
    unittest.main()
