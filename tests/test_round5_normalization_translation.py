"""Candidate M proof fixtures use invented Unicode, SQLite and token inputs only."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import random
import sys
import unicodedata
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store as storage
from memory_book import text as lexical
from memory_book import token_budget


RANGES = ((0x00, 0x7F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
          (0x3001, 0x3003), (0x3008, 0x3011), (0x3014, 0x301F),
          (0x2010, 0x2010), (0x2012, 0x2015), (0x2018, 0x201F),
          (0x2022, 0x2022), (0x30FB, 0x30FB))
IDENTITY = {chr(code) for lo, hi in RANGES for code in range(lo, hi + 1)}
MAPPED = {chr(code): chr(code - 0xFEE0) for code in range(0xFF01, 0xFF5F)}
MAPPED.update({"\u3000": " ", "\u2011": "\u2010", "\u2026": "..."})
COMPATIBLE = IDENTITY | set(MAPPED)
HAS_TIKTOKEN = importlib.util.find_spec("tiktoken") is not None
NORMALIZE, CATEGORY = unicodedata.normalize, unicodedata.category


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


def c_calls(function, value, query=True):
    counts = {"normalize": 0, "category": 0, "translate": 0}
    previous = sys.getprofile()

    def profile(_frame, event, arg):
        if event == "c_call":
            if arg is NORMALIZE:
                counts["normalize"] += 1
            elif arg is CATEGORY:
                counts["category"] += 1
            elif getattr(arg, "__name__", None) == "translate" and type(getattr(arg, "__self__", None)) is str:
                counts["translate"] += 1
    try:
        sys.setprofile(profile)
        result = function(value, query=query)
    finally:
        sys.setprofile(previous)
    return result, counts


@contextmanager
def literal_terms_everywhere():
    """Replace all three shipping terms bindings with the literal historical body."""
    with patch.object(lexical, "terms", legacy), patch.object(storage, "terms", legacy), \
         patch.object(token_budget, "terms", legacy):
        yield


class NormalizationTranslationTests(unittest.TestCase):
    def test_mapping_and_extended_scalar_set_are_exactly_prospective(self):
        table = {ord(char): (ord(target) if len(target) == 1 else target) for char, target in MAPPED.items()}
        self.assertEqual(len(table), 97)
        self.assertEqual(lexical._NORMALIZATION_TRANSLATION, table)
        actual = {chr(code) for code in range(0x110000)
                  if lexical._NORMALIZATION_COMPATIBILITY.fullmatch(chr(code)) is not None}
        self.assertEqual(actual, COMPATIBLE)
        self.assertEqual(actual - IDENTITY, set(MAPPED))
        self.assertIsNotNone(lexical._NORMALIZATION_COMPATIBILITY.fullmatch(""))
        self.assertEqual(set(lexical._NORMALIZATION_UCD_VERSIONS),
                         {"13.0.0", "14.0.0", "15.0.0", "15.1.0", "16.0.0"})

    def test_every_mapping_has_exact_nfkc_nfkd_targets_and_target_closure(self):
        for source, target in MAPPED.items():
            with self.subTest(codepoint=hex(ord(source))):
                self.assertEqual(unicodedata.normalize("NFKC", source), target)
                self.assertEqual(unicodedata.normalize("NFKD", source), target)
                self.assertEqual(source.translate(lexical._NORMALIZATION_TRANSLATION), target)
                self.assertEqual(unicodedata.combining(source), 0)
                self.assertFalse(unicodedata.category(source).startswith("M"))
                self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(target))
                for char in target:
                    self.assertEqual(unicodedata.normalize("NFKC", char), char)
                    self.assertEqual(unicodedata.normalize("NFKD", char), char)
                    self.assertEqual(unicodedata.combining(char), 0)
                    self.assertFalse(unicodedata.category(char).startswith("M"))
                    self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(char.casefold()))
        print("M exact scalar translation certificate:", {
            "ucd": unicodedata.unidata_version, "mapped_scalars": len(MAPPED),
            "fullwidth_ascii": 94, "special_mappings": {"3000": "0020", "2011": "2010", "2026": "002e 002e 002e"},
            "fresh_rows_decoded": 0, "corpus_retrieval_calls": 0})

    def test_whole_alphabet_and_casefold_cannot_reorder_compose_or_leave_identity(self):
        value = "".join(sorted(COMPATIBLE))
        translated = value.translate(lexical._NORMALIZATION_TRANSLATION)
        self.assertEqual(unicodedata.normalize("NFKC", value), translated)
        self.assertEqual(unicodedata.normalize("NFKD", value), translated)
        self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(translated))
        folded = lexical.CAMEL_BOUNDARY.sub(r"\1 \2", translated).casefold()
        self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(folded))
        self.assertEqual(unicodedata.normalize("NFKD", folded), folded)
        for char in value:
            with self.subTest(codepoint=hex(ord(char))):
                self.assertEqual(unicodedata.combining(char), 0)
                self.assertFalse(unicodedata.category(char).startswith("M"))
                self.assertFalse(0x1100 <= ord(char) <= 0x11FF)

    def test_every_new_scalar_across_ordered_representative_boundaries(self):
        representatives = "".join(MAPPED) + "aZ9 _./:-\x00\t\n中一㐀鿿。、〈〉《》「」【】〜‐—‘’“”•・"
        for first in representatives:
            for second in representatives:
                value = first + second
                target = value.translate(lexical._NORMALIZATION_TRANSLATION)
                with self.subTest(first=hex(ord(first)), second=hex(ord(second))):
                    self.assertEqual(unicodedata.normalize("NFKC", value), target)
                    self.assertEqual(unicodedata.normalize("NFKD", value), target)
                    self.assertIsNotNone(lexical._NORMALIZATION_IDENTITY.fullmatch(target))

    def test_every_new_scalar_terms_query_and_index_match_literal_legacy(self):
        for char in MAPPED:
            for value in (char, "中pre" + char + "Post文", "why" + char + "AlphaBeta"):
                with self.subTest(codepoint=hex(ord(char)), value=value):
                    for query in (False, True):
                        self.assertEqual(lexical.terms(value, query=query), legacy(value, query))
                    self.assertEqual(lexical.index_text(value), " ".join(legacy(value)))
                    self.assertEqual(lexical.query_terms(value), list(dict.fromkeys(legacy(value, True)))[:64])

    def test_translation_precedes_case_boundaries_and_preserves_query_rules(self):
        cases = ["alphaＢeta", "ａｌｐｈａＢｅｔａ", "ＡlphaBeta", "aＢＣdＥf",
                 "为什么请告诉我alphaＢeta　指南…现在如何查找。",
                 "ＡＰＩ＿Ｖ２ path／foo．py key：value version－２ alpha‑Beta",
                 "pre…Post，原文１９９７年", "the　and　AlphaBeta", "［Ｑｕｏｔｅ］＂value＂"]
        self.assertEqual(lexical.terms("alphaＢeta"), ["alpha", "beta"])
        self.assertEqual(lexical.terms("alphaＢeta", query=True), ["alpha", "beta"])
        for value in cases:
            for query in (False, True):
                with self.subTest(value=value, query=query):
                    self.assertEqual(lexical.terms(value, query=query), legacy(value, query))

    def test_marks_composition_and_other_compatibility_scalars_keep_literal_fallback(self):
        exclusions = ["e\u0301", "Ａ\u0301", "a\u0315\u0300", "\u1100\u1161\u11a8",
                      "\u0cc6\u0cc2", "\u09c7\u09be", "\u302a", "\u20dd", "\ufe0f", "\u034f",
                      "\uff00", "\uff5f", "\uff61", "\uff76\uff9e", "\uf900", "\u212a", "\u2024",
                      "é", "ß", "İ", "Σ", "①", "㍿", "\U00020000", "👩\u200d💻", "\ud800", "\udfff"]
        for excluded in exclusions:
            value = "中文alphaＢeta" + excluded
            with self.subTest(excluded=excluded):
                self.assertIsNone(lexical._NORMALIZATION_COMPATIBILITY.fullmatch(value))
                for query in (False, True):
                    self.assertEqual(lexical.terms(value, query=query), legacy(value, query))
                actual, actual_calls = c_calls(lexical.terms, value)
                expected, expected_calls = c_calls(legacy, value)
                self.assertEqual(actual, expected)
                self.assertEqual(actual_calls, expected_calls)

    def test_deterministic_invented_mixtures_match_literal_legacy(self):
        rng = random.Random(51603313)
        admitted = sorted(COMPATIBLE)
        unsafe = list("éßİ㍿①Ωｶﾞ\u0301\u0315\u034f\u302a\u1100\u1161\ud800\udfff😀")
        for index in range(360):
            alphabet = admitted if index % 2 else admitted + unsafe
            pieces = [rng.choice(alphabet) for _ in range(rng.randrange(0, 200))]
            if index % 3 == 0:
                pieces.insert(0, "为什么alphaＢeta　ＡＰＩ＿Ｖ２…")
            value = "".join(pieces)
            for query in (False, True):
                with self.subTest(index=index, query=query):
                    self.assertEqual(lexical.terms(value, query=query), legacy(value, query))

    def test_real_c_call_work_is_eliminated_for_every_new_eligible_scalar(self):
        examples = []
        supported = unicodedata.unidata_version in lexical._NORMALIZATION_UCD_VERSIONS
        for char in MAPPED:
            value = "中文alpha" + char + "Beta資料"
            actual, fast = c_calls(lexical.terms, value)
            expected, slow = c_calls(legacy, value)
            with self.subTest(codepoint=hex(ord(char))):
                self.assertEqual(actual, expected)
                self.assertEqual(slow["normalize"], 2)
                self.assertGreater(slow["category"], 0)
                self.assertEqual(slow["translate"], 0)
                if supported:
                    self.assertEqual(fast, {"normalize": 0, "category": 0, "translate": 1})
                else:
                    self.assertEqual(fast, slow)
            if char in {"Ｂ", "\u3000", "\u2011", "\u2026"}:
                examples.append({"source": hex(ord(char)), "candidate": fast, "literal_legacy": slow})
        print("M invented C-call mechanism; no latency or corpus claim:", examples)

    def test_original_k_identity_and_ascii_paths_never_translate(self):
        for value in ("", "ASCII AlphaBeta", "中文资料《AlphaBeta》—引用。"):
            with self.subTest(value=value):
                actual, counts = c_calls(lexical.terms, value)
                self.assertEqual(actual, legacy(value, True))
                self.assertEqual(counts["translate"], 0)
                if value.isascii() or unicodedata.unidata_version in lexical._NORMALIZATION_UCD_VERSIONS:
                    self.assertEqual(counts, {"normalize": 0, "category": 0, "translate": 0})

    def test_unknown_versions_and_nonordinary_hooks_keep_literal_normalization_order(self):
        value = "中文alphaＢeta　資料…non‑breaking"
        with patch.object(unicodedata, "unidata_version", "unrecognized-future-ucd"):
            actual, calls = c_calls(lexical.terms, value)
            expected, old_calls = c_calls(legacy, value)
            self.assertEqual((actual, calls), (expected, old_calls))
            self.assertEqual(calls["normalize"], 2)
            self.assertEqual(calls["translate"], 0)
        hooks = [(unicodedata, "normalize"), (unicodedata, "category"),
                 (lexical, "CAMEL_BOUNDARY"), (lexical, "_strip_nonspacing_marks")]
        for module, name in hooks:
            original = getattr(module, name)
            with self.subTest(hook=name), patch.object(module, name, wraps=original) as hook:
                expected = legacy(value, True)
                expected_calls = list(hook.mock_calls)
                hook.reset_mock()
                actual = lexical.terms(value, query=True)
                self.assertEqual(actual, expected)
                self.assertEqual(hook.mock_calls, expected_calls)

    def test_subclass_stateful_isascii_truth_is_consumed_exactly_once(self):
        class Truth:
            def __init__(self, first, events):
                self.first, self.events = first, events
            def __bool__(self):
                self.events.append("truth")
                if self.events.count("truth") != 1:
                    raise AssertionError("isascii truth evaluated twice")
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
            def translate(self, _table):
                raise AssertionError("Subclass must retain literal old path")

        for first in (False, True):
            for query in (False, True):
                previous, current = UnusualString("alphaＢeta 中文", first), UnusualString("alphaＢeta 中文", first)
                with self.subTest(first=first, query=query):
                    expected = legacy(previous, query)
                    self.assertEqual(lexical.terms(current, query=query), expected)
                    self.assertEqual(current.events, previous.events)
                    self.assertEqual(current.events, ["isascii", "truth"])
                    self.assertEqual(expected[:2], ["alphabeta", "中文"] if first else ["alpha", "beta"])


class NormalizationTranslationBookTests(unittest.TestCase):
    def make_book(self):
        book = MemoryBook(":memory:", segmentation="turn", min_page_chars=0, cache_size=0)
        self.addCleanup(book.close)
        samples = (
            ("anchor", "实验记录", "石英仪器 alphaＢeta　指南指向 Cedar Observatory。版本ＡＰＩ＿Ｖ２记录于１９９７年…王先生使用non‑breaking标记。"),
            ("target", "Cedar Observatory", "北方海湾保存原始观察。规范资料列明负责人王先生。alphaＢeta 是原始仪器名，保留精确来源。"),
            ("alphabet", "Ｒｏｃｋｅｔ＿Ｌａｂ", "完整注册兼容字符原文：" + "".join(MAPPED) + "。所有标点和字符保持原始source spans，不改写记忆内容。"),
            ("excluded", "Résumé Ａ", "Ａ\u0301 e\u0301 é ① ㍿ ｶﾞ 原始日期2002年。unsupported composition必须保留字面旧路径。"),
        )
        for identity, title, body in samples:
            book.ingest({"project": "invented-m-lab", "session_id": identity, "title": title,
                "task_id": "archive", "created_at": "2001-02-03T04:05:06Z",
                "messages": [{"role": "user", "content": body}]})
        return book

    def test_real_fts_and_complete_native_payloads_match_literal_terms_reference(self):
        with literal_terms_everywhere():
            before = self.make_book()
        after = self.make_book()
        for table in ("pages_fts", "pages_stem_fts"):
            sql = f"SELECT rowid,title,question,body,directory FROM {table} ORDER BY rowid"
            self.assertEqual([tuple(row) for row in before.db.execute(sql)],
                             [tuple(row) for row in after.db.execute(sql)])
        self.assertEqual([tuple(row) for row in before.db.execute("SELECT id,content FROM pages ORDER BY id")],
                         [tuple(row) for row in after.db.execute("SELECT id,content FROM pages ORDER BY id")])
        queries = ("石英仪器alphaＢeta", "为什么１９９７年记录是什么", "ＡＰＩ＿Ｖ２", "non‑breaking标记",
                   "完整注册兼容字符…", "é ABC", "未匹配的词语")
        for query in queries:
            for options in ({}, {"follow_titles": True}, {"coverage": True}, {"strategy": "flat"}):
                with self.subTest(query=query, options=options):
                    arguments = {"project": "invented-m-lab", "budget_chars": 1000, "use_cache": False, **options}
                    with literal_terms_everywhere():
                        old = before.recall(query, **arguments)
                    new = after.recall(query, **arguments)
                    self.assertEqual({key: value for key, value in old.items() if key != "latency_ms"},
                                     {key: value for key, value in new.items() if key != "latency_ms"})

    @unittest.skipUnless(HAS_TIKTOKEN, "optional exact tokenizer is not installed")
    def test_exact_token_payload_and_source_spans_match_literal_terms_reference(self):
        with literal_terms_everywhere():
            before = self.make_book()
        after = self.make_book()
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (0, 32, 128, 512):
                for follow in (False, True):
                    with self.subTest(tokenizer=tokenizer, budget=budget, follow_titles=follow):
                        arguments = {"project": "invented-m-lab", "budget_chars": 1000, "use_cache": False,
                                     "tokenizer": tokenizer, "budget_tokens": budget, "follow_titles": follow}
                        query = "石英仪器alphaＢeta ＡＰＩ＿Ｖ２ 原文資料…"
                        with literal_terms_everywhere():
                            old = before.recall(query, **arguments)
                        new = after.recall(query, **arguments)
                        self.assertEqual({key: value for key, value in old.items() if key != "latency_ms"},
                                         {key: value for key, value in new.items() if key != "latency_ms"})


if __name__ == "__main__":
    unittest.main()
