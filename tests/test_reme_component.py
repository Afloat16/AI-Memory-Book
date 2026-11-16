"""ReMe adapter integrity contracts; optional tests execute real pinned ReMe."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks.competitors.reme import (
    ReMeComponent, environment, git_blob_sha1, load_lock, prepare, source_identity,
)
from benchmarks.competitors.reme_worker import (
    authenticate_chunk, authenticate_results, original_path,
)


def document(identity="page-1", project="Team/Parser-A", text="HTTPParser keeps the exact input bytes.\n"):
    return {"id": identity, "project": project, "title": "Input contract",
            "text": text, "created_at": "2026-01-01T00:00:00+00:00"}


def native_chunk(doc):
    end_line = 1 + doc["text"].count("\n") - int(doc["text"].endswith("\n"))
    digest = hashlib.sha256(" ".join([original_path(doc), "1", str(end_line), doc["text"]]).encode()).hexdigest()
    return {"id": digest, "path": original_path(doc),
            "text": doc["text"], "start_line": 1, "end_line": end_line,
            "embedding": None, "metadata": {}, "scores": {"keyword": 0.75, "score": 0.75}}


class ReMeContracts(unittest.TestCase):
    def test_exact_project_names_and_source_ids_never_collide_after_normalization(self):
        names = ["Team/Parser-A", "team/parser-a", "Team_Parser-A", "Team/Parser_A",
                 "Team/Parser-A ", "Team/Parser-AB", "团队/解析器", "../Team/Parser-A"]
        paths = [original_path(document(project=name)) for name in names]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(p.startswith("pages/") and p.endswith(".txt") for p in paths))
        self.assertTrue(all(".." not in Path(p).parts for p in paths))
        self.assertNotEqual(original_path(document(identity="A/B")),
                            original_path(document(identity="A_B")))

    def test_native_chunk_must_be_one_complete_unchanged_original(self):
        doc = document()
        value = native_chunk(doc)
        chunk = SimpleNamespace(**value)
        node = SimpleNamespace(path=value["path"], chunk_ids=[value["id"]])
        self.assertIs(authenticate_chunk(doc, node, [chunk], value["path"]), chunk)
        for chunks in ([], [chunk, chunk]):
            with self.subTest(chunks=len(chunks)), self.assertRaises(ValueError):
                authenticate_chunk(doc, node, chunks, value["path"])
        changed = SimpleNamespace(**{**value, "text": doc["text"].strip()})
        with self.assertRaisesRegex(ValueError, "changed original"):
            authenticate_chunk(doc, node, [changed], value["path"])
        wrong_line = SimpleNamespace(**{**value, "end_line": 2})
        with self.assertRaisesRegex(ValueError, "coordinates"):
            authenticate_chunk(doc, node, [wrong_line], value["path"])

    def test_foreign_source_and_modified_identity_are_errors_not_filtered_results(self):
        doc, foreign = document(), document("page-2", "team/parser-a")
        original = native_chunk(doc)
        other = {**native_chunk(foreign), "id": "other-native-id"}
        originals = {original["path"]: doc, other["path"]: foreign}
        chunks = {original["path"]: original, other["path"]: other}
        records = authenticate_results([original], originals, chunks, doc["project"], 5)
        self.assertEqual(records, [{"id": doc["id"], "project": doc["project"], "text": doc["text"]}])
        for row in (other, {**original, "path": "unmapped"}, {**original, "id": "invented"},
                    {**original, "start_line": 2}, {**original, "text": "rewritten"}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                authenticate_results([row], originals, chunks, doc["project"], 5)

    def test_duplicates_limits_and_nonfinite_scores_are_not_silently_repaired(self):
        doc = document()
        row = native_chunk(doc)
        originals, chunks = {row["path"]: doc}, {row["path"]: row}
        for native, limit in (([row, row], 5), ([row], 0),
                              ([{**row, "scores": {"score": float("nan")}}], 5)):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                authenticate_results(native, originals, chunks, doc["project"], limit)
        self.assertEqual(authenticate_results([], originals, chunks, "unknown", 5), [])

    def test_native_payload_and_order_are_preserved(self):
        docs = [document("b"), document("a")]
        native = [{**native_chunk(doc), "id": f"native-{i}", "metadata": {"native_field": i}}
                  for i, doc in enumerate(docs)]
        before = copy.deepcopy(native)
        records = authenticate_results(native, {r["path"]: d for r, d in zip(native, docs)},
                                       {r["path"]: r for r in native}, docs[0]["project"], 5)
        self.assertEqual([r["id"] for r in records], ["b", "a"])
        self.assertEqual(native, before)

    def test_every_source_file_is_authenticated_and_extra_code_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "reme"
            package.mkdir()
            data = b"value = 1\n"
            (package / "__init__.py").write_bytes(data)
            spec = {"repository": "official", "commit": "pinned",
                    "declared_source_version": "test", "release_status": "test",
                    "files": {"reme/__init__.py": {"bytes": len(data),
                                                  "git_blob_sha1": git_blob_sha1(data)}}}
            self.assertEqual(source_identity(root, spec)["verified_files"], 1)
            (package / "extra.py").write_text("unexpected = True\n")
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                source_identity(root, spec)
            (package / "extra.py").unlink()
            (package / "__init__.py").write_bytes(b"value = 2\n")
            with self.assertRaisesRegex(ValueError, "changed"):
                source_identity(root, spec)

    def test_dependency_lock_is_separate_and_native_source_is_explicit(self):
        lock = load_lock()
        self.assertEqual(lock["source"]["commit"], "b13034ba2ff7339bb03df4fa4ee130b47a731c6c")
        self.assertEqual(lock["component"]["embedding_store"], "")
        self.assertIn("reme/components/keyword_index/bm25_index.py", lock["source"]["files"])
        self.assertIn("reme/components/tokenizer/stopwords", lock["source"]["files"])
        self.assertNotIn("reme-ai", lock["dependencies"]["packages"])
        self.assertEqual(lock["dependencies"]["package_count"], len(lock["dependencies"]["packages"]))

    def test_worker_does_not_inherit_model_credentials_or_user_pythonpath(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"LLM_API_KEY": "not-for-worker", "EMBEDDING_API_KEY": "not-for-worker",
                                         "OPENAI_API_KEY": "not-for-worker", "PYTHONPATH": "/untrusted"}):
                env = environment(Path(temp) / "state", Path(temp) / "cache")
            for key in ("LLM_API_KEY", "EMBEDDING_API_KEY", "OPENAI_API_KEY", "HOME"):
                self.assertNotIn(key, env)
            self.assertNotEqual(env["PYTHONPATH"], "/untrusted")
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")


@unittest.skipUnless(os.environ.get("MEMORY_BOOK_REME_PYTHON") and os.environ.get("MEMORY_BOOK_REME_CACHE"),
                     "Real ReMe smoke needs the separately locked Python environment and prepared cache")
class ReMeNativeSmoke(unittest.TestCase):
    def test_real_upstream_exact_scope_source_read_and_unknown_project(self):
        python = os.environ["MEMORY_BOOK_REME_PYTHON"]
        cache = Path(os.environ["MEMORY_BOOK_REME_CACHE"])
        prepare(cache, python=python, offline=True)
        docs = [document("one", "Team/Parser-A", "HTTPParser memorytoken buffer 32.\n"),
                document("two", "team/parser-a", "HTTPParser memorytoken buffer 256.\n"),
                document("three", "Team/Parser-AB", "HTTPParser memorytoken buffer 128.\n")]
        with tempfile.TemporaryDirectory() as temp:
            with ReMeComponent(docs, cache, Path(temp) / "state", python=python) as component:
                self.assertEqual(component.metadata["native_chunk_count"], len(docs))
                self.assertEqual(component.metadata["python_network_attempts"], [])
                for doc in docs:
                    result = component.search("HTTPParser memorytoken", doc["project"], limit=1)
                    self.assertEqual(result["hit_ids"], [doc["id"]])
                    self.assertEqual(result["records"][0]["text"], doc["text"])
                    row = result["native_payload"][0]
                    self.assertEqual(row["path"], original_path(doc))
                    path = Path(temp) / "state" / "workspace" / row["path"]
                    self.assertEqual(path.read_bytes(), doc["text"].encode("utf-8"))
                missing = component.search("HTTPParser memorytoken", "Team/Parser")
                self.assertEqual(missing["hit_ids"], [])
                self.assertEqual(missing["native_search_filter"], {"paths": []})


if __name__ == "__main__":
    unittest.main()
