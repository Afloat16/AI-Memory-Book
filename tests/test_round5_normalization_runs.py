"""Candidate N uses invented Unicode, actual C-call receivers and SQLite only."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import random
import sys
import unicodedata
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import text as lexical
from tests.test_round5_normalization_translation import (
    legacy as literal_terms,
    literal_terms_everywhere,
)


# Independent scalar/range data, never obtained from the candidate regex/table.
RANGES = ((0x00, 0x7F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
          (0x3001, 0x3003), (0x3008, 0x3011), (0x3014, 0x301F),
          (0x2010, 0x2010), (0x2012, 0x2015), (0x2018, 0x201F),
          (0x2022, 0x2022), (0x30FB, 0x30FB))
IDENTITY = frozenset(chr(code) for lo, hi in RANGES for code in range(lo, hi + 1))
MAPPED = {chr(code): chr(code - 0xFEE0) for code in range(0xFF01, 0xFF5F)}
MAPPED.update({"\u3000": " ", "\u2011": "\u2010", "\u2026": "..."})
COMPATIBILITY = frozenset(MAPPED)
COMPLETE_ALPHABET = IDENTITY | COMPATIBILITY
FIXED_TABLE = {ord(char): (ord(target) if len(target) == 1 else target)
               for char, target in MAPPED.items()}
NORMALIZE, CATEGORY = unicodedata.normalize, unicodedata.category
HAS_TIKTOKEN = importlib.util.find_spec("tiktoken") is not None
BASE_TEXT_SHA256 = "7c085f278252ff91cde97ba16a63c2a35365ddddb64fe12200c92c3e8e1d5ff7"
FROZEN_MODULES = {
    "tests/test_lexical_cache.py": "501f2464b6c67643ea4659df9af5a75bc73176e7",
    "tests/test_project_rowid_bounds.py": "2803337d063b5fff8726b2aecd4e5f2b387db466",
    "tests/test_round4_highlight.py": "c54b5eff4705edc03edf84e522d09f27eec2efa9",
    "tests/test_round4_sealed_counts.py": "3a39ea7ec191dd61771bbcd3731d7ba76d67b2e2",
    "tests/test_round4_token_work.py": "d717fe702714ad76dc05e43a659ef1c265d70dad",
    "tests/test_round5_materialization.py": "cc422d255db945c54ee333af0665e23b481d9ead",
    "tests/test_round5_native_rows.py": "facc9e054fca9c3a1cf5cf92b947226af402700d",
    "tests/test_round5_normalization_identity.py": "3d2786d7db7f4a5920a664b6c861251bc83625ab",
    "tests/test_round5_normalization_translation.py": "a7b90d5108e199d307944cf2687ee9320e2dbb2c",
    "tests/test_round5_ranked_entries.py": "43ee1dde53f2e003d28b01fd62c0490d5d3dd472",
    "tests/test_round5_statement_cache.py": "63def6e359cdc524339321ff48f5539cf351b0d1",
    "tests/test_title_reference.py": "9771f4cdc591b73ffdc3bad697437f0d3a279fa0",
    "tests/test_title_reference_interfaces.py": "3b03ac4b37c969b8f9283e466323fe561b3cbdb3",
    "tests/test_title_reference_native_integration.py": "fc0111d48f1ad0b2214e99582c6a13268102a0b3",
    "tests/test_token_budget.py": "9b1abe5830108a786124347ec350e5830969d149"
}

PATTERN_BLOCK = r'''# Only mapped runs enter translate; certified identity spans stay untouched.
_NORMALIZATION_TRANSLATION_RUN = re.compile(r"[\uff01-\uff5e\u3000\u2011\u2026]+")
'''
HELPER_BLOCK = '''def _translate_normalization_run(match: re.Match[str]) -> str:
    """Apply the existing fixed mapping to one adjacent compatibility run."""
    return match.group().translate(_NORMALIZATION_TRANSLATION)


'''
OLD_LINE = "                text = text.translate(_NORMALIZATION_TRANSLATION)\n"
NEW_LINE = "                text = _NORMALIZATION_TRANSLATION_RUN.sub(_translate_normalization_run, text)\n"


def independent_runs(value):
    """Find maximal compatible intervals by scalar membership, without regex."""
    result = []
    start = None
    for index, character in enumerate(value):
        if character in COMPATIBILITY:
            if start is None:
                start = index
        elif start is not None:
            result.append((start, index, value[start:index]))
            start = None
    if start is not None:
        result.append((start, len(value), value[start:]))
    return result


def direct_substitution(value):
    return lexical._NORMALIZATION_TRANSLATION_RUN.sub(
        lexical._translate_normalization_run, value)


def actual_work(function, value, query=True):
    """Observe real C-call receivers; never replace translate or the runtime."""
    work = {"normalize": 0, "category": 0, "translate_receivers": [],
            "run_sub": 0, "run_callbacks": []}
    previous = sys.getprofile()
    run_code = lexical._translate_normalization_run.__code__
    run_pattern = lexical._NORMALIZATION_TRANSLATION_RUN

    def profile(frame, event, arg):
        if event == "c_call":
            if arg is NORMALIZE:
                work["normalize"] += 1
            elif arg is CATEGORY:
                work["category"] += 1
            elif getattr(arg, "__name__", None) == "translate":
                receiver = getattr(arg, "__self__", None)
                if type(receiver) is str:
                    work["translate_receivers"].append(receiver)
            elif (getattr(arg, "__name__", None) == "sub" and
                  getattr(arg, "__self__", None) is run_pattern):
                work["run_sub"] += 1
        elif event == "call" and frame.f_code is run_code:
            match = frame.f_locals["match"]
            work["run_callbacks"].append((*match.span(), match.group()))

    try:
        sys.setprofile(profile)
        result = function(value, query=query)
    finally:
        sys.setprofile(previous)
    return result, work


class NormalizationRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(lexical.__file__).read_text(encoding="utf-8")
        for block in (PATTERN_BLOCK, HELPER_BLOCK, NEW_LINE):
            if source.count(block) != 1:
                raise AssertionError("N source inverse requires one exact registered block")
        restored = source.replace(PATTERN_BLOCK, "", 1).replace(HELPER_BLOCK, "", 1)
        restored = restored.replace(NEW_LINE, OLD_LINE, 1)
        if hashlib.sha256(restored.encode("utf-8")).hexdigest() != BASE_TEXT_SHA256:
            raise AssertionError("N inverse does not reproduce complete frozen LM text.py")
        namespace = {"__name__": "frozen_lm_text_reference",
                     "__file__": str(Path(lexical.__file__))}
        exec(compile(restored, "<frozen-lm-text-reference>", "exec"), namespace)
        cls.base_terms = staticmethod(namespace["terms"])
        cls.restored_text = restored

    def test_inverse_source_and_all_fifteen_original_modules_remain_exact(self):
        self.assertEqual(hashlib.sha256(self.restored_text.encode("utf-8")).hexdigest(),
                         BASE_TEXT_SHA256)
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(len(FROZEN_MODULES), 15)
        for relative, expected in FROZEN_MODULES.items():
            with self.subTest(path=relative):
                payload = (root / relative).read_bytes()
                header = b"blob " + str(len(payload)).encode("ascii") + b"\0"
                self.assertEqual(hashlib.sha1(header + payload).hexdigest(), expected)
        self.assertEqual(lexical._NORMALIZATION_TRANSLATION, FIXED_TABLE)

    def test_regex_has_exact_97_scalar_members_and_no_empty_match(self):
        pattern = lexical._NORMALIZATION_TRANSLATION_RUN
        self.assertEqual(pattern.pattern, r"[\uff01-\uff5e\u3000\u2011\u2026]+")
        actual = {chr(code) for code in range(0x110000)
                  if pattern.fullmatch(chr(code)) is not None}
        self.assertEqual(actual, COMPATIBILITY)
        self.assertEqual(len(actual), 97)
        self.assertFalse(actual & IDENTITY)
        self.assertIsNone(pattern.fullmatch(""))
        self.assertIsNone(pattern.search(""))
        self.assertEqual(list(pattern.finditer("")), [])

    def test_every_identity_scalar_separates_maximal_runs(self):
        pattern = lexical._NORMALIZATION_TRANSLATION_RUN
        for separator in sorted(IDENTITY):
            value = "ＡＢ" + separator + "…‑"
            with self.subTest(separator=hex(ord(separator))):
                expected = [(0, 2, "ＡＢ"), (3, 5, "…‑")]
                self.assertEqual(independent_runs(value), expected)
                self.assertEqual([(*m.span(), m.group()) for m in pattern.finditer(value)],
                                 expected)
                self.assertEqual(direct_substitution(value), value.translate(FIXED_TABLE))

    def test_all_97_mappings_and_ordered_pairs_match_whole_string_normalization(self):
        for first in MAPPED:
            for second in MAPPED:
                value = "中alpha" + first + second + "Beta資料"
                translated = direct_substitution(value)
                with self.subTest(first=hex(ord(first)), second=hex(ord(second))):
                    self.assertEqual(translated, value.translate(FIXED_TABLE))
                    self.assertEqual(translated, NORMALIZE("NFKC", value))
                    self.assertEqual(translated, NORMALIZE("NFKD", value))
        for character, target in MAPPED.items():
            with self.subTest(character=hex(ord(character))):
                self.assertEqual(direct_substitution(character), target)
                value = "中alpha" + character + "Beta資料"
                for query in (False, True):
                    self.assertEqual(lexical.terms(value, query=query), literal_terms(value, query))
                self.assertEqual(lexical.index_text(value), " ".join(literal_terms(value)))
                self.assertEqual(lexical.query_terms(value),
                                 list(dict.fromkeys(literal_terms(value, True)))[:64])

    def test_sparse_dense_and_whole_alphabet_substitution_is_pointwise(self):
        cases = [
            "", "plain ASCII\nAlphaBeta", "中文资料《AlphaBeta》",
            "中文" * 300 + "…" + "AlphaBeta " * 200,
            "ＡＢＣ１２３" * 128, "…" * 257,
            "Ａ中Ｂ甲Ｃ", "before…middle…after", "…‑　Ｂ…‑　",
            "".join(MAPPED), "".join(sorted(COMPLETE_ALPHABET)),
            "".join(reversed(sorted(COMPLETE_ALPHABET))),
        ]
        for value in cases:
            expected = "".join(MAPPED.get(character, character) for character in value)
            with self.subTest(length=len(value), runs=len(independent_runs(value))):
                self.assertEqual(direct_substitution(value), expected)
                self.assertEqual(expected, value.translate(FIXED_TABLE))
                self.assertEqual(expected, NORMALIZE("NFKC", value))
                self.assertEqual(expected, NORMALIZE("NFKD", value))

    def test_substitution_finishes_before_whole_string_camel_and_casefold(self):
        cases = [
            "alphaＢeta", "ＡbetaＣase", "aＢＣdＥf", "ＡlphaBeta",
            "alpha…Ｂeta", "甲ＡlphaBeta乙", "ＡＢ中cＤe",
            "为什么请告诉我alphaＢeta　指南…现在如何查找。",
            "ＡＰＩ＿Ｖ２ path／foo．py key：value version－２ alpha‑Beta",
            "the　and　AlphaBeta", "…AlphaＢeta…ＧammaDelta…",
        ]
        self.assertEqual(lexical.terms("alphaＢeta"), ["alpha", "beta"])
        self.assertEqual(lexical.terms("ＡbetaＣase"), ["abeta", "case"])
        for value in cases:
            for query in (False, True):
                with self.subTest(value=value, query=query):
                    self.assertEqual(lexical.terms(value, query=query), literal_terms(value, query))
                    self.assertEqual(lexical.terms(value, query=query),
                                     self.base_terms(value, query=query))

    def test_actual_translate_receivers_are_only_independently_found_runs(self):
        cases = [
            "中文" * 300 + "…" + "AlphaBeta " * 200,
            "ＡＢＣ１２３" * 128, "…" * 257,
            "Ａ中Ｂ甲Ｃ", "before…middle…after", "…‑　Ｂ…‑　",
            "alphaＢeta", "ＡbetaＣase", "".join(MAPPED),
        ]
        old_characters = new_characters = callbacks = 0
        supported = unicodedata.unidata_version in lexical._NORMALIZATION_UCD_VERSIONS
        for value in cases:
            expected_runs = independent_runs(value)
            expected_receivers = [run for _, _, run in expected_runs]
            expected_count = sum(character in COMPATIBILITY for character in value)
            actual, work = actual_work(lexical.terms, value)
            expected, old_work = actual_work(self.base_terms, value)
            with self.subTest(length=len(value), runs=len(expected_runs)):
                self.assertEqual(actual, expected)
                self.assertEqual(actual, literal_terms(value, True))
                if supported:
                    self.assertEqual((work["normalize"], work["category"]), (0, 0))
                    self.assertEqual(work["run_sub"], 1)
                    self.assertEqual(work["run_callbacks"], expected_runs)
                    self.assertEqual(work["translate_receivers"], expected_receivers)
                    self.assertEqual(sum(map(len, work["translate_receivers"])), expected_count)
                    self.assertEqual("".join(work["translate_receivers"]),
                                     "".join(c for c in value if c in COMPATIBILITY))
                    self.assertTrue(all(set(receiver) <= COMPATIBILITY
                                        for receiver in work["translate_receivers"]))
                    self.assertEqual(old_work["translate_receivers"], [value])
                    self.assertEqual((old_work["normalize"], old_work["category"]), (0, 0))
                    self.assertEqual(old_work["run_sub"], 0)
                    self.assertEqual(old_work["run_callbacks"], [])
                else:
                    self.assertEqual(work, old_work)
                old_characters += sum(map(len, old_work["translate_receivers"]))
                new_characters += sum(map(len, work["translate_receivers"]))
                callbacks += len(work["run_callbacks"])
        if supported:
            self.assertLess(new_characters, old_characters)
            self.assertGreater(callbacks, len(cases))
        print("N actual invented translate receivers; no timing claim:", {
            "ucd": unicodedata.unidata_version, "cases": len(cases),
            "old_receiver_characters": old_characters,
            "new_receiver_characters": new_characters, "run_callbacks": callbacks,
            "corpus_retrieval_calls": 0, "fresh_rows_decoded": 0})

    def test_all_single_new_scalars_keep_the_original_m_exact_call_assertion(self):
        supported = unicodedata.unidata_version in lexical._NORMALIZATION_UCD_VERSIONS
        for character in MAPPED:
            value = "中文alpha" + character + "Beta資料"
            actual, work = actual_work(lexical.terms, value)
            expected, old_work = actual_work(self.base_terms, value)
            with self.subTest(character=hex(ord(character))):
                self.assertEqual(actual, expected)
                if supported:
                    self.assertEqual((work["normalize"], work["category"]), (0, 0))
                    self.assertEqual(work["translate_receivers"], [character])
                    self.assertEqual(len(old_work["translate_receivers"]), 1)
                    self.assertEqual(work["run_callbacks"], independent_runs(value))
                else:
                    self.assertEqual(work, old_work)

    def test_original_k_ascii_and_empty_paths_never_enter_run_substitution(self):
        for value in ("", "ASCII AlphaBeta", "中文资料《AlphaBeta》—引用。", "\x00\t\n"):
            for query in (False, True):
                actual, work = actual_work(lexical.terms, value, query=query)
                expected, previous = actual_work(self.base_terms, value, query=query)
                with self.subTest(value=value, query=query):
                    self.assertEqual((actual, work), (expected, previous))
                    self.assertEqual(work["run_sub"], 0)
                    self.assertEqual(work["run_callbacks"], [])
                    self.assertEqual(work["translate_receivers"], [])

    def test_deterministic_invented_mixtures_equal_frozen_m_and_literal_legacy(self):
        rng = random.Random(51603314)
        identity = sorted(IDENTITY)
        mapped = sorted(COMPATIBILITY)
        excluded = list("éßİ㍿①Ωｶﾞ\u0301\u0315\u034f\u302a\u1100\u1161\ud800\udfff😀")
        for index in range(360):
            pieces = []
            for _ in range(rng.randrange(0, 200)):
                choose = rng.randrange(10)
                alphabet = mapped if choose < 4 else identity
                if index % 2 and choose == 9:
                    alphabet = excluded
                pieces.append(rng.choice(alphabet))
            if index % 3 == 0:
                pieces.insert(0, "为什么alphaＢeta　ＡＰＩ＿Ｖ２…")
            value = "".join(pieces)
            with self.subTest(index=index):
                self.assertEqual(direct_substitution(value), value.translate(FIXED_TABLE))
                for query in (False, True):
                    actual = lexical.terms(value, query=query)
                    self.assertEqual(actual, literal_terms(value, query))
                    self.assertEqual(actual, self.base_terms(value, query=query))

    def test_excluded_unicode_keeps_literal_work_and_never_enters_new_callback(self):
        exclusions = [
            "e\u0301", "Ａ\u0301", "a\u0315\u0300", "\u1100\u1161\u11a8",
            "\u0cc6\u0cc2", "\u09c7\u09be", "\u302a", "\u20dd", "\ufe0f", "\u034f",
            "\uff00", "\uff5f", "\uff61", "\uff76\uff9e", "\uf900", "\u212a", "\u2024",
            "é", "ß", "İ", "Σ", "①", "㍿", "\U00020000", "👩\u200d💻", "\ud800", "\udfff",
        ]
        for excluded in exclusions:
            value = "中文alphaＢeta…Ａ中Ｂ" + excluded
            self.assertIsNone(lexical._NORMALIZATION_COMPATIBILITY.fullmatch(value))
            for query in (False, True):
                actual, work = actual_work(lexical.terms, value, query=query)
                expected, previous = actual_work(literal_terms, value, query=query)
                with self.subTest(excluded=excluded, query=query):
                    self.assertEqual((actual, work), (expected, previous))
                    self.assertEqual(work["run_sub"], 0)
                    self.assertEqual(work["run_callbacks"], [])

    def test_unknown_ucd_and_all_nonordinary_hooks_retain_literal_calls(self):
        value = "中文alphaＢeta…Ａ中Ｂ　資料"
        with patch.object(unicodedata, "unidata_version", "unrecognized-future-ucd"):
            actual, work = actual_work(lexical.terms, value)
            expected, previous = actual_work(literal_terms, value)
            self.assertEqual((actual, work), (expected, previous))
            self.assertEqual(work["normalize"], 2)
            self.assertEqual(work["run_callbacks"], [])
            self.assertEqual(work["run_sub"], 0)
        hooks = ((unicodedata, "normalize"), (unicodedata, "category"),
                 (lexical, "CAMEL_BOUNDARY"), (lexical, "_strip_nonspacing_marks"))
        for module, name in hooks:
            original = getattr(module, name)
            with self.subTest(hook=name), patch.object(module, name, wraps=original) as hook:
                expected, previous = actual_work(literal_terms, value)
                old_calls = list(hook.mock_calls)
                hook.reset_mock()
                actual, work = actual_work(lexical.terms, value)
                self.assertEqual((actual, work), (expected, previous))
                self.assertEqual(hook.mock_calls, old_calls)
                self.assertEqual(work["run_callbacks"], [])
                self.assertEqual(work["run_sub"], 0)

    def test_nonordinary_hook_errors_keep_literal_exception_and_event_order(self):
        value = "中文alphaＢeta…Ａ中Ｂ　資料"
        events = []

        class DeliberateFailure(RuntimeError):
            pass

        def fail(*arguments, **keywords):
            events.append((arguments, keywords))
            raise DeliberateFailure("invented normalization hook failure")

        class BrokenCamel:
            def sub(self, *arguments, **keywords):
                return fail(*arguments, **keywords)

        for module, name, replacement in (
                (unicodedata, "normalize", fail),
                (unicodedata, "category", fail),
                (lexical, "CAMEL_BOUNDARY", BrokenCamel()),
                (lexical, "_strip_nonspacing_marks", fail)):
            with self.subTest(hook=name), patch.object(module, name, replacement):
                observed = []
                for function in (literal_terms, lexical.terms):
                    events.clear()
                    with self.assertRaisesRegex(DeliberateFailure, "invented normalization hook failure"):
                        function(value, query=True)
                    observed.append(list(events))
                self.assertEqual(observed[0], observed[1])
                self.assertEqual(len(observed[0]), 1)

    def test_stateful_subclass_truth_and_errors_keep_literal_initial_order(self):
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
                raise AssertionError("Subclass must not enter normalization runs")

        for first in (False, True):
            for query in (False, True):
                previous = UnusualString("alphaＢeta 中文…Ａ中Ｂ", first)
                current = UnusualString("alphaＢeta 中文…Ａ中Ｂ", first)
                expected, old_work = actual_work(literal_terms, previous, query=query)
                actual, work = actual_work(lexical.terms, current, query=query)
                with self.subTest(first=first, query=query):
                    self.assertEqual((actual, work), (expected, old_work))
                    self.assertEqual(current.events, previous.events)
                    self.assertEqual(current.events, ["isascii", "truth"])
                    self.assertEqual(work["run_sub"], 0)
                    self.assertEqual(work["run_callbacks"], [])

        class AsciiFailure(RuntimeError):
            pass

        class RaisingString(str):
            def isascii(self):
                raise AsciiFailure("invented initial isascii failure")

        for function in (literal_terms, lexical.terms):
            with self.subTest(function=function.__name__):
                with self.assertRaisesRegex(AsciiFailure, "invented initial isascii failure"):
                    function(RaisingString("alphaＢeta 中文"), query=True)


class NormalizationRunBookTests(unittest.TestCase):
    def make_book(self):
        book = MemoryBook(":memory:", segmentation="turn", max_page_chars=400,
                          min_page_chars=0, cache_size=0)
        self.addCleanup(book.close)
        samples = (
            ("anchor", "铜镜记录",
             "石英仪器 alphaＢeta 指向 Cedar Observatory。ＡＰＩ＿Ｖ２　版本…负责人王先生。"
             "参照 non‑breaking 条目保留原始名称。"),
            ("target", "Cedar Observatory",
             "北方海湾保存原始观察。规范资料列明负责人王先生。alphaＢeta 是原始仪器名，保留精确来源。"),
            ("dense", "Ｒｏｃｋｅｔ＿Ｌａｂ",
             "连续兼容字符：" + "ＡｌｐｈａＢｅｔａ１２３" * 28 + "。原始日期１９９７年…"),
            ("alternating", "交替字符资料",
             "Ａ中Ｂ文Ｃ档Ｄ" * 32 + "。alphaＢeta 石英仪器仍在 Cedar Observatory。"),
            ("alphabet", "完整兼容字符原文",
             "固定集合：" + "".join(MAPPED) + "。标点保留…Ａ中Ｂ。"),
            ("excluded", "Résumé Ａ",
             "Ａ\u0301 e\u0301 é ① ㍿ ｶﾞ 原始日期2002年。unsupported composition必须保留字面旧路径。"),
            ("ascii", "Ordinary archive",
             "AlphaBeta instrument notes keep exact source references and unchanged ordinary ASCII terms."),
        )
        for identity, title, body in samples:
            book.ingest({"project": "invented-n-lab", "session_id": identity,
                         "title": title, "task_id": "archive",
                         "created_at": "2001-02-03T04:05:06Z",
                         "messages": [{"role": "user", "content": body}]})
        return book

    def test_real_fts_and_full_native_scoped_payloads_equal_literal_reference(self):
        with literal_terms_everywhere():
            before = self.make_book()
        after = self.make_book()
        for table in ("pages_fts", "pages_stem_fts"):
            sql = f"SELECT rowid,title,question,body,directory FROM {table} ORDER BY rowid"
            self.assertEqual([tuple(row) for row in before.db.execute(sql)],
                             [tuple(row) for row in after.db.execute(sql)])
        sql = "SELECT id,content,source_refs FROM pages ORDER BY id"
        self.assertEqual([tuple(row) for row in before.db.execute(sql)],
                         [tuple(row) for row in after.db.execute(sql)])
        chapter_id = before.db.execute("SELECT id FROM chapters ORDER BY id LIMIT 1").fetchone()[0]
        queries = ("石英仪器alphaＢeta", "为什么１９９７年记录是什么", "ＡＰＩ＿Ｖ２",
                   "non‑breaking条目", "Ａ中Ｂ文Ｃ", "完整兼容字符…",
                   "é ABC", "现在 alphaＢeta", "未匹配的词语")
        options = ({}, {"follow_titles": True}, {"coverage": True}, {"strategy": "flat"},
                   {"chapter": chapter_id}, {"session": "anchor"})
        for query in queries:
            for choice in options:
                for budget in (0, 120, 1000):
                    with self.subTest(query=query, options=choice, budget=budget):
                        arguments = {"project": "invented-n-lab", "budget_chars": budget,
                                     "use_cache": False, **choice}
                        with literal_terms_everywhere():
                            old = before.recall(query, **arguments)
                        new = after.recall(query, **arguments)
                        self.assertEqual({key: value for key, value in old.items() if key != "latency_ms"},
                                         {key: value for key, value in new.items() if key != "latency_ms"})

    @unittest.skipUnless(HAS_TIKTOKEN, "optional exact tokenizer is not installed")
    def test_both_exact_tokenizers_and_source_spans_equal_literal_reference(self):
        with literal_terms_everywhere():
            before = self.make_book()
        after = self.make_book()
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (0, 32, 128, 512):
                for follow in (False, True):
                    for query in ("石英仪器alphaＢeta ＡＰＩ＿Ｖ２ 原文資料…", "Ａ中Ｂ文Ｃ 连续兼容字符"):
                        with self.subTest(tokenizer=tokenizer, budget=budget,
                                          follow_titles=follow, query=query):
                            arguments = {"project": "invented-n-lab", "budget_chars": 1000,
                                         "use_cache": False, "tokenizer": tokenizer,
                                         "budget_tokens": budget, "follow_titles": follow}
                            with literal_terms_everywhere():
                                old = before.recall(query, **arguments)
                            new = after.recall(query, **arguments)
                            self.assertEqual({key: value for key, value in old.items() if key != "latency_ms"},
                                             {key: value for key, value in new.items() if key != "latency_ms"})


if __name__ == "__main__":
    unittest.main()
