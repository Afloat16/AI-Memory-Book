"""Artificial end-to-end identity guards for the versioned fresh evaluators."""
from __future__ import annotations

import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import memory_book
from memory_book import MemoryBook
from benchmarks.run import engine_source_hash
from benchmarks.semantic_eval import source_snapshot
from scripts import round5_title_reference_fresh_v2 as native
from scripts import round5_title_reference_fresh_components_v2 as component
from scripts.round5_source_content_snapshot import source_content_snapshot


PAYLOAD = {"project": "invented", "session_id": "one", "title": "Invented source",
           "task_id": "task", "created_at": "2003-04-05T06:07:08Z",
           "messages": [{"role": "user", "content": "Quartz appears beside the cedar instrument."}]}


class FreshV2SourceIntegrationTests(unittest.TestCase):
    def book(self, path=":memory:"):
        book = MemoryBook(path, cache_size=0)
        self.addCleanup(book.close)
        book.ingest(PAYLOAD)
        return book

    def report(self, book):
        full, content = source_snapshot(book.db), source_content_snapshot(book.db)
        return {"source_snapshot_before": full, "source_snapshot_after": full,
                "source_content_before": content, "source_content_after": content,
                "index_before": native.indexed_content(book.db)}

    def test_native_cross_worker_content_and_full_within_worker_are_both_required(self):
        books = [self.book() for _ in range(5)]
        reports = [self.report(book) for book in books]
        self.assertGreater(len({row["source_snapshot_before"] for row in reports}), 1)
        native.verify_cross_worker_sources(reports)
        with self.assertRaisesRegex(ValueError, "All five"):
            native.verify_cross_worker_sources(reports[:4])
        wrong = copy.deepcopy(reports)
        books[1].db.execute("UPDATE projects SET updated_at=updated_at || '-changed'")
        wrong[1]["source_snapshot_after"] = source_snapshot(books[1].db)
        self.assertEqual(source_content_snapshot(books[1].db), wrong[1]["source_content_before"])
        with self.assertRaisesRegex(ValueError, "Full source snapshot changed within"):
            native.verify_cross_worker_sources(wrong)
        wrong = copy.deepcopy(reports)
        books[2].db.execute("UPDATE sessions SET created_at=created_at || '-source-change'")
        changed = source_content_snapshot(books[2].db)
        wrong[2]["source_content_before"] = wrong[2]["source_content_after"] = changed
        with self.assertRaisesRegex(ValueError, "identical deterministic"):
            native.verify_cross_worker_sources(wrong)
        wrong = copy.deepcopy(reports)
        wrong[3]["index_before"] = "different-index"
        with self.assertRaisesRegex(ValueError, "lexical index"):
            native.verify_cross_worker_sources(wrong)

    def test_separate_export_cross_check_keeps_content_and_index_strict(self):
        baseline, exporter = self.book(), self.book()
        baseline_report = self.report(baseline)
        export = {"source_snapshot": source_snapshot(exporter.db),
                  "source_content_snapshot": source_content_snapshot(exporter.db),
                  "index": native.indexed_content(exporter.db)}
        self.assertNotEqual(export["source_snapshot"], baseline_report["source_snapshot_before"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invented-native-report"
            path.write_text("invented")
            with patch.object(component.native, "paths", return_value={"report": path}), \
                 patch.object(component.native, "completed_prefix", return_value=[baseline_report]):
                self.assertTrue(component.check_native_export({}, None, {}, {}, export, required=True))
                exporter.db.execute("UPDATE turns SET content=content || ' changed original'")
                wrong = {**export, "source_content_snapshot": source_content_snapshot(exporter.db)}
                with self.assertRaisesRegex(ValueError, "deterministic source content"):
                    component.check_native_export({}, None, {}, {}, wrong, required=True)
                with self.assertRaisesRegex(ValueError, "deterministic source content"):
                    component.check_native_export({}, None, {}, {}, {**export, "index": "changed"}, required=True)

    def test_copied_book_and_canonical_bundle_keep_original_full_and_byte_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export_path = root / "export.db"
            with MemoryBook(export_path, cache_size=0) as book:
                book.ingest(PAYLOAD)
                documents = component.reused.documents_from(book)
                bundle = {"database": "export.db", "source_snapshot": source_snapshot(book.db),
                          "source_content_snapshot": source_content_snapshot(book.db),
                          "index": component.indexed_content(book.db),
                          "documents": documents, "documents_sha256": component.digest(documents),
                          "diagnostics": {}, "diagnostics_sha256": component.digest({})}
            bundle["database_sha256"] = component.sha(export_path)
            package = Path(memory_book.__file__).resolve().parent
            expected = {"commit": "c" * 40, "runtime_sha256": engine_source_hash(package)}
            with patch.object(component, "ROOT", root), \
                 patch.object(component, "scope", return_value={"native_boundaries": {"book": "invented"}}), \
                 patch.object(component.reused, "imported_book",
                              return_value=(MemoryBook, package, {"fixture": True})):
                engine = component.BookComponent(package.parent, expected, root / "copy.db", bundle, False)
                self.assertEqual(engine.originals, bundle["source_snapshot"])
                engine.close()
                wrong = {**bundle, "source_snapshot": "0" * 64}
                with self.assertRaisesRegex(ValueError, "canonical pages/index/sources"):
                    component.BookComponent(package.parent, expected, root / "bad-copy.db", wrong, False)
                comparison = {"state": "component-state", "output": "component-output"}
                path = component.canonical_bundle(comparison)
                component.save(path, bundle, exclusive=True)
                report = {"bundle_sha256": component.sha(path),
                          "database_sha256": bundle["database_sha256"]}
                self.assertEqual(component.load_bundle(comparison, report), bundle)
                db = sqlite3.connect(export_path)
                try:
                    db.execute("UPDATE projects SET updated_at=updated_at || '-storage-change'")
                    db.commit()
                    self.assertEqual(source_content_snapshot(db), bundle["source_content_snapshot"])
                    self.assertNotEqual(source_snapshot(db), bundle["source_snapshot"])
                finally:
                    db.close()
                with self.assertRaisesRegex(ValueError, "Canonical database/documents/diagnostics changed"):
                    component.load_bundle(comparison, report)

    def test_original_numeric_quality_cost_resource_and_schedule_gates_are_unchanged(self):
        old_native = native.read(native.ROOT / "benchmarks/experiments/round5-title-reference-fresh-scope.json")
        new_native = native.read(native.ROOT / native.d.SCOPE)
        for key in ("baseline", "selection", "native", "quality_gates", "cost_gates", "resources"):
            with self.subTest(scope="native", section=key):
                self.assertEqual(new_native[key], old_native[key])
        old_component = component.read(component.ROOT / "benchmarks/experiments/round5-title-reference-fresh-components-scope.json")
        new_component = component.read(component.ROOT / component.SCOPE)
        for key in ("engines", "axes", "schedule", "native_boundaries", "quality_and_integrity", "dependencies"):
            with self.subTest(scope="component", section=key):
                self.assertEqual(new_component[key], old_component[key])


if __name__ == "__main__":
    unittest.main()
