"""Exact bounded highlight reads retained after rejecting candidate B cache."""

import unittest

from memory_book import MemoryBook


class HighlightWhitelistTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:")

    def tearDown(self):
        self.book.close()

    def test_highlight_bytes_match_original_query_across_guard_boundaries(self):
        rows = [(1, "run", "walking only"), (2, "", "running swiftly"),
                (3, "", "running unselected"), (4, "", "run and running"),
                (256, "", "running boundary"), (257, "", "running wider"),
                (700, "", "running far away")]
        self.book.db.executemany(
            "INSERT INTO pages_stem_fts(rowid,title,question,body,directory) VALUES(?,?,'',?,'')", rows)
        expression = '("run") AND body : ("run")'
        for ids in ([2], [2, 4], [2, 256], [1, 256], [1, 257], [2, 700], [255, 256], [2, 2]):
            with self.subTest(ids=ids):
                original = self.book.db.execute(
                    "SELECT rowid,highlight(pages_stem_fts,2,?,?) body FROM pages_stem_fts "
                    "WHERE pages_stem_fts MATCH ? AND rowid IN (" + ",".join("?" for _ in ids) + ")",
                    ["\x01", "\x02", expression, *ids]).fetchall()
                trace = []
                self.book.db.set_trace_callback(trace.append)
                try:
                    actual = self.book._highlighted_bodies(expression, ids)
                finally:
                    self.book.db.set_trace_callback(None)
                self.assertEqual({row["rowid"]: row["body"] for row in actual},
                                 {row["rowid"]: row["body"] for row in original})
                self.assertTrue(all(row["rowid"] in ids for row in actual))
                query = next(sql for sql in trace if "highlight(pages_stem_fts" in sql)
                bounded = len(ids) > 1 and max(ids) - min(ids) + 1 <= 256
                self.assertEqual("BETWEEN" in query, bounded)
                self.assertEqual("+rowid" in query, bounded)
        stem_only = self.book._highlighted_bodies(expression, [2])
        self.assertEqual(stem_only[0]["body"], "\x01running\x02 swiftly")

    def test_empty_highlight_selection_does_not_read_source(self):
        trace = []
        self.book.db.set_trace_callback(trace.append)
        try:
            self.assertEqual(self.book._highlighted_bodies('"run"', []), [])
        finally:
            self.book.db.set_trace_callback(None)
        self.assertEqual(trace, [])


if __name__ == "__main__":
    unittest.main()
