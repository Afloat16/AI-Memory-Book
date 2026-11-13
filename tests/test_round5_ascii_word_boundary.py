"""Candidate O proofs use invented text, native C events and exact frozen sources."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import itertools
from pathlib import Path
import random
import re
import sys
import types
import unicodedata
import unittest
from unittest.mock import Mock, patch

from memory_book import MemoryBook
from memory_book import text as lexical
from tests.test_round5_normalization_translation import (
    legacy as literal_terms,
    literal_terms_everywhere,
)


# The inverse counterpart may change only under a separately frozen combination.
COUNTERPART_TEXT_SHA256 = "7c085f278252ff91cde97ba16a63c2a35365ddddb64fe12200c92c3e8e1d5ff7"
FROZEN_LM_TEXT_SHA256 = "7c085f278252ff91cde97ba16a63c2a35365ddddb64fe12200c92c3e8e1d5ff7"
UNFIXED_TEXT_SHA256 = "31df3017243057309d08166d88fed62ca9f9c9592cc79176613359aafb4ec4e9"
FROZEN_MODULES = {
    "tests/test_round5_statement_cache.py": "55acd7d4fd4ab0dafbed6c825c33f80d712e12a1f76c49c1d0b30bc0ab5fba54",
    "tests/test_round5_native_rows.py": "f557eb50cecbeb4ffe216145aca461edd3a3371b84e3da603c92a31bf79e8f42",
    "tests/test_round5_materialization.py": "2a652356adff1de9344ed4fea904caee7e8b58b1ac4266d73553fc1520c74a9d",
    "tests/test_round4_sealed_counts.py": "a2e43be0bcd9978e392b60c8ef5b5e9de54277edf84fdf4ebe9ec2b8a30df2a9",
    "tests/test_round4_highlight.py": "59cab84b24ea873670b5b1689d18bbdd170bf1cbb635a85ecba2a30e4104390b",
    "tests/test_round4_token_work.py": "d05efe980d65f1d61017316f4410455646f4853efbe0f22194a0d9a0e9f02bdc",
    "tests/test_token_budget.py": "89fa3919c92f97e5b3f7ff44f92fa2ebcf0f6121ed941a21dd5b450bc300aa4c",
    "tests/test_project_rowid_bounds.py": "417a58396aa5d08d87a249e32fe41beb2e5176d82c4d6a47d0b4bd53075bb1aa",
    "tests/test_lexical_cache.py": "419170a018e2baf0c0bdb70fc5414ac79922da402aa27ed9151a16208cd3d354",
    "tests/test_title_reference.py": "d97603c308877748a36bf7e6450a97b656c701de5989e590c37900bf72591c80",
    "tests/test_title_reference_interfaces.py": "8ba7e5a2c72903b5aff36a06a31ae9ea642db254eed48b3a4dd5c9a4589da63f",
    "tests/test_title_reference_native_integration.py": "a249e57df8a477b649c8feb1b74265aa4a21158bb84905fd959dc30f026da6bc",
    "tests/test_round5_normalization_identity.py": "184195e982a74eb91f9be0ef854d9be53823c9eafe13574b80a69b97dc8ee7dc",
    "tests/test_round5_ranked_entries.py": "e4e4b1be159d9b45dc537e537c0040c10def2cf19683fd30dfdb038e05af548b",
    "tests/test_round5_normalization_translation.py": "25434916a32bd8015e453393d76b1e5336ab5f5e24655b899d4ae25f2aff3ba9"
}
UNCHANGED_SOURCE_FILES = {
    "src/memory_book/__init__.py": "3b91357e9271f1abbe7d2dd4c01f0067ca5b5a65d6065844c850328d49e6aad7",
    "src/memory_book/__main__.py": "935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d",
    "src/memory_book/cli.py": "f0e06d1d15e250aa4a6b1279a451f8d3d02acd1b8f7bd0a849b840397603e190",
    "src/memory_book/clients.py": "c87c2ebd4dbd6b193b186f493586f53183a38e8108fd7011df3aa474f9b2058f",
    "src/memory_book/importers.py": "f61aabfaa3e1fd2f46010e3c745e3275bb0d84c6d8e1b83317fda9e6b5cd7b76",
    "src/memory_book/integration.py": "88ed9bf5a0ee90b93516dc9ded0e0a8f1459354f25fbcc5afe70197b9444c6c5",
    "src/memory_book/mcp_server.py": "7f4e0cd884690bf585809c1d246228440a940e4752729928f2fc7b6698f0a1df",
    "src/memory_book/paths.py": "37fd4089455082aa680b1fb3dcef8645e558bb43b7d27285ef32997629622bf4",
    "src/memory_book/segmentation.py": "773cb62777bb11a66f1d2318bd75601f9ac38ea0fb6e7a534c1d8844a1a16e75",
    "src/memory_book/semantic.py": "41df86bced1b613deea2f1b1361eba9f32c3786f5185a06253fbfd32270ac91e",
    "src/memory_book/service.py": "55bd05f45cafc5dcd6c1fc5ceceade85f005a85a850b908c7bb155cff5a3584f",
    "src/memory_book/static/index.html": "52f6e2d22fd25f6d5f9bd4df345c5c5e1ecaa907c326e61abc33a9b29c70d2d7",
    "src/memory_book/store.py": "38c405b640216992b29b49c2f1937b8c5b644383f3cbfbcf764c5a7d502a9c58",
    "src/memory_book/sync.py": "89b2ac4b30b9b14ac564c3d328a51fbba97b2efc8a8dd1997892fc4142501291",
    "src/memory_book/title_reference.py": "7e2c17fe5af2882f6471fd5610e1eca65eeac7f02e73f9daf6b5f2970709423e",
    "src/memory_book/token_budget.py": "505ece57e7227ee1955d76883411362a1f462c28a2e8964984be818395266180",
    "src/memory_book/web.py": "4e2cbfa33434322c78f57624c8faa32f4be9fb7fc29c8ffc4ed916e244446dcc"
}
FIXED_MODULE_BLOCK = r'''# This certificate excludes every old CJK scalar, including unassigned points,
# and every other word character outside lowercase ASCII letters and digits.
# Remaining Unicode characters can only separate the original lexical pieces.
_ASCII_LEXICAL_EXCLUSIONS = re.compile(rf"[{CJK}]|[^\W0-9a-z_]")
_ORDINARY_ASCII_RUNS = ASCII_RUNS
_ORDINARY_RUNS = RUNS
_ORDINARY_CJK_RUN = CJK_RUN
_ORDINARY_IDENTIFIER_SEPARATOR = IDENTIFIER_SEPARATOR
_ORDINARY_ZH_QUESTION = ZH_QUESTION
_ORDINARY_STOP = STOP

'''
FIXED_BRANCH_BLOCK = r'''    if (type(text) is str and type(query) is bool
            and ASCII_RUNS is _ORDINARY_ASCII_RUNS
            and RUNS is _ORDINARY_RUNS
            and CJK_RUN is _ORDINARY_CJK_RUN
            and IDENTIFIER_SEPARATOR is _ORDINARY_IDENTIFIER_SEPARATOR
            and ZH_QUESTION is _ORDINARY_ZH_QUESTION
            and (query is False or STOP is _ORDINARY_STOP)
            and _ASCII_LEXICAL_EXCLUSIONS.search(text) is None):
        # Whole-string certification also covers punctuation-rich English.
        # Identifier splitting and ordered STOP membership remain identical.
        parts = ASCII_RUNS.findall(text)
        return [part for part in parts if part not in STOP] if query else parts
'''
UNFIXED_MODULE_BLOCK = FIXED_MODULE_BLOCK.replace("_ORDINARY_STOP = STOP\n", "")
UNFIXED_BRANCH_BLOCK = FIXED_BRANCH_BLOCK.replace(
    "            and (query is False or STOP is _ORDINARY_STOP)\n", "")
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))
ASCII_WORDS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
OLD_WORD = re.compile(r"\w", re.UNICODE)
HOOK_NAMES = ("ASCII_RUNS", "RUNS", "CJK_RUN", "IDENTIFIER_SEPARATOR", "ZH_QUESTION")
RESTORED_NAMES = HOOK_NAMES + ("STOP", "ZH_STOP", "CAMEL_BOUNDARY", "_strip_nonspacing_marks")
HAS_TIKTOKEN = importlib.util.find_spec("tiktoken") is not None


def in_old_cjk(code):
    return any(lo <= code <= hi for lo, hi in CJK_RANGES)


def independent_exclusion(character):
    return (in_old_cjk(ord(character)) or
            ((character.isalnum() or character == "_") and
             character not in ASCII_WORDS and character != "_"))


@contextmanager
def restored_namespace(namespace):
    """Every witness gets a fresh original hook state, including on exceptions."""
    previous = {name: namespace[name] for name in RESTORED_NAMES}
    try:
        yield namespace
    finally:
        namespace.update(previous)


def frozen_namespace(source, name):
    namespace = {"__name__": name, "__file__": "<hash-locked-reference>"}
    exec(compile(source, "<" + name + ">", "exec"), namespace)
    return namespace


def nested_code(code):
    result = {code}
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            result.update(nested_code(value))
    return result


def actual_pattern_work(function, namespace, value, query=False):
    """Observe real builtin receivers and generator resumptions without wrappers."""
    pattern_methods = {
        (id(namespace["ASCII_RUNS"]), "findall"): "ascii_findall",
        (id(namespace["RUNS"]), "finditer"): "runs_finditer",
        (id(namespace["CJK_RUN"]), "fullmatch"): "cjk_fullmatch",
        (id(namespace["IDENTIFIER_SEPARATOR"]), "split"): "identifier_split",
        (id(namespace["ZH_QUESTION"]), "sub"): "question_sub",
    }
    work = {key: 0 for key in pattern_methods.values()}
    work["lexical_generator_resumptions"] = 0
    generators = {code for code in nested_code(function.__code__) if code.co_name == "<genexpr>"}
    previous = sys.getprofile()

    def profile(frame, event, arg):
        if event == "c_call":
            key = pattern_methods.get((id(getattr(arg, "__self__", None)),
                                       getattr(arg, "__name__", None)))
            if key is not None:
                work[key] += 1
        elif event == "call" and frame.f_code in generators:
            work["lexical_generator_resumptions"] += 1

    try:
        sys.setprofile(profile)
        result = function(value, query=query)
    finally:
        sys.setprofile(previous)
    return result, work


def frozen_grammar_parts(namespace, value):
    """Original post-normalization lexical grammar, without O's certificate."""
    result = []
    for match in namespace["RUNS"].finditer(value):
        token = match.group()
        if namespace["CJK_RUN"].fullmatch(token):
            result.extend([token] if len(token) == 1 else
                          [token[index:index + 2] for index in range(len(token) - 1)])
        else:
            result.extend(part for part in namespace["IDENTIFIER_SEPARATOR"].split(token) if part)
    return result


class AsciiWordBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(lexical.__file__).read_text(encoding="utf-8")
        for block in (FIXED_MODULE_BLOCK, FIXED_BRANCH_BLOCK):
            if source.count(block) != 1:
                raise AssertionError("O source must contain exactly the registered block")
        counterpart = source.replace(FIXED_MODULE_BLOCK, "", 1).replace(FIXED_BRANCH_BLOCK, "", 1)
        if hashlib.sha256(counterpart.encode("utf-8")).hexdigest() != COUNTERPART_TEXT_SHA256:
            raise AssertionError("O whole-file inverse does not reproduce its exact frozen counterpart")
        path = Path(__file__).resolve().parent / "fixtures" / "round5_o_unfixed_text.txt"
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != UNFIXED_TEXT_SHA256:
            raise AssertionError("Historical O witness source drifted")
        unfixed = payload.decode("utf-8")
        for block in (UNFIXED_MODULE_BLOCK, UNFIXED_BRANCH_BLOCK):
            if unfixed.count(block) != 1:
                raise AssertionError("Historical O source does not contain the original blocks")
        lm = unfixed.replace(UNFIXED_MODULE_BLOCK, "", 1).replace(UNFIXED_BRANCH_BLOCK, "", 1)
        if hashlib.sha256(lm.encode("utf-8")).hexdigest() != FROZEN_LM_TEXT_SHA256:
            raise AssertionError("Independent historical inverse is not the complete frozen LM file")
        cls.counterpart = counterpart
        cls.lm_source = lm
        cls.unfixed_source = unfixed
        cls.lm_namespace = frozen_namespace(lm, "frozen_lm_ascii_reference")
        cls.unfixed_namespace = frozen_namespace(unfixed, "frozen_unfixed_o_reference")

    def references(self, include_unfixed=False):
        result = [
            ("literal-pre-k", literal_terms, lexical.__dict__),
            ("frozen-lm", self.lm_namespace["terms"], self.lm_namespace),
            ("current", lexical.terms, lexical.__dict__),
        ]
        if include_unfixed:
            result.insert(2, ("unfixed-o", self.unfixed_namespace["terms"], self.unfixed_namespace))
        return result

    def test_complete_inverse_historical_fixture_and_all_old_source_modules(self):
        self.assertEqual(hashlib.sha256(self.counterpart.encode("utf-8")).hexdigest(),
                         COUNTERPART_TEXT_SHA256)
        self.assertEqual(hashlib.sha256(self.lm_source.encode("utf-8")).hexdigest(),
                         FROZEN_LM_TEXT_SHA256)
        self.assertEqual(hashlib.sha256(self.unfixed_source.encode("utf-8")).hexdigest(),
                         UNFIXED_TEXT_SHA256)
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(len(FROZEN_MODULES), 15)
        self.assertEqual(len(UNCHANGED_SOURCE_FILES), 17)
        for path, expected in {**FROZEN_MODULES, **UNCHANGED_SOURCE_FILES}.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((root / path).read_bytes()).hexdigest(), expected)
        runtime = root / "src" / "memory_book"
        actual_python = {str(path.relative_to(root)) for path in runtime.rglob("*.py")}
        expected_python = {path for path in UNCHANGED_SOURCE_FILES if path.endswith(".py")}
        expected_python.add("src/memory_book/text.py")
        self.assertEqual(actual_python, expected_python)
        self.assertIs(lexical.STOP, lexical._ORDINARY_STOP)
        self.assertIs(type(lexical._ORDINARY_STOP), frozenset)
        self.assertTrue(all(type(part) is str for part in lexical._ORDINARY_STOP))

    def test_every_unicode_scalar_certificate_matches_independent_old_grammar(self):
        counts = {"scalars": 0, "rejected": 0, "old_cjk": 0, "unassigned_cjk": 0}
        old_runs = self.lm_namespace["RUNS"]
        for code in range(0x110000):
            character = chr(code)
            expected = independent_exclusion(character)
            actual = lexical._ASCII_LEXICAL_EXCLUSIONS.search(character) is not None
            if actual != expected:
                self.fail("certificate differs at " + hex(code))
            if bool(OLD_WORD.fullmatch(character)) != (character.isalnum() or character == "_"):
                self.fail("independent Unicode word oracle differs at " + hex(code))
            if not expected and character not in ASCII_WORDS:
                if old_runs.fullmatch(character) is not None:
                    self.fail("certified separator is an old grammar token at " + hex(code))
            if in_old_cjk(code):
                if not actual or self.lm_namespace["CJK_RUN"].fullmatch(character) is None:
                    self.fail("old CJK scalar was not rejected at " + hex(code))
                counts["old_cjk"] += 1
                counts["unassigned_cjk"] += unicodedata.category(character) == "Cn"
            counts["scalars"] += 1
            counts["rejected"] += expected
        self.assertEqual(counts["scalars"], 0x110000)
        self.assertEqual(counts["old_cjk"], 28096)
        self.assertGreater(counts["unassigned_cjk"], 0)
        self.assertIsNone(lexical._ASCII_LEXICAL_EXCLUSIONS.search(""))
        print("O exhaustive scalar certificate; no timing claim:", {
            "ucd": unicodedata.unidata_version, **counts,
            "corpus_retrieval_calls": 0, "fresh_rows_decoded": 0})

    def test_unassigned_cjk_stays_in_original_cjk_grammar(self):
        values = [chr(code) for lo, hi in CJK_RANGES for code in range(lo, hi + 1)
                  if unicodedata.category(chr(code)) == "Cn"]
        self.assertTrue(values)
        for character in values:
            value = "alpha" + character + "beta"
            with self.subTest(codepoint=hex(ord(character))):
                self.assertIsNotNone(lexical._ASCII_LEXICAL_EXCLUSIONS.search(character))
                self.assertIn(character, frozen_grammar_parts(self.lm_namespace, value))
                for query in (False, True):
                    expected = self.lm_namespace["terms"](value, query=query)
                    self.assertEqual(lexical.terms(value, query=query), expected)
                    self.assertEqual(literal_terms(value, query), expected)

    def test_every_ascii_identifier_connector_boundary_has_identical_tokens(self):
        connectors = [""]
        for size in range(1, 5):
            connectors.extend("".join(parts) for parts in itertools.product("_./:-", repeat=size))
        for connector in connectors:
            for value in ("alpha" + connector + "beta—gamma" + connector + "delta",
                          connector + "alpha—beta" + connector):
                with self.subTest(connector=connector, value=value):
                    self.assertIsNone(lexical._ASCII_LEXICAL_EXCLUSIONS.search(value))
                    self.assertEqual(frozen_grammar_parts(self.lm_namespace, value),
                                     re.findall(r"[a-z0-9]+", value))
                    for query in (False, True):
                        actual = lexical.terms(value, query=query)
                        self.assertEqual(actual, self.lm_namespace["terms"](value, query=query))
                        self.assertEqual(actual, literal_terms(value, query))

    def test_unicode_punctuation_fold_marks_format_and_surrogate_boundaries(self):
        separators = ("—", "’", "“”", "。、", "‐", "‑", "…", "\u2028", "\u2029",
                      "\u00a0", "\u2009", "\u200b", "\u200c", "\u200d", "\u200f",
                      "\u2060", "👩\u200d💻", "\x00", "\ud800", "\udfff",
                      "\u20dd", "\u093e", "\u0301", "\ufe0f")
        cases = [left + separator + right for separator in separators
                 for left, right in (("alpha", "beta_gamma"), ("AlphaBeta", "ＧammaDelta"),
                                     ("e\u0301", "Straße"), ("a\u0315\u0300", "İKelvin"))]
        cases.extend(("汉字—alpha", "\U00020000—alpha", "١٢٣—beta", "βΣ—alpha",
                      "가—alpha", "Ⅻ—alpha", "㍿—alpha", "ＡlphaＢeta—gamma",
                      "为什么alpha—beta", "请告诉我alpha—beta", "the—alpha_and_beta"))
        for value in cases:
            for query in (False, True):
                with self.subTest(value=value, query=query):
                    actual = lexical.terms(value, query=query)
                    self.assertEqual(actual, self.lm_namespace["terms"](value, query=query))
                    self.assertEqual(actual, literal_terms(value, query))
                    self.assertEqual(lexical.index_text(value), " ".join(literal_terms(value)))
                    self.assertEqual(lexical.query_terms(value),
                                     list(dict.fromkeys(literal_terms(value, True)))[:64])

    def test_real_c_calls_and_generator_entries_show_only_the_certified_route(self):
        examples = ("alpha—beta_gamma", "alpha…beta”gamma", "👩\u200d💻AlphaBeta\x00gamma—delta",
                    "e\u0301—alphaＢeta", "a\u20ddb\u200fc", "the—alpha_and_beta")
        records = []
        for value in examples:
            for query in (False, True):
                actual, work = actual_pattern_work(lexical.terms, lexical.__dict__, value, query)
                expected, previous = actual_pattern_work(
                    self.lm_namespace["terms"], self.lm_namespace, value, query)
                with self.subTest(value=value, query=query):
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual, literal_terms(value, query))
                    self.assertEqual(work["ascii_findall"], 1)
                    self.assertEqual(work["runs_finditer"], 0)
                    self.assertEqual(work["identifier_split"], 0)
                    self.assertEqual(work["lexical_generator_resumptions"], 0)
                    self.assertEqual(previous["ascii_findall"], 0)
                    self.assertEqual(previous["runs_finditer"], 1)
                    self.assertGreater(previous["identifier_split"], 0)
                    self.assertGreater(previous["lexical_generator_resumptions"], 0)
                records.append({"query": query, "candidate": work, "frozen_lm": previous})
        print("O actual invented regex/loop mechanism; no timing claim:", records)

