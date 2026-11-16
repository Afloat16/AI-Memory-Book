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
from types import FunctionType
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

    def test_four_native_entrypoints_dispatch_and_joined_keeps_reference(self):
        messages = [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer " * 20}]
        turns = segmentation.make_turns(messages)
        operations = [
            ("make_turns", lambda: segmentation.make_turns(messages)),
            ("page_cuts", lambda: segmentation._cuts("body " * 30, 20)),
            ("build_pages", lambda: segmentation._pages(turns, 20)),
            ("segment_turns", lambda: segmentation.segment(turns, "adaptive", 40, 0, .12)),
        ]
        for name, operation in operations:
            with patch.object(NATIVE, name, wraps=getattr(NATIVE, name)) as observed:
                operation()
                observed.assert_called_once()
        self.assertFalse(hasattr(NATIVE, "joined_turns"))
        with patch.object(segmentation, "_native_segmentation_ready",
                          side_effect=AssertionError("joined must not pay a native readiness check")):
            self.assertEqual(segmentation._joined(turns), reference_namespace()["_joined"](turns))


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
        self.assertIs(NATIVE.build_pages([object()], 8, namespace), NotImplemented)
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
        self.assertIs(NATIVE.build_pages([turn], 8, reference_namespace()), NotImplemented)
        self.assertEqual(events, [])
        for operation_name in ("_joined", "_pages"):
            observations = []
            for backend in (None, NATIVE):
                turn, events = specimen()
                with patch.object(segmentation, "_NATIVE", backend):
                    actual = outcome(lambda: segmentation._joined([turn]) if operation_name == "_joined"
                                     else segmentation._pages([turn], 8))
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

# This is the unchanged readiness body frozen at 0be1f095; execute its code
# against the live module namespace so patched classes/tables are observed.
_READY_REFERENCE_SOURCE = "def _native_segmentation_ready(name: str) -> bool:\n    if _NATIVE is None or not _NATIVE_SEGMENTATION_CERTIFIED:\n        return False\n    classes, functions = _NATIVE_SEGMENTATION_DEPENDENCIES[name]\n    for function in functions:\n        if _NATIVE_SEGMENTATION_GLOBALS.get(function) is not _NATIVE_SEGMENTATION_DEFAULTS[function]:\n            return False\n    for name in classes:\n        cls, new, init, getattribute, fields = _NATIVE_SEGMENTATION_CLASS_STATES[name]\n        if (_NATIVE_SEGMENTATION_GLOBALS.get(name) is not cls\n                or cls.__new__ is not new or cls.__init__ is not init or cls.__getattribute__ is not getattribute\n                or any(cls.__dict__.get(field) is not value for field, value in fields)):\n            return False\n    return True\n"
_ready_namespace = {}
exec(_READY_REFERENCE_SOURCE, _ready_namespace)
_REFERENCE_READY = FunctionType(_ready_namespace["_native_segmentation_ready"].__code__, segmentation.__dict__)


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeSegmentationReadinessTests(unittest.TestCase):
    def call_native(self, name):
        return NATIVE.segmentation_ready(
            name, segmentation._NATIVE_SEGMENTATION_GLOBALS,
            segmentation._NATIVE_SEGMENTATION_DEFAULTS,
            segmentation._NATIVE_SEGMENTATION_CLASS_STATES,
            segmentation._NATIVE_SEGMENTATION_DEPENDENCIES,
        )

    def test_public_guard_really_calls_native_and_matches_frozen_guard(self):
        names = tuple(segmentation._NATIVE_SEGMENTATION_DEPENDENCIES)
        with patch.object(NATIVE, "segmentation_ready", wraps=NATIVE.segmentation_ready) as observed:
            for name in names:
                self.assertIs(_REFERENCE_READY(name), True)
                self.assertIs(segmentation._native_segmentation_ready(name), True)
        self.assertEqual(observed.call_count, len(names))
        for name in names:
            self.assertIs(self.call_native(name), _REFERENCE_READY(name))

    def test_each_dependency_scope_and_each_class_field_is_checked_afresh(self):
        names = tuple(segmentation._NATIVE_SEGMENTATION_DEPENDENCIES)
        for dependency in ("Turn", "Page", "Section", "headline", "similarity", "is_followup",
                           "_joined", "_cuts", "_pages"):
            with self.subTest(dependency=dependency), patch.object(segmentation, dependency, object()):
                for name in names:
                    classes, functions = segmentation._NATIVE_SEGMENTATION_DEPENDENCIES[name]
                    expected = dependency not in classes + functions
                    self.assertIs(_REFERENCE_READY(name), expected)
                    self.assertIs(self.call_native(name), expected)
            for name in names:
                self.assertIs(self.call_native(name), True)
        for class_name, fields in segmentation._NATIVE_SEGMENTATION_FIELDS.items():
            cls = getattr(segmentation, class_name)
            for field in fields:
                with self.subTest(class_name=class_name, field=field), patch.object(cls, field, object(), create=True):
                    for name in names:
                        expected = class_name not in segmentation._NATIVE_SEGMENTATION_DEPENDENCIES[name][0]
                        self.assertIs(_REFERENCE_READY(name), expected)
                        self.assertIs(self.call_native(name), expected)
                for name in names:
                    self.assertIs(self.call_native(name), True)

    def fresh_guard_class(self, class_name):
        # Changing an inherited __new__ can leave CPython's tp_new slot changed
        # after delattr.  Exercise the guard on a disposable class, never the
        # production Turn/Page/Section used by subsequent compatibility tests.
        cls = type("Guard" + class_name, (), {})
        fields = segmentation._NATIVE_SEGMENTATION_FIELDS[class_name]
        state = (cls, cls.__new__, cls.__init__, cls.__getattribute__,
                 tuple((field, cls.__dict__.get(field)) for field in fields))
        states = dict(segmentation._NATIVE_SEGMENTATION_CLASS_STATES)
        states[class_name] = state
        return cls, state, states

    def test_class_methods_keep_scoped_identity_checks(self):
        names = tuple(segmentation._NATIVE_SEGMENTATION_DEPENDENCIES)
        for class_name in ("Turn", "Page", "Section"):
            for method in ("__new__", "__init__", "__getattribute__"):
                cls, _, states = self.fresh_guard_class(class_name)

                def replacement(*args, **kwargs):
                    raise AssertionError("identity checks must not invoke replacement")

                with patch.object(segmentation, class_name, cls), \
                     patch.object(segmentation, "_NATIVE_SEGMENTATION_CLASS_STATES", states):
                    with self.subTest(class_name=class_name, method=method), patch.object(cls, method, replacement):
                        for name in names:
                            expected = class_name not in segmentation._NATIVE_SEGMENTATION_DEPENDENCIES[name][0]
                            self.assertIs(_REFERENCE_READY(name), expected)
                            self.assertIs(self.call_native(name), expected)
                    for name in names:
                        self.assertIs(self.call_native(name), True)

    def test_function_failure_short_circuits_before_invalid_class_state(self):
        states = dict(segmentation._NATIVE_SEGMENTATION_CLASS_STATES, Turn=None)
        with patch.object(segmentation, "_NATIVE_SEGMENTATION_CLASS_STATES", states):
            with patch.object(segmentation, "headline", object()):
                self.assertIs(_REFERENCE_READY("build_pages"), False)
                self.assertIs(self.call_native("build_pages"), False)
            self.assertEqual(outcome(lambda: _REFERENCE_READY("build_pages")),
                             outcome(lambda: self.call_native("build_pages")))

    def test_class_descriptors_keep_read_order_mutations_and_errors(self):
        for behavior in ("same", "field-change", "raise"):
            observations = []
            for operation in (_REFERENCE_READY, self.call_native):
                cls, captured, states = self.fresh_guard_class("Turn")
                events = []

                class Descriptor:
                    def __init__(self, label, value):
                        self.label, self.value = label, value

                    def __get__(self, instance, owner):
                        events.append(self.label)
                        if behavior == "field-change" and self.label == "new":
                            owner.content = "changed during descriptor"
                        if behavior == "raise" and self.label == "init":
                            raise RuntimeError("init certificate lookup")
                        return self.value

                with patch.object(segmentation, "Turn", cls), \
                     patch.object(segmentation, "_NATIVE_SEGMENTATION_CLASS_STATES", states), \
                     patch.object(cls, "content", None, create=True), \
                     patch.object(cls, "__new__", Descriptor("new", captured[1])), \
                     patch.object(cls, "__init__", Descriptor("init", captured[2])), \
                     patch.object(cls, "__getattribute__", Descriptor("getattribute", captured[3])):
                    events.clear()
                    actual = outcome(lambda: operation("make_turns"))
                    observations.append((actual, list(events)))
            self.assertEqual(observations[0], observations[1], behavior)
            expected_events = ["new", "init"] if behavior == "raise" else ["new", "init", "getattribute"]
            self.assertEqual(observations[0][1], expected_events)

    def test_nonexact_guard_tables_fall_back_before_observable_access(self):
        for table_name in ("_NATIVE_SEGMENTATION_GLOBALS", "_NATIVE_SEGMENTATION_DEFAULTS",
                           "_NATIVE_SEGMENTATION_CLASS_STATES", "_NATIVE_SEGMENTATION_DEPENDENCIES"):
            observations = []
            ordinary = getattr(segmentation, table_name)
            for operation in (_REFERENCE_READY, segmentation._native_segmentation_ready):
                events = []

                class Table(dict):
                    def get(self, key, default=None):
                        events.append(("get", key))
                        return super().get(key, default)

                    def __getitem__(self, key):
                        events.append(("getitem", key))
                        return super().__getitem__(key)

                with patch.object(segmentation, table_name, Table(ordinary)):
                    self.assertIs(self.call_native("build_pages"), NotImplemented)
                    self.assertEqual(events, [])
                    actual = outcome(lambda: operation("build_pages"))
                    observations.append((actual, list(events)))
            self.assertEqual(observations[0], observations[1], table_name)
            self.assertTrue(observations[0][1])

    def test_unusual_metadata_preserves_unpack_and_missing_key_errors(self):
        for value in (None, (), ((),), ((), (), ()), (("Turn",), None),
                      [], [()], [(), (), ()], list(range(8)),
                      {}, {0: None}, dict.fromkeys(range(3)), dict.fromkeys(range(8))):
            dependencies = dict(segmentation._NATIVE_SEGMENTATION_DEPENDENCIES, make_turns=value)
            with self.subTest(dependencies=value), patch.object(segmentation, "_NATIVE_SEGMENTATION_DEPENDENCIES", dependencies):
                self.assertEqual(outcome(lambda: _REFERENCE_READY("make_turns")),
                                 outcome(lambda: self.call_native("make_turns")))
        for value in (None, (), (TURN,), tuple(range(6)),
                      [], [TURN], list(range(6)), list(range(9)),
                      {}, {0: TURN}, dict.fromkeys(range(6)), dict.fromkeys(range(9))):
            states = dict(segmentation._NATIVE_SEGMENTATION_CLASS_STATES, Turn=value)
            with self.subTest(state=value), patch.object(segmentation, "_NATIVE_SEGMENTATION_CLASS_STATES", states):
                self.assertEqual(outcome(lambda: _REFERENCE_READY("make_turns")),
                                 outcome(lambda: self.call_native("make_turns")))
        self.assertEqual(outcome(lambda: _REFERENCE_READY("unknown")),
                         outcome(lambda: self.call_native("unknown")))

    def test_container_subclasses_keep_bounded_unpack_errors_without_length_callback(self):
        def unexpected_length(self):
            raise AssertionError("unpacking a container subclass must not call __len__")

        class TupleSubclass(tuple):
            __len__ = unexpected_length

        class ListSubclass(list):
            __len__ = unexpected_length

        class DictSubclass(dict):
            __len__ = unexpected_length

        for expected, table_name, key in (
            (2, "_NATIVE_SEGMENTATION_DEPENDENCIES", "make_turns"),
            (5, "_NATIVE_SEGMENTATION_CLASS_STATES", "Turn"),
        ):
            values = (TupleSubclass(range(expected + 4)),
                      ListSubclass(range(expected + 4)),
                      DictSubclass.fromkeys(range(expected + 4)))
            for value in values:
                table = dict(getattr(segmentation, table_name), **{key: value})
                with self.subTest(count=expected, container=type(value).__name__), patch.object(segmentation, table_name, table):
                    reference = outcome(lambda: _REFERENCE_READY("make_turns"))
                    actual = outcome(lambda: self.call_native("make_turns"))
                self.assertEqual(reference, actual)
                self.assertEqual(actual, ("error", ValueError,
                                         ("too many values to unpack (expected %d)" % expected,)))

    def test_custom_unpack_iterator_is_not_consumed_past_first_extra_value(self):
        observations = []
        for operation in (_REFERENCE_READY, self.call_native):
            events = []

            def values():
                for value in ((), (), "extra", "never"):
                    events.append(value)
                    yield value

            dependencies = dict(segmentation._NATIVE_SEGMENTATION_DEPENDENCIES, make_turns=values())
            with patch.object(segmentation, "_NATIVE_SEGMENTATION_DEPENDENCIES", dependencies):
                actual = outcome(lambda: operation("make_turns"))
            observations.append((actual, events))
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(len(observations[0][1]), 3)



@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeSegmentationModuleStateTests(unittest.TestCase):
    @staticmethod
    def clone_native_module(label):
        specification = importlib.util.spec_from_file_location(
            "memory_book_state_" + label + "._native", NATIVE.__file__)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module

    def test_two_module_instances_keep_independent_lifetimes(self):
        import gc
        import weakref
        namespace = reference_namespace()
        messages = [{"role": "user", "content": "source question"},
                    {"role": "assistant", "content": "answer " * 20}]
        turns = namespace["make_turns"](messages)
        expected_pages = namespace["_pages"](turns, 30)
        expected_sections = namespace["segment"](turns, "adaptive", 30, 0, .12)
        first = self.clone_native_module("first")
        second = self.clone_native_module("second")
        self.assertIsNot(first, second)
        first_reference, second_reference = weakref.ref(first), weakref.ref(second)
        for unused in range(3):
            self.assertEqual(first.make_turns(messages, namespace), turns)
            self.assertEqual(second.build_pages(turns, 30, namespace), expected_pages)
            self.assertEqual(first.build_pages(turns, 30, namespace), expected_pages)
            self.assertEqual(second.segment_turns(turns, "adaptive", 30, 0, .12, namespace), expected_sections)
        held_function = first.make_turns
        del first
        gc.collect()
        self.assertIsNotNone(first_reference())
        self.assertEqual(held_function(messages, namespace), turns)
        del held_function
        gc.collect()
        self.assertIsNone(first_reference())
        self.assertEqual(second.segment_turns(turns, "adaptive", 30, 0, .12, namespace), expected_sections)
        del second
        gc.collect()
        self.assertIsNone(second_reference())

    def test_returned_reference_dict_keeps_its_keys_after_module_collection(self):
        import gc
        import weakref
        namespace = reference_namespace()
        turns = [TURN(7, "q", "original 中🙂", (2, 3))]
        module = self.clone_native_module("retained_result")
        reference = weakref.ref(module)
        actual = module.build_pages(turns, 8, namespace)
        del module
        gc.collect()
        self.assertIsNone(reference())
        self.assertEqual(actual, namespace["_pages"](turns, 8))
        retained_ref = actual[0].refs[0]
        self.assertEqual(list(retained_ref),
                         ["turn_index", "start", "end", "turn_start", "turn_end", "message_indices"])
        self.assertEqual(retained_ref["message_indices"], [2, 3])
        self.assertEqual(actual[0].content[retained_ref["start"]:retained_ref["end"]],
                         turns[0].content[retained_ref["turn_start"]:retained_ref["turn_end"]])

    def test_available_shared_gil_subinterpreters_keep_main_module_working(self):
        script = r'''
import json
try:
    import _xxsubinterpreters as interpreters
except ImportError:
    print(json.dumps({"available": False}))
else:
    from memory_book import segmentation as main
    payload = """
from memory_book import segmentation as module
turns = module.make_turns([{"role": "user", "content": "q"}, {"role": "assistant", "content": "answer " * 10}])
assert module._native_segmentation_ready("make_turns")
joined, refs = module._joined(turns)
assert joined[refs[0]["start"]:refs[0]["end"]] == turns[0].content
assert module.segment(turns, "adaptive", 30, 0, .12)
"""
    def create_shared():
        try:
            return interpreters.create(isolated=False)
        except TypeError:
            return interpreters.create()
    created = []
    try:
        first = create_shared()
        created.append(first)
        second = create_shared()
        created.append(second)
        interpreters.run_string(first, payload)
        interpreters.run_string(second, payload)
        interpreters.destroy(first)
        created.remove(first)
        interpreters.run_string(second, payload)
        turns = main.make_turns([{"role": "user", "content": "main remains live"}])
        assert main._joined(turns)[0] == "USER: main remains live"
        print(json.dumps({"available": True, "interpreters": 2, "main_valid": True}))
    finally:
        for interpreter in reversed(created):
            interpreters.destroy(interpreter)
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native", PYTHONDONTWRITEBYTECODE="1",
                           PYTHONPATH=str(Path(segmentation.__file__).resolve().parents[1]))
        process = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment,
                                 capture_output=True, text=True, timeout=45)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        if not result["available"]:
            self.skipTest("_xxsubinterpreters is not available in this Python build")
        self.assertEqual(result, {"available": True, "interpreters": 2, "main_valid": True})


if __name__ == "__main__":
    unittest.main()
