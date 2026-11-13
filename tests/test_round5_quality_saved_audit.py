"""Coordinate regressions for offline classification, without a Book/database."""
import unittest

from scripts.round5_quality_saved_audit import classify_missing, reference_covers


class SavedEvidenceCoordinateTests(unittest.TestCase):
    def test_role_prefix_is_not_sentence(self):
        self.assertFalse(reference_covers("ab", {"turn_start": 0, "turn_end": 2}, "USER: ab"))

    def test_complete_sentence_without_role_prefix(self):
        self.assertTrue(reference_covers("ab", {"turn_start": 6, "turn_end": 8}, "USER: ab"))

    def test_original_whitespace_and_normalized_evidence(self):
        sentence = "  exact   evidence  "
        original = "USER: " + sentence
        self.assertTrue(reference_covers(sentence, {"turn_start": 8, "turn_end": 24}, original))
        self.assertFalse(reference_covers(sentence, {"turn_start": 8, "turn_end": 12}, original))

    def test_invalid_canonical_turn_coordinates_rejected(self):
        for lo, hi in ((-1, 2), (0, 9), (5, 3), (False, 2)):
            with self.subTest(lo=lo, hi=hi), self.assertRaises(ValueError):
                reference_covers("ab", {"turn_start": lo, "turn_end": hi}, "USER: ab")

    def test_missing_classification_uses_original_reference_rule(self):
        required = [("s1", 0, "ab"), ("s2", 1, "cd"), ("s3", 2, "ef"), ("s4", 3, "gh")]
        originals = {("p", sid, index): "USER: " + sentence for sid, index, sentence in required}
        sources = [[{"project": "p", "session_id": "s2", "turn_index": 0, "turn_start": 0, "turn_end": 8},
                    {"project": "p", "session_id": "s3", "turn_index": 2, "turn_start": 0, "turn_end": 2},
                    {"project": "p", "session_id": "s4", "turn_index": 3, "turn_start": 6, "turn_end": 8}]]
        counts, missing = classify_missing(required, [None] * 4, sources, "p", originals)
        self.assertEqual(list(counts.values()), [1, 1, 1, 1])
        self.assertEqual([row["annotation_index"] for row in missing], [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()
