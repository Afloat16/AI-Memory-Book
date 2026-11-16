"""Deterministic, source-preserving question grouping.

No generated summary replaces source text. Sections group adjacent related
questions; long individual turns are split into addressable continuation pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text import headline, is_followup, similarity
from . import text as _text_module
from ._text_backend import NATIVE as _NATIVE


@dataclass(frozen=True)
class Turn:
    index: int
    question: str
    content: str
    message_indices: tuple[int, ...]


@dataclass(frozen=True)
class Page:
    title: str
    question: str
    content: str
    refs: tuple[dict, ...]


@dataclass(frozen=True)
class Section:
    title: str
    summary: str
    pages: tuple[Page, ...]


def make_turns(messages: list[dict]) -> list[Turn]:
    if _native_segmentation_ready("make_turns"):
        result = _NATIVE.make_turns(messages, _NATIVE_SEGMENTATION_GLOBALS)
        if result is not NotImplemented:
            return result
    groups: list[list[tuple[int, dict]]] = []
    pending: list[tuple[int, dict]] = []
    for i, message in enumerate(messages):
        if message["role"] == "user":
            if pending and any(m["role"] in {"user", "assistant", "tool"} for _, m in pending):
                groups.append(pending)
            pending = [(i, message)]
        elif pending or message["role"] in {"assistant", "tool"}:
            pending.append((i, message))
    if pending:
        groups.append(pending)
    turns: list[Turn] = []
    for group in groups:
        question = next((m["content"] for _, m in group if m["role"] == "user"), "Conversation note")
        body = "\n\n".join(f'{m["role"].upper()}: {m["content"]}' for _, m in group)
        turns.append(Turn(len(turns), question, body, tuple(i for i, _ in group)))
    return turns


def _joined(turns: list[Turn]) -> tuple[str, list[dict]]:
    if _native_segmentation_ready("joined_turns"):
        result = _NATIVE.joined_turns(turns, _NATIVE_SEGMENTATION_GLOBALS)
        if result is not NotImplemented:
            return result
    parts, refs, pos = [], [], 0
    for turn in turns:
        if parts:
            pos += 2
        parts.append(turn.content)
        refs.append({"turn_index": turn.index, "start": pos, "end": pos + len(turn.content), "turn_start": 0, "turn_end": len(turn.content), "message_indices": list(turn.message_indices)})
        pos += len(turn.content)
    return "\n\n".join(parts), refs


def _cuts(text: str, cap: int) -> list[tuple[int, int]]:
    """Prefer paragraph/line breaks; hard split oversized lines without data loss."""
    if _NATIVE is not None:
        result = _NATIVE.page_cuts(text, cap)
        if result is not NotImplemented:
            return result
    cuts, start = [], 0
    while start < len(text):
        end = min(start + cap, len(text))
        if end < len(text):
            floor = start + cap // 2
            boundary = text.rfind("\n\n", floor, end)
            if boundary < 0:
                boundary = text.rfind("\n", floor, end)
            if boundary >= floor:
                end = boundary + (2 if text[boundary:boundary + 2] == "\n\n" else 1)
        cuts.append((start, end))
        start = end
    return cuts


def _pages(group: list[Turn], cap: int | None) -> tuple[Page, ...]:
    if _native_segmentation_ready("build_pages"):
        result = _NATIVE.build_pages(group, cap, _NATIVE_SEGMENTATION_GLOBALS)
        if result is not NotImplemented:
            return result
    text, refs = _joined(group)
    spans = [(0, len(text))] if cap is None else _cuts(text, cap)
    question_hints = {t.index: headline(t.question, 240) for t in group}
    first_title = headline(group[0].question, 76)
    pages = []
    for number, (start, end) in enumerate(spans):
        local_refs = []
        for ref in refs:
            lo, hi = max(start, ref["start"]), min(end, ref["end"])
            if lo < hi:
                local_refs.append({**ref, "start": lo - start, "end": hi - start, "turn_start": lo - ref["start"], "turn_end": hi - ref["start"]})
        suffix = f" · {number + 1}/{len(spans)}" if len(spans) > 1 else ""
        local_turns = {r["turn_index"] for r in local_refs}
        # A long user prompt must not be copied in full into every continuation
        # page: doing so grows the index quadratically in prompt length.
        question = " | ".join(question_hints[t.index] for t in group if t.index in local_turns)[:1200]
        pages.append(Page(first_title + suffix, question, text[start:end], tuple(local_refs)))
    return tuple(pages)


def segment(turns: list[Turn], mode: str, max_chars: int, min_chars: int, threshold: float) -> list[Section]:
    if _native_segmentation_ready("segment_turns"):
        result = _NATIVE.segment_turns(turns, mode, max_chars, min_chars, threshold, _NATIVE_SEGMENTATION_GLOBALS)
        if result is not NotImplemented:
            return result
    if mode not in {"adaptive", "turn", "session"}:
        raise ValueError("segmentation must be adaptive, turn, or session")
    if not turns:
        raise ValueError("session needs at least one user, assistant, or tool message")
    groups: list[list[Turn]] = []
    if mode == "session":
        groups = [turns]
    elif mode == "turn":
        groups = [[turn] for turn in turns]
    else:
        current: list[Turn] = []
        size = 0
        for turn in turns:
            related = not current or similarity(current[-1].question, turn.question) >= threshold or is_followup(turn.question)
            can_fit = size + len(turn.content) + 2 <= max_chars
            # Tiny adjacent notes may share a section until the minimum size;
            # beyond that, a topic change starts a new section. This is an
            # explicit heuristic, evaluated against turn/session baselines.
            if current and (not can_fit or (not related and size >= min_chars) or len(current) >= 4):
                groups.append(current)
                current, size = [], 0
            current.append(turn)
            size += len(turn.content) + 2
        if current:
            groups.append(current)
    return [Section(headline(g[0].question), " · ".join(headline(t.question, 96) for t in g)[:360], _pages(g, max_chars if mode == "adaptive" else None)) for g in groups]


# Keep the reference bodies above available to custom classes, patched helpers
# and unusual direct inputs.  Certificate checks are scoped to each function's
# actual dependencies; cuts only needs its exact string/positive-int contract.
_NATIVE_SEGMENTATION_GLOBALS = globals()
_NATIVE_SEGMENTATION_DEFAULTS = {
    name: _NATIVE_SEGMENTATION_GLOBALS[name]
    for name in ("Turn", "Page", "Section", "headline", "similarity", "is_followup", "_joined", "_cuts", "_pages")
}
_NATIVE_SEGMENTATION_FIELDS = {
    "Turn": ("index", "question", "content", "message_indices"),
    "Page": ("title", "question", "content", "refs"),
    "Section": ("title", "summary", "pages"),
}
_NATIVE_SEGMENTATION_CLASS_STATES = {
    name: (cls, cls.__new__, cls.__init__, cls.__getattribute__,
           tuple((field, cls.__dict__.get(field)) for field in _NATIVE_SEGMENTATION_FIELDS[name]))
    for name, cls in (("Turn", Turn), ("Page", Page), ("Section", Section))
}
_NATIVE_SEGMENTATION_CERTIFIED = (
    all(getattr(function, "__module__", None) == "memory_book.text"
        and getattr(function, "__name__", None) == name
        and getattr(function, "__globals__", None) is _text_module.__dict__
        and getattr(getattr(function, "__code__", None), "co_name", None) == name
        for name, function in (("headline", headline), ("similarity", similarity), ("is_followup", is_followup)))
    and all(type(cls) is type and cls.__mro__ == (cls, object)
            and getattr(cls.__init__, "__module__", None) == __name__
            for cls in (Turn, Page, Section))
)
_NATIVE_SEGMENTATION_DEPENDENCIES = {
    "make_turns": (("Turn",), ()),
    "joined_turns": (("Turn",), ()),
    "build_pages": (("Turn", "Page"), ("_joined", "_cuts", "headline")),
    "segment_turns": (("Turn", "Section"), ("_pages", "headline", "similarity", "is_followup")),
}


def _native_segmentation_ready(name: str) -> bool:
    if _NATIVE is None or not _NATIVE_SEGMENTATION_CERTIFIED:
        return False
    classes, functions = _NATIVE_SEGMENTATION_DEPENDENCIES[name]
    for function in functions:
        if _NATIVE_SEGMENTATION_GLOBALS.get(function) is not _NATIVE_SEGMENTATION_DEFAULTS[function]:
            return False
    for name in classes:
        cls, new, init, getattribute, fields = _NATIVE_SEGMENTATION_CLASS_STATES[name]
        if (_NATIVE_SEGMENTATION_GLOBALS.get(name) is not cls
                or cls.__new__ is not new or cls.__init__ is not init or cls.__getattribute__ is not getattribute
                or any(cls.__dict__.get(field) is not value for field, value in fields)):
            return False
    return True
