"""Deterministic, source-preserving question grouping.

No generated summary replaces source text. Sections group adjacent related
questions; long individual turns are split into addressable continuation pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text import headline, is_followup, similarity


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
