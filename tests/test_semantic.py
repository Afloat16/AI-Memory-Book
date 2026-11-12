"""Lifecycle and routing tests; these fixture vectors are not quality scores."""

import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.semantic import DIMENSIONS, SemanticIndexError, fuse_candidates


def session(project="p", name="s", content="A small original source.", **extra):
    return {"project": project, "session_id": name, "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": content}], **extra}


class FixtureEncoder:
    """Deterministic fixtures exercise storage, never a semantic benchmark."""

    fingerprint = "fixture-model-v1"
    identity = {"fixture": True}
    runtime = {"fixture": "1"}
    load_ms = 0

    def encode_pages(self, pages):
        return [(page["id"], 0, 0, len(page["content"]),
                 struct.pack("<" + "f" * DIMENSIONS, 1.0, *([0.0] * (DIMENSIONS - 1))))
                for page in pages]


class SemanticLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "memory.db"
        self.book = MemoryBook(self.path, semantic_model_dir=self.temp.name)
        self.book._semantic_model = FixtureEncoder()
        self.book.ingest(session())

    def tearDown(self):
        self.book.close()
        self.temp.cleanup()

    def test_default_path_does_not_load_model_or_create_derived_tables(self):
        with MemoryBook(":memory:", semantic_model_dir="/missing/model") as book:
            book.ingest(session())
            result = book.recall("original source")
            self.assertIsNone(book._semantic_model)
            self.assertNotIn("semantic", result)
            self.assertFalse(book.db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'semantic_%'").fetchone())

    def test_explicit_configuration_and_strict_option(self):
        with MemoryBook(":memory:") as book:
            with self.assertRaisesRegex(ValueError, "explicit semantic_model_dir"):
                book.recall("source", semantic=True)
            with self.assertRaisesRegex(ValueError, "explicit semantic_model_dir"):
                book.build_semantic_index()
        for value in (1, "true", None):
            with self.assertRaisesRegex(ValueError, "semantic must be a boolean"):
                self.book.recall("source", semantic=value)
        with self.assertRaisesRegex(ValueError, "book strategy"):
            self.book.recall("source", semantic=True, strategy="flat")

    def test_build_preserves_every_source_and_address(self):
        exported = self.book.export()
        pages = [tuple(row) for row in self.book.db.execute("SELECT * FROM pages ORDER BY id")]
        revision = self.book.revision
        report = self.book.build_semantic_index()
        self.assertEqual(report["pages"], 1)
        self.assertEqual(report["windows"], 1)
        self.assertEqual(report["vector_bytes"], DIMENSIONS * 4)
        self.assertEqual(self.book.revision, revision)
        self.assertEqual(self.book.export(), exported)
        self.assertEqual([tuple(row) for row in self.book.db.execute("SELECT * FROM pages ORDER BY id")], pages)

    def test_missing_stale_and_changed_model_fail_before_cached_recall(self):
        with self.assertRaisesRegex(SemanticIndexError, "No semantic index"):
            self.book.recall("source", semantic=True)
        self.book.build_semantic_index()
        with patch("memory_book.semantic.rank_pages", return_value=[]):
            self.book.recall("source", semantic=True)
            cached = self.book.recall("source", semantic=True)
            self.assertTrue(cached["cache_hit"])
        self.book._semantic_model.fingerprint = "different-fixture"
        with self.assertRaisesRegex(SemanticIndexError, "different model"):
            self.book.recall("source", semantic=True)
        self.book._semantic_model.fingerprint = "fixture-model-v1"
        self.book.ingest(session(content="An updated original source."))
        with self.assertRaisesRegex(SemanticIndexError, "stale"):
            self.book.recall("source", semantic=True)
        self.assertTrue(self.book.recall("source")["results"])

    def test_concurrent_writer_prevents_stale_publish_and_retains_previous_index(self):
        self.book.build_semantic_index()
        before = [tuple(row) for row in self.book.db.execute("SELECT * FROM semantic_meta")]
        encode = self.book._semantic_model.encode_pages

        def encode_while_writing(pages):
            vectors = encode(pages)
            with MemoryBook(self.path) as writer:
                writer.ingest(session(name="new", content="A concurrent write."))
            return vectors

        with patch.object(self.book._semantic_model, "encode_pages", side_effect=encode_while_writing):
            with self.assertRaisesRegex(SemanticIndexError, "changed while building"):
                self.book.build_semantic_index()
        self.assertEqual([tuple(row) for row in self.book.db.execute("SELECT * FROM semantic_meta")], before)
        self.assertFalse(self.book.db.in_transaction)
        self.assertEqual(len(self.book.export()), 2)

    def test_encode_failure_keeps_existing_index(self):
        self.book.build_semantic_index()
        before = [tuple(row) for row in self.book.db.execute("SELECT * FROM semantic_vectors")]
        with patch.object(self.book._semantic_model, "encode_pages", side_effect=RuntimeError("fixture failure")):
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                self.book.build_semantic_index()
        self.assertEqual([tuple(row) for row in self.book.db.execute("SELECT * FROM semantic_vectors")], before)
        self.assertFalse(self.book.db.in_transaction)

    def test_old_writer_deletion_invalidates_index_and_cascades_vectors(self):
        self.book.build_semantic_index()
        with MemoryBook(self.path) as writer:
            writer.delete_project("p")
        self.assertEqual(self.book.db.execute("SELECT COUNT(*) FROM semantic_vectors").fetchone()[0], 0)
        with self.assertRaisesRegex(SemanticIndexError, "stale"):
            self.book.recall("source", semantic=True)
        empty = self.book.build_semantic_index()
        self.assertEqual(empty["windows"], 0)

    def test_fusion_preserves_score_margins_and_is_deterministic(self):
        lexical = [{"id": "a", "score": 1000}, {"id": "b", "score": 1}]
        semantic = [{"id": "c", "semantic_similarity": .99}, {"id": "b", "semantic_similarity": .4}]
        rows = fuse_candidates(lexical, semantic)
        self.assertEqual([row["id"] for row in rows], ["a", "c", "b"])
        self.assertAlmostEqual(rows[0]["score"], .75)
        self.assertEqual(lexical[0]["score"], 1000)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "optional semantic vector tests need NumPy")
class SemanticVectorRoutingTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.book = MemoryBook(":memory:", semantic_model_dir="/fixture")
        model = FixtureEncoder()
        model.np = np
        model.encode_query = lambda query: np.asarray([[1.0] + [0.0] * (DIMENSIONS - 1)], dtype="<f4")
        self.book._semantic_model = model

    def tearDown(self):
        self.book.close()

    def test_scope_before_candidate_limit_and_original_source_spans(self):
        # More out-of-scope pages than the registered 96-candidate limit.
        for i in range(100):
            self.book.ingest(session(project="other", name=f"outside-{i}", content=f"Outside original {i}."))
        first = self.book.ingest(session(project="wanted", name="inside", content="Kept original evidence.", task_id="one"))
        self.book.ingest(session(project="wanted", name="exclude", content="Another original page.", task_id="two"))
        self.book.build_semantic_index()
        result = self.book.recall("unrelatedword", project="wanted", chapter=first["chapter_id"],
                                  session="inside", limit=1, semantic=True)
        self.assertEqual(len(result["results"]), 1)
        row = result["results"][0]
        self.assertIn("Kept original evidence.", row["text"])
        self.assertTrue(all(ref["project"] == "wanted" and ref["session_id"] == "inside"
                            for ref in row["source_refs"]))
        original = self.book.read(row["id"])["content"]
        self.assertEqual(row["text"], "\n…\n".join(original[a:b] for a, b in row["excerpt_spans"]))

    def test_cache_isolation_no_lexical_terms_and_budget_zero(self):
        self.book.ingest(session(content="Source content unrelated to the query."))
        self.book.build_semantic_index()
        lexical = self.book.recall("differentword")
        semantic = self.book.recall("differentword", semantic=True)
        self.assertEqual(lexical["results"], [])
        self.assertTrue(semantic["results"])
        self.assertFalse(semantic["cache_hit"])
        self.assertTrue(self.book.recall("differentword", semantic=True)["cache_hit"])
        self.assertTrue(self.book.recall("differentword")["cache_hit"])
        self.assertTrue(self.book.recall("and", semantic=True)["results"])
        self.assertEqual(self.book.recall("and", semantic=True, budget_chars=0)["context"], "")

    def test_corrupt_vector_fails_instead_of_returning_unverified_candidates(self):
        self.book.ingest(session())
        self.book.build_semantic_index()
        self.book.db.execute("UPDATE semantic_vectors SET vector=?", (b"bad",))
        with self.assertRaisesRegex(SemanticIndexError, "dimensions"):
            self.book.recall("unrelatedword", semantic=True)


if __name__ == "__main__":
    unittest.main()
