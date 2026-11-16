"""Real SQLite snapshots must preserve live evidence without changing sources."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.cli import main
from memory_book import maintenance
from memory_book.maintenance import backup_database, check_database
from memory_book.store import APPLICATION_ID, SCHEMA_VERSION


def session(identifier="initial", answer="Use chronological splitting; retain the fully masked softmax rule."):
    return {"project": "engineering", "session_id": identifier, "task_id": "training",
            "created_at": "2026-11-15T01:00:00Z", "messages": [
                {"role": "user", "content": "Which data split and softmax policy?"},
                {"role": "assistant", "content": answer}]}


def snapshot_rows(connection):
    return {"sources": [tuple(row) for row in connection.execute(
                "SELECT id,raw_json,content_hash FROM sessions ORDER BY id")],
            "pages": [tuple(row) for row in connection.execute(
                "SELECT id,content,source_refs FROM pages ORDER BY id")],
            "meta": [tuple(row) for row in connection.execute("SELECT key,value FROM meta ORDER BY key")]}


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source #? 中文.db"
        self.book = MemoryBook(self.source)
        self.book.db.execute("PRAGMA wal_autocheckpoint=0")
        self.book.ingest(session())

    def tearDown(self):
        self.book.close()
        self.temporary.cleanup()

    def assert_no_temporary_backups(self):
        self.assertFalse(list(self.root.rglob(".memory-book-backup-*")))

    def test_live_wal_backup_is_standalone_preserves_sources_and_addresses(self):
        self.book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        main_digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.book.ingest(session("wal-only", "Negative weights require Bellman-Ford, not Dijkstra."))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), main_digest)
        self.assertGreater(Path(str(self.source) + "-wal").stat().st_size, 0)
        before = snapshot_rows(self.book.db)
        output = self.root / "snapshots" / "copy #? 中文.db"

        result = backup_database(self.source, output)

        self.assertTrue(result["ok"])
        self.assertEqual(result["runtime_state"], "ready")
        self.assertEqual(result["sessions"], 2)
        self.assertEqual(result["revision"], self.book.revision)
        self.assertEqual(result["integrity_check"], ["ok"])
        self.assertEqual(result["foreign_key_violations"], 0)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), main_digest)
        self.assertTrue(Path(str(self.source) + "-wal").is_file())
        self.assertFalse(any(Path(str(output) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")))
        # A SQLite context ends the transaction; closing also releases the handle.
        with contextlib.closing(sqlite3.connect(output)) as copy, copy:
            self.assertEqual(snapshot_rows(copy), before)
            self.assertEqual(copy.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(copy.execute("PRAGMA application_id").fetchone()[0], APPLICATION_ID)
        self.book.ingest(session("later"))
        self.assertEqual(check_database(output)["sessions"], 2)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assert_no_temporary_backups()

    def test_online_copy_stays_consistent_during_a_committed_writer(self):
        self.book.db.execute("CREATE TABLE backup_test_padding(value BLOB)")
        self.book.db.execute("INSERT INTO backup_test_padding VALUES(zeroblob(2097152))")
        start = threading.Event()
        finished = threading.Event()
        failures = []

        def write():
            try:
                if not start.wait(5):
                    raise AssertionError("backup never reached a page batch")
                with MemoryBook(self.source) as writer:
                    writer.ingest(session("during-backup", "Top-k ties use deterministic identifier order."))
            except BaseException as exc:
                failures.append(exc)
            finally:
                finished.set()

        original = maintenance._Deadline.check

        def during_copy(deadline, *progress):
            original(deadline, *progress)
            if progress and not start.is_set():
                start.set()
                if not finished.wait(5):
                    raise AssertionError("writer blocked during an online backup")

        thread = threading.Thread(target=write)
        thread.start()
        try:
            with patch.object(maintenance._Deadline, "check", during_copy):
                result = backup_database(self.source, self.root / "concurrent.db", timeout=10)
        finally:
            start.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, failures)
        self.assertTrue(result["ok"])
        self.assertIn(result["sessions"], (1, 2))
        with contextlib.closing(sqlite3.connect(self.root / "concurrent.db")) as copy, copy:
            self.assertEqual(copy.execute("PRAGMA foreign_key_check").fetchall(), [])
            for identifier, raw in copy.execute("SELECT id,raw_json FROM sessions"):
                self.assertEqual(copy.execute("SELECT count(*) FROM turns WHERE session_pk=?", (identifier,)).fetchone()[0], 1)
                self.assertGreater(copy.execute("SELECT count(*) FROM pages WHERE session_pk=?", (identifier,)).fetchone()[0], 0)
                self.assertEqual(json.loads(raw)["project"], "engineering")

    def test_readonly_check_includes_live_wal_and_does_not_open_memorybook(self):
        before = snapshot_rows(self.book.db)
        revision = self.book.revision
        with patch("memory_book.store.MemoryBook", side_effect=AssertionError("maintenance must not migrate")):
            result = check_database(self.source)
        self.assertTrue(result["ok"])
        self.assertEqual(result["revision"], revision)
        self.assertEqual(result["sessions"], 1)
        self.assertEqual(snapshot_rows(self.book.db), before)

    def test_old_schemas_and_unmarked_legacy_archives_are_not_migrated(self):
        for version in sorted({1, 2, 3, SCHEMA_VERSION}):
            for marked in (True, False):
                with self.subTest(version=version, marked=marked):
                    source = self.root / f"schema-{version}-{marked}.db"
                    with MemoryBook(source) as book:
                        book.ingest(session())
                    with contextlib.closing(sqlite3.connect(source)) as db, db:
                        if version < 3:
                            db.execute("DROP TRIGGER IF EXISTS meta_revision_sync_stem")
                            db.execute("DROP TRIGGER IF EXISTS pages_delete_stem_fts")
                            db.execute("DROP TABLE pages_stem_fts")
                        if version == 1:
                            db.execute("ALTER TABLE sessions DROP COLUMN settings_json")
                        db.execute(f"PRAGMA user_version={version}")
                        if not marked:
                            db.execute("PRAGMA application_id=0")
                    before = source.read_bytes()
                    output = self.root / f"copy-{version}-{marked}.db"
                    check = check_database(source)
                    result = backup_database(source, output)
                    self.assertTrue(check["ok"])
                    self.assertEqual(result["schema_version"], version)
                    expected_state = "ready" if version == SCHEMA_VERSION else "migration_required"
                    self.assertEqual(check["runtime_state"], expected_state)
                    self.assertEqual(result["runtime_state"], expected_state)
                    self.assertEqual(source.read_bytes(), before)
                    with (
                        contextlib.closing(sqlite3.connect(source)) as original, original,
                        contextlib.closing(sqlite3.connect(output)) as copy, copy,
                    ):
                        self.assertEqual(original.execute("PRAGMA user_version").fetchone()[0], version)
                        self.assertEqual(copy.execute("PRAGMA user_version").fetchone()[0], version)
                        self.assertEqual(copy.execute("PRAGMA application_id").fetchone()[0], APPLICATION_ID if marked else 0)
                        self.assertEqual(snapshot_rows(copy), snapshot_rows(original))

    def test_runtime_metadata_damage_is_reported_but_preserved_in_safe_snapshots(self):
        cases = {
            "lexical-guard": "DROP TRIGGER meta_revision_require_lexical",
            "stem-guard": "DROP TRIGGER meta_revision_sync_stem",
            "missing-version": "DELETE FROM meta WHERE key='lexical_index_version'",
            "wrong-version": "UPDATE meta SET value='999' WHERE key='lexical_index_version'",
            "missing-lexical-revision": "DELETE FROM meta WHERE key='lexical_revision'",
            "wrong-lexical-revision": "UPDATE meta SET value='999' WHERE key='lexical_revision'",
            "missing-stem-revision": "DELETE FROM meta WHERE key='stem_revision'",
            "wrong-stem-revision": "UPDATE meta SET value='999' WHERE key='stem_revision'",
        }
        for name, mutation in cases.items():
            with self.subTest(case=name):
                source = self.root / f"{name}.db"
                with MemoryBook(source) as book:
                    book.ingest(session())
                connection = sqlite3.connect(source, isolation_level=None)
                try:
                    connection.execute(mutation)
                    before_rows = snapshot_rows(connection)
                finally:
                    connection.close()
                before = source.read_bytes()
                checked = check_database(source)
                output = self.root / f"{name}-snapshot.db"
                saved = backup_database(source, output)
                for result in (checked, saved):
                    self.assertTrue(result["ok"], "runtime diagnostics must not block a structurally valid snapshot")
                    self.assertEqual(result["runtime_state"], "repair_required")
                    self.assertTrue(any("Runtime repair required" in warning for warning in result["warnings"]))
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(check_database(output)["runtime_state"], "repair_required")
                with contextlib.closing(sqlite3.connect(output)) as copy, copy:
                    self.assertEqual(snapshot_rows(copy), before_rows)

    def test_source_and_journal_paths_are_never_destinations(self):
        before = snapshot_rows(self.book.db)
        for output in (self.source, self.root / "unused" / ".." / self.source.name,
                       *(Path(str(self.source) + suffix) for suffix in ("-wal", "-shm", "-journal"))):
            with self.subTest(output=output), self.assertRaises((ValueError, FileExistsError)):
                backup_database(self.source, output)
        self.assertEqual(snapshot_rows(self.book.db), before)
        self.assert_no_temporary_backups()

    def test_source_symlink_is_resolved_and_destination_symlinks_are_refused(self):
        alias = self.root / "source-alias.db"
        try:
            alias.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        self.assertTrue(backup_database(alias, self.root / "from-alias.db")["ok"])
        dangling = self.root / "dangling.db"
        dangling.symlink_to(self.root / "absent.db")
        for output in (alias, dangling):
            with self.subTest(output=output), self.assertRaises((ValueError, FileExistsError)):
                backup_database(self.source, output)
            self.assertTrue(output.is_symlink())
        self.assertFalse((self.root / "absent.db").exists())

    def test_hard_linked_sources_are_refused_to_avoid_ambiguous_wal_paths(self):
        alias = self.root / "hard-alias.db"
        try:
            os.link(self.source, alias)
        except (OSError, NotImplementedError):
            self.skipTest("hard links are unavailable")
        try:
            for source in (self.source, alias):
                with self.subTest(source=source), self.assertRaisesRegex(ValueError, "hard-link"):
                    backup_database(source, self.root / "not-created.db")
                with self.assertRaisesRegex(ValueError, "hard-link"):
                    check_database(source)
            self.assertFalse((self.root / "not-created.db").exists())
        finally:
            alias.unlink()
        self.assertTrue(check_database(self.source)["ok"])

    def test_existing_output_and_output_sidecars_are_preserved(self):
        output = self.root / "existing.db"
        output.write_bytes(b"keep this file")
        with self.assertRaises(FileExistsError):
            backup_database(self.source, output)
        self.assertEqual(output.read_bytes(), b"keep this file")
        directory = self.root / "directory.db"
        directory.mkdir()
        with self.assertRaises(FileExistsError):
            backup_database(self.source, directory)
        for suffix in ("-wal", "-shm", "-journal"):
            output = self.root / f"target{suffix}.db"
            sidecar = Path(str(output) + suffix)
            sidecar.write_bytes(b"keep journal")
            with self.assertRaises(FileExistsError):
                backup_database(self.source, output)
            self.assertEqual(sidecar.read_bytes(), b"keep journal")
            self.assertFalse(output.exists())
        self.assert_no_temporary_backups()

    def test_atomic_publish_does_not_overwrite_a_racing_file(self):
        output = self.root / "race.db"
        publish = maintenance._publish

        def competitor(snapshot, destination):
            destination.write_bytes(b"another writer won")
            publish(snapshot, destination)

        with patch.object(maintenance, "_publish", competitor), self.assertRaises(FileExistsError):
            backup_database(self.source, output)
        self.assertEqual(output.read_bytes(), b"another writer won")
        self.assert_no_temporary_backups()
        self.assertTrue(check_database(self.source)["ok"])

    def test_missing_invalid_and_foreign_sources_do_not_create_output(self):
        missing = self.root / "missing" / "source.db"
        junk = self.root / "junk.db"
        junk.write_bytes(b"not SQLite")
        foreign = self.root / "foreign.db"
        with contextlib.closing(sqlite3.connect(foreign)) as db, db:
            db.execute("CREATE TABLE account(value TEXT)")
            db.execute("PRAGMA application_id=12345")
        empty_sqlite = self.root / "empty.db"
        sqlite3.connect(empty_sqlite).close()
        for source in (missing, junk, foreign, empty_sqlite, self.root):
            output = self.root / "invalid-output.db"
            with self.subTest(source=source):
                with self.assertRaises((ValueError, OSError, sqlite3.DatabaseError)):
                    check_database(source)
                with self.assertRaises((ValueError, OSError, sqlite3.DatabaseError)):
                    backup_database(source, output)
                self.assertFalse(output.exists())
        self.assertFalse(missing.parent.exists())
        self.assert_no_temporary_backups()

    def test_foreign_key_damage_is_reported_and_not_published_as_verified(self):
        self.book.db.execute("PRAGMA foreign_keys=OFF")
        self.book.db.execute("UPDATE pages SET project_id='missing-project'")
        self.book.db.execute("PRAGMA foreign_keys=ON")
        check = check_database(self.source)
        self.assertFalse(check["ok"])
        self.assertEqual(check["integrity_check"], ["ok"])
        self.assertGreater(check["foreign_key_violations"], 0)
        output = self.root / "invalid-snapshot.db"
        with self.assertRaisesRegex(ValueError, "verification failed"):
            backup_database(self.source, output)
        self.assertFalse(output.exists())
        self.assert_no_temporary_backups()

    def test_copy_failure_and_keyboard_interrupt_leave_no_published_snapshot(self):
        original = maintenance._Deadline.check
        for error in (RuntimeError("simulated interruption"), KeyboardInterrupt()):
            output = self.root / "interrupted.db"

            def fail_during_copy(deadline, *progress):
                original(deadline, *progress)
                if progress:
                    raise error

            with patch.object(maintenance._Deadline, "check", fail_during_copy):
                with self.assertRaises(type(error)):
                    backup_database(self.source, output)
            self.assertFalse(output.exists())
            self.assert_no_temporary_backups()
            self.assertTrue(check_database(self.source)["ok"])

    def test_real_exclusive_lock_during_backup_has_a_bounded_timeout(self):
        self.book.close()
        locker = sqlite3.connect(self.source, isolation_level=None)
        locker.execute("PRAGMA journal_mode=DELETE")
        identity = maintenance._archive_identity
        locked = False

        def lock_after_identification(connection):
            nonlocal locked
            result = identity(connection)
            if not locked:
                locker.execute("BEGIN EXCLUSIVE")
                locked = True
            return result

        output = self.root / "timeout.db"
        started = time.monotonic()
        try:
            with patch.object(maintenance, "_archive_identity", lock_after_identification):
                with self.assertRaises(TimeoutError):
                    backup_database(self.source, output, timeout=0.08)
        finally:
            locker.rollback()
            locker.close()
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(output.exists())
        self.assert_no_temporary_backups()
        self.assertTrue(check_database(self.source)["ok"])

    def test_check_sql_work_is_interrupted_at_its_deadline(self):
        self.book.db.execute("CREATE TABLE backup_test_padding(value BLOB)")
        self.book.db.executemany("INSERT INTO backup_test_padding VALUES(?)", [(b"row",)] * 2000)
        expired = False
        identity = maintenance._archive_identity

        def expire_before_integrity(connection):
            nonlocal expired
            result = identity(connection)
            expired = True
            return result

        with patch.object(maintenance, "_archive_identity", expire_before_integrity), \
                patch.object(maintenance._Deadline, "expired", lambda _: expired):
            with self.assertRaises(TimeoutError):
                check_database(self.source)
        self.assertTrue(check_database(self.source)["ok"])

    def test_invalid_timeouts_are_rejected_before_any_output(self):
        for timeout in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                backup_database(self.source, self.root / "never.db", timeout=timeout)
        self.assertFalse((self.root / "never.db").exists())


class MaintenanceCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "archive.db"
        with MemoryBook(self.source) as book:
            book.ingest(session())

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_explicit_database_ignores_broken_capture_config_and_never_constructs_book(self):
        config = self.root / "broken.json"
        config.write_text("broken JSON")
        with patch.dict(os.environ, {"MEMORY_BOOK_CONFIG": str(config)}, clear=False), \
                patch("memory_book.cli.MemoryBook", side_effect=AssertionError("maintenance must not migrate")):
            for command in (["check-database"], ["backup", "--output", str(self.root / "snapshot.db")]):
                code, output, error = self.run_cli("--db", str(self.source), *command)
                self.assertEqual((code, error), (0, ""))
                self.assertTrue(json.loads(output)["ok"])

    def test_default_command_uses_configured_database_and_reports_json(self):
        from memory_book.sync import SyncConfig, save_config
        config = self.root / "config.json"
        save_config(SyncConfig(database=self.source, state_path=self.root / "state.json"), config)
        environment = {"MEMORY_BOOK_CONFIG": str(config), "MEMORY_BOOK_HOME": str(self.root / "wrong")}
        with patch.dict(os.environ, environment, clear=True):
            code, output, error = self.run_cli("backup", "--output", str(self.root / "snapshot.db"))
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["source"], str(self.source))

    def test_check_failure_and_bad_source_have_distinct_nonzero_exits(self):
        with contextlib.closing(sqlite3.connect(self.source)) as db, db:
            db.execute("UPDATE pages SET project_id='missing'")
        code, output, _ = self.run_cli("--db", str(self.source), "check-database")
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output)["ok"])
        missing = self.root / "never-created.db"
        code, output, error = self.run_cli("--db", str(missing), "check-database")
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("memory-book:", error)
        self.assertFalse(missing.exists())

    def test_runtime_repair_diagnostics_do_not_change_structural_success_exit(self):
        with contextlib.closing(sqlite3.connect(self.source)) as db, db:
            db.execute("DROP TRIGGER meta_revision_require_lexical")
        for command in (["check-database"], ["backup", "--output", str(self.root / "repairable-snapshot.db")]):
            code, output, error = self.run_cli("--db", str(self.source), *command)
            self.assertEqual((code, error), (0, ""))
            result = json.loads(output)
            self.assertTrue(result["ok"])
            self.assertEqual(result["runtime_state"], "repair_required")
            self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
