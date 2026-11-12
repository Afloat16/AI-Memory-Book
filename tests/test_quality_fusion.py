"""Fusion invariants; fixture scores are not retrieval-quality evidence."""

import copy
import math
import unittest

from memory_book.semantic import fuse_candidates


class ScoreAwareFusionTests(unittest.TestCase):
    def test_strong_lexical_margin_survives_a_semantic_bonus_to_every_other_page(self):
        lexical = [{"id": "anchor", "score": 9.01},
                   *({"id": str(i), "score": 6} for i in range(30))]
        semantic = [{"id": str(i), "semantic_similarity": .9} for i in range(30)]
        semantic.append({"id": "floor", "semantic_similarity": .1})
        self.assertEqual(fuse_candidates(lexical, semantic)[0]["id"], "anchor")

    def test_lexical_rescaling_keeps_order_and_combined_scores(self):
        lexical = [{"id": "a", "score": 12}, {"id": "b", "score": 3}]
        semantic = [{"id": "b", "semantic_similarity": .8},
                    {"id": "c", "semantic_similarity": .6}]
        scaled = [{**row, "score": row["score"] * 1000} for row in lexical]
        self.assertEqual(fuse_candidates(lexical, semantic), fuse_candidates(scaled, semantic))

    def test_equal_cosines_add_no_semantic_confidence_or_page_id_reordering(self):
        lexical = [{"id": "z", "score": 1}, {"id": "a", "score": 1}]
        semantic = [{"id": "other", "semantic_similarity": .7},
                    {"id": "a", "semantic_similarity": .7}]
        result = fuse_candidates(lexical, semantic)
        self.assertEqual([row["id"] for row in result], ["z", "a", "other"])
        self.assertEqual([row["score"] for row in result], [.75, .75, 0])

    def test_absent_route_is_zero_even_when_all_returned_cosines_are_negative(self):
        lexical = [{"id": "a", "score": 10}, {"id": "b", "score": -2}]
        semantic = [{"id": "c", "semantic_similarity": -.1},
                    {"id": "b", "semantic_similarity": -.3}]
        result = {row["id"]: row for row in fuse_candidates(lexical, semantic)}
        self.assertEqual(result["a"]["score"], .75)
        self.assertEqual(result["b"]["score"], 0)
        self.assertEqual(result["c"]["score"], .25)

    def test_zero_lexical_scale_is_finite_and_semantic_rank_can_supply_candidates(self):
        rows = fuse_candidates([{"id": "a", "score": 0}], [
            {"id": "b", "semantic_similarity": .8}, {"id": "c", "semantic_similarity": .4}])
        self.assertEqual(rows[0]["id"], "b")
        self.assertTrue(all(math.isfinite(row["score"]) for row in rows))

    def test_empty_route_preserves_surviving_order_and_does_not_mutate_inputs(self):
        lexical = [{"id": "z", "score": .5}, {"id": "a", "score": 1}]
        semantic = [{"id": "c", "semantic_similarity": .7},
                    {"id": "b", "semantic_similarity": .7}]
        before = copy.deepcopy((lexical, semantic))
        self.assertEqual(fuse_candidates(lexical, []), lexical)
        rows = fuse_candidates([], semantic)
        self.assertEqual([row["id"] for row in rows], ["c", "b"])
        self.assertAlmostEqual(rows[0]["score"], 1 / 61)
        fuse_candidates(lexical, semantic)
        self.assertEqual((lexical, semantic), before)
        self.assertEqual(fuse_candidates([], []), [])

    def test_corrupt_scores_and_duplicate_identities_fail_explicitly(self):
        for value in (math.inf, -math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fuse_candidates([{"id": "a", "score": value}], [])
            with self.subTest(value=value), self.assertRaises(ValueError):
                fuse_candidates([], [{"id": "a", "semantic_similarity": value}])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            fuse_candidates([{"id": "a", "score": 1}, {"id": "a", "score": 2}], [])


if __name__ == "__main__":
    unittest.main()
