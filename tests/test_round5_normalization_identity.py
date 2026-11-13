"""Candidate K proof fixtures use only invented Unicode and SQLite inputs."""
from __future__ import annotations

import importlib.util
import random
import sys
import unicodedata
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import text as lexical


RANGES = ((0x00, 0x7F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
          (0x3001, 0x3003), (0x3008, 0x3011), (0x3014, 0x301F),
          (0x2010, 0x2010), (0x2012, 0x2015), (0x2018, 0x201F),
          (0x2022, 0x2022), (0x30FB, 0x30FB))
ADMITTED = {chr(code) for start, end in RANGES for code in range(start, end + 1)}
HAS_TIKTOKEN = importlib.util.find_spec("tiktoken") is not None


def legacy(text, query=False):
    """Literal pre-K terms structure, including historical truth evaluation."""
    if not text.isascii():
        text = unicodedata.normalize("NFKC", text)
    text = lexical.CAMEL_BOUNDARY.sub(r"\1 \2", text).casefold()
    if not text.isascii():
        # Normalize the whole string first: canonical ordering can cross
        # character boundaries. Only the category lookup/deletion is reused.
        text = lexical._strip_nonspacing_marks(unicodedata.normalize("NFKD", text))
    if text.isascii():
        # After case folding, the Unicode/identifier rule reduces exactly to
        # lowercase ASCII alphanumeric runs; its separators never add tokens.
        parts = lexical.ASCII_RUNS.findall(text)
        return [part for part in parts if part not in lexical.STOP] if query else parts
    if query:
        # Remove complete Chinese question phrases before bigramming; otherwise
        # 为什么 leaves the meaningless fragment 为什 as a retrieval feature.
        text = lexical.ZH_QUESTION.sub(" ", text)
    result: list[str] = []
    for match in lexical.RUNS.finditer(text):
        value = match.group()
        if lexical.CJK_RUN.fullmatch(value):
            parts = [value] if len(value) == 1 else [value[i:i + 2] for i in range(len(value) - 1)]
            result.extend(p for p in parts if not query or p not in lexical.ZH_STOP)
        else:
            parts = lexical.IDENTIFIER_SEPARATOR.split(value)
            # Indexed identifiers share the same split with queries; FTS syntax is
            # never passed through, even for user input containing quotes or OR.
            result.extend(p for p in parts if p and (not query or p not in lexical.STOP))
    return result


def c_calls(value):
    counts = {"normalize": 0, "category": 0}
    normalize, category = unicodedata.normalize, unicodedata.category
    previous = sys.getprofile()

    def profile(frame, event, arg):
        if event == "c_call":
            if arg is normalize:
                counts["normalize"] += 1
            elif arg is category:
                counts["category"] += 1

    try:
        sys.setprofile(profile)
        result = lexical.terms(value, query=True)
    finally:
        sys.setprofile(previous)
    return result, counts


class NormalizationIdentityTests(unittest.TestCase):
    def test_regex_admits_exactly_registered_scalars(self):
        actual = {chr(code) for code in range(0x110000)
                  if lexical._NORMALIZATION_IDENTITY.fullmatch(chr(code))}
        self.assertEqual(actual, ADMITTED)
        self.assertNotIn("\u1100", actual)  # Hangul L Jamo
        self.assertNotIn("\u1161", actual)  # Hangul V Jamo
        self.assertNotIn("\u0301", actual)  # Combining acute
        self.assertNotIn("\u2011", actual)  # Nonbreaking hyphen has compatibility decomposition
        self.assertNotIn("\u2026", actual)  # Ellipsis has compatibility decomposition

    def test_every_admitted_scalar_and_complete_alphabet_are_identity_stable(self):
        alphabet = "".join(sorted(ADMITTED))
        for char in alphabet:
            with self.subTest(code=hex(ord(char))):
                self.assertEqual(unicodedata.normalize("NFKC", char), char)
                self.assertEqual(unicodedata.normalize("NFKD", char), char)
                self.assertEqual(unicodedata.combining(char), 0)
                self.assertNotEqual(unicodedata.category(char), "Mn")
                self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(char.casefold()))
        self.assertEqual(unicodedata.normalize("NFKC", alphabet), alphabet)
        self.assertEqual(unicodedata.normalize("NFKD", alphabet), alphabet)
        print("K exhaustive invented Unicode certificate:",
              {"ucd": unicodedata.unidata_version, "admitted_scalars": len(ADMITTED),
               "whole_alphabet_NFKC_NFKD_identity": True,
               "fresh_rows_decoded": 0, "retrieval_calls": 0})

    def test_representative_cross_boundaries_keep_whole_string_identity(self):
        representatives = "aZ9 \n中一㐀鿿。、〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟‐‒–—―‘’‚‛“”„‟•・"
        for first in representatives:
            for second in representatives:
                value = first + second
                with self.subTest(value=value):
                    self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(value))
                    self.assertEqual(unicodedata.normalize("NFKC", value), value)
                    self.assertEqual(unicodedata.normalize("NFKD", value), value)

    def test_mixed_strings_match_preserved_whole_string_fallback_exactly(self):
        cases = ["", "ASCII CamelCase path/foo.py API_v2:403",
                 "为什么请告诉我《中英文AlphaBeta标识符》现在如何查找。",
                 "原文日期2001-02-03T04:05:06Z，正文是Cedar Observatory。",
                 "中文“quoted”与‘词语’•目录・资料—记录",
                 "\x00\t\n中\r\x7f",
                 "é e\u0301 a\u0315\u0300 Straße İ Σ K ① ㍿ ＡＢＣ",
                 "\u1100\u1161\u11a8 가각", "\u0cc6\u0cc2 \u09c7\u09be",
                 "<|endoftext|> 保留原文 \ud800 lone \udfff",
                 "汉字\ufe0f 标记\u034f \u302a \uff9e \u2026 \u2011",
                 "\uf900\ufa0e \U00020000 emoji👩\u200d💻"]
        for value in cases:
            for query in (False, True):
                with self.subTest(value=value, query=query):
                    self.assertEqual(lexical.terms(value, query=query), legacy(value, query))
            with patch.object(lexical, "_NORMALIZATION_UCD_VERSIONS", frozenset()):
                expected_index = lexical.index_text(value)
                expected_query = lexical.query_terms(value)
            self.assertEqual(lexical.index_text(value), expected_index)
            self.assertEqual(lexical.query_terms(value), expected_query)

    def test_deterministic_invented_unicode_mixes_match_legacy(self):
        rng = random.Random(516033)
        admitted = sorted(ADMITTED)
        extra = list("éßİ㍿①ＡΩｶﾞ…‐‑\u0301\u0315\u034f\u302a")
        extra += ["\u1100", "\u1161", "\ud800", "\udfff", "\U00020000", "😀"]
        mixed = admitted + extra
        for number in range(320):
            alphabet = admitted if number % 2 else mixed
            pieces = [rng.choice(alphabet)
                      for _ in range(rng.randrange(0, 160))]
            if number % 3 == 0:
                pieces.insert(0, "为什么AlphaBeta")
            value = "".join(pieces)
            for query in (False, True):
                with self.subTest(number=number, query=query):
                    self.assertEqual(lexical.terms(value, query=query), legacy(value, query))

    def test_real_c_call_profile_skips_only_certified_normalization(self):
        value = "中文资料《AlphaBeta》引用。"
        result, fast = c_calls(value)
        self.assertEqual(result, legacy(value, True))
        if unicodedata.unidata_version in lexical._NORMALIZATION_UCD_VERSIONS:
            self.assertEqual(fast, {"normalize": 0, "category": 0})
        with patch.object(lexical, "_NORMALIZATION_UCD_VERSIONS", frozenset()):
            old, slow = c_calls(value)
        self.assertEqual(result, old)
        self.assertEqual(slow["normalize"], 2)
        self.assertGreater(slow["category"], 0)
        fallback, accented = c_calls("中文é資料")
        self.assertEqual(fallback, legacy("中文é資料", True))
        self.assertEqual(accented["normalize"], 2)
        self.assertGreater(accented["category"], 0)
        print("K invented C-call mechanism:", {"ordinary": fast, "legacy": slow, "accented": accented})

    def test_changed_native_hooks_and_ucd_version_keep_legacy_work(self):
        value = "中文资料《AlphaBeta》引用。"
        expected = legacy(value, True)
        ordinary = unicodedata.normalize
        with patch.object(unicodedata, "normalize", wraps=ordinary) as wrapped:
            self.assertEqual(lexical.terms(value, query=True), expected)
            self.assertEqual(wrapped.call_count, 2)
        with patch.object(unicodedata, "category", wraps=unicodedata.category) as wrapped:
            self.assertEqual(lexical.terms(value, query=True), expected)
            self.assertGreater(wrapped.call_count, 0)
        with patch.object(lexical, "_strip_nonspacing_marks", wraps=lexical._strip_nonspacing_marks) as wrapped:
            self.assertEqual(lexical.terms(value, query=True), expected)
            self.assertEqual(wrapped.call_count, 1)
        with patch.object(lexical, "CAMEL_BOUNDARY", wraps=lexical.CAMEL_BOUNDARY):
            _, counts = c_calls(value)
            self.assertEqual(counts["normalize"], 2)
        with patch.object(unicodedata, "unidata_version", "unrecognized-future-ucd"):
            result, counts = c_calls(value)
        self.assertEqual(result, expected)
        self.assertEqual(counts["normalize"], 2)
        self.assertGreater(counts["category"], 0)

    def test_string_subclass_keeps_its_historical_isascii_behavior(self):
        class ClaimedAscii(str):
            def isascii(self):
                return True

        class ClaimedUnicode(str):
            def isascii(self):
                return False

        for value in (ClaimedAscii("Ａ中文"), ClaimedUnicode("ASCIIWord"), ClaimedUnicode("中文资料")):
            for query in (False, True):
                with self.subTest(value=value, kind=type(value), query=query):
                    self.assertEqual(lexical.terms(value, query=query), legacy(value, query))


    def test_stateful_isascii_truth_matches_literal_pre_k_structure(self):
        class Truth:
            def __init__(self, first, events):
                self.first, self.events = first, events

            def __bool__(self):
                self.events.append("truth")
                if self.events.count("truth") != 1:
                    raise AssertionError("Historical isascii truth must be consumed only once")
                return self.first

        class UnusualString(str):
            def __new__(cls, value, first):
                result = super().__new__(cls, value)
                result.events = []
                result.truth = Truth(first, result.events)
                return result

            def isascii(self):
                self.events.append("isascii")
                return self.truth

        for first in (True, False):
            for query in (False, True):
                with self.subTest(first=first, query=query):
                    previous = UnusualString("alphaＢeta 中文", first)
                    current = UnusualString("alphaＢeta 中文", first)
                    expected = legacy(previous, query)
                    actual = lexical.terms(current, query=query)
                    self.assertEqual(actual, expected)
                    self.assertEqual(current.events, previous.events)
                    self.assertEqual(current.events, ["isascii", "truth"])
                    self.assertEqual(expected[:2], ["alphabeta", "中文"] if first else ["alpha", "beta"])


class NormalizationIdentityBookTests(unittest.TestCase):
    def make_book(self):
        book = MemoryBook(":memory:", segmentation="turn", min_page_chars=0, cache_size=0)
        self.addCleanup(book.close)
        for identity, title, body in (
            ("anchor", "实验记录", "石英仪器AlphaBeta 指向 Cedar Observatory。石英仪器安装于1997年。"),
            ("target", "Cedar Observatory", "北方海湾保存原始观察。规范资料列明负责人王先生。"),
            ("accent", "Résumé", "é e\u0301 ＡＢＣ 原文日期2002年。保留完整来源。"),
        ):
            book.ingest({"project": "invented-lab", "session_id": identity,
                "title": title, "task_id": "archive", "created_at": "2001-02-03T04:05:06Z",
                "messages": [{"role": "user", "content": body}]})
        return book

    def test_actual_index_and_character_payload_equal_legacy(self):
        with patch.object(lexical, "_NORMALIZATION_UCD_VERSIONS", frozenset()):
            before = self.make_book()
        after = self.make_book()
        for table in ("pages_fts", "pages_stem_fts"):
            sql = f"SELECT rowid,title,question,body,directory FROM {table} ORDER BY rowid"
            self.assertEqual([tuple(row) for row in before.db.execute(sql)],
                             [tuple(row) for row in after.db.execute(sql)])
        for query in ("石英仪器AlphaBeta", "为什么原文日期是什么", "é ABC", "未匹配的词语"):
            for options in ({}, {"follow_titles": True}, {"coverage": True}, {"strategy": "flat"}):
                with self.subTest(query=query, options=options):
                    arguments = {"project": "invented-lab", "budget_chars": 1000, "use_cache": False, **options}
                    with patch.object(lexical, "_NORMALIZATION_UCD_VERSIONS", frozenset()):
                        old = before.recall(query, **arguments)
                    new = after.recall(query, **arguments)
                    self.assertEqual({key: value for key, value in old.items() if key != "latency_ms"},
                                     {key: value for key, value in new.items() if key != "latency_ms"})

    @unittest.skipUnless(HAS_TIKTOKEN, "optional exact tokenizer is not installed")
    def test_actual_token_payload_and_source_spans_equal_legacy(self):
        book = self.make_book()
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (0, 32, 128, 512):
                with self.subTest(tokenizer=tokenizer, budget=budget):
                    arguments = {"project": "invented-lab", "budget_chars": 1000, "use_cache": False,
                                 "tokenizer": tokenizer, "budget_tokens": budget}
                    with patch.object(lexical, "_NORMALIZATION_UCD_VERSIONS", frozenset()):
                        old = book.recall("石英仪器AlphaBeta 原文资料", **arguments)
                    new = book.recall("石英仪器AlphaBeta 原文资料", **arguments)
                    self.assertEqual({key: value for key, value in old.items() if key != "latency_ms"},
                                     {key: value for key, value in new.items() if key != "latency_ms"})


if __name__ == "__main__":
    unittest.main()
