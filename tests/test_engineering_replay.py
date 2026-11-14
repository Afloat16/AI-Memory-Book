"""Artificial protocol counterexamples; no upstream tests or real-case recall."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import engineering_replay as replay


def block(identity="block", source="source", text="base", start=0, commit="c", project="repo"):
    return {"id": identity, "source_id": source, "project": project, "commit": commit,
            "path": "example.py", "created_at": "2024-01-01T00:00:00Z",
            "title": "original source", "text": text, "start_char": start,
            "end_char": start + len(text), "start_line": 1, "end_line": 1}


def span(source="source", text="base", start=0):
    return {"source_id": source, "start_char": start, "end_char": start + len(text),
            "quote": text, "quote_sha256": replay.digest(text.encode())}


class ReplayControlsTests(unittest.TestCase):
    def test_chunking_preserves_every_original_unicode_character(self):
        text = ("  café = 1\n\n" * 120) + "é" * 1000
        record = {"id": "source", "repository": "repo", "commit": "c",
                  "path": "example.py", "committer_utc": "2024-01-01T00:00:00Z", "text": text}
        chunks = list(replay.chunks(record))
        self.assertEqual("".join(b["text"] for b in chunks), text)
        self.assertTrue(all(0 < len(b["text"]) <= 900 for b in chunks))
        for previous, following in zip(chunks, chunks[1:]):
            self.assertEqual(previous["end_char"], following["start_char"])
        self.assertEqual(chunks[-1]["end_char"], len(text))

    def test_git_blob_identity_is_not_plain_content_sha1(self):
        self.assertEqual(replay.source_blob(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")
        self.assertNotEqual(replay.source_blob(b"hello\n"), replay.source_blob(b"hello\r\n"))

    def test_cutoff_rejects_future_wrong_project_and_nonancestor(self):
        old = block("old", commit="a")
        current = block("current")
        future = block("future", commit="d")
        future["created_at"] = "2024-02-01T00:00:00Z"
        wrong = block("wrong", project="other")
        divergent = block("divergent", commit="side")
        case = {"project": "repo", "public_input": {"target_repo": "repo",
                "snapshot_commit": "c", "availability_cutoff_utc": "2024-01-01T00:00:00Z"}}
        inputs = {"blocks": [old, current, future, wrong, divergent],
                  "ancestors": {("repo", "a", "c"), ("repo", "d", "c")}}
        self.assertEqual({b["id"] for b in replay.eligible_blocks(inputs, case)}, {"old", "current"})

    def test_public_project_metadata_must_agree(self):
        with self.assertRaises(ValueError):
            replay.eligible_blocks({"blocks": [], "ancestors": set()},
                {"project": "repo", "public_input": {"target_repo": "other",
                 "snapshot_commit": "c", "availability_cutoff_utc": "2024-01-01T00:00:00Z"}})

    def test_flat_control_handles_identifiers_without_indexing_labels(self):
        item = block(text="class ABCCodec: pass")
        item["reference_answer"] = "hiddenanswerphrase"
        engine = replay.FlatFTS([item, block("other", "other", "unrelated")], Path("."))
        try:
            self.assertEqual(engine.search("abc codec", "repo")[0], ["block"])
            self.assertEqual(engine.search("hiddenanswerphrase", "repo")[0], [])
        finally:
            engine.close()

    def test_common_first_fit_keeps_original_blocks_without_truncation(self):
        a, b, c = block("a", text="tiny"), block("b", text="x" * 150), block("c", text="small")
        mapping = {x["id"]: x for x in (a, b, c)}
        cap = len(replay.source_block_text(a) + "\n\n" + replay.source_block_text(c))
        packed = replay.pack_blocks(["a", "b", "c"], mapping, cap, len)
        self.assertEqual(packed["block_ids"], ["a", "c"])
        self.assertEqual(packed["context"], replay.source_block_text(a) + "\n\n" + replay.source_block_text(c))
        self.assertEqual(packed["context_tokens"], cap)

    def test_duplicates_do_not_trigger_replacement_reads(self):
        item = block()
        self.assertEqual(replay.checked_ids(["block", "block"], {"block": item}, "repo"), ["block"])
        with self.assertRaises(ValueError):
            replay.checked_ids(["future"], {"block": item}, "repo")
        with self.assertRaises(ValueError):
            replay.checked_ids(["block"] * 6, {"block": item}, "repo")
        with self.assertRaises(ValueError):
            replay.checked_ids(["block"], {"block": item}, "another")

    def test_evidence_requires_original_source_identity_and_full_span(self):
        required = span(text="abcdef")
        pieces = [block("one", text="abc"), block("two", text="def", start=3)]
        self.assertFalse(replay.covered(required, pieces[:1]))
        self.assertTrue(replay.covered(required, pieces))
        label = {"answerable": True, "required_spans": [required], "stale_spans": []}
        self.assertEqual(replay.evidence_score(label, pieces)["first_evidence_rank"], 2)
        wrong = [block(text="abcdef", source="other")]
        self.assertEqual(replay.evidence_score(label, wrong)["evidence_recall"], 0)

    def test_unsupported_retrieval_is_not_generated_answer_correctness(self):
        label = {"answerable": False, "required_spans": [], "stale_spans": []}
        score = replay.evidence_score(label, [])
        self.assertIsNone(score["complete_evidence"])
        self.assertIsNone(score["evidence_recall"])
        self.assertFalse(score["unsupported_nonempty"])
        self.assertTrue(replay.evidence_score(label, [block()])["unsupported_nonempty"])

    def test_native_book_mapping_rejects_scope_switch(self):
        payload = {"results": [{"source_refs": [{"session_id": "block", "project": "other"}]}]}
        with self.assertRaises(ValueError):
            replay.native_ids_from_payload("candidate", payload, "repo")

    def test_gold_cannot_reference_future_source_or_changed_quote(self):
        current = block()
        case = {"id": "q", "project": "repo", "public_input": {"target_repo": "repo",
                "snapshot_commit": "c", "availability_cutoff_utc": current["created_at"]}}
        inputs = {"cases": [case], "blocks": [current], "ancestors": set(),
                  "records": {"source": {"kind": "implementation_source", "text": "base"},
                              "future": {"kind": "implementation_source", "text": "base"}}}
        gold = {"queries": {"q": {"answerable": True, "required_spans": [span()], "stale_spans": []}}}
        replay.validate_gold(inputs, gold)
        changed = deepcopy(gold)
        changed["queries"]["q"]["required_spans"][0]["source_id"] = "future"
        with self.assertRaises(ValueError):
            replay.validate_gold(inputs, changed)
        changed = deepcopy(gold)
        changed["queries"]["q"]["required_spans"][0]["quote"] = "fake"
        with self.assertRaises(ValueError):
            replay.validate_gold(inputs, changed)

    def test_exclusive_claim_preserves_first_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "claim.json"
            replay.atomic(path, {"first": True}, exclusive=True)
            with self.assertRaises(FileExistsError):
                replay.atomic(path, {"replacement": True}, exclusive=True)
            self.assertEqual(replay.read_json(path), {"first": True})

    def test_binding_cannot_replace_registered_baseline_protocol_or_matrix(self):
        protocol = {"protocol": "artificial", "matrix": {"retrieval_calls": 80},
                    "baseline": {"commit": "a" * 40, "runtime_sha256": "b" * 64}}
        binding = {"schema_version": 1, "protocol": "artificial",
                   "status": "frozen-before-first-replay-score", "generation": "none",
                   "protocol_sha256": "f" * 64, "expected_matrix": protocol["matrix"],
                   "sources": {"v0.3.4": {**protocol["baseline"], "source_root": "/baseline"},
                               "candidate": {"commit": "c" * 40, "runtime_sha256": "d" * 64,
                                             "source_root": "/candidate"}}}
        replay.validate_binding_identity(binding, protocol, "f" * 64)
        mutations = [
            lambda b: b["sources"]["v0.3.4"].update(commit="e" * 40),
            lambda b: b["sources"]["v0.3.4"].update(runtime_sha256="e" * 64),
            lambda b: b.update(protocol_sha256="e" * 64),
            lambda b: b.update(expected_matrix={"retrieval_calls": 79}),
            lambda b: b["sources"].pop("candidate"),
        ]
        for mutate in mutations:
            changed = deepcopy(binding)
            mutate(changed)
            with self.assertRaises(ValueError):
                replay.validate_binding_identity(changed, protocol, "f" * 64)
        same_pair = deepcopy(binding)
        same_pair.update(created_at="another timestamp", evaluator_commit="another evaluator")
        same_pair["sources"]["candidate"]["source_root"] = "/moved-candidate"
        self.assertEqual(replay.claim_key(binding), replay.claim_key(same_pair))


class SavedFixtureAuditTests(unittest.TestCase):
    """A complete 80-attempt artificial ledger, including a candidate loss."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engineering-replay-artificial-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.one = block()
        self.inputs = {"cases": [], "blocks": [self.one], "ancestors": set(),
                       "records": {"source": {"kind": "implementation_source", "text": "base"}}}
        self.gold = {"queries": {}}
        for i in range(20):
            identity = f"artificial-{i:02d}"
            self.inputs["cases"].append({"id": identity, "project": "repo", "category": "fixture",
                "query": f"artificial query {i}", "public_input": {"target_repo": "repo",
                "snapshot_commit": "c", "availability_cutoff_utc": self.one["created_at"]}})
            self.gold["queries"][identity] = {"answerable": bool(i % 5),
                "required_spans": [span()] if i % 5 else [], "stale_spans": []}
        self.binding = {"protocol": "artificial", "sources": {"fixture": True},
                        "evaluator_commit": "fixture", "expected_matrix": {"retrieval_calls": 80}}
        self.binding_hash = "artificial-binding"
        self.rows = {}
        for arm_index, arm in enumerate(replay.ARMS):
            report = {"status": "complete", "binding_sha256": self.binding_hash,
                      "gold_loaded_by_worker": False, "rows": [], "setups": [],
                      "worker_peak_rss_bytes": 1, "rss_scope": "artificial fixture"}
            planned = [c for _, cases in replay.plan_cases(self.inputs["cases"]) for c in cases]
            for ordinal, case in enumerate(planned):
                ids = [] if arm == "candidate" and case["id"] == "artificial-01" else ["block"]
                if arm == "flat-fts":
                    payload = {"results": [{"id": x, "score": -1.0} for x in ids]}
                elif arm == "billion-context":
                    payload = {"results": [{"ref": x} for x in ids]}
                else:
                    payload = {"results": [{"source_refs": [{"session_id": x, "project": "repo"}]} for x in ids]}
                request = {"query_id": case["id"], "query": case["query"],
                           "public_input": case["public_input"], "limit": 5, "view": "repo@c"}
                sequence = arm_index * 20 + ordinal
                row = {**request, "sequence": sequence, "arm": arm, "category": "fixture",
                       "lookup_wall_ms": float(arm_index + 1), "readback_ms": 0.01,
                       "native_payload": payload, "native_payload_tokens": len(json.dumps(
                           payload, ensure_ascii=False, separators=(",", ":"))),
                       "native_ids": ids, "selected_blocks": [self.one] if ids else [],
                       "source_block_reads": len(ids), "duplicate_native_ids": 0,
                       "status": "complete", "projections": []}
                for budget in (1024, 4096):
                    projection = replay.pack_blocks(ids, {"block": self.one}, budget, len)
                    projection["packing_ms"] = 0.01
                    row["projections"].append(projection)
                report["rows"].append(row)
                replay.append_event(self.directory / "attempts.jsonl", {"event": "intent",
                    "sequence": sequence, "arm": arm, "query_id": case["id"],
                    "binding_sha256": self.binding_hash, "request_sha256": replay.digest(replay.encoded(request))})
                replay.append_event(self.directory / "attempts.jsonl", {"event": "completion",
                    "sequence": sequence, "arm": arm, "query_id": case["id"], "status": "complete",
                    "row_sha256": replay.digest(replay.encoded(row))})
            replay.atomic(self.directory / (arm + ".json"), report)

    def audit(self):
        original = replay.read_json
        def read(path):
            return self.gold if Path(path) == replay.ROOT / replay.GOLD else original(path)
        with patch.object(replay, "verify_binding", return_value=(self.binding, self.binding_hash, self.inputs)), \
                patch.object(replay, "verify_tokenizer", return_value=len), \
                patch.object(replay, "read_json", side_effect=read), \
                patch.object(replay, "make_engine", side_effect=AssertionError("Audit must never retrieve")):
            return replay.audit_saved(self.directory / "unused-binding.json", self.directory)

    def change_row(self, mutate):
        path = self.directory / "candidate.json"
        report = replay.read_json(path)
        row = report["rows"][0]
        mutate(row)
        replay.atomic(path, report)
        events = [json.loads(line) for line in (self.directory / "attempts.jsonl").read_text().splitlines()]
        for event in events:
            if event["event"] == "completion" and event["sequence"] == row["sequence"]:
                event["row_sha256"] = replay.digest(replay.encoded(row))
        (self.directory / "attempts.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events))

    def test_complete_saved_fixture_keeps_candidate_loss_and_all_empty_controls(self):
        report = self.audit()
        self.assertTrue(report["integrity_passed"])
        self.assertFalse(report["product_acceptance_evaluated"])
        self.assertEqual(len(report["cells"]), 200)
        self.assertEqual(len([c for c in report["cells"] if c["arm"] == "no-memory"]), 40)
        losses = [d for d in report["all_deltas_vs_v034"] if d["arm"] == "candidate"
                  and d["changes"]["complete_evidence"] is not None
                  and d["changes"]["complete_evidence"] < 0]
        self.assertEqual(len(losses), 2)

    def test_changed_query_is_rejected_even_if_completion_hash_is_rewritten(self):
        self.change_row(lambda row: row.update(query="different artificial question"))
        with self.assertRaises(ValueError):
            self.audit()

    def test_native_payload_and_selected_ids_must_match(self):
        def mutate(row):
            row["native_payload"] = {"results": []}
            row["native_payload_tokens"] = len(json.dumps(
                row["native_payload"], ensure_ascii=False, separators=(",", ":")))
        self.change_row(mutate)
        with self.assertRaises(ValueError):
            self.audit()

    def test_changed_context_is_not_accepted_as_a_source_quote(self):
        def mutate(row):
            projection = row["projections"][0]
            projection.update(context="fabricated", context_sha256=replay.digest(b"fabricated"),
                              context_tokens=len("fabricated"))
        self.change_row(mutate)
        with self.assertRaises(ValueError):
            self.audit()

    def test_negative_timing_is_rejected(self):
        self.change_row(lambda row: row.update(lookup_wall_ms=-1))
        with self.assertRaises(ValueError):
            self.audit()

    def test_missing_finish_is_not_replayed_or_scored(self):
        path = self.directory / "attempts.jsonl"
        lines = path.read_text().splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n")
        with self.assertRaises(ValueError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
