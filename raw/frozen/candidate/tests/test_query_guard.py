from types import SimpleNamespace
import unittest

from benchmarks.query_guard import require_query_count


class QueryGuardTests(unittest.TestCase):
    def test_wrong_count_and_duplicate_ids_stop_before_scoring(self):
        data = SimpleNamespace(queries=[SimpleNamespace(id=str(n)) for n in range(264)])
        with self.assertRaisesRegex(ValueError, "Expected 128 queries, selected 264"):
            require_query_count(data, 128)
        require_query_count(data, 264)
        data.queries[-1].id = data.queries[0].id
        with self.assertRaisesRegex(ValueError, "unique"):
            require_query_count(data, 264)

    def test_guard_rejects_ambiguous_expected_counts(self):
        data = SimpleNamespace(queries=[SimpleNamespace(id="one")])
        for value in (True, False, "1", 1.0, 0, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_query_count(data, value)
        require_query_count(data, 1)
        require_query_count(data, None)
