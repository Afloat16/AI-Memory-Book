"""Private exact intersections without constructing irrelevant lexical features.

The public lexical implementation remains the reference. A cached ordinary
entry represents its complete query=True feature set at first use, not the
answer for one query. Custom query members can still request that original set.
"""
from __future__ import annotations

from types import ModuleType

from . import text as _lexical

_TERMS = _lexical.terms
_TERMS_CODE = _TERMS.__code__
_UNICODE = _lexical.unicodedata
_NORMALIZE = _UNICODE.normalize
_CATEGORY = _UNICODE.category
_STRIP = _lexical._strip_nonspacing_marks
_STRIP_CODE = _STRIP.__code__
_ASCII_RUNS = _lexical.ASCII_RUNS
_RUNS = _lexical.RUNS
_CJK_RUN = _lexical.CJK_RUN
_CAMEL = _lexical.CAMEL_BOUNDARY
_SEPARATOR = _lexical.IDENTIFIER_SEPARATOR
_QUESTION = _lexical.ZH_QUESTION
_STOP, _ZH_STOP = _lexical.STOP, _lexical.ZH_STOP
_GLOBALS = (("ASCII_RUNS", _ASCII_RUNS), ("RUNS", _RUNS), ("CJK_RUN", _CJK_RUN),
            ("CAMEL_BOUNDARY", _CAMEL), ("IDENTIFIER_SEPARATOR", _SEPARATOR),
            ("ZH_QUESTION", _QUESTION), ("STOP", _STOP), ("ZH_STOP", _ZH_STOP),
            ("_strip_nonspacing_marks", _STRIP), ("unicodedata", _UNICODE))


def _ordinary(function) -> bool:
    # An unchanged function alias can still observe replaced module globals.
    # Only identity reads of ordinary dictionaries precede the original fallback.
    if (function is not _TERMS or _TERMS.__code__ is not _TERMS_CODE or
            _STRIP.__code__ is not _STRIP_CODE or type(_lexical) is not ModuleType or
            type(_UNICODE) is not ModuleType):
        return False
    namespace = vars(_lexical)
    return (all(namespace.get(name) is value for name, value in _GLOBALS) and
            all(name not in namespace for name in ("len", "range", "set", "ord")) and
            vars(_UNICODE).get("normalize") is _NORMALIZE and
            vars(_UNICODE).get("category") is _CATEGORY)


class _Entry:
    """One full logical feature set, with at most one query-specific count."""
    __slots__ = ("_text", "_ascii", "_features", "_query", "_count")

    def __init__(self, text: str):
        if not text.isascii():
            text = _NORMALIZE("NFKC", text)
        text = _CAMEL.sub(r"\1 \2", text).casefold()
        if not text.isascii():
            text = _STRIP(_NORMALIZE("NFKD", text))
        self._ascii = text.isascii()
        self._text = text if self._ascii else _QUESTION.sub(" ", text)
        self._features = None
        self._query = None
        self._count = 0

    def full_set(self) -> set[str]:
        if self._features is None:
            # Reproduce the original feature order before set construction.
            # Do not normalize again or consult subsequently replaced globals.
            if self._ascii:
                result = [part for part in _ASCII_RUNS.findall(self._text) if part not in _STOP]
            else:
                result = []
                for match in _RUNS.finditer(self._text):
                    value = match.group()
                    if _CJK_RUN.fullmatch(value):
                        parts = [value] if len(value) == 1 else [value[i:i + 2] for i in range(len(value) - 1)]
                        result.extend(part for part in parts if part not in _ZH_STOP)
                    else:
                        parts = _SEPARATOR.split(value)
                        result.extend(part for part in parts if part and part not in _STOP)
            self._features = set(result)
        return self._features

    def count(self, wanted: set[str]) -> int:
        if type(wanted) is not set or any(type(term) is not str for term in wanted):
            return len(wanted.intersection(self.full_set()))
        if self._query is not None and wanted == self._query:
            return self._count
        needed = wanted.difference(_STOP, _ZH_STOP)
        if self._ascii:
            found = needed.intersection(_ASCII_RUNS.findall(self._text))
        else:
            singles, bigrams, words = set(), set(), set()
            for term in needed:
                if _CJK_RUN.fullmatch(term):
                    if len(term) == 1:
                        singles.add(term)
                    elif len(term) == 2:
                        bigrams.add(term)
                elif term:
                    words.add(term)
            found = set()
            possible = len(singles) + len(bigrams) + len(words)
            if possible:
                for match in _RUNS.finditer(self._text):
                    value = match.group()
                    if _CJK_RUN.fullmatch(value):
                        if len(value) == 1:
                            if value in singles:
                                found.add(value)
                        else:
                            # Within one certified CJK run, substring membership
                            # of a two-character term is exactly bigram membership.
                            for term in bigrams:
                                if term not in found and term in value:
                                    found.add(term)
                    elif words:
                        found.update(words.intersection(_SEPARATOR.split(value)))
                    if len(found) == possible:
                        break
        self._query, self._count = frozenset(wanted), len(found)
        return self._count


def overlap_entry(text, function):
    if type(text) is str and _ordinary(function):
        return _Entry(text)
    return set(function(text, query=True))


def cached_overlap(wanted, entry) -> int:
    if type(entry) is _Entry:
        return entry.count(wanted)
    return len(wanted.intersection(entry))


def query_overlap(wanted, text, function) -> int:
    entry = overlap_entry(text, function)
    if type(entry) is _Entry:
        if type(wanted) is set and all(type(term) is str for term in wanted):
            return entry.count(wanted)
        entry = entry.full_set()
    # Keep this consumer's original operand direction on every custom path.
    return len(wanted & entry)
