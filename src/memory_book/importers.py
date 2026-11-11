"""Explicit, text-only transcript importers.

Supported formats are canonical JSON, ChatGPT's exported current branch, Claude
Code JSONL, and Codex rollout JSONL. Imports read only the requested file. Image,
audio, tool-call, and tool-result blocks are not decoded; these importers do not
claim to reconstruct a vendor's entire execution history.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORMATS = ("auto", "canonical", "chatgpt", "claude-code", "codex")
ROLES = frozenset(("user", "assistant", "system", "developer", "tool"))
MAX_IMPORT_BYTES = 64 * 1024 * 1024


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            raise ValueError("Invalid transcript timestamp") from None
    raise ValueError("Transcript timestamp must be a string or Unix timestamp")


def _text(content: Any) -> str:
    """Read known text blocks only; never stringify arbitrary objects."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    pieces = []
    for part in content:
        if isinstance(part, str):
            pieces.append(part)
        elif isinstance(part, dict):
            kind = part.get("type", part.get("content_type"))
            if kind in ("text", "input_text", "output_text"):
                value = part.get("text")
                if isinstance(value, str):
                    pieces.append(value)
    return "\n".join(pieces)


def _default_id(path: Path, value: Any) -> str:
    digest = hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"{path.stem[:80] or 'session'}-{digest}"


def _title(messages: list[dict[str, str]], fallback: str) -> str:
    for message in messages:
        if message["role"] == "user":
            return " ".join(message["content"].split())[:120] or fallback
    return fallback


def _finish(
    record: dict[str, Any],
    messages: list[dict[str, str]],
    path: Path,
    project: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    if not messages:
        raise ValueError("Transcript contains no supported textual messages")
    chosen_project = project if project is not None else record.get("project")
    if chosen_project is None:
        raise ValueError("Project is missing; pass project= or --project explicitly")
    session_id = record.get("session_id")
    title = record.get("title")
    result: dict[str, Any] = {
        "project": _nonempty(chosen_project, "project"),
        "session_id": _nonempty(
            _default_id(path, record) if session_id is None else session_id, "session_id"
        ),
        "title": _nonempty(_title(messages, path.stem) if title is None else title, "title"),
        "messages": messages,
    }
    if record.get("project_name") is not None:
        result["project_name"] = _nonempty(record["project_name"], "project_name")
    chosen_task = task_id if task_id is not None else record.get("task_id")
    # The canonical exporter uses an empty task_id for an ungrouped session.
    # Explicit caller overrides are validated separately and cannot be empty.
    if chosen_task is not None and chosen_task != "":
        result["task_id"] = _nonempty(chosen_task, "task_id")
    if record.get("task_title") not in (None, ""):
        result["task_title"] = _nonempty(record["task_title"], "task_title")
    created = _timestamp(record.get("created_at"))
    if created is not None:
        result["created_at"] = created
    return result


def _canonical(
    data: Any, path: Path, project: str | None, task_id: str | None
) -> list[dict[str, Any]]:
    records = data.get("sessions") if isinstance(data, dict) and "sessions" in data else data
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ValueError("Canonical JSON must contain a session or a non-empty sessions list")
    sessions = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("messages"), list):
            raise ValueError(f"Session {index + 1}: messages must be an array")
        messages = []
        for position, message in enumerate(record["messages"]):
            if (
                not isinstance(message, dict)
                or not isinstance(message.get("role"), str)
                or message["role"] not in ROLES
            ):
                raise ValueError(f"Session {index + 1}, message {position + 1}: unsupported role")
            if not isinstance(message.get("content"), str):
                raise ValueError(f"Session {index + 1}, message {position + 1}: content must be text")
            if message["content"].strip():
                messages.append({"role": message["role"], "content": message["content"]})
        sessions.append(_finish(record, messages, path, project, task_id))
    return sessions


def _chatgpt(
    data: Any, path: Path, project: str | None, task_id: str | None
) -> list[dict[str, Any]]:
    records = data if isinstance(data, list) else [data]
    if not records:
        raise ValueError("ChatGPT export has no conversations")
    sessions = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("mapping"), dict):
            raise ValueError("ChatGPT conversation requires a mapping object")
        mapping = record["mapping"]
        current = record.get("current_node")
        if not isinstance(current, str) or current not in mapping:
            raise ValueError("ChatGPT export requires a valid current_node; branch guessing is disabled")
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        while current is not None:
            if not isinstance(current, str) or current not in mapping:
                raise ValueError("ChatGPT current branch contains a missing parent")
            if current in seen:
                raise ValueError("ChatGPT current branch contains a cycle")
            seen.add(current)
            node = mapping[current]
            if not isinstance(node, dict):
                raise ValueError("ChatGPT mapping node must be an object")
            chain.append(node)
            current = node.get("parent")
        messages = []
        for node in reversed(chain):
            message = node.get("message")
            if not isinstance(message, dict):
                continue
            author = message.get("author")
            role = author.get("role") if isinstance(author, dict) else None
            content = message.get("content")
            body = _text(content.get("parts")) if isinstance(content, dict) else ""
            if isinstance(role, str) and role in ROLES and body.strip():
                messages.append({"role": role, "content": body})
        canonical = {
            "project": record.get("project"),
            "session_id": record.get("id") or record.get("conversation_id") or _default_id(path, record),
            "title": record.get("title") or None,
            "created_at": record.get("create_time"),
        }
        sessions.append(_finish(canonical, messages, path, project, task_id))
    return sessions


def _native(
    records: Any, kind: str, path: Path, project: str | None, task_id: str | None
) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ValueError(f"{kind} requires non-empty JSONL records")
    fallback = _default_id(path, records)
    current_id = fallback
    groups: dict[str, dict[str, Any]] = {}

    def group(session_id: str, timestamp: Any) -> dict[str, Any]:
        if session_id not in groups:
            groups[session_id] = {"session_id": session_id, "created_at": timestamp, "messages": []}
        return groups[session_id]

    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{kind} records must be objects")
        timestamp = record.get("timestamp")
        if kind == "codex":
            payload = record.get("payload")
            if record.get("type") == "session_meta" and isinstance(payload, dict):
                current_id = _nonempty(payload.get("id") or fallback, "session id")
                group(current_id, timestamp)
                continue
            # event_msg mirrors response_item in rollout logs; consuming both duplicates turns.
            if record.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            message = payload
            session_id = current_id
        else:
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            session_id = _nonempty(record.get("sessionId") or fallback, "session id")
        role = message.get("role")
        body = _text(message.get("content"))
        if isinstance(role, str) and role in ROLES and body.strip():
            group(session_id, timestamp)["messages"].append({"role": role, "content": body})
    sessions = [
        _finish(record, record["messages"], path, project, task_id)
        for record in groups.values()
        if record["messages"]
    ]
    if not sessions:
        raise ValueError(f"{kind} transcript contains no supported textual messages")
    return sessions


def _detect(data: Any) -> str:
    if isinstance(data, dict) and ("sessions" in data or "messages" in data):
        return "canonical"
    records = data if isinstance(data, list) else [data]
    if records and all(isinstance(item, dict) and "mapping" in item for item in records):
        return "chatgpt"
    if records and all(isinstance(item, dict) and "messages" in item for item in records):
        return "canonical"
    if any(isinstance(item, dict) and item.get("type") in ("session_meta", "response_item") for item in records):
        return "codex"
    if any(
        isinstance(item, dict)
        and isinstance(item.get("message"), dict)
        and ("sessionId" in item or item.get("type") in ("user", "assistant"))
        for item in records
    ):
        return "claude-code"
    raise ValueError("Unsupported transcript format; expected canonical, chatgpt, claude-code, or codex")


def load_sessions(
    path: str | Path,
    format: str = "auto",
    project: str | None = None,
    task_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load one explicitly selected transcript file into canonical sessions.

    ``project`` and ``task_id`` override source values when supplied. Vendor
    formats need an explicit project. ChatGPT imports only ``current_node``'s
    ancestor chain, never discarded branches. Claude Code and Codex imports
    retain recognized text messages, not binary content or complete tool logs.
    Missing native session IDs use a filename/content-derived identifier; edited
    files without stable IDs therefore represent a new snapshot.

    Empty, malformed, and unrecognized files raise ``ValueError``. All sessions
    are validated before this function returns; it performs no database writes.
    """
    if format not in FORMATS:
        raise ValueError(f"Unknown import format; choose one of: {', '.join(FORMATS)}")
    if project is not None:
        _nonempty(project, "project")
    if task_id is not None:
        _nonempty(task_id, "task_id")
    path = Path(path)
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError("Transcript exceeds the 64 MiB per-file import limit")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Transcript must be UTF-8 JSON or JSONL") from None
    if not text.strip():
        raise ValueError("Transcript file is empty")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                raise ValueError(f"Malformed JSON/JSONL at line {line_number}") from None
    kind = _detect(data) if format == "auto" else format
    if kind == "canonical":
        return _canonical(data, path, project, task_id)
    if kind == "chatgpt":
        return _chatgpt(data, path, project, task_id)
    return _native(data, kind, path, project, task_id)
