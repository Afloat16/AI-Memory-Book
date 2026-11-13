"""One opt-in, source-backed title hop over a bounded lexical result pool.

This module is imported only by eligible title-following recalls. It neither
changes source/index data nor interprets a title mention as an endorsement.
"""

from __future__ import annotations

from collections import Counter
import json
import sqlite3
import unicodedata

from .text import query_terms


CATALOG_LIMIT = 512
ANCHOR_PREFIX_CHARACTERS = 4096
TITLE_MAX_CHARACTERS = 256


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _normalized_prefix(text: str) -> tuple[str, list[int], list[int]]:
    """Casefold/collapse whitespace while retaining original character spans."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for position, character in enumerate(text[:ANCHOR_PREFIX_CHARACTERS]):
        for folded in character.casefold():
            if folded.isspace():
                if not characters:
                    continue
                if characters[-1] == " ":
                    ends[-1] = position + 1
                    continue
                folded = " "
            characters.append(folded)
            starts.append(position)
            ends.append(position + 1)
    if characters and characters[-1] == " ":
        characters.pop()
        starts.pop()
        ends.pop()
    return "".join(characters), starts, ends


def _word_character(character: str) -> bool:
    return character == "_" or unicodedata.category(character)[0] in {"L", "N", "M"}


def _eligible_title(title: str) -> bool:
    stripped = title.strip()
    nonspace = [character for character in stripped if not character.isspace()]
    return (len(stripped) <= TITLE_MAX_CHARACTERS and len(nonspace) >= 4
            and not all(character.isnumeric() for character in nonspace)
            and len(set(query_terms(stripped))) >= 2)


def _mention_projection(anchor: dict, refs: list, start: int, end: int) -> dict | None:
    """Accept only one complete source projection with provable boundaries."""
    projections = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        values = [ref.get(key) for key in
                  ("start", "end", "turn_start", "turn_end", "turn_index")]
        if any(type(value) is not int for value in values):
            continue
        lo, hi, turn_lo, turn_hi, turn = values
        if (ref.get("project") != anchor["project_id"]
                or ref.get("session_id") != anchor["session_id"]
                or not 0 <= lo <= start < end <= hi <= len(anchor["content"])
                or not 0 <= turn_lo <= turn_hi or turn < 0
                or hi - lo != turn_hi - turn_lo):
            continue
        # An inserted join or a continuation-page cut is not a word boundary.
        # A source reference proves the original start only when turn_start=0;
        # it does not certify that its right edge is the original turn's EOF.
        if (start == lo and turn_lo != 0) or end == hi:
            continue
        projections.append({"page_start": start, "page_end": end,
                            "turn_index": turn,
                            "turn_start": turn_lo + start - lo,
                            "turn_end": turn_lo + end - lo})
    return projections[0] if len(projections) == 1 else None


def _find_reference(anchor: dict, catalog: list[dict], excluded_sessions: set[str]) -> tuple[dict, dict] | None:
    """Find the earliest unique complete title mention, without guessing aliases."""
    # Every scoped title participates in uniqueness before eligibility checks.
    normalized = [_normalize(row["title"]) for row in catalog]
    counts = Counter(normalized)
    text = anchor["content"]
    folded, starts, ends = _normalized_prefix(text)
    refs = json.loads(anchor["source_refs"])
    if not isinstance(refs, list):
        return None
    matches = []
    for row, title in zip(catalog, normalized):
        if (counts[title] != 1 or row["external_id"] in excluded_sessions
                or not _eligible_title(row["title"])):
            continue
        position = folded.find(title)
        while position >= 0:
            stop = position + len(title)
            start, end = starts[position], ends[stop - 1]
            # Do not start/end in the middle of one character's casefold.
            complete_fold = ((position == 0 or ends[position - 1] <= start)
                             and (stop == len(folded) or starts[stop] >= end))
            left = start == 0 or not _word_character(text[start - 1])
            right = end == len(text) or not _word_character(text[end])
            if (complete_fold and left and right
                    and _normalize(text[start:end]) == title):
                projection = _mention_projection(anchor, refs, start, end)
                if projection is not None:
                    matches.append(((start, -(end - start), row["id"]), row, projection))
                    break
            position = folded.find(title, position + 1)
    if not matches:
        return None
    _, target, projection = min(matches, key=lambda match: match[0])
    return target, projection


def follow_title_reference(db: sqlite3.Connection, candidates: list[dict], *,
                           project: str, chapter: str | None,
                           session: str | None, limit: int) -> tuple[list[dict], dict]:
    """Apply one hop under recall's existing read snapshot.

    The caller supplies the complete original candidate order after novelty
    selection, with its original top-limit page bodies already materialized.
    Only the target's pool membership is returned, never the full pool.
    """
    anchor = candidates[0]
    provenance = {"version": 1, "active": True, "applied": False,
                  "reason": "no_title_reference", "project": project,
                  "anchor_page_id": anchor["id"],
                  "anchor_session_id": anchor["session_id"],
                  "target_initial_page_in_pool": None,
                  "target_initial_session_in_pool": None}
    clauses, params = ["s.project_id=?"], [project]
    if chapter is not None:
        clauses.append("s.chapter_id=?")
        params.append(chapter)
    if session is not None:
        clauses.append("s.external_id=?")
        params.append(session)
    catalog = [dict(row) for row in db.execute(
        "SELECT s.id,s.external_id,s.title FROM sessions s WHERE " +
        " AND ".join(clauses) + " LIMIT 513", params)]
    if len(catalog) > CATALOG_LIMIT:
        provenance["reason"] = "catalog_limit"
        return candidates, provenance
    excluded = {row["session_id"] for row in candidates[:limit]}
    reference = _find_reference(anchor, catalog, excluded)
    if reference is None:
        return candidates, provenance
    target_session, mention = reference
    original_target = next((row for row in candidates
                            if row["project_id"] == project
                            and row["session_id"] == target_session["external_id"]), None)
    clauses = ["p.session_pk=?", "p.project_id=?"]
    params = [target_session["id"], project]
    if chapter is not None:
        clauses.append("p.chapter_id=?")
        params.append(chapter)
    if session is not None:
        clauses.append("s.external_id=?")
        params.append(session)
    if original_target is not None:
        clauses.append("p.id=?")
        params.append(original_target["id"])
    page = db.execute(
        """SELECT p.rid,p.id,p.project_id,p.chapter_id,c.title chapter_title,
          s.external_id session_id,s.title session_title,s.created_at,
          p.title,p.section_id,p.session_pk,p.content,p.source_refs,
          pr.name project_name,sec.title section_title FROM pages p
          JOIN sessions s ON s.id=p.session_pk JOIN chapters c ON c.id=p.chapter_id
          JOIN projects pr ON pr.id=p.project_id JOIN sections sec ON sec.id=p.section_id
          WHERE """ + " AND ".join(clauses) +
        " ORDER BY sec.ordinal,p.ordinal,p.id LIMIT 1", params).fetchone()
    if page is None:
        provenance["reason"] = "no_target_page"
        return candidates, provenance
    target = dict(original_target) if original_target is not None else {}
    target.update(dict(page))
    if original_target is None:
        target["score"] = 0.0
    page_in_pool = any(row["id"] == target["id"] for row in candidates)
    provenance.update(applied=True, reason="applied", target_page_id=target["id"],
                      target_session_id=target["session_id"], mention=mention,
                      target_initial_page_in_pool=page_in_pool,
                      target_initial_session_in_pool=original_target is not None,
                      target_route="existing_lexical" if original_target is not None else "title_reference")
    reordered = [anchor, target]
    reordered.extend(row for row in candidates[1:] if row["id"] != target["id"])
    return reordered, provenance
