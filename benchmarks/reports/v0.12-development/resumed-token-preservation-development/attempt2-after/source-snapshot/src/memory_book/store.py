"""Transactional SQLite source archive, book index, and budgeted recall."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from bisect import bisect_right
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from types import FunctionType
from typing import Any

from .segmentation import make_turns, segment
from ._text_backend import NATIVE as _NATIVE
from .text import (IDENTIFIER_WORD_BOUNDARY, estimate_tokens, excerpt, headline,
                   identifier_terms as terms, index_text, query_terms, terms as lexical_terms)

SCHEMA_VERSION = 4
INDEX_VERSION = 3
LEXICAL_INDEX_VERSION = 1
RECALL_VERSION = 20
APPLICATION_ID = 0x4D424F4B
MAX_SESSION_CHARS = 8_000_000
CURRENT_QUERY = re.compile(r"\b(?:latest|current|now|final|finally)\b|当前|现在|最新|最终|最后", re.IGNORECASE)
HISTORICAL_QUERY = re.compile(r"\b(?:original|initial|previous|earlier|before|history|historical|formerly|old|as of)\b|最初|最早|之前|以前|原来|原始|历史|旧|\b(?:19|20)\d{2}\b", re.IGNORECASE)
# These are source requests, not requests for an earlier state. Only mask them
# for intent detection when a separate current cue exists; source/query text
# and the lexical index stay unchanged. Bare "original decision" remains
# ambiguous, as do comparisons and as-of references elsewhere in the query.
PROVENANCE_QUERY = re.compile(
    r"\boriginal\s+(?:source(?:\s+evidence)?|evidence|quotation|quote|text|transcript|message)s?\b|"
    r"\b(?:cite|quote)\s+(?:the\s+)?original\s+(?:(?:engineering|technical|design)\s+)?decision(?:\s+record)?\b|"
    r"原始(?:的)?(?:证据|出处|来源|引用|原文|记录|文本|会话|对话)|"
    r"(?:找出|引用|提供|展示|给出|定位|追溯)(?:其|该|这项|对应的|相关的|所依据的)?"
    r"原始(?:的)?(?:(?:工程|技术|设计)(?:的)?)?决策(?:记录|依据|原文)?", re.IGNORECASE)
DATASET_YEAR_QUERY = re.compile(
    r"\b(?:dataset|data\s+set)\s*[:=_-]?\s*(?:19|20)\d{2}\b(?![-/]\d)|"
    r"\b(?:19|20)\d{2}\s+(?:dataset|data\s+set)\b|"
    r"数据集\s*[:：=_-]?\s*(?:19|20)\d{2}\b(?![-/]\d)|"
    r"\b(?:19|20)\d{2}\s*(?:年版|版)?数据集", re.IGNORECASE)
COMPARISON_QUERY = re.compile(r"\b(?:compare|compared|comparison|versus|vs)\b|比较|对比|相比", re.IGNORECASE)
NEGATED_CURRENT_QUERY = re.compile(
    r"\bnot\s+(?:the\s+)?(?:current|latest|final)\b|"
    r"(?:不要|不是|并非|不看|不查)(?:当前|现在|最新|最终)", re.IGNORECASE)
# Repeated observations are evidence for event counts and chronology. This
# conservative lexical guard does not interpret arbitrary intent, and avoids
# treating parameter names such as "retention count" as event-count requests.
EVENT_QUERY = re.compile(
    r"\b(?:how\s+often|how\s+many(?:\s+\w+){0,3}\s+(?:times|sessions|events|occurrences)|"
    r"(?:count|number)\s+of\s+(?:the\s+)?(?:times|sessions|events|occurrences)|"
    r"(?:count|list|enumerate)\s+(?:all\s+|the\s+)?(?:sessions|events|occurrences)|"
    r"(?:session|event|occurrence)\s+counts?|occurrences?|frequenc(?:y|ies)|"
    r"timeline|chronolog(?:y|ical)|(?:sequence|order)\s+of\s+(?:events|decisions)|"
    r"(?:each|every)\s+(?:session|event|occurrence))\b|"
    r"次数|多少次|几次|频率|频次|逐次|每次|各次|时间线|时间顺序|先后|事件序列|"
    r"统计.{0,12}(?:会话|事件|次数)|(?:会话|事件).{0,12}(?:数量|个数|总数)", re.IGNORECASE)


def _resolve_temporal_intent(query: str, temporal: str, strategy: str) -> dict:
    """Resolve bounded lexical hints, with an explicit override for callers.

    Relevance is the existing relevance order, not an as-of state solver.
    A current query may ask for provenance or name a dataset edition. Ignore
    only those narrow spans when looking for *other* historical cues; genuine
    history/comparison/date references retain their conservative precedence.
    Occurrence queries always retain repeated sources, even with an override.
    """
    if not isinstance(temporal, str) or temporal not in {"auto", "current", "relevance"}:
        raise ValueError("temporal must be auto, current, or relevance")
    if temporal == "current" and strategy == "flat":
        raise ValueError("temporal=current requires the book strategy")
    current = list(dict.fromkeys(match.group() for match in CURRENT_QUERY.finditer(query)))
    ignored = []
    remaining = query
    if current and not COMPARISON_QUERY.search(query) and not NEGATED_CURRENT_QUERY.search(query):
        def mask(match: re.Match[str]) -> str:
            ignored.append(match.group())
            return " " * len(match.group())
        remaining = PROVENANCE_QUERY.sub(mask, remaining)
        remaining = DATASET_YEAR_QUERY.sub(mask, remaining)
    historical = list(dict.fromkeys(match.group() for match in HISTORICAL_QUERY.finditer(remaining)))
    if strategy == "flat":
        resolved, basis = "relevance", "flat_strategy"
    elif temporal != "auto":
        resolved, basis = temporal, "explicit_override"
    elif historical:
        resolved = "relevance"
        basis = "mixed_temporal_cues" if current else "historical_cue"
    elif current:
        resolved, basis = "current", "current_cue"
    else:
        resolved, basis = "relevance", "no_current_cue"
    result = {"requested": temporal, "resolved": resolved, "basis": basis,
              "preserve_occurrences": bool(EVENT_QUERY.search(query))}
    if current:
        result["current_cues"] = current
    if historical:
        result["historical_cues"] = historical
    if ignored:
        result["provenance_or_dataset_labels"] = list(dict.fromkeys(ignored))
    return result


ASCII_WORD = re.compile(r"[a-zA-Z]")
QUERY_CONJUNCTION = re.compile(r"\band\b|以及|并且|和", re.IGNORECASE)
RECALL_METADATA_INDEX_SQL = """CREATE INDEX IF NOT EXISTS pages_recall_metadata
ON pages(rid,id,project_id,chapter_id,session_pk);"""
STEM_INDEX_SQL = "CREATE VIRTUAL TABLE IF NOT EXISTS pages_stem_fts USING fts5(title, question, body, directory, tokenize='porter unicode61');"
STEM_DELETE_SQL = """CREATE TRIGGER IF NOT EXISTS pages_delete_stem_fts AFTER DELETE ON pages BEGIN
 DELETE FROM pages_stem_fts WHERE rowid = OLD.rid;
END;"""
STEM_REVISION_SQL = """CREATE TRIGGER IF NOT EXISTS meta_revision_sync_stem
AFTER UPDATE OF value ON meta
WHEN NEW.key='revision'
 AND COALESCE((SELECT value FROM meta WHERE key='stem_revision'), '') != NEW.value
BEGIN
 DELETE FROM pages_stem_fts;
 INSERT INTO pages_stem_fts(rowid,title,question,body,directory)
  SELECT rowid,title,question,body,directory FROM pages_fts;
 INSERT OR REPLACE INTO meta(key,value) VALUES('stem_revision',NEW.value);
END;"""
LEXICAL_REVISION_SQL = """CREATE TRIGGER IF NOT EXISTS meta_revision_require_lexical
BEFORE UPDATE OF value ON meta
WHEN NEW.key='revision'
 AND COALESCE((SELECT value FROM meta WHERE key='lexical_revision'), '') != NEW.value
BEGIN
 SELECT RAISE(ABORT,'Memory Book lexical index changed; restart older writers with the current version');
END;"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('revision', '0');
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 task_id TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
 UNIQUE(project_id, task_id)
);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, external_id TEXT NOT NULL,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
 title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 content_hash TEXT NOT NULL, raw_json TEXT NOT NULL, segmentation TEXT NOT NULL,
 message_count INTEGER NOT NULL, turn_count INTEGER NOT NULL, content_chars INTEGER NOT NULL,
 settings_json TEXT NOT NULL DEFAULT '{}',
 UNIQUE(project_id, external_id)
);
CREATE INDEX IF NOT EXISTS sessions_chapter ON sessions(chapter_id, created_at);
CREATE TABLE IF NOT EXISTS turns (
 id TEXT PRIMARY KEY, session_pk TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, question TEXT NOT NULL, content TEXT NOT NULL, message_indices TEXT NOT NULL,
 UNIQUE(session_pk, ordinal)
);
CREATE TABLE IF NOT EXISTS sections (
 id TEXT PRIMARY KEY, session_pk TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
 title TEXT NOT NULL, summary TEXT NOT NULL, ordinal INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sections_chapter ON sections(chapter_id, session_pk, ordinal);
CREATE TABLE IF NOT EXISTS pages (
 rid INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
 section_id TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
 session_pk TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, question TEXT NOT NULL, content TEXT NOT NULL,
 source_refs TEXT NOT NULL, ordinal INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS pages_project ON pages(project_id);
CREATE INDEX IF NOT EXISTS pages_session ON pages(session_pk);
CREATE INDEX IF NOT EXISTS pages_chapter ON pages(chapter_id);
CREATE INDEX IF NOT EXISTS pages_section ON pages(section_id, ordinal);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(title, question, body, directory, tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS pages_delete_fts AFTER DELETE ON pages BEGIN
 DELETE FROM pages_fts WHERE rowid = OLD.rid;
END;
CREATE TABLE IF NOT EXISTS recall_cache (
 key TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, touched_ns INTEGER NOT NULL
);
""" + RECALL_METADATA_INDEX_SQL + "\n" + STEM_INDEX_SQL + "\n" + STEM_DELETE_SQL + """
INSERT OR IGNORE INTO meta(key,value)
 SELECT 'stem_revision',value FROM meta WHERE key='revision';
INSERT OR IGNORE INTO meta(key,value)
 SELECT 'lexical_revision',value FROM meta WHERE key='revision';
INSERT OR IGNORE INTO meta VALUES ('lexical_index_version', '1');
""" + STEM_REVISION_SQL + "\n" + LEXICAL_REVISION_SQL + """
PRAGMA application_id = 1296191307;
PRAGMA user_version = 4;
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, *values: str) -> str:
    return prefix + hashlib.sha256(_json(values).encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _string(value: Any, name: str, *, maximum: int = 500, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{name} must be a nonempty string")
    value = value.strip()
    if len(value) > maximum or "\x00" in value:
        raise ValueError(f"{name} must be at most {maximum} characters and contain no NUL")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid UTF-8 text without unpaired surrogates") from exc
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def normalize_session(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("a session must be a JSON object")
    project = _string(payload.get("project"), "project", maximum=200)
    session_id = _string(payload.get("session_id"), "session_id", maximum=256)
    title = _string(payload.get("title") or session_id, "title", maximum=500)
    task_id = _string(payload.get("task_id") or "", "task_id", maximum=256, required=False)
    task_title = _string(payload.get("task_title") or task_id or title, "task_title", maximum=500)
    created = payload.get("created_at") or ""
    if created:
        if not isinstance(created, str):
            raise ValueError("created_at must be an ISO 8601 string")
        try:
            stamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError) as exc:
            raise ValueError("created_at must be an ISO 8601 string") from exc
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > 50_000:
        raise ValueError("messages must be a nonempty list of at most 50000 text messages")
    normalized = []
    total = 0
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or not isinstance(message.get("role"), str) or message["role"] not in {"user", "assistant", "system", "developer", "tool"}:
            raise ValueError(f"messages[{i}] needs a supported role")
        content = message.get("content")
        if not isinstance(content, str) or "\x00" in content:
            raise ValueError(f"messages[{i}].content must be text without NUL")
        try:
            content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"messages[{i}].content must be valid UTF-8 text without unpaired surrogates") from exc
        total += len(content)
        normalized.append({"role": message["role"], "content": content})
    if total > MAX_SESSION_CHARS:
        raise ValueError(f"session text exceeds {MAX_SESSION_CHARS} characters")
    if not any(m["content"].strip() and m["role"] in {"user", "assistant", "tool"} for m in normalized):
        raise ValueError("session must contain nonempty conversational content")
    return {"project": project, "project_name": _string(payload.get("project_name") or project, "project_name", maximum=500), "session_id": session_id, "title": title, "task_id": task_id, "task_title": task_title, "created_at": created, "messages": normalized}


def _context_allocations(pages: list[dict], budget: int) -> list[tuple[dict, str, int]]:
    """Share the body budget after reserving citations and complete short pages.

    Allocating while rendering only gives unused space to later results. That
    can truncate an early page even when all selected pages fit. Reserve small
    pages first, then share the remaining space between the longer pages. The
    order of evidence is unchanged and no answer labels are consulted.
    """
    if _NATIVE is not None:
        native = _NATIVE.context_allocations(pages, budget)
        if native is not NotImplemented:
            return native
    selected: list[tuple[dict, str]] = []
    minimum, overhead = 0, 0
    for row in pages:
        header = f'[{row["id"]}] {row["project_id"]} / {row["session_id"]} | {row["created_at"]}\n'
        citation_cost = len(header) + (2 if selected else 0)
        required = citation_cost + min(120, len(row["content"]))
        if minimum + required > budget:
            # Keep the previous tiny-budget behavior: one useful cited
            # fragment is preferable to several headers with almost no text.
            if not selected and budget > citation_cost + 8:
                selected.append((row, header))
                overhead += citation_cost
            break
        selected.append((row, header))
        minimum += required
        overhead += citation_cost
    allowances = [0] * len(selected)
    remaining = budget - overhead
    order = sorted(range(len(selected)), key=lambda i: len(selected[i][0]["content"]))
    for position, i in enumerate(order):
        allowance = min(len(selected[i][0]["content"]), remaining // (len(order) - position))
        allowances[i] = allowance
        remaining -= allowance
    return [(row, header, allowances[i]) for i, (row, header) in enumerate(selected)]


def _directory_tokens(text: str) -> frozenset[str]:
    return frozenset(terms(text, query=True))


_ORDINARY_DIRECTORY_TOKENS = _directory_tokens


def _ordinary_json_loader():
    # A wrapper installed before importing this module must not be certified
    # merely because it was the first callable we saw. Unknown origins keep
    # the original parsing calls. Deliberately forged private code is excluded.
    loader = json.loads
    if (type(loader) is FunctionType and loader.__module__ == "json"
            and loader.__name__ == loader.__qualname__ == loader.__code__.co_name == "loads"
            and loader.__code__.co_filename == getattr(json, "__file__", None)):
        return loader
    return None


_ORDINARY_JSON_LOADS = _ordinary_json_loader()


def _refs_from_parsed(refs: list[dict], spans: list[tuple[int, int]]) -> list[dict]:
    """Clip a single-span capture which the caller may consume only once."""
    if _NATIVE is not None:
        native = _NATIVE.refs_from_parsed(refs, spans)
        if native is not NotImplemented:
            return native
    result = []
    for lo, hi in spans:
        for ref in refs:
            start, end = max(lo, ref["start"]), min(hi, ref["end"])
            if start < end:
                result.append({**ref, "start": start, "end": end,
                    "turn_start": ref["turn_start"] + start - ref["start"],
                    "turn_end": ref["turn_start"] + end - ref["start"]})
    return result


def _query_facets(query: str) -> list[list[str]]:
    """Recognize a small explicit conjunction, without semantic query rewriting.

    Each side needs at least two lexical terms: a name such as ``research and
    development`` is not automatically treated as two independent questions.
    This is deliberately limited syntax support, not a claim to parse intent.
    """
    pieces = QUERY_CONJUNCTION.split(query)
    if not 2 <= len(pieces) <= 3:
        return []
    facets = [query_terms(piece) for piece in pieces]
    return facets if all(len(facet) >= 2 for facet in facets) else []


def _matching_turn_refs(content: str, refs: list[dict], matched: set[str]) -> list[dict]:
    """Locate comparable subjects in source spans, without guessing dates.

    A later unrelated turn sharing a page must not make an earlier fact newer.
    Require one source span to contain the group's complete exact-term match.
    Continuation pages of the same turn receive the same position. An invalid
    reference cannot establish chronology; ordinary source validation remains
    in the existing selected-page path.
    """
    if not isinstance(content, str) or not isinstance(refs, list) or not matched:
        return []
    matching = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        start, end, turn = (ref.get(key) for key in ("start", "end", "turn_index"))
        if (any(type(value) is not int for value in (start, end, turn))
                or not 0 <= start < end <= len(content) or turn < 0):
            continue
        # The caller's match set already came from this complete page's FTS
        # body. A full-page source span needs no second lexical analysis.
        if (start == 0 and end == len(content)) or matched.issubset(terms(content[start:end])):
            matching.append(ref)
    return matching


def _latest_matching_turn(content: str, raw_refs: str, matched: set[str]) -> int | None:
    try:
        refs = json.loads(raw_refs)
    except (TypeError, ValueError):
        return None
    return max((ref["turn_index"] for ref in _matching_turn_refs(content, refs, matched)), default=None)


def _current_excerpt_ref(content: str, refs: list[dict], matched: set[str], allowance: int | None = None,
                         *, original_turns: dict[int, str] | None = None) -> dict | None:
    """Propose a complete matching turn, optionally bounded by excerpt size.

    The caller supplies full original turns from the existing read snapshot.
    The proposed turn must independently contain a comparable declaration;
    a later agenda or another environment cannot obtain a special excerpt
    through term overlap alone. An unbounded
    proposal can restrict token supplements without shortening a full page
    that already fits both budgets.
    """
    if (not isinstance(refs, list)
            or len({ref.get("turn_index") for ref in refs if isinstance(ref, dict)
                    and type(ref.get("turn_index")) is int}) < 2):
        return None
    matching = _matching_turn_refs(content, refs, matched)
    if not matching:
        return None
    latest_turn = max(ref["turn_index"] for ref in matching)
    latest = [ref for ref in matching if ref["turn_index"] == latest_turn]
    # A partial or ambiguous later span must not silently promote an older
    # turn. A complete original turn is certified separately under the read
    # snapshot, not inferred from this page's own claimed coordinates.
    if len(latest) != 1:
        return None
    ref = latest[0]
    start, end = ref["start"], ref["end"]
    if (type(ref.get("turn_start")) is not int or ref["turn_start"] != 0
            or type(ref.get("turn_end")) is not int or ref["turn_end"] != end - start
            or (allowance is not None
                and end - start + bool(start) + (end < len(content)) > allowance)):
        return None
    if original_turns is None:
        return None
    sources, analysis_refs, pool, matches = {}, {}, [], {}
    for candidate in matching:
        ordinal = candidate["turn_index"]
        body = original_turns.get(ordinal)
        lo, hi = candidate["start"], candidate["end"]
        if (type(body) is not str or candidate.get("turn_start") != 0
                or candidate.get("turn_end") != len(body) or content[lo:hi] != body):
            continue
        sources[ordinal] = body
        analysis_refs[ordinal] = json.dumps([{**candidate, "start": 0, "end": len(body)}])
        # An excerpt needs its own complete match. A directory title cannot
        # supply the scope of the proposed source turn inside a mixed page.
        pool.append({"rid": ordinal, "chapter_id": "same-page", "chapter_title": ""})
        matches[ordinal] = matched.intersection(terms(body))
    contexts = {}
    groups, _ = _declaration_groups(None, pool, matches, sources, analysis_refs,
                                   authenticated_turns=set(sources), qualifier_contexts=contexts)
    declared = any(subjects and any(pool[position]["rid"] == latest_turn for position in positions)
                   for (_, subjects, _), positions in groups.items())
    # A source that explicitly revokes the previous value is useful even when
    # its replacement is available only as an indivisible code block. Keep the
    # revocation visible without parsing that code as a current declaration.
    # A conflicting/ambiguous assignment in the same turn blocks this route.
    revoked = (not contexts.get(latest_turn) and latest_turn in sources
               and any(_EXPLICIT_REVOCATION.fullmatch(clause.strip())
                       for clause, _ in _declaration_clauses(sources[latest_turn], analysis_refs[latest_turn])))
    if not declared and not revoked:
        return None
    return ref


def _distinct_current_pages(pool: list[dict], contents: dict[int, str]) -> tuple[list[dict], list[dict]]:
    """Prefer distinct raw pages within one project/task, retaining every source.

    Exact original text is the key: FTS normalization would erase meaningful
    code punctuation. Each duplicate group's newest source keeps that group's
    first relevance slot; ties retain the existing order. Other occurrences
    remain available for backfill, and are never removed from the archive.
    """
    groups = {}
    for position, item in enumerate(pool):
        body = contents.get(item["rid"])
        key = (item["project_id"], item["chapter_id"], body if type(body) is str else object())
        groups.setdefault(key, []).append(position)
    ordered = list(pool)
    deferred = set()
    for positions in groups.values():
        if len(positions) < 2:
            continue
        first = positions[0]
        newest = max(positions, key=lambda index: pool[index]["created_at"])
        if first != newest:
            first_score, newest_score = ordered[first]["score"], ordered[newest]["score"]
            ordered[first], ordered[newest] = ordered[newest], ordered[first]
            ordered[first]["score"], ordered[newest]["score"] = first_score, newest_score
        deferred.update(positions[1:])
    return ([item for index, item in enumerate(ordered) if index not in deferred],
            [item for index, item in enumerate(ordered) if index in deferred])


_FIELD_BINDING = re.compile(
    r"(?<![\w.])(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*"
    r"(?<![<>=!:])=(?!=|>)\s*[+-]?(?:\w|['\"`])")
_FIELD_REFERENCE = re.compile(
    r"(?<![\w.])(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?:==|!=|<=|>=|=)")
_NONDECLARATIVE = re.compile(
    r"\b(?:example|examples|sample|hypothetical|suppose|if|unless|could|would|might|"
    r"not|never|assert|return|print|def|class|lambda|import)\b|"
    r"e\.g\.|例如|示例|假设|如果|伪代码|不要|不能", re.IGNORECASE)
_NUMBER_WORD = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
                r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
                r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?)")
_QUANTITY_UNIT = (r"(?:attempts?|retries|retry|seconds?|milliseconds?|microseconds?|nanoseconds?|"
                  r"minutes?|hours?|days?|bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|"
                  r"kib|mib|gib|tib|kb|mb|gb|tb|ms|us|µs|μs|ns|min|s|h|b|"
                  r"requests?|workers?|threads?|tokens?|steps?|items?|connections?|"
                  r"次|毫秒|微秒|秒|分钟|小时|字节|步|个|%)")
_QUANTITY_VALUE = (r"(?:[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?|"
                   + _NUMBER_WORD + r")(?:\s*" + _QUANTITY_UNIT + r")?(?!\w)")
_PROSE_VALUE = (r"(?:" + _QUANTITY_VALUE + r"|"
                r"(?:true|false|null|none)\b|\"[^\"\n]+\"|'[^'\n]+'|`[^`\n]+`)")
_PROSE_BINDING = re.compile(
    r"(?<![\w._-])(?P<subject>[A-Za-z_\u3400-\u9fff][A-Za-z0-9_.\-\u3400-\u9fff]*?"
    r"(?:[ \t]+[A-Za-z_\u3400-\u9fff][A-Za-z0-9_.\-\u3400-\u9fff]*){0,7})(?:"
    r"\s+(?:(?:is|are)\s+(?:now\s+)?|(?:is|are)\s+(?:now\s+)?set\s+to\s+|"
    r"(?:has|have)\s+been\s+set\s+to\s+|(?:was\s+)?(?:changed|set)\s+to\s+)"
    r"|\s*(?:现在)?(?:设置为|设为|改为|调整为|是|为))" + _PROSE_VALUE, re.IGNORECASE)
# Resource limits, not quality thresholds: oversized/ambiguous input keeps the
# existing candidate path rather than analyzing a chosen prefix as complete.
_MAX_DECLARATION_FIELDS = 64
_MAX_DECLARATION_CHARS = 64_000
_DIRECT_QUALIFIER = re.compile(
    r"\w+(?:[.-]\w+)*(?:[ \t]+\w+(?:[.-]\w+)*)*[ \t]*:?")
_SIMPLE_ASSIGNMENT_VALUE = re.compile(
    r"\s*=\s*(?:" + _PROSE_VALUE + r"|[+-]?\w+(?:[./:-]\w+)*)(?P<suffix>.*)\Z",
    re.IGNORECASE)
_PROSE_QUANTITY_SUFFIX = re.compile(
    r"\s*"
    r"(?:[,，]\s*(?:旧值|原值|前值)(?:已经|已)?"
    r"(?:因(?P<reason>[^。，.!?;；:：,\"'`]+?)而)?"
    r"(?:失效|无效|撤销|弃用))?[.!。]?\s*\Z",
    re.IGNORECASE)
_SIMPLE_REASON = re.compile(r"\s+because\s+(?P<reason>[^.!?;:]+?)[.!。]?\s*\Z", re.IGNORECASE)
_REASON_RELATION = re.compile(
    r"\b(?:for|from|to|in|on|at|under|with|without|per|when|whenever|except|only|"
    r"unless|provided|assuming|conditional|hypothetical|pending|proposed|tentative|"
    r"awaiting|unapproved)\b|['\"`?,，]|"
    r"假如|假设|若|除非|仅|只在|只对|用于|适用|针对|条件|待批|待审|等待|尚未|审批|批准|提议|临时",
    re.IGNORECASE)
# Conventional reporting labels are not environment names. This deliberately
# small grammar strips no arbitrary prefix: e.g. "Production", "EU staging"
# and labels absent from the query remain distinct exact scope signatures.
_DECLARATION_FRAME = re.compile(
    r"(?:(?:selected|approved|recorded|configured|measured|accepted|confirmed|"
    r"initial|original|current|updated|final|corrected|revised)|"
    r"(?:(?:initial|original|current|approved|selected|measured|recorded|updated|final|accepted)\s+)*"
    r"(?:(?:project|implementation|runtime)\s+)?"
    r"(?:decision|configuration|contract|settings?|replacement|value)"
    r"(?:\s+for\s+(?:the\s+)?(?:(?:initial|original|current|previous|prior)\s+)?"
    r"(?:decision|configuration|contract|settings?|value))?)\Z", re.IGNORECASE)
_EXPLICIT_REVOCATION = re.compile(
    r"(?:(?:the\s+)?(?:old|previous|former|prior)\s+(?:value|setting|configuration|contract|decision)"
    r"\s+(?:is|was)\s+(?:invalid|obsolete|revoked|withdrawn|no\s+longer\s+valid)|"
    r"(?:旧值|原值|前值)(?:已经|已)?(?:失效|无效|撤销|弃用))[.!。]?", re.IGNORECASE)


def _declaration_scope(prefix: str) -> str | None:
    """Keep explicit labels, including ones the query did not mention."""
    prefix = re.sub(r"^the(?:\s+|$)", "", prefix, flags=re.IGNORECASE)
    if _DECLARATION_FRAME.fullmatch(prefix):
        return ""
    tokens = set(query_terms(prefix))
    if not set(lexical_terms(prefix)) <= tokens:
        return None  # A relation such as "from X to Y" is not a simple label.
    return " ".join(prefix.casefold().split())


def _prose_subjects(subject: str):
    """Enumerate bounded subject suffixes without erasing identifier dots."""
    for word in re.finditer(r"[A-Za-z_\u3400-\u9fff][A-Za-z0-9_.\-\u3400-\u9fff]*", subject):
        name = subject[word.start():]
        yield name, _field_identity(name)


def _simple_declaration_suffix(suffix: str) -> bool:
    """Accept a quantity or a bounded causal explanation, never a new scope.

    Units are part of the value grammar shared by assignments and prose.
    A simple ``because`` clause or complete Chinese old-value withdrawal may
    explain the value, but cannot introduce another binding, condition, quoted
    example or scope change. Chinese explanations must end at the withdrawal;
    a second comma or arbitrary trailing clause cannot waive qualification.
    Unrecognized explanations keep relevance ordering and original text.
    """
    reason = _PROSE_QUANTITY_SUFFIX.fullmatch(suffix)
    if reason is not None and reason["reason"] is None:
        return True
    if reason is None:
        reason = _SIMPLE_REASON.fullmatch(suffix)
    if reason is None:
        return False
    body = reason["reason"]
    return bool(body.strip()) and not (
        _NONDECLARATIVE.search(body) or _REASON_RELATION.search(body)
        or _FIELD_REFERENCE.search(body) or _PROSE_BINDING.search(body))


def _declaration_qualifier(line: str, binding: re.Match, identity: tuple, *, prose: bool) -> str | None:
    """Recognize a direct label on one simple declaration, without inference.

    Complex prefixes, unrecognized explanations, or multiple assignments remain
    available through relevance retrieval, but cannot obtain a different
    declaration's position through timestamp ordering. No environment-name
    list or cross-sentence scope inheritance is used.
    """
    if prose:
        if not _simple_declaration_suffix(line[binding.end():]):
            return None
        subject = binding["subject"]
        field_start = None
        for word in re.finditer(r"[A-Za-z_\u3400-\u9fff][A-Za-z0-9_.\-\u3400-\u9fff]*", subject):
            if _field_identity(subject[word.start():]) == identity:
                field_start = binding.start("subject") + word.start()
                break
        if field_start is None:
            return None
    else:
        value = _SIMPLE_ASSIGNMENT_VALUE.fullmatch(line[binding.end("name"):])
        if value is None or not _simple_declaration_suffix(value["suffix"]):
            return None
        field_start = binding.start("name")
    prefix = line[:field_start].strip()
    if not prefix:
        return ""
    return prefix.rstrip(":").strip() if _DIRECT_QUALIFIER.fullmatch(prefix) else None


def _declaration_clauses(content: str, raw_refs: str) -> list[tuple[str, int]]:
    """Parse an authenticated single-turn page outside code and examples.

    The caller checks equality with the original turn: coordinates alone cannot
    distinguish a complete turn from its first continuation page. This remains
    a syntactic hint, never certification that an archived statement is true.
    """
    if len(content) > _MAX_DECLARATION_CHARS:
        return []
    try:
        refs = json.loads(raw_refs)
    except (TypeError, ValueError):
        return []
    if (not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict)
            or any(type(refs[0].get(key)) is not int for key in ("start", "end", "turn_start", "turn_end"))
            or (refs[0]["start"], refs[0]["end"], refs[0]["turn_start"], refs[0]["turn_end"])
            != (0, len(content), 0, len(content))):
        return []
    clauses = []
    fence = None
    offset = 0
    for full_line in content.splitlines(keepends=True):
        raw = full_line.rstrip("\r\n")
        line_offset = offset
        offset += len(full_line)
        if fence is not None:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*", raw):
                fence = None
            continue
        role = re.match(r"^(?:USER|ASSISTANT|SYSTEM|DEVELOPER|TOOL):\s?", raw)
        line = raw[role.end():] if role else raw
        line_offset += role.end() if role else 0
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if opening:
            fence = (opening[1][0], len(opening[1]))
            continue
        if line.startswith(("    ", "\t")) or line.lstrip().startswith((">", "#", "//")):
            continue
        if re.search(r"[?？]", line):
            continue
        cursor = 0
        boundaries = [match.span() for match in re.finditer(r"[。！？]|(?<=[.!?])(?:\s+|$)", line)]
        for start, end in [*boundaries, (len(line), len(line))]:
            clause = line[cursor:start]
            if clause and not re.search(r"[?？]", clause) and not _NONDECLARATIVE.search(clause):
                clauses.append((clause, line_offset + cursor))
            cursor = end
    return clauses


def _field_identity(name: str) -> tuple[tuple[str, ...], ...]:
    # Keep both real word boundaries and qualified-name segments. Query stop
    # words do not apply to identifiers: a_bc != bc; user.id != user_id.
    return tuple(tuple(lexical_terms(IDENTIFIER_WORD_BOUNDARY.sub(" ", segment)))
                 for segment in name.split("."))


def _quoted_spans(line: str) -> list[tuple[int, int]]:
    """One pass handles quotations and backtick runs without rescanning prefixes."""
    spans, opening = [], None
    for token in re.finditer(r"`+|['\"]", line):
        position = token.start()
        before = position - 1
        while before >= 0 and line[before] == "\\":
            before -= 1
        if (position - before - 1) % 2:
            continue
        mark = token.group()
        if opening is None:
            if (mark == "'" and position > 0 and token.end() < len(line)
                    and line[position - 1].isalnum() and line[token.end()].isalnum()):
                continue  # An apostrophe inside an ordinary word.
            opening = (mark, position)
        elif mark == opening[0]:
            spans.append((opening[1], token.end()))
            opening = None
    if opening is not None:
        spans.append((opening[1], len(line)))
    return spans


def _complete_declaration_pages(db: sqlite3.Connection, contents: dict[int, str],
                                references: dict[int, str]) -> set[int]:
    pairs = []
    for rid, body in contents.items():
        if len(body) > _MAX_DECLARATION_CHARS:
            continue
        try:
            refs = json.loads(references[rid])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict):
            continue
        ref = refs[0]
        if (any(type(ref.get(key)) is not int for key in ("start", "end", "turn_start", "turn_end", "turn_index"))
                or ref["turn_index"] < 0
                or (ref["start"], ref["end"], ref["turn_start"], ref["turn_end"])
                != (0, len(body), 0, len(body))):
            continue
        pairs.append((rid, ref["turn_index"]))
    certified = set()
    for offset in range(0, len(pairs), 64):
        batch = pairs[offset:offset + 64]
        rows = db.execute(
            "SELECT p.rid FROM pages p JOIN turns t ON t.session_pk=p.session_pk "
            "WHERE t.content=p.content AND (" +
            " OR ".join("(p.rid=? AND t.ordinal=?)" for _ in batch) + ")",
            [value for pair in batch for value in pair])
        certified.update(row["rid"] for row in rows)
    return certified


def _partial_declaration_anchors(db: sqlite3.Connection, pool: list[dict],
                                 contents: dict[int, str], references: dict[int, str],
                                 complete: set[int]) -> dict[int, tuple[str, str]]:
    """Authenticate full original turns behind existing continuation pages.

    A partial page cannot establish a newer declaration. It may supply an
    existing relevance slot to a complete comparable turn, after its entire
    original source (not a truncated prefix) has been read and parsed. Added
    chronological proposals never gain this exception. Returned bodies and
    synthetic analysis coordinates are internal only; output citations remain
    the unmodified stored page/source coordinates.
    """
    pending = {}
    for item in pool:
        rid = item["rid"]
        if rid in complete or item.get("_revision_proposal"):
            continue
        body = contents.get(rid)
        if type(body) is not str:
            continue
        try:
            refs = json.loads(references[rid])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict):
            continue
        ref = refs[0]
        if (any(type(ref.get(key)) is not int for key in ("start", "end", "turn_start", "turn_end", "turn_index"))
                or (ref["start"], ref["end"]) != (0, len(body))
                or not 0 <= ref["turn_start"] < ref["turn_end"]
                or ref["turn_end"] - ref["turn_start"] != len(body)
                or ref["turn_index"] < 0
                or ref.get("project") != item["project_id"]
                or ref.get("session_id") != item["session_id"]):
            continue
        pending[rid] = ref
    anchors = {}
    pairs = list(pending.items())
    for offset in range(0, len(pairs), 64):
        batch = pairs[offset:offset + 64]
        rows = db.execute(
            "SELECT p.rid,t.content FROM pages p JOIN turns t ON t.session_pk=p.session_pk "
            "JOIN sessions s ON s.id=p.session_pk AND s.project_id=p.project_id "
            "AND s.chapter_id=p.chapter_id WHERE length(t.content)<=? AND (" +
            " OR ".join("(p.rid=? AND t.ordinal=?)" for _ in batch) + ")",
            [_MAX_DECLARATION_CHARS,
             *[value for rid, ref in batch for value in (rid, ref["turn_index"])]])
        for row in rows:
            rid, original = row["rid"], row["content"]
            ref = pending[rid]
            if (type(original) is not str or not len(contents[rid]) < len(original) <= _MAX_DECLARATION_CHARS
                    or ref["turn_end"] > len(original)
                    or original[ref["turn_start"]:ref["turn_end"]] != contents[rid]):
                continue
            analysis = {**ref, "start": 0, "end": len(original),
                        "turn_start": 0, "turn_end": len(original)}
            anchors[rid] = original, json.dumps([analysis])
    return anchors


def _declaration_groups(db: sqlite3.Connection | None, pool: list[dict], matched: dict[int, set[str]],
                        contents: dict[int, str], references: dict[int, str], *,
                        qualifier_contexts: dict | None = None,
                        authenticated_turns: set[int] | None = None) -> tuple[dict, dict]:
    """Compare the same declared field without promoting mere later mentions.

    Values never enter the key or score. Field names come only from candidate
    text, and must match the query. Clear prose updates to those fields are
    included, so a change from ``retry_limit=3`` to ``retry limit is now 7``
    remains comparable. Plain numeric prose can establish its own subject;
    an unrelated code example is not required to supply its field spelling.
    Query terms supported only by the common chapter title are navigation
    context. All other matched facets must qualify each declaration itself.
    Unclassified prose/code stays in its original relevance slot.
    """
    query = set().union(*matched.values())
    # Local qualifiers govern every timestamp transfer, including candidates
    # already present in the original relevance pool.
    if qualifier_contexts is None:
        qualifier_contexts = {}
    complete = (_complete_declaration_pages(db, contents, references)
                if authenticated_turns is None else authenticated_turns)
    anchors = (_partial_declaration_anchors(db, pool, contents, references, complete)
               if authenticated_turns is None else {})
    if anchors:
        contents = {**contents, **{rid: values[0] for rid, values in anchors.items()}}
        references = {**references, **{rid: values[1] for rid, values in anchors.items()}}
        for item in pool:
            if item["rid"] in anchors:
                item["_current_anchor_only"] = True
        complete = complete | anchors.keys()
    fields, declared = {}, {}
    ordinary = (type(db) is sqlite3.Connection and db.row_factory is sqlite3.Row
                and db.text_factory is str and json.loads is _ORDINARY_JSON_LOADS
                and all(type(body) is str for body in contents.values()))
    seen_bodies = set()
    # Code/examples/comparisons may identify a field's spelling, but never
    # establish its current value. This also recognizes older prose followed
    # by a code example without treating the example as the latest revision.
    for body in contents.values():
        if len(body) > _MAX_DECLARATION_CHARS:
            continue
        if ordinary:
            if body in seen_bodies:
                continue
            seen_bodies.add(body)
        for binding in _FIELD_REFERENCE.finditer(body):
            name = binding["name"]
            aliases = set(query_terms(name))
            if not aliases.intersection(query):
                continue
            identity = _field_identity(name)
            if not all(identity):
                continue
            if identity not in fields and len(fields) == _MAX_DECLARATION_FIELDS:
                return {}, {"basis": "relevance retained: field analysis exceeded 64 fields"}
            fields.setdefault(identity, set()).update(aliases)
    # Derive a plain-prose field only from the query-matching subject suffix.
    # Existing assignment identities take precedence, retaining dotted-name
    # boundaries and cross-spelling aliases. This is syntax, not truth scoring.
    for body in dict.fromkeys(contents.values()) if ordinary else contents.values():
        if len(body) > _MAX_DECLARATION_CHARS:
            continue
        for binding in _PROSE_BINDING.finditer(body):
            suffixes = list(_prose_subjects(binding["subject"]))
            if any(identity in fields for _, identity in suffixes):
                continue
            for name, identity in suffixes:
                aliases = set(query_terms(name))
                if not aliases or not aliases <= query or not set(lexical_terms(name)) <= aliases:
                    continue
                if identity not in fields and len(fields) == _MAX_DECLARATION_FIELDS:
                    return {}, {"basis": "relevance retained: field analysis exceeded 64 fields"}
                fields.setdefault(identity, set()).update(aliases)
                break
    if not fields:
        oversized = sum(len(body) > _MAX_DECLARATION_CHARS for body in contents.values())
        return {}, ({"oversized_candidates": oversized,
                     "basis": "relevance retained: pages over 64000 characters were not analyzed"}
                    if oversized else {})
    clauses, parsed_clauses = {}, {}
    for rid, body in contents.items():
        if rid not in complete or not matched.get(rid):
            continue
        if ordinary and body in parsed_clauses:
            clauses[rid] = parsed_clauses[body]
        else:
            clauses[rid] = _declaration_clauses(body, references[rid])
            if ordinary:
                # Every page was independently checked against its own full
                # source turn above. Only the pure syntax of identical text
                # is shared, never source authentication or coordinates.
                parsed_clauses[body] = clauses[rid]
    parsed_fields, parsed_contexts = {}, {}
    for rid, lines in clauses.items():
        body = contents[rid]
        if ordinary and body in parsed_fields:
            subjects = parsed_fields[body]
            if subjects:
                declared[rid] = subjects
            if qualifier_contexts is not None:
                qualifier_contexts[rid] = parsed_contexts[body]
            continue
        # Parse quotes once in the original whole turn. Splitting first would
        # lose quotation state across a sentence or newline inside a quote.
        quoted = _quoted_spans(body)
        starts = [span[0] for span in quoted]

        def quoted_at(position):
            index = bisect_right(starts, position) - 1
            return index >= 0 and position < quoted[index][1]

        local = {}
        for line, origin in lines:
            bindings = list(_FIELD_BINDING.finditer(line))
            prose_bindings = list(_PROSE_BINDING.finditer(line))
            single = (qualifier_contexts is not None and
                      sum(not quoted_at(origin + binding.start())
                          for binding in (*bindings, *prose_bindings)) == 1)
            for binding in bindings:
                identity = _field_identity(binding["name"])
                if identity in fields and not quoted_at(origin + binding.start()):
                    declared.setdefault(rid, set()).add(identity)
                    if qualifier_contexts is not None:
                        prefix = (_declaration_qualifier(line, binding, identity, prose=False)
                                  if single else None)
                        local.setdefault(identity, []).append(prefix)
            for binding in prose_bindings:
                if quoted_at(origin + binding.start()):
                    continue
                # One scan per clause and bounded dictionary lookups; do not
                # scan every field's regex over every source clause. Longest
                # subject suffix wins, without crossing a qualified-name dot.
                for _, identity in _prose_subjects(binding["subject"]):
                    if identity in fields:
                        declared.setdefault(rid, set()).add(identity)
                        if qualifier_contexts is not None:
                            prefix = (_declaration_qualifier(line, binding, identity, prose=True)
                                      if single else None)
                            local.setdefault(identity, []).append(prefix)
                        break
        if qualifier_contexts is not None:
            # More than one declaration of the same field is ambiguous for a
            # whole-page revision, even if one of the prefixes looks suitable.
            qualifier_contexts[rid] = {identity: values[0] if len(values) == 1 else None
                                       for identity, values in local.items()}
            if ordinary:
                # This is only syntax derived from identical body bytes. The
                # source for each rid was independently authenticated above.
                parsed_contexts[body] = qualifier_contexts[rid]
        if ordinary:
            parsed_fields[body] = frozenset(declared.get(rid, ()))
    groups, unqualified = {}, 0
    directory_terms = {}
    for position, item in enumerate(pool):
        rid = item["rid"]
        if not matched[rid]:
            continue
        subjects = frozenset(declared.get(rid, ()))
        aliases = set().union(*(fields[subject] for subject in subjects)) if subjects else set()
        title = item["chapter_title"]
        if title not in directory_terms:
            directory_terms[title] = frozenset(query_terms(title))
        required = matched[rid] - aliases - directory_terms[title]
        local = qualifier_contexts.get(rid, {})
        signatures = []
        comparable = bool(subjects)
        for subject in subjects:
            prefix = local.get(subject)
            if prefix is None:
                comparable = False
                break
            scope = _declaration_scope(prefix)
            if scope is None or not required <= set(query_terms(scope)):
                comparable = False
                break
            signatures.append(scope)
        if signatures and any(signature != signatures[0] for signature in signatures[1:]):
            comparable = False
        if comparable:
            key = (item["chapter_id"], subjects, signatures[0])
        else:
            # Keep all original evidence available without lending its score
            # to an agenda, partial turn, suffix-qualified or mixed-scope page.
            key = (item["chapter_id"], frozenset(), (rid,))
            unqualified += bool(subjects)
        groups.setdefault(key, []).append(position)
    return groups, {"declaration_candidates": len(declared),
                    "unclassified_candidates": sum(bool(matched[item["rid"]]) and item["rid"] not in declared
                                                   for item in pool),
                    "oversized_candidates": sum(len(body) > _MAX_DECLARATION_CHARS for body in contents.values()),
                    "unqualified_declarations": unqualified,
                    "complete_source_partial_anchors": len(anchors),
                    "basis": "same declared fields and statement-local qualifiers; chapter terms are navigation context; syntax is not authority"}


def _qualify_revision_proposals(db: sqlite3.Connection, pool: list[dict],
                                matched: dict[int, set[str]], contents: dict[int, str],
                                references: dict[int, str], *, declarations: bool,
                                diagnostics: dict | None) -> tuple[list[dict], dict, dict]:
    """Check supplements before they can take any original relevance slot.

    Every transferred position requires a complete, independently authenticated
    turn declaring the same fields and statement-local facets. An added page
    must also have an independently qualified original page
    in the same chapter. A proposal cannot authenticate another proposal.

    Rejected text must not supply field spellings to the retained pool. Repeat
    analysis on the smaller set until stable, without moving pages or scores.
    Each non-final pass removes at least one of the at-most-96 proposals; raw
    source pages have already been read under recall's existing snapshot.
    """
    proposed = {item["rid"] for item in pool if item.get("_revision_proposal")}
    passes = 0
    facet_rejected = set()
    while True:
        refined, diagnostic = {}, {}
        contexts = {} if proposed else None
        if declarations and len(pool) > 1:
            refined, diagnostic = _declaration_groups(
                db, pool, matched, contents, references, qualifier_contexts=contexts)
            passes += 1
        if not proposed:
            break
        comparable = set()
        for (_, subjects, scope), positions in refined.items():
            if not subjects:
                continue
            eligible = positions
            if any(not pool[i].get("_revision_proposal") for i in eligible):
                comparable.update(pool[i]["rid"] for i in eligible)
            if scope:
                facet_rejected.update(pool[i]["rid"] for i in positions
                                      if pool[i].get("_revision_proposal")
                                      and pool[i]["rid"] not in comparable)
        rejected = {item["rid"] for item in pool
                    if item.get("_revision_proposal") and item["rid"] not in comparable}
        if not rejected:
            break
        pool = [item for item in pool if item["rid"] not in rejected]
        retained = {item["rid"] for item in pool}
        matched = {rid: terms for rid, terms in matched.items() if rid in retained}
        contents = {rid: body for rid, body in contents.items() if rid in retained}
        references = {rid: refs for rid, refs in references.items() if rid in retained}
        proposed.difference_update(rejected)
    expansion = diagnostics.get("candidate_expansion") if diagnostics is not None else None
    if expansion is not None:
        qualified = sum(bool(item.get("_revision_proposal")) for item in pool)
        expansion.update({
            "qualification": "complete_source_declaration_with_original_pool_anchor",
            "facet_qualification": "adjacent_qualifier_on_single_simple_declaration",
            "rejected_facet_proposals": len(facet_rejected),
            "qualification_passes": passes,
            "qualified_proposals": qualified,
            "rejected_before_ordering": expansion["added_to_pool"] - qualified,
            "qualified_pool_size": len(pool),
        })
    return pool, refined, diagnostic


def _prefer_current_pool(db: sqlite3.Connection, pool: list[dict],
                         matched: dict[int, set[str]], *,
                         distinct: bool, declarations: bool = True,
                         diagnostics: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Order comparable revisions after any candidate route has been fused.

    Recency stays within one task: declarations of the same field also require
    equal remaining query facets; unclassified pages keep exact-term groups.
    Pure semantic similarity cannot establish a factual revision. All source
    reads stay inside recall's existing SQLite read snapshot.
    """
    groups = {}
    for i, item in enumerate(pool):
        if matched[item["rid"]]:
            key = (item["chapter_id"], frozenset(matched[item["rid"]]))
            groups.setdefault(key, []).append(i)
    repeated = set()
    for positions in groups.values():
        sessions = {}
        for i in positions:
            item = pool[i]
            key = (item["project_id"], item["session_id"])
            sessions.setdefault(key, []).append(item["rid"])
        for ids in sessions.values():
            if len(ids) > 1:
                repeated.update(ids)
    turn_positions = {}
    distinct = distinct and len(pool) > 1
    contents, references = {}, {}
    declarations = declarations and len(pool) > 1
    wanted_sources = repeated | ({item["rid"] for item in pool} if distinct or declarations else set())
    if wanted_sources:
        ids = sorted(wanted_sources)
        for row in db.execute(
                "SELECT rid,content,source_refs FROM pages WHERE rid IN (" +
                ",".join("?" for _ in ids) + ")", ids):
            contents[row["rid"]] = row["content"]
            references[row["rid"]] = row["source_refs"]
    pool, refined, diagnostic = _qualify_revision_proposals(
        db, pool, matched, contents, references, declarations=declarations, diagnostics=diagnostics)
    if diagnostic and diagnostics is not None:
        diagnostics["declaration_ordering"] = diagnostic
    # Qualification can remove supplementary pages. Rebuild positional groups
    # before any permutation. Unclassified text keeps its relevance position;
    # occurrence queries retain their separate chronology behavior.
    groups = {}
    for i, item in enumerate(pool):
        if matched[item["rid"]]:
            key = (item["chapter_id"], frozenset(matched[item["rid"]]))
            groups.setdefault(key, []).append(i)
    if declarations:
        groups = refined
    repeated = set()
    for positions in groups.values():
        sessions = {}
        for i in positions:
            item = pool[i]
            sessions.setdefault((item["project_id"], item["session_id"]), []).append(item["rid"])
        for ids in sessions.values():
            if len(ids) > 1:
                repeated.update(ids)
    for rid in repeated:
        turn = _latest_matching_turn(contents[rid], references[rid], matched[rid])
        if turn is not None:
            turn_positions[rid] = turn
    for positions in groups.values():
        scores = [pool[i]["score"] for i in positions]
        eligible = [pool[i] for i in positions if not pool[i].get("_current_anchor_only")]
        if not eligible:
            continue
        revisions = sorted(eligible, key=lambda item: item["created_at"], reverse=True)
        revisions.extend(pool[i] for i in positions if pool[i].get("_current_anchor_only"))
        sessions = {}
        for i, item in enumerate(revisions):
            if item["rid"] in turn_positions and not item.get("_current_anchor_only"):
                key = (item["project_id"], item["session_id"])
                sessions.setdefault(key, []).append(i)
        for same_session in sessions.values():
            # Turn positions order corrections only inside the same session;
            # a continuation within one source turn keeps its relevance order.
            ordered = sorted((revisions[i] for i in same_session),
                             key=lambda item: turn_positions[item["rid"]], reverse=True)
            for i, item in zip(same_session, ordered):
                revisions[i] = item
        for i, item, score in zip(positions, revisions, scores):
            pool[i], item["score"] = item, score
    return _distinct_current_pages(pool, contents) if distinct else (pool, [])


def _admit_revision_proposals(pool: list[dict], deferred: list[dict],
                              diagnostics: dict) -> tuple[list[dict], list[dict]]:
    """Keep only already-qualified proposals that have a relevance slot."""
    expansion = diagnostics.get("candidate_expansion")
    if expansion is None:
        return pool, deferred
    rejected = {item["id"] for item in (*pool, *deferred)
                if item.get("_revision_proposal") and item["score"] <= 0}
    pool = [item for item in pool if item["id"] not in rejected]
    deferred = [item for item in deferred if item["id"] not in rejected]
    admitted = [item for item in (*pool, *deferred) if item.get("_revision_proposal")]
    expansion["scoreless_proposals"] = len(rejected)
    expansion["unmatched_proposals"] = expansion["added_to_pool"] - len(admitted)
    expansion["admitted_proposals"] = len(admitted)
    expansion["admitted_new_candidates"] = sum(bool(item.get("_revision_discovered")) for item in admitted)
    return pool, deferred


class _RecallCandidates(dict):
    """Candidate rows with request-local, same-snapshot covering metadata."""

    __slots__ = ("metadata",)


class MemoryBook:
    """One SQLite connection per instance. Use a separate instance per thread.

    The database and raw conversations stay on the caller's machine. Lexical
    recall invokes no model or embedding provider. Opt-in exact token budgets
    may download the tokenizer's public vocabulary on first use; no source or
    query text is transmitted by that vocabulary initialization.
    """

    def __init__(self, path: str | Path = ".memory-book/memory.db", *, segmentation: str = "adaptive", max_page_chars: int = 900, min_page_chars: int = 400, similarity_threshold: float = 0.12, cache_size: int = 128, semantic_model_dir: str | Path | None = None):
        if segmentation not in {"adaptive", "turn", "session"}:
            raise ValueError("segmentation must be adaptive, turn, or session")
        _integer(max_page_chars, "max_page_chars", 128, 100_000)
        _integer(min_page_chars, "min_page_chars", 0, max_page_chars)
        _integer(cache_size, "cache_size", 0, 10_000)
        if isinstance(similarity_threshold, bool) or not isinstance(similarity_threshold, (int, float)) or not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        self.path = str(path)
        self.segmentation, self.max_page_chars = segmentation, max_page_chars
        self.min_page_chars, self.similarity_threshold = min_page_chars, similarity_threshold
        self.cache_size = cache_size
        if semantic_model_dir is not None and (not isinstance(semantic_model_dir, (str, Path)) or not str(semantic_model_dir).strip()):
            raise ValueError("semantic_model_dir must be an explicit local model directory")
        self.semantic_model_dir = Path(semantic_model_dir).expanduser().resolve() if semantic_model_dir is not None else None
        self._semantic_model = None
        self._token_count_memo = None
        # Directory text is immutable as a key: a rename or a concurrent
        # writer naturally gets a new entry. Cache only within this connection
        # and bound retained text independently of result-cache settings.
        self._directory_tokens = lru_cache(maxsize=512)(_directory_tokens)
        self._ordinary_directory_cache = self._directory_tokens
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self.path = str(Path(self.path).expanduser())
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
            if app_id not in {0, APPLICATION_ID}:
                raise ValueError("refusing to open a database belonging to another application")
            if version not in {0, 1, 2, 3, SCHEMA_VERSION}:
                raise ValueError(f"unsupported database schema {version}; expected {SCHEMA_VERSION}")
            # A modest connection-local pager target, independent of the
            # query-result cache. This does not persist a file-format setting.
            self.db.execute("PRAGMA cache_size=-4096")
            if version < SCHEMA_VERSION or not self._stem_guard_ready() or not self._lexical_guard_ready():
                self._migrate_schema()
            # The narrow covering index is derived metadata only. Adding it
            # leaves source rows, addresses, revision and schema compatibility
            # unchanged; SQLite also maintains it for older/external writers.
            self.db.execute(RECALL_METADATA_INDEX_SQL)
            self._enable_wal()
            self.db.execute("PRAGMA synchronous=NORMAL")
        except BaseException:
            self.db.close()
            raise

    def _enable_wal(self) -> None:
        """Bound mode-change contention by the existing ten-second lock budget.

        A journal-mode lock upgrade can report SQLITE_BUSY without invoking
        SQLite's busy handler. Retry only that condition, outside a transaction;
        the schema migration has already committed. This deadline includes the
        first SQLite wait and every later wait in this WAL setup stage.
        """
        deadline = time.monotonic() + 10.0
        retried = False
        while True:
            try:
                # Consume the one-row PRAGMA result so its statement releases
                # locks before another initializer or the synchronous setting.
                # :memory: legitimately retains the "memory" journal mode.
                self.db.execute("PRAGMA journal_mode=WAL").fetchone()
            except sqlite3.OperationalError as exc:
                code = getattr(exc, "sqlite_errorcode", None)
                # Python 3.10 lacks the error-code attribute and constants.
                busy = (code & 0xFF) == 5 if code is not None else str(exc) == "database is locked"
                if not busy:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(0.01, remaining))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                self.db.execute(f"PRAGMA busy_timeout={int(remaining * 1000)}").fetchone()
                retried = True
            else:
                if retried:
                    self.db.execute("PRAGMA busy_timeout=10000").fetchone()
                # Failed initialization is closed by __init__; do not issue
                # cleanup SQL that could mask its original SQLite exception.
                return

    def __enter__(self) -> MemoryBook:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.db.close()
        finally:
            try:
                self._directory_tokens.cache_clear()
            finally:
                self._semantic_model = None
                if self._token_count_memo is not None:
                    self._token_count_memo.clear()

    def _token_memo_snapshot(self) -> dict[str, int]:
        """Read-only private diagnostics; never allocate or warm the memo."""
        if self._token_count_memo is not None:
            return self._token_count_memo.snapshot()
        return {"allocated": 0, "entry_limit": 2048, "text_byte_limit": 2097152,
                **dict.fromkeys(("entries", "text_bytes", "hits", "misses", "evictions",
                                 "invalidations", "oversized_bypasses", "uncertified_bypasses"), 0)}

    def _batch_original_turns(self, wanted: dict[str, set[int]]) -> dict | None:
        """Read a small native pair set under the caller's existing snapshot.

        Unknown/customized limits and input shapes keep the old per-session
        loop, including its sort, binding and corruption errors. In particular
        Python 3.10 has no getlimit, so it retains that original query path.
        """
        if (type(self.db) is not sqlite3.Connection or self.db.row_factory is not sqlite3.Row
                or self.db.text_factory is not str or len(wanted) < 2
                or any(type(session) is not str or type(ordinals) is not set or not ordinals
                    or any(type(ordinal) is not int or not -(1 << 63) <= ordinal < (1 << 63)
                           for ordinal in ordinals) for session, ordinals in wanted.items())):
            return None
        count = sum(map(len, wanted.values()))
        getlimit = getattr(self.db, "getlimit", None)
        if count > 400 or getlimit is None:
            return None
        if 2 * count > getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER):
            return None
        # The new relation must not turn a lowered compiler limit into a new
        # failure. Accept only ordinary or more permissive structural limits;
        # do not swallow SQL errors or retry a possibly interrupted snapshot.
        for category, minimum in ((sqlite3.SQLITE_LIMIT_COLUMN, 2000),
                (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 1000),
                (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 500),
                (sqlite3.SQLITE_LIMIT_VDBE_OP, 250000000)):
            if getlimit(category) < minimum:
                return None
        statement = """WITH requested_turns(session_pk,ordinal) AS (VALUES """ + ",".join(
            "(?,?)" for _ in range(count)) + """)
          SELECT requested_turns.session_pk AS session_pk,t.ordinal,t.content FROM requested_turns
          CROSS JOIN turns t ON t.session_pk=requested_turns.session_pk
            AND t.ordinal=requested_turns.ordinal"""
        if len(statement) > getlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH):
            return None  # This fixed SQL contains ASCII only.
        parameters = [value for session, ordinals in wanted.items()
                      for ordinal in sorted(ordinals) for value in (session, ordinal)]
        return {(row["session_pk"], row["ordinal"]): row["content"]
                for row in self.db.execute(statement, parameters)}

    def _highlighted_bodies(self, expression: str, ids: list[int]) -> list[sqlite3.Row]:
        """Retain the original point-whitelist read for selected excerpts."""
        if not ids:
            return []
        parameters = ["\x01", "\x02", expression, *ids]
        return self.db.execute("""SELECT rowid,highlight(pages_stem_fts,2,?,?) body
          FROM pages_stem_fts WHERE pages_stem_fts MATCH ? AND rowid IN (""" +
          ",".join("?" for _ in ids) + ")", parameters).fetchall()

    def _semantic_encoder(self):
        if self.semantic_model_dir is None:
            raise ValueError("Semantic recall requires an explicit semantic_model_dir")
        if self._semantic_model is None:
            from .semantic import SemanticModel
            self._semantic_model = SemanticModel(self.semantic_model_dir)
        return self._semantic_model

    def build_semantic_index(self) -> dict:
        """Explicitly build optional local vectors without changing sources.

        Any ingestion, deletion or relinking makes the index stale. Semantic
        recall fails until this method succeeds; lexical recall remains usable.
        """
        from .semantic import build_index
        return build_index(self.db, self._semantic_encoder())

    def _stem_guard_ready(self) -> bool:
        """Also recognize schema-3 development databases created before the guard."""
        return bool(self.db.execute("""SELECT
          EXISTS(SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='meta_revision_sync_stem')
          AND EXISTS(SELECT 1 FROM meta WHERE key='stem_revision')""").fetchone()[0])

    def _lexical_guard_ready(self) -> bool:
        return bool(self.db.execute("""SELECT
          EXISTS(SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='meta_revision_require_lexical')
          AND EXISTS(SELECT 1 FROM meta WHERE key='lexical_index_version' AND value=?)
          AND EXISTS(SELECT 1 FROM meta WHERE key='lexical_revision'
                     AND value=(SELECT value FROM meta WHERE key='revision'))""",
          (str(LEXICAL_INDEX_VERSION),)).fetchone()[0])

    def _migrate_schema(self) -> None:
        """Initialize or upgrade atomically without changing page addresses."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            # Another connection may have upgraded while this one waited for
            # the write lock. Never replay ALTER/backfill from a stale version.
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
            if app_id not in {0, APPLICATION_ID}:
                raise ValueError("refusing to migrate a database belonging to another application")
            if version not in {0, 1, 2, 3, SCHEMA_VERSION}:
                raise ValueError(f"unsupported database schema {version}; expected {SCHEMA_VERSION}")
            if version == 0:
                existing = self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                if existing:
                    raise ValueError("refusing to initialize a non-Memory-Book database")
                # executescript commits an already-open transaction. Execute
                # complete statements instead, retaining whole triggers and
                # the lock that protects the empty-database check above.
                statement = ""
                for line in SCHEMA.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        self.db.execute(statement)
                        statement = ""
                if statement.strip():
                    self.db.execute(statement)
            elif version < SCHEMA_VERSION or not self._stem_guard_ready() or not self._lexical_guard_ready():
                names = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"meta", "projects", "sessions", "pages", "pages_fts", "recall_cache"} <= names:
                    raise ValueError("refusing to migrate a non-Memory-Book database")
                if version == 1:
                    self._migrate_v1()
                if version < SCHEMA_VERSION or not self._lexical_guard_ready():
                    self._migrate_v3()
                else:
                    self._migrate_v2()
                self._changed()
                self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _migrate_v1(self) -> None:
        """Upgrade the development schema inside the caller's write transaction.

        Schema 1 did not record custom pagination limits. Retain actual pages
        and record the historical defaults for future relinking.
        """
        self.db.execute("ALTER TABLE sessions ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")
        rows = self.db.execute("SELECT id,created_at,raw_json,segmentation FROM sessions").fetchall()
        for row in rows:
            source = json.loads(row["raw_json"])
            source["created_at"] = source.get("created_at") or row["created_at"]
            settings = {"segmentation": row["segmentation"], "max_page_chars": 1800, "min_page_chars": 400, "similarity_threshold": 0.12}
            self.db.execute("UPDATE sessions SET raw_json=?,settings_json=? WHERE id=?", (_json(source), _json(settings), row["id"]))
        self.db.execute("DELETE FROM pages_fts")
        pages = self.db.execute("SELECT p.*,c.title chapter_title,s.title session_title FROM pages p JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk").fetchall()
        for page in pages:
            question = headline(page["question"], 1200)
            self.db.execute("UPDATE pages SET question=? WHERE rid=?", (question, page["rid"]))
            self.db.execute("INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", (page["rid"], index_text(page["title"]), index_text(question), index_text(page["content"]), index_text(page["chapter_title"] + " " + page["session_title"])))

    def _migrate_v2(self) -> None:
        """Add the local stem index from existing tokens, preserving source bytes."""
        self.db.execute(STEM_INDEX_SQL)
        self.db.execute("DELETE FROM pages_stem_fts")
        self.db.execute("""INSERT INTO pages_stem_fts(rowid,title,question,body,directory)
          SELECT rowid,title,question,body,directory FROM pages_fts""")
        self.db.execute(STEM_DELETE_SQL)
        self.db.execute("""INSERT OR REPLACE INTO meta(key,value)
          SELECT 'stem_revision',value FROM meta WHERE key='revision'""")
        self.db.execute(STEM_REVISION_SQL)

    def _migrate_v3(self) -> None:
        """Rebuild only derived lexical indexes, preserving all page addresses.

        INDEX_VERSION also participates in source hashes and stays unchanged:
        an unchanged transcript must not be resegmented after this upgrade.
        A bounded cursor avoids materializing the archive's source text at once.
        Older connections cannot run this tokenizer, so their next revision
        update is rejected atomically instead of silently restoring stale tokens.
        """
        self.db.execute("DELETE FROM pages_fts")
        pages = self.db.execute("""SELECT p.rid,p.title,p.question,p.content,
          c.title chapter_title,s.title session_title FROM pages p
          JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
          ORDER BY p.rid""")
        directory_text = lru_cache(maxsize=512)(index_text)
        while batch := pages.fetchmany(128):
            self.db.executemany(
                "INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)",
                ((page["rid"], index_text(page["title"]), index_text(page["question"]),
                  index_text(page["content"]), directory_text(page["chapter_title"] + " " + page["session_title"]))
                 for page in batch))
        self._migrate_v2()
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('lexical_index_version',?)",
                        (str(LEXICAL_INDEX_VERSION),))
        self.db.execute("""INSERT OR REPLACE INTO meta(key,value)
          SELECT 'lexical_revision',value FROM meta WHERE key='revision'""")
        self.db.execute("DROP TRIGGER IF EXISTS meta_revision_require_lexical")
        self.db.execute(LEXICAL_REVISION_SQL)

    @property
    def revision(self) -> int:
        return int(self.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])

    def _changed(self) -> None:
        # Current writers already update both lexical indexes in their transaction.
        # Mark that work before advancing revision, so the database guard does
        # nothing on the normal path. The lexical guard rejects an already-open
        # older writer: copying its exact tokens into the stem index cannot
        # reproduce identifier aliases. Its caller rolls back the whole write.
        self.db.execute("""INSERT OR REPLACE INTO meta(key,value)
          SELECT 'stem_revision',CAST(value AS INTEGER)+1 FROM meta WHERE key='revision'""")
        self.db.execute("""INSERT OR REPLACE INTO meta(key,value)
          SELECT 'lexical_revision',CAST(value AS INTEGER)+1 FROM meta WHERE key='revision'""")
        self.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
        self.db.execute("DELETE FROM recall_cache")

    def _refresh_chapter(self, chapter_id: str, *, reindex_directory: bool = False) -> None:
        rows = self.db.execute("SELECT sec.summary FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.chapter_id=? ORDER BY s.created_at, sec.ordinal LIMIT 8", (chapter_id,)).fetchall()
        if not rows:
            self.db.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
        else:
            summary = " · ".join(row[0] for row in rows)[:900]
            self.db.execute("UPDATE chapters SET summary=?,updated_at=? WHERE id=?", (summary, _now(), chapter_id))
            if reindex_directory:
                title = self.db.execute("SELECT title FROM chapters WHERE id=?", (chapter_id,)).fetchone()[0]
                pages = self.db.execute("SELECT p.rid,s.title FROM pages p JOIN sessions s ON s.id=p.session_pk WHERE p.chapter_id=?", (chapter_id,)).fetchall()
                for page in pages:
                    values = (index_text(title + " " + page["title"]), page["rid"])
                    self.db.execute("UPDATE pages_fts SET directory=? WHERE rowid=?", values)
                    self.db.execute("UPDATE pages_stem_fts SET directory=? WHERE rowid=?", values)

    def ingest(self, payload: dict) -> dict:
        source = normalize_session(payload)
        turns = make_turns(source["messages"])
        sections = segment(turns, self.segmentation, self.max_page_chars, self.min_page_chars, self.similarity_threshold)
        project, external = source["project"], source["session_id"]
        session_pk = _id("ss_", project, external)
        task_key = "task:" + source["task_id"] if source["task_id"] else "session:" + external
        chapter_id = _id("ch_", project, task_key)
        now = _now()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT * FROM sessions WHERE id=?", (session_pk,)).fetchone()
            old_project = self.db.execute("SELECT name FROM projects WHERE id=?", (project,)).fetchone()
            old_chapter = self.db.execute("SELECT title FROM chapters WHERE id=?", (chapter_id,)).fetchone()
            if not payload.get("project_name") and old_project:
                source["project_name"] = old_project["name"]
            if not payload.get("task_title") and old_chapter:
                source["task_title"] = old_chapter["title"]
            source["created_at"] = source["created_at"] or (old["created_at"] if old else now)
            source_json = _json(source)
            settings = {"segmentation": self.segmentation, "max_page_chars": self.max_page_chars, "min_page_chars": self.min_page_chars, "similarity_threshold": self.similarity_threshold}
            content_hash = hashlib.sha256(_json([source, settings, INDEX_VERSION]).encode()).hexdigest()
            if old and old["content_hash"] == content_hash:
                counts = self.db.execute("SELECT COUNT(*) FROM pages WHERE session_pk=?", (session_pk,)).fetchone()[0]
                self.db.execute("COMMIT")
                return {"project": project, "session_id": external, "chapter_id": chapter_id, "pages": counts, "sections": len(sections), "turns": len(turns), "skipped": True, "revision": self.revision}
            self.db.execute("INSERT INTO projects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at", (project, source["project_name"], now, now))
            self.db.execute("INSERT INTO chapters(id,project_id,task_id,title,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at", (chapter_id, project, task_key, source["task_title"], now))
            if old:
                self.db.execute("DELETE FROM sessions WHERE id=?", (session_pk,))
            created = source["created_at"]
            self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (session_pk, external, project, chapter_id, source["title"], created, now, content_hash, source_json, self.segmentation, len(source["messages"]), len(turns), sum(len(t.content) for t in turns), _json(settings)))
            for turn in turns:
                self.db.execute("INSERT INTO turns VALUES(?,?,?,?,?,?)", (_id("t_", session_pk, str(turn.index)), session_pk, turn.index, turn.question, turn.content, _json(turn.message_indices)))
            page_count = 0
            indexed_directory = index_text(source["task_title"] + " " + source["title"])
            for i, section in enumerate(sections):
                section_id = _id("sec_", session_pk, str(i), section.title)
                self.db.execute("INSERT INTO sections VALUES(?,?,?,?,?,?)", (section_id, session_pk, chapter_id, section.title, section.summary, i))
                for j, page in enumerate(section.pages):
                    page_id = _id("p_", session_pk, str(i), str(j), page.content)
                    refs = [{**ref, "session_id": external, "project": project, "created_at": created} for ref in page.refs]
                    cur = self.db.execute("INSERT INTO pages(id,section_id,session_pk,chapter_id,project_id,title,question,content,source_refs,ordinal) VALUES(?,?,?,?,?,?,?,?,?,?)", (page_id, section_id, session_pk, chapter_id, project, page.title, page.question, page.content, _json(refs), j))
                    indexed = (cur.lastrowid, index_text(page.title), index_text(page.question), index_text(page.content), indexed_directory)
                    self.db.execute("INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", indexed)
                    self.db.execute("INSERT INTO pages_stem_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", indexed)
                    page_count += 1
            self._refresh_chapter(chapter_id, reindex_directory=bool(old_chapter and old_chapter["title"] != source["task_title"]))
            if old and old["chapter_id"] != chapter_id:
                self._refresh_chapter(old["chapter_id"])
            self._changed()
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return {"project": project, "session_id": external, "chapter_id": chapter_id, "pages": page_count, "sections": len(sections), "turns": len(turns), "skipped": False, "revision": self.revision}

    def projects(self) -> list[dict]:
        rows = self.db.execute("""SELECT p.*,
          (SELECT COUNT(*) FROM sessions WHERE project_id=p.id) sessions,
          (SELECT COUNT(*) FROM chapters WHERE project_id=p.id) chapters,
          (SELECT COUNT(*) FROM pages WHERE project_id=p.id) pages
          FROM projects p ORDER BY p.name,p.id""").fetchall()
        return [dict(row) for row in rows]

    def search_directory(self, query: str, *, project: str | None = None,
                         chapter: str | None = None, limit: int = 10,
                         offset: int = 0) -> dict:
        """Locate directory entries without treating their titles as evidence."""
        from .directory import search_directory
        return search_directory(self, query, project=project, chapter=chapter,
                                limit=limit, offset=offset)

    def toc(self, project: str, *, offset: int = 0, limit: int = 50) -> dict:
        _integer(offset, "offset", 0, 10_000_000)
        _integer(limit, "limit", 1, 100)
        owns_snapshot = not self.db.in_transaction
        if owns_snapshot:
            self.db.execute("BEGIN")
        try:
            row = self.db.execute("SELECT * FROM projects WHERE id=?", (project,)).fetchone()
            if row is None:
                raise KeyError(f"project not found: {project}")
            total = self.db.execute("SELECT COUNT(*) FROM chapters WHERE project_id=?", (project,)).fetchone()[0]
            chapters = self.db.execute("""SELECT c.*,
              (SELECT COUNT(*) FROM sessions WHERE chapter_id=c.id) sessions,
              (SELECT COUNT(*) FROM sections WHERE chapter_id=c.id) sections,
              (SELECT COUNT(*) FROM pages WHERE chapter_id=c.id) pages
              FROM chapters c WHERE project_id=? ORDER BY title,id LIMIT ? OFFSET ?""", (project, limit, offset)).fetchall()
            return {"project": dict(row), "chapters": [dict(c) for c in chapters], "total": total, "next_offset": offset + limit if offset + limit < total else None, "revision": self.revision}
        finally:
            if owns_snapshot and self.db.in_transaction:
                self.db.execute("ROLLBACK")

    def chapter(self, chapter_id: str, *, project: str | None = None, offset: int = 0, limit: int = 50, page_limit: int = 20) -> dict:
        """Read a task directory, optionally requiring its exact project ID.

        Ordinary section previews share a read snapshot. An existing caller
        transaction is reused and is never committed or rolled back here.
        Customized section readers retain the original per-section call path.
        """
        _integer(offset, "offset", 0, 10_000_000)
        _integer(limit, "limit", 1, 100)
        _integer(page_limit, "page_limit", 1, 100)
        if project is not None:
            _string(project, "project")
        section_reader = self.section
        ordinary = (getattr(section_reader, "__func__", None) is _ORDINARY_SECTION
                    and getattr(section_reader, "__self__", None) is self)
        owns_snapshot = ordinary and not self.db.in_transaction
        if owns_snapshot:
            self.db.execute("BEGIN")
        try:
            scope = " AND project_id=?" if project is not None else ""
            parameters = (chapter_id, project) if project is not None else (chapter_id,)
            row = self.db.execute("SELECT * FROM chapters WHERE id=?" + scope, parameters).fetchone()
            if row is None:
                raise KeyError(f"chapter not found: {chapter_id}")
            total = self.db.execute("SELECT COUNT(*) FROM sections WHERE chapter_id=?", (chapter_id,)).fetchone()[0]
            owner = ",s.project_id _section_project" if ordinary else ""
            rows = self.db.execute("SELECT sec.*,s.external_id session_id,s.title session_title,s.created_at" + owner + " FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.chapter_id=? ORDER BY s.created_at,s.id,sec.ordinal LIMIT ? OFFSET ?", (chapter_id, limit, offset)).fetchall()
            totals = {}
            if ordinary and rows:
                selected = [sec["id"] for sec in rows
                            if project is None or sec["_section_project"] == project]
                if selected:
                    placeholders = ",".join("?" for _ in selected)
                    totals = dict(self.db.execute("SELECT section_id,COUNT(*) FROM pages WHERE section_id IN (" + placeholders + ") GROUP BY section_id", selected))
            sections = []
            for sec in rows:
                details = dict(sec)
                if ordinary:
                    section_project = details.pop("_section_project")
                    if project is not None and section_project != project:
                        raise KeyError(f"section not found: {sec['id']}")
                    pages_total = totals.get(sec["id"], 0)
                    # Reuse section()'s indexed query and convert one bounded
                    # preview at a time, without a compound merge or sort.
                    page_rows = self.db.execute("SELECT id,title,length(content) chars,source_refs FROM pages WHERE section_id=? ORDER BY ordinal LIMIT ? OFFSET ?", (sec["id"], page_limit, 0)).fetchall()
                    preview = {
                        "pages": [{"id": p["id"], "title": p["title"], "chars": p["chars"], "turn_indices": sorted({r["turn_index"] for r in json.loads(p["source_refs"])})} for p in page_rows],
                        "total": pages_total,
                        "next_offset": page_limit if page_limit < pages_total else None,
                    }
                    del page_rows
                else:
                    preview = self.section(sec["id"], project=project, limit=page_limit)
                sections.append({**details, "pages": preview["pages"], "pages_total": preview["total"], "pages_next_offset": preview["next_offset"]})
            return {**dict(row), "sections": sections, "total": total, "next_offset": offset + limit if offset + limit < total else None}
        finally:
            if owns_snapshot and self.db.in_transaction:
                self.db.execute("ROLLBACK")

    def section(self, section_id: str, *, project: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        """Read one consistent page directory with an optional exact project ID."""
        _integer(offset, "offset", 0, 10_000_000)
        _integer(limit, "limit", 1, 100)
        if project is not None:
            _string(project, "project")
        owns_snapshot = not self.db.in_transaction
        if owns_snapshot:
            self.db.execute("BEGIN")
        try:
            scope = " AND s.project_id=?" if project is not None else ""
            parameters = (section_id, project) if project is not None else (section_id,)
            row = self.db.execute("SELECT sec.*,s.external_id session_id,s.title session_title FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.id=?" + scope, parameters).fetchone()
            if row is None:
                raise KeyError(f"section not found: {section_id}")
            total = self.db.execute("SELECT COUNT(*) FROM pages WHERE section_id=?", (section_id,)).fetchone()[0]
            pages = self.db.execute("SELECT id,title,length(content) chars,source_refs FROM pages WHERE section_id=? ORDER BY ordinal LIMIT ? OFFSET ?", (section_id, limit, offset)).fetchall()
            return {**dict(row), "pages": [{"id": p["id"], "title": p["title"], "chars": p["chars"], "turn_indices": sorted({r["turn_index"] for r in json.loads(p["source_refs"])})} for p in pages], "total": total, "next_offset": offset + limit if offset + limit < total else None}
        finally:
            if owns_snapshot and self.db.in_transaction:
                self.db.execute("ROLLBACK")

    def _breadcrumb(self, row: sqlite3.Row | dict) -> list[dict]:
        return [{"id": row["project_id"], "title": row["project_name"], "kind": "project"}, {"id": row["chapter_id"], "title": row["chapter_title"], "kind": "chapter"}, {"id": row["section_id"], "title": row["section_title"], "kind": "section"}, {"id": row["id"], "title": row["title"], "kind": "page"}]

    @staticmethod
    def _refs(row: sqlite3.Row | dict, spans: list[tuple[int, int]]) -> list[dict]:
        result = []
        for lo, hi in spans:
            for ref in json.loads(row["source_refs"]):
                start, end = max(lo, ref["start"]), min(hi, ref["end"])
                if start < end:
                    result.append({**ref, "start": start, "end": end, "turn_start": ref["turn_start"] + start - ref["start"], "turn_end": ref["turn_start"] + end - ref["start"]})
        return result

    def read(self, page_id: str, *, project: str | None = None, offset: int = 0, limit: int = 12_000) -> dict:
        """Read original evidence, optionally requiring its exact project ID."""
        _integer(offset, "offset", 0, MAX_SESSION_CHARS * 2)
        _integer(limit, "limit", 1, 100_000)
        if project is not None:
            _string(project, "project")
        scope = " AND p.project_id=?" if project is not None else ""
        parameters = (page_id, project) if project is not None else (page_id,)
        row = self.db.execute("""SELECT p.*,pr.name project_name,c.title chapter_title,sec.title section_title,s.external_id session_id,s.created_at
          FROM pages p JOIN projects pr ON pr.id=p.project_id JOIN chapters c ON c.id=p.chapter_id
          JOIN sections sec ON sec.id=p.section_id JOIN sessions s ON s.id=p.session_pk WHERE p.id=?""" + scope, parameters).fetchone()
        if row is None:
            raise KeyError(f"page not found or changed: {page_id}")
        total, end = len(row["content"]), min(offset + limit, len(row["content"]))
        return {"id": row["id"], "title": row["title"], "content": row["content"][offset:end], "offset": offset, "total_chars": total, "next_offset": end if end < total else None, "source_refs": self._refs(row, [(offset, end)]), "breadcrumb": self._breadcrumb(row), "created_at": row["created_at"]}

    def get_session(self, project: str, session_id: str) -> dict:
        row = self.db.execute("SELECT raw_json FROM sessions WHERE project_id=? AND external_id=?", (project, session_id)).fetchone()
        if row is None:
            raise KeyError(f"session not found: {project}/{session_id}")
        return json.loads(row[0])

    def export(self, project: str | None = None) -> list[dict]:
        if project is None:
            rows = self.db.execute("SELECT raw_json FROM sessions ORDER BY project_id,created_at,id")
        else:
            rows = self.db.execute("SELECT raw_json FROM sessions WHERE project_id=? ORDER BY created_at,id", (project,))
        return [json.loads(row[0]) for row in rows]

    def link_session(self, project: str, session_id: str, task_id: str, title: str | None = None) -> dict:
        """Reassign a chapter without silently changing the session's split policy."""
        source = self.get_session(project, session_id)
        row = self.db.execute("SELECT segmentation,settings_json FROM sessions WHERE project_id=? AND external_id=?", (project, session_id)).fetchone()
        settings = json.loads(row["settings_json"])
        settings.setdefault("segmentation", row["segmentation"])
        previous = {key: getattr(self, key) for key in settings}
        try:
            for key, value in settings.items():
                setattr(self, key, value)
            source.pop("project_name", None)
            source.pop("task_title", None)
            source["task_id"] = _string(task_id, "task_id", maximum=256)
            if title is not None:
                source["task_title"] = _string(title, "title")
            return self.ingest(source)
        finally:
            for key, value in previous.items():
                setattr(self, key, value)

    def delete_session(self, project: str, session_id: str) -> bool:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id,chapter_id FROM sessions WHERE project_id=? AND external_id=?", (project, session_id)).fetchone()
            if row:
                self.db.execute("DELETE FROM sessions WHERE id=?", (row["id"],))
                self._refresh_chapter(row["chapter_id"])
                self.db.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), project))
                self._changed()
            self.db.execute("COMMIT")
            return row is not None
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def delete_project(self, project: str) -> bool:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.db.execute("DELETE FROM projects WHERE id=?", (project,))
            if cur.rowcount:
                self._changed()
            self.db.execute("COMMIT")
            return bool(cur.rowcount)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def stats(self) -> dict:
        values = {key: self.db.execute(f"SELECT COUNT(*) FROM {key}").fetchone()[0] for key in ("projects", "chapters", "sessions", "turns", "sections", "pages")}
        values["chars"] = self.db.execute("SELECT COALESCE(SUM(content_chars),0) FROM sessions").fetchone()[0]
        values["page_chars"] = self.db.execute("SELECT COALESCE(SUM(length(content)),0) FROM pages").fetchone()[0]
        values["cache_entries"] = self.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
        values["database_bytes"] = self.db.execute("PRAGMA page_count").fetchone()[0] * self.db.execute("PRAGMA page_size").fetchone()[0]
        values["revision"], values["schema_version"] = self.revision, SCHEMA_VERSION
        return values

    def _project_rowid_bounds(self, project: str | None) -> tuple[int, int] | None:
        """Bound FTS iteration only when a project occupies a narrow rowid span.

        These covering-index probes run in recall's existing read snapshot.
        They retain no state across calls. Interleaved or archive-wide projects
        keep the original query plan instead of paying for ineffective bounds.
        """
        if project is None:
            return None
        lo, hi, archive_lo, archive_hi = self.db.execute("""SELECT
          (SELECT MIN(rid) FROM pages WHERE project_id=?),
          (SELECT MAX(rid) FROM pages WHERE project_id=?),
          (SELECT MIN(rid) FROM pages), (SELECT MAX(rid) FROM pages)""",
          (project, project)).fetchone()
        if lo is None:
            return (0, -1)
        if 2 * (hi - lo + 1) <= archive_hi - archive_lo + 1:
            return (lo, hi)
        return None

    def _bounded_candidate_metadata(self, rows: dict[str, dict], relevance: dict[str, float],
                                    count: int) -> dict[str, dict] | None:
        """Load shared directories once, retaining a certified ranking prefix.

        Each native title multiplier lies in [1, 1.15]. At least ``count``
        actual scores reach the count-th base relevance, so a strictly lower
        upper bound cannot enter that prefix, under any existing tie rule.
        Validate directories for the full union before omitting tail work:
        malformed archives must still take the old path and raise its errors.
        All queries stay inside recall's existing read snapshot.
        """
        if (len(rows) <= count or self.db.row_factory is not sqlite3.Row
                or self.db.text_factory is not str
                or self._directory_tokens is not self._ordinary_directory_cache
                or getattr(self._directory_tokens, "__wrapped__", None) is not _ORDINARY_DIRECTORY_TOKENS
                or any(type(row["rid"]) is not int for row in rows.values())
                or any(not math.isfinite(value) or value < 0 for value in relevance.values())):
            return None
        floor = sorted(relevance.values(), reverse=True)[count - 1]
        retained = {identity for identity, value in relevance.items() if value * 1.15 >= floor}
        if len(retained) == len(rows):
            return None
        if type(rows) is _RecallCandidates:
            # The native FTS queries already visited this covering index.
            # Reuse only this call's captured fields; ordinary dictionaries
            # and customized connection paths retain the independent read.
            light = rows.metadata.values()
        else:
            ids = [row["rid"] for row in rows.values()]
            light = self.db.execute("""SELECT id,project_id,chapter_id,session_pk
              FROM pages INDEXED BY pages_recall_metadata WHERE rid IN (""" +
              ",".join("?" for _ in ids) + ")", ids).fetchall()
        if (len(light) != len(rows) or {row[0] for row in light} != set(rows)
                or any(type(value) is not str for row in light for value in row)):
            return None
        pairs = list(dict.fromkeys((row[2], row[3]) for row in light))
        directories = self.db.execute("""WITH requested(chapter_id,session_pk) AS (VALUES """ +
            ",".join("(?,?)" for _ in pairs) + """)
          SELECT requested.chapter_id,requested.session_pk,c.id,s.id,
            c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at
          FROM requested LEFT JOIN chapters c ON c.id=requested.chapter_id
          LEFT JOIN sessions s ON s.id=requested.session_pk""",
          [value for pair in pairs for value in pair]).fetchall()
        # Empty titles are valid. Missing rows and non-text titles fall back
        # before mutating any candidate, preserving the old exception order.
        if (len(directories) != len(pairs) or
                any(type(value) is not str for row in directories for value in row)):
            return None
        metadata = {(row[0], row[1]): row for row in directories}
        if set(metadata) != set(pairs):
            return None
        for identity, project, chapter, session_pk in light:
            if identity in retained:
                directory = metadata[(chapter, session_pk)]
                rows[identity].update(project_id=project, chapter_id=chapter,
                    chapter_title=directory[4], session_id=directory[5],
                    session_title=directory[6], created_at=directory[7])
        return {identity: row for identity, row in rows.items() if identity in retained}

    def _current_revision_pool(self, candidates: list[dict], pool_size: int,
                               expression: str, where: str, params: list,
                               exact_ids: set[str], exact_complete: bool,
                               diagnostics: dict) -> tuple[list[dict], list[dict]]:
        """Extend an existing task's comparison pool with bounded recent hits.

        BM25's top 96 and the result-size-derived pool can hide a short recent
        correction beneath repeated earlier text. Every supplement is a
        proposal, including previously ranked tail pages. Only authenticated
        declarations comparable to an original same-task/field/facet anchor
        can take a relevance slot. New tasks cannot enter here.

        At most 96 recent rows are retained across the leading chapters, with
        an equal per-chapter quota when the original route was truncated.
        A complete exact route reuses all its metadata (fewer than 96 rows).
        Otherwise SQLite orders matching postings by source-session time;
        the retained rows are bounded, but the database scan/sort is not.
        Every route applies all caller scopes before its LIMIT and runs under
        recall's existing read snapshot. This is not a latest-state database.
        """
        pool = list(candidates[:pool_size])
        chapter_ids = list(dict.fromkeys(item["chapter_id"] for item in pool))
        selected_chapters = chapter_ids[:96]
        if not selected_chapters:
            return pool, list(candidates[pool_size:])
        quota, remainder = divmod(96, len(selected_chapters))
        by_id = {item["id"]: item for item in candidates}
        seen = {item["id"] for item in pool}
        returned = added = discovered = 0
        quotas = []
        for index, chapter_id in enumerate(selected_chapters):
            bound = quota + (index < remainder)
            if exact_complete:
                route = [item for item in candidates
                         if item["chapter_id"] == chapter_id and item["id"] in exact_ids]
                # Stable two-pass sorting keeps equal timestamps on ID order.
                route.sort(key=lambda item: item["id"])
                route.sort(key=lambda item: item["created_at"], reverse=True)
                bound = len(route)
            else:
                route = self.db.execute("""SELECT p.id,p.rid,p.project_id,p.chapter_id,
                  c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at
                  FROM pages_fts JOIN pages p ON p.rid=pages_fts.rowid
                  JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
                  JOIN sections sec ON sec.id=p.section_id
                  WHERE pages_fts MATCH ? AND p.chapter_id=?""" + where +
                  " ORDER BY s.created_at DESC,s.id,sec.ordinal DESC,p.ordinal DESC,p.id LIMIT ?",
                  [expression, chapter_id, *params, bound]).fetchall()
            returned += len(route)
            quotas.append({"chapter_id": chapter_id, "limit": bound, "returned": len(route)})
            for row in route:
                identity = row["id"]
                if identity in seen:
                    continue
                seen.add(identity)
                added += 1
                item = by_id.get(identity)
                if item is None:
                    # No new relevance score is invented for a chronological
                    # proposal. It can enter returned evidence only by taking
                    # the slot of a comparable, already ranked source.
                    item = {**dict(row), "rank": 0.0, "score": 0.0, "_revision_discovered": True}
                    discovered += 1
                # Existing tail scores and positions must survive rejection.
                # Both known tail pages and newly discovered pages qualify
                # before any score permutation or same-text de-duplication.
                pool.append({**item, "_revision_proposal": True})
        diagnostics["candidate_expansion"] = {
            "route": "recent_exact_body_matches_in_leading_chapters",
            "metadata_source": "complete_exact_route" if exact_complete else "scoped_fts_chronology",
            "ordering_fields": ["sessions.created_at DESC", "sessions.id", "sections.ordinal DESC", "pages.ordinal DESC", "pages.id"],
            "candidate_limit": 96, "returned": returned, "added_to_pool": added,
            "new_candidates": discovered, "pool_size": len(pool),
            "original_pool_size": pool_size,
            "proposed_existing_candidates": added - discovered,
            "chapters_not_expanded": max(0, len(chapter_ids) - len(selected_chapters)),
            "chapter_routes": quotas,
            "scope_before_limit": True,
            "database_scan_bounded": exact_complete,
            "basis": "Recent matches only propose comparable revisions; timestamps and syntax do not establish authority.",
        }
        # Only finally admitted copies are removed from the original tail by
        # the caller. Rejected copies leave its exact order and scores intact.
        return pool, list(candidates[pool_size:])

    def recall(self, query: str, project: str | None = None, chapter: str | None = None, session: str | None = None, *, budget_chars: int = 2400, limit: int = 5, strategy: str = "book", use_cache: bool = True, coverage: bool = False, budget_tokens: int | None = None, tokenizer: str = "cl100k_base", semantic: bool = False, temporal: str = "auto") -> dict:
        """Recall source evidence with optional current-state ordering.

        temporal=auto conservatively infers current versus relevance ordering;
        current explicitly prefers comparable recent evidence, and relevance
        disables this preference. Neither mode resolves an authoritative state
        or filters to an as-of date. Flat evaluation uses relevance ordering.
        The returned temporal diagnostic explains the effective choice.
        """
        started = time.perf_counter_ns()
        query = _string(query, "query", maximum=8000, required=False)
        temporal_intent = _resolve_temporal_intent(query, temporal, strategy)
        _integer(budget_chars, "budget_chars", 0, 100_000)
        _integer(limit, "limit", 1, 50)
        from .token_budget import TOKENIZERS, TokenCounter
        if not isinstance(tokenizer, str) or tokenizer not in TOKENIZERS:
            raise ValueError("tokenizer must be cl100k_base or o200k_base")
        if budget_tokens is not None:
            _integer(budget_tokens, "budget_tokens", 0, 100_000)
        token_counter = TokenCounter(tokenizer) if budget_tokens is not None else None
        if token_counter is not None:
            from .token_budget import _ExactTokenMemo, _attach_count_memo
            if self._token_count_memo is None:
                self._token_count_memo = _ExactTokenMemo()
            _attach_count_memo(token_counter, self._token_count_memo)
        if strategy not in {"book", "flat"}:
            raise ValueError("strategy must be book or flat")
        if not isinstance(coverage, bool):
            raise ValueError("coverage must be a boolean")
        if coverage and strategy != "book":
            raise ValueError("coverage requires the book strategy")
        if not isinstance(semantic, bool):
            raise ValueError("semantic must be a boolean")
        if semantic and strategy != "book":
            raise ValueError("semantic recall requires the book strategy")
        for key, val in (("project", project), ("chapter", chapter), ("session", session)):
            if val is not None:
                _string(val, key)
        qt = query_terms(query)
        current_query = temporal_intent["resolved"] == "current"
        use_stem = strategy == "book" and any(ASCII_WORD.search(token) for token in qt)
        semantic_model = self._semantic_encoder() if semantic else None
        # A read snapshot ties candidates, sources, and the cache revision together.
        self.db.execute("BEGIN")
        try:
            revision = self.revision
            cache_options = [INDEX_VERSION, RECALL_VERSION, query, project, chapter, session, budget_chars, limit, strategy, coverage, temporal]
            if semantic_model is not None:
                from .semantic import FUSION_VERSION, SEMANTIC_VERSION, check_index, fuse_candidates, rank_pages
                check_index(self.db, revision, semantic_model)
                cache_options.extend(["semantic", SEMANTIC_VERSION, semantic_model.fingerprint, FUSION_VERSION])
            if token_counter is not None:
                cache_options.extend([budget_tokens, tokenizer, token_counter.version])
            cache_key = hashlib.sha256(_json(cache_options).encode()).hexdigest()
            cached = self.db.execute("SELECT payload FROM recall_cache WHERE key=? AND revision=?", (cache_key, revision)).fetchone() if use_cache and self.cache_size else None
            if cached:
                result = json.loads(cached[0])
                self.db.execute("COMMIT")
                result["cache_hit"] = True
                result["latency_ms"] = (time.perf_counter_ns() - started) / 1e6
                return result
            clauses, params = [], []
            if project is not None:
                clauses.append("p.project_id=?")
                params.append(project)
            if chapter is not None:
                clauses.append("p.chapter_id=?")
                params.append(chapter)
            if session is not None:
                clauses.append("s.external_id=?")
                params.append(session)
            where = " AND " + " AND ".join(clauses) if clauses else ""
            candidates: list[dict] = []
            full_candidate_count = None
            allocations: list[tuple[dict, str, int]] = []
            selected_pages: list[dict] = []
            source_units_for = None
            captured_refs = None
            current_matches: dict[int, set[str]] = {}
            current_spans: dict[str, tuple[int, int]] = {}
            current_unit_spans: dict[str, tuple[int, int]] = {}
            original_turns = None
            refs_by_page = None
            if (qt or (semantic and query)) and budget_chars:
                expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in qt)
                # The index enforces a body match, so a chapter name alone is
                # never treated as evidence. Select only metadata for candidate
                # ranking; large source bodies are loaded for selected pages.
                expression = f"({expression}) AND body : ({expression})"
                # Apply every requested scope before truncating the FTS hits.
                # Directory joins are needed only for the bounded candidates;
                # display-only fields are deferred to the final page fetch.
                scope_join = " JOIN sessions s ON s.id=p.session_pk" if session is not None else ""
                project_bounds = self._project_rowid_bounds(project) if qt and session is None else None
                # A chapter/session-only scope can be more selective than
                # MATCH. Leave those unconstrained join orders free to use
                # pages_chapter/pages_session. FTS-first bounded routes and
                # ordinary global/project routes use the narrow covering map.
                covering_hint = (" INDEXED BY pages_recall_metadata" if
                                 project_bounds is not None or (chapter is None and session is None) else "")
                carry_metadata = (use_stem and not coverage and not semantic
                    and type(self.db) is sqlite3.Connection
                    and self.db.row_factory is sqlite3.Row and self.db.text_factory is str
                    and self._directory_tokens is self._ordinary_directory_cache
                    and getattr(self._directory_tokens, "__wrapped__", None) is _ORDINARY_DIRECTORY_TOKENS)
                if carry_metadata:
                    # Extra projected fields and removing the old IN query
                    # must not change errors under customized SQLite limits.
                    # Python 3.10 cannot inspect them and retains the old SQL.
                    getlimit = getattr(self.db, "getlimit", None)
                    carry_metadata = getlimit is not None and all(getlimit(category) >= minimum
                        for category, minimum in ((sqlite3.SQLITE_LIMIT_COLUMN, 2000),
                            (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 1000),
                            (sqlite3.SQLITE_LIMIT_VDBE_OP, 250000000),
                            (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 192),
                            (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 10000)))
                route_metadata = ",p.project_id,p.chapter_id,p.session_pk" if carry_metadata else ""
                routes = []
                for table in (("pages_fts", "pages_stem_fts") if use_stem else ("pages_fts",)):
                    # Table identifiers are fixed above; query text and every
                    # caller-supplied scope remain bound SQL parameters.
                    page_join = " CROSS JOIN" if project_bounds is not None else " JOIN"
                    statement = (f"""SELECT p.rid,p.id,bm25({table},2.0,2.0,1.0,0.25) rank{route_metadata}
                      FROM {table}""" + page_join +
                      f" pages p{covering_hint} ON p.rid={table}.rowid" + scope_join +
                      f" WHERE {table} MATCH ?" + where)
                    route_params = [expression, *params]
                    if project_bounds is not None:
                        # Keep FTS outermost so range constraints narrow one
                        # posting scan, rather than restarting MATCH per page.
                        # The original scope still filters before the LIMIT.
                        statement += f" AND {table}.rowid BETWEEN ? AND ?"
                        route_params.extend(project_bounds)
                    statement += " ORDER BY rank,p.id LIMIT 96"
                    if not use_stem:
                        # Keep the single-route path to one candidate query.
                        statement = """SELECT p.id,p.rid,p.project_id,p.chapter_id,
                          c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at,hits.rank
                          FROM (""" + statement + """) hits
                          JOIN pages p INDEXED BY pages_recall_metadata ON p.rid=hits.rid
                          JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
                          ORDER BY hits.rank,p.id"""
                    routes.append(self.db.execute(statement, route_params).fetchall() if qt else [])
                # Identical ordered routes add no candidate/ranking information.
                # Keep BM25's score scale so novelty selection does not change
                # merely because the same ranking was observed a second time.
                fuse_routes = use_stem and (
                    len(routes[0]) != len(routes[1]) or
                    any(exact["id"] != stem["id"] for exact, stem in zip(*routes)))
                if fuse_routes:
                    # Scores and ordinal maps are only consulted by fusion.
                    # The common equal-route path needs one copy of each exact
                    # candidate, not a stem copy that is immediately replaced.
                    exact_ranks = {row["id"]: i + 1 for i, row in enumerate(routes[0])}
                    stem_ranks = {row["id"]: i + 1 for i, row in enumerate(routes[1])}
                    exact_scores = {row["id"]: max(0.0, -row["rank"]) for row in routes[0]}
                    stem_scores = {row["id"]: max(0.0, -row["rank"]) for row in routes[1]}
                    exact_scale = max(exact_scores.values(), default=1.0) or 1.0
                    stem_scale = max(stem_scores.values(), default=1.0) or 1.0
                if carry_metadata:
                    rows = _RecallCandidates()
                    rows.metadata = {}
                    for route in reversed(routes) if fuse_routes else routes[:1]:
                        for row in route:
                            identity = row[1]
                            rows[identity] = {"rid": row[0], "id": identity, "rank": row[2]}
                            rows.metadata[identity] = (identity, row[3], row[4], row[5])
                elif fuse_routes:
                    rows = {row["id"]: dict(row) for route in reversed(routes) for row in route}
                else:
                    rows = {row["id"]: dict(row) for row in routes[0]}
                bounded = None
                base_relevance = None
                if (use_stem and rows and strategy == "book" and not coverage and not semantic and not current_query
                        and self.db.row_factory is sqlite3.Row and self.db.text_factory is str
                        and self._directory_tokens is self._ordinary_directory_cache
                        and getattr(self._directory_tokens, "__wrapped__", None) is _ORDINARY_DIRECTORY_TOKENS):
                    pool_size = limit * 4 if current_query or (len(qt) > 1 and limit > 1) else limit
                    if len(rows) > pool_size:
                        base_relevance = ({identity: 2 * exact_scores.get(identity, 0.0) / exact_scale +
                            stem_scores.get(identity, 0.0) / stem_scale for identity in rows}
                            if fuse_routes else {identity: -row["rank"] for identity, row in rows.items()})
                        bounded = self._bounded_candidate_metadata(rows, base_relevance, pool_size)
                if bounded is not None:
                    full_candidate_count = len(rows)
                    rows = bounded
                elif use_stem and rows:
                    # Exact and stem routes commonly overlap. Fetch their
                    # directory metadata once, after both bounded searches.
                    ids = [row["rid"] for row in rows.values()]
                    metadata = self.db.execute("""SELECT p.id,p.project_id,p.chapter_id,
                      c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at
                      FROM pages p INDEXED BY pages_recall_metadata
                      JOIN chapters c ON c.id=p.chapter_id
                      JOIN sessions s ON s.id=p.session_pk WHERE p.rid IN (""" +
                      ",".join("?" for _ in ids) + ")", ids)
                    metadata_columns = tuple(column[0] for column in metadata.description)
                    for row in metadata:
                        # sqlite3.Row's string-key lookup scans its columns.
                        # This query has unique fixed column names, so one
                        # ordered value pass avoids repeated scans and a
                        # temporary dictionary for every candidate.
                        if type(row) is sqlite3.Row:
                            rows[row[0]].update(zip(metadata_columns, row))
                        else:
                            rows[row["id"]].update(dict(row))
                qset = set(qt)
                ranked = NotImplemented
                if (_NATIVE is not None and type(self) is MemoryBook
                        and type(self.db) is sqlite3.Connection
                        and self.db.row_factory is sqlite3.Row and self.db.text_factory is str
                        and self._directory_tokens is self._ordinary_directory_cache
                        and getattr(self._directory_tokens, "__wrapped__", None) is _ORDINARY_DIRECTORY_TOKENS
                        and (type(rows) is dict or (type(rows) is _RecallCandidates
                            and _RecallCandidates.values is dict.values))):
                    fusion = ((exact_scores, exact_scale, stem_scores, stem_scale, exact_ranks, stem_ranks)
                              if fuse_routes else None)
                    # Preserve a replacement made by a directory-token callback:
                    # the original loop looks this attribute up for each new directory.
                    lookup_directory = lambda directory: self._directory_tokens(directory)
                    ranked = _NATIVE.rank_candidates(list(rows.values()), qset, lookup_directory,
                        strategy == "book", base_relevance if bounded is not None else None, fusion)
                if ranked is not NotImplemented:
                    candidates.extend(ranked)
                else:
                    directory_overlaps = {}
                    for row in rows.values():
                        item = row  # already a private dictionary; rows is not reused
                        title_overlap = 0.0
                        if strategy == "book":
                            directory = item["chapter_title"] + " " + item["session_title"]
                            if directory not in directory_overlaps:
                                directory_overlaps[directory] = len(qset & self._directory_tokens(directory)) / len(qset)
                            title_overlap = directory_overlaps[directory]
                        if bounded is not None:
                            relevance = base_relevance[item["id"]]
                        elif fuse_routes:
                            # Retain each route's
                            # relative BM25 margins instead of only its ordinal rank.
                            # Exact relevance retains the predeclared 2:1 preference.
                            # An absent route contributes zero, never a fake score.
                            relevance = (2 * exact_scores.get(item["id"], 0.0) / exact_scale +
                                         stem_scores.get(item["id"], 0.0) / stem_scale)
                        else:
                            relevance = -item["rank"]
                        item["score"] = relevance * (1 + 0.15 * title_overlap if strategy == "book" else 1)
                        candidates.append(item)
                    if fuse_routes:
                        candidates.sort(key=lambda item: (-item["score"], exact_ranks.get(item["id"], 97),
                                                          stem_ranks.get(item["id"], 97), item["id"]))
                    else:
                        candidates.sort(key=lambda item: (-item["score"], item["id"]))
                if strategy == "book" and candidates and (current_query or (len(qt) > 1 and limit > 1)):
                    # Rerank a bounded pool using the FTS body's existing
                    # tokens. Complementary query facets can otherwise be
                    # crowded out by several almost-identical high scores.
                    pool = candidates[:limit * 4]
                    pool_count = len(pool)
                    tail = candidates[pool_count:]
                    if current_query and semantic_model is None:
                        pool, tail = self._current_revision_pool(
                            candidates, pool_count, expression, where, params,
                            {row["id"] for row in routes[0]}, len(routes[0]) < 96,
                            temporal_intent)
                    deferred = []
                    ids = [item["rid"] for item in pool]
                    matched = {row["rowid"]: qset.intersection(row["body"].split())
                               for row in self.db.execute(
                                   "SELECT rowid,body FROM pages_fts WHERE rowid IN (" +
                                   ",".join("?" for _ in ids) + ")", ids)}
                    if current_query:
                        current_matches = matched
                        pool, deferred = _prefer_current_pool(
                            self.db, pool, matched,
                            distinct=limit > 1 and not temporal_intent["preserve_occurrences"],
                            declarations=not temporal_intent["preserve_occurrences"], diagnostics=temporal_intent)
                        pool, deferred = _admit_revision_proposals(pool, deferred, temporal_intent)
                    selected = (_NATIVE.select_novelty(pool, deferred, matched, len(qset), limit)
                                if _NATIVE is not None else NotImplemented)
                    if selected is NotImplemented:
                        chosen, pending = [pool[0]], pool[1:]
                        covered = set(matched[pool[0]["rid"]])
                        while (pending or deferred) and len(chosen) < limit:
                            if not pending:
                                pending, deferred = deferred, []
                            best = max(range(len(pending)), key=lambda i: pending[i]["score"] *
                                       (1 + len(matched[pending[i]["rid"]] - covered) / len(qset)))
                            item = pending.pop(best)
                            chosen.append(item)
                            covered.update(matched[item["rid"]])
                        selected = chosen + pending + deferred
                    if current_query and semantic_model is None:
                        retained = {item["id"] for item in selected}
                        tail = [item for item in tail if item["id"] not in retained]
                    candidates = selected + tail
                facets = (_query_facets(query) if coverage and strategy == "book" and limit > 1 and
                          not current_query and not temporal_intent.get("current_cues") and
                          not temporal_intent.get("historical_cues") else [])
                if candidates and facets:
                    # A whole-query OR score can fill every result slot with
                    # one requested subject. Rank each explicit clause over
                    # the already scoped, bounded candidate union and reserve
                    # its best page after the unchanged first result. No new
                    # sources, generated text, or answer labels enter this path.
                    candidate_ids = [item["rid"] for item in candidates]
                    original_positions = {item["rid"]: i for i, item in enumerate(candidates)}
                    preferred = [candidates[0]]
                    seen = {candidates[0]["rid"]}
                    for facet in facets:
                        clause = " OR ".join('"' + token.replace('"', '""') + '"' for token in facet)
                        clause = f"({clause}) AND body : ({clause})"
                        scores = []
                        for table in (("pages_fts", "pages_stem_fts") if use_stem else ("pages_fts",)):
                            # Unary + keeps SQLite from executing MATCH once
                            # per rowid in the IN-list. FTS scans the clause
                            # once, then applies the identical integer filter.
                            hits = self.db.execute(
                                f"SELECT rowid,bm25({table},2.0,2.0,1.0,0.25) rank FROM {table} "
                                f"WHERE {table} MATCH ? AND +rowid IN (" +
                                ",".join("?" for _ in candidate_ids) + ") ORDER BY rank,rowid LIMIT 96",
                                [clause, *candidate_ids]).fetchall()
                            route = {row["rowid"]: max(0.0, -row["rank"]) for row in hits}
                            scale = max(route.values(), default=1.0) or 1.0
                            scores.append({rid: value / scale for rid, value in route.items()})
                        found = set().union(*(route.keys() for route in scores))
                        if not found:
                            continue
                        leader = max(found, key=lambda rid: (
                            2 * scores[0].get(rid, 0.0) +
                            (scores[1].get(rid, 0.0) if use_stem else 0.0),
                            -original_positions[rid]))
                        if leader not in seen:
                            preferred.append(candidates[original_positions[leader]])
                            seen.add(leader)
                    candidates = preferred + [item for item in candidates if item["rid"] not in seen]
                if semantic_model is not None:
                    candidates = fuse_candidates(candidates, rank_pages(self.db, semantic_model, query, where, params))
                    if current_query and candidates:
                        # Fusion can add new comparable revisions or restore
                        # an old page ahead of a newer one. Apply the same
                        # source-checked preference to the final bounded pool.
                        pool = candidates[:limit * 4]
                        pool_count = len(pool)
                        tail = candidates[pool_count:]
                        if qt:
                            pool, tail = self._current_revision_pool(
                                candidates, pool_count, expression, where, params,
                                {row["id"] for row in routes[0]}, len(routes[0]) < 96,
                                temporal_intent)
                        ids = [item["rid"] for item in pool]
                        matched = {row["rowid"]: qset.intersection(row["body"].split())
                                   for row in self.db.execute(
                                       "SELECT rowid,body FROM pages_fts WHERE rowid IN (" +
                                       ",".join("?" for _ in ids) + ")", ids)}
                        current_matches = matched
                        pool, deferred = _prefer_current_pool(
                            self.db, pool, matched,
                            distinct=limit > 1 and not temporal_intent["preserve_occurrences"],
                            declarations=not temporal_intent["preserve_occurrences"], diagnostics=temporal_intent)
                        pool, deferred = _admit_revision_proposals(pool, deferred, temporal_intent)
                        retained = {item["id"] for item in (*pool, *deferred)}
                        candidates = pool + deferred + [item for item in tail if item["id"] not in retained]
                if candidates:
                    selected_ids = [item["id"] for item in candidates[:limit]]
                    sources = {row["id"]: dict(row) for row in self.db.execute(
                        """SELECT p.id,p.title,p.section_id,p.session_pk,p.content,p.source_refs,
                          pr.name project_name,sec.title section_title FROM pages p
                          JOIN projects pr ON pr.id=p.project_id JOIN sections sec ON sec.id=p.section_id
                          WHERE p.id IN (""" + ",".join("?" for _ in selected_ids) + ")", selected_ids)}
                    for item in candidates[:limit]:
                        item.update(sources[item["id"]])
                    selected_pages = candidates[:limit]
                    allocations = _context_allocations(selected_pages, budget_chars)
                    truncated_ids = [item["rid"] for item, _, allowance in allocations
                                     if allowance < len(item["content"])] if use_stem else []
                    if truncated_ids:
                        # Highlight the normalized indexed body only when an
                        # actual excerpt needs word forms absent from the query.
                        # Full pages need no extra read or term extraction.
                        highlighted = self._highlighted_bodies(expression, truncated_ids)
                        forms = {}
                        for row in highlighted:
                            seen = set(qt)
                            extra = []
                            for match in re.finditer("\x01([^\x01\x02]+)\x02", row["body"]):
                                # FTS can merge adjacent highlighted tokens.
                                for form in match.group(1).split():
                                    if form not in seen:
                                        seen.add(form)
                                        extra.append(form)
                                        if len(extra) == 64:
                                            break
                                if len(extra) == 64:
                                    break
                            if extra:
                                forms[row["rowid"]] = qt + extra
                        for item, _, _ in allocations:
                            if item["rid"] in forms:
                                item["excerpt_terms"] = forms[item["rid"]]
                    if token_counter is not None and budget_tokens:
                        # Supplemental units are parsed in original turns so a
                        # page boundary cannot turn a cut sentence/fence into a
                        # purportedly complete new source unit. Read them under
                        # the same snapshot as ranking and page coordinates.
                        from .token_budget import prepare_source_units, _ORDINARY_PREPARE_SOURCE_UNITS
                        ordinary_prepare = prepare_source_units is _ORDINARY_PREPARE_SOURCE_UNITS
                        if (ordinary_prepare and json.loads is _ORDINARY_JSON_LOADS
                                and self.db.row_factory is sqlite3.Row and self.db.text_factory is str):
                            captured_refs = {}
                        wanted: dict[str, set[int]] = {}
                        refs_by_page = {}
                        for row in selected_pages:
                            raw = row["source_refs"]
                            refs = refs_by_page[row["id"]] = json.loads(raw)
                            if captured_refs is not None and type(raw) is str:
                                captured_refs[row["id"]] = (raw, refs)
                            wanted.setdefault(row["session_pk"], set()).update(
                                ref["turn_index"] for ref in refs)
                        original_turns = self._batch_original_turns(wanted) if ordinary_prepare else None
                        if original_turns is None:
                            original_turns = {}
                            for session_pk, ordinals in wanted.items():
                                ordered = sorted(ordinals)
                                for source in self.db.execute(
                                    "SELECT ordinal,content FROM turns WHERE session_pk=? AND ordinal IN (" +
                                    ",".join("?" for _ in ordered) + ")", [session_pk, *ordered]):
                                    original_turns[(session_pk, source["ordinal"])] = source["content"]
                        source_units_for = prepare_source_units(selected_pages, original_turns, refs_by_page)
                    if current_matches and budget_tokens != 0:
                        # A current correction may share one page with its
                        # obsolete version. Character excerpts still change
                        # only when a complete comparable turn fits. Token
                        # supplements also need this source boundary when the
                        # entire page fits the character budget, or a selected
                        # page was omitted from the character allocations.
                        proposed = {}
                        char_allowances = {row["id"]: allowance for row, _, allowance in allocations}
                        current_pages = (selected_pages if source_units_for is not None
                                         else [row for row, _, _ in allocations])
                        excerpt_candidates = []
                        known_turns = dict(original_turns) if original_turns is not None else {}
                        wanted = {}
                        for row in current_pages:
                            match_set = current_matches.get(row["rid"])
                            allowance = char_allowances.get(row["id"])
                            if (not match_set or (source_units_for is None
                                                  and allowance >= len(row["content"]))):
                                continue
                            refs = (refs_by_page[row["id"]] if refs_by_page is not None
                                    else json.loads(row["source_refs"]))
                            excerpt_candidates.append((row, refs, match_set, allowance))
                            for ref in _matching_turn_refs(row["content"], refs, match_set):
                                if (row["session_pk"], ref["turn_index"]) not in known_turns:
                                    wanted.setdefault(row["session_pk"], set()).add(ref["turn_index"])
                        extra_turns = self._batch_original_turns(wanted) if wanted else {}
                        if extra_turns is None:
                            extra_turns = {}
                            for session_pk, ordinals in wanted.items():
                                ordered = sorted(ordinals)
                                for source in self.db.execute(
                                        "SELECT ordinal,content FROM turns WHERE session_pk=? AND ordinal IN (" +
                                        ",".join("?" for _ in ordered) + ")", [session_pk, *ordered]):
                                    extra_turns[(session_pk, source["ordinal"])] = source["content"]
                        known_turns.update(extra_turns)
                        for row, refs, match_set, allowance in excerpt_candidates:
                            originals = {ref["turn_index"]: known_turns.get((row["session_pk"], ref["turn_index"]))
                                         for ref in _matching_turn_refs(row["content"], refs, match_set)}
                            ref = _current_excerpt_ref(row["content"], refs, match_set,
                                                       None if source_units_for is not None else allowance,
                                                       original_turns=originals)
                            if ref is not None:
                                proposed[row["id"]] = (row, ref)
                        for identity, (row, ref) in proposed.items():
                            key = (row["session_pk"], ref["turn_index"])
                            original = known_turns.get(key)
                            start, end = ref["start"], ref["end"]
                            if (isinstance(original, str) and ref["turn_end"] == len(original)
                                    and row["content"][start:end] == original):
                                current_unit_spans[identity] = (start, end)
                                allowance = char_allowances.get(identity)
                                if (allowance is not None and allowance < len(row["content"])
                                        and end - start + bool(start) + (end < len(row["content"])) <= allowance):
                                    current_spans[identity] = (start, end)
                        if source_units_for is not None and current_unit_spans:
                            ordinary_units_for = source_units_for

                            def source_units_for(row):
                                units = ordinary_units_for(row)
                                span = current_unit_spans.get(row["id"])
                                if span is None:
                                    return units
                                # If the full current turn exceeds the token
                                # cap, only intact units of that turn may fill
                                # the gap. Never reselect an obsolete turn.
                                lo, hi = span
                                return [(start, end) for start, end in units if lo <= start < end <= hi]
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        # Exact-token first-fit must start from the same character-only
        # evidence blocks exposed by this request. Otherwise a completed short
        # record can disappear or change its source metadata merely because a
        # token cap was supplied, even when that whole block fits the cap.
        # Protect authenticated current turns in both routes before assembling
        # the shared legacy blocks; token supplements retain their own policy.
        from .context_budget import complete_short_pages
        allocations = complete_short_pages(
            allocations, protected_ids=frozenset(current_spans))
        legacy = []
        for row, header, allowance in allocations:
            if row["id"] in current_spans:
                start, end = current_spans[row["id"]]
                text = (("…" if start else "") + row["content"][start:end]
                        + ("…" if end < len(row["content"]) else ""))
                spans = [(start, end)]
            else:
                text, spans = excerpt(row["content"], query, allowance, prepared_terms=row.get("excerpt_terms", qt))
            legacy.append((row, header, text, spans))
        assembled = legacy
        if token_counter is not None:
            from .token_budget import assemble_with_count
            assembled, context_tokens = assemble_with_count(
                legacy, selected_pages, qt, budget_chars=budget_chars,
                budget_tokens=budget_tokens, counter=token_counter,
                source_units_for=source_units_for)
        results, blocks = [], []
        # Limit the work/response, but do not force one task/chapter branch.
        for row, header, text, spans in assembled:
            crumbs = self._breadcrumb(row)
            # The address and date are sufficient for agent recall. Display
            # names remain in breadcrumb metadata and exact read_page results;
            # repeating three long titles in every context block crowds out
            # evidence at small budgets without adding source identity.
            block = header + text
            reference_method = self._refs
            captured = None
            if (reference_method is _ORDINARY_REFS and captured_refs is not None and type(row) is dict
                    and type(row.get("id")) is str
                    and json.loads is _ORDINARY_JSON_LOADS
                    and type(spans) in (tuple, list) and len(spans) == 1
                    and all(type(span) in (tuple, list) and len(span) == 2
                            and all(type(value) is int for value in span) for span in spans)):
                captured = captured_refs.get(row.get("id"))
                if captured is not None and row.get("source_refs") is not captured[0]:
                    captured = None
            if captured is not None:
                # A fresh JSON parse per span previously kept nested fields
                # such as message_indices independent. Expose this captured
                # object graph only once; multiple spans or a repeated page
                # retain the original per-span parsing path.
                captured_refs.pop(row["id"])
                refs = _refs_from_parsed(captured[1], spans)
            else:
                refs = reference_method(row, spans)
            coverage = len(set(qt) & set(terms(text, query=True))) / len(qt) if qt else 0.0
            results.append({"id": row["id"], "title": row["title"], "text": text, "source_refs": refs, "breadcrumb": crumbs, "score": row["score"], "lexical_coverage": coverage, "created_at": row["created_at"], "truncated": len(text) < len(row["content"]), "page_chars": len(row["content"]), "excerpt_spans": [[a, b] for a, b in spans]})
            blocks.append(block)
        context = "\n\n".join(blocks)
        warnings = []
        if project is None and len({r["breadcrumb"][0]["id"] for r in results}) > 1:
            warnings.append("Results span projects; supply project to disambiguate.")
        if results and (current_query or temporal_intent.get("current_cues")):
            warnings.append("Historical evidence can conflict. Check source timestamps; retrieval does not resolve which decision is authoritative.")
        if temporal_intent["basis"] == "mixed_temporal_cues":
            warnings.append("Current and historical cues are both present; auto kept relevance ordering. Use temporal=current only when the current state is intended; relevance is not an as-of state resolver.")
        if not results and candidates:
            warnings.append("Budget too small to return an evidence block including its citation.")
        candidate_count = len(candidates) if full_candidate_count is None else full_candidate_count
        result = {"query": query, "results": results, "context": context, "context_chars": len(context), "estimated_tokens": estimate_tokens(context), "candidate_count": candidate_count, "revision": revision, "cache_hit": False, "warnings": warnings, "strategy": strategy, "budget_chars": budget_chars, "temporal": temporal_intent, "truncated": candidate_count > len(results) or any(r["truncated"] for r in results)}
        if semantic_model is not None:
            result.update(semantic=True, semantic_model_fingerprint=semantic_model.fingerprint)
        if token_counter is not None:
            result.update(budget_tokens=budget_tokens, tokenizer=tokenizer,
                          tokenizer_version=token_counter.version,
                          context_tokens=context_tokens)
        if use_cache and self.cache_size:
            # A concurrent ingestion must not be overwritten by an old cache.
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if self.revision == revision:
                    self.db.execute("INSERT OR REPLACE INTO recall_cache VALUES(?,?,?,?)", (cache_key, revision, _json(result), time.time_ns()))
                    self.db.execute("DELETE FROM recall_cache WHERE key IN (SELECT key FROM recall_cache ORDER BY touched_ns DESC LIMIT -1 OFFSET ?)", (self.cache_size,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        result["latency_ms"] = (time.perf_counter_ns() - started) / 1e6
        return result


_ORDINARY_REFS = MemoryBook._refs
_ORDINARY_SECTION = MemoryBook.section
