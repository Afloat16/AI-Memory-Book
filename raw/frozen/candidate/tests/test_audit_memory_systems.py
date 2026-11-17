"""Small retained-output fixtures; no foreign packages, models or retrieval."""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from scripts import audit_memory_systems as audit


def fixture():
    steps, cases, sources, sessions = audit.canonical_protocol()
    case = copy.deepcopy(next(iter(cases.values())))
    checkpoint = case["checkpoint"]
    session_id = case["required"][0]["session_id"]
    source_id = (case["project"], session_id, 0)
    body = sources[checkpoint][source_id]
    session = sessions[checkpoint][source_id[:2]]
    doc = {"id": "fixture-page", "project": case["project"], "title": session["title"],
           "text": body, "created_at": session["created_at"], "source_refs": [{
               "project": case["project"], "session_id": session_id, "turn_index": 0,
               "start": 0, "end": len(body), "turn_start": 0, "turn_end": len(body),
               "created_at": session["created_at"], "message_indices": [0, 1]}]}
    protocol = ([steps[0]], {case["id"]: case}, sources, sessions)
    docs = {checkpoint: {doc["id"]: doc}}
    payload = {"results": [{"id": doc["id"], "text": body}]}
    samples = [{"repetition": n, "adapter_call_ms": 1.0, "native_search_ms": 1.0,
                "native_bridge_ms": 1.0, "hit_ids": [doc["id"]],
                "native_sha256": audit.workflow.sha(payload), "native": copy.deepcopy(payload)}
               for n in range(audit.REPEATS)]
    native = {"case_id": case["id"], "backend": "book", "query": case["query"],
              "project": case["project"], "checkpoint": checkpoint, "samples": samples}
    packed = []
    for budget in audit.BUDGETS:
        response = audit.common_pack([doc["id"]], docs[checkpoint], case["project"], budget)
        packed.append({"case_id": case["id"], "backend": "book", "query": case["query"],
                       "project": case["project"], "checkpoint": checkpoint,
                       "category": case["category"], "budget_chars": budget,
                       "response": response, "latency_ms": [1.0] * audit.REPEATS,
                       "repeat_outputs_equal": True,
                       "native_first_output_sha256": samples[0]["native_sha256"],
                       "score": audit.workflow.score(case, response, sources[checkpoint], budget)})
    return protocol, docs, native, packed


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class MemorySystemsAuditContracts(unittest.TestCase):
    def test_canonical_equality_rejects_json_type_changes(self):
        tracker = audit.Audit()
        self.assertTrue(tracker.equal({"a": 1, "b": 2}, {"b": 2, "a": 1}, "equality", "order"))
        self.assertFalse(tracker.equal(True, 1, "equality", "boolean"))
        self.assertFalse(tracker.equal(1200.0, 1200, "equality", "integer"))
        tracker.unique([{"budget": 1200.0}], ("budget",), {(1200,)}, "typed-identity")
        self.assertEqual(tracker.failed_counts["row_identity_types"], 1)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for raw in ('{"case_id": "first", "case_id": "second"}',
                    '{"latency_ms": NaN}', '{"score": Infinity}', '{"score": -Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                audit.strict_json(raw)

    def test_duplicate_matrix_row_does_not_replace_missing_case(self):
        tracker = audit.Audit()
        rows = [{"case_id": "one", "backend": "book", "budget": 1200}] * 2
        expected = {("one", "book", 1200), ("two", "book", 1200)}
        index = tracker.unique(rows, ("case_id", "backend", "budget"), expected, "fixture")
        self.assertEqual(len(index), 1)
        self.assertEqual(tracker.failed_counts["unique_row_identity"], 1)
        self.assertEqual(tracker.failed_counts["complete_exact_matrix"], 1)

    def test_plain_and_gzip_disagreement_is_retained_as_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "raw.jsonl"
            path.write_bytes(b'{"value": 1}\n')
            Path(str(path) + ".gz").write_bytes(gzip.compress(b'{"value": 2}\n'))
            tracker = audit.Audit()
            self.assertEqual(tracker.jsonl(path), [{"value": 1}])
            self.assertEqual(tracker.failed_counts["equivalent_duplicate_transports"], 1)
            self.assertEqual(len(tracker.inputs), 2)

    def test_valid_retained_candidates_and_both_whole_block_budgets_recompute(self):
        protocol, docs, native, packed = fixture()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_rows(folder / "native.jsonl", [native])
            write_rows(folder / "raw.jsonl", packed)
            tracker = audit.Audit()
            native_index = audit.audit_native_rows(tracker, folder, protocol[1], docs, ("book",), "fixture")
            rescored = audit.audit_packed_rows(tracker, folder, protocol, ("book",), "fixture",
                                              documents=docs, native=native_index)
            self.assertEqual(len(rescored), 2)
            self.assertEqual(tracker.failures, [])

    def test_score_and_entire_packed_response_are_independently_checked(self):
        protocol, docs, native, packed = fixture()
        packed[0]["score"]["matched_evidence"] = 0
        # This does not affect the scorer, but is still an unauthorized change
        # to the common packer's complete response.
        packed[1]["response"]["extra_field"] = "not produced by common_pack"
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_rows(folder / "raw.jsonl", packed)
            tracker = audit.Audit()
            audit.audit_packed_rows(tracker, folder, protocol, ("book",), "fixture", documents=docs,
                                    native={(native["case_id"], "book"): native})
            self.assertEqual(tracker.failed_counts["score_recomputes_exactly"], 1)
            self.assertEqual(tracker.failed_counts["whole_packed_response_rebuilds"], 1)

    def test_three_repetitions_cannot_hide_a_different_candidate_list(self):
        protocol, docs, native, _ = fixture()
        changed = native["samples"][1]
        changed["hit_ids"] = []
        changed["native"] = {"results": []}
        changed["native_sha256"] = audit.workflow.sha(changed["native"])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_rows(folder / "native.jsonl", [native])
            tracker = audit.Audit()
            audit.audit_native_rows(tracker, folder, protocol[1], docs, ("book",), "fixture")
            self.assertEqual(tracker.failed_counts["three_candidates_stable"], 1)
            self.assertEqual(tracker.failed_counts["complete_nontiming_native_stability"], 1)
            self.assertEqual(tracker.failed_counts["native_digest_recomputes"], 0)

    def test_first_and_repeat_native_timing_boundaries_recompute_separately(self):
        _, _, native, _ = fixture()
        for sample, value in zip(native["samples"], (100.0, 2.0, 4.0)):
            sample["adapter_call_ms"] = value
            sample["native_search_ms"] = value / 2
            sample["native_bridge_ms"] = value / 4
        summary = audit.native_timing_summary({(native["case_id"], "book"): native}, ("book",))
        self.assertEqual(summary["book"]["first_query_search"]["adapter_call_ms"],
                         {"samples": 1, "p50_ms": 100.0, "p95_ms": 100.0})
        self.assertEqual(summary["book"]["repeat_query_search"]["adapter_call_ms"],
                         {"samples": 2, "p50_ms": 3.0, "p95_ms": 3.9})
        self.assertEqual(summary["book"]["repeat_query_search"]["native_search_ms"]["p50_ms"], 1.5)
        self.assertEqual(summary["book"]["repeat_query_search"]["native_bridge_ms"]["p50_ms"], .75)

    def test_query_and_source_corruptions_fail_despite_self_consistent_hashes(self):
        protocol, docs, native, _ = fixture()
        native["query"] = "rewritten question"
        for sample in native["samples"]:
            sample["native"]["results"][0]["text"] = "altered original source"
            sample["native_sha256"] = audit.workflow.sha(sample["native"])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_rows(folder / "native.jsonl", [native])
            tracker = audit.Audit()
            audit.audit_native_rows(tracker, folder, protocol[1], docs, ("book",), "fixture")
            self.assertEqual(tracker.failed_counts["native_case_metadata"], 1)
            self.assertEqual(tracker.failed_counts["native_original_body"], 3)

    def test_failure_mode_worsening_is_retained_even_when_pass_counts_do_not_change(self):
        protocol, _, _, packed = fixture()
        case_id = packed[0]["case_id"]
        old, new = copy.deepcopy(packed[0]), copy.deepcopy(packed[0])
        for row in (old, new):
            row["score"]["complete_evidence"] = False
        old["score"]["fixed_consumer"] = {"selected_policy": None, "abstained": True, "all_passed": False}
        new["score"]["fixed_consumer"] = {"selected_policy": "wrong_policy", "abstained": False,
                                            "all_passed": False}
        new["score"]["stale_only"] = True
        key = (case_id, "book", 1200)
        result = audit.paired({key: old}, {key: new}, protocol[1], 1200, "book", "book", "fixture")
        self.assertEqual(result["complete_evidence"]["counts"]["gains"], 0)
        self.assertEqual(result["fixed_policy"]["counts"]["losses"], 0)
        self.assertEqual(result["stale_only"]["introduced"], [case_id])
        self.assertEqual(result["change_details"][0]["left"]["fixed_consumer"]["abstained"], True)
        self.assertEqual(result["change_details"][0]["right"]["fixed_consumer"]["selected_policy"], "wrong_policy")

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "retained.json"
            output.write_text('{"retained": true}\n')
            with self.assertRaises(FileExistsError):
                audit.run(Path(temp), output)
            self.assertEqual(output.read_text(), '{"retained": true}\n')


if __name__ == "__main__":
    unittest.main()
