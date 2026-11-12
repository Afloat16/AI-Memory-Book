"""Synthetic-record integrity and bounded-boost checks; no corpus retrieval."""
import copy
import json
import random
import unittest
from unittest.mock import patch

from scripts import run_novelty_probe as probe


def fixture():
    plan, binding = probe.registered()
    plan = copy.deepcopy(plan)
    for cohort in plan["cohorts"]:
        cohort["queries"] = 2
    report = {"plan": plan, "binding": binding, "workers": [], "error": None,
              "evaluator_hashes": {"fake": "digest"}, "evaluator_unchanged": True}
    for cohort in plan["cohorts"]:
        ids = [cohort["name"] + "-fake-0", cohort["name"] + "-fake-1"]
        order = list(ids)
        random.Random(61).shuffle(order)
        for mode in probe.MODES:
            identity = binding["modes"][mode]
            worker = {"cohort": cohort["name"], "mode": mode, "status": "completed",
                "source": {"source_sha256": identity["source_sha256"],
                           "provenance": {"git_commit": identity["commit"], "commit_identifies_source": True}},
                "source_sha256_after": identity["source_sha256"],
                "dataset": {"queries": 2, "sha256": cohort["sha256"]},
                "query_ids": sorted(ids), "query_ids_original_order": ids,
                "evaluator_hashes": report["evaluator_hashes"], "evaluator_unchanged": True,
                "originals_unchanged": True, "indexed_content": {"fake": cohort["name"]},
                "indexed_content_after": {"fake": cohort["name"]}, "cache_rows": 0, "configurations": []}
            for budget in probe.BUDGETS:
                rows = []
                for identity in order:
                    rows.append({"id": identity, "category": "fake", "answerable": True,
                        "required_evidence": 1, "matched_evidence": 1, "complete": True,
                        "reciprocal_rank": 1.0, "evidence_ranks": [1], "stale_ranks": [],
                        "stale_only": False, "stale_before_current": False, "nonempty": True,
                        "returned_characters": 10, "returned_utf8_bytes": 10,
                        "context_size_consistent": True, "budget_violation": False,
                        "duplicate_source_characters": 0, "context_tokens": {e: 3 for e in probe.ENCODINGS},
                        "elapsed_ms": 1.0, "returned_payload_tokens": {e: 20 for e in probe.ENCODINGS},
                        "context_sha256": "fake-context", "diagnostic_groups": ["all", "category:fake"],
                        **{key: 0 for key in probe.INVARIANTS}})
                worker["configurations"].append({"budget_chars": 8000, "budget_tokens": budget,
                    "tokenizer": "cl100k_base", "rows": rows, **probe.summarize(rows)})
            report["workers"].append(worker)
    return plan, binding, report


class NoveltyProbeTests(unittest.TestCase):
    def test_complete_fake_matrix_and_json_reordering(self):
        plan, binding, report = fixture()
        with patch.object(probe, "registered", return_value=(plan, binding)):
            self.assertTrue(probe.validate(report)["passed"])
            first = probe.comparisons(report)
            restored = json.loads(probe.canonical(report))
            self.assertEqual(probe.comparisons(restored), first)
            result = probe.screen(first, complete=True)
            self.assertEqual(result["status"], "stop_both_candidates_rejected_or_no_gain")

    def test_incomplete_source_cache_budget_and_changed_aggregate_fail(self):
        for mutation in ("worker", "budget", "query", "source", "cache", "aggregate"):
            plan, binding, report = fixture()
            if mutation == "worker":
                report["workers"].pop()
            elif mutation == "budget":
                report["workers"][0]["configurations"].pop()
            elif mutation == "query":
                report["workers"][0]["configurations"][0]["rows"].pop()
            elif mutation == "source":
                report["workers"][0]["source_sha256_after"] = "different"
            elif mutation == "cache":
                report["workers"][0]["cache_rows"] = 1
            else:
                report["workers"][0]["configurations"][0]["metrics"]["matched_evidence"] = 9
            with self.subTest(mutation=mutation), patch.object(probe, "registered", return_value=(plan, binding)):
                self.assertFalse(probe.validate(report)["passed"])

    def test_cap_and_stronger_relevance_protection(self):
        for size in range(1, 65):
            for new_count in range(size + 1):
                namespace = {"pending": [{"rid": "page"}], "i": 0,
                             "matched": {"page": set(range(new_count))}, "covered": set(),
                             "qset": set(range(size)), "min": min, "len": len}
                values = {mode: eval(expression, {"__builtins__": {}}, namespace)
                          for mode, expression in probe.EXPRESSIONS.items()}
                self.assertEqual(values["no_novelty"], 1.0)
                self.assertGreaterEqual(values["capped_novelty_025"], 1.0)
                self.assertLessEqual(values["capped_novelty_025"], 1.25)
                self.assertLessEqual(values["capped_novelty_025"], values["default"])
                self.assertGreater(1.26 * values["no_novelty"], values["capped_novelty_025"])

    def test_loss_cannot_be_hidden_by_gains_elsewhere(self):
        plan, binding, report = fixture()
        with patch.object(probe, "registered", return_value=(plan, binding)):
            cells = probe.comparisons(report)
            selected = [c for c in cells if c["mode"] == "no_novelty"]
            selected[0]["baseline"]["metrics"]["complete_evidence_rate"] = .5
            selected[1]["candidate"]["metrics"]["evidence_recall"] = .5
            result = probe.screen(cells, complete=True)
            self.assertFalse(result["candidates"]["no_novelty"]["worth_further_validation"])
            self.assertTrue(result["candidates"]["no_novelty"]["aggregate_gains"])
            self.assertTrue(result["candidates"]["no_novelty"]["declared_screen_losses"])
            self.assertEqual(probe.screen(cells, complete=False)["status"], "incomplete_no_selection")


if __name__ == "__main__":
    unittest.main()
