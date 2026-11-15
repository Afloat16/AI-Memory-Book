"""Code naming variants must retrieve original evidence within the same scope."""

from __future__ import annotations

import unittest

from memory_book import MemoryBook
from memory_book.text import identifier_terms, index_text, query_terms, similarity, terms


class IdentifierLexicalTests(unittest.TestCase):
    def test_segmentation_tokens_keep_their_existing_meaning(self):
        self.assertEqual(terms("HTTPParser HTTP2Parser parseHTTPResponse"),
                         ["httpparser", "http2parser", "parse", "httpresponse"])
        self.assertEqual(similarity("HTTPParser", "http_parser"), 0.0)
        for spelling in ("HTTPParser", "HttpParser", "httpParser", "http_parser", "HTTP_PARSER"):
            with self.subTest(spelling=spelling):
                self.assertEqual(set(identifier_terms(spelling)), {"httpparser", "http", "parser"})

    def test_acronyms_numbers_and_qualified_names_have_bounded_lexical_aliases(self):
        for spelling in ("HTTP2Parser", "Http2Parser", "http2Parser", "http2_parser"):
            with self.subTest(spelling=spelling):
                self.assertEqual(set(identifier_terms(spelling)), {"http2parser", "http2", "parser"})
        self.assertEqual(set(identifier_terms("network.HTTPParser::parseResponse")),
                         {"network", "httpparser", "http", "parser", "parse", "response", "parseresponse"})
        self.assertNotIn("networkhttpparser", index_text("network.HTTPParser"))
        self.assertEqual(identifier_terms("HTTP parser"), terms("HTTP parser"))
        self.assertEqual(identifier_terms("ordinary words 缓存有效期"), terms("ordinary words 缓存有效期"))
        self.assertEqual(set(query_terms("当前 ＨＴＴＰＰａｒｓｅｒ 是什么")),
                         {"httpparser", "http", "parser"})
        self.assertLessEqual(len(query_terms(" ".join(f"HTTPParser{i}_timeout" for i in range(100)))), 64)
        self.assertEqual(query_terms("XMLHttpRequest"), query_terms("xml_http_request"))
        self.assertEqual(query_terms("parseHTTPResponse"), query_terms("parse_http_response"))


class IdentifierRecallTests(unittest.TestCase):
    @staticmethod
    def add(book, spelling, *, project="code", sid="target", note="uses a 317ms deadline"):
        return book.ingest({
            "project": project, "session_id": sid,
            "created_at": "2026-01-02T00:00:00Z",
            "messages": [{"role": "user", "content": "Implementation note"},
                         {"role": "assistant", "content": f"{spelling} {note}."}],
        })

    def assert_original_evidence(self, book, response, spelling):
        self.assertLessEqual(response["context_chars"], 2400)
        self.assertIn(spelling, response["context"])
        self.assertEqual(response["results"][0]["source_refs"][0]["session_id"], "target")
        for item in response["results"]:
            page = book.read(item["id"])["content"]
            for lo, hi in item["excerpt_spans"]:
                self.assertIn(page[lo:hi], item["text"])
            for ref in item["source_refs"]:
                source = book.get_session(ref["project"], ref["session_id"])
                turn = "\n\n".join(f'{m["role"].upper()}: {m["content"]}' for m in source["messages"])
                self.assertEqual(page[ref["start"]:ref["end"]], turn[ref["turn_start"]:ref["turn_end"]])

    def test_naming_variants_retrieve_each_other_in_both_directions(self):
        families = (
            ("HTTPParser", "HttpParser", "httpParser", "http_parser", "HTTP_PARSER"),
            ("XMLHttpRequest", "XmlHttpRequest", "xmlHttpRequest", "xml_http_request"),
            ("parseHTTPResponse", "ParseHttpResponse", "parse_http_response"),
            ("HTTP2Parser", "Http2Parser", "http2Parser", "http2_parser"),
            ("network.HTTPParser.parseResponse", "network::http_parser::parse_response"),
        )
        for family in families:
            for spelling in family:
                with MemoryBook(":memory:", segmentation="turn") as book:
                    self.add(book, spelling)
                    self.add(book, "JSON parser", sid="unrelated", note="accepts trailing commas")
                    for query in family:
                        with self.subTest(source=spelling, query=query):
                            result = book.recall(query, project="code", limit=1, use_cache=False)
                            self.assert_original_evidence(book, result, spelling)

    def test_bilingual_and_quoted_queries_preserve_scope_and_source_spelling(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            self.add(book, "HTTPParser", note="超时阈值为 317ms")
            for number in range(100):
                self.add(book, "http_parser", project="foreign", sid=f"foreign-{number}",
                         note="超时阈值为 999ms")
            for query in ("当前 http_parser 超时阈值", '"HttpParser" OR *', "请问 HTTP_PARSER 的超时阈值是什么"):
                with self.subTest(query=query):
                    result = book.recall(query, project="code", limit=1, use_cache=False)
                    self.assert_original_evidence(book, result, "HTTPParser")
                    self.assertNotIn("999ms", result["context"])
                    self.assertNotIn("http_parser", result["context"])
                    self.assertTrue(all(ref["project"] == "code"
                                        for item in result["results"] for ref in item["source_refs"]))

    def test_excerpts_keep_original_offsets_and_aliases_do_not_replace_source(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            self.add(book, "Background detail. " * 80 + "\nHTTPParser", note="uses a 317ms deadline")
            result = book.recall("http_parser deadline", project="code", budget_chars=350,
                                 limit=1, use_cache=False)
            self.assert_original_evidence(book, result, "HTTPParser")
            self.assertIn("317ms", result["context"])
            self.assertLessEqual(result["context_chars"], 350)
            self.assertNotIn("http_parser", result["context"])

    def test_identifier_indexes_follow_replacement_and_deletion(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            self.add(book, "HTTPParser")
            self.assertIn("HTTPParser", book.recall("http_parser", project="code")["context"])
            self.add(book, "SocketBuilder")
            self.assertEqual(book.recall("http_parser", project="code")["results"], [])
            self.assertIn("SocketBuilder", book.recall("socket_builder", project="code")["context"])
            book.delete_session("code", "target")
            self.assertEqual(book.recall("socket_builder", project="code")["results"], [])

    def test_multiple_identifier_facets_keep_both_constraints(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            self.add(book, "HTTPParser", note="uses a 317ms deadline")
            self.add(book, "XMLSerializer", sid="serializer", note="preserves UTF-8 encoding")
            for number in range(8):
                self.add(book, "HTTP parser", sid=f"noise-{number}", note="has ordinary HTTP parser logs")
            for query in ("HTTPParser and XMLSerializer", "http_parser 以及 xml_serializer"):
                with self.subTest(query=query):
                    result = book.recall(query, project="code", limit=2, coverage=True, use_cache=False)
                    self.assertIn("317ms", result["context"])
                    self.assertIn("UTF-8", result["context"])
                    self.assertEqual({ref["session_id"] for item in result["results"]
                                      for ref in item["source_refs"]}, {"target", "serializer"})
                    self.assertLessEqual(result["context_chars"], 2400)

    def test_current_correction_remains_comparable_after_a_naming_style_change(self):
        for original, corrected in (("XMLHttpRequest", "xml_http_request"),
                                    ("parseHTTPResponse", "parse_http_response"),
                                    ("HTTP2Parser", "http2_parser")):
            with MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest({
                    "project": "code", "session_id": "target", "task_id": "timeout",
                    "created_at": "2026-01-02T00:00:00Z", "messages": [
                        {"role": "user", "content": f"Current {original} timeout"},
                        {"role": "assistant", "content": f"{original} timeout is 17ms."},
                        {"role": "user", "content": f"Current {corrected} timeout"},
                        {"role": "assistant", "content": f"{corrected} timeout is 29ms."},
                    ],
                })
                for spelling in (original, corrected):
                    with self.subTest(original=original, query=spelling):
                        result = book.recall(f"current {spelling} timeout", project="code",
                                             limit=1, use_cache=False)
                        self.assertIn(f"{corrected} timeout is 29ms", result["context"])
                        self.assertNotIn("17ms", result["context"])
                        self.assertEqual({ref["turn_index"] for ref in result["results"][0]["source_refs"]}, {1})


if __name__ == "__main__":
    unittest.main()
