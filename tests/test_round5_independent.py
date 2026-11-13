"""Independent transaction and exact-score checks for the round-five paths."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.text import query_terms, terms


class OriginalTransactionBook(MemoryBook):
    """Exercise the preserved write transaction, as before replay preflight."""

    def _unchanged_ingest(self, *args, **kwargs):
        return None


def source(identity="seed", **changes):
    return {"project": "audit", "session_id": identity, "task_id": "original",
            "created_at": "2026-01-02T00:00:00Z", "title": "Calibration evidence",
            "messages": [{"role": "system", "content": "Source instructions."},
                         {"role": "user", "content": "Calibrate pressure."},
                         {"role": "assistant", "content": "Pressure remains 82. " * 30},
                         {"role": "tool", "content": "Measured value: 82."}], **changes}


class IndependentReplayTests(unittest.TestCase):
    def test_move_metadata_and_equivalent_utc_date_match_the_original_transaction(self):
        with MemoryBook(":memory:", max_page_chars=256, min_page_chars=0) as candidate, \
                OriginalTransactionBook(":memory:", max_page_chars=256, min_page_chars=0) as reference, \
                patch("memory_book.store._now", return_value="2026-11-14T00:00:00+00:00"):
            moved = source(task_id="destination", created_at="")
            operations = [source(project_name="Original lab", task_title="Original task"),
                          source("other", task_id="destination", project_name="Current lab",
                                 task_title="Destination task"),
                          moved, moved,
                          source(task_id="destination", created_at="2026-01-02T08:00:00+08:00"),
                          source(task_id="destination", project_name="Explicit lab", task_title="Explicit task")]
            for payload in operations:
                with self.subTest(payload=payload):
                    self.assertEqual(candidate.ingest(payload), reference.ingest(payload))
                    self.assertEqual(candidate.export(), reference.export())
                    self.assertEqual(list(candidate.db.iterdump()), list(reference.db.iterdump()))
            stored = candidate.get_session("audit", "seed")
            self.assertEqual(stored["created_at"], "2026-01-02T00:00:00+00:00")
            self.assertEqual(stored["project_name"], "Explicit lab")
            self.assertEqual(stored["task_title"], "Explicit task")

    def test_preflight_miss_rechecks_a_transaction_writer_that_already_saved_the_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.db"
            with MemoryBook(path) as reader, OriginalTransactionBook(path) as writer:
                reader.ingest(source())
                desired = source(messages=[{"role": "assistant", "content": "Pressure changed to 93."}])
                check = reader._unchanged_ingest
                written = []

                def intervening_write(*args, **kwargs):
                    result = check(*args, **kwargs)
                    self.assertIsNone(result)
                    written.append(writer.ingest(desired))
                    return result

                with patch.object(reader, "_unchanged_ingest", side_effect=intervening_write):
                    result = reader.ingest(desired)
                self.assertEqual(result, {**written[0], "skipped": True})
                self.assertEqual(result["revision"], 2)
                self.assertEqual(reader.get_session("audit", "seed"), writer.get_session("audit", "seed"))
                self.assertFalse(reader.db.in_transaction)
                self.assertEqual(reader.db.execute("PRAGMA foreign_key_check").fetchall(), [])


class IndependentScoreTests(unittest.TestCase):
    def test_identical_and_fused_routes_preserve_the_original_float_bits(self):
        with MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
            texts = ("alpha calibration stable", "alpha calibrated pressure",
                     "alpha calibrating pressure pressure", "alpha calibration calibration report")
            for i, text in enumerate(texts):
                book.ingest(source(str(i), task_id="shared", task_title="Alpha calibration",
                                   title="Alpha calibration evidence",
                                   messages=[{"role": "assistant", "content": text}]))
            for query, expected_fusion in (("alpha", False), ("calibration", True)):
                qt = query_terms(query)
                expression = ' OR '.join('"' + value + '"' for value in qt)
                expression = f"({expression}) AND body : ({expression})"
                routes = []
                for table in ("pages_fts", "pages_stem_fts"):
                    routes.append(book.db.execute(
                        f"SELECT p.id,bm25({table},2.0,2.0,1.0,0.25) rank FROM {table} "
                        f"JOIN pages p ON p.rid={table}.rowid WHERE {table} MATCH ? "
                        "ORDER BY rank,p.id LIMIT 96", (expression,)).fetchall())
                fused = [row["id"] for row in routes[0]] != [row["id"] for row in routes[1]]
                self.assertEqual(fused, expected_fusion)
                scores = [{row["id"]: max(0.0, -row["rank"]) for row in route} for route in routes]
                scales = [max(values.values(), default=1.0) or 1.0 for values in scores]
                rows = {row["id"]: dict(row) for route in reversed(routes) for row in route}
                qset = set(qt)
                for row in rows.values():
                    overlap = len(qset & set(terms("Alpha calibration Alpha calibration evidence", query=True))) / len(qset)
                    relevance = (2 * scores[0].get(row["id"], 0.0) / scales[0] +
                                 scores[1].get(row["id"], 0.0) / scales[1]) if fused else -row["rank"]
                    row["expected"] = relevance * (1 + 0.15 * overlap)
                result = book.recall(query, budget_chars=100000, limit=50, use_cache=False)
                self.assertEqual({row["id"] for row in result["results"]}, set(rows))
                for row in result["results"]:
                    self.assertEqual(row["score"].hex(), rows[row["id"]]["expected"].hex())


if __name__ == "__main__":
    unittest.main()
