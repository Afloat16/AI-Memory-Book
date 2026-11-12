import hashlib
import unittest

from benchmarks.round2_data import select_ids


class Round2SelectionTests(unittest.TestCase):
    def test_new_selection_excludes_every_old_id_and_ignores_input_order(self):
        ids = ["id-" + str(index) for index in range(400)]
        old = ids[:128]
        chosen = select_ids(ids, old, "fixed-prefix:", 256)
        self.assertEqual(len(chosen), 256)
        self.assertFalse(set(chosen) & set(old))
        self.assertEqual(chosen, select_ids(list(reversed(ids)), old, "fixed-prefix:", 256))
        expected = sorted(ids[128:], key=lambda value: hashlib.sha256(("fixed-prefix:" + value).encode()).hexdigest())[:256]
        self.assertEqual(chosen, expected)

    def test_invalid_or_undersized_input_is_rejected_without_replacement(self):
        for ids, excluded, count in ((["a", "a"], [], 1), (["a"], ["missing"], 1),
                                      (["a", "b"], ["a"], 2), (["a"], [], 0)):
            with self.assertRaises(ValueError):
                select_ids(ids, excluded, "prefix:", count)


if __name__ == "__main__":
    unittest.main()
