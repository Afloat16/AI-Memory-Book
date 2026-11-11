"""Explicit, incremental local transcript capture with a quiet polling worker.

Only configured source directories are walked. No client history is discovered
or read merely by importing this module or creating a configuration. Source
removal never deletes an archived session. The manifest and optional JSONL log
contain file metadata, counters and error codes, never conversation text.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import ntpath
import os
import posixpath
import re
import signal
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterator

from .importers import FORMATS, MAX_IMPORT_BYTES, parse_sessions, transcript_info
from .store import MemoryBook, normalize_session


CONFIG_VERSION = 1
STATE_VERSION = 1
STATE_APPLICATION = "ai-memory-book-sync"
MAX_STATE_BYTES = 32 * 1024 * 1024
MAX_FILES_PER_SOURCE = 100_000
LOG_ROTATE_BYTES = 1024 * 1024
EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    "subagents", "tool-results", "tool_outputs", "attachments",
})
EXCLUDED_NAMES = frozenset({
    "auth.json", "credentials.json", "secrets.json", "settings.json", "config.json",
    "package.json", "package-lock.json", "manifest.json", "session_index.jsonl",
    "history.json", "history.jsonl", "logs.json", "logs.jsonl",
})
DEFAULT_PATTERNS = {
    "claude-code": ("*.jsonl",),
    "codex": ("rollout-*.jsonl",),
    "gemini": ("session-*.json", "session-*.jsonl"),
    "kimi-legacy": ("context.jsonl",),
    "canonical": ("*.json", "*.jsonl"),
    "chatgpt": ("*.json",),
    "auto": ("*.json", "*.jsonl"),
}


def _absolute(value: str | Path, base: Path | None = None) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError("A nonempty filesystem path is required")
    path = Path(value).expanduser()
    return Path(os.path.abspath(path if path.is_absolute() else (base or Path.cwd()) / path))


def _string(value: Any, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{name} must be a nonempty string of at most {maximum} characters")
    return value.strip()


def _workspace_key(value: str) -> str:
    """Normalize declared paths without opening or resolving their directories."""
    value = _string(value, "workspace", 4096)
    value = os.path.expanduser(value)
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"):
        return ntpath.normcase(ntpath.normpath(value))
    if not value.startswith("/"):
        raise ValueError("workspace metadata must use an absolute path")
    return str(PurePosixPath(posixpath.normpath(value)))


def _slug(value: str) -> str:
    return re.sub(r"[^\w.-]+", "-", value.casefold()).strip(".-_")[:64] or "project"


def project_for_workspace(workspace: str, prefix: str | None = None) -> str:
    """Stable readable project identity, including a hash to separate namesakes."""
    key = _workspace_key(workspace)
    name = PureWindowsPath(key).name if "\\" in key else PurePosixPath(key).name
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{_slug(prefix) + '-' if prefix else ''}{_slug(name)}-{digest}"


@dataclass(frozen=True)
class WatchSource:
    id: str
    path: Path
    format: str = "auto"
    project: str | None = None
    project_mode: str = "metadata"
    project_prefix: str | None = None
    task_id: str | None = None
    patterns: tuple[str, ...] = ()
    recursive: bool = True
    workspace: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _string(self.id, "source id", 100))
        object.__setattr__(self, "path", _absolute(self.path))
        if self.format not in FORMATS:
            raise ValueError("unsupported source format")
        if self.project_mode not in {"metadata", "subdirectory", "explicit"}:
            raise ValueError("project_mode must be metadata, subdirectory, or explicit")
        for name in ("project", "project_prefix", "task_id"):
            value = getattr(self, name)
            if value is not None:
                _string(value, name, 200 if name == "project" else 100)
        if self.project_mode == "explicit" and self.project is None:
            raise ValueError("explicit project_mode requires project")
        if not isinstance(self.recursive, bool):
            raise ValueError("recursive must be a boolean")
        if not isinstance(self.patterns, (tuple, list)):
            raise ValueError("patterns must be an array")
        patterns = tuple(_string(pattern, "pattern", 200) for pattern in self.patterns)
        if any("/" in pattern or "\\" in pattern or pattern.startswith(".") for pattern in patterns):
            raise ValueError("patterns match filenames only, without directory separators or hidden files")
        object.__setattr__(self, "patterns", patterns)
        if self.workspace is not None:
            object.__setattr__(self, "workspace", _workspace_key(self.workspace))


@dataclass(frozen=True)
class SyncConfig:
    database: Path
    state_path: Path
    log_path: Path | None = None
    poll_interval: float = 5.0
    sources: tuple[WatchSource, ...] = ()
    max_file_bytes: int = MAX_IMPORT_BYTES
    reader_enabled: bool = False
    reader_host: str = "127.0.0.1"
    reader_port: int = 8765

    def __post_init__(self) -> None:
        for name in ("database", "state_path", "log_path"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _absolute(value))
        if (isinstance(self.poll_interval, bool) or not isinstance(self.poll_interval, (int, float))
                or not math.isfinite(self.poll_interval) or not 0.05 <= self.poll_interval <= 3600):
            raise ValueError("poll_interval must be between 0.05 and 3600 seconds")
        if (isinstance(self.max_file_bytes, bool) or not isinstance(self.max_file_bytes, int)
                or not 128 <= self.max_file_bytes <= MAX_IMPORT_BYTES):
            raise ValueError("max_file_bytes must be between 128 and 64 MiB")
        sources = tuple(self.sources)
        if not all(isinstance(source, WatchSource) for source in sources):
            raise ValueError("sources must contain WatchSource objects")
        if len({source.id for source in sources}) != len(sources):
            raise ValueError("source ids must be unique")
        object.__setattr__(self, "sources", sources)
        if not isinstance(self.reader_enabled, bool):
            raise ValueError("reader_enabled must be a boolean")
        if self.reader_host not in {"127.0.0.1", "::1", "localhost", "0.0.0.0"}:
            raise ValueError("unsupported reader bind address")
        if isinstance(self.reader_port, bool) or not isinstance(self.reader_port, int) or not 0 <= self.reader_port <= 65535:
            raise ValueError("reader_port must be between 0 and 65535")
        protected = {self.database, *(Path(str(self.database) + suffix) for suffix in ("-wal", "-shm", "-journal"))}
        if self.state_path in protected or self.log_path in protected or self.log_path == self.state_path:
            raise ValueError("database, state, and log paths must be distinct")
        artifacts = [self.database, self.state_path, *( [self.log_path] if self.log_path is not None else [])]
        for index, left in enumerate(artifacts):
            for right in artifacts[index + 1:]:
                if left.resolve() == right.resolve() or (left.exists() and right.exists() and left.samefile(right)):
                    raise ValueError("database, state, and log paths must not alias the same file")


def _config_dict(config: SyncConfig) -> dict[str, Any]:
    value = asdict(config)
    value["version"] = CONFIG_VERSION
    for field in ("database", "state_path", "log_path"):
        value[field] = str(value[field]) if value[field] is not None else None
    for source in value["sources"]:
        source["path"] = str(source["path"])
        source["patterns"] = list(source["patterns"])
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("refusing to replace a symlink with sync metadata")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def save_config(config: SyncConfig, path: str | Path) -> Path:
    """Save explicit settings atomically; no source files are opened."""
    path = _absolute(path)
    if path in {config.database, config.state_path, config.log_path}:
        raise ValueError("config path must not overwrite database, state, or log")
    _atomic_json(path, _config_dict(config))
    return path


def load_config(path: str | Path) -> SyncConfig:
    path = _absolute(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("sync configuration exceeds 1 MiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("sync configuration must be UTF-8 JSON") from None
    if not isinstance(value, dict) or value.get("version", 1) != CONFIG_VERSION:
        raise ValueError("unsupported sync configuration version")
    allowed = set(SyncConfig.__dataclass_fields__) | {"version", "reader"}
    if set(value) - allowed:
        raise ValueError("unknown sync configuration field")
    sources = value.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources must be an array")
    parsed = []
    for source in sources:
        if not isinstance(source, dict) or set(source) - set(WatchSource.__dataclass_fields__):
            raise ValueError("invalid source configuration fields")
        source = dict(source)
        source["path"] = _absolute(source.get("path", ""), path.parent)
        if source.get("workspace") is not None and not isinstance(source["workspace"], str):
            raise ValueError("workspace must be a string")
        if source.get("workspace") and not re.match(r"^(?:/|[A-Za-z]:[\\/]|\\\\)", source["workspace"]):
            source["workspace"] = str(_absolute(source["workspace"], path.parent))
        try:
            parsed.append(WatchSource(**source))
        except TypeError:
            raise ValueError("each source requires id and path") from None
    reader = value.get("reader", {})
    if not isinstance(reader, dict) or set(reader) - {"enabled", "host", "port"}:
        raise ValueError("invalid reader configuration")
    options = {key: val for key, val in value.items() if key in SyncConfig.__dataclass_fields__}
    for key, default in (("database", None), ("state_path", None), ("log_path", None)):
        val = options.get(key, default)
        if val is None and key != "log_path":
            raise ValueError(f"sync configuration requires {key}")
        options[key] = _absolute(val, path.parent) if val is not None else None
    for key in ("enabled", "host", "port"):
        if key in reader and "reader_" + key not in options:
            options["reader_" + key] = reader[key]
    options["sources"] = tuple(parsed)
    return SyncConfig(**options)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _empty_state() -> dict[str, Any]:
    return {"application": STATE_APPLICATION, "version": STATE_VERSION,
            "files": {}, "worker": {"running": False}}


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    if path.is_symlink() or path.stat().st_size > MAX_STATE_BYTES:
        raise ValueError("invalid sync state path or size")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("sync state is corrupt; preserve it and choose a new state_path") from None
    if (not isinstance(value, dict) or value.get("application") != STATE_APPLICATION
            or value.get("version") != STATE_VERSION or not isinstance(value.get("files"), dict)
            or not all(isinstance(item, dict) for item in value["files"].values())
            or not isinstance(value.get("worker"), dict)):
        raise ValueError("refusing to overwrite an unrelated or unsupported state file")
    return value


@contextmanager
def _state_lock(config: SyncConfig) -> Iterator[None]:
    """OS lock, automatically released after a worker crash; no stale-PID guess."""
    path = Path(str(config.state_path) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("sync lock cannot be a symlink")
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            raise RuntimeError("a sync worker already holds this state file") from None
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _safe_ancestors(path: Path, boundary: Path) -> bool:
    # Inspect the selected tree, not OS aliases above it (for example macOS
    # /var -> /private/var). Descendant symlinks and a symlink root are excluded.
    for item in (path, *path.parents):
        try:
            if _linked(item):
                return False
        except FileNotFoundError:
            continue
        if item == boundary:
            break
    return True


def _signature(info: os.stat_result) -> list[int]:
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


class _Deferred(Exception):
    pass


class _Ignored(Exception):
    pass


def _read_snapshot(path: Path, max_bytes: int, boundary: Path) -> tuple[bytes, list[int]]:
    if not _safe_ancestors(path, boundary):
        raise _Ignored("symlink")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise _Ignored("not_regular")
    if before.st_size > max_bytes:
        raise ValueError("file_too_large")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise _Deferred("file_changed_during_read")
        data = handle.read(max_bytes + 1)
        after = os.fstat(handle.fileno())
    if len(data) > max_bytes:
        raise ValueError("file_too_large")
    if _signature(before) != _signature(after) or _signature(after) != _signature(path.lstat()):
        raise _Deferred("file_changed_during_read")
    return data, _signature(after)


def _complete_text(data: bytes, path: Path, format: str) -> tuple[str, bool]:
    """Ignore only an unterminated, incomplete final JSONL record."""
    if not data.strip():
        raise _Deferred("empty_file")
    stream = path.suffix.casefold() == ".jsonl" or format in {"claude-code", "codex", "kimi-legacy"}
    partial = False
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        if not stream or data.endswith(b"\n"):
            raise ValueError("invalid_utf8") from None
        boundary = data.rfind(b"\n")
        if boundary < 0:
            raise _Deferred("partial_record") from None
        try:
            text = data[:boundary + 1].decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("invalid_utf8") from None
        partial = True
    if not stream:
        return text, partial
    try:
        json.loads(text)
        return text, partial
    except json.JSONDecodeError:
        pass
    lines = text.splitlines(keepends=True)
    if lines and not text.endswith(("\n", "\r")) and lines[-1].strip():
        try:
            json.loads(lines[-1])
        except json.JSONDecodeError:
            text = "".join(lines[:-1])
            partial = True
    if not text.strip():
        raise _Deferred("partial_record")
    return text, partial


def _paths(source: WatchSource) -> Iterator[Path]:
    if not source.path.exists():
        raise FileNotFoundError("source_missing")
    if not source.path.is_dir() or not _safe_ancestors(source.path, source.path):
        raise ValueError("source_must_be_a_real_directory")
    patterns = source.patterns or DEFAULT_PATTERNS[source.format]
    pending = [source.path]
    count = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            if entry.is_symlink():
                continue
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if source.recursive and not entry.name.startswith(".") and entry.name.casefold() not in EXCLUDED_DIRECTORIES:
                    if not _linked(path):
                        pending.append(path)
                continue
            name = entry.name.casefold()
            if (not entry.is_file(follow_symlinks=False) or name.startswith(".")
                    or name in EXCLUDED_NAMES or path.suffix.casefold() not in {".json", ".jsonl"}
                    or any(word in name for word in ("credential", "secret", "api-key", "api_key"))
                    or not any(fnmatch.fnmatchcase(entry.name, pattern) for pattern in patterns)):
                continue
            # Gemini migrates a legacy session-*.json into its .jsonl sibling.
            # Prefer the active stream when both snapshots remain on disk.
            if source.format == "gemini" and path.suffix == ".json" and Path(str(path) + "l").is_file():
                continue
            count += 1
            if count > MAX_FILES_PER_SOURCE:
                raise ValueError("source_file_limit")
            yield path


def _file_key(source: WatchSource, path: Path) -> str:
    # Include the selected source root: editing a config to point elsewhere must
    # not overwrite unrelated no-ID transcripts merely sharing a filename.
    identity = f"{source.id}\0{source.path}\0{path.relative_to(source.path).as_posix()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _source_fingerprint(source: WatchSource) -> str:
    value = asdict(source)
    value["path"] = str(source.path)
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _choose_project(source: WatchSource, path: Path, info: dict[str, Any]) -> str | None:
    workspaces = sorted({_workspace_key(value) for value in info["workspaces"]})
    if source.workspace is not None and source.workspace not in workspaces:
        raise _Ignored("workspace_mismatch")
    if source.project is not None:
        return source.project
    if source.project_mode == "subdirectory":
        relative = path.relative_to(source.path)
        group = relative.parts[0] if len(relative.parts) > 1 else source.path.name
        digest = hashlib.sha256(f"{source.path}\0{group}".encode("utf-8")).hexdigest()[:12]
        return f"{_slug(source.project_prefix) + '-' if source.project_prefix else ''}{_slug(group)}-{digest}"
    if info["format"] == "canonical" and info["projects"]:
        return None  # Keep explicit project labels on each canonical session.
    if source.workspace is not None:
        return project_for_workspace(source.workspace, source.project_prefix)
    if len(workspaces) == 1:
        return project_for_workspace(workspaces[0], source.project_prefix)
    hashes = info.get("project_hashes", [])
    if len(hashes) == 1:
        return f"{_slug(source.project_prefix or info['format'])}-{hashlib.sha256(hashes[0].encode('utf-8')).hexdigest()[:16]}"
    raise ValueError("ambiguous_project" if len(workspaces) > 1 else "missing_project_metadata")


def _log(config: SyncConfig, event: str, *, source_id: str | None = None,
         file_key: str | None = None, code: str | None = None, **counts: Any) -> None:
    if config.log_path is None:
        return
    path = config.log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("sync log cannot be a symlink")
    if path.exists() and path.stat().st_size >= LOG_ROTATE_BYTES:
        os.replace(path, Path(str(path) + ".1"))
    payload = {"at": _now(), "event": event}
    for name, value in (("source_id", source_id), ("file_key", file_key), ("code", code)):
        if value is not None:
            payload[name] = value
    payload.update({key: val for key, val in counts.items() if isinstance(val, (bool, int, float))})
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _error_code(exc: Exception) -> str:
    # Never log str(exc): malformed input and OS errors may include source text.
    if isinstance(exc, ValueError):
        safe = {"file_too_large", "missing_project_metadata", "ambiguous_project", "invalid_utf8", "session_id_conflict"}
        return str(exc) if str(exc) in safe else "invalid_transcript"
    if isinstance(exc, sqlite3.Error):
        return "database_error"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, FileNotFoundError):
        return "source_missing"
    return "read_error" if isinstance(exc, OSError) else "import_error"


def _bind_database(book: MemoryBook, config: SyncConfig, state: dict[str, Any]) -> bool:
    """Bind skip metadata to this database generation, including path recreation."""
    book.db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('sync_generation',?)", (uuid.uuid4().hex,))
    generation = book.db.execute("SELECT value FROM meta WHERE key='sync_generation'").fetchone()[0]
    identity = {"path": str(config.database.resolve()), "generation": generation}
    previous = state.get("database", {})
    changed = (previous.get("path") != identity["path"] or previous.get("generation") != generation
               or book.revision < previous.get("revision", 0))
    if changed:
        state["files"] = {}
    state["database"] = {**identity, "revision": book.revision}
    return changed


def _ownership(config: SyncConfig, state: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Only current sources and still-present files retain source ownership."""
    sources = {source.id: source for source in config.sources}
    fingerprints = {key: _source_fingerprint(source) for key, source in sources.items()}
    owners: dict[tuple[str, str], str] = {}
    for key, record in state["files"].items():
        source = sources.get(record.get("source_id"))
        active = source is not None and record.get("source_fingerprint") == fingerprints[source.id]
        record["inactive"] = not active
        if not active or record.get("missing"):
            continue
        relative = Path(record.get("relative_path", ""))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        path = source.path / relative
        try:
            if not path.is_file() or _linked(path):
                continue
        except OSError:
            continue
        for identity in record.get("sessions", []):
            if isinstance(identity, list) and len(identity) == 2 and all(isinstance(item, str) for item in identity):
                owners[tuple(identity)] = key
    return owners


def _cycle(config: SyncConfig, state: dict[str, Any], *, force: bool = False,
           stop_event: threading.Event | None = None) -> dict[str, Any]:
    started = time.perf_counter_ns()
    summary: dict[str, Any] = {key: 0 for key in (
        "scanned", "imported", "updated_sessions", "skipped", "partial", "deferred", "errors", "ignored", "missing")}
    summary["error_details"] = []
    seen: set[str] = set()
    completed_sources: set[str] = set()
    protected = {config.database, config.state_path, config.log_path,
                 Path(str(config.state_path) + ".lock"),
                 *(Path(str(config.database) + suffix) for suffix in ("-wal", "-shm", "-journal"))}
    now = time.time()
    with MemoryBook(config.database) as book:
        summary["database_rebound"] = _bind_database(book, config, state)
        owners = _ownership(config, state)
        for source in config.sources:
            if stop_event is not None and stop_event.is_set():
                break
            source_fingerprint = _source_fingerprint(source)
            try:
                paths = _paths(source)
                for path in paths:
                    if stop_event is not None and stop_event.is_set():
                        break
                    if path in protected:
                        continue
                    key = _file_key(source, path)
                    seen.add(key)
                    summary["scanned"] += 1
                    previous = state["files"].get(key, {})
                    record = {**previous, "source_id": source.id,
                              "relative_path": path.relative_to(source.path).as_posix(),
                              "last_seen_at": _now(), "missing": False, "inactive": False}
                    try:
                        signature = _signature(path.lstat())
                        unchanged_metadata = (previous.get("signature") == signature
                                              and previous.get("source_fingerprint") == source_fingerprint)
                        if not force and unchanged_metadata and previous.get("status") in {"ok", "partial", "ignored"}:
                            summary["skipped"] += 1
                            state["files"][key] = record
                            continue
                        if not force and unchanged_metadata and previous.get("retry_after", 0) > now:
                            summary["deferred"] += 1
                            state["files"][key] = record
                            continue
                        data, signature = _read_snapshot(path, config.max_file_bytes, source.path)
                        digest = hashlib.sha256(data).hexdigest()
                        record.update(signature=signature, source_fingerprint=source_fingerprint, sha256=digest)
                        if (not force and previous.get("sha256") == digest
                                and previous.get("source_fingerprint") == source_fingerprint
                                and previous.get("status") in {"ok", "partial", "ignored"}):
                            summary["skipped"] += 1
                            state["files"][key] = record
                            continue
                        text, partial = _complete_text(data, path, source.format)
                        try:
                            info = transcript_info(text, source.format)
                        except ValueError as exc:
                            if source.format == "auto" and str(exc).startswith("Unsupported transcript format"):
                                raise _Ignored("unrecognized_format") from None
                            raise
                        project = _choose_project(source, path, info)
                        complete_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                        if (not force and previous.get("complete_sha256") == complete_hash
                                and previous.get("source_fingerprint") == source_fingerprint
                                and previous.get("status") in {"ok", "partial"}):
                            record.update(status="partial" if partial else "ok", attempts=0, retry_after=0)
                            summary["skipped"] += 1
                            summary["partial"] += int(partial)
                            state["files"][key] = record
                            continue
                        sessions = parse_sessions(text, source_path=path, format=info["format"],
                                                  project=project, task_id=source.task_id,
                                                  fallback_id="watch-" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32])
                        for session in sessions:
                            normalize_session(session)  # Validate the whole file before writing its first session.
                        identities = {(session["project"], session["session_id"]) for session in sessions}
                        if any(identity in owners and owners[identity] != key for identity in identities):
                            raise ValueError("session_id_conflict")
                        changed = 0
                        for session in sessions:
                            changed += not book.ingest(session)["skipped"]
                        record.update(status="partial" if partial else "ok", attempts=0, retry_after=0,
                                      complete_sha256=complete_hash, sessions=[list(item) for item in sorted(identities)],
                                      last_success_at=_now(), last_error_code=None, format=info["format"])
                        summary["imported"] += 1
                        summary["updated_sessions"] += changed
                        summary["partial"] += int(partial)
                        owners.update({identity: key for identity in identities})
                        _log(config, "file_imported", source_id=source.id, file_key=key,
                             sessions=len(sessions), changed=changed, partial=partial)
                    except _Ignored as exc:
                        record.update(status="ignored", last_error_code=str(exc), attempts=0,
                                      source_fingerprint=source_fingerprint,
                                      signature=_signature(path.lstat()) if path.exists() else None)
                        summary["ignored"] += 1
                    except _Deferred as exc:
                        record.update(status="deferred", last_error_code=str(exc), retry_after=0)
                        summary["deferred"] += 1
                    except Exception as exc:
                        code = _error_code(exc)
                        attempts = int(previous.get("attempts", 0)) + 1
                        record.update(status="error", last_error_code=code, attempts=attempts,
                                      retry_after=now + min(300, config.poll_interval * 2 ** min(attempts - 1, 6)),
                                      source_fingerprint=source_fingerprint,
                                      signature=_signature(path.lstat()) if path.exists() else None)
                        summary["errors"] += 1
                        summary["error_details"].append({"source_id": source.id, "file_key": key, "code": code})
                        _log(config, "file_error", source_id=source.id, file_key=key, code=code)
                    state["files"][key] = record
                if stop_event is None or not stop_event.is_set():
                    completed_sources.add(source.id)
            except (OSError, ValueError) as exc:
                summary["errors"] += 1
                code = _error_code(exc)
                summary["error_details"].append({"source_id": source.id, "code": code})
                _log(config, "source_error", source_id=source.id, code=code)
        state["database"]["revision"] = book.revision
    for key, record in state["files"].items():
        if record.get("source_id") in completed_sources and key not in seen:
            record["missing"] = True
            summary["missing"] += 1
    summary["elapsed_ms"] = (time.perf_counter_ns() - started) / 1_000_000
    summary["finished_at"] = _now()
    state["last_cycle"] = summary
    state["worker"]["heartbeat_at"] = summary["finished_at"]
    _atomic_json(config.state_path, state)
    return summary


def sync_once(config: SyncConfig, force: bool = False) -> dict[str, Any]:
    """Process changed transcripts once; a bad file never stops other files."""
    with _state_lock(config):
        state = _load_state(config.state_path)
        return _cycle(config, state, force=force)


def sync_status(config: SyncConfig) -> dict[str, Any]:
    """Read only the manifest, never scan client sources as a status side effect."""
    state = _load_state(config.state_path)
    counts: dict[str, int] = {}
    for record in state["files"].values():
        key = "inactive" if record.get("inactive") else "missing" if record.get("missing") else record.get("status", "unknown")
        counts[key] = counts.get(key, 0) + 1
    worker = dict(state.get("worker", {}))
    if worker.get("running"):
        try:
            os.kill(int(worker.get("pid", 0)), 0)
        except (OSError, TypeError, ValueError):
            worker["running"] = False
            worker["stale_state"] = True
    return {"configured_sources": len(config.sources), "tracked_files": len(state["files"]),
            "files_by_status": counts, "worker": worker, "last_cycle": state.get("last_cycle")}


def watch(config: SyncConfig, stop_event: threading.Event | None = None,
          on_cycle: Callable[[dict[str, Any]], None] | None = None,
          max_cycles: int | None = None) -> dict[str, Any]:
    """Poll explicit sources quietly until signalled; Event.wait makes stop prompt."""
    if max_cycles is not None and (isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or max_cycles < 1):
        raise ValueError("max_cycles must be a positive integer")
    owns_event = stop_event is None
    stop = stop_event if stop_event is not None else threading.Event()
    handlers: dict[int, Any] = {}
    with _state_lock(config):
        state = _load_state(config.state_path)
        state["worker"] = {"running": True, "pid": os.getpid(), "started_at": _now(), "heartbeat_at": _now()}
        _atomic_json(config.state_path, state)
        if owns_event and threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda *_: stop.set())
        last: dict[str, Any] = {}
        cycles = 0
        try:
            _log(config, "worker_started", pid=os.getpid())
            while not stop.is_set():
                try:
                    last = _cycle(config, state, stop_event=stop)
                except (OSError, ValueError, sqlite3.Error) as exc:
                    # Database/state failures remain observable without logging
                    # exception strings or terminating capture permanently.
                    last = {"errors": 1, "code": _error_code(exc), "finished_at": _now()}
                    _log(config, "cycle_error", code=_error_code(exc))
                cycles += 1
                if on_cycle is not None:
                    on_cycle(last)
                if max_cycles is not None and cycles >= max_cycles:
                    break
                stop.wait(config.poll_interval)
        finally:
            try:
                state["worker"].update(running=False, stopped_at=_now(), heartbeat_at=_now())
                _atomic_json(config.state_path, state)
                _log(config, "worker_stopped", cycles=cycles)
            finally:
                for sig, previous in handlers.items():
                    signal.signal(sig, previous)
        return last
