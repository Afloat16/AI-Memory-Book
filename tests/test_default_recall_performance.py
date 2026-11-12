from __future__ import annotations

import random
import unicodedata
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import text as lexical


def legacy_terms(text, *, query=False):
    """Frozen cb7486b lexical algorithm, independent of the new fast paths."""
    if not text.isascii():
        text = unicodedata.normalize("NFKC", text)
    text = lexical.CAMEL_BOUNDARY.sub(r"\1 \2", text).casefold()
    if not text.isascii():
        text = "".join(c for c in unicodedata.normalize("NFKD", text)
                       if unicodedata.category(c) != "Mn")
    if query:
        text = lexical.ZH_QUESTION.sub(" ", text)
    result = []
    for match in lexical.RUNS.finditer(text):
        value = match.group()
        if lexical.CJK_RUN.fullmatch(value):
            parts = [value] if len(value) == 1 else [value[i:i + 2] for i in range(len(value) - 1)]
            result.extend(p for p in parts if not query or p not in lexical.ZH_STOP)
        else:
            parts = lexical.IDENTIFIER_SEPARATOR.split(value)
            result.extend(p for p in parts if p and (not query or p not in lexical.STOP))
    return result


def legacy_source_fold(text):
    folded, positions = [], []
    for index, character in enumerate(text):
        piece = "".join(c for c in unicodedata.normalize("NFKD", character).casefold()
                        if unicodedata.category(c) != "Mn")
        folded.append(piece)
        positions.extend([index] * len(piece))
    return "".join(folded), positions


class UnicodeLexicalEquivalenceTests(unittest.TestCase):
    def test_all_ascii_pairs_preserve_run_order_duplicates_and_stop_filtering(self):
        for left in range(128):
            for right in range(128):
                text = chr(left) + chr(right)
                for query in (False, True):
                    self.assertEqual(lexical.terms(text, query=query),
                                     legacy_terms(text, query=query), (repr(text), query))

    def test_long_ascii_identifiers_and_unicode_normalization_match_frozen_algorithm(self):
        rng = random.Random(88217)
        alphabet = "abcXYZ019_./:-!? \t\r\n'\"[]{}+="
        cases = ["".join(rng.choices(alphabet, k=128)) for _ in range(100)]
        cases += ["parseHTTP_response/v2.0:url-ID café Straße",
                  "ＡPI/cacheKey ① Ⅸ ﻻ", "a\u0315\u0300\u0327b",
                  "a\u0345b", "a\u302eb", "a\ufe0fb", "a\U0001d165b",
                  "请告诉我缓存如何失效", "👩🏽‍💻 café e\u0301",
                  "\ud800word\udfff", "a--b...c___d::e//f"]
        for text in cases:
            for query in (False, True):
                with self.subTest(text=repr(text), query=query):
                    self.assertEqual(lexical.terms(text, query=query),
                                     legacy_terms(text, query=query))

    def test_category_mn_is_distinct_from_combining_class(self):
        # Mn with combining class zero must disappear. Mc with nonzero class
        # must remain; removing it would incorrectly join the adjacent words.
        self.assertEqual(unicodedata.category("\ufe0f"), "Mn")
        self.assertEqual(unicodedata.combining("\ufe0f"), 0)
        self.assertNotEqual(unicodedata.category("\u302e"), "Mn")
        self.assertNotEqual(unicodedata.combining("\u302e"), 0)
        self.assertEqual(lexical._strip_nonspacing_marks("a\ufe0fb\u302ec"), "ab\u302ec")
        self.assertEqual(lexical.terms("a\ufe0fb"), ["ab"])
        self.assertEqual(lexical.terms("a\u302eb"), ["a", "b"])

    def test_mark_translation_matches_category_filter_for_deterministic_unicode_fuzz(self):
        rng = random.Random(3721)
        for _ in range(100):
            text = "".join(chr(rng.randrange(0x110000)) for _ in range(64))
            text += "a\u0301\u0315\u0300\ufe0f\u302e\U0001d165b"
            expected = "".join(c for c in text if unicodedata.category(c) != "Mn")
            self.assertEqual(lexical._strip_nonspacing_marks(text), expected)

    def test_cached_character_fold_preserves_every_original_offset(self):
        rng = random.Random(6429)
        pieces = ["a", "A", "é", "e\u0301", "Straße", "\u0315\u0300", "\u0345",
                  "缓存", "\u302e", "\ufe0f", "\U0001d165", "👩🏽‍💻", "\n", " "]
        cases = ["café Straße 缓存45秒。\n" * 100]
        cases += ["".join(rng.choices(pieces, k=60)) for _ in range(80)]
        for text in cases:
            self.assertEqual(lexical._fold_excerpt_source(text), legacy_source_fold(text))

    def test_excerpt_payload_and_coordinates_match_frozen_unicode_transform(self):
        texts = [
            "Unrelated notes. " * 20 + "\nASSISTANT: café Straße pressure is 82.\n" + "Later notes. " * 20,
            "a\u0315\u0300 repeated. " * 30 + "\n缓存现在保留23分钟。\n" + "a\u302eb background. " * 30,
            "ASCII parseHTTP_response/v2.0 examples. " * 40,
        ]
        for text in texts:
            for budget in (1, 7, 16, 64, 100, 400):
                for query in ("pressure cafe strasse", "缓存保留", "http response", "absent"):
                    actual = lexical.excerpt(text, query, budget)
                    with patch.object(lexical, "terms", legacy_terms), patch.object(
                            lexical, "_fold_excerpt_source", legacy_source_fold):
                        expected = lexical.excerpt(text, query, budget)
                    self.assertEqual(actual, expected, (budget, query))


class DirectoryIndexReuseTests(unittest.TestCase):
    @staticmethod
    def session(identity="one", title="Unique Session", task_title="Unique Directory"):
        return {"project": "lab", "session_id": identity, "title": title,
                "task_id": "shared", "task_title": task_title,
                "created_at": "2025-01-02T12:00:00Z",
                "messages": [{"role": "user", "content": "Review the calibration."},
                             {"role": "assistant", "content": "Pressure is 82 pascals. " * 100}]}

    def test_same_directory_is_normalized_once_per_changed_ingest(self):
        with MemoryBook(":memory:", segmentation="adaptive", max_page_chars=250, min_page_chars=0) as book:
            source = self.session()
            directory = source["task_title"] + " " + source["title"]
            with patch("memory_book.store.index_text", wraps=lexical.index_text) as normalize:
                result = book.ingest(source)
            self.assertGreater(result["pages"], 1)
            self.assertEqual(sum(call.args == (directory,) for call in normalize.call_args_list), 1)
            expected = lexical.index_text(directory)
            for table in ("pages_fts", "pages_stem_fts"):
                self.assertEqual({r[0] for r in book.db.execute(f"SELECT directory FROM {table}")}, {expected})

    def test_directory_reuse_preserves_inheritance_and_chapter_rename(self):
        with MemoryBook(":memory:", segmentation="adaptive", max_page_chars=250, min_page_chars=0) as book:
            book.ingest(self.session())
            second = self.session("two", "Second Session")
            second.pop("task_title")
            book.ingest(second)
            book.ingest(self.session(task_title="Renamed café Directory"))
            rows = book.db.execute("SELECT p.rid,c.title,s.title session_title FROM pages p JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk").fetchall()
            for row in rows:
                expected = lexical.index_text(row["title"] + " " + row["session_title"])
                for table in ("pages_fts", "pages_stem_fts"):
                    actual = book.db.execute(f"SELECT directory FROM {table} WHERE rowid=?", (row["rid"],)).fetchone()[0]
                    self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
