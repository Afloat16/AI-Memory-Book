"""Indexed directory discovery, separate from original-evidence retrieval.

The existing FTS index repeats directory metadata on each page. Discovery
groups those indexed hits into chapters *before* applying pagination; a large
chapter therefore occupies one result rather than one result per page. Only
title, question and directory columns can match. Summaries are navigation
metadata, not a claim that the matching directory answers the question.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .scope import validate_project
from .text import query_terms

if TYPE_CHECKING:
    from .store import MemoryBook


SECTION_PREVIEW_LIMIT = 5

# The equality checks retain the project/chapter/session ownership chain even
# if a database contains individually valid foreign keys with mixed ownership.
# MATCH drives the lookup; no title LIKE search or Python archive scan is used.
_MATCH_FROM = """
FROM pages_fts
CROSS JOIN pages p ON p.rid=pages_fts.rowid
JOIN chapters c ON c.id=p.chapter_id AND c.project_id=p.project_id
JOIN sessions s ON s.id=p.session_pk
  AND s.chapter_id=p.chapter_id AND s.project_id=p.project_id
JOIN sections sec ON sec.id=p.section_id
  AND sec.chapter_id=p.chapter_id AND sec.session_pk=p.session_pk
"""


def _ranked_hits(where: str) -> str:
    """Keep FTS auxiliary evaluation inside its MATCH cursor.

    LIMIT -1 deliberately prevents SQLite from flattening this subquery into
    the aggregate that consumes it. It places no candidate cap: project and
    chapter predicates run before grouping, and pagination happens afterward.
    This also works on SQLite versions before MATERIALIZED CTE syntax.
    """
    return ("SELECT p.chapter_id,p.section_id,"
            "bm25(pages_fts,2.0,1.0,0.0,4.0) AS match_rank "
            + _MATCH_FROM + " WHERE " + where + " LIMIT -1")


def _batch_directory_matches(book: MemoryBook, where: str, parameters: list,
                             project: str | None, limit: int, offset: int) -> tuple | None:
    """Share one MATCH across complete aggregates and bounded previews.

    Each section belongs to one chapter. Summing section page counts and
    taking their minimum ranks therefore preserves the original chapter
    aggregates exactly. The non-flattening hits fence keeps bm25 inside its
    MATCH cursor. Ordinary CTEs and windows need no schema, JSON extension or
    MATERIALIZED syntax. Older/customized connections use the original path.
    """
    def statement(predicate: str) -> str:
        return """WITH hits AS (""" + _ranked_hits(predicate) + """),
          section_matches AS (
            SELECT chapter_id,section_id,MIN(match_rank) AS match_rank,
              COUNT(*) AS matching_pages FROM hits GROUP BY chapter_id,section_id
          ), chapter_matches AS (
            SELECT chapter_id,MIN(match_rank) AS match_rank,SUM(matching_pages) AS matching_pages,
              COUNT(DISTINCT section_id) AS matching_sections_total
            FROM section_matches GROUP BY chapter_id
          ), ranked_chapters AS (
            SELECT * FROM chapter_matches ORDER BY match_rank,chapter_id LIMIT ? OFFSET ?
          ), section_ranks AS (
            SELECT sm.*,ROW_NUMBER() OVER (
              PARTITION BY sm.chapter_id ORDER BY sm.match_rank,sm.section_id) AS preview_position
            FROM section_matches sm JOIN ranked_chapters rc ON rc.chapter_id=sm.chapter_id
          )
          SELECT totals.total,rc.chapter_id,rc.match_rank,rc.matching_pages,rc.matching_sections_total,
            sr.section_id,sr.match_rank AS section_match_rank,sr.matching_pages AS section_matching_pages,
            sec.title,sec.summary,sec.session_pk,s.external_id AS session_id,
            s.title AS session_title,s.created_at,
            (SELECT COUNT(*) FROM pages p
             WHERE p.section_id=sec.id AND p.session_pk=sec.session_pk
               AND p.chapter_id=sec.chapter_id AND p.project_id=s.project_id) AS pages_total
          FROM (SELECT COUNT(*) AS total FROM chapter_matches) totals
          LEFT JOIN ranked_chapters rc ON 1=1
          LEFT JOIN section_ranks sr ON sr.chapter_id=rc.chapter_id AND sr.preview_position<=?
          LEFT JOIN sections sec ON sec.id=sr.section_id
          LEFT JOIN sessions s ON s.id=sec.session_pk
          ORDER BY rc.match_rank,rc.chapter_id,sr.match_rank,sr.section_id"""

    if any(type(value) is not str for value in parameters):
        return None
    sql = statement(where)
    query_parameters = [*parameters, limit, offset, SECTION_PREVIEW_LIMIT]
    if not book._can_batch_scoped_query(sql, len(query_parameters)):
        return None
    bounds = book._project_rowid_bounds(project)
    if bounds is not None:
        bounded_sql = statement(where + " AND pages_fts.rowid BETWEEN ? AND ?")
        bounded_parameters = [*parameters, *bounds, limit, offset, SECTION_PREVIEW_LIMIT]
        if book._can_batch_scoped_query(bounded_sql, len(bounded_parameters)):
            sql, query_parameters = bounded_sql, bounded_parameters
    rows = book.db.execute(sql, query_parameters).fetchall()
    ranked, sections, seen = [], {}, set()
    for row in rows:
        chapter_id = row["chapter_id"]
        if chapter_id is None:
            continue
        if chapter_id not in seen:
            seen.add(chapter_id)
            ranked.append({key: row[key] for key in
                           ("chapter_id", "match_rank", "matching_pages", "matching_sections_total")})
            sections[chapter_id] = []
        if row["section_id"] is not None:
            sections[chapter_id].append({
                "section_id": row["section_id"], "match_rank": row["section_match_rank"],
                "matching_pages": row["section_matching_pages"],
                **{key: row[key] for key in ("title", "summary", "session_pk", "session_id",
                                           "session_title", "created_at", "pages_total")},
            })
    return rows[0]["total"], ranked, sections


def search_directory(book: MemoryBook, query: str, *, project: str | None = None,
                     chapter: str | None = None, limit: int = 10, offset: int = 0) -> dict:
    """Find matching chapter and section addresses without returning evidence.

    ``total`` counts distinct matching chapters. Each chapter includes at most
    five matching section previews with the real stored IDs required for a
    subsequent scoped chapter/section read. Chapter and section ordering uses
    the best (lowest) native FTS5 BM25 rank of a matching metadata row, followed
    by its exact ID. Repeated matching pages do not add their ranks together.
    BM25 is not a confidence or answerability score; its length normalization
    still uses the existing page index's document lengths.

    Query tokenization shares the archive's Chinese/English and code-identifier
    aliases. Empty/stopword-only queries return no matches; use ``toc`` to
    browse a project. Project and chapter IDs are exact, never inferred from
    labels or silently broadened. An unknown or conflicting scope raises
    ``KeyError`` even when the query is empty.

    Scope validation, revision, counts, metadata and previews use one read
    snapshot. An existing caller transaction is neither committed nor rolled
    back. This function creates no index, cache entry or persistent schema.
    """
    # Local import avoids a module cycle when MemoryBook exposes this helper.
    from .store import _integer, _string

    query = _string(query, "query", maximum=8000, required=False)
    _integer(limit, "limit", 1, 100)
    _integer(offset, "offset", 0, 10_000_000)
    if project is not None:
        validate_project(project)
    if chapter is not None:
        normalized = _string(chapter, "chapter", maximum=500)
        if normalized != chapter:
            raise ValueError("chapter must be an exact ID without surrounding whitespace")
    tokens = query_terms(query)

    db = book.db
    owns_snapshot = not db.in_transaction
    if owns_snapshot:
        db.execute("BEGIN")
    try:
        revision = book.revision
        if project is not None and db.execute(
                "SELECT 1 FROM projects WHERE id=?", (project,)).fetchone() is None:
            raise KeyError(f"project not found: {project}")
        if chapter is not None:
            row = db.execute("SELECT project_id FROM chapters WHERE id=?", (chapter,)).fetchone()
            if row is None or (project is not None and row["project_id"] != project):
                raise KeyError(f"chapter not found: {chapter}")

        response = {
            "query": query,
            "result_type": "directory",
            "evidence": False,
            "scope": {"project": project, "chapter": chapter},
            "revision": revision,
            "indexed_fields": ["title", "question", "directory"],
            "ranking": "best_metadata_bm25_then_id",
            "section_preview_limit": SECTION_PREVIEW_LIMIT,
            "results": [], "total": 0,
            "offset": offset, "limit": limit, "next_offset": None,
        }
        if not tokens:
            return response

        words = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        expression = "{title question directory} : (" + words + ")"
        predicates, parameters = ["pages_fts MATCH ?"], [expression]
        if project is not None:
            predicates.append("p.project_id=?")
            parameters.append(project)
        if chapter is not None:
            predicates.append("p.chapter_id=?")
            parameters.append(chapter)
        where = " AND ".join(predicates)

        batched = _batch_directory_matches(book, where, parameters, project, limit, offset)
        total = (batched[0] if batched is not None else
                 db.execute("SELECT COUNT(DISTINCT p.chapter_id) " + _MATCH_FROM
                            + " WHERE " + where, parameters).fetchone()[0])
        response["total"] = total
        if offset >= total:
            return response

        # The only chapter LIMIT is outside GROUP BY: even thousands of pages
        # in one chapter cannot consume another chapter's result slot.
        ranked = batched[1] if batched is not None else db.execute(
            "SELECT chapter_id,MIN(match_rank) AS match_rank,COUNT(*) AS matching_pages,"
            "COUNT(DISTINCT section_id) AS matching_sections_total FROM ("
            + _ranked_hits(where) + ") AS hits GROUP BY chapter_id "
            "ORDER BY match_rank,chapter_id LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
        identities = [row["chapter_id"] for row in ranked]
        placeholders = ",".join("?" for _ in identities)
        metadata = {
            row["id"]: dict(row) for row in db.execute(
                """SELECT c.id,c.project_id,c.task_id,c.title,c.summary,pr.name AS project_name,
                (SELECT COUNT(*) FROM pages p
                 WHERE p.chapter_id=c.id AND p.project_id=c.project_id) AS pages_total,
                (SELECT COUNT(*) FROM sessions s
                 WHERE s.chapter_id=c.id AND s.project_id=c.project_id) AS sessions_total,
                (SELECT COUNT(*) FROM sections sec JOIN sessions s ON s.id=sec.session_pk
                 WHERE sec.chapter_id=c.id AND s.chapter_id=c.id
                   AND s.project_id=c.project_id) AS sections_total
                FROM chapters c JOIN projects pr ON pr.id=c.project_id WHERE c.id IN ("""
                + placeholders + ")", identities,
            )
        }
        for match in ranked:
            chapter_id = match["chapter_id"]
            details = metadata[chapter_id]
            section_where = where + " AND p.chapter_id=?"
            section_rows = batched[2][chapter_id] if batched is not None else db.execute(
                """SELECT matched.section_id,matched.match_rank,matched.matching_pages,
                sec.title,sec.summary,sec.session_pk,s.external_id AS session_id,
                s.title AS session_title,s.created_at,
                (SELECT COUNT(*) FROM pages p
                 WHERE p.section_id=sec.id AND p.session_pk=sec.session_pk
                   AND p.chapter_id=sec.chapter_id AND p.project_id=s.project_id) AS pages_total
                FROM (
                  SELECT section_id,MIN(match_rank) AS match_rank,COUNT(*) AS matching_pages
                  FROM (""" + _ranked_hits(section_where) + """ ) AS hits
                  GROUP BY section_id ORDER BY match_rank,section_id LIMIT ?
                ) AS matched
                JOIN sections sec ON sec.id=matched.section_id
                JOIN sessions s ON s.id=sec.session_pk
                ORDER BY matched.match_rank,matched.section_id""",
                [*parameters, chapter_id, SECTION_PREVIEW_LIMIT],
            ).fetchall()
            sections = []
            for section in section_rows:
                preview = dict(section)
                sections.append({
                    "kind": "section", "id": preview["section_id"],
                    "project_id": details["project_id"], "chapter_id": chapter_id,
                    **preview,
                })
            response["results"].append({
                "kind": "chapter", **details, "chapter_id": chapter_id,
                "match_rank": match["match_rank"],
                "matching_pages": match["matching_pages"],
                "matching_sections_total": match["matching_sections_total"],
                "sections": sections,
                "sections_truncated": match["matching_sections_total"] > len(sections),
            })
        response["next_offset"] = offset + limit if offset + limit < total else None
        return response
    finally:
        if owns_snapshot and db.in_transaction:
            db.execute("ROLLBACK")
