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

FORMATS = ("auto", "canonical", "chatgpt", "claude-code", "codex", "gemini", "kimi-legacy")
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


def _default_id(path: Path, value: Any, fallback_id: str | None = None) -> str:
    if fallback_id is not None:
        return _nonempty(fallback_id, "fallback_id")
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
    fallback_id: str | None = None,
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
            _default_id(path, record, fallback_id) if session_id is None else session_id, "session_id"
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
    data: Any, path: Path, project: str | None, task_id: str | None,
    fallback_id: str | None = None,
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
        stable = f"{fallback_id}:{index}" if fallback_id and len(records) > 1 else fallback_id
        sessions.append(_finish(record, messages, path, project, task_id, stable))
    return sessions


def _chatgpt(
    data: Any, path: Path, project: str | None, task_id: str | None,
    fallback_id: str | None = None,
) -> list[dict[str, Any]]:
    records = data if isinstance(data, list) else [data]
    if not records:
        raise ValueError("ChatGPT export has no conversations")
    sessions = []
    for index, record in enumerate(records):
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
            "session_id": record.get("id") or record.get("conversation_id") or _default_id(
                path, record, f"{fallback_id}:{index}" if fallback_id and len(records) > 1 else fallback_id),
            "title": record.get("title") or None,
            "created_at": record.get("create_time"),
        }
        sessions.append(_finish(canonical, messages, path, project, task_id))
    return sessions


def _native(
    records: Any, kind: str, path: Path, project: str | None, task_id: str | None,
    fallback_id: str | None = None,
) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ValueError(f"{kind} requires non-empty JSONL records")
    fallback = _default_id(path, records, fallback_id)
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
    records = data if isinstance(data, list) else [data]
    if any(isinstance(item, dict) and isinstance(item.get("role"), str)
           and item["role"] in {"_system_prompt", "_usage", "_checkpoint"} for item in records):
        return "kimi-legacy"
    if any(isinstance(item, dict) and isinstance(item.get("sessionId"), str)
           and (isinstance(item.get("projectHash"), str) or isinstance(item.get("messages"), list))
           and "message" not in item for item in records):
        return "gemini"
    if isinstance(data, dict) and ("sessions" in data or "messages" in data):
        return "canonical"
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
    raise ValueError("Unsupported transcript format; expected canonical, chatgpt, claude-code, codex, gemini, or kimi-legacy")


def _kimi_legacy(data: Any, path: Path, project: str | None, task_id: str | None,
                 fallback_id: str | None = None) -> list[dict[str, Any]]:
    """Read archived Python Kimi's active context.jsonl, not current Kimi Code.

    Verified public schema: MoonshotAI/kimi-cli src/kimi_cli/soul/context.py
    and packages/kosong/src/kosong/message.py. Only known text parts are retained;
    bookkeeping, private thinking parts, multimodal bytes and tool calls are not.
    """
    records = data if isinstance(data, list) else [data]
    messages = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Kimi legacy records must be objects")
        role = record.get("role")
        if role in ("_system_prompt", "_usage", "_checkpoint"):
            continue
        if not isinstance(role, str) or role not in ROLES:
            raise ValueError("Kimi legacy record has an unsupported role")
        body = _text(record.get("content"))
        if body.strip():
            messages.append({"role": role, "content": body})
    session_id = (path.parent.name if path.name == "context.jsonl" and path.parent.name
                  else _default_id(path, data, fallback_id))
    return [_finish({"session_id": session_id}, messages, path, project, task_id, fallback_id)]


def _gemini_document(data: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replay Gemini's documented JSONL updates before extracting text.

    Independently implemented from the public record schema and accumulator
    semantics at google-gemini/gemini-cli, chatRecordingTypes.ts and
    chatRecordingService.ts (verified source SHA
    3c9ecd4c4d542f5e50e7f3368d4fd4c157910676 for the service).
    Unlike a permissive client resume loader, malformed complete JSONL lines
    are rejected by our strict parser rather than silently discarded.
    """
    records = data if isinstance(data, list) else [data]
    metadata: dict[str, Any] = {}
    messages: dict[str, dict[str, Any]] = {}

    def add_message(message: Any) -> None:
        if not isinstance(message, dict) or not isinstance(message.get("id"), str):
            raise ValueError("Gemini messages require a string id")
        messages[message["id"]] = dict(message)

    def apply_patch(patch: Any) -> None:
        if not isinstance(patch, dict):
            raise ValueError("Gemini message patch must be an object")
        message_id = patch.get("id")
        if isinstance(message_id, str) and message_id in messages and "content" in patch:
            messages[message_id]["content"] = patch["content"]
        # Tool results are deliberately not imported as conversation text.

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Gemini records must be objects")
        if "$rewindTo" in record:
            target = record["$rewindTo"]
            if not isinstance(target, str):
                raise ValueError("Gemini rewind target must be a string")
            ids = list(messages)
            if target not in messages:
                messages.clear()
            else:
                for message_id in ids[ids.index(target):]:
                    del messages[message_id]
        elif "$patch" in record:
            patch = record["$patch"]
            apply_patch(patch)
            updates = patch.get("updates", [])
            removals = patch.get("removeIds", [])
            if not isinstance(updates, list) or not isinstance(removals, list):
                raise ValueError("Gemini patch updates and removeIds must be arrays")
            for update in updates:
                apply_patch(update)
            for message_id in removals:
                if isinstance(message_id, str):
                    messages.pop(message_id, None)
            if "orderIds" in patch:
                ordering = patch["orderIds"]
                if not isinstance(ordering, list):
                    raise ValueError("Gemini patch orderIds must be an array")
                ordered = {message_id: messages[message_id] for message_id in ordering
                           if isinstance(message_id, str) and message_id in messages}
                messages = {**{key: value for key, value in messages.items() if key not in ordered}, **ordered}
        elif "$set" in record:
            update = record["$set"]
            if not isinstance(update, dict):
                raise ValueError("Gemini metadata update must be an object")
            if "messages" in update:
                if not isinstance(update["messages"], list):
                    raise ValueError("Gemini metadata messages must be an array")
                messages.clear()
                for message in update["messages"]:
                    add_message(message)
            metadata.update(update)
        elif isinstance(record.get("id"), str):
            add_message(record)
        elif isinstance(record.get("sessionId"), str):
            metadata.update(record)
            if "messages" in record:
                if not isinstance(record["messages"], list):
                    raise ValueError("Gemini messages must be an array")
                for message in record["messages"]:
                    add_message(message)
        else:
            raise ValueError("Unrecognized Gemini transcript record")
    if not isinstance(metadata.get("sessionId"), str):
        raise ValueError("Gemini transcript requires sessionId metadata")
    return metadata, list(messages.values())


def _gemini_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = content if isinstance(content, list) else [content]
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought"):
            texts.append(part["text"])
    return "\n".join(texts)


def _gemini(data: Any, path: Path, project: str | None, task_id: str | None,
            fallback_id: str | None = None) -> list[dict[str, Any]]:
    metadata, records = _gemini_document(data)
    messages = []
    for record in records:
        kind = record.get("type")
        role = {"user": "user", "gemini": "assistant"}.get(kind) if isinstance(kind, str) else None
        body = _gemini_text(record.get("content"))
        if role and body.strip():
            messages.append({"role": role, "content": body})
    summary = metadata.get("summary")
    canonical = {"session_id": metadata.get("sessionId"), "created_at": metadata.get("startTime")}
    if isinstance(summary, str) and summary.strip():
        canonical["title"] = summary.strip()[:200]
    return [_finish(canonical, messages, path, project, task_id, fallback_id)]


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
    return parse_sessions(text, source_path=path, format=format, project=project, task_id=task_id)


def _parse_document(text: str) -> Any:
    if not isinstance(text, str):
        raise ValueError("Transcript must be text")
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
    return data


def transcript_info(text: str, format: str = "auto") -> dict[str, Any]:
    """Inspect recognized source metadata without guessing a default project.

    This function reads only its supplied text. It never opens a client's data
    directory, environment, or sidecar configuration.
    """
    if format not in FORMATS:
        raise ValueError(f"Unknown import format; choose one of: {', '.join(FORMATS)}")
    data = _parse_document(text)
    kind = _detect(data) if format == "auto" else format
    if kind == "gemini":
        metadata, _ = _gemini_document(data)
        directories = metadata.get("directories", [])
        return {"format": kind,
                "workspaces": [value for value in directories if isinstance(value, str)]
                              if isinstance(directories, list) else [],
                "projects": [],
                "project_hashes": [metadata["projectHash"]]
                                  if isinstance(metadata.get("projectHash"), str) else []}
    records = data if isinstance(data, list) else [data]
    if kind == "canonical" and isinstance(data, dict) and "sessions" in data:
        records = data["sessions"]
    workspaces: set[str] = set()
    projects: set[str] = set()
    project_hashes: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        cwd = record.get("cwd")
        if kind == "codex" and record.get("type") == "session_meta":
            payload = record.get("payload")
            if isinstance(payload, dict):
                cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            workspaces.add(cwd)
        if kind == "canonical" and isinstance(record.get("project"), str):
            projects.add(record["project"])
        if isinstance(record.get("projectHash"), str):
            project_hashes.add(record["projectHash"])
    return {"format": kind, "workspaces": sorted(workspaces),
            "projects": sorted(projects), "project_hashes": sorted(project_hashes)}


def parse_sessions(
    text: str,
    source_path: str | Path,
    format: str = "auto",
    project: str | None = None,
    task_id: str | None = None,
    *,
    fallback_id: str | None = None,
) -> list[dict[str, Any]]:
    """Parse supplied transcript text, with no filesystem or database access.

    ``fallback_id`` is an optional stable source identity for incremental
    watchers. Native session identifiers still take precedence. Without this
    option, one-shot imports retain their historical content-derived fallback.
    A caller must bound the text and explicitly handle incomplete writes before
    calling this strict parser.
    """
    if format not in FORMATS:
        raise ValueError(f"Unknown import format; choose one of: {', '.join(FORMATS)}")
    if project is not None:
        _nonempty(project, "project")
    if task_id is not None:
        _nonempty(task_id, "task_id")
    if fallback_id is not None:
        _nonempty(fallback_id, "fallback_id")
    data = _parse_document(text)
    kind = _detect(data) if format == "auto" else format
    path = Path(source_path)
    if kind == "canonical":
        return _canonical(data, path, project, task_id, fallback_id)
    if kind == "chatgpt":
        return _chatgpt(data, path, project, task_id, fallback_id)
    if kind == "gemini":
        return _gemini(data, path, project, task_id, fallback_id)
    if kind == "kimi-legacy":
        return _kimi_legacy(data, path, project, task_id, fallback_id)
    return _native(data, kind, path, project, task_id, fallback_id)
