"""Fresh correctness fixtures for the registered round-four token candidate."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book.store import MemoryBook
from memory_book.token_budget import (
    TokenCounter, assemble, assemble_with_count, prepare_source_units,
    projected_units, source_units,
)


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None


def page(identity, text, *, original=None, lo=0, hi=None, session=None):
    original = text if original is None else original
    hi = len(original) if hi is None else hi
    refs = [{"turn_index": 0, "start": 0, "end": len(text),
             "turn_start": lo, "turn_end": hi}]
    return {"id": identity, "project_id": "fresh-round4",
            "session_id": session or identity, "session_pk": session or identity,
            "created_at": "2026-11-13T00:00:00Z", "content": text,
            "source_refs": json.dumps(refs)}


def header(row):
    return f'[{row["id"]}] {row["project_id"]} / {row["session_id"]} | {row["created_at"]}\n'


def entry(row):
    return row, header(row), row["content"], [(0, len(row["content"]))]


def parsed_refs(rows):
    return {row["id"]: json.loads(row["source_refs"]) for row in rows}


def linear_projection(row, turns, cache):
    """The pre-round-four containment/equality rule, without a start index."""
    spans = set()
    for ref in json.loads(row["source_refs"]):
        key = row["session_pk"], ref["turn_index"]
        original = turns[key]
        if key not in cache:
            cache[key] = source_units(original)
        for start, end in cache[key]:
            if ref["turn_start"] <= start < end <= ref["turn_end"]:
                lo = ref["start"] + start - ref["turn_start"]
                hi = ref["start"] + end - ref["turn_start"]
                if row["content"][lo:hi] != original[start:end]:
                    raise ValueError("Page source coordinates do not match the original turn")
                spans.add((lo, hi))
    return sorted(spans)


def eager_units(rows, turns, refs_by_page):
    cache = {}
    ready = {row["id"]: linear_projection(row, turns, cache) for row in rows}
    return lambda row: ready[row["id"]]


def source(session="one", text=None):
    return {"project": "fresh-round4", "session_id": session,
            "created_at": "2026-11-13T00:00:00Z", "task_id": session,
            "messages": [
                {"role": "user", "content": "Which pressure and retry were recorded?"},
                {"role": "assistant", "content": text or (
                    "Pressure is 82 pascals. Retry is 45 seconds.\n" +
                    "Additional background stays available for exact inspection. " * 45)},
            ]}


def stable(payload):
    return {key: value for key, value in payload.items() if key != "latency_ms"}


class ScriptCounter:
    def __init__(self, counts, *, prepared=None, minimum=0):
        self.counts = dict(counts)
        self.calls = []
        self.prepared = prepared
        self.minimum = minimum

    def count(self, text):
        self.calls.append(text)
        return self.counts[text]

    def count_after(self, prefix):
        owner = self

        class Prepared:
            minimum_tokens = owner.minimum

            def __call__(self, text):
                return owner.prepared

        return Prepared()


class ProjectionAndCertificateTests(unittest.TestCase):
    def test_long_turn_nested_spans_keep_exact_containment(self):
        lines = [f"Record {i:04d}: pressure is 82. Retry is 45.\r\n" for i in range(500)]
        lines[230:230] = ["```python\r\n", "USER: ```\r\n", "value = '缓存 👩🏽‍💻'\r\n", "```\r\n"]
        original = "".join(lines)
        units = source_units(original)
        turns = {("long", 0): original}
        cuts = [(0, len(lines[0])),
                (len("".join(lines[:229])), len("".join(lines[:236]))),
                (len("".join(lines[:231])) + 2, len("".join(lines[:233])) - 1),
                (len(original) - 100, len(original))]
        for lo, hi in cuts:
            row = page("cut", original[lo:hi], original=original, lo=lo, hi=hi, session="long")
            with self.subTest(lo=lo, hi=hi):
                self.assertEqual(projected_units(row, turns, {("long", 0): units}),
                                 linear_projection(row, turns, {("long", 0): units}))

    def test_same_start_longer_ends_are_still_excluded(self):
        original = "0123456789" * 10
        row = page("nested", original[10:40], original=original, lo=10, hi=40)
        units = [(0, 100), (10, 20), (10, 40), (10, 60),
                 (20, 25), (25, 40), (30, 60), (40, 50)]
        self.assertEqual(projected_units(row, {("nested", 0): original},
                                         {("nested", 0): units}),
                         [(0, 10), (0, 30), (10, 15), (15, 30)])

    def test_source_parsing_is_lazy_and_cached_by_session_and_ordinal(self):
        one = page("one", "Pressure is 82.\nRetry is 45.")
        two = page("two", "Pressure is 93.\nRetry is 60.")
        rows = [one, two]
        turns = {(row["session_pk"], 0): row["content"] for row in rows}
        with patch("memory_book.token_budget.source_units", wraps=source_units) as parse:
            resolve = prepare_source_units(rows, turns, parsed_refs(rows))
            self.assertEqual(parse.call_count, 0)
            expected = linear_projection(two, turns, {})
            self.assertEqual(resolve(two), expected)
            self.assertEqual(resolve(two), expected)
            self.assertEqual(parse.call_args_list, [unittest.mock.call(two["content"])])

    def test_uncertified_difference_without_a_complete_unit_keeps_old_acceptance(self):
        original = "Prelude.\n```python\npressure = 82\n"
        lo = original.index("```")
        row = page("partial", original[lo:].replace("82", "93"),
                   original=original, lo=lo)
        turns = {("partial", 0): original}
        self.assertEqual(linear_projection(row, turns, {}), [])
        with patch("memory_book.token_budget.source_units", wraps=source_units) as parse:
            resolve = prepare_source_units([row], turns, parsed_refs([row]))
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(resolve(row), [])
            self.assertEqual(parse.call_count, 1)

    def test_uncertified_unused_end_field_does_not_add_a_rejection(self):
        row = page("bad-end", "Pressure is 82.\nRetry is 45.")
        refs = json.loads(row["source_refs"])
        refs[0]["end"] = -1  # The historical projection rule does not use it.
        row["source_refs"] = json.dumps(refs)
        turns = {("bad-end", 0): row["content"]}
        resolve = prepare_source_units([row], turns, parsed_refs([row]))
        self.assertEqual(resolve(row), linear_projection(row, turns, {}))

    def test_corruption_and_missing_turn_are_rejected_before_resolution(self):
        original = "Pressure is 82."
        row = page("bad", "Pressure is 93.")
        with self.assertRaisesRegex(ValueError, "Page source coordinates"):
            prepare_source_units([row], {("bad", 0): original}, parsed_refs([row]))
        with self.assertRaises(KeyError):
            prepare_source_units([row], {}, parsed_refs([row]))

    def test_noninteger_map_keeps_original_projection_error(self):
        row = page("float", "Pressure is 82.")
        refs = json.loads(row["source_refs"])
        refs[0]["start"] = 0.5
        row["source_refs"] = json.dumps(refs)
        turns = {("float", 0): row["content"]}
        with self.assertRaises(TypeError):
            linear_projection(row, turns, {})
        with self.assertRaises(TypeError):
            prepare_source_units([row], turns, parsed_refs([row]))

    def test_missing_unused_bound_keeps_historical_short_circuit(self):
        row = page("outside", "Pressure is 82.")
        refs = json.loads(row["source_refs"])
        refs[0]["turn_start"] = len(row["content"]) + 1
        del refs[0]["turn_end"]
        row["source_refs"] = json.dumps(refs)
        turns = {("outside", 0): row["content"]}
        self.assertEqual(linear_projection(row, turns, {}), [])
        resolve = prepare_source_units([row], turns, parsed_refs([row]))
        self.assertEqual(resolve(row), [])


class AcceptedCountTests(unittest.TestCase):
    def test_nonmonotonic_counts_preserve_each_first_fit_decision(self):
        rows = [page(name, name) for name in ("first", "second", "third")]
        legacy = [(row, "", row["content"], [(0, len(row["content"]))]) for row in rows]
        counts = {"first": 11, "second": 4, "second\n\nthird": 7,
                  "first\n\nsecond\n\nthird": 1}
        counter = ScriptCounter(counts)
        kept, count = assemble_with_count(legacy, rows, [], budget_chars=1000,
                                          budget_tokens=10, counter=counter)
        self.assertEqual([item[0]["id"] for item in kept], ["second", "third"])
        self.assertEqual(count, 7)
        self.assertEqual(counter.calls, ["first", "second", "second\n\nthird"])
        self.assertEqual(assemble(legacy, rows, [], budget_chars=1000,
                                  budget_tokens=10, counter=ScriptCounter(counts)), kept)

    def test_later_rejections_do_not_replace_the_accepted_count(self):
        rows = [page(name, name) for name in ("first", "second", "third")]
        legacy = [(row, "", row["content"], [(0, len(row["content"]))]) for row in rows]
        counter = ScriptCounter({"first": 6, "first\n\nsecond": 11,
                                 "first\n\nthird": 12})
        kept, count = assemble_with_count(legacy, rows, [], budget_chars=1000,
                                          budget_tokens=10, counter=counter)
        self.assertEqual([item[0]["id"] for item in kept], ["first"])
        self.assertEqual(count, 6)

    def test_prepared_suffix_count_is_retained_on_acceptance(self):
        row = page("suffix", "aaaa\nbbbb\ncccc\ndddd")
        row["token_source_units"] = [(0, 4), (5, 9), (10, 14), (15, 19)]
        counter = ScriptCounter({header(row) + "aaaa…": 11}, prepared=8, minimum=4)
        kept, count = assemble_with_count([], [row], [], budget_chars=1000,
                                          budget_tokens=10, counter=counter)
        self.assertEqual(kept[0][3], [(5, 9)])
        self.assertEqual(count, 8)

    def test_zero_budget_never_requests_supplemental_units(self):
        row = page("zero", "pressure")
        with patch("memory_book.token_budget.source_units", side_effect=AssertionError("parsed")):
            resolve = prepare_source_units([row], {("zero", 0): row["content"]}, parsed_refs([row]))
            kept, count = assemble_with_count([entry(row)], [row], [], budget_chars=1000,
                                              budget_tokens=0,
                                              counter=ScriptCounter({header(row) + row["content"]: 3}),
                                              source_units_for=resolve)
        self.assertEqual((kept, count), ([], 0))


@unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for exact budget checks")
class NativeTokenWorkTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=5000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)
        self.book.ingest(source())

    def test_all_fit_parses_no_units_and_does_not_reencode_final_context(self):
        legacy = self.book.recall("pressure retry", limit=1, use_cache=False)
        ordinary_count = TokenCounter.count
        for tokenizer in ("cl100k_base", "o200k_base"):
            calls = []

            def counted(counter, text):
                calls.append(text)
                return ordinary_count(counter, text)

            with self.subTest(tokenizer=tokenizer), \
                    patch("memory_book.token_budget.source_units", side_effect=AssertionError("unused units")), \
                    patch.object(TokenCounter, "count", counted):
                result = self.book.recall("pressure retry", limit=1, budget_tokens=100000,
                                          tokenizer=tokenizer, use_cache=False)
            self.assertEqual(result["results"], legacy["results"])
            self.assertEqual(result["context"], legacy["context"])
            self.assertEqual(calls, [result["context"]])
            self.assertEqual(result["context_tokens"], ordinary_count(TokenCounter(tokenizer), result["context"]))

    def test_partial_fit_only_parses_the_page_that_needs_a_supplement(self):
        one = page("one", "Pressure is already recorded.")
        two = page("two", "Pressure is 82 pascals.\n" + "Further detail remains available. " * 100)
        rows = [one, two]
        turns = {(row["session_pk"], 0): row["content"] for row in rows}
        for tokenizer in ("cl100k_base", "o200k_base"):
            counter = TokenCounter(tokenizer)
            expected = header(one) + one["content"] + "\n\n" + header(two) + "Pressure is 82 pascals.…"
            cap = counter.count(expected)
            with self.subTest(tokenizer=tokenizer), \
                    patch("memory_book.token_budget.source_units", wraps=source_units) as parse:
                resolve = prepare_source_units(rows, turns, parsed_refs(rows))
                kept, count = assemble_with_count([entry(row) for row in rows], rows, ["pressure"],
                                                  budget_chars=10000, budget_tokens=cap,
                                                  counter=counter, source_units_for=resolve)
            self.assertEqual("\n\n".join(head + text for _, head, text, _ in kept), expected)
            self.assertEqual(count, cap)
            self.assertEqual(parse.call_args_list, [unittest.mock.call(two["content"])])

    def test_unicode_fences_scopes_and_budgets_match_eager_linear_projection(self):
        text = ("Pressure is 82 pascals.\r\nRetry is 45 seconds.\r\n"
                "缓存保留45秒。 café e\u0301 👩🏽‍💻 <|endoftext|> is literal.\r\n"
                "```python\r\npressure = 82\r\nUSER: ```\r\nretry = 45\r\n```\r\n" +
                "Background remains inspectable. " * 80 +
                "\r\n~~~python\r\nunfinished_pressure = 93\r\n")
        self.book.ingest(source("unicode", text))
        for tokenizer in ("cl100k_base", "o200k_base"):
            independent = TokenCounter(tokenizer)
            for chars in (0, 160, 1200, 8000):
                for tokens in (0, 1, 64, 128, 1024):
                    options = dict(project="fresh-round4", budget_chars=chars,
                                   budget_tokens=tokens, tokenizer=tokenizer, use_cache=False)
                    with self.subTest(tokenizer=tokenizer, chars=chars, tokens=tokens):
                        with patch("memory_book.token_budget.prepare_source_units", eager_units):
                            expected = self.book.recall("pressure and retry 缓存", **options)
                        result = self.book.recall("pressure and retry 缓存", **options)
                        self.assertEqual(stable(result), stable(expected))
                        self.assertEqual(result["context_tokens"], independent.count(result["context"]))
                        self.assertLessEqual(result["context_tokens"], tokens)
                        self.assertLessEqual(len(result["context"]), chars)

    def test_corrupt_unused_source_is_rejected_and_read_transaction_rolls_back(self):
        row = self.book.db.execute("SELECT id,content FROM pages LIMIT 1").fetchone()
        self.book.db.execute("UPDATE pages SET content=? WHERE id=?",
                             (row["content"].replace("82", "93"), row["id"]))
        for tokenizer in ("cl100k_base", "o200k_base"):
            with self.subTest(tokenizer=tokenizer), self.assertRaisesRegex(ValueError, "Page source coordinates"):
                self.book.recall("pressure", budget_tokens=100000, tokenizer=tokenizer, use_cache=False)
            self.assertFalse(self.book.db.in_transaction)
        self.book.db.execute("UPDATE pages SET content=? WHERE id=?", (row["content"], row["id"]))
        self.assertIn("82 pascals", self.book.recall("pressure", budget_tokens=100000)["context"])

    def test_external_writer_cannot_change_captured_lazy_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.db"
            with MemoryBook(path, segmentation="turn", max_page_chars=5000, min_page_chars=0,
                            cache_size=0) as reader, MemoryBook(path, segmentation="turn",
                                                              max_page_chars=5000, min_page_chars=0) as writer:
                reader.ingest(source())
                options = dict(budget_tokens=96, use_cache=False)
                expected = reader.recall("pressure retry", **options)
                self.assertIn("82 pascals", expected["context"])
                state = {"written": False, "resolving": False}
                late_reads = []

                def trace(statement):
                    if state["resolving"]:
                        late_reads.append(statement)

                def prepare(rows, turns, refs):
                    resolve = prepare_source_units(rows, turns, refs)

                    def after_commit(row):
                        self.assertFalse(reader.db.in_transaction)
                        state["resolving"] = True
                        if not state["written"]:
                            writer.ingest(source(text="Pressure is now 97 pascals. Retry is 60 seconds."))
                            state["written"] = True
                        return resolve(row)

                    return after_commit

                reader.db.set_trace_callback(trace)
                with patch("memory_book.token_budget.prepare_source_units", prepare):
                    result = reader.recall("pressure retry", **options)
                reader.db.set_trace_callback(None)
                self.assertTrue(state["written"])
                self.assertEqual(late_reads, [])
                self.assertEqual(stable(result), stable(expected))
                self.assertGreater(reader.revision, result["revision"])
                self.assertIn("97 pascals", reader.recall("pressure retry", **options)["context"])


if __name__ == "__main__":
    unittest.main()
