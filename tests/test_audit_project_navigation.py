"""Retained-record audit rejection tests; no models or quality retrieval."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from scripts import audit_project_navigation as audit


def document(identity="p1", project="Scope-A", text="alpha\nbeta\n"):
    return {"id": identity, "project": project, "text": text, "title": "Configure fixture",
            "source_refs": [{"project": project, "session_id": "active-config", "turn_index": 0}]}


def native_record(doc, eligible):
    identity = audit.reme_identity(doc)
    return {"hit_ids": [doc["id"]],
            "records": [{"id": doc["id"], "project": doc["project"], "text": doc["text"]}],
            "native_search_filter": {"paths": [audit.reme_identity(item)["native_path"] for item in eligible]},
            "native_payload": [{"id": identity["native_chunk_id"], "path": identity["native_path"],
                                "start_line": 1, "end_line": identity["end_line"], "text": doc["text"],
                                "scores": {"keyword": 1.0}}]}


def scope_row(name, response=None, *, chapter="ch-scope-a"):
    status, projects = audit.SCOPE_CASES[name]
    kwargs = audit.scope_kwargs(name, chapter)
    call = {"method": "recall", "args": ["scopecontracttoken"], "kwargs": kwargs, "status": status}
    if status == "error":
        call.update(error_type="ValueError", error="explicit project required")
    else:
        call["response"] = response if response is not None else {"context": "", "results": []}
    return {"request": {"kwargs": copy.deepcopy(kwargs), "expected": status, "expected_projects": projects},
            "calls": [call]}


class ProjectNavigationAuditContracts(unittest.TestCase):
    def test_native_reme_hash_and_lf_coordinates_have_a_fixed_reference(self):
        value = audit.reme_identity(document())
        self.assertEqual(value["native_path"],
                         "pages/75aacb55b7e7e3cd9386a88aa4823555b725a8be8b953d2637bce9c732bae770/"
                         "f64551fcd6f07823cb87971cfb91446425da18286b3ab1ef935e0cbd7a69f68a.txt")
        self.assertEqual(value["native_chunk_id"], "c493f5fc40c136e33b0bc16cf5273edbbd580014f4735dbc4fedf2825d809907")
        self.assertEqual(value["end_line"], 2)
        self.assertEqual(audit.reme_identity(document(text="alpha\u2028beta\n"))["end_line"], 1)
        self.assertNotEqual(value["native_path"], audit.reme_identity(document(project="scope-a"))["native_path"])

    def test_native_reme_filter_cannot_use_only_the_returned_hits(self):
        first, second, foreign = document(), document("p2"), document("p3", "Scope-AB")
        docs = {item["id"]: item for item in (first, second, foreign)}
        native = native_record(first, [first, second])
        tracker = audit.old.Audit()
        audit.verify_reme_native(tracker, native, [first["id"]], docs, first["project"], "valid")
        self.assertEqual(tracker.failures, [])
        for selected in ([first], [first, second, foreign]):
            changed = copy.deepcopy(native)
            changed["native_search_filter"]["paths"] = [audit.reme_identity(item)["native_path"] for item in selected]
            tracker = audit.old.Audit()
            audit.verify_reme_native(tracker, changed, [first["id"]], docs, first["project"], "changed-filter")
            self.assertEqual(tracker.failed_counts["reme_exact_prelimit_paths"], 1)

    def test_changed_native_chunk_identity_or_body_is_not_repaired(self):
        doc = document()
        native = native_record(doc, [doc])
        for field, changed_value, failed_check in (("id", "invented", "reme_native_chunk_identity"),
                                                   ("text", "rewritten", "reme_native_original_text"),
                                                   ("end_line", 3, "reme_native_chunk_identity")):
            changed = copy.deepcopy(native)
            changed["native_payload"][0][field] = changed_value
            tracker = audit.old.Audit()
            audit.verify_reme_native(tracker, changed, [doc["id"]], {doc["id"]: doc}, doc["project"], "fixture")
            self.assertEqual(tracker.failed_counts[failed_check], 1)

    def test_scope_producer_cannot_rewrite_the_registered_request(self):
        row = scope_row("multiple-books")
        row["calls"][0]["kwargs"] = {"project": "scope-a"}
        row["request"]["kwargs"] = {"project": "scope-a"}
        tracker = audit.old.Audit()
        audit.verify_scope_call(tracker, row, "multiple-books", "ch-scope-a", {}, "fixture")
        self.assertEqual(tracker.failed_counts["scope_registered_parameters"], 1)
        self.assertEqual(tracker.failed_counts["scope_registered_request"], 1)

    def test_empty_unknown_scope_cannot_hide_foreign_text_outside_results(self):
        body = "USER: scopecontracttoken\n\nASSISTANT: foreign original value."
        row = scope_row("unknown-project", {"context": body, "results": []})
        tracker = audit.old.Audit()
        audit.verify_scope_call(tracker, row, "unknown-project", "ch-scope-a",
                                {("scope-a", "shared", 0): body}, "fixture")
        self.assertEqual(tracker.failed_counts["no_scope_result_has_empty_context"], 1)
        self.assertEqual(tracker.failed_counts["no_unreferenced_foreign_scope_body"], 1)

    def test_directory_summary_is_checked_against_original_question_and_body(self):
        doc = document(project="alpha", text="USER: Configure fixture\n\nASSISTANT: Original fixture answer.")
        request = {"id": "directory-fixture", "project": "alpha", "kind": "title", "query": "Configure fixture"}
        entry = {"section_id": "s1", "matched_page_id": doc["id"], "title": doc["title"],
                 "summary": doc["title"], "session_id": "active-config", "breadcrumb": [{"id": "alpha"}],
                 "source_refs": doc["source_refs"]}
        row = {"request": request, "calls": [{"method": "search_directory", "args": [request["query"], "alpha"],
                "kwargs": {"offset": 0, "limit": 2}, "status": "ok", "response": {
                    "project": {"id": "alpha"}, "match_fields": ["title", "question", "directory"],
                    "entries": [entry], "total": 1, "next_offset": None}}]}
        tracker = audit.old.Audit()
        audit.audit_directory_query(tracker, row, request, {doc["id"]: doc}, "valid")
        self.assertEqual(tracker.failures, [])
        row["calls"][0]["response"]["entries"][0]["summary"] = doc["text"]
        tracker = audit.old.Audit()
        audit.audit_directory_query(tracker, row, request, {doc["id"]: doc}, "corrupted")
        self.assertEqual(tracker.failed_counts["directory_no_hidden_source_body"], 1)
        self.assertEqual(tracker.failed_counts["directory_question_summary"], 1)

    def test_global_and_neighbor_missing_denominators_remain_separate(self):
        cases = {"global": {"required": [], "category": "missing_evidence_global"},
                 "neighbor": {"required": [], "category": "missing_evidence_neighbor"}}
        rows = {("global", "book", 1200): {"case_id": "global", "backend": "book", "budget_chars": 1200,
                                             "response": {"context": "Unrelated retained source"}},
                ("neighbor", "book", 1200): {"case_id": "neighbor", "backend": "book", "budget_chars": 1200,
                                               "response": {"context": ""}}}
        cells = {cell["category"]: cell for cell in audit.missing_categories(rows, cases)
                 if cell["backend"] == "book" and cell["budget_chars"] == 1200}
        self.assertEqual(cells["missing_evidence_global"]["nonempty_context_case_ids"], ["global"])
        self.assertEqual(cells["missing_evidence_neighbor"]["empty_context_case_ids"], ["neighbor"])
        self.assertTrue(all(cell["expected_cases"] == 1 and cell["completed_cases"] == 1 for cell in cells.values()))

    def test_cross_harness_comparison_checks_all_packed_fields(self):
        left = {("case", "book", budget): {"response": {"context": "", "results": [], "omitted_for_budget": []}}
                for budget in audit.BUDGETS}
        right = copy.deepcopy(left)
        right[("case", "book", 2400)]["response"]["unexpected"] = "not produced by common_pack"
        tracker = audit.old.Audit()
        result = audit.compare_packed(tracker, left, right, {"case": {}}, ("book",), "fixture")
        self.assertEqual(result["equal_pairs"], 1)
        self.assertEqual(result["mismatches"], [["case", "book", 2400]])

    def test_audit_output_cannot_overwrite_retained_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "retained.json"
            output.write_text('{"retained":true}\n')
            with self.assertRaises(FileExistsError):
                audit.run(Path(temp), output)
            self.assertEqual(output.read_text(), '{"retained":true}\n')

    def test_independent_roundtrip_audit_accepts_real_tiny_native_windows(self):
        from memory_book import MemoryBook
        from benchmarks import engineering_components as components
        from benchmarks import project_navigation_contracts as contracts

        source = {"project": "audit-scope", "session_id": "active-config", "task_id": audit.data.MAIN_TASK,
                  "created_at": "2026-01-01T00:00:00+00:00", "messages": [
                      {"role": "user", "content": "Independent address fixture"},
                      {"role": "assistant", "content": "Original audit fixture text. " * 9}]}
        source_id = (source["project"], source["session_id"], 0)
        originals = {source_id: audit.engineering.original_turn(source)}
        request = {"project": source["project"], "task_id": audit.data.MAIN_TASK, "session_id": "active-config"}
        with tempfile.TemporaryDirectory() as temp, MemoryBook(Path(temp) / "tiny.db") as book:
            book.ingest(source)
            docs = {doc["id"]: doc for doc in components.export_documents(book, {source_id[:2]: source})}
            row = contracts.execute_probe("tiny", "roundtrip", request, lambda probe: contracts.directory_roundtrip(
                probe, book, source["project"], originals, {}))
            self.assertEqual(row["status"], "passed", row.get("error"))
            tracker = audit.old.Audit()
            audit.audit_call_traffic(tracker, row, "tiny")
            audit.audit_roundtrip(tracker, row, source["project"], docs, originals, "tiny")
            self.assertEqual(tracker.failures, [])

    def test_independent_scope_audit_accepts_real_two_source_fixture(self):
        from benchmarks import project_navigation_contracts as contracts

        with tempfile.TemporaryDirectory() as temp:
            rows, sources = contracts.scope_contracts(Path(temp))
        self.assertEqual(len(rows), 14)
        chapter = next(row for row in rows if row["case_id"] == "scope:known-chapter")["calls"][0]["kwargs"]["chapter"]
        originals = {(source["project"], source["session_id"], 0): audit.engineering.original_turn(source) for source in sources}
        tracker = audit.old.Audit()
        for row in rows:
            self.assertEqual(row["status"], "passed", row.get("error"))
            audit.verify_scope_call(tracker, row, row["case_id"][len("scope:"):], chapter, originals, row["case_id"])
        self.assertEqual(tracker.failures, [])


if __name__ == "__main__":
    unittest.main()
