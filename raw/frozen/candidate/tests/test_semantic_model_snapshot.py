"""A single verified artifact snapshot is the only input to optional runtimes."""

import builtins
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from memory_book import semantic


class SemanticModelSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contents = {"fixture.onnx": b"verified model fixture", "tokenizer.json": b'{"fixture":"verified"}'}
        self.files = []
        for name, content in self.contents.items():
            (self.root / name).write_bytes(content)
            self.files.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(semantic, "MODEL_FILES", self.files))

    def fake_runtime(self, *, before_numpy=None):
        events = []
        captured = {}
        tokenizer = Mock()
        tokenizer.token_to_id.return_value = 0
        def from_str(text):
            captured["tokenizer"] = text
            return tokenizer
        def disable():
            events.append("disable")
        def session(blob, **kwargs):
            captured["model"] = blob
            captured["options"] = kwargs["sess_options"]
            self.assertEqual(kwargs["providers"], ["CPUExecutionProvider"])
            events.append("session")
            return SimpleNamespace(get_inputs=lambda: [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")])
        ort = SimpleNamespace(disable_telemetry_events=disable, SessionOptions=SimpleNamespace, InferenceSession=session)
        original_import = builtins.__import__
        def importing(name, *args, **kwargs):
            if name in {"numpy", "onnxruntime", "tokenizers"}:
                self.assertEqual(os.environ.get("ORT_DISABLE_TELEMETRY"), "1")
                events.append(name)
                if name == "numpy":
                    if before_numpy:
                        before_numpy()
                    return SimpleNamespace()
                if name == "onnxruntime":
                    return ort
                return SimpleNamespace(Tokenizer=SimpleNamespace(from_str=from_str))
            return original_import(name, *args, **kwargs)
        self.stack.enter_context(patch("builtins.__import__", side_effect=importing))
        self.stack.enter_context(patch.dict(os.environ, {"ORT_DISABLE_TELEMETRY": "0"}))
        self.stack.enter_context(patch.object(semantic.importlib.metadata, "version", return_value="fixture"))
        return events, captured

    def forbid_runtime_imports(self):
        original_import = builtins.__import__
        def importing(name, *args, **kwargs):
            self.assertNotIn(name, {"numpy", "onnxruntime", "tokenizers"}, "Invalid artifacts must fail before optional imports")
            return original_import(name, *args, **kwargs)
        return patch("builtins.__import__", side_effect=importing)

    def test_runtime_consumes_one_read_per_file_with_unchanged_identity(self):
        expected_identity = semantic.verify_model_files(self.root)
        reads = []
        original_read = Path.read_bytes
        def reading(path):
            reads.append(path.name)
            return original_read(path)
        events, captured = self.fake_runtime()
        with patch.object(Path, "read_bytes", reading):
            model = semantic.SemanticModel(self.root)
        self.assertEqual(reads, [entry["path"] for entry in self.files])
        self.assertEqual(captured["model"], self.contents["fixture.onnx"])
        self.assertEqual(captured["tokenizer"], self.contents["tokenizer.json"].decode("utf-8"))
        self.assertEqual(events, ["numpy", "onnxruntime", "tokenizers", "disable", "session"])
        self.assertEqual(model.identity, expected_identity)
        canonical = json.dumps(expected_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(model.fingerprint, hashlib.sha256(canonical.encode()).hexdigest())
        self.assertEqual(captured["options"].intra_op_num_threads, 1)
        self.assertEqual(captured["options"].inter_op_num_threads, 1)

    def test_replacement_after_verification_cannot_change_runtime_bytes(self):
        def replace_files():
            for name, content in self.contents.items():
                (self.root / name).write_bytes(b"x" * len(content))
        events, captured = self.fake_runtime(before_numpy=replace_files)
        model = semantic.SemanticModel(self.root)
        self.assertEqual(captured["model"], self.contents["fixture.onnx"])
        self.assertEqual(captured["tokenizer"], self.contents["tokenizer.json"].decode("utf-8"))
        self.assertEqual(model.identity["files"], self.files)
        self.assertEqual(events[-1], "session")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            semantic.verify_model_files(self.root)

    def test_missing_wrong_length_and_wrong_hash_fail_before_optional_imports(self):
        path = self.root / "fixture.onnx"
        for content, message in ((None, "Missing or incorrect"), (b"short", "Missing or incorrect"),
                                 (b"x" * len(self.contents[path.name]), "SHA-256 mismatch")):
            with self.subTest(content=content):
                if content is None:
                    path.unlink()
                else:
                    path.write_bytes(content)
                with self.forbid_runtime_imports(), self.assertRaisesRegex(ValueError, message):
                    semantic.SemanticModel(self.root)

    def test_changed_bytes_during_read_fail_before_optional_imports(self):
        original_read = Path.read_bytes
        for suffix, message in ((b"extra", "changed during initialization"), (b"", "SHA-256 mismatch")):
            with self.subTest(suffix=suffix):
                def changed(path):
                    original = original_read(path)
                    return b"x" * len(original) + suffix if path.name == "fixture.onnx" else original
                with patch.object(Path, "read_bytes", changed), self.forbid_runtime_imports(), \
                        self.assertRaisesRegex(ValueError, message):
                    semantic.SemanticModel(self.root)

    def test_public_verification_keeps_streaming_without_retained_blobs(self):
        large = b"model fixture" * 200000
        (self.root / "fixture.onnx").write_bytes(large)
        self.files[0].update(bytes=len(large), sha256=hashlib.sha256(large).hexdigest())
        original_open = Path.open
        reads = []
        class Stream:
            def __init__(self, handle):
                self.handle = handle
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return self.handle.__exit__(*args)
            def read(self, size):
                reads.append(size)
                return self.handle.read(size)
        def opening(path, *args, **kwargs):
            return Stream(original_open(path, *args, **kwargs))
        with patch.object(Path, "read_bytes", side_effect=AssertionError("verification must stream")), \
                patch.object(Path, "open", opening), self.forbid_runtime_imports():
            identity = semantic.verify_model_files(self.root)
        self.assertEqual(identity["files"], self.files)
        self.assertGreaterEqual(len(reads), 5)
        self.assertEqual(set(reads), {1024 * 1024})


if __name__ == "__main__":
    unittest.main()
