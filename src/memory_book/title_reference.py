"""One opt-in, source-proven title hop inside an existing recall snapshot.

This module does not search for paraphrases or construct a persistent graph.
Only a unique complete session title, literally present in the lexical leader's
original text, can nominate one other source. All limits are the registered T1
limits, independent of the query, corpus, annotations, or observed outcomes.
"""

from __future__ import annotations

from collections import Counter
import json
import unicodedata

from .text import query_terms

VERSION = 1
CATALOG_LIMIT = 512
PREFIX_CHARS = 4096
TITLE_CHARS = 256


def normalize_title(text: str) -> str:
    """Retain punctuation and accents; only casefold and collapse whitespace."""
    return " ".join(text.casefold().split())


def _word_internal(character: str) -> bool:
    return character == "_" or unicodedata.category(character)[0] in "LNM"


def _normalization_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Map every normalized character to its complete original character/run.

    A casefold expansion has repeated spans. A collapsed whitespace separator
    covers the complete original run, so no match can silently discard part of
    a source character or splice nonadjacent original text.
    """
    parts, spans = [], []
    pending_space = None
    for position, character in enumerate(text):
        if character.isspace():
            if parts and pending_space is None:
                pending_space = position
            continue
        if pending_space is not None:
            parts.append(" ")
            spans.append((pending_space, position))
            pending_space = None
        folded = character.casefold()
        parts.extend(folded)
        spans.extend([(position, position + 1)] * len(folded))
    return "".join(parts), spans


def _eligible_title(title: str) -> bool:
    stripped = title.strip()
    nonspace = "".join(stripped.split())
    return (len(stripped) <= TITLE_CHARS and len(nonspace) >= 4 and
            not all(character.isnumeric() for character in nonspace) and
            len(query_terms(stripped)) >= 2)


def _mentions(prefix: str, titles: list[tuple[str, dict]]) -> list[tuple[int, int, dict]]:
    """Find whole titles while retaining the real adjacent source character.

    ``prefix`` contains up to PREFIX_CHARS + 1 original characters. The last
    extra character can reject a word cut at the search boundary, but cannot
    participate in a title match.
    """
    source = prefix[:PREFIX_CHARS]
    normalized = normalize_title(source)
    possible = []
    for title, session in titles:
        start = normalized.find(title)
        while start >= 0:
            possible.append((start, start + len(title), title, session))
            start = normalized.find(title, start + 1)
    if not possible:
        return []
    mapped, spans = _normalization_map(source)
    # Both paths implement exactly the same transform; do not guess offsets
    # if a future change makes their definitions disagree.
    if mapped != normalized:
        return []
    result = []
    for start, end, title, session in possible:
        if ((start and spans[start - 1] == spans[start]) or
                (end < len(spans) and spans[end - 1] == spans[end])):
            continue
        lo, hi = spans[start][0], spans[end - 1][1]
        if normalize_title(source[lo:hi]) != title:
            continue
        if lo and _word_internal(prefix[lo - 1]):
            continue
        if hi < len(prefix) and _word_internal(prefix[hi]):
            continue
        result.append((lo, hi, session))
    result.sort(key=lambda match: (match[0], -(match[1] - match[0]), match[2]["id"]))
    return result


def _source_projection(db, anchor: dict, lo: int, hi: int, *, project: str,
                       session_id: str) -> dict | None:
    """Prove one mention's original turn mapping without repairing cut edges."""
    refs = json.loads(anchor["source_refs"])
    if not isinstance(refs, list):
        return None
    covering = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        fields = ("start", "end", "turn_start", "turn_end", "turn_index")
        if any(type(ref.get(key)) is not int for key in fields):
            continue
        if not (0 <= ref["start"] <= lo < hi <= ref["end"] <= anchor["page_chars"]):
            continue
        if (ref["turn_start"] < 0 or ref["turn_index"] < 0 or
                ref["turn_end"] - ref["turn_start"] != ref["end"] - ref["start"] or
                ref.get("project") != project or ref.get("session_id") != session_id):
            continue
        covering.append(ref)
    if len(covering) != 1:
        return None
    ref = covering[0]
    # A page/turn separator says nothing about the character outside a slice.
    # Only an original start, or a neighbor within this same source mapping,
    # can prove the left boundary; never fetch neighboring text to rescue it.
    if lo == ref["start"] and ref["turn_start"] != 0:
        return None
    turn_lo = ref["turn_start"] + lo - ref["start"]
    turn_hi = turn_lo + hi - lo
    # Where the page claims an in-reference neighbor, verify that neighbor too.
    # A corrupted page must not turn an original letter/mark into a delimiter.
    # This adds at most two original characters and never rescues a cut edge.
    before = int(lo > ref["start"])
    after = int(hi < ref["end"])
    original = db.execute(
        "SELECT length(content) chars,substr(content,?,?) source_slice FROM turns "
        "WHERE session_pk=? AND ordinal=?",
        (turn_lo + 1 - before, hi - lo + before + after,
         anchor["session_pk"], ref["turn_index"])).fetchone()
    if original is None or ref["turn_end"] > original["chars"]:
        return None
    if hi == ref["end"] and turn_hi != original["chars"]:
        return None
    if original["source_slice"] != anchor["prefix"][lo - before:hi + after]:
        return None
    return {"page_span": [lo, hi], "turn_index": ref["turn_index"],
            "turn_span": [turn_lo, turn_hi]}


def follow_title_reference(db, candidates: list[dict], *, project: str,
                          chapter: str | None, session: str | None,
                          limit: int) -> tuple[list[dict], dict]:
    """Return the complete candidate order with at most one target inserted.

    The caller supplies the unchanged full lexical order after novelty. Every
    database read occurs in the caller's existing read transaction. A target
    without an eligible page terminates this one-hop attempt rather than
    trying another mention or broadening the scope.
    """
    state = {"version": VERSION, "active": False, "applied": False,
             "reason": "no_lexical_results"}
    if not candidates:
        return candidates, state
    state.update(active=True, reason="no_title_mention")
    clauses, params = ["project_id=?"], [project]
    if chapter is not None:
        clauses.append("chapter_id=?")
        params.append(chapter)
    if session is not None:
        clauses.append("external_id=?")
        params.append(session)
    catalog = db.execute(
        "SELECT id,external_id,title FROM sessions WHERE " + " AND ".join(clauses) +
        " ORDER BY id LIMIT 513", params).fetchall()
    if len(catalog) > CATALOG_LIMIT:
        state["reason"] = "catalog_overflow"
        return candidates, state
    # Ineligible titles still participate in collision counting. In particular,
    # a long whitespace spelling cannot make an otherwise ambiguous name unique.
    normalized = [(normalize_title(row["title"]), dict(row)) for row in catalog]
    multiplicity = Counter(title for title, _ in normalized)
    selected_sources = {row["session_id"] for row in candidates[:limit]}
    titles = [(title, row) for title, row in normalized
              if multiplicity[title] == 1 and _eligible_title(row["title"]) and
              row["external_id"] not in selected_sources]
    if not titles:
        state["reason"] = "no_unique_title"
        return candidates, state
    leader = candidates[0]
    anchor_row = db.execute(
        "SELECT session_pk,substr(content,1,4097) prefix,length(content) page_chars,source_refs "
        "FROM pages WHERE id=?", (leader["id"],)).fetchone()
    if anchor_row is None:
        state["reason"] = "anchor_unavailable"
        return candidates, state
    anchor = dict(anchor_row)
    chosen = None
    for lo, hi, target in _mentions(anchor["prefix"], titles):
        projection = _source_projection(db, anchor, lo, hi, project=project,
                                        session_id=leader["session_id"])
        if projection is not None:
            chosen = target, projection
            break
    if chosen is None:
        return candidates, state
    target, projection = chosen
    initial_page_ids = {row["id"] for row in candidates}
    initial_session_ids = {row["session_id"] for row in candidates}
    linked = next((row for row in candidates
                   if row["session_id"] == target["external_id"]), None)
    route = "lexical"
    if linked is None:
        target_clauses = ["p.session_pk=?", "p.project_id=?"]
        target_params = [target["id"], project]
        if chapter is not None:
            target_clauses.append("p.chapter_id=?")
            target_params.append(chapter)
        if session is not None:
            target_clauses.append("s.external_id=?")
            target_params.append(session)
        entry = db.execute(
            "SELECT p.id,p.rid,p.project_id,p.chapter_id,c.title chapter_title,"
            "s.external_id session_id,s.title session_title,s.created_at "
            "FROM pages p JOIN sections sec ON sec.id=p.section_id "
            "JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk "
            "WHERE " + " AND ".join(target_clauses) +
            " ORDER BY sec.ordinal,p.ordinal,p.id LIMIT 1", target_params).fetchone()
        if entry is None:
            state["reason"] = "no_target_page"
            return candidates, state
        linked = dict(entry)
        linked["score"] = 0.0
        route = "title_reference"
    state.update(applied=True, reason="applied",
                 anchor={"page_id": leader["id"], "session_id": leader["session_id"],
                         "session_pk": anchor["session_pk"]},
                 target={"page_id": linked["id"], "session_id": linked["session_id"],
                         "session_pk": target["id"], "route": route},
                 mention=projection,
                 target_initial_page_in_pool=linked["id"] in initial_page_ids,
                 target_initial_session_in_pool=linked["session_id"] in initial_session_ids)
    return ([leader, linked] + [row for row in candidates[1:]
                                if row["id"] != linked["id"]]), state
