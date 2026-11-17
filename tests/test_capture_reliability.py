from __future__ import annotations

import ctypes
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from memory_book import MemoryBook, importers, sync


class ProcessStatusTests(unittest.TestCase):
    def setUp(self):
        self.contexts = ExitStack()
        self.addCleanup(self.contexts.close)

    def status(self, pid):
        state = {"files": {}, "worker": {"running": True, "pid": pid}}
        config = SimpleNamespace(state_path=None, sources=())
        with patch.object(sync, "_load_state", return_value=state):
            result = sync.sync_status(config)
        self.assertTrue(state["worker"]["running"], "status must not alter the manifest")
        return result["worker"]

    def windows(self, *, handle=0x1234567887654321, result=0x102, error=0):
        kernel = SimpleNamespace(OpenProcess=Mock(return_value=handle),
                                 WaitForSingleObject=Mock(return_value=result),
                                 CloseHandle=Mock(return_value=True))
        loader = self.contexts.enter_context(patch.object(ctypes, "WinDLL", return_value=kernel, create=True))
        self.contexts.enter_context(patch.object(ctypes, "get_last_error", return_value=error, create=True))
        self.contexts.enter_context(patch.object(ctypes, "WinError", side_effect=lambda code: OSError(code, "Windows error"), create=True))
        system = SimpleNamespace(name="nt", kill=Mock(side_effect=AssertionError("Windows status must not signal")))
        self.contexts.enter_context(patch.object(sync, "os", system))
        return kernel, loader, system

    def test_windows_status_waits_without_signalling_and_closes_handle(self):
        kernel, loader, system = self.windows()
        worker = self.status(123)
        self.assertTrue(worker["running"])
        self.assertNotIn("stale_state", worker)
        loader.assert_called_once_with("kernel32", use_last_error=True)
        kernel.OpenProcess.assert_called_once_with(0x00100000, False, 123)
        self.assertIs(kernel.OpenProcess.restype, wintypes.HANDLE)
        kernel.WaitForSingleObject.assert_called_once_with(0x1234567887654321, 0)
        kernel.CloseHandle.assert_called_once_with(0x1234567887654321)
        system.kill.assert_not_called()

    def test_windows_exited_process_is_stale_and_handle_is_closed(self):
        kernel, _, _ = self.windows(result=0)
        self.assertEqual(self.status(123), {"running": False, "pid": 123, "stale_state": True})
        kernel.CloseHandle.assert_called_once_with(0x1234567887654321)

    def test_windows_failed_wait_still_closes_handle(self):
        kernel, _, _ = self.windows(result=0xFFFFFFFF, error=6)
        self.assertFalse(self.status(123)["running"])
        kernel.CloseHandle.assert_called_once_with(0x1234567887654321)

    def test_windows_missing_process_has_no_handle_to_close(self):
        kernel, _, _ = self.windows(handle=None, error=87)
        self.assertFalse(self.status(123)["running"])
        kernel.WaitForSingleObject.assert_not_called()
        kernel.CloseHandle.assert_not_called()

    def test_windows_access_denied_does_not_claim_the_process_exited(self):
        kernel, _, _ = self.windows(handle=None, error=5)
        self.assertTrue(self.status(123)["running"])
        kernel.WaitForSingleObject.assert_not_called()
        kernel.CloseHandle.assert_not_called()

    def test_invalid_windows_pids_are_not_probed_or_wrapped(self):
        kernel, loader, system = self.windows()
        for pid in (None, True, False, [], {}, 0, -1, "0", "-1", "bad", 1.5,
                    0x100000000, "4294967296", "9" * 100):
            with self.subTest(pid=pid):
                self.assertFalse(self.status(pid)["running"])
        loader.assert_not_called()
        kernel.OpenProcess.assert_not_called()
        system.kill.assert_not_called()

    def test_posix_permission_denied_still_means_the_process_exists(self):
        system = SimpleNamespace(name="posix", kill=Mock(side_effect=PermissionError()))
        with patch.object(sync, "os", system):
            self.assertTrue(self.status("123")["running"])
        system.kill.assert_called_once_with(123, 0)

    def test_posix_missing_or_oversized_pid_is_stale(self):
        for error in (ProcessLookupError(), OverflowError()):
            with self.subTest(error=type(error).__name__):
                system = SimpleNamespace(name="posix", kill=Mock(side_effect=error))
                with patch.object(sync, "os", system):
                    self.assertFalse(self.status(123)["running"])

    @unittest.skipUnless(os.name == "nt", "real Windows process handles")
    def test_windows_status_leaves_owned_child_alive_and_detects_exit_259(self):
        # Only this test's child is ever addressed. Exit 259 must not be confused
        # with STILL_ACTIVE, which is why the implementation waits on a handle.
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read(1); sys.exit(259)"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(3):
                self.assertTrue(self.status(child.pid)["running"])
                self.assertIsNone(child.poll(), "reading status terminated the child")
            _, stderr = child.communicate(b"x", timeout=10)
            self.assertEqual(child.returncode, 259, stderr.decode(errors="replace"))
            self.assertFalse(self.status(child.pid)["running"])
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)


class TranscriptBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    @staticmethod
    def session(content, session_id="one"):
        return {"project": "example", "session_id": session_id,
                "messages": [{"role": "user", "content": content}]}

    def test_jsonl_preserves_unicode_separators_with_each_record_ending(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            records = [self.session("before" + separator + "after"), self.session("second", "two")]
            for ending in ("\n", "\r\n", "\r"):
                with self.subTest(separator=repr(separator), ending=repr(ending)):
                    text = ending.join(json.dumps(record, ensure_ascii=False) for record in records) + ending
                    sessions = importers.parse_sessions(text, "source.jsonl", format="canonical")
                    self.assertEqual([item["messages"] for item in sessions], [item["messages"] for item in records])
                    self.assertEqual([item["session_id"] for item in sessions], ["one", "two"])

    def test_incremental_capture_preserves_unicode_and_completes_partial_tail(self):
        content = "before\u0085middle\u2028next\u2029after"
        question = {"type": "user", "sessionId": "native", "message": {"role": "user", "content": content}}
        answer = {"type": "assistant", "sessionId": "native", "message": {"role": "assistant", "content": content}}
        for index, ending in enumerate(("\n", "\r\n", "\r")):
            with self.subTest(ending=repr(ending)):
                source = self.root / str(index)
                source.mkdir()
                config = sync.SyncConfig(self.root / f"{index}.db", self.root / f"{index}.state.json",
                                         sources=(sync.WatchSource("native", source, "claude-code", project="example"),))
                path = source / "session.jsonl"
                prefix = json.dumps(question, ensure_ascii=False) + ending
                tail = json.dumps(answer, ensure_ascii=False)
                path.write_bytes((prefix + tail[:-5]).encode("utf-8"))
                first = sync.sync_once(config)
                self.assertEqual((first["imported"], first["partial"], first["errors"]), (1, 1, 0))
                with MemoryBook(config.database) as book:
                    self.assertEqual(book.get_session("example", "native")["messages"], [question["message"]])
                path.write_bytes((prefix + tail).encode("utf-8"))  # A complete final record needs no newline.
                second = sync.sync_once(config)
                self.assertEqual((second["updated_sessions"], second["partial"], second["errors"]), (1, 0, 0))
                with MemoryBook(config.database) as book:
                    self.assertEqual(book.get_session("example", "native")["messages"], [question["message"], answer["message"]])
                self.assertEqual(sync.sync_once(config)["skipped"], 1)

    def test_partial_utf8_tail_keeps_complete_cr_lf_prefix_and_rejects_complete_error(self):
        for ending in ("\n", "\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                prefix = json.dumps(self.session("literal\u2028separator"), ensure_ascii=False) + ending
                data = b"\xef\xbb\xbf" + prefix.encode("utf-8") + b'{"content":"\xe4\xb8'
                self.assertEqual(sync._complete_text(data, Path("source.jsonl"), "canonical"), (prefix, True))
                with self.assertRaisesRegex(ValueError, "invalid_utf8"):
                    sync._complete_text(data + ending.encode(), Path("source.jsonl"), "canonical")

    def test_malformed_complete_record_keeps_physical_line_number(self):
        for ending in ("\n", "\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                text = json.dumps(self.session("literal\u2028separator"), ensure_ascii=False) + ending + "{broken}" + ending
                with self.assertRaisesRegex(ValueError, "Malformed JSON/JSONL at line 2"):
                    importers.parse_sessions(text, "source.jsonl", format="canonical")

    def test_import_rejects_file_that_grows_after_size_check(self):
        path = self.root / "growing.json"
        path.write_text(json.dumps(self.session("small")), encoding="utf-8")
        large = json.dumps(self.session("x" * 1024)).encode()
        original_open = Path.open

        def grow_before_read(selected, mode="r", *args, **kwargs):
            if selected == path and mode.startswith("r"):
                with original_open(path, "wb") as handle:
                    handle.write(large)
            return original_open(selected, mode, *args, **kwargs)

        with patch.object(importers, "MAX_IMPORT_BYTES", 256), patch.object(Path, "open", grow_before_read):
            with self.assertRaisesRegex(ValueError, "Transcript exceeds the 64 MiB per-file import limit"):
                importers.load_sessions(path)

    def test_import_read_stops_at_size_limit_plus_one(self):
        path = self.root / "bounded.json"
        path.write_text("{}", encoding="utf-8")
        data = json.dumps(self.session("x" * 1024)).encode()
        sizes = []

        class BoundedReader(io.BytesIO):
            def read(reader, size=-1):
                if not 0 <= size <= 257:
                    raise AssertionError("import attempted an unbounded read")
                sizes.append(size)
                return super().read(size)

        with patch.object(importers, "MAX_IMPORT_BYTES", 256), patch.object(Path, "open", return_value=BoundedReader(data)):
            with self.assertRaisesRegex(ValueError, "Transcript exceeds the 64 MiB per-file import limit"):
                importers.load_sessions(path)
        self.assertTrue(sizes)

    def test_exact_byte_limit_preserves_bom_line_endings_and_fallback_ids(self):
        path = self.root / "exact.jsonl"
        records = [self.session("问题\u2029answer"), self.session("second")]
        for record in records:
            del record["session_id"]
        expected = importers.parse_sessions("\n".join(json.dumps(record, ensure_ascii=False) for record in records), path)
        for ending in ("\n", "\r\n", "\r"):
            for bom in (b"", b"\xef\xbb\xbf"):
                with self.subTest(ending=repr(ending), bom=bool(bom)):
                    data = bom + ending.join(json.dumps(record, ensure_ascii=False) for record in records).encode("utf-8")
                    path.write_bytes(data)
                    with patch.object(importers, "MAX_IMPORT_BYTES", len(data)):
                        self.assertEqual(importers.load_sessions(path), expected)


if __name__ == "__main__":
    unittest.main()
