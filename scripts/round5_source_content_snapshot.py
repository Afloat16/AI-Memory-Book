"""Deterministic cross-ingest identity for the prospectively registered fresh v2.

The original full source_snapshot remains mandatory within each worker and for
copies of the same exported database. Only the four audited storage-clock
columns below are omitted from this additional cross-ingest identity.
"""
from __future__ import annotations

import hashlib
import json
import re

VERSION = "round5-source-content-snapshot-1"
# (name, declared type, NOT NULL flag, default SQL, primary-key position)
SCHEMA = {
    "projects": (
        ("id", "TEXT", 0, None, 1), ("name", "TEXT", 1, None, 0),
        ("created_at", "TEXT", 1, None, 0), ("updated_at", "TEXT", 1, None, 0)),
    "chapters": (
        ("id", "TEXT", 0, None, 1), ("project_id", "TEXT", 1, None, 0),
        ("task_id", "TEXT", 1, None, 0), ("title", "TEXT", 1, None, 0),
        ("summary", "TEXT", 1, "''", 0), ("updated_at", "TEXT", 1, None, 0)),
    "sessions": (
        ("id", "TEXT", 0, None, 1), ("external_id", "TEXT", 1, None, 0),
        ("project_id", "TEXT", 1, None, 0), ("chapter_id", "TEXT", 1, None, 0),
        ("title", "TEXT", 1, None, 0), ("created_at", "TEXT", 1, None, 0),
        ("updated_at", "TEXT", 1, None, 0), ("content_hash", "TEXT", 1, None, 0),
        ("raw_json", "TEXT", 1, None, 0), ("segmentation", "TEXT", 1, None, 0),
        ("message_count", "INTEGER", 1, None, 0), ("turn_count", "INTEGER", 1, None, 0),
        ("content_chars", "INTEGER", 1, None, 0), ("settings_json", "TEXT", 1, "'{}'", 0)),
    "turns": (
        ("id", "TEXT", 0, None, 1), ("session_pk", "TEXT", 1, None, 0),
        ("ordinal", "INTEGER", 1, None, 0), ("question", "TEXT", 1, None, 0),
        ("content", "TEXT", 1, None, 0), ("message_indices", "TEXT", 1, None, 0)),
    "sections": (
        ("id", "TEXT", 0, None, 1), ("session_pk", "TEXT", 1, None, 0),
        ("chapter_id", "TEXT", 1, None, 0), ("title", "TEXT", 1, None, 0),
        ("summary", "TEXT", 1, None, 0), ("ordinal", "INTEGER", 1, None, 0)),
    "pages": (
        ("rid", "INTEGER", 0, None, 1), ("id", "TEXT", 1, None, 0),
        ("section_id", "TEXT", 1, None, 0), ("session_pk", "TEXT", 1, None, 0),
        ("chapter_id", "TEXT", 1, None, 0), ("project_id", "TEXT", 1, None, 0),
        ("title", "TEXT", 1, None, 0), ("question", "TEXT", 1, None, 0),
        ("content", "TEXT", 1, None, 0), ("source_refs", "TEXT", 1, None, 0),
        ("ordinal", "INTEGER", 1, None, 0)),
}
EXCLUDED_STORAGE_COLUMNS = {
    "projects": ("created_at", "updated_at"),
    "chapters": ("updated_at",),
    "sessions": ("updated_at",),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_content_snapshot(db):
    """Hash the complete audited schema and every retained cell, without writes."""
    if (db.execute("PRAGMA user_version").fetchone()[0] != 3 or
            db.execute("PRAGMA application_id").fetchone()[0] != 0x4D424F4B):
        raise ValueError("Cross-ingest snapshot requires the registered MemoryBook schema")
    schemas, table_hashes, row_counts, retained_columns = {}, {}, {}, {}
    for table, specification in SCHEMA.items():
        schema = [tuple(row) for row in db.execute(f"PRAGMA table_info({table})")]
        expected = [(i, *column) for i, column in enumerate(specification)]
        if schema != expected:
            raise ValueError("Cross-ingest source schema changed: " + table)
        columns = [column[0] for column in specification
                   if column[0] not in EXCLUDED_STORAGE_COLUMNS.get(table, ())]
        # Identifiers are fixed above, not supplied by a caller or database row.
        quoted = ",".join('"' + name + '"' for name in columns)
        rows = [list(row) for row in db.execute(
            f'SELECT {quoted} FROM "{table}" ORDER BY id')]
        create_sql = db.execute("SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?",
                                (table,)).fetchone()
        if create_sql is None or type(create_sql[0]) is not str:
            raise ValueError("Missing source table definition: " + table)
        schemas[table] = {"table_info": [list(row) for row in schema],
                          "create_sql": create_sql[0],
                          "foreign_keys": [list(row) for row in db.execute(
                              f"PRAGMA foreign_key_list({table})")]}
        row_counts[table] = len(rows)
        retained_columns[table] = columns
        table_hashes[table] = digest({"columns": columns, "rows": rows})
    identity = {
        "version": VERSION,
        "excluded_storage_columns": {name: list(columns)
                                     for name, columns in EXCLUDED_STORAGE_COLUMNS.items()},
        "schema_sha256": digest(schemas),
        "retained_columns": retained_columns,
        "row_counts": row_counts,
        "table_sha256": table_hashes,
    }
    return {**identity, "sha256": digest(identity)}


def verify_content_snapshot(value):
    """Reject incomplete or internally inconsistent saved v2 identities."""
    fields = {"version", "excluded_storage_columns", "schema_sha256",
              "retained_columns", "row_counts", "table_sha256", "sha256"}
    expected_columns = {table: [column[0] for column in specification
        if column[0] not in EXCLUDED_STORAGE_COLUMNS.get(table, ())]
        for table, specification in SCHEMA.items()}
    if (type(value) is not dict or set(value) != fields or
            value["version"] != VERSION or
            value["excluded_storage_columns"] != {name: list(columns)
                for name, columns in EXCLUDED_STORAGE_COLUMNS.items()} or
            value["retained_columns"] != expected_columns or
            type(value["row_counts"]) is not dict or
            set(value["row_counts"]) != set(SCHEMA) or
            any(type(count) is not int or count < 0 for count in value["row_counts"].values()) or
            type(value["table_sha256"]) is not dict or set(value["table_sha256"]) != set(SCHEMA)):
        raise ValueError("Saved deterministic source identity has changed shape")
    hashes = [value["schema_sha256"], value["sha256"], *value["table_sha256"].values()]
    if (any(type(item) is not str or re.fullmatch("[0-9a-f]{64}", item) is None
            for item in hashes) or
            value["sha256"] != digest({key: item for key, item in value.items() if key != "sha256"})):
        raise ValueError("Saved deterministic source identity checksum differs")
    return value
