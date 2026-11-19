"""Bounded lexical coverage of explicitly named identifiers in returned evidence.

This is not an answerability classifier. An identifier mention is not a value,
an approval, or a complete answer; a missing spelling is not archive absence.
The check reads only the final source excerpts, never titles or navigation text.
"""

from __future__ import annotations

import re

from .text import IDENTIFIER_WORD_BOUNDARY


_NAME = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_NAMES = re.compile(r"(?<![A-Za-z0-9_])" + _NAME + r"(?![A-Za-z0-9_])")
_INLINE_NAME = re.compile(r"(?<!`)`(" + _NAME + r")`(?!`)")
_ADDRESS = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+|[^\s@]+@[^\s@]+\.[^\s@]+")
_CAMEL = re.compile(r"[a-z][A-Z]|[A-Z][A-Z][a-z]")
_ALTERNATIVE = re.compile(r"\b(?:or|except|without|rather\s+than|instead\s+of|not)\b|或|而非|不是|排除|不要", re.I)
_MAX_IDENTIFIERS = 32
_MAX_PARTS = 32


def _identity(name: str) -> tuple[tuple[str, ...], ...]:
    # Keep namespace and whole-word boundaries. Do not equate user.id with
    # user_id, a_bc with ab_c, or a field with a substring of a larger name.
    segments = []
    for segment in name.split("."):
        leading = len(segment) - len(segment.lstrip("_"))
        trailing = len(segment) - len(segment.rstrip("_"))
        words = tuple(part.casefold() for part in IDENTIFIER_WORD_BOUNDARY.split(segment) if part)
        segments.append((("_" * leading,) if leading else ()) + words
                        + (("_" * trailing,) if trailing else ()))
    return tuple(segments)


def _requested(query: str) -> list[tuple[str, tuple]]:
    quoted = {match.span(1) for match in _INLINE_NAME.finditer(query)}
    addresses = [match.span() for match in _ADDRESS.finditer(query)]
    result, seen = [], set()
    for match in _NAMES.finditer(query):
        name = match.group()
        if any(lo <= match.start() < hi for lo, hi in addresses):
            continue
        if not ("_" in name or "." in name or _CAMEL.search(name) or match.span() in quoted):
            continue
        identity = _identity(name)
        if identity not in seen and all(identity):
            seen.add(identity)
            result.append((name, identity))
    return result


def _mentions(text: str, wanted: set[tuple]) -> set[tuple]:
    """Recognize whole code names and adjacent prose words, preserving dots."""
    found = set()
    plain = {identity[0] for identity in wanted if len(identity) == 1}
    maximum = max(map(len, plain), default=0)
    run, previous_end = [], 0
    for match in _NAMES.finditer(text):
        identity = _identity(match.group())
        if identity in wanted:
            found.add(identity)
        if not maximum or len(identity) != 1:
            run = []
            previous_end = match.end()
            continue
        gap = text[previous_end:match.start()]
        if not gap or not gap.isspace():
            run = []
        run.append(identity[0])
        # Each entry is one whole source token. Never match only the final
        # words of a larger code name such as max_retry_limit.
        run = run[-maximum:]
        words = ()
        for parts in reversed(run):
            words = parts + words
            if len(words) > maximum:
                break
            if words in plain:
                found.add((words,))
        previous_end = match.end()
    return found


def assess_identifier_coverage(query: str, results: list[dict]) -> dict | None:
    """Describe literal identifier coverage without dropping any evidence.

    Unmarked ordinary prose, URLs and numeric dates are outside this narrow
    check. Explicit alternatives are not treated as an obligation to cover
    every name. Case folding and snake/camel/prose aliases are lexical aids,
    not an assertion that case-sensitive program symbols are interchangeable.
    """
    requested = _requested(query)
    if not requested:
        return None
    base = {"scope": "returned_excerpts", "requested_identifiers": [name for name, _ in requested]}
    if (len(requested) > _MAX_IDENTIFIERS
            or any(sum(map(len, identity)) > _MAX_PARTS for _, identity in requested)
            or _ALTERNATIVE.search(query)):
        return {**base, "status": "not_assessed", "missing_identifiers": [],
                "basis": "Identifier coverage was not inferred for alternatives, exclusions, or requests exceeding the bounded syntax limits."}
    wanted = {identity for _, identity in requested}
    found = set()
    for result in results:
        found.update(_mentions(result["text"], wanted - found))
        if found == wanted:
            break
    missing = [name for name, identity in requested if identity not in found]
    return {**base, "status": "insufficient_evidence" if missing else "identifier_mentions_present",
            "missing_identifiers": missing,
            "basis": "Only whole identifier mentions in returned source excerpts were checked, with case-folded snake/camel/prose aliases and preserved namespaces. Missing mentions do not prove archive absence; present mentions do not establish a value, authority, semantic answer, or completeness."}
