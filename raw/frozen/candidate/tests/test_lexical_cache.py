"""Check that bounded directory-token reuse does not change recall or retain text globally."""

from __future__ import annotations

import unittest

from memory_book import MemoryBook
from memory_book.text import query_terms, terms


class LexicalCacheTests(unittest.TestCase):
    def test_tokenization_preserves_identifier_unicode_and_question_rules(self):
        self.assertEqual(
            terms("parseHTTP_response/v2.0:url-ID café Straße", query=True),
            ["parse", "http", "response", "v2", "0", "url", "id", "cafe", "strasse"],
        )
        self.assertEqual(query_terms("请告诉我缓存如何失效"), ["缓存", "失效"])
        self.assertEqual(terms("ＡPI/cacheKey"), ["api", "cache", "key"])

    def test_directory_cache_is_bounded_immutable_and_connection_local(self):
        first = MemoryBook(":memory:")
        second = MemoryBook(":memory:")
        try:
            initial = first._directory_tokens("Private calibration archive")
            self.assertIsInstance(initial, frozenset)
            self.assertIs(first._directory_tokens("Private calibration archive"), initial)
            self.assertEqual(second._directory_tokens.cache_info().currsize, 0)
            for number in range(520):
                self.assertIn(str(number), first._directory_tokens(f"Directory {number}"))
            self.assertEqual(first._directory_tokens.cache_info().currsize, 512)
            self.assertEqual(first._directory_tokens("Private calibration archive"), initial)
        finally:
            first.close()
            second.close()
        self.assertEqual(first._directory_tokens.cache_info().currsize, 0)
        self.assertEqual(second._directory_tokens.cache_info().currsize, 0)

    def test_warm_and_cold_directory_tokens_return_identical_evidence_after_rename(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            source = {
                "project": "lab", "session_id": "visit", "title": "Archive",
                "task_id": "instruments", "task_title": "Records",
                "created_at": "2025-07-03T12:00:00Z",
                "messages": [{"role": "user", "content": "Calibration threshold is 13."}],
            }
            book.ingest(source)

            def recall():
                result = book.recall("calibration", project="lab", use_cache=False)
                result.pop("latency_ms")
                return result

            original = recall()
            self.assertEqual(recall(), original)
            self.assertGreater(book._directory_tokens.cache_info().hits, 0)
            book.ingest({**source, "title": "Calibration", "task_title": "Calibration records"})
            renamed = recall()
            self.assertEqual(renamed["results"][0]["breadcrumb"][1]["title"], "Calibration records")
            self.assertNotEqual(renamed["revision"], original["revision"])
            book._directory_tokens.cache_clear()
            self.assertEqual(recall(), renamed)


if __name__ == "__main__":
    unittest.main()
