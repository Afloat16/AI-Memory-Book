"""Shared lexical analysis, conservative size accounting, and extractive excerpts.

FTS receives pre-tokenized text. CJK bigrams make Chinese searchable without an
external segmenter; they are lexical features, not semantic embeddings.
"""

from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from itertools import islice

CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
RUNS = re.compile(rf"[{CJK}]+|[^\W_{CJK}]+(?:[_./:-][^\W_{CJK}]+)*", re.UNICODE)
ASCII_RUNS = re.compile(r"[a-z0-9]+")
CJK_RUN = re.compile(rf"^[{CJK}]+$")
CJK_CHARACTER = re.compile(rf"[{CJK}]")
CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")
IDENTIFIER_SEPARATOR = re.compile(r"[_./:-]+")
ZH_QUESTION = re.compile(r"为什么|请告诉我|请问|是什么|什么|怎么样|怎么|如何|多少|哪些|哪个|是否")
STOP = frozenset("a an the is are was were be been to of in on at for from and or it this that these those with as by what which who when where why how do does did can could would should please tell me we our you your i my about now current latest final s t re ve ll d m".split())
ZH_STOP = frozenset("什么 怎么 如何 为什么 哪个 哪些 是否 现在 当前 最后 最终 我们 这个 那个 一个 一下 请问 告诉 多少 了吗 的是 是什 么的 如何 何时 怎样".split())


def _strip_nonspacing_marks(text: str) -> str:
    """Remove category Mn without changing the caller's normalization order."""
    removed = {ord(c): None for c in set(text) if unicodedata.category(c) == "Mn"}
    return text.translate(removed) if removed else text


def terms(text: str, *, query: bool = False) -> list[str]:
    """NFKC text -> English words/identifier pieces and Chinese bigrams."""
    if not text.isascii():
        text = unicodedata.normalize("NFKC", text)
    text = CAMEL_BOUNDARY.sub(r"\1 \2", text).casefold()
    if not text.isascii():
        # Normalize the whole string first: canonical ordering can cross
        # character boundaries. Only the category lookup/deletion is reused.
        text = _strip_nonspacing_marks(unicodedata.normalize("NFKD", text))
    if text.isascii():
        # After case folding, the Unicode/identifier rule reduces exactly to
        # lowercase ASCII alphanumeric runs; its separators never add tokens.
        parts = ASCII_RUNS.findall(text)
        return [part for part in parts if part not in STOP] if query else parts
    if query:
        # Remove complete Chinese question phrases before bigramming; otherwise
        # 为什么 leaves the meaningless fragment 为什 as a retrieval feature.
        text = ZH_QUESTION.sub(" ", text)
    result: list[str] = []
    for match in RUNS.finditer(text):
        value = match.group()
        if CJK_RUN.fullmatch(value):
            parts = [value] if len(value) == 1 else [value[i:i + 2] for i in range(len(value) - 1)]
            result.extend(p for p in parts if not query or p not in ZH_STOP)
        else:
            parts = IDENTIFIER_SEPARATOR.split(value)
            # Indexed identifiers share the same split with queries; FTS syntax is
            # never passed through, even for user input containing quotes or OR.
            result.extend(p for p in parts if p and (not query or p not in STOP))
    return result


def index_text(text: str) -> str:
    return " ".join(terms(text))


def query_terms(text: str) -> list[str]:
    # Bound SQL expression complexity and preserve repeated-word neutrality.
    return list(dict.fromkeys(terms(text, query=True)))[:64]


def estimate_tokens(text: str) -> int:
    """Size heuristic only. Never presented as a model tokenizer's exact count."""
    cjk = len(CJK_CHARACTER.findall(text))
    return cjk + math.ceil((len(text) - cjk) / 4)


def headline(text: str, limit: int = 88) -> str:
    clean = " ".join(text.split())
    return clean[:limit].rstrip() + ("…" if len(clean) > limit else "")


def similarity(left: str, right: str) -> float:
    a, b = set(terms(left, query=True)), set(terms(right, query=True))
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


def is_followup(question: str) -> bool:
    q = question.strip().casefold()
    return bool(re.match(r"^(那|它|这个|这项|该|继续|还有|为什么|那么|是否|可以|再|and\b|what about\b|why\b|how about\b|then\b|that\b|it\b|can we\b)", q))


def _evidence_units(text: str, width: int) -> list[tuple[int, int]]:
    """Prefer intact source lines, falling back to sentences inside long lines.

    These are only excerpt boundaries, never synthesized or rewritten facts.
    A short speaker-labelled line can contain a qualification in a different
    sentence, so keep the whole line when it fits the available window.
    """
    units = []
    for line in re.finditer(r"[^\n]+", text):
        lo, hi = line.span()
        if hi - lo <= width:
            units.append((lo, hi))
            continue
        start = lo
        for boundary in re.finditer(r"[。！？]|[.!?](?=\s|$)", line.group()):
            end = lo + boundary.end()
            if end - start <= width:
                units.append((start, end))
            start = end
            while start < hi and text[start].isspace():
                start += 1
        if start < hi and hi - start <= width:
            units.append((start, hi))
    return units


def _fold_excerpt_source(text: str) -> tuple[str, list[int]]:
    """Reuse the existing per-character fold while retaining exact offsets.

    This is intentionally the historical source-map transform, not whole-text
    NFKD. The local cache retains no text between excerpts or recall calls.
    """
    folded, positions = [], []
    character_folds: dict[str, tuple[str, int]] = {}
    for index, character in enumerate(text):
        entry = character_folds.get(character)
        if entry is None:
            piece = "".join(c for c in unicodedata.normalize("NFKD", character).casefold()
                            if unicodedata.category(c) != "Mn")
            entry = (piece, len(piece))
            character_folds[character] = entry
        piece, size = entry
        folded.append(piece)
        if size == 1:
            positions.append(index)
        elif size:
            positions.extend([index] * size)
    return "".join(folded), positions


def excerpt(text: str, query: str, max_chars: int, *, prepared_terms: list[str] | None = None) -> tuple[str, list[tuple[int, int]]]:
    """Return one bounded original-text window and exact character offsets.

    Every segmentation baseline uses the same function. Whole-session baselines
    therefore get relevance-centered windows, not a deliberately weak prefix.
    """
    if max_chars <= 0:
        return "", []
    if len(text) <= max_chars:
        return text, [(0, len(text))]
    if max_chars < 8:
        return text[:max_chars], [(0, max_chars)]
    width = max_chars - 2  # reserve potential leading and trailing ellipses
    q = query_terms(query) if prepared_terms is None else prepared_terms
    # Keep a source map through accent folding and expansions such as ß -> ss.
    lower = text.casefold()
    # ASCII and the common CJK/Latin case need no per-character source map.
    # Only use identity offsets when normalization leaves the folded string
    # unchanged, case folding preserves length, and no removable mark exists.
    identity_offsets = (len(lower) == len(text) and
                        (text.isascii() or
                         (unicodedata.normalize("NFKD", text).casefold() == lower and
                          not any(unicodedata.category(c) == "Mn" for c in set(lower)))))
    source_positions = None
    if not identity_offsets:
        lower, source_positions = _fold_excerpt_source(text)
    positions: list[tuple[int, str]] = []
    for term in q:
        for match in islice(re.finditer(re.escape(term), lower), 40):
            positions.append((match.start() if source_positions is None else source_positions[match.start()], term))
    positions.sort()
    starts = {0, max(0, len(text) - width)}
    for pos, _ in positions:
        starts.add(max(0, min(len(text) - width, pos - width // 3)))
    # A keyword-centred window can cut off the start of a complete utterance
    # even when that utterance fits. Add source-boundary alternatives and use
    # complete-unit coverage to break equal-coverage ties before placement.
    units = _evidence_units(text, width) if positions else []
    unit_starts = [lo for lo, _ in units]
    masks = {}
    term_bits = {term: 1 << i for i, term in enumerate(dict.fromkeys(q))}
    for pos, term in positions:
        index = bisect_right(unit_starts, pos) - 1
        if index >= 0 and pos < units[index][1]:
            masks[index] = masks.get(index, 0) | term_bits[term]
    matched_units = [(units[i][0], units[i][1], mask) for i, mask in sorted(masks.items())]
    for lo, hi, _ in matched_units:
        starts.add(min(lo, len(text) - width))
        starts.add(max(0, hi - width))
    unit_starts = [lo for lo, _, _ in matched_units]
    unit_ends = [hi for _, hi, _ in matched_units]
    best_start, best_score = 0, (-1, -1, -1.0, -1.0, -1)
    left = right = position_sum = 0
    inside: Counter[str] = Counter()
    for start in sorted(starts):
        # Candidate starts increase monotonically. Maintain the matching
        # window instead of rescanning every occurrence for every start.
        while right < len(positions) and positions[right][0] < start + width:
            pos, term = positions[right]
            inside[term] += 1
            position_sum += pos
            right += 1
        while left < right and positions[left][0] < start:
            pos, term = positions[left]
            inside[term] -= 1
            if not inside[term]:
                del inside[term]
            position_sum -= pos
            left += 1
        whole_terms = 0
        first_unit = bisect_left(unit_starts, start)
        last_unit = bisect_right(unit_ends, start + width)
        for index in range(first_unit, last_unit):
            whole_terms |= matched_units[index][2]
        # Equal keyword coverage must not prefer a window whose last few
        # characters merely begin the relevant sentence. Leave room after the
        # matched topic for its value, qualification, or following answer.
        count = right - left
        placement = abs((position_sum / count - start) / width - 1 / 3) if count else 1.0
        # Repetition cannot make an incomplete keyword-dense fragment beat
        # intact source evidence with the same distinct query-term coverage.
        # Frequency still breaks ties after coverage and source completeness.
        score = (len(inside), whole_terms.bit_count(),
                 math.fsum(math.log1p(n) for n in inside.values()), -placement, -start)
        if score > best_score:
            best_start, best_score = start, score
    end = min(len(text), best_start + width)
    return ("…" if best_start else "") + text[best_start:end] + ("…" if end < len(text) else ""), [(best_start, end)]
