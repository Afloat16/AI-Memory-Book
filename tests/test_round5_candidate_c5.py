"""Bounded exact-count reuse: full text, implementation identity and lifecycle."""
from contextlib import contextmanager
import importlib.util
import sys
from types import MethodType, ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import token_budget as budget


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None
TEXT = "[page] fixture / session | 2026-11-14T00:00:00Z\nQuartz pressure is 82."


def populate(book):
    for number, text in enumerate(("Quartz pressure is 82. Retry is 45 seconds. " * 12,
            "Quartz café e\u0301 缓存45秒。 👩🏽‍💻 <|endoftext|> is literal.\n" * 8,
            "Quartz example.\n```python\npressure = 82\n```\nQualification remains.")):
        book.ingest({"project": "fixture", "session_id": str(number), "title": "Quartz",
            "created_at": "2026-11-14T00:00:00Z",
            "messages": [{"role": "user", "content": text}]})


def payload(book, **options):
    result = book.recall("quartz pressure retry", use_cache=False, **options)
    result.pop("latency_ms")
    return result


def attached(name="cl100k_base", memo=None):
    counter = budget.TokenCounter(name)
    memo = budget._ExactTokenMemo() if memo is None else memo
    budget._attach_count_memo(counter, memo)
    return counter, memo


@contextmanager
def fake_encoding(encoder):
    """No optional package or private CoreBPE is required by this fixture."""
    module = ModuleType("tiktoken")
    module.__version__, module.Encoding = "0.12.0", type(encoder)
    module.get_encoding = lambda name: encoder
    budget._encoding.cache_clear()
    try:
        with patch.dict(sys.modules, {"tiktoken": module, "tiktoken._tiktoken": None}):
            yield module
    finally:
        budget._encoding.cache_clear()


class ExactCountMemoWithoutTokensTests(unittest.TestCase):
    def test_lazy_readonly_snapshot_and_character_only_recall(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            initial = book._token_memo_snapshot()
            self.assertEqual((initial["allocated"], initial["entries"], initial["text_bytes"]), (0, 0, 0))
            self.assertEqual((initial["entry_limit"], initial["text_byte_limit"]), (2048, 2097152))
            initial["entries"] = 9000
            populate(book)
            with patch.object(budget, "TokenCounter", side_effect=AssertionError("loaded tokenizer")):
                payload(book)
            self.assertEqual(book._token_memo_snapshot()["allocated"], 0)
            self.assertEqual(book._token_memo_snapshot()["entries"], 0)

    def test_shared_lru_zero_count_and_oversized_text_preserve_bounds(self):
        memo = budget._ExactTokenMemo()
        memo.entry_limit = 2
        first, second = ("cl100k_base", object(), object()), ("o200k_base", object(), object())
        for identity, text, count in ((first, "a", 0), (second, "b", 2)):
            self.assertIsNone(memo.lookup(identity, text))
            memo.store(identity, text, count)
        self.assertEqual(memo.lookup(first, "a"), 0)
        self.assertIsNone(memo.lookup(first, "c"))
        memo.store(first, "c", 3)
        self.assertEqual(list(memo.entries), [(first[0], "a"), (first[0], "c")])
        self.assertEqual(memo.snapshot()["evictions"], 1)
        self.assertEqual(memo.text_bytes, sum(sys.getsizeof(text) for _, text in memo.entries))
        memo.text_byte_limit = memo.text_bytes
        before = list(memo.entries)
        self.assertIsNone(memo.lookup(first, "x" * 200))
        memo.store(first, "x" * 200, 25)
        self.assertEqual(list(memo.entries), before)
        self.assertEqual(memo.snapshot()["oversized_bypasses"], 1)
        replacement = (first[0], first[1], object())
        self.assertIsNone(memo.lookup(replacement, "a"))
        self.assertEqual(memo.snapshot()["entries"], 0)
        self.assertEqual(memo.snapshot()["invalidations"], 1)
        self.assertEqual(memo.identities, {first[0]: replacement[1:]})

    def test_close_clears_retained_text_even_when_both_cleanup_steps_fail(self):
        def fail(message):
            raise RuntimeError(message)
        for db_error, directory_error in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(db_error=db_error, directory_error=directory_error):
                book = MemoryBook.__new__(MemoryBook)
                book.db = SimpleNamespace(close=lambda: fail("db") if db_error else None)
                book._directory_tokens = SimpleNamespace(cache_clear=lambda: fail("directory") if directory_error else None)
                book._semantic_model = object()
                memo = book._token_count_memo = budget._ExactTokenMemo()
                identity = ("cl100k_base", object(), object())
                memo.lookup(identity, TEXT)
                memo.store(identity, TEXT, 1)
                if db_error or directory_error:
                    with self.assertRaisesRegex(RuntimeError, "directory" if directory_error else "db"):
                        book.close()
                else:
                    book.close()
                self.assertEqual((memo.text_bytes, len(memo.entries), len(memo.identities)), (0, 0, 0))
                self.assertIsNone(book._semantic_model)
                self.assertEqual(book._token_memo_snapshot()["misses"], 1)

    def test_fake_encoder_without_private_core_uses_original_exact_path(self):
        class Encoder:
            def __init__(self):
                self.calls = 0
            def encode_ordinary(self, text):
                self.calls += 1
                return list(text)
        encoder = Encoder()
        with fake_encoding(encoder):
            counter, memo = attached()
            self.assertFalse(budget._can_seal_blocks(counter))
            self.assertEqual(counter.count(TEXT), len(TEXT))
            self.assertEqual(counter.count(TEXT), len(TEXT))
            self.assertEqual(encoder.calls, 2)
            self.assertEqual((memo.hits, len(memo.entries)), (0, 0))

    def test_custom_counter_factory_with_slots_keeps_constructor_contract(self):
        class Counter:
            __slots__ = ()
            version = "custom"
            def __init__(self, name):
                if name != "cl100k_base":
                    raise AssertionError(name)
            def count(self, text):
                return len(text)
            def count_after(self, prefix):
                return budget._PrefixTokenCounter(self.count, prefix)
        with MemoryBook(":memory:", cache_size=0, segmentation="turn") as book:
            populate(book)
            with patch.object(budget, "TokenCounter", Counter):
                result = payload(book, budget_tokens=10000)
            self.assertEqual(result["context_tokens"], len(result["context"]))
            self.assertEqual(result["tokenizer_version"], "custom")
            self.assertEqual(book._token_memo_snapshot()["entries"], 0)


@unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for native exact-count memo checks")
class NativeExactCountMemoTests(unittest.TestCase):
    def test_complete_native_text_counts_unicode_and_special_literals_exactly(self):
        memo = budget._ExactTokenMemo()
        texts = [TEXT, "[p]\ncafé e\u0301 缓存 👩🏽‍💻", "[p]\n<|endoftext|><|fim_prefix|>",
                 "[p]\r\n```python\nx = 'a'\n```", "[p]\n\ud800\udfff", "[p]\n "]
        for name in budget.TOKENIZERS:
            counter, _ = attached(name, memo)
            self.assertIs(counter.count.__func__, budget._ORDINARY_COUNT)
            for text in texts:
                expected = len(counter.encoding.encode_ordinary(text))
                self.assertEqual(counter.count(text), expected)
                before = memo.hits
                self.assertEqual(counter.count(text), expected)
                self.assertEqual(memo.hits, before + 1)
                self.assertEqual(memo.entries[(name, text)][1], sys.getsizeof(text))
        self.assertEqual(len(memo.entries), len(texts) * 2)
        self.assertEqual(set(memo.identities), set(budget.TOKENIZERS))
        before = len(memo.entries)
        for text in ("", "evidence", "[header]", "[header]\n", "prefix\n[body]"):
            self.assertEqual(counter.count(text), len(counter.encoding.encode_ordinary(text)))
        self.assertEqual(len(memo.entries), before)

    def test_native_str_subclasses_are_not_hashed_sized_or_normalized(self):
        class Text(str):
            def __hash__(self):
                raise AssertionError("subclass hash invoked")
            def __sizeof__(self):
                raise AssertionError("subclass sizeof invoked")
            def startswith(self, *args):
                raise AssertionError("subclass startswith invoked")
        counter, memo = attached()
        text = Text(TEXT)
        self.assertEqual(counter.count(text), len(counter.encoding.encode_ordinary(text)))
        self.assertEqual((len(memo.entries), memo.hits), (0, 0))
        class Counter(budget.TokenCounter):
            pass
        other = Counter("cl100k_base")
        budget._attach_count_memo(other, memo)
        self.assertIsNone(other._memo)
        self.assertEqual(other.count(TEXT), counter.count(TEXT))

    def test_custom_counter_and_encoder_methods_bypass_even_when_calling_original(self):
        for target_kind, methods in (("counter", ("count", "count_after")),
                                     ("encoder", budget._ENCODER_METHOD_NAMES)):
            for name in methods:
                for class_patch in (False, True):
                    with self.subTest(target=target_kind, method=name, class_patch=class_patch):
                        counter, memo = attached()
                        expected = counter.count(TEXT)
                        target = counter if target_kind == "counter" else counter.encoding
                        original = getattr(type(target), name)
                        def wrapper(instance, *args, **kwargs):
                            return original(instance, *args, **kwargs)
                        patched = type(target) if class_patch else target
                        method = wrapper if class_patch else MethodType(wrapper, target)
                        with patch.object(patched, name, method):
                            self.assertFalse(budget._can_seal_blocks(counter))
                            self.assertEqual(counter.count(TEXT), expected)
                            self.assertEqual(memo.hits, 0)
                            self.assertEqual(len(memo.entries), 0)

    def test_rebinding_original_methods_to_another_receiver_is_uncertified(self):
        other = budget.TokenCounter("o200k_base")
        for method in budget._ENCODER_METHOD_NAMES:
            counter, memo = attached()
            counter.count(TEXT)
            with patch.object(counter.encoding, method, getattr(other.encoding, method)):
                self.assertFalse(budget._can_seal_blocks(counter))
                expected = len(counter.encoding.encode_ordinary(TEXT))
                self.assertEqual(counter.count(TEXT), expected)
                self.assertEqual((memo.hits, len(memo.entries)), (0, 0))
        for method in ("count", "count_after"):
            counter, _ = attached()
            with patch.object(counter, method, getattr(other, method)):
                self.assertFalse(budget._can_seal_blocks(counter))

    def test_unknown_or_removed_pattern_and_versions_keep_full_counting(self):
        import tiktoken
        for change in ("counter-version", "package-version", "pattern", "missing-pattern"):
            counter, memo = attached()
            expected = counter.count(TEXT)
            encoding = counter.encoding
            if change == "missing-pattern":
                original = encoding._pat_str
                del encoding._pat_str
                try:
                    self.assertFalse(budget._can_seal_blocks(counter))
                    self.assertEqual(counter.count(TEXT), expected)
                finally:
                    encoding._pat_str = original
            else:
                target, attribute, value = ((counter, "version", "future") if change == "counter-version"
                    else (tiktoken, "__version__", "future") if change == "package-version"
                    else (encoding, "_pat_str", "unregistered"))
                with patch.object(target, attribute, value):
                    self.assertFalse(budget._can_seal_blocks(counter))
                    self.assertEqual(counter.count(TEXT), expected)
            self.assertEqual((memo.hits, len(memo.entries)), (0, 0))

    def test_core_and_encoding_replacement_invalidate_memo_and_sealing(self):
        import tiktoken
        counter, memo = attached()
        encoding, original = counter.encoding, counter.encoding._core_bpe
        other = budget.TokenCounter("o200k_base").encoding
        counter.count(TEXT)
        try:
            encoding._core_bpe = other._core_bpe
            self.assertFalse(budget._can_seal_blocks(counter))
            self.assertEqual(counter.count(TEXT), len(encoding.encode_ordinary(TEXT)))
            self.assertEqual((memo.hits, len(memo.entries)), (0, 0))
            budget._encoding.cache_clear()
            replacement, replacement_memo = attached()
            self.assertFalse(budget._can_seal_blocks(replacement))
            self.assertEqual(replacement.count(TEXT), len(encoding.encode_ordinary(TEXT)))
            self.assertEqual(len(replacement_memo.entries), 0)
        finally:
            encoding._core_bpe = original
            budget._encoding.cache_clear()
        counter, memo = attached()
        counter.count(TEXT)
        counter.encoding = other
        self.assertFalse(budget._can_seal_blocks(counter))
        self.assertEqual(counter.count(TEXT), len(other.encode_ordinary(TEXT)))
        self.assertEqual((len(memo.entries), len(memo.identities)), (0, 0))
        budget._encoding.cache_clear()
        try:
            with patch.object(tiktoken, "get_encoding", return_value=other):
                new_counter, new_memo = attached()
                self.assertFalse(budget._can_seal_blocks(new_counter))
                self.assertEqual(new_counter.count(TEXT), len(other.encode_ordinary(TEXT)))
                self.assertEqual(len(new_memo.entries), 0)
        finally:
            budget._encoding.cache_clear()

    def test_core_change_during_real_encode_is_not_inserted(self):
        counter, memo = attached()
        encoding, original = counter.encoding, counter.encoding._core_bpe
        alternate = budget.TokenCounter("o200k_base").encoding._core_bpe
        expected = len(encoding.encode_ordinary(TEXT))
        code = type(encoding).encode_ordinary.__code__
        previous = sys.getprofile()
        def observe(frame, event, value):
            if event == "return" and frame.f_code is code and frame.f_locals.get("self") is encoding:
                encoding._core_bpe = alternate
        sys.setprofile(observe)
        try:
            self.assertEqual(counter.count(TEXT), expected)
            self.assertEqual((len(memo.entries), len(memo.identities)), (0, 0))
            self.assertFalse(budget._can_seal_blocks(counter))
        finally:
            sys.setprofile(previous)
            encoding._core_bpe = original

    def test_encode_failure_and_oversized_success_are_never_retained(self):
        counter, memo = attached()
        expected = counter.count(TEXT)
        memo.text_byte_limit = memo.text_bytes
        large = "[large]\n" + "quartz 中文 " * 100
        self.assertEqual(counter.count(large), len(counter.encoding.encode_ordinary(large)))
        self.assertEqual(list(memo.entries), [(counter.name, TEXT)])
        self.assertEqual(memo.oversized_bypasses, 1)
        with patch.object(counter.encoding, "encode_ordinary", side_effect=RuntimeError("encode failed")) as encode:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "encode failed"):
                    counter.count(TEXT)
            self.assertEqual(encode.call_count, 2)
        self.assertEqual(len(memo.entries), 0)
        self.assertEqual(counter.count(TEXT), expected)

    def test_full_payloads_match_uncached_counting_across_caps_and_book_lifetimes(self):
        with MemoryBook(":memory:", cache_size=0, segmentation="turn") as book, \
                MemoryBook(":memory:", cache_size=0) as untouched:
            populate(book)
            for name in budget.TOKENIZERS:
                for cap in (0, 1, 64, 128, 512, 2048):
                    options = dict(tokenizer=name, budget_tokens=cap, budget_chars=8000)
                    with patch.object(budget, "_attach_count_memo"):
                        expected = payload(book, **options)
                    self.assertEqual(payload(book, **options), expected)
                    self.assertEqual(payload(book, **options), expected)
                    self.assertEqual(expected["context_tokens"], budget.TokenCounter(name).count(expected["context"]))
            snapshot = book._token_memo_snapshot()
            self.assertGreater(snapshot["hits"], 0)
            self.assertLessEqual(snapshot["entries"], 2048)
            self.assertLessEqual(snapshot["text_bytes"], 2097152)
            self.assertEqual(untouched._token_memo_snapshot()["allocated"], 0)
            book.close()
            self.assertEqual(book._token_memo_snapshot()["text_bytes"], 0)
            self.assertEqual(book._token_memo_snapshot()["entries"], 0)

    def test_source_corruption_is_still_checked_after_memo_warming(self):
        with MemoryBook(":memory:", cache_size=0, segmentation="turn") as book:
            populate(book)
            result = payload(book, budget_tokens=512, budget_chars=8000)
            payload(book, budget_tokens=512, budget_chars=8000)
            self.assertGreater(book._token_memo_snapshot()["hits"], 0)
            identity = result["results"][0]["id"]
            book.db.execute("UPDATE pages SET content=replace(content,'Quartz','Wrong!') WHERE id=?", (identity,))
            errors = []
            for use_memo in (True, False):
                with patch.object(budget, "_attach_count_memo", wraps=budget._attach_count_memo if use_memo else None):
                    try:
                        payload(book, budget_tokens=512, budget_chars=8000)
                    except Exception as exc:
                        errors.append((type(exc), exc.args))
            self.assertEqual(len(errors), 2)
            self.assertEqual(errors[0], errors[1])


if __name__ == "__main__":
    unittest.main()
