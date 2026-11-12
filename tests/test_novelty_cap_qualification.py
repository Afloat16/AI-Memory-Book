import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qualification", ROOT / "scripts/novelty_cap_qualification.py")
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def sample(identity, ranks):
    return {"id": identity, "evidence_ranks": ranks, "complete": all(r is not None for r in ranks),
            "context_sha256": identity + str(ranks), "block_hashes": [], "required_evidence": len(ranks)}


def report(rows):
    return {"configurations": [{"budget_chars": 2000, "tokenizer": "cl100k_base", "budget_tokens": 512,
        "query_results": rows, "metrics": {}, "by_group": {}}]}


class QualificationTests(unittest.TestCase):
    def test_complete_gain_does_not_compensate_for_another_loss(self):
        old = report([sample("a", [1]), sample("b", [None])])
        new = report([sample("a", [None]), sample("b", [1])])
        result = qualification.compare_reports(old, new)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["comparisons"][0]["complete_question_losses"], ["a"])

    def test_annotation_loss_rejects_even_when_both_remain_incomplete(self):
        old, new = report([sample("a", [1, None])]), report([sample("a", [None, 2])])
        result = qualification.compare_reports(old, new)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(result["comparisons"][0]["annotation_losses"]), 1)

    def test_identical_or_improved_evidence_qualifies(self):
        old, new = report([sample("a", [1, None])]), report([sample("a", [1, 2])])
        self.assertEqual(qualification.compare_reports(old, new)["status"], "qualified")
        self.assertEqual(qualification.compare_reports(old, old)["status"], "qualified")

    def test_query_axis_changes_are_not_missing_losses(self):
        with self.assertRaises(ValueError):
            qualification.compare_reports(report([sample("a", [1])]), report([sample("b", [1])]))

    def test_source_and_q2_stage_are_explicit_for_both_roles(self):
        plan = {"sources": {"current": {"commit": "control"}, "cap": {"commit": "candidate"}},
                "phases": [{"name": "A", "token_budgets": [512]}], "variants": qualification.VARIANTS,
                "common": {"repeats": 1}, "cohort": {"seed": 23017},
                "native": {"budget_chars": [2000, 8000], "tokenizers": ["cl100k_base", "o200k_base"]}}
        calls = 0
        for variant in qualification.VARIANTS:
            phase, registered, hp, hb = qualification.worker_spec(plan, "A", variant["name"])
            self.assertEqual(hb["candidate"], plan["sources"][variant["source"]])
            self.assertEqual(registered["helper_stage"] == "candidate-semantic-native", variant["semantic"])
            calls += 256 * len(hp["native"]["budget_chars"]) * len(hp["native"]["tokenizers"]) * len(phase["token_budgets"])
        self.assertEqual(calls, 4096)


if __name__ == "__main__":
    unittest.main()
