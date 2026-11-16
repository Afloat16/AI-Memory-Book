"""Read-only archive checks and verified, non-overwriting SQLite snapshots.

These operations intentionally do not construct MemoryBook: opening a book can
initialize or migrate it. Maintenance must leave the source schema and evidence
alone, including when an older archive is being backed up before an upgrade.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time


_SIDECARS = ("-wal", "-shm", "-journal")
_TABLE_COLUMNS = {
    "meta": {"key", "value"},
    "projects": {"id", "name"},
    "chapters": {"id", "project_id", "task_id"},
    "sessions": {"id", "external_id", "project_id", "chapter_id", "raw_json", "content_hash"},
    "turns": {"id", "session_pk", "ordinal", "content"},
    "sections": {"id", "session_pk", "chapter_id"},
    "pages": {"rid", "id", "project_id", "session_pk", "content", "source_refs"},
    "pages_fts": {"title", "question", "body", "directory"},
    "recall_cache": {"key", "revision", "payload"},
}
_COUNT_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")


class _Deadline:
    def __init__(self, timeout: float):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number of seconds")
        self.ends = time.monotonic() + timeout

    def expired(self) -> bool:
        return time.monotonic() >= self.ends

    def check(self, *_: object) -> None:
        if self.expired():
            raise TimeoutError("database maintenance timed out; the source archive was not changed")

    def progress(self) -> int:
        return int(self.expired())


def _source_path(value: str | Path) -> tuple[Path, Path, tuple[int, int]]:
    if str(value) == ":memory:":
        raise ValueError("maintenance requires an existing on-disk archive")
    requested = Path(value).expanduser().absolute()
    source = requested.resolve(strict=True)
    info = source.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("source archive must be a regular file")
    if info.st_nlink > 1:
        raise ValueError("source archive has hard-link aliases; remove the aliases and use its original path so SQLite can find the correct WAL")
    return requested, source, (info.st_dev, info.st_ino)


def _same_source(source: Path, identity: tuple[int, int]) -> None:
    info = source.stat()
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != identity:
        raise RuntimeError("source archive was replaced during maintenance; retry with the current file")
    if info.st_nlink > 1:
        raise ValueError("source archive acquired a hard-link alias during maintenance; use its original path without hard-link aliases")


def _connect_readonly(source: Path, deadline: _Deadline) -> sqlite3.Connection:
    deadline.check()
    # Do not use immutable=1: live WAL frames and ordinary SQLite locking must
    # remain visible. URI quoting also preserves spaces, #, ? and Unicode paths.
    connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True,
                                 timeout=min(0.2, max(0.001, deadline.ends - time.monotonic())),
                                 isolation_level=None)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(deadline.progress, 1000)
        return connection
    except BaseException:
        connection.close()
        raise


def _archive_identity(connection: sqlite3.Connection) -> tuple[int, int, list[str]]:
    # Read the runtime constants without opening a MemoryBook or running any
    # migrations. Keep known older schemas readable after a runtime upgrade.
    from .store import APPLICATION_ID, SCHEMA_VERSION

    version = connection.execute("PRAGMA user_version").fetchone()[0]
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    if application_id not in (0, APPLICATION_ID):
        raise ValueError("refusing a database belonging to another application")
    if version not in {1, 2, 3, SCHEMA_VERSION}:
        raise ValueError(f"unsupported archive schema {version}; supported: 1, 2, 3 and {SCHEMA_VERSION}")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = dict(_TABLE_COLUMNS)
    if version >= 3:
        required["pages_stem_fts"] = _TABLE_COLUMNS["pages_fts"]
    for table, columns in required.items():
        if table not in tables:
            raise ValueError(f"not a complete AI-Memory-Book archive: missing table {table}")
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not columns <= actual:
            raise ValueError(f"not an AI-Memory-Book archive: unexpected layout for {table}")
    warnings = []
    if not application_id:
        warnings.append("Unmarked legacy archive recognized by its known schema and table layout.")
    return application_id, version, warnings


def _runtime_state(connection: sqlite3.Connection, version: int, revision: str) -> tuple[str, list[str]]:
    """Report repairable runtime metadata separately from snapshot integrity."""
    from .store import LEXICAL_INDEX_VERSION, SCHEMA_VERSION

    if version != SCHEMA_VERSION:
        return "migration_required", [
            f"Runtime migration required from schema {version} to {SCHEMA_VERSION}; maintenance preserved the older schema."]
    markers = dict(connection.execute("SELECT key,value FROM meta WHERE key IN "
                                      "('lexical_index_version','lexical_revision','stem_revision')"))
    guards = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
              "AND name IN ('meta_revision_require_lexical','meta_revision_sync_stem')")}
    warnings = []
    if markers.get("lexical_index_version") != str(LEXICAL_INDEX_VERSION):
        warnings.append("Runtime repair required: lexical_index_version is missing or does not match this runtime.")
    for marker in ("lexical_revision", "stem_revision"):
        if markers.get(marker) != revision:
            warnings.append(f"Runtime repair required: {marker} is missing or does not match revision.")
    for guard in ("meta_revision_require_lexical", "meta_revision_sync_stem"):
        if guard not in guards:
            warnings.append(f"Runtime repair required: missing revision guard {guard}.")
    return ("repair_required" if warnings else "ready"), warnings


def _inspect(connection: sqlite3.Connection, deadline: _Deadline) -> dict:
    """Inspect one consistent read snapshot; no writes or repair statements."""
    deadline.check()
    connection.execute("BEGIN")
    try:
        application_id, version, warnings = _archive_identity(connection)
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check(100)")]
        violations = 0
        examples = []
        for table, rowid, parent, foreign_key in connection.execute("PRAGMA foreign_key_check"):
            violations += 1
            if len(examples) < 20:
                examples.append({"table": table, "rowid": rowid, "parent": parent, "foreign_key": foreign_key})
            deadline.check()
        revision_row = connection.execute("SELECT value FROM meta WHERE key='revision'").fetchone()
        if revision_row is None:
            raise ValueError("archive has no revision marker")
        try:
            revision = int(revision_row[0])
        except (TypeError, ValueError) as exc:
            raise ValueError("archive has an invalid revision marker") from exc
        if revision < 0:
            raise ValueError("archive has an invalid revision marker")
        runtime_state, runtime_warnings = _runtime_state(connection, version, revision_row[0])
        warnings.extend(runtime_warnings)
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in _COUNT_TABLES}
        database_bytes = (connection.execute("PRAGMA page_count").fetchone()[0]
                          * connection.execute("PRAGMA page_size").fetchone()[0])
        deadline.check()
        return {"ok": integrity == ["ok"] and violations == 0,
                "application_id": application_id, "schema_version": version, "revision": revision,
                "runtime_state": runtime_state,
                **counts, "database_bytes": database_bytes, "integrity_check": integrity,
                "foreign_key_violations": violations, "foreign_key_errors": examples,
                "warnings": warnings}
    finally:
        connection.execute("ROLLBACK")


def check_database(source: str | Path, *, timeout: float = 30.0) -> dict:
    """Check an existing archive without creating, migrating or repairing it.

    Structural/FK failures return ok=False. Invalid paths, application identity,
    unreadable SQLite data and timeouts raise rather than appearing healthy.
    runtime_state separately identifies migration or repairable metadata needs;
    these do not make a structurally intact source unsafe to snapshot. This does
    not validate the truth of source text or retrieval quality.
    """
    deadline = _Deadline(timeout)
    _, path, identity = _source_path(source)
    connection = _connect_readonly(path, deadline)
    try:
        _same_source(path, identity)
        result = _inspect(connection, deadline)
        _same_source(path, identity)
        return {"database": str(path), **result}
    except sqlite3.OperationalError:
        deadline.check()
        raise
    finally:
        connection.close()


def _check_output(output: Path, requested_source: Path, source: Path) -> None:
    protected = set()
    for base in (requested_source, source):
        protected.add(base.resolve())
        protected.update(Path(str(base) + suffix).resolve() for suffix in _SIDECARS)
    if output.resolve() in protected:
        raise ValueError("backup output cannot be the source archive or one of its journal files")
    # lexists also rejects dangling symlinks. Existing hard links are therefore
    # rejected without ever opening them as SQLite destinations.
    if os.path.lexists(output):
        raise FileExistsError(f"backup output already exists; choose a new path: {output}")
    for suffix in _SIDECARS:
        if os.path.lexists(str(output) + suffix):
            raise FileExistsError(f"backup output has an existing SQLite journal file: {output}{suffix}")


def _publish(snapshot: Path, output: Path) -> None:
    """Atomically publish a completed snapshot without replacing a raced file."""
    if os.name == "nt":
        # Windows rename, unlike os.replace, fails when the target exists.
        os.rename(snapshot, output)
    else:
        # POSIX rename could overwrite a target created after the last check.
        # A hard link in the same filesystem has atomic no-replace semantics.
        # Unsupported filesystems fail safely; never fall back to replacement.
        os.link(snapshot, output, follow_symlinks=False)


def backup_database(source: str | Path, output: str | Path, *, timeout: float = 30.0) -> dict:
    """Create a verified standalone snapshot of an existing, possibly live DB.

    The destination must be new. Source pages are read through SQLite's online
    backup API, so committed WAL data is included without checkpointing the
    source. Only the database is copied, not capture config, logs or model files.
    """
    deadline = _Deadline(timeout)
    requested_source, source_path, identity = _source_path(source)
    requested_output = Path(output).expanduser().absolute()
    _check_output(requested_output, requested_source, source_path)
    source_connection = _connect_readonly(source_path, deadline)
    try:
        _same_source(source_path, identity)
        _archive_identity(source_connection)
        requested_output.parent.mkdir(parents=True, exist_ok=True)
        target = requested_output.parent.resolve() / requested_output.name
        _check_output(target, requested_source, source_path)
        # A private directory prevents a partially written SQLite file from
        # appearing at the requested output path, and contains cleanup sidecars.
        with tempfile.TemporaryDirectory(prefix=".memory-book-backup-", dir=target.parent) as temporary:
            snapshot = Path(temporary) / "snapshot.db"
            descriptor = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
            destination = sqlite3.connect(str(snapshot), isolation_level=None)
            try:
                destination.execute("PRAGMA synchronous=FULL")
                destination.set_progress_handler(deadline.progress, 1000)
                source_connection.backup(destination, pages=128, progress=deadline.check, sleep=0.01)
                deadline.check()
                # Finish as a self-contained file; do not publish a snapshot
                # whose newest pages live in a companion WAL.
                mode = destination.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
                if mode != "delete":
                    raise RuntimeError("could not finalize a standalone backup file")
                result = _inspect(destination, deadline)
                if not result["ok"]:
                    raise ValueError("backup verification failed: SQLite integrity or foreign-key errors; no output published")
            finally:
                destination.close()
            # Windows' flush primitive needs a writable handle as well.
            with snapshot.open("r+b") as stream:
                os.fsync(stream.fileno())
            _same_source(source_path, identity)
            _check_output(target, requested_source, source_path)
            deadline.check()
            _publish(snapshot, target)
        return {"source": str(source_path), "output": str(target), **result}
    except sqlite3.OperationalError:
        deadline.check()
        raise
    finally:
        source_connection.close()
