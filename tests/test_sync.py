from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.sync import (SyncConfig, WatchSource, load_config,
                              project_for_workspace, save_config, sync_once,
                              sync_status, watch)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "transcripts"
        self.source.mkdir()
        self.config = SyncConfig(self.root / "book.sqlite3", self.root / "state.json",
                                 self.root / "worker.jsonl", poll_interval=.05,
                                 sources=(WatchSource("fixture", self.source, "canonical"),))

    def payload(self, *, project="alpha", session_id="s1", answer="Remember the cobalt value."):
        value = {"project": project, "messages": [{"role": "user", "content": "Which value?"},
                                                   {"role": "assistant", "content": answer}]}
        if session_id is not None:
            value["session_id"] = session_id
        return value

    def write(self, name="conversation.json", payload=None):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload or self.payload(), ensure_ascii=False), encoding="utf-8")
        return path

    def native_config(self, format="claude-code", **options):
        return replace(self.config, sources=(WatchSource("fixture", self.source, format, **options),))

    def write_codex(self, name, cwd, session_id="s1", answer="Configured response"):
        path = self.source / name
        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": cwd}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": "Configuration?"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": answer}},
        ]
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
        return path

    def test_idle_poll_is_metadata_only_and_updates_are_idempotent(self):
        path = self.write()
        first = sync_once(self.config)
        self.assertEqual((first["imported"], first["updated_sessions"]), (1, 1))
        with patch("memory_book.sync._read_snapshot", side_effect=AssertionError("unchanged file read")):
            self.assertEqual(sync_once(self.config)["skipped"], 1)
        with MemoryBook(self.config.database) as book:
            revision = book.revision
        stamp = path.stat()
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
        self.assertEqual(sync_once(self.config)["skipped"], 1)  # Same bytes, different stat.
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.revision, revision)
        self.write(payload=self.payload(answer="Updated to the amber value."))
        self.assertEqual(sync_once(self.config)["updated_sessions"], 1)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)
            self.assertIn("amber", book.get_session("alpha", "s1")["messages"][1]["content"])

    def test_fallback_identity_is_stable_when_a_transcript_grows(self):
        source = self.payload(session_id=None)
        self.write(payload=source)
        sync_once(self.config)
        with MemoryBook(self.config.database) as book:
            first = book.export()[0]["session_id"]
        source["messages"].append({"role": "user", "content": "Another question"})
        self.write(payload=source)
        sync_once(self.config)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)
            self.assertEqual(book.export()[0]["session_id"], first)
            self.assertEqual(len(book.export()[0]["messages"]), 3)

    def test_partial_jsonl_append_preserves_complete_prefix_then_updates(self):
        config = self.native_config(project="alpha")
        path = self.source / "session.jsonl"
        question = {"type": "user", "sessionId": "native", "message": {"role": "user", "content": "Status?"}}
        answer = {"type": "assistant", "sessionId": "native", "message": {"role": "assistant", "content": "Complete answer"}}
        prefix = json.dumps(question) + "\n"
        full_answer = json.dumps(answer)
        path.write_text(prefix + full_answer[:-8], encoding="utf-8")
        result = sync_once(config)
        self.assertEqual((result["imported"], result["partial"], result["errors"]), (1, 1, 0))
        with MemoryBook(config.database) as book:
            self.assertEqual(len(book.get_session("alpha", "native")["messages"]), 1)
        path.write_text(prefix + full_answer + "\n", encoding="utf-8")
        self.assertEqual(sync_once(config)["updated_sessions"], 1)
        with MemoryBook(config.database) as book:
            self.assertEqual(len(book.get_session("alpha", "native")["messages"]), 2)
            self.assertEqual(book.stats()["sessions"], 1)

    def test_partial_utf8_tail_is_deferred_without_losing_prefix(self):
        config = self.native_config(project="alpha")
        record = {"type": "user", "sessionId": "native", "message": {"role": "user", "content": "问题"}}
        path = self.source / "session.jsonl"
        path.write_bytes((json.dumps(record) + "\n").encode() + b'{"content":"\xe4\xb8')
        result = sync_once(config)
        self.assertEqual((result["imported"], result["partial"], result["errors"]), (1, 1, 0))

    def test_malformed_complete_line_is_isolated_and_repair_is_retried(self):
        good = self.write("good.json")
        broken = self.write("broken.json", self.payload(session_id="broken"))
        broken.write_text('{"messages": broken JSON}\n', encoding="utf-8")
        # I/O and scheduling must not consume the 50 ms backoff under test.
        with patch("memory_book.sync.time.time", return_value=1000.0) as clock:
            result = sync_once(self.config)
            self.assertEqual((result["imported"], result["errors"]), (1, 1))
            clock.return_value = 1000.025
            deferred = sync_once(self.config)
            self.assertEqual((deferred["deferred"], deferred["errors"]), (1, 0))
            clock.return_value = 1000.051
            retried = sync_once(self.config)
            self.assertEqual((retried["deferred"], retried["errors"]), (0, 1))
            # A changed file bypasses the next backoff deadline immediately.
            clock.return_value = 1000.052
            broken.write_text(json.dumps(self.payload(session_id="broken")), encoding="utf-8")
            self.assertEqual(sync_once(self.config)["updated_sessions"], 1)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 2)
        self.assertTrue(good.exists())

    def test_corrupt_update_leaves_previous_session_intact(self):
        path = self.write()
        sync_once(self.config)
        path.write_text('{"session_id":"s1","messages": [', encoding="utf-8")
        self.assertEqual(sync_once(self.config)["errors"], 1)
        with MemoryBook(self.config.database) as book:
            self.assertIn("cobalt", book.get_session("alpha", "s1")["messages"][1]["content"])

    def test_metadata_maps_namesake_workspaces_to_separate_projects(self):
        self.write_codex("rollout-a.jsonl", "/team-one/api", answer="first")
        self.write_codex("rollout-b.jsonl", "/team-two/api", answer="second")
        config = self.native_config("codex")
        result = sync_once(config)
        self.assertEqual(result["updated_sessions"], 2)
        with MemoryBook(config.database) as book:
            self.assertEqual(book.stats()["projects"], 2)
            self.assertEqual(book.get_session(project_for_workspace("/team-one/api"), "s1")["messages"][1]["content"], "first")
            self.assertEqual(book.get_session(project_for_workspace("/team-two/api"), "s1")["messages"][1]["content"], "second")

    def test_workspace_filter_is_exact_and_does_not_guess_missing_metadata(self):
        self.write_codex("rollout-a.jsonl", "/team/api")
        self.write_codex("rollout-b.jsonl", "/team/api-other")
        self.write_codex("rollout-c.jsonl", None)
        config = self.native_config("codex", workspace="/team/api")
        result = sync_once(config)
        self.assertEqual((result["imported"], result["ignored"]), (1, 2))
        with MemoryBook(config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)

    def test_missing_project_metadata_is_an_error_instead_of_global_merge(self):
        source = self.payload()
        del source["project"]
        self.write(payload=source)
        self.assertEqual(sync_once(self.config)["errors"], 1)
        self.assertEqual(sync_status(self.config)["last_cycle"]["error_details"][0]["code"], "missing_project_metadata")

    def test_explicit_project_and_task_overrides(self):
        self.write()
        config = self.native_config("canonical", project="override", task_id="shared-task")
        self.assertEqual(sync_once(config)["updated_sessions"], 1)
        with MemoryBook(config.database) as book:
            item = book.get_session("override", "s1")
            self.assertEqual(item["task_id"], "shared-task")

    def test_duplicate_session_ids_do_not_silently_overwrite_another_file(self):
        self.write("first.json")
        self.write("second.json", self.payload(answer="conflicting copy"))
        result = sync_once(self.config)
        self.assertEqual((result["imported"], result["errors"]), (1, 1))
        self.assertEqual(result["error_details"][0]["code"], "session_id_conflict")

    def test_removed_source_file_never_deletes_memory(self):
        path = self.write()
        sync_once(self.config)
        path.unlink()
        self.assertEqual(sync_once(self.config)["missing"], 1)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)

    def test_size_limit_and_unknown_files(self):
        self.write("large.json", self.payload(answer="x" * 1024))
        self.write("settings.json", self.payload(session_id="must-not-import"))
        (self.source / "notes.txt").write_text("not a transcript", encoding="utf-8")
        (self.source / "credentials.json").write_text("must not read", encoding="utf-8")
        config = replace(self.config, max_file_bytes=512)
        result = sync_once(config)
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["error_details"][0]["code"], "file_too_large")

    def test_symlink_file_and_directory_are_ignored(self):
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "conversation.json"
        target.write_text(json.dumps(self.payload()), encoding="utf-8")
        try:
            (self.source / "link.json").symlink_to(target)
            (self.source / "linked-folder").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        self.assertEqual(sync_once(self.config)["scanned"], 0)

    def test_logs_and_state_never_store_message_bodies(self):
        private_text = "private-transcript-marker-4872"
        self.write(payload=self.payload(answer=private_text))
        sync_once(self.config)
        self.assertNotIn(private_text, self.config.log_path.read_text())
        self.assertNotIn(private_text, self.config.state_path.read_text())
        self.assertIn("file_imported", self.config.log_path.read_text())

    def test_worker_stops_promptly_and_rejects_a_second_worker(self):
        self.write()
        stop, ready = threading.Event(), threading.Event()
        errors = []
        config = replace(self.config, poll_interval=60)
        def run_worker():
            try:
                watch(config, stop_event=stop, on_cycle=lambda _: ready.set())
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run_worker)
        worker.start()
        try:
            self.assertTrue(ready.wait(3))
            self.assertTrue(sync_status(config)["worker"]["running"])
            with self.assertRaisesRegex(RuntimeError, "already holds"):
                sync_once(config)
        finally:
            started = time.monotonic()
            stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.monotonic() - started, 3)
        self.assertFalse(errors, errors)
        self.assertFalse(sync_status(config)["worker"]["running"])

    def test_config_round_trip_and_status_do_not_open_sources(self):
        config = replace(self.config, reader_port=0, reader_host="0.0.0.0")
        path = self.root / "config.json"
        with patch("memory_book.sync._paths", side_effect=AssertionError("source scan")):
            save_config(config, path)
            loaded = load_config(path)
            self.assertEqual(config, loaded)
            self.assertEqual(sync_status(loaded)["tracked_files"], 0)

    def test_workspace_normalization_is_host_independent(self):
        from memory_book.sync import _workspace_key
        self.assertEqual(_workspace_key("/team/one/../api"), "/team/api")
        self.assertEqual(_workspace_key("C:/Work/API/../Project"), "c:\\work\\project")
        self.assertEqual(project_for_workspace("C:/Work/Project"), project_for_workspace("c:\\work\\project"))

    def test_corrupt_state_is_not_silently_replaced(self):
        self.config.state_path.write_text("broken state", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "state is corrupt"):
            sync_once(self.config)
        self.assertEqual(self.config.state_path.read_text(), "broken state")

    def test_gemini_legacy_snapshot_is_skipped_after_jsonl_migration(self):
        metadata = {"sessionId": "gemini-one", "projectHash": "bucket", "directories": ["/team/project"]}
        old = {**metadata, "messages": [{"id": "m1", "type": "user", "content": "old snapshot"}]}
        self.write("session-one.json", old)
        records = [metadata, {"id": "m1", "type": "user", "content": "active stream"}]
        (self.source / "session-one.jsonl").write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        config = self.native_config("gemini")
        result = sync_once(config)
        self.assertEqual((result["scanned"], result["updated_sessions"], result["errors"]), (1, 1, 0))
        with MemoryBook(config.database) as book:
            self.assertEqual(book.export()[0]["messages"][0]["content"], "active stream")

    def test_switching_database_rebinds_manifest_instead_of_skipping_sources(self):
        self.write()
        sync_once(self.config)
        second = replace(self.config, database=self.root / "second.sqlite3")
        result = sync_once(second)
        self.assertTrue(result["database_rebound"])
        self.assertEqual(result["updated_sessions"], 1)
        with MemoryBook(second.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)

    def test_recreated_database_at_same_path_rebinds_manifest(self):
        self.write()
        sync_once(self.config)
        self.config.database.unlink()
        result = sync_once(self.config)
        self.assertTrue(result["database_rebound"])
        self.assertEqual(result["updated_sessions"], 1)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)

    def test_renamed_source_releases_ownership_without_duplicate_fallback(self):
        self.write(payload=self.payload(session_id=None))
        sync_once(self.config)
        renamed = replace(self.config, sources=(WatchSource("new-label", self.source, "canonical"),))
        result = sync_once(renamed)
        self.assertEqual(result["errors"], 0)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)
        self.assertEqual(sync_status(renamed)["files_by_status"]["inactive"], 1)

    def test_moved_native_file_does_not_wait_for_old_ownership(self):
        source = self.write()
        sync_once(self.config)
        source.rename(self.source / "renamed.json")
        result = sync_once(self.config)
        self.assertEqual(result["errors"], 0)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)

    def test_stop_is_checked_between_active_files(self):
        self.write("one.json", self.payload(session_id="one"))
        self.write("two.json", self.payload(session_id="two"))
        stop = threading.Event()
        original = MemoryBook.ingest
        def stop_after_one(book, payload):
            result = original(book, payload)
            stop.set()
            return result
        with patch.object(MemoryBook, "ingest", stop_after_one):
            result = watch(self.config, stop_event=stop)
        self.assertEqual(result["updated_sessions"], 1)
        with MemoryBook(self.config.database) as book:
            self.assertEqual(book.stats()["sessions"], 1)
        self.assertEqual(sync_once(self.config)["updated_sessions"], 1)


if __name__ == "__main__":
    unittest.main()
