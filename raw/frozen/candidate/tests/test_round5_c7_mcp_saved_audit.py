"""Reject semantic/output changes while retaining per-archive full snapshots.

These small fixtures create no product database, SDK session or timing run.
"""
from __future__ import annotations

import copy
import sqlite3
import unittest

from benchmarks.semantic_eval import source_snapshot
from scripts import audit_round5_c7_mcp_development as audit


def fixture_workers():
    workers = []
    for i, (round_, label) in enumerate(((0, "baseline"), (0, "candidate"), (1, "candidate"), (1, "baseline"))):
        archive = {"source_snapshot_sha256": str(i) * 64,
            "indexed_content": {name: {"rows": 1, "sha256": "a" * 64} for name in audit.INDEX_TABLES},
            "revision": 1, "cache_entries": 0}
        workers.append({"key": f"r{round_}-public1015-{label}", "round": round_, "label": label,
            "archive_before": archive, "archive_after": copy.deepcopy(archive),
            "fresh_ingestion_results_sha256": "b" * 64, "unchanged_reingestion_results_sha256": "c" * 64,
            "configurations": [{"rows": [{"query_id": "question-1", "wall_ms": i + 1,
                "engine_source_sha256": label, "payload_sha256": "d" * 64,
                "native_payload_sha256": "e" * 64, "context_sha256": "f" * 64,
                "envelope_sha256": "a" * 64, "token_metadata": {"context_tokens": 300}}]}]})
    return workers


class SavedArchiveTests(unittest.TestCase):
    def test_distinct_independent_snapshots_keep_all_within_worker_checks(self):
        workers = fixture_workers()
        before = copy.deepcopy(workers)
        result = audit.assert_archive_projections(workers)
        self.assertEqual(result["distinct_cross_archive_snapshot_hashes"], 4)
        self.assertTrue(all(row["within_worker_unchanged"] for row in result["original_complete_snapshots"]))
        self.assertEqual(workers, before)

    def test_source_snapshot_really_includes_host_timestamp_columns(self):
        with sqlite3.connect(":memory:") as db:
            for table in ("projects", "chapters", "sessions", "turns", "sections", "pages"):
                db.execute(f"CREATE TABLE {table}(id TEXT, updated_at TEXT)")
                db.execute(f"INSERT INTO {table} VALUES('same-id','2026-11-14T00:00:00Z')")
            before = source_snapshot(db)
            db.execute("UPDATE projects SET updated_at='2026-11-14T00:00:01Z'")
            self.assertNotEqual(source_snapshot(db), before)

    def test_changed_full_snapshot_within_any_worker_is_rejected(self):
        workers = fixture_workers()
        workers[2]["archive_after"]["source_snapshot_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "within-worker"):
            audit.assert_archive_projections(workers)

    def test_changed_semantic_table_cannot_hide_behind_snapshot_exception(self):
        for table in audit.INDEX_TABLES:
            with self.subTest(table=table):
                workers = fixture_workers()
                for when in ("archive_before", "archive_after"):
                    workers[1][when]["indexed_content"][table]["sha256"] = "9" * 64
                with self.assertRaisesRegex(ValueError, "logical source/index/ingestion"):
                    audit.assert_archive_projections(workers)

    def test_missing_table_or_extra_unchecked_archive_field_is_rejected(self):
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                workers = fixture_workers()
                for when in ("archive_before", "archive_after"):
                    if mutation == "missing":
                        workers[1][when]["indexed_content"].pop("turns")
                    else:
                        workers[1][when]["unverified_source"] = "changed"
                with self.assertRaises(ValueError):
                    audit.assert_archive_projections(workers)

    def test_changed_ingestion_or_revision_or_nonempty_cache_is_rejected(self):
        for field in (*audit.INGESTION_FIELDS, "revision", "cache_entries"):
            with self.subTest(field=field):
                workers = fixture_workers()
                if field in audit.INGESTION_FIELDS:
                    workers[1][field] = "9" * 64
                else:
                    for when in ("archive_before", "archive_after"):
                        workers[1][when][field] += 1
                with self.assertRaises(ValueError):
                    audit.assert_archive_projections(workers)


class SavedOutputTests(unittest.TestCase):
    def test_only_elapsed_and_engine_identity_differ_in_valid_pairs(self):
        pairs, queries, timing = audit.paired_outputs(fixture_workers(), ["question-1"])
        self.assertEqual((len(pairs), len(queries), len(timing)), (2, 1, 4))

    def test_any_complete_hash_or_token_metadata_change_is_rejected(self):
        for field in ("payload_sha256", "native_payload_sha256", "context_sha256", "envelope_sha256", "token_metadata"):
            with self.subTest(field=field):
                workers = fixture_workers()
                workers[3]["configurations"][0]["rows"][0][field] = "changed"
                with self.assertRaisesRegex(ValueError, "Complete output"):
                    audit.paired_outputs(workers, ["question-1"])

    def test_new_non_timing_field_is_compared_in_full(self):
        workers = fixture_workers()
        workers[1]["configurations"][0]["rows"][0]["extra_source_field"] = "cannot ignore"
        with self.assertRaisesRegex(ValueError, "Complete output"):
            audit.paired_outputs(workers, ["question-1"])

    def test_missing_duplicate_or_replaced_worker_cannot_pass(self):
        for kind in ("missing", "duplicate", "wrong-question"):
            with self.subTest(kind=kind):
                workers = fixture_workers()
                if kind == "missing":
                    workers.pop()
                elif kind == "duplicate":
                    workers[-1] = copy.deepcopy(workers[0])
                else:
                    workers[-1]["configurations"][0]["rows"][0]["query_id"] = "another-question"
                with self.assertRaises(ValueError):
                    audit.paired_outputs(workers, ["question-1"])


if __name__ == "__main__":
    unittest.main()
