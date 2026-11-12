import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qualification", ROOT / "scripts/novelty_cap_qualification.py")
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def sample(identity, ranks):
    return {"id": identity, "evidence_ranks": ranks, "complete": all(r is not None for r in ranks),
            "context_sha256": identity + str(ranks), "block_hashes": [], "required_evidence": len(ranks)}


def report(rows):
    return {"configurations": [{"budget_chars": 2000, "tokenizer": "cl100k_base", "budget_tokens": 512,
        "query_results": rows, "metrics": {}, "by_group": {}}]}


class QualificationTests(unittest.TestCase):
    def test_complete_gain_does_not_compensate_for_another_loss(self):
        old = report([sample("a", [1]), sample("b", [None])])
        new = report([sample("a", [None]), sample("b", [1])])
        result = qualification.compare_reports(old, new)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["comparisons"][0]["complete_question_losses"], ["a"])

    def test_annotation_loss_rejects_even_when_both_remain_incomplete(self):
        old, new = report([sample("a", [1, None])]), report([sample("a", [None, 2])])
        result = qualification.compare_reports(old, new)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(result["comparisons"][0]["annotation_losses"]), 1)

    def test_identical_or_improved_evidence_qualifies(self):
        old, new = report([sample("a", [1, None])]), report([sample("a", [1, 2])])
        self.assertEqual(qualification.compare_reports(old, new)["status"], "qualified")
        self.assertEqual(qualification.compare_reports(old, old)["status"], "qualified")

    def test_query_axis_changes_are_not_missing_losses(self):
        with self.assertRaises(ValueError):
            qualification.compare_reports(report([sample("a", [1])]), report([sample("b", [1])]))

    def test_source_and_q2_stage_are_explicit_for_both_roles(self):
        plan = {"sources": {"current": {"commit": "control"}, "cap": {"commit": "candidate"}},
                "phases": [{"name": "A", "token_budgets": [512]}], "variants": qualification.VARIANTS,
                "common": {"repeats": 1}, "cohort": {"seed": 23017},
                "native": {"budget_chars": [2000, 8000], "tokenizers": ["cl100k_base", "o200k_base"]}}
        calls = 0
        for variant in qualification.VARIANTS:
            phase, registered, hp, hb = qualification.worker_spec(plan, "A", variant["name"])
            self.assertEqual(hb["candidate"], plan["sources"][variant["source"]])
            self.assertEqual(registered["helper_stage"] == "candidate-semantic-native", variant["semantic"])
            calls += 256 * len(hp["native"]["budget_chars"]) * len(hp["native"]["tokenizers"]) * len(phase["token_budgets"])
        self.assertEqual(calls, 4096)

    def test_actions_rerun_and_wrong_ref_are_rejected(self):
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book",
               "GITHUB_REF": "refs/heads/ci/novelty-cap-qualification-run", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        with patch.dict(os.environ, env):
            self.assertEqual(qualification.actions_identity(), "123-1")
            with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
                with self.assertRaises(ValueError): qualification.actions_identity()
            with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main"}):
                with self.assertRaises(ValueError): qualification.actions_identity()

    def test_vector_digest_tracks_blob_bytes_not_write_time_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = (Path(directory) / name for name in ("a.db", "b.db"))
            for path, metadata in ((a, "first clock"), (b, "later clock")):
                with sqlite3.connect(path) as db:
                    db.execute("CREATE TABLE semantic_vectors(page_id TEXT, ordinal INT, char_start INT, char_end INT, vector BLOB, PRIMARY KEY(page_id,ordinal))")
                    db.execute("CREATE TABLE semantic_meta(singleton INT, revision INT, model_fingerprint TEXT, metadata TEXT)")
                    db.execute("INSERT INTO semantic_meta VALUES(1,7,'same-model',?)", (metadata,))
                    db.execute("INSERT INTO semantic_vectors VALUES('p',0,0,5,?)", (bytes(1536),))
            self.assertEqual(qualification.vectors_digest(a), qualification.vectors_digest(b))
            with sqlite3.connect(b) as db:
                db.execute("UPDATE semantic_vectors SET vector=?", (b'\x01' + bytes(1535),))
            self.assertNotEqual(qualification.vectors_digest(a)["sha256"], qualification.vectors_digest(b)["sha256"])

    def test_public_whitelist_includes_only_named_worker_ledgers(self):
        plan = json.loads(qualification.PLAN.read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cp = root / "checkpoint.json"; cp.write_text("{}")
            for name in ("A-current-q2.attempts.jsonl.gz", "private.log", "source.json", "other.attempts.jsonl.gz"):
                (root / name).write_bytes(b"fixture")
            names = {p.name for p in qualification.public_names(cp, root, plan)}
            self.assertEqual(names, {"checkpoint.json", "A-current-q2.attempts.jsonl.gz"})

    def controller_fixture(self, decisions, fail_worker=None):
        plan = json.loads(qualification.PLAN.read_bytes())
        observed = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def execute(argv, *args):
                name = argv[argv.index("--variant") + 1]
                phase = argv[argv.index("--phase") + 1]
                observed.append((phase, name))
                state = Path(argv[argv.index("--state") + 1]); state.mkdir(parents=True)
                # This toy public record verifies supervisor preservation when
                # a killed worker cannot produce a full raw/summary report.
                (state / "attempts.jsonl").write_text('{"event":"started","id":"invented"}\n')
                if name == fail_worker:
                    raise TimeoutError("invented terminated worker")
                return 0
            def assess(plan, binding, manifest, cp, phase, result_dir):
                return {"phase": phase["name"], "status": decisions[phase["name"]],
                        "actual_finished_calls": phase["expected_calls"]}
            with patch.dict(os.environ, {}), redirect_stdout(io.StringIO()), \
                 patch.object(qualification, "ROOT", root), patch.object(qualification, "registered_inputs", return_value=(plan, {}, {}, {}, {})), \
                 patch.object(qualification, "verify_source_delta"), patch.object(qualification, "actions_identity", return_value="123-1"), \
                 patch.object(qualification, "git", return_value="fixture-head"), patch.object(qualification, "host_record", return_value={"id":"123-1"}), \
                 patch.object(qualification, "publish", return_value="fixture-commit"), patch.object(qualification, "snapshot"), \
                 patch.object(qualification.round2_data, "prepare_data", return_value=root / "never-read.json"), \
                 patch("benchmarks.token_compare.TokenCounter"), patch.object(qualification.subprocess, "run"), \
                 patch.object(qualification, "execute", side_effect=execute), patch.object(qualification, "assess_phase", side_effect=assess), \
                 patch.object(qualification, "verify_export"), patch.object(qualification, "sha", return_value="fixture-hash"):
                code = qualification.run(SimpleNamespace())
            cp = json.loads((root / "benchmarks/reports/novelty-cap-123-1-checkpoint.json").read_bytes())
            ledger_saved = list((root / "benchmarks/results/novelty-cap-123-1").glob("*.attempts.jsonl.gz"))
            return code, cp, observed, len(ledger_saved)

    def test_a_loss_finishes_a_then_stops_before_b(self):
        code, cp, observed, ledgers = self.controller_fixture({"A": "rejected"})
        self.assertEqual(code, 2)
        self.assertEqual(cp["status"], "rejected")
        self.assertEqual(cp["phases"]["B"]["status"], "not-run")
        self.assertEqual(len(observed), 5)  # export plus all four A workers
        self.assertTrue(all(phase == "A" for phase, _ in observed))
        self.assertEqual(ledgers, 5)

    def test_only_qualified_a_allows_b(self):
        code, cp, observed, ledgers = self.controller_fixture({"A": "qualified", "B": "qualified"})
        self.assertEqual(code, 0)
        self.assertEqual(cp["status"], "qualified-regression-only-awaiting-separate-decision")
        self.assertEqual(len(observed), 9)
        self.assertEqual(ledgers, 9)

    def test_killed_worker_preserves_ledger_without_claiming_completion(self):
        code, cp, observed, ledgers = self.controller_fixture({}, fail_worker="current-default")
        self.assertEqual(code, 2)
        self.assertEqual(cp["status"], "failed-incomplete")
        self.assertEqual(cp["workers"]["A-current-default"]["status"], "interrupted")
        self.assertIn("ledger_output", cp["workers"]["A-current-default"])
        self.assertEqual(cp["workers"]["A-current-default"]["outputs"], {})
        self.assertEqual(cp["phases"]["B"]["status"], "not-run")
        self.assertEqual(ledgers, 2)

    def test_worker_b_rejects_a_mislabeled_checkpoint_before_reading_data(self):
        plan = json.loads(qualification.PLAN.read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); private = root / ".artifacts/novelty-cap/123-1"
            result = root / "benchmarks/results/novelty-cap-123-1"; result.mkdir(parents=True)
            (result / "A-gate.json").write_text(json.dumps({"status": "rejected"}))
            cp = {"run_id": "123-1", "host": {"id":"123-1"}, "source_commit":"fixture-head", "plan_sha256":"fixture-hash",
                  "binding_sha256":"fixture-hash", "workers":{"B-current-default":{"status":"running"}},
                  "phases":{"A":{"status":"qualified","gate_sha256":"fixture-hash"},"B":{"status":"running"}}}
            checkpoint = root / "benchmarks/reports/novelty-cap-123-1-checkpoint.json"; checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps(cp))
            args = SimpleNamespace(host_id="123-1", phase="B", variant="current-default", output=result / "B-current-default",
                state=private / "states/B-current-default", bundle=private / "bundle.json", source=private / "current/src",
                model_dir=private / "model", data=private / "never-read.json")
            with patch.object(qualification, "ROOT", root), patch.object(qualification, "registered_inputs", return_value=(plan, {}, {}, {}, {})), \
                 patch.object(qualification, "actions_identity", return_value="123-1"), patch.object(qualification, "git", return_value="fixture-head"), \
                 patch.object(qualification, "sha", return_value="fixture-hash"), patch.object(qualification, "assess_phase", return_value={"status":"rejected"}), \
                 patch.object(qualification.round2_data, "load") as load:
                with self.assertRaisesRegex(ValueError, "A gate"):
                    qualification.worker(args)
                load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
