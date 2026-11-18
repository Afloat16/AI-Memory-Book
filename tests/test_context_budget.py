"""Budget conservation and source completeness for short-record allocation."""
import copy
import random
import unittest

from memory_book.context_budget import complete_short_pages


def allocation(length, allowance, identity):
    return ({"id": identity, "content": "x" * length}, f"[{identity}] project / source\n", allowance)


class CompleteShortPagesTests(unittest.TestCase):
    def test_short_original_record_can_finish_without_dropping_a_result(self):
        records = [allocation(156, 146, "decision")]
        records += [allocation(367, 146, str(i)) for i in range(4)]
        original = copy.deepcopy(records)
        result = complete_short_pages(records)
        self.assertEqual(result[0][2], len(result[0][0]["content"]))
        self.assertEqual([r[0]["id"] for r in result], [r[0]["id"] for r in original])
        self.assertEqual(sum(r[2] for r in result), sum(r[2] for r in original))
        self.assertTrue(all(r[2] >= 120 for r in result[1:]))
        self.assertEqual(records, original)

    def test_already_complete_sources_and_short_fragments_never_donate(self):
        records = [allocation(150, 140, "short"), allocation(400, 400, "complete"),
                   allocation(200, 180, "partial-short")]
        self.assertEqual(complete_short_pages(records), records)

    def test_insufficient_slack_does_not_partially_rebalance(self):
        records = [allocation(240, 130, "short"), allocation(500, 150, "long")]
        self.assertEqual(complete_short_pages(records), records)

    def test_one_tiny_excerpt_retains_its_original_allowance(self):
        for length in (30, 150, 500):
            records = [allocation(length, 9, "only")]
            self.assertEqual(complete_short_pages(records), records)
        self.assertEqual(complete_short_pages([]), [])

    def test_fitting_current_turn_cannot_lose_its_reserved_space(self):
        # This longer page's 147-character current turn already fits. A
        # shorter allowance could make the caller fall back to an old turn.
        records = [allocation(900, 147, "current"), allocation(180, 150, "memo")]
        self.assertEqual(complete_short_pages(records, protected_ids=frozenset({"current"})), records)
        with_donor = records + [allocation(600, 170, "older-other")]
        result = complete_short_pages(with_donor, protected_ids=frozenset({"current"}))
        self.assertEqual(result[0][2], 147)
        self.assertEqual(result[1][2], 180)
        self.assertEqual(sum(r[2] for r in result), sum(r[2] for r in with_donor))

    def test_fixed_current_excerpt_cannot_take_space_it_will_not_render(self):
        # The caller renders a fixed authenticated turn from this short page,
        # irrespective of a larger allowance. Increasing it would waste the
        # donor's original source text without adding any current evidence.
        records = [allocation(181, 153, "current"), allocation(793, 154, "long")]
        self.assertEqual(complete_short_pages(records, protected_ids=frozenset({"current"})), records)

    def test_budget_source_order_and_complete_record_invariants(self):
        rng = random.Random(42018)
        for _ in range(600):
            records = []
            for index in range(rng.randrange(1, 21)):
                length = rng.randrange(1, 2001)
                allowance = rng.randrange(min(length, 120), length + 1)
                records.append(allocation(length, allowance, str(index)))
            before = copy.deepcopy(records)
            result = complete_short_pages(records)
            self.assertEqual(records, before)
            self.assertEqual(len(result), len(records))
            self.assertEqual(sum(r[2] for r in result), sum(r[2] for r in records))
            for old, new in zip(records, result):
                self.assertIs(old[0], new[0])
                self.assertEqual(old[1], new[1])
                length = len(old[0]["content"])
                self.assertLessEqual(new[2], length)
                if old[2] == length:
                    self.assertEqual(old[2], new[2])
                elif length <= 240:
                    self.assertGreaterEqual(new[2], old[2])
                else:
                    self.assertGreaterEqual(new[2], min(old[2], 120))


if __name__ == "__main__":
    unittest.main()
