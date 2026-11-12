"""The local semantic model opts out before an optional runtime can initialize."""

import builtins
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from memory_book import semantic


class SemanticPrivacyTests(unittest.TestCase):
    def test_runtime_initialization_and_session_cannot_precede_telemetry_opt_out(self):
        events = []
        tokenizer = Mock()
        tokenizer.token_to_id.return_value = 0

        def disable():
            events.append("disabled")

        def session(*args, **kwargs):
            self.assertEqual(events, ["import-with-opt-out", "disabled"])
            self.assertEqual(kwargs["providers"], ["CPUExecutionProvider"])
            events.append("session")
            return SimpleNamespace(get_inputs=lambda: [SimpleNamespace(name="input_ids"),
                                                        SimpleNamespace(name="attention_mask")])

        ort = SimpleNamespace(disable_telemetry_events=disable,
                              SessionOptions=SimpleNamespace, InferenceSession=session)
        original_import = builtins.__import__

        def importing(name, *args, **kwargs):
            if name == "onnxruntime":
                # A telemetry-enabled runtime would observe this at import,
                # before the later API opt-out is even available.
                self.assertEqual(os.environ.get("ORT_DISABLE_TELEMETRY"), "1")
                events.append("import-with-opt-out")
                return ort
            if name == "numpy":
                return SimpleNamespace()
            if name == "tokenizers":
                return SimpleNamespace(Tokenizer=SimpleNamespace(from_str=lambda _: tokenizer))
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = []
            for name, content in (("fixture.onnx", b"model fixture"), ("tokenizer.json", b"{}")):
                (root / name).write_bytes(content)
                files.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            with patch.object(semantic, "MODEL_FILES", files), \
                    patch.dict(os.environ, {"ORT_DISABLE_TELEMETRY": "0"}), \
                    patch("builtins.__import__", side_effect=importing), \
                    patch.object(semantic.importlib.metadata, "version", return_value="fixture"):
                model = semantic.SemanticModel(root)
                self.assertEqual(events, ["import-with-opt-out", "disabled", "session"])
                self.assertEqual(model.identity["semantic_version"], semantic.SEMANTIC_VERSION)
                self.assertEqual(model.identity["files"], files)

    def test_invalid_local_artifacts_do_not_initialize_an_optional_runtime(self):
        original_import = builtins.__import__

        def importing(name, *args, **kwargs):
            self.assertNotEqual(name, "onnxruntime", "Invalid model must fail before optional runtime initialization")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory, patch("builtins.__import__", side_effect=importing), \
                self.assertRaisesRegex(ValueError, "Missing or incorrect semantic model"):
            semantic.SemanticModel(directory)


if __name__ == "__main__":
    unittest.main()
