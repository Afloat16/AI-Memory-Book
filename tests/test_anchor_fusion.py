"""Q2 ordering invariants with invented candidates, never gold evidence."""
import copy
import random
import unittest

from benchmarks.round2_anchor_eval import legacy_rrf
from memory_book.semantic import fuse_candidates


class LexicalAnchorFusionTests(unittest.TestCase):
    def test_preserves_every_candidate_score_and_all_nonanchor_relative_order(self):
        for seed in range(40):
            randomizer = random.Random(seed)
            ids = list(map(str, range(18)))
            randomizer.shuffle(ids)
            lexical = [{"id": name, "score": randomizer.random()} for name in ids[:12]]
            randomizer.shuffle(ids)
            semantic = [{"id": name, "semantic_similarity": randomizer.random()} for name in ids[:14]]
            before = copy.deepcopy((lexical, semantic))
            original = legacy_rrf(lexical, semantic)
            actual = fuse_candidates(lexical, semantic)
            anchor = lexical[0]["id"]
            self.assertEqual(actual[0]["id"], anchor)
            self.assertEqual([row["id"] for row in actual[1:]], [row["id"] for row in original if row["id"] != anchor])
            self.assertEqual({row["id"]: row for row in actual}, {row["id"]: row for row in original})
            self.assertEqual((lexical, semantic), before)

    def test_existing_lexical_order_wins_over_larger_raw_lexical_score(self):
        lexical = [{"id": "novelty-leader", "score": .001}, {"id": "large-score", "score": 1000}]
        semantic = [{"id": "large-score", "semantic_similarity": .9}]
        actual = fuse_candidates(lexical, semantic)
        self.assertEqual(actual[0]["id"], "novelty-leader")
        self.assertLess(actual[0]["score"], actual[1]["score"])
        self.assertEqual(actual[1]["score"], legacy_rrf(lexical, semantic)[0]["score"])

    def test_anchor_already_first_and_empty_routes_are_exact_legacy_results(self):
        lexical = [{"id": "a", "score": 1}, {"id": "b", "score": 5}]
        semantic = [{"id": "a", "semantic_similarity": .9}, {"id": "c", "semantic_similarity": .5}]
        for left, right in ((lexical, semantic), (lexical, []), ([], semantic), ([], [])):
            self.assertEqual(fuse_candidates(left, right), legacy_rrf(left, right))

    def test_top_five_changes_at_most_one_membership(self):
        lexical = [{"id": "anchor", "score": 1}, *({"id": str(i), "score": 1} for i in range(8))]
        semantic = [{"id": str(i), "semantic_similarity": .9} for i in range(8)]
        old = legacy_rrf(lexical, semantic)
        self.assertNotIn("anchor", {row["id"] for row in old[:5]})
        new = fuse_candidates(lexical, semantic)
        self.assertEqual({row["id"] for row in new[:5]} - {row["id"] for row in old[:5]}, {"anchor"})
        self.assertEqual(len({row["id"] for row in old[:5]} - {row["id"] for row in new[:5]}), 1)


if __name__ == "__main__":
    unittest.main()
