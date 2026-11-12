"""Explicit benchmark source pins must not silently use the historical default."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from benchmarks.competitors import billion, claude_mem


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ExplicitUpstreamPins(unittest.TestCase):
    def test_billion_passes_selected_lock_to_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "selected.json"
            lock.write_text(json.dumps({"files": []}))
            with patch.object(billion, "fetch_bytes", side_effect=AssertionError("unexpected download")), \
                    patch.object(billion.subprocess, "run") as compiler:
                compiler.return_value.returncode = 0
                result = billion.prepare(root / "cache", offline=True, lock_path=lock)
            self.assertEqual(Path(compiler.call_args.args[0][-1]), lock)
            self.assertEqual(result, root / "cache" / ".memory-book-js")

    def test_billion_selected_source_still_checks_git_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            content = b"unchanged source"
            (cache / "source.ts").write_bytes(content)
            lock = root / "selected.json"
            lock.write_text(json.dumps({"files": [{"path": "source.ts", "bytes": len(content),
                "sha256": sha(content), "git_blob_sha": "0" * 40}]}))
            with patch.object(billion.subprocess, "run") as compiler:
                with self.assertRaisesRegex(ValueError, "integrity"):
                    billion.prepare(cache, offline=True, lock_path=lock)
                compiler.assert_not_called()

    def test_claude_selected_archive_and_metadata_are_bound_to_same_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            archive = cache / "selected-source.tar.gz"
            files = {"src/services/sqlite/SessionStore.ts": b"export {};",
                "src/services/sqlite/SessionSearch.ts": b"export {};",
                "package.json": b'{"version":"test-selected"}', "LICENSE": b"fixture"}
            with tarfile.open(archive, "w:gz") as stream:
                for path, data in files.items():
                    entry = tarfile.TarInfo("upstream/" + path)
                    entry.size = len(data)
                    stream.addfile(entry, io.BytesIO(data))
            executable = b"fake executable; never executed"
            runtime = cache / "selected-runtime.zip"
            with zipfile.ZipFile(runtime, "w") as stream:
                stream.writestr("bin/bun", executable)
            specification = {"repository": "fixture/source", "commit": "selected-commit",
                "package_version": "test-selected", "license": "fixture", "source_url": "fixture",
                "source_archive": {"name": archive.name, "bytes": archive.stat().st_size,
                    "sha256": sha(archive.read_bytes())},
                "runtime": {"name": runtime.name, "bytes": runtime.stat().st_size,
                    "sha256": sha(runtime.read_bytes()), "member": "bin/bun",
                    "binary_bytes": len(executable), "binary_sha256": sha(executable)}}
            lock = root / "selected.json"
            lock.write_text(json.dumps(specification))
            with patch.object(claude_mem.platform, "system", return_value="Linux"), \
                    patch.object(claude_mem.platform, "machine", return_value="x86_64"), \
                    patch.object(claude_mem, "fetch_bytes", side_effect=AssertionError("unexpected download")):
                binary, source, expected, metadata = claude_mem.prepare(cache, offline=True, lock_path=lock)
            self.assertEqual(expected, files)
            self.assertEqual(binary.read_bytes(), executable)
            self.assertEqual(metadata["commit"], "selected-commit")
            self.assertEqual(metadata["lock_sha256"], sha(lock.read_bytes()))
            self.assertEqual((source / "package.json").read_bytes(), files["package.json"])


if __name__ == "__main__":
    unittest.main()
