"""Adversarial evaluator and corpus integrity, not tuned retrieval targets."""

from copy import deepcopy
from datetime import datetime
import tempfile
from pathlib import Path
import unittest

from benchmarks import v014_scale as scale
from benchmarks import v014_audit as audit
from benchmarks.v014_workload import (TARGETS, TRANSFER_TARGETS, cases, checkpoints,
    digest, sessions, source_for, source_turn)


def supplied(case, spec, session=None):
    source = source_for(spec, case["project"], session or case["required"][0]["session_id"])
    text = source_turn(source["messages"], 0)
    ref = {"project": source["project"], "session_id": source["session_id"], "turn_index": 0,
           "start": 0, "end": len(text), "turn_start": 0, "turn_end": len(text), "created_at": source["created_at"]}
    hit = {"id": "p_fixture", "text": text, "source_refs": [ref], "breadcrumb": [{"id": source["project"]}]}
    header = f"[p_fixture] {ref['project']} / {ref['session_id']} | {ref['created_at']}\n"
    return {"context": (header if case["surface"] == "recall" else "") + text, "results": [hit]}


class V014WorkloadTests(unittest.TestCase):
    def test_stage_sizes_come_from_source_turns_and_fixed_old_targets(self):
        self.assertEqual([s["total_pages"] for s in checkpoints()],
                         [1024, 1024, 10016, 50016, 100032, 100032, 100032, 100020])
        self.assertGreaterEqual(checkpoints("expanded")[-1]["total_pages"], 200000)
        for spec in checkpoints("smoke"):
            sources = list(sessions(spec))
            self.assertEqual(sum(len(r["messages"]) // 2 for r in sources), spec["total_pages"])
            self.assertEqual(len({(r["project"], r["session_id"]) for r in sources}), len(sources))
            for target in TARGETS:
                if target["lifecycle"] == "inactive":
                    expected = 15 if spec["delete_config"] else 16
                    self.assertEqual(sum(len(r["messages"]) // 2 for r in sources if r["project"] == target["project"]), expected)

    def test_age_control_and_layout_control_change_only_registered_axis(self):
        initial, aged = [list(sessions(s)) for s in checkpoints("smoke")[:2]]
        for one, two in zip(initial, aged):
            first, second = one.pop("created_at"), two.pop("created_at")
            self.assertEqual(one, two)
            self.assertEqual((datetime.fromisoformat(first) - datetime.fromisoformat(second)).days, 7300)
        grouped, interleaved = [list(sessions(s)) for s in checkpoints("smoke")[4:6]]
        self.assertEqual({(r["project"], r["session_id"]): digest(r) for r in grouped},
                         {(r["project"], r["session_id"]): digest(r) for r in interleaved})
        self.assertNotEqual(grouped, interleaved)

    def test_gold_and_original_reconstruction_include_transfer_foreign_distractors(self):
        for spec in checkpoints("smoke"):
            for source in sessions(spec):
                self.assertEqual(source_for(spec, source["project"], source["session_id"]), source)
            for case in cases(spec):
                for gold in case["required"] + case["stale"]:
                    original = source_for(spec, case["project"], gold["session_id"])
                    self.assertIn(gold["quote"], source_turn(original["messages"], gold["turn_index"]))
        self.assertEqual(len(cases()), 108)
        self.assertEqual(sum(c["cohort"] == "authored-transfer-v014" for c in cases()), 36)
        sources = list(sessions(checkpoints("smoke")[3]))
        self.assertTrue(any("-transfer-foreign-" in s["project"] for s in sources))
        self.assertTrue(any(s["project"] != "lease-archive" and s["project_name"] == "lease engine" for s in sources))

    def test_deleted_sources_are_not_reconstructable_or_answerable(self):
        spec = checkpoints("smoke")[-1]
        for target in TARGETS:
            with self.assertRaises(KeyError):
                source_for(spec, target["project"], "active-config")
        deleted = [c for c in cases(spec) if c["category"] in {"identifier", "replacement"}]
        self.assertEqual(len(deleted), 24)
        self.assertTrue(all(not c["required"] for c in deleted))


class V014AuditorTests(unittest.TestCase):
    def setUp(self):
        self.spec = checkpoints("smoke")[0]
        self.case = next(c for c in cases() if c["id"] == "lease-archive:current")
        self.response = supplied(self.case, self.spec)

    def test_complete_citations_pass_and_fabricated_suffix_does_not(self):
        self.assertTrue(scale.score(self.response, self.case, self.spec)["complete"])
        bad = deepcopy(self.response)
        bad["results"][0]["text"] += " invented material"
        bad["context"] += " invented material"
        self.assertFalse(scale.score(bad, self.case, self.spec)["complete"])
        self.assertTrue(scale.score(bad, self.case, self.spec)["source_errors"])

    def test_foreign_scope_and_bad_unicode_offsets_cannot_receive_credit(self):
        for key, value in (("project", "lease-live"), ("turn_end", 999999), ("created_at", "2026-11-19")):
            bad = deepcopy(self.response)
            bad["results"][0]["source_refs"][0][key] = value
            self.assertFalse(scale.score(bad, self.case, self.spec)["complete"])

    def test_multisource_requires_both_evidence_pages_and_retains_current_rank(self):
        case = next(c for c in cases() if c["id"] == "lease-archive:multi_source")
        current = supplied(case, self.spec)
        boundary = supplied(case, self.spec, "boundary-contract")
        self.assertFalse(scale.score(current, case, self.spec)["complete"])
        both = {"context": boundary["context"] + "\n\n" + current["context"],
                "results": boundary["results"] + current["results"]}
        result = scale.score(both, case, self.spec)
        self.assertTrue(result["complete"])
        self.assertEqual(result["required_ranks"], [2, 1])
        self.assertFalse(result["current_source_first"])

    def test_missing_is_measured_separately_and_deletion_rejects_stale_cache(self):
        missing = next(c for c in cases() if c["id"] == "lease-archive:missing")
        result = scale.score(self.response, missing, self.spec)
        self.assertIsNone(result["complete"])
        self.assertTrue(result["returned_context_for_missing"])
        config = next(c for c in cases() if c["id"] == "lease-archive:identifier")
        old = supplied(config, self.spec)
        revised = checkpoints("smoke")[-2]
        new_case = next(c for c in cases(revised) if c["id"] == config["id"])
        self.assertTrue(scale.score(old, new_case, revised)["source_errors"])
        deleted = checkpoints("smoke")[-1]
        deleted_case = next(c for c in cases(deleted) if c["id"] == config["id"])
        self.assertTrue(scale.score(old, deleted_case, deleted)["source_errors"])

    def test_required_fields_are_explicit_inputs_not_gold_answer_values(self):
        for case in cases():
            fields = scale.required_fields(case)
            for field in fields:
                self.assertIn(field, case["query"])
                self.assertNotIn("=", field)

    def test_protocol_bindings_include_inherited_auditor_and_workload(self):
        identity = scale.protocol_identity()
        self.assertIn("benchmarks/v013_scale.py", identity["files"])
        self.assertIn("benchmarks/v013_workload.py", identity["files"])
        self.assertIn("benchmarks/v014_audit.py", identity["files"])
        self.assertTrue(all(len(value) == 64 for value in identity["files"].values()))

    def test_exact_matrix_count_separates_gate_and_lifecycle_calls(self):
        bound = {"repetitions": 1, "warm_calls": 1, "required_fields_controls": True}
        reference, replacement = checkpoints("smoke")[0], checkpoints("smoke")[-2]
        self.assertEqual(audit.expected_count(bound, reference, "baseline", 0), 144)
        self.assertEqual(audit.expected_count(bound, reference, "candidate", 0), 216)
        self.assertEqual(audit.expected_count(bound, replacement, "baseline", 0), 179)
        self.assertEqual(audit.expected_count(bound, replacement, "candidate", 1), 21)

    def test_work_counter_connections_and_cache_purge_include_local_books(self):
        class Database:
            def __init__(self): self.calls = []
            def execute(self, sql): self.calls.append(sql)
        from types import SimpleNamespace
        parent, first, second = Database(), Database(), Database()
        book = SimpleNamespace(db=parent, _project_indexes=SimpleNamespace(entries={
            "first": SimpleNamespace(book=SimpleNamespace(db=first)),
            "second": SimpleNamespace(book=SimpleNamespace(db=second))}))
        self.assertEqual(scale.cached_connections(book), [parent, first, second])
        scale.clear_recall_caches(book)
        for connection in (parent, first, second):
            self.assertEqual(connection.calls, ["DELETE FROM recall_cache"])


if __name__ == "__main__":
    unittest.main()
