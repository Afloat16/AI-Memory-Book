from pathlib import Path
import tempfile
import unittest

from benchmarks.answer_eval import database_file_bytes, source_options


class AnswerSourceOptionsTests(unittest.TestCase):
    def test_explicit_options_preserve_default_and_validate_types(self):
        self.assertEqual(source_options({}), {})
        self.assertEqual(source_options({"native_token_budget": True, "coverage": False}),
                         {"native_token_budget": True, "coverage": False})
        self.assertEqual(source_options({"semantic_model_dir": "model"})["semantic_model_dir"],
                         str(Path("model").resolve()))
        for options in ({"native_token_budget": 1}, {"coverage": "false"},
                        {"semantic_model_dir": ""}, {"unknown": True}, []):
            with self.subTest(options=options), self.assertRaises(ValueError):
                source_options(options)

    def test_database_storage_separates_absent_sidecars_from_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.db"
            path.write_bytes(b"abcd")
            Path(str(path) + "-wal").write_bytes(b"abcdef")
            result = database_file_bytes(path)
            self.assertEqual(result["files_bytes"], {"database": 4, "wal": 6, "shm": 0})
            self.assertEqual(result["total_bytes"], 10)
            self.assertFalse(result["present"]["shm"])
            self.assertEqual(path.read_bytes(), b"abcd")
