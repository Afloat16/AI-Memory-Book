"""Narrow historical Markdown-order repair gates; no retrieval or real data."""
import json
import unittest

from scripts import audit_novelty_probe_results as audit
from scripts import run_novelty_probe as probe


def fixture():
    return {"validation": {"passed": True}, "comparisons": [], "screening": {
        "status": "followup_candidate_exists", "candidates": {
            "no_novelty": {"worth_further_validation": False, "declared_screen_losses": ["fake"],
                           "aggregate_gains": []},
            "capped_novelty_025": {"worth_further_validation": True, "declared_screen_losses": [],
                                   "aggregate_gains": ["fake"]}}}}


class NoveltyResultAuditTests(unittest.TestCase):
    def test_only_registered_display_order_reproduces_saved_markdown(self):
        original = fixture()
        saved = probe.markdown(original)
        restored = json.loads(probe.canonical(original))
        self.assertNotEqual(saved, probe.markdown(restored))
        result = audit.presentation_order_audit(restored, saved)
        self.assertTrue(result["passed"])
        self.assertFalse(result["original_audit_byte_comparison_passed"])
        self.assertEqual(result["registered_order"], list(probe.MODES[1:]))
        self.assertEqual(result["deserialized_order"], sorted(probe.MODES[1:]))

    def test_order_allowance_cannot_hide_changed_numbers_text_or_candidate(self):
        original = fixture()
        saved = probe.markdown(original)
        for mutation in ("number", "text", "candidate"):
            restored = json.loads(probe.canonical(original))
            altered = saved
            if mutation == "number":
                restored["screening"]["candidates"]["no_novelty"]["declared_screen_losses"].append("other")
            elif mutation == "text":
                altered = saved.replace("Development timings", "Final timings")
            else:
                restored["screening"]["candidates"]["additional_candidate"] = {}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit.presentation_order_audit(restored, altered)


if __name__ == "__main__":
    unittest.main()
