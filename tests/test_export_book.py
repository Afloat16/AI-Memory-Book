"""Consistent, retryable directory exports under sync and output races."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.cli import export_book


def session(answer="ORIGINAL_EVIDENCE", sid="session-1"):
    return {
        "project": "demo", "session_id": sid, "task_id": "task-1",
        "title": "Implementation decision", "created_at": "2026-11-15T12:00:00Z",
        "messages": [{"role": "user", "content": "Which implementation should we use?"},
                     {"role": "assistant", "content": answer}],
    }


class ExportBookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "memory.db"
        self.book = MemoryBook(self.database)
        self.book.ingest(session())

    def tearDown(self):
        self.book.close()
        self.temporary.cleanup()

    def assert_no_staging(self):
        self.assertEqual(list(self.root.glob(".memory-book-export-*")), [])

    def assert_complete_export(self, output, expected):
        self.assertTrue((output / "INDEX.md").is_file())
        self.assertEqual(json.loads((output / "sessions.json").read_text(encoding="utf-8")), expected)
        pages = list((output / "pages").glob("*.md"))
        self.assertTrue(pages)
        return "\n".join(page.read_text(encoding="utf-8") for page in pages)

    def test_export_remains_one_snapshot_while_an_independent_writer_updates(self):
        before = self.book.export("demo")
        output = self.root / "export"
        original_read = self.book.read
        updates = []
        with MemoryBook(self.database) as writer:
            def read_then_update(*args, **kwargs):
                item = original_read(*args, **kwargs)
                if not updates:
                    updates.append(writer.ingest(session("REPLACEMENT_EVIDENCE")))
                return item

            with patch.object(self.book, "read", side_effect=read_then_update):
                export_book(self.book, "demo", str(output))

        self.assertEqual(len(updates), 1)
        markdown = self.assert_complete_export(output, before)
        self.assertIn("ORIGINAL_EVIDENCE", markdown)
        self.assertNotIn("REPLACEMENT_EVIDENCE", markdown)
        self.assertFalse(self.book.db.in_transaction)
        self.assertIn("REPLACEMENT_EVIDENCE", self.book.export("demo")[0]["messages"][1]["content"])
        with MemoryBook(":memory:") as restored:
            for payload in json.loads((output / "sessions.json").read_text(encoding="utf-8")):
                restored.ingest(payload)
            self.assertEqual(restored.export("demo"), before)
            for page in (output / "pages").glob("*.md"):
                self.assertTrue(page.read_text(encoding="utf-8").endswith(restored.read(page.stem)["content"]))
        self.assert_no_staging()

    def test_destination_stays_absent_or_empty_until_all_files_are_written(self):
        expected = self.book.export("demo")
        write_text = Path.write_text
        for exists in (False, True):
            with self.subTest(existing_empty_directory=exists):
                output = self.root / f"complete-{exists}"
                if exists:
                    output.mkdir()
                writes = []

                def check_visibility(path, *args, **kwargs):
                    self.assertEqual(output.exists(), exists)
                    if exists:
                        self.assertEqual(list(output.iterdir()), [])
                    writes.append(path.name)
                    return write_text(path, *args, **kwargs)

                with patch.object(Path, "write_text", check_visibility):
                    result = export_book(self.book, "demo", str(output))
                self.assertIn("INDEX.md", writes)
                self.assertIn("sessions.json", writes)
                self.assertEqual(result["output"], str(output.resolve()))
                self.assertEqual(result["pages"], len(list((output / "pages").glob("*.md"))))
                self.assert_complete_export(output, expected)
                self.assert_no_staging()

    def test_write_failure_cleans_staging_preserves_target_and_allows_retry(self):
        expected = self.book.export("demo")
        write_text = Path.write_text
        for exists in (False, True):
            for failed_name in ("INDEX.md", "sessions.json"):
                with self.subTest(existing_empty_directory=exists, failure=failed_name):
                    output = self.root / f"write-failure-{exists}-{failed_name}"
                    if exists:
                        output.mkdir()

                    def fail_write(path, *args, **kwargs):
                        if path.name == failed_name:
                            raise OSError("simulated output failure")
                        return write_text(path, *args, **kwargs)

                    with patch.object(Path, "write_text", fail_write), self.assertRaisesRegex(OSError, "simulated"):
                        export_book(self.book, "demo", str(output))
                    self.assertFalse(self.book.db.in_transaction)
                    self.assertEqual(output.exists(), exists)
                    if exists:
                        self.assertEqual(list(output.iterdir()), [])
                    self.assert_no_staging()
                    export_book(self.book, "demo", str(output))
                    self.assert_complete_export(output, expected)

    def test_interrupted_read_releases_snapshot_and_allows_retry(self):
        output = self.root / "interrupted"
        with patch.object(self.book, "export", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            export_book(self.book, "demo", str(output))
        self.assertFalse(self.book.db.in_transaction)
        self.assertFalse(output.exists())
        self.assert_no_staging()
        export_book(self.book, "demo", str(output))
        self.assert_complete_export(output, self.book.export("demo"))

    def test_publication_failure_restores_only_a_removed_empty_target(self):
        for exists in (False, True):
            with self.subTest(existing_empty_directory=exists):
                output = self.root / f"rename-failure-{exists}"
                if exists:
                    output.mkdir()
                with patch("memory_book.cli.os.rename", side_effect=OSError("simulated rename failure")), \
                        self.assertRaisesRegex(OSError, "simulated rename failure"):
                    export_book(self.book, "demo", str(output))
                self.assertFalse(self.book.db.in_transaction)
                self.assertEqual(output.exists(), exists)
                if exists:
                    self.assertEqual(list(output.iterdir()), [])
                self.assert_no_staging()
                export_book(self.book, "demo", str(output))
                self.assert_complete_export(output, self.book.export("demo"))

    def test_preexisting_nonempty_directory_and_file_are_untouched(self):
        directory = self.root / "occupied"
        directory.mkdir()
        owned_file = directory / "keep.txt"
        owned_file.write_bytes(b"user data")
        regular_file = self.root / "regular-file"
        regular_file.write_bytes(b"more user data")
        for output in (directory, regular_file):
            with self.subTest(target=output.name), self.assertRaisesRegex(ValueError, "absent or an empty directory"):
                export_book(self.book, "demo", str(output))
        self.assertEqual(owned_file.read_bytes(), b"user data")
        self.assertEqual(list(directory.iterdir()), [owned_file])
        self.assertEqual(regular_file.read_bytes(), b"more user data")
        self.assert_no_staging()

    def test_nonempty_directory_or_file_created_at_publication_is_preserved(self):
        rename = os.rename
        for exists in (False, True):
            for target_kind in ("directory", "file"):
                with self.subTest(existing_empty_directory=exists, concurrent_target=target_kind):
                    output = self.root / f"race-{exists}-{target_kind}"
                    if exists:
                        output.mkdir()

                    def race_rename(source, destination):
                        self.assertFalse(self.book.db.in_transaction)
                        self.assert_complete_export(Path(source), self.book.export("demo"))
                        if target_kind == "directory":
                            output.mkdir(exist_ok=True)
                            (output / "keep.txt").write_bytes(b"concurrent user data")
                        else:
                            if output.exists():
                                output.rmdir()
                            output.write_bytes(b"concurrent user data")
                        return rename(source, destination)

                    with patch("memory_book.cli.os.rename", side_effect=race_rename), self.assertRaises(OSError):
                        export_book(self.book, "demo", str(output))
                    if target_kind == "directory":
                        self.assertEqual([path.name for path in output.iterdir()], ["keep.txt"])
                        self.assertEqual((output / "keep.txt").read_bytes(), b"concurrent user data")
                    else:
                        self.assertEqual(output.read_bytes(), b"concurrent user data")
                    self.assert_no_staging()

    def test_target_filled_before_publication_is_rejected_without_mutation(self):
        output = self.root / "filled-target"
        original_export = self.book.export

        def fill_target(project):
            output.mkdir()
            (output / "keep.txt").write_text("new owner", encoding="utf-8")
            return original_export(project)

        with patch.object(self.book, "export", side_effect=fill_target), \
                self.assertRaisesRegex(ValueError, "absent or an empty directory"):
            export_book(self.book, "demo", str(output))
        self.assertEqual([path.name for path in output.iterdir()], ["keep.txt"])
        self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "new owner")
        self.assertFalse(self.book.db.in_transaction)
        self.assert_no_staging()

    def test_symlink_targets_are_preserved_before_and_during_publication(self):
        target = self.root / "link-target"
        target.mkdir()
        probe = self.root / "link-probe"
        try:
            probe.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Directory symlinks are unavailable: {exc}")
        probe.unlink()
        rename = os.rename
        for phase in ("initial", "publish"):
            with self.subTest(phase=phase):
                output = self.root / f"symlink-{phase}"
                if phase == "initial":
                    output.symlink_to(target, target_is_directory=True)
                    with self.assertRaisesRegex(ValueError, "without symlinks"):
                        export_book(self.book, "demo", str(output))
                else:
                    def race_rename(source, destination):
                        output.symlink_to(target, target_is_directory=True)
                        return rename(source, destination)

                    with patch("memory_book.cli.os.rename", side_effect=race_rename), self.assertRaises(OSError):
                        export_book(self.book, "demo", str(output))
                self.assertTrue(output.is_symlink())
                self.assertEqual(list(target.iterdir()), [])
                self.assert_no_staging()
                output.unlink()

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_windows_directory_junction_is_not_followed_or_removed(self):
        target = self.root / "junction-target"
        target.mkdir()
        output = self.root / "junction-output"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(output), str(target)],
                       check=True, capture_output=True)
        try:
            with self.assertRaisesRegex(ValueError, "without symlinks or junctions"):
                export_book(self.book, "demo", str(output))
            self.assertTrue(output.is_dir())
            self.assertEqual(list(target.iterdir()), [])
            self.assert_no_staging()
        finally:
            output.rmdir()

    def test_caller_transaction_is_neither_committed_nor_rolled_back(self):
        output = self.root / "outer-transaction"
        self.book.db.execute("BEGIN")
        try:
            with self.assertRaisesRegex(ValueError, "active transaction"):
                export_book(self.book, "demo", str(output))
            self.assertTrue(self.book.db.in_transaction)
            self.assertFalse(output.exists())
            self.assert_no_staging()
        finally:
            self.book.db.execute("ROLLBACK")
        export_book(self.book, "demo", str(output))
        self.assert_complete_export(output, self.book.export("demo"))

    def test_unknown_project_publishes_nothing(self):
        output = self.root / "unknown-project"
        with self.assertRaises(KeyError):
            export_book(self.book, "missing", str(output))
        self.assertFalse(output.exists())
        self.assertFalse(self.book.db.in_transaction)
        self.assert_no_staging()

    def test_empty_current_directory_is_rejected_before_staging_and_remains_usable(self):
        directory = self.root / "caller-cwd"
        directory.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(directory)
            for output in (".", str(directory), "../caller-cwd"):
                with self.subTest(output=output), \
                        patch("tempfile.TemporaryDirectory", side_effect=AssertionError("must reject cwd before staging")), \
                        self.assertRaisesRegex(ValueError, "current working directory; choose a new subdirectory"):
                    export_book(self.book, "demo", output)
                self.assertTrue(Path.cwd().samefile(directory))
                self.assertEqual(list(directory.iterdir()), [])
                self.assertFalse(self.book.db.in_transaction)
                self.assert_no_staging()
                probe = Path("still-usable.txt")
                probe.write_text("caller can still use its cwd", encoding="utf-8")
                self.assertEqual((directory / probe).read_text(encoding="utf-8"), "caller can still use its cwd")
                probe.unlink()
            export_book(self.book, "demo", "new-export")
            self.assert_complete_export(directory / "new-export", self.book.export("demo"))
            self.assertEqual(list(directory.glob(".memory-book-export-*")), [])
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
