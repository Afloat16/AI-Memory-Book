"""Shared lexical analysis, conservative size accounting, and extractive excerpts.

FTS receives pre-tokenized text. CJK bigrams make Chinese searchable without an
external segmenter; they are lexical features, not semantic embeddings.
"""

from __future__ import annotations

import math
import re
import sys
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from itertools import islice

from ._text_backend import NATIVE as _NATIVE

CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
RUNS = re.compile(rf"[{CJK}]+|[^\W_{CJK}]+(?:[_./:-][^\W_{CJK}]+)*", re.UNICODE)
ASCII_RUNS = re.compile(r"[a-z0-9]+")
CJK_RUN = re.compile(rf"^[{CJK}]+$")
CJK_CHARACTER = re.compile(rf"[{CJK}]")
CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")
IDENTIFIER_SEPARATOR = re.compile(r"[_./:-]+")
IDENTIFIER_RUN = re.compile(r"[A-Za-z0-9_]+")
IDENTIFIER_WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
ZH_QUESTION = re.compile(r"为什么|请告诉我|请问|是什么|什么|怎么样|怎么|如何|多少|哪些|哪个|是否")
STOP = frozenset("a an the is are was were be been to of in on at for from and or it this that these those with as by what which who when where why how do does did can could would should please tell me we our you your i my about now current latest final s t re ve ll d m".split())
ZH_STOP = frozenset("什么 怎么 如何 为什么 哪个 哪些 是否 现在 当前 最后 最终 我们 这个 那个 一个 一下 请问 告诉 多少 了吗 的是 是什 么的 如何 何时 怎样".split())

# Keep Python's dynamic dependencies observable. Customized inputs and patched
# helpers use the unchanged reference body below, including its error behavior.
_NATIVE_CAMEL_BOUNDARY = CAMEL_BOUNDARY
_NATIVE_ASCII_RUNS = ASCII_RUNS
_NATIVE_STOP = STOP
_NATIVE_ZH_STOP = ZH_STOP
_NATIVE_RUNS = RUNS
_NATIVE_CJK_RUN = CJK_RUN
_NATIVE_IDENTIFIER_SEPARATOR = IDENTIFIER_SEPARATOR
_NATIVE_IDENTIFIER_RUN = IDENTIFIER_RUN
_NATIVE_IDENTIFIER_WORD_BOUNDARY = IDENTIFIER_WORD_BOUNDARY
_NATIVE_NORMALIZE = unicodedata.normalize
_NATIVE_CATEGORY = unicodedata.category
_NATIVE_FINDITER = re.finditer
_NATIVE_ESCAPE = re.escape
_NATIVE_ISLICE = islice
_NATIVE_LOG1P = math.log1p
_NATIVE_FSUM = math.fsum
_NATIVE_BISECT_LEFT = bisect_left
_NATIVE_BISECT_RIGHT = bisect_right
_NATIVE_COUNTER = Counter
_NATIVE_COUNTER_METHOD_NAMES = ("__new__", "__init__", "update", "__missing__", "__getitem__",
                                "__setitem__", "__delitem__", "__len__", "values")
_NATIVE_COUNTER_METHODS = tuple(getattr(Counter, name, None) for name in _NATIVE_COUNTER_METHOD_NAMES)
_NATIVE_C_EVIDENCE_UNITS = getattr(_NATIVE, "evidence_units", None)
_NATIVE_C_LITERAL_POSITIONS = getattr(_NATIVE, "literal_positions", None)
_NATIVE_ASCII_CERTIFIED = (
    type(CAMEL_BOUNDARY) is re.Pattern and CAMEL_BOUNDARY.pattern == r"([a-z])([A-Z])"
    and CAMEL_BOUNDARY.flags == re.UNICODE
    and type(ASCII_RUNS) is re.Pattern and ASCII_RUNS.pattern == r"[a-z0-9]+"
    and ASCII_RUNS.flags == re.UNICODE
)
_NATIVE_FINDITER_CERTIFIED = (
    getattr(re.finditer, "__module__", None) == "re"
    and getattr(re.finditer, "__name__", None) == "finditer"
    and getattr(re.finditer, "__globals__", None) is re.__dict__
    and getattr(getattr(re.finditer, "__code__", None), "co_name", None) == "finditer"
)
_NATIVE_LITERAL_CERTIFIED = (
    _NATIVE_FINDITER_CERTIFIED
    and getattr(re.escape, "__module__", None) == "re"
    and getattr(re.escape, "__name__", None) == "escape"
    and getattr(re.escape, "__globals__", None) is re.__dict__
    and getattr(getattr(re.escape, "__code__", None), "co_name", None) == "escape"
    and type(islice) is type and islice.__module__ == "itertools" and islice.__name__ == "islice"
)
_NATIVE_IDENTIFIER_CERTIFIED = (
    type(IDENTIFIER_RUN) is re.Pattern and IDENTIFIER_RUN.pattern == r"[A-Za-z0-9_]+"
    and IDENTIFIER_RUN.flags == re.UNICODE
    and type(IDENTIFIER_WORD_BOUNDARY) is re.Pattern
    and IDENTIFIER_WORD_BOUNDARY.pattern == r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
    and IDENTIFIER_WORD_BOUNDARY.flags == re.UNICODE
)
_NATIVE_UNICODE_REGEX_CERTIFIED = (
    type(RUNS) is re.Pattern
    and RUNS.pattern == rf"[{CJK}]+|[^\W_{CJK}]+(?:[_./:-][^\W_{CJK}]+)*"
    and RUNS.flags == re.UNICODE
    and type(CJK_RUN) is re.Pattern and CJK_RUN.pattern == rf"^[{CJK}]+$"
    and CJK_RUN.flags == re.UNICODE
    and type(IDENTIFIER_SEPARATOR) is re.Pattern and IDENTIFIER_SEPARATOR.pattern == r"[_./:-]+"
    and IDENTIFIER_SEPARATOR.flags == re.UNICODE
)
_NATIVE_FOLD_CERTIFIED = (
    type(unicodedata.normalize) is type(len)
    and getattr(unicodedata.normalize, "__module__", None) == "unicodedata"
    and getattr(unicodedata.normalize, "__name__", None) == "normalize"
    and type(unicodedata.category) is type(len)
    and getattr(unicodedata.category, "__module__", None) == "unicodedata"
    and getattr(unicodedata.category, "__name__", None) == "category"
)
_NATIVE_WINDOW_CERTIFIED = (
    all(type(function) is type(len) and getattr(function, "__module__", None) == module
        and getattr(function, "__name__", None) == name
        for function, module, name in (
            (math.log1p, "math", "log1p"), (math.fsum, "math", "fsum"),
            (bisect_left, "_bisect", "bisect_left"), (bisect_right, "_bisect", "bisect_right")))
    and all(type(function) is type(len)
            and getattr(function, "__module__", None) in {"_native", "memory_book._native"}
            and getattr(function, "__name__", None) == name
            and getattr(function, "__self__", None) is _NATIVE
            for function, name in ((_NATIVE_C_EVIDENCE_UNITS, "evidence_units"),
                                   (_NATIVE_C_LITERAL_POSITIONS, "literal_positions")))
    and type(Counter) is type and Counter.__module__ == "collections" and Counter.__name__ == "Counter"
    and Counter.__mro__ == (Counter, dict, object)
    and all(getattr(getattr(Counter, name, None), "__module__", None) == "collections"
            and getattr(getattr(Counter, name, None), "__name__", None) == name
            for name in ("__init__", "update", "__missing__", "__delitem__"))
    and all(getattr(Counter, name, None) is getattr(dict, name)
            for name in ("__new__", "__getitem__", "__setitem__", "__len__", "values"))
)


def _strip_nonspacing_marks(text: str) -> str:
    """Remove category Mn without changing the caller's normalization order."""
    if (_NATIVE is not None and _NATIVE_FOLD_CERTIFIED and type(text) is str
            and unicodedata.category is _NATIVE_CATEGORY):
        return _NATIVE.strip_nonspacing_marks(text, unicodedata.category)
    removed = {ord(c): None for c in set(text) if unicodedata.category(c) == "Mn"}
    return text.translate(removed) if removed else text


def terms(text: str, *, query: bool = False) -> list[str]:
    """NFKC text -> English words/identifier pieces and Chinese bigrams."""
    if (_NATIVE is not None and _NATIVE_ASCII_CERTIFIED and type(text) is str and type(query) is bool
            and text.isascii() and CAMEL_BOUNDARY is _NATIVE_CAMEL_BOUNDARY
            and ASCII_RUNS is _NATIVE_ASCII_RUNS and STOP is _NATIVE_STOP):
        return _NATIVE.terms_ascii(text, query, STOP)
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
        if (_NATIVE is not None and _NATIVE_ASCII_CERTIFIED and type(text) is str and type(query) is bool
                and ASCII_RUNS is _NATIVE_ASCII_RUNS and STOP is _NATIVE_STOP):
            return _NATIVE.ascii_tokens(text, query, STOP)
        parts = ASCII_RUNS.findall(text)
        return [part for part in parts if part not in STOP] if query else parts
    if query:
        # Remove complete Chinese question phrases before bigramming; otherwise
        # 为什么 leaves the meaningless fragment 为什 as a retrieval feature.
        text = ZH_QUESTION.sub(" ", text)
    if (_NATIVE is not None and _NATIVE_UNICODE_REGEX_CERTIFIED
            and type(text) is str and type(query) is bool
            and RUNS is _NATIVE_RUNS and CJK_RUN is _NATIVE_CJK_RUN
            and IDENTIFIER_SEPARATOR is _NATIVE_IDENTIFIER_SEPARATOR
            and STOP is _NATIVE_STOP and ZH_STOP is _NATIVE_ZH_STOP):
        return _NATIVE.unicode_tokens(text, query, STOP, ZH_STOP)
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


_NATIVE_TERMS = terms


def _native_identifier_aliases_ready(text: str, normalized: str, query: bool) -> bool:
    return (_NATIVE is not None and _NATIVE_IDENTIFIER_CERTIFIED and _NATIVE_ASCII_CERTIFIED
            and type(text) is str and type(normalized) is str and type(query) is bool
            and IDENTIFIER_RUN is _NATIVE_IDENTIFIER_RUN
            and IDENTIFIER_WORD_BOUNDARY is _NATIVE_IDENTIFIER_WORD_BOUNDARY
            and CAMEL_BOUNDARY is _NATIVE_CAMEL_BOUNDARY
            and ASCII_RUNS is _NATIVE_ASCII_RUNS and STOP is _NATIVE_STOP
            and terms is _NATIVE_TERMS)


def identifier_terms(text: str, *, query: bool = False) -> list[str]:
    """Add code-spelling aliases without changing source or segmentation terms.

    HTTPParser, HttpParser and http_parser share component words and a compact
    spelling. Indexes keep every legacy token, including order and frequency,
    so exact-spelling queries do not lose existing matches. Queries use the
    canonical components: a legacy partial token such as ``xmlhttp`` must not
    make XMLHttpRequest and xml_http_request incomparable current subjects.
    Aliases never cross a qualified-name/path separator or a whitespace gap.
    This is deterministic lexical normalization, not translation or stemming.
    """
    normalized = text if text.isascii() else unicodedata.normalize("NFKC", text)
    if (_NATIVE is not None and _NATIVE_IDENTIFIER_CERTIFIED and type(normalized) is str
            and IDENTIFIER_WORD_BOUNDARY is _NATIVE_IDENTIFIER_WORD_BOUNDARY):
        has_boundary = _NATIVE.identifier_has_boundary(normalized)
    else:
        has_boundary = IDENTIFIER_WORD_BOUNDARY.search(normalized)
    if not has_boundary:
        return terms(normalized, query=query)
    if query:
        if _native_identifier_aliases_ready(text, normalized, query):
            prepared, aliases = _NATIVE.identifier_aliases(normalized, True, STOP)
            return terms(prepared, query=True) + aliases
        aliases = []

        def canonical(match: re.Match[str]) -> str:
            value = match.group()
            parts = [part.casefold() for part in IDENTIFIER_WORD_BOUNDARY.split(value) if part]
            if len(parts) < 2:
                return value
            joined = "".join(parts)
            if joined not in STOP:
                aliases.append(joined)
            return " ".join(parts)

        return terms(IDENTIFIER_RUN.sub(canonical, normalized), query=True) + aliases
    result = terms(normalized)
    # Whole-text terms() may call customized Unicode helpers.  Check the
    # per-identifier dependencies afterwards so any mutations remain visible.
    if _native_identifier_aliases_ready(text, normalized, query):
        _, aliases = _NATIVE.identifier_aliases(normalized, False, STOP)
        result.extend(aliases)
        return result
    for match in IDENTIFIER_RUN.finditer(normalized):
        value = match.group()
        parts = [part.casefold() for part in IDENTIFIER_WORD_BOUNDARY.split(value) if part]
        if len(parts) < 2:
            continue
        existing = set(terms(value))
        for alias in [*parts, "".join(parts)]:
            if alias not in existing:
                result.append(alias)
                existing.add(alias)
    return result


def index_text(text: str) -> str:
    return " ".join(identifier_terms(text))


def query_terms(text: str) -> list[str]:
    # Bound SQL expression complexity and preserve repeated-word neutrality.
    return list(dict.fromkeys(identifier_terms(text, query=True)))[:64]


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
    if (_NATIVE is not None and _NATIVE_FINDITER_CERTIFIED and type(text) is str and type(width) is int
            and -sys.maxsize - 1 <= width <= sys.maxsize
            and re.finditer is _NATIVE_FINDITER):
        return _NATIVE.evidence_units(text, width)
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
    if (_NATIVE is not None and _NATIVE_FOLD_CERTIFIED and type(text) is str
            and unicodedata.normalize is _NATIVE_NORMALIZE
            and unicodedata.category is _NATIVE_CATEGORY):
        return _NATIVE.fold_excerpt_source(text, unicodedata.normalize, unicodedata.category)
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


_NATIVE_EVIDENCE_UNITS = _evidence_units


def _native_excerpt_window_ready() -> bool:
    return (_NATIVE is not None and _NATIVE_WINDOW_CERTIFIED and _NATIVE_FINDITER_CERTIFIED
            and _evidence_units is _NATIVE_EVIDENCE_UNITS
            and _NATIVE.evidence_units is _NATIVE_C_EVIDENCE_UNITS
            and _NATIVE.literal_positions is _NATIVE_C_LITERAL_POSITIONS
            and re.finditer is _NATIVE_FINDITER
            and math.log1p is _NATIVE_LOG1P and math.fsum is _NATIVE_FSUM
            and bisect_left is _NATIVE_BISECT_LEFT and bisect_right is _NATIVE_BISECT_RIGHT
            and Counter is _NATIVE_COUNTER
            and all(getattr(Counter, name, None) is method
                    for name, method in zip(_NATIVE_COUNTER_METHOD_NAMES, _NATIVE_COUNTER_METHODS)))


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
    if (_NATIVE is not None and _NATIVE_LITERAL_CERTIFIED
            and type(lower) is str and type(q) is list and all(type(term) is str for term in q)
            and (source_positions is None or type(source_positions) is list)
            and re.finditer is _NATIVE_FINDITER and re.escape is _NATIVE_ESCAPE
            and islice is _NATIVE_ISLICE):
        positions = _NATIVE.literal_positions(lower, q, source_positions)
    else:
        for term in q:
            for match in islice(re.finditer(re.escape(term), lower), 40):
                positions.append((match.start() if source_positions is None else source_positions[match.start()], term))
    if _native_excerpt_window_ready():
        native_window = _NATIVE.excerpt_window(text, q, positions, width, _evidence_units, math.log1p, math.fsum)
        if native_window is not NotImplemented:
            return native_window
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
