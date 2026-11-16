"""Independent v0.8.1 segmentation oracle and native-family compatibility."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

from memory_book import segmentation as segmentation

ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)
TURN, PAGE, SECTION = segmentation.Turn, segmentation.Page, segmentation.Section
HEADLINE, SIMILARITY, FOLLOWUP = segmentation.headline, segmentation.similarity, segmentation.is_followup

_REFERENCE_SOURCE = "def make_turns(messages: list[dict]) -> list[Turn]:\n    groups: list[list[tuple[int, dict]]] = []\n    pending: list[tuple[int, dict]] = []\n    for i, message in enumerate(messages):\n        if message[\"role\"] == \"user\":\n            if pending and any(m[\"role\"] in {\"user\", \"assistant\", \"tool\"} for _, m in pending):\n                groups.append(pending)\n            pending = [(i, message)]\n        elif pending or message[\"role\"] in {\"assistant\", \"tool\"}:\n            pending.append((i, message))\n    if pending:\n        groups.append(pending)\n    turns: list[Turn] = []\n    for group in groups:\n        question = next((m[\"content\"] for _, m in group if m[\"role\"] == \"user\"), \"Conversation note\")\n        body = \"\\n\\n\".join(f'{m[\"role\"].upper()}: {m[\"content\"]}' for _, m in group)\n        turns.append(Turn(len(turns), question, body, tuple(i for i, _ in group)))\n    return turns\n\n\ndef _joined(turns: list[Turn]) -> tuple[str, list[dict]]:\n    parts, refs, pos = [], [], 0\n    for turn in turns:\n        if parts:\n            pos += 2\n        parts.append(turn.content)\n        refs.append({\"turn_index\": turn.index, \"start\": pos, \"end\": pos + len(turn.content), \"turn_start\": 0, \"turn_end\": len(turn.content), \"message_indices\": list(turn.message_indices)})\n        pos += len(turn.content)\n    return \"\\n\\n\".join(parts), refs\n\n\ndef _cuts(text: str, cap: int) -> list[tuple[int, int]]:\n    \"\"\"Prefer paragraph/line breaks; hard split oversized lines without data loss.\"\"\"\n    cuts, start = [], 0\n    while start < len(text):\n        end = min(start + cap, len(text))\n        if end < len(text):\n            floor = start + cap // 2\n            boundary = text.rfind(\"\\n\\n\", floor, end)\n            if boundary < 0:\n                boundary = text.rfind(\"\\n\", floor, end)\n            if boundary >= floor:\n                end = boundary + (2 if text[boundary:boundary + 2] == \"\\n\\n\" else 1)\n        cuts.append((start, end))\n        start = end\n    return cuts\n\n\ndef _pages(group: list[Turn], cap: int | None) -> tuple[Page, ...]:\n    text, refs = _joined(group)\n    spans = [(0, len(text))] if cap is None else _cuts(text, cap)\n    question_hints = {t.index: headline(t.question, 240) for t in group}\n    first_title = headline(group[0].question, 76)\n    pages = []\n    for number, (start, end) in enumerate(spans):\n        local_refs = []\n        for ref in refs:\n            lo, hi = max(start, ref[\"start\"]), min(end, ref[\"end\"])\n            if lo < hi:\n                local_refs.append({**ref, \"start\": lo - start, \"end\": hi - start, \"turn_start\": lo - ref[\"start\"], \"turn_end\": hi - ref[\"start\"]})\n        suffix = f\" · {number + 1}/{len(spans)}\" if len(spans) > 1 else \"\"\n        local_turns = {r[\"turn_index\"] for r in local_refs}\n        # A long user prompt must not be copied in full into every continuation\n        # page: doing so grows the index quadratically in prompt length.\n        question = \" | \".join(question_hints[t.index] for t in group if t.index in local_turns)[:1200]\n        pages.append(Page(first_title + suffix, question, text[start:end], tuple(local_refs)))\n    return tuple(pages)\n\n\ndef segment(turns: list[Turn], mode: str, max_chars: int, min_chars: int, threshold: float) -> list[Section]:\n    if mode not in {\"adaptive\", \"turn\", \"session\"}:\n        raise ValueError(\"segmentation must be adaptive, turn, or session\")\n    if not turns:\n        raise ValueError(\"session needs at least one user, assistant, or tool message\")\n    groups: list[list[Turn]] = []\n    if mode == \"session\":\n        groups = [turns]\n    elif mode == \"turn\":\n        groups = [[turn] for turn in turns]\n    else:\n        current: list[Turn] = []\n        size = 0\n        for turn in turns:\n            related = not current or similarity(current[-1].question, turn.question) >= threshold or is_followup(turn.question)\n            can_fit = size + len(turn.content) + 2 <= max_chars\n            # Tiny adjacent notes may share a section until the minimum size;\n            # beyond that, a topic change starts a new section. This is an\n            # explicit heuristic, evaluated against turn/session baselines.\n            if current and (not can_fit or (not related and size >= min_chars) or len(current) >= 4):\n                groups.append(current)\n                current, size = [], 0\n            current.append(turn)\n            size += len(turn.content) + 2\n        if current:\n            groups.append(current)\n    return [Section(headline(g[0].question), \" · \".join(headline(t.question, 96) for t in g)[:360], _pages(g, max_chars if mode == \"adaptive\" else None)) for g in groups]\n"
_REFERENCE_CODE = compile(_REFERENCE_SOURCE, __file__ + ':v0.8.1', 'exec')


def reference_namespace():
    namespace = dict(Turn=TURN, Page=PAGE, Section=SECTION, headline=HEADLINE,
                     similarity=SIMILARITY, is_followup=FOLLOWUP)
    exec(_REFERENCE_CODE, namespace)
    return namespace


def outcome(operation):
    try:
        return "value", operation()
    except Exception as error:
        return "error", type(error), error.args


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeSegmentationTests(unittest.TestCase):
    def compare(self, name, *args):
        reference = reference_namespace()
        expected = outcome(lambda: reference[name](*args))
        actual = outcome(lambda: getattr(segmentation, name)(*args))
        self.assertEqual(actual, expected, (name, args))
        return actual

    def test_role_grouping_leading_notes_and_message_indices(self):
        cases = [
            [], [{"role": "system", "content": "only ignored system"}],
            [{"role": "assistant", "content": "note"}],
            [{"role": "tool", "content": "note"}, {"role": "developer", "content": "kept"}],
            [{"role": "system", "content": "ignored"}, {"role": "developer", "content": "ignored"},
             {"role": "user", "content": "question 1"}, {"role": "assistant", "content": "answer"},
             {"role": "system", "content": "kept"}, {"role": "tool", "content": "result"},
             {"role": "user", "content": "question 2"}],
            [{"role": "user", "content": ""}, {"role": "user", "content": "第二🙂\ud800"},
             {"role": "other", "content": "\x00"}, {"role": "assistant", "content": "ok"}],
        ]
        for messages in cases:
            self.compare("make_turns", messages)
        turns = segmentation.make_turns(cases[4])
        self.assertEqual(turns[0].message_indices, (2, 3, 4, 5))
        self.assertEqual(turns[1].message_indices, (6,))

    def test_cuts_boundaries_and_full_source_preservation(self):
        self.assertEqual(segmentation._cuts("a" * 7 + "\n\n" + "b" * 5, 8)[0], (0, 9))
        values = ["", "abc", "\n\n\n", "a" * 300, "a\nb\n\nc\n",
                  "中🙂\ud800é\u0301\n\n" * 30, "a" * 7 + "\n\n" + "b" * 30,
                  "a" * 9 + "\n" + "b" * 10, "\r\n\r\nx\u2028y"]
        for value in values:
            for cap in (1, 2, 3, 4, 7, 8, 9, 16, 31, 1000):
                self.compare("_cuts", value, cap)
                spans = segmentation._cuts(value, cap)
                self.assertEqual("".join(value[lo:hi] for lo, hi in spans), value)

    def test_joined_offsets_pages_and_nested_reference_sharing(self):
        turns = [TURN(5, "question one", "a" * 20 + "\n\n" + "b" * 20, (1, 2)),
                 TURN(9, "question two", "缓存🙂\ud800\n" * 10, (3, 4))]
        self.compare("_joined", turns)
        for cap in (None, 1, 8, 20, 40, 1000):
            self.compare("_pages", turns, cap)
        pages = segmentation._pages([turns[0]], 8)
        self.assertIsNot(pages[0].refs[0], pages[1].refs[0])
        self.assertIs(pages[0].refs[0]["message_indices"], pages[1].refs[0]["message_indices"])
        pages[0].refs[0]["message_indices"].append(99)
        self.assertEqual(pages[1].refs[0]["message_indices"], [1, 2, 99])
        expected_keys = ["turn_index", "start", "end", "turn_start", "turn_end", "message_indices"]
        self.assertEqual(list(pages[0].refs[0]), expected_keys)
        empty = [TURN(0, "empty", "", ())]
        self.assertEqual(len(segmentation._pages(empty, None)), 1)
        self.assertEqual(segmentation._pages(empty, 8), ())

    def test_grouping_size_accounting_maximum_four_and_modes(self):
        turns = [TURN(i, "same question", "aaaa", (i,)) for i in range(9)]
        for maximum in (6, 10, 12, 18, 1000):
            for minimum in (0, 5, 1000):
                for threshold in (0, 0.12, 1, float("nan")):
                    self.compare("segment", turns, "adaptive", maximum, minimum, threshold)
        self.assertEqual(len(segmentation.segment(turns[:2], "adaptive", 10, 0, .12)), 2)
        self.assertEqual(len(segmentation.segment(turns[:2], "adaptive", 12, 0, .12)), 1)
        self.assertEqual(len(segmentation.segment(turns, "adaptive", 1000, 0, .12)), 3)
        for mode in ("turn", "session", "invalid", [], None):
            self.compare("segment", turns, mode, 20, 0, .12)
        self.compare("segment", [], "adaptive", 20, 0, .12)

    def test_seeded_messages_and_adaptive_outputs(self):
        rng = random.Random(904337)
        roles = ["user", "assistant", "tool", "system", "developer", "other"]
        alphabet = "abc AB09\n\t缓存éß🙂\ud800\udfff。"
        for _ in range(100):
            messages = [{"role": rng.choice(roles),
                         "content": "".join(rng.choices(alphabet, k=rng.randrange(0, 100)))}
                        for _ in range(rng.randrange(1, 18))]
            self.compare("make_turns", messages)
            turns = segmentation.make_turns(messages)
            self.compare("_joined", turns)
            for mode in ("adaptive", "turn", "session"):
                self.compare("segment", turns, mode, rng.randrange(1, 130), rng.randrange(0, 80), .12)

    def test_related_short_circuit_is_preserved_even_when_over_capacity(self):
        turns = [TURN(i, "q" + str(i), "x" * 40, (i,)) for i in range(6)]
        for maximum in (30, 10000):
            for similar in (True, False):
                observations = []
                for native in (False, True):
                    namespace = reference_namespace()
                    calls = []

                    def similarity(left, right):
                        calls.append(("similarity", left, right))
                        return 1.0 if similar else 0.0

                    def followup(question):
                        calls.append(("followup", question))
                        return False

                    namespace.update(similarity=similarity, is_followup=followup)
                    value = (NATIVE.segment_turns(turns, "adaptive", maximum, 0, .5, namespace)
                             if native else namespace["segment"](turns, "adaptive", maximum, 0, .5))
                    observations.append((value, calls))
                self.assertEqual(observations[0], observations[1])
                self.assertEqual(sum(call[0] == "similarity" for call in observations[0][1]), 5)
                self.assertEqual(any(call[0] == "followup" for call in observations[0][1]), not similar)

    def test_question_hint_key_is_evaluated_before_headline_callback(self):
        observations = []
        for native in (False, True):
            namespace = reference_namespace()
            turn = TURN(5, "question", "content " * 10, (0,))
            calls = []

            def headline(value, limit=88):
                calls.append((limit, turn.index))
                if limit == 240:
                    object.__setattr__(turn, "index", 7)
                elif limit == 76:
                    object.__setattr__(turn, "index", 5)
                return HEADLINE(value, limit)

            namespace["headline"] = headline
            value = (NATIVE.build_pages([turn], 15, namespace)
                     if native else namespace["_pages"]([turn], 15))
            observations.append((value, calls))
        self.assertEqual(observations[0], observations[1])
        self.assertTrue(all(page.question == "question" for page in observations[0][0]))

    def test_duplicate_turn_indices_keep_last_hint_and_original_repetitions(self):
        turns = [TURN(5, "first question", "first body", (1,)), TURN(5, "second question", "second body", (2,))]
        self.compare("_pages", turns, None)
        pages = segmentation._pages(turns, None)
        self.assertEqual(pages[0].question, "second question | second question")

    def test_all_five_public_entrypoints_really_dispatch(self):
        messages = [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer " * 20}]
        turns = segmentation.make_turns(messages)
        operations = [
            ("make_turns", lambda: segmentation.make_turns(messages)),
            ("joined_turns", lambda: segmentation._joined(turns)),
            ("page_cuts", lambda: segmentation._cuts("body " * 30, 20)),
            ("build_pages", lambda: segmentation._pages(turns, 20)),
            ("segment_turns", lambda: segmentation.segment(turns, "adaptive", 40, 0, .12)),
        ]
        for name, operation in operations:
            with patch.object(NATIVE, name, wraps=getattr(NATIVE, name)) as observed:
                operation()
                observed.assert_called_once()


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeSegmentationFallbackTests(unittest.TestCase):
    def compare_paths(self, operation):
        values = []
        for backend in (None, NATIVE):
            with patch.object(segmentation, "_NATIVE", backend):
                values.append(outcome(operation))
        self.assertEqual(values[0], values[1])
        return values[0]

    def test_unusual_messages_turns_numbers_and_exceptions_use_reference(self):
        class Values(list):
            pass

        class Message(dict):
            def __getitem__(self, key):
                if key == "role":
                    raise RuntimeError("custom role")
                return super().__getitem__(key)

        class Turn(TURN):
            pass

        for messages in (Values([{"role": "user", "content": "q"}]),
                         [{"role": "user", "content": None}], [{}], [Message(role="user", content="q")]):
            self.compare_paths(lambda: segmentation.make_turns(messages))
        for turns in (Values([TURN(0, "q", "body", (0,))]), [Turn(0, "q", "body", (0,))],
                      [TURN(True, "q", "body", (0,))], [TURN(0, "q", None, (0,))]):
            self.compare_paths(lambda: segmentation._joined(turns))
            self.compare_paths(lambda: segmentation._pages(turns, 8))
            self.compare_paths(lambda: segmentation.segment(turns, "adaptive", 20, 0, .12))
        turns = [TURN(0, "q", "body " * 10, (0,))]
        for cap in (True, 8.5, 10 ** 100):
            self.compare_paths(lambda: segmentation._pages(turns, cap))

    def test_patched_helpers_and_class_methods_keep_call_order(self):
        turns = [TURN(0, "alpha", "first " * 10, (0,)), TURN(1, "beta", "second " * 10, (1,))]
        for name in ("headline", "similarity", "is_followup", "_joined", "_cuts", "_pages"):
            ordinary = getattr(segmentation, name)
            observations = []
            for backend in (None, NATIVE):
                calls = []

                def observe(*args, **kwargs):
                    calls.append((args, kwargs))
                    return ordinary(*args, **kwargs)

                with patch.object(segmentation, "_NATIVE", backend), patch.object(segmentation, name, observe):
                    actual = segmentation.segment(turns, "adaptive", 30, 0, 1.0)
                observations.append((actual, calls))
            self.assertEqual(observations[0], observations[1])
        ordinary = TURN.__init__
        observations = []
        for backend in (None, NATIVE):
            calls = []

            def initialize(instance, *args, **kwargs):
                calls.append((args, kwargs))
                ordinary(instance, *args, **kwargs)

            with patch.object(TURN, "__init__", initialize), patch.object(segmentation, "_NATIVE", backend):
                actual = segmentation.make_turns([{"role": "user", "content": "q"}])
            observations.append((actual, calls))
        self.assertEqual(observations[0], observations[1])

    def test_direct_unsupported_inputs_return_before_callbacks(self):
        namespace = reference_namespace()

        def forbidden(*args, **kwargs):
            self.fail("unsupported input called a dependency")

        namespace.update(headline=forbidden, similarity=forbidden, is_followup=forbidden)
        self.assertIs(NATIVE.make_turns([{"role": "user", "content": None}], namespace), NotImplemented)
        self.assertIs(NATIVE.joined_turns([object()], namespace), NotImplemented)
        for cap in (0, -1, True, 1.5, 10 ** 100):
            self.assertIs(NATIVE.page_cuts("abc", cap), NotImplemented)
        turn = TURN(0, "q", "body", (0,))
        self.assertIs(NATIVE.build_pages([turn], 0, namespace), NotImplemented)
        self.assertIs(NATIVE.segment_turns([turn], [], 20, 0, .12, namespace), NotImplemented)

    def test_colliding_instance_dict_key_does_not_run_during_native_preflight(self):
        def specimen():
            turn = TURN(0, "question", "body", (0,))
            events = []
            dictionary = turn.__dict__
            content = dictionary.pop("content")

            class Key:
                armed = False

                def __hash__(self):
                    return hash("content")

                def __eq__(self, other):
                    if self.armed:
                        events.append(other)
                        dictionary.clear()
                    return False

            key = Key()
            dictionary[key] = "foreign"
            dictionary["content"] = content
            key.armed = True
            return turn, events

        turn, events = specimen()
        self.assertIs(NATIVE.joined_turns([turn], reference_namespace()), NotImplemented)
        self.assertEqual(events, [])
        observations = []
        for backend in (None, NATIVE):
            turn, events = specimen()
            with patch.object(segmentation, "_NATIVE", backend):
                actual = outcome(lambda: segmentation._joined([turn]))
            observations.append((actual, events))
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0][0][0], "error")
        self.assertEqual(observations[0][0][1], AttributeError)
        self.assertEqual(observations[0][1], ["content"])

    def test_helper_wrapped_before_import_is_not_certified(self):
        script = r'''
import functools, importlib, json
from memory_book import text
from memory_book import segmentation as original
ordinary = text.headline
@functools.wraps(ordinary)
def wrapped(*args, **kwargs):
    return ordinary(*args, **kwargs)
text.headline = wrapped
module = importlib.reload(original)
assert not module._NATIVE_SEGMENTATION_CERTIFIED
turns = module.make_turns([{"role": "user", "content": "q"}, {"role": "assistant", "content": "body " * 20}])
actual = repr(module.segment(turns, "adaptive", 30, 0, .12))
module._NATIVE = None
expected = repr(module.segment(turns, "adaptive", 30, 0, .12))
print(json.dumps([actual, expected]))
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native", PYTHONDONTWRITEBYTECODE="1",
                           PYTHONPATH=str(Path(segmentation.__file__).resolve().parents[1]))
        process = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        actual, expected = json.loads(process.stdout)
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
