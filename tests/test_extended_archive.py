"""Exercise restoration safety against the actual saved v0.11 manifest."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.experiments.restore_extended_raw import restore, verify_bundle


MANIFEST = Path(__file__).resolve().parents[1] / "benchmarks/reports/v0.11-extended-lexical/raw-manifest.json"


class ExtendedArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="extended-archive-test-")
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.output = self.temporary / "restored"

    def test_actual_archive_restores_every_original_audited_byte(self):
        manifest = restore(MANIFEST, self.output)
        audit = json.loads((self.output / "attempt1/audit.json").read_text())
        self.assertEqual((audit["status"], audit["packed_responses"], audit["native_calls"]), ("verified", 480, 720))
        self.assertEqual(len(manifest["archives"]), 3)
        for name, digest in audit["files"].items():
            self.assertEqual(hashlib.sha256((self.output / "attempt1" / name).read_bytes()).hexdigest(), digest)
        before = (self.output / "attempt1/raw.jsonl").read_bytes()
        with self.assertRaisesRegex(FileExistsError, "already exists"):
            restore(MANIFEST, self.output)
        self.assertEqual((self.output / "attempt1/raw.jsonl").read_bytes(), before)

    def test_actual_archive_rejects_corrupt_compressed_bytes(self):
        manifest = restore(MANIFEST, self.output)
        path = self.output / manifest["archives"][0]["gzip_path"]
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            verify_bundle(self.output / MANIFEST.name)

    def test_actual_manifest_rejects_path_escape_and_duplicate_destination(self):
        manifest = restore(MANIFEST, self.output)
        manifest_path = self.output / MANIFEST.name
        original_path = manifest["archives"][0]["raw_path"]
        for bad_path in ("../escaped.jsonl", "C:/escaped.jsonl", "attempt1/raw.jsonl:alternate", "\\\\server\\escaped.jsonl"):
            manifest["archives"][0]["raw_path"] = bad_path
            manifest_path.write_text(json.dumps(manifest))
            with self.subTest(path=bad_path), self.assertRaisesRegex(ValueError, "Unsafe manifest path|Manifest paths"):
                verify_bundle(manifest_path)
        self.assertFalse((self.temporary / "escaped.jsonl").exists())
        manifest["archives"][0]["raw_path"] = original_path
        manifest["preserved_files"].append(manifest["preserved_files"][0])
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "Repeated output path"):
            verify_bundle(manifest_path)

    def test_actual_archive_rejects_symlinked_source(self):
        manifest = restore(MANIFEST, self.output)
        relative = manifest["archives"][0]["gzip_path"]
        path = self.output / relative
        path.unlink()
        path.symlink_to(MANIFEST.parent / relative)
        with self.assertRaisesRegex(ValueError, "Symlinked source path"):
            verify_bundle(self.output / MANIFEST.name)


if __name__ == "__main__":
    unittest.main()
