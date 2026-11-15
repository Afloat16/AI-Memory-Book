"""Source, budget and chronology guards for the shared component diagnostic."""
import copy
from pathlib import Path
import tempfile
import unittest

from benchmarks import engineering_workflow as workflow
from benchmarks.engineering_components import book_search, common_pack, export_documents, mapped_ids
from memory_book import MemoryBook


class EngineeringComponentTests(unittest.TestCase):
    def test_pages_are_exact_current_source_versions_at_every_checkpoint(self):
        visible = {}
        with tempfile.TemporaryDirectory() as directory, MemoryBook(Path(directory) / "book.db") as book:
            for step in workflow.workload():
                for session in step["sessions"]:
                    book.ingest(session)
                    visible[(session["project"], session["session_id"])] = session
                docs = export_documents(book, visible)
                self.assertEqual(len(docs), len(visible))
                for doc in docs:
                    self.assertLessEqual(int(doc["created_at"][5:7]), step["checkpoint"])
                    ref = doc["source_refs"][0]
                    self.assertEqual(doc["text"], workflow.original_turn(visible[(doc["project"], ref["session_id"])]))
                    if step["checkpoint"] >= 5 and ref["session_id"] == "active-config":
                        self.assertNotIn("=64.", doc["text"])

    def test_common_pack_preserves_full_body_and_budget_without_native_excerpt(self):
        sessions = workflow.workload()[0]["sessions"][:3]
        visible = {(s["project"], s["session_id"]): s for s in sessions}
        with tempfile.TemporaryDirectory() as directory, MemoryBook(Path(directory) / "book.db") as book:
            for session in sessions:
                book.ingest(session)
            docs = {doc["id"]: doc for doc in export_documents(book, visible)}
        project = sessions[0]["project"]
        ids = list(docs)
        for budget in (1, 250, 1200, 2400):
            response = common_pack(ids, docs, project, budget)
            self.assertLessEqual(len(response["context"]), budget)
            self.assertEqual(workflow.source_errors(response, workflow.visible_sources(visible), project), [])
            for hit in response["results"]:
                self.assertEqual(hit["text"], docs[hit["id"]]["text"])
        full = common_pack(ids[:1], docs, project, 2400)
        exact = len(full["context"])
        self.assertEqual(common_pack(ids[:1], docs, project, exact), full)
        self.assertEqual(common_pack(ids[:1], docs, project, exact - 1)["results"], [])
        corrupted = copy.deepcopy(docs)
        corrupted[ids[0]]["text"] += " FABRICATED"
        response = common_pack(ids[:1], corrupted, project, 2400)
        self.assertTrue(workflow.source_errors(response, workflow.visible_sources(visible), project))

    def test_mapping_rejects_duplicate_unknown_and_cross_project_hits(self):
        docs = {"a": {"project": "one"}, "b": {"project": "two"}}
        self.assertEqual(mapped_ids({"results": [{"ref": "a"}]}, "billion", docs, "one"), ["a"])
        for hits in ([{"ref": "a"}, {"ref": "a"}], [{"ref": "missing"}], [{"ref": "b"}]):
            with self.assertRaises(ValueError):
                mapped_ids({"results": hits}, "billion", docs, "one")

    def test_native_book_call_gets_no_gold_and_does_not_use_common_cap_to_excerpt(self):
        class Spy:
            def recall(self, *args, **kwargs):
                self.call = (args, kwargs)
                return {"results": [], "context": ""}
        spy = Spy()
        book_search(spy, "current edge policy", "routing-online")
        self.assertEqual(spy.call, (("current edge policy",), {"project": "routing-online", "limit": 5,
            "budget_chars": 100000, "use_cache": False, "coverage": False}))


if __name__ == "__main__":
    unittest.main()
