"""Artificial acronym regressions; no engineering evaluation corpus is used."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.text import identifier_families, identifier_phrase_matches, index_text


def stable(value):
    return {key: item for key, item in value.items() if key not in {"latency_ms", "cache_hit"}}


class IdentifierRecallTests(unittest.TestCase):
    def book(self, **options):
        book = MemoryBook(":memory:", segmentation="turn", max_page_chars=100000,
                          min_page_chars=0, cache_size=0, **options)
        self.addCleanup(book.close)
        return book

    def add(self, book, sid, content, project="engineering"):
        return book.ingest({"project": project, "session_id": sid,
                            "created_at": "2025-01-01T00:00:00Z",
                            "messages": [{"role": "assistant", "content": content}]})

    def recall(self, book, query, **options):
        return book.recall(query, project="engineering", use_cache=False, **options)

    def first(self, result):
        return result["results"][0]["source_refs"][0]["session_id"]

    def legacy(self, book, query, **options):
        with patch("memory_book.store.identifier_families", return_value=[]):
            return self.recall(book, query, **options)

    def test_aliases_leave_the_index_tokenizer_unchanged(self):
        cases = {
            "HTTPServer": (("httpserver",), ("http", "server")),
            "HTTP Server": (("http", "server"), ("httpserver",)),
            "parseHTTPRequest": (("parse", "httprequest"), ("parse", "http", "request")),
            "parse HTTP request": (("http", "request"), ("httprequest",)),
            "parse_HTTP2Request": (("parse", "http2request"), ("parse", "http2", "request")),
        }
        for query, family in cases.items():
            with self.subTest(query=query):
                self.assertIn(family, identifier_families(query))
        self.assertEqual(index_text("HTTPServer parseHTTPRequest"), "httpserver parse httprequest")
        self.assertEqual(identifier_families("http server parse http request"), [])
        self.assertEqual(identifier_families("normal natural language request"), [])

    def test_expansion_is_bounded_on_long_queries(self):
        query = ("HTTPServer JSONParser XMLDecoder RPCClient TCPListener UDPReader " * 160)[:8000]
        families = identifier_families(query)
        self.assertEqual(len(families), 4)
        self.assertTrue(all(0 < len(form) <= 8 for family in families for form in family))
        self.assertEqual(identifier_families("HTTP" + "s" * 7997), [])
        self.assertEqual(identifier_families(query + "x"), [])

    def test_source_matches_require_complete_identifier_boundaries(self):
        phrases = [("httpserver",), ("http", "server"), ("parse", "http", "request")]
        for text in ("MyHTTPServerCache", "my_HTTPServer_cache", "HTTP Serverless", "parseHTTPRequester"):
            with self.subTest(text=text):
                self.assertEqual(identifier_phrase_matches(text, phrases), set())
        self.assertEqual(identifier_phrase_matches("HTTPServer HTTP Server", phrases), set(phrases[:2]))
        self.assertEqual(identifier_phrase_matches("HTTP unrelated中文 Server", phrases), set())

    def test_both_acronym_directions_recover_original_source(self):
        for query, source in (("HTTP Server", "HTTPServer rejects duplicate headers."),
                              ("HTTPServer", "The HTTP Server rejects duplicate headers."),
                              ("parse HTTP request", "parseHTTPRequest rejects ambiguous encodings."),
                              ("parseHTTPRequest", "Use parse HTTP request for the encoded input.")):
            with self.subTest(query=query):
                book = self.book()
                self.add(book, "target", source)
                result = self.recall(book, query, limit=1)
                self.assertEqual(self.first(result), "target")
                self.assertIn(source, result["context"])

    def test_existing_candidate_gains_complete_alias_evidence(self):
        book = self.book()
        self.add(book, "target", "parseHTTPRequest rejects ambiguous encodings.")
        self.add(book, "generic", "parse parse parse parse parse unrelated input.")
        old = self.legacy(book, "parse HTTP request", limit=1)
        new = self.recall(book, "parse HTTP request", limit=1)
        self.assertEqual(self.first(old), "generic")
        self.assertEqual(self.first(new), "target")
        self.assertEqual(old["candidate_count"], new["candidate_count"])

    def test_original_form_preference_does_not_ignore_other_query_terms(self):
        book = self.book()
        self.add(book, "original", "HTTPServer handles ordinary scheduling.")
        self.add(book, "alias", "The HTTP Server has a documented deadlock workaround.")
        self.assertEqual(self.first(self.recall(book, "HTTPServer", limit=1)), "original")
        self.assertEqual(self.first(self.recall(book, "HTTPServer deadlock", limit=1)), "alias")

    def test_longer_source_identifier_is_not_promoted_as_original(self):
        book = self.book()
        self.add(book, "prefix", "MyHTTPServerCache handles scheduling.")
        self.add(book, "suffix", "HTTP Serverless handles scheduling.")
        self.add(book, "target", "The HTTP Server handles scheduling.")
        self.assertEqual(self.first(self.recall(book, "HTTPServer", limit=1)), "target")

    def test_every_scope_filters_before_the_supplementary_limit(self):
        book = self.book()
        for number in range(100):
            self.add(book, f"foreign-{number}", "HTTPServer HTTPServer HTTPServer.", project="other")
        target = self.add(book, "local", "HTTPServer rejects ambiguous headers.")
        for scope in ({"project": "engineering"}, {"chapter": target["chapter_id"]},
                      {"session": "local"}, {"project": "engineering", "chapter": target["chapter_id"], "session": "local"}):
            with self.subTest(scope=scope):
                result = book.recall("HTTP Server", limit=1, use_cache=False, **scope)
                self.assertEqual(self.first(result), "local")
                self.assertTrue(all(ref["project"] == "engineering"
                                    for hit in result["results"] for ref in hit["source_refs"]))
        self.assertEqual(book.recall("HTTP Server", project="other", session="local", use_cache=False)["results"], [])

    def test_original_form_only_preserves_full_legacy_payload(self):
        book = self.book()
        for number in range(25):
            self.add(book, f"exact-{number}", f"HTTPServer keeps engineering record {number}.")
        for options in ({"limit": 2}, {"limit": 5, "budget_chars": 300}):
            with self.subTest(options=options):
                self.assertEqual(stable(self.recall(book, "HTTPServer", **options)),
                                 stable(self.legacy(book, "HTTPServer", **options)))

    def test_unaffected_modes_and_queries_never_call_supplementary_route(self):
        book = self.book()
        self.add(book, "note", "HTTPServer and normal conference calibration notes.")
        cases = [("conference calibration", {}), ("http server", {}),
                 ("HTTPServer", {"strategy": "flat"}), ("HTTPServer", {"coverage": True}),
                 ("latest HTTPServer", {}), ("HTTPServer as of 2024", {}),
                 ("HTTPServer", {"semantic": True})]
        with patch.object(book, "_identifier_candidates", side_effect=AssertionError("unexpected expansion")), \
                patch.object(book, "_semantic_encoder", return_value=None):
            # The semantic stub checks only dispatch; existing semantic suites
            # separately exercise encoder/index/fusion behavior.
            for query, options in cases:
                with self.subTest(query=query, options=options):
                    self.assertEqual(stable(self.recall(book, query, **options)),
                                     stable(self.legacy(book, query, **options)))

    def test_chinese_multiple_families_and_small_budget_keep_exact_spans(self):
        book = self.book()
        fact = "HTTP Server uses the JSON Parser for the packet."
        self.add(book, "target", "Unrelated archived engineering note.\n" * 100 + fact +
                 "\nUnrelated archived engineering note." * 100)
        options = {"limit": 1, "budget_chars": 300}
        if importlib.util.find_spec("tiktoken"):
            options["budget_tokens"] = 128
        result = self.recall(book, "使用 HTTPServer 和 JSONParser", **options)
        self.assertIn(fact, result["context"])
        self.assertLessEqual(len(result["context"]), 300)
        if "context_tokens" in result:
            self.assertLessEqual(result["context_tokens"], 128)
        for hit in result["results"]:
            original = book.read(hit["id"])["content"]
            for lo, hi in hit["excerpt_spans"]:
                self.assertIn(original[lo:hi], hit["text"])
            self.assertTrue(hit["source_refs"])

    def test_oversized_single_or_total_bodies_fall_back_completely(self):
        for count, repeats in ((1, 12000), (3, 9000)):
            with self.subTest(count=count):
                book = self.book()
                self.add(book, "original", "HTTPServer keeps the original evidence.")
                for number in range(count):
                    self.add(book, f"large-{number}", "HTTP Server " + "padding " * repeats)
                self.assertEqual(stable(self.recall(book, "HTTPServer", limit=2)),
                                 stable(self.legacy(book, "HTTPServer", limit=2)))

    def test_existing_index_is_unchanged_and_v10_result_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "existing.db"
            with MemoryBook(path) as book:
                self.add(book, "target", "HTTPServer rejects ambiguous headers.")
                old_key = [3, 10, "HTTP Server", "engineering", None, None, 4000, 5, "book", False]
                digest = hashlib.sha256(json.dumps(old_key, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                book.db.execute("INSERT INTO recall_cache VALUES(?,?,?,?)",
                                (digest, book.revision, '{"context":"old cached miss"}', 0))
                before = {table: [tuple(row) for row in book.db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                          for table in ("pages_fts", "pages_stem_fts", "sessions", "pages")}
            with MemoryBook(path) as book:
                result = book.recall("HTTP Server", project="engineering")
                self.assertFalse(result["cache_hit"])
                self.assertEqual(self.first(result), "target")
                self.assertTrue(book.recall("HTTP Server", project="engineering")["cache_hit"])
                after = {table: [tuple(row) for row in book.db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                         for table in before}
                self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
