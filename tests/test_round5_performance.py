"""Artificial failure fixtures only; no benchmark input or retrieval is loaded."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from scripts import round5_performance as bench


def ledger_bytes(worker):
    events = []
    for config in worker["configurations"]:
        for row in config["rows"]:
            seq = len(events) // 2
            events.extend([{"event": "started", "seq": seq, "config": config["id"],
                            "query_id": row["query_id"], "at": "fixture"},
                           {"event": "finished", "seq": seq, "config": config["id"],
                            "row": row, "at": "fixture"}])
    return b"".join(bench.json_bytes(event) for event in events)


def fixture(factor=.85):
    plan = json.loads(bench.PLAN.read_bytes())
    formal = plan["candidate"]["formal"]
    formal["calls"] = 5 * 7 * 2 * 4
    sources = {"baseline": {"commit": bench.BASELINE, "runtime_sha256": bench.BASELINE_HASH},
               "candidate": {"commit": "a" * 40, "runtime_sha256": bench.digest("candidate")}}
    run = {"binding": {"sources": sources, "plan_commit": bench.PLAN_COMMIT,
                      "addendum_commit": bench.ADDENDUM_COMMIT, "addendum_sha256": bench.ADDENDUM_SHA256,
                      "canonical_addendum_commit": bench.CANONICAL_ADDENDUM_COMMIT,
                      "canonical_addendum_sha256": bench.CANONICAL_ADDENDUM_SHA256,
                      "derived_addendum_commit": bench.DERIVED_ADDENDUM_COMMIT,
                      "derived_addendum_sha256": bench.DERIVED_ADDENDUM_SHA256},
        "evaluator_files": {"fixture": "hash"},
        "host": {"boot": "same-boot"}, "schedule": bench.schedule(plan),
        "cohorts": {name: {"queries": len(ids), "sha256": bench.digest(name),
                           "query_ids": sorted(ids), "query_ids_original_order": ids}
                    for name, ids in (("synthetic61", ["b", "a"]), ("public1015", ["z", "y", "x"]))}}
    report = {"plan": plan, "plan_commit": bench.PLAN_COMMIT,
              "addendum_commit": bench.ADDENDUM_COMMIT, "addendum_sha256": bench.ADDENDUM_SHA256, "run": run,
              "canonical_addendum_commit": bench.CANONICAL_ADDENDUM_COMMIT,
              "canonical_addendum_sha256": bench.CANONICAL_ADDENDUM_SHA256,
              "derived_addendum_commit": bench.DERIVED_ADDENDUM_COMMIT,
              "derived_addendum_sha256": bench.DERIVED_ADDENDUM_SHA256,
              "workers": [], "evaluator_unchanged": True, "error": None}
    for item in run["schedule"]:
        worker = {**item, "status": "completed", "error": None,
            "run_identity_sha256": bench.digest(run), "source": sources[item["label"]],
            "source_after": sources[item["label"]], "dataset_sha256": run["cohorts"][item["cohort"]]["sha256"],
            "runtime_import_ms": 1, "native_open_ms": 1, "fresh_ingestion_ms": 1,
            "unchanged_reingestion_ms": 1, "mcp_startup_to_initialize_ms": 1,
            "native_memory_after_ingestion": {"rss_bytes": 1000, "hwm_bytes": 1200},
            "native_memory_after_calls": {"rss_bytes": 1100, "hwm_bytes": 1300},
            "mcp_server_memory_after_calls": {"available": True, "rss_bytes": 2000, "hwm_bytes": 2200},
            "all_replayed_sessions_skipped": True, "native_recall_cache_rows": 0,
            "indexed_content": {"pages": "unchanged"}, "indexed_content_after_calls": {"pages": "unchanged"},
            "fresh_ingestion_results_sha256": bench.digest("ingest"),
            "unchanged_reingestion_results_sha256": bench.digest("replay"),
            "mcp_tool_schema_sha256": bench.digest("schema"), "mcp_instructions_sha256": bench.digest("instructions"),
            "mcp_initialization_tokens": {name: {"tool_schema": 20, "instructions": 10} for name in bench.ENCODINGS},
            "storage_after_mcp_live": {"logical_database_bytes": 4096}, "configurations": []}
        worker["mcp_sessions"] = {"mcp-char4000": {key: worker[key] for key in bench.MCP_SESSION_FIELDS}}
        worker["mcp_sessions"]["mcp-token1024"] = copy.deepcopy(worker["mcp_sessions"]["mcp-char4000"])
        for index, config in enumerate(formal["configs"]):
            rows = []
            mcp = config["surface"] == "official-sdk-mcp-stdio"
            ids = bench.query_order(run["cohorts"][item["cohort"]]["query_ids_original_order"], item["round"], index)
            for position, identity in enumerate(ids):
                elapsed = (10 + item["round"] * .01 + position * .001) * (factor if item["label"] == "candidate" else 1)
                row = {"query_id": identity, "category": "fixture", "wall_ms": elapsed,
                    "engine_source_sha256": sources[item["label"]]["runtime_sha256"],
                    "payload_sha256": bench.digest([identity, config["id"]]),
                    "native_payload_sha256": bench.digest([identity, config["id"].replace("mcp-", "native-") if mcp else config["id"]]),
                    "context_sha256": bench.digest(identity), "envelope_sha256": bench.digest(identity) if mcp else None,
                    "response_utf8_bytes": 50, "envelope_utf8_bytes": 70 if mcp else None,
                    "context_chars": 10, "result_count": 1, "cache_rows_before": 0, "cache_rows_after": 1 if mcp else 0,
                    "tokens": {name: {"context": 10, "response_text": 20,
                                      "response_envelope_json": 30 if mcp else None} for name in bench.ENCODINGS},
                    "token_metadata": {surface: {"budget_tokens": config["budget_tokens"],
                        "tokenizer": "cl100k_base", "tokenizer_version": "0.12.0", "context_tokens": 10}
                        for surface in ("native", "response")} if config["budget_tokens"] is not None else None,
                    "invariants": {name: 0 for name in bench.INVARIANTS}}
                rows.append(row)
            worker["configurations"].append({**config, "rows": rows,
                "latency": bench.latency_summary([r["wall_ms"] for r in rows])})
        worker["ledger_sha256"] = bench.sha(ledger_bytes(worker))
        report["workers"].append(worker)
    report["validation"] = bench.validation(report)
    return report


def save_worker(state, worker, run):
    prefix = state / "workers" / worker["key"]
    bench.exclusive(Path(str(prefix) + ".started.json"),
                    {"worker": next(w for w in run["schedule"] if w["key"] == worker["key"]),
                     "run_identity_sha256": bench.digest(run)})
    bench.atomic(Path(str(prefix) + ".json.gz"), worker, compressed=True)
    ledger = ledger_bytes(worker)
    Path(str(prefix) + ".attempts.jsonl").write_bytes(ledger)
    Path(str(prefix) + ".attempts.jsonl.gz").write_bytes(gzip.compress(ledger, mtime=0))


class PerformanceGateTests(unittest.TestCase):
    def test_registered_plan_is_fixed_to_original_commit_and_exact_bytes(self):
        raw = bench.PLAN.read_bytes()
        self.assertEqual(bench.PLAN_COMMIT, "7068594181c7e98c576f68a81daf85cd0d06c729")
        registrations = {
            ("show", bench.PLAN_COMMIT + ":benchmarks/experiments/round5-plan.json"): raw,
            ("show", bench.ADDENDUM_COMMIT + ":benchmarks/experiments/round5-materialization-addendum.json"):
                bench.ADDENDUM.read_bytes(),
            ("show", bench.CANONICAL_ADDENDUM_COMMIT + ":benchmarks/experiments/round5-canonical-row-addendum.json"):
                bench.CANONICAL_ADDENDUM.read_bytes(),
            ("show", bench.DERIVED_ADDENDUM_COMMIT + ":benchmarks/experiments/round5-derived-map-addendum.json"):
                bench.DERIVED_ADDENDUM.read_bytes(),
        }
        with patch.object(bench, "git", side_effect=lambda *args: registrations[args]) as git:
            self.assertEqual(bench.load_plan(), json.loads(raw))
            self.assertEqual(git.call_args_list, [call(*args) for args in registrations])
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            altered = Path(directory) / "plan.json"
            altered.write_bytes(raw + b" ")
            with patch.object(bench, "PLAN", altered), patch.object(bench, "git", return_value=raw):
                with self.assertRaisesRegex(ValueError, "registered plan changed"):
                    bench.load_plan()
        with patch.object(bench, "git", return_value=raw + b" "):
            with self.assertRaisesRegex(ValueError, "registered plan changed"):
                bench.load_plan()

    def test_candidate_b_addendum_is_fixed_to_commit_hash_and_exact_bytes(self):
        raw = bench.ADDENDUM.read_bytes()
        self.assertEqual(bench.ADDENDUM_COMMIT, "9042570d8cff01be7c95cd01f8698e166fc7d313")
        self.assertEqual(bench.ADDENDUM_SHA256, "547aa0068fc5fd6a18e448719d855295c3c85ac78faea69867d208c175f77a34")
        self.assertEqual(bench.sha(raw), bench.ADDENDUM_SHA256)
        with patch.object(bench, "git", return_value=raw) as git:
            self.assertEqual(bench.load_addendum(), json.loads(raw))
            git.assert_called_once_with("show", bench.ADDENDUM_COMMIT +
                                        ":benchmarks/experiments/round5-materialization-addendum.json")
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "addendum.json"
            path.write_bytes(raw + b" ")
            with patch.object(bench, "ADDENDUM", path), patch.object(bench, "git", return_value=raw):
                with self.assertRaisesRegex(ValueError, "registered candidate-B addendum changed"):
                    bench.load_addendum()
            # Even a coherent replacement of the local and committed bytes
            # cannot replace the separately pinned original content hash.
            with patch.object(bench, "ADDENDUM", path), patch.object(bench, "git", return_value=raw + b" "):
                with self.assertRaisesRegex(ValueError, "addendum hash differs"):
                    bench.load_addendum()
        with patch.object(bench, "git", return_value=raw + b" "):
            with self.assertRaisesRegex(ValueError, "registered candidate-B addendum changed"):
                bench.load_addendum()

    def test_candidate_b_addendum_preserves_plan_link_and_prior_evidence(self):
        original = json.loads(bench.ADDENDUM.read_bytes())
        mutations = (lambda x: x.update(status="registered-after-measurement"),
                     lambda x: x.update(original_plan_commit="0" * 40),
                     lambda x: x.update(prior_candidate_commit="0" * 40),
                     lambda x: x.update(prior_candidate_runtime_sha256="0" * 64),
                     lambda x: x["evidence"].update(profile_pairs=4731),
                     lambda x: x["evidence"].update(paired_calls=4095),
                     lambda x: x["evidence"].update(paired_payload_pairs=2047))
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "addendum.json"
            for mutate in mutations:
                changed = copy.deepcopy(original)
                mutate(changed)
                raw = bench.json_bytes(changed)
                path.write_bytes(raw)
                with patch.object(bench, "ADDENDUM", path), patch.object(bench, "git", return_value=raw), \
                        patch.object(bench, "ADDENDUM_SHA256", bench.sha(raw)):
                    with self.assertRaisesRegex(ValueError, "addendum registration|retained candidate-A evidence"):
                        bench.load_addendum()

    def test_candidate_c_scope_is_fixed_to_commit_hash_and_exact_bytes(self):
        raw = bench.CANONICAL_ADDENDUM.read_bytes()
        self.assertEqual(bench.CANONICAL_ADDENDUM_COMMIT, "c724452e8f7333af73ed8a0424f572b7d7280a07")
        self.assertEqual(bench.CANONICAL_ADDENDUM_SHA256,
                         "7a5ee634bebfcf9088e9f1401026b4bb3720080c751ce63f95798b87fbdfb28c")
        self.assertEqual(bench.sha(raw), bench.CANONICAL_ADDENDUM_SHA256)
        with patch.object(bench, "git", return_value=raw) as git:
            self.assertEqual(bench.load_canonical_addendum(), json.loads(raw))
            git.assert_called_once_with("show", bench.CANONICAL_ADDENDUM_COMMIT +
                                        ":benchmarks/experiments/round5-canonical-row-addendum.json")
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "canonical.json"
            path.write_bytes(raw + b" ")
            with patch.object(bench, "CANONICAL_ADDENDUM", path), patch.object(bench, "git", return_value=raw):
                with self.assertRaisesRegex(ValueError, "registered candidate-C addendum changed"):
                    bench.load_canonical_addendum()
            with patch.object(bench, "CANONICAL_ADDENDUM", path), patch.object(bench, "git", return_value=raw + b" "):
                with self.assertRaisesRegex(ValueError, "Candidate-C addendum hash differs"):
                    bench.load_canonical_addendum()
        with patch.object(bench, "git", return_value=raw + b" "):
            with self.assertRaisesRegex(ValueError, "registered candidate-C addendum changed"):
                bench.load_canonical_addendum()

    def test_candidate_c_scope_keeps_both_registrations_and_retained_b_evidence(self):
        original = json.loads(bench.CANONICAL_ADDENDUM.read_bytes())
        mutations = (lambda x: x.update(status="registered-after-measurement"),
                     lambda x: x.update(original_plan_commit="0" * 40),
                     lambda x: x.update(materialization_addendum_commit="0" * 40),
                     lambda x: x.update(prior_candidate_commit="0" * 40),
                     lambda x: x.update(prior_candidate_runtime_sha256="0" * 64),
                     lambda x: x["evidence"].update(profile_pairs=4731),
                     lambda x: x["evidence"].update(paired_calls=4095),
                     lambda x: x["evidence"].update(paired_payload_pairs=2047))
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "canonical.json"
            for mutate in mutations:
                changed = copy.deepcopy(original)
                mutate(changed)
                raw = bench.json_bytes(changed)
                path.write_bytes(raw)
                with patch.object(bench, "CANONICAL_ADDENDUM", path), patch.object(bench, "git", return_value=raw), \
                        patch.object(bench, "CANONICAL_ADDENDUM_SHA256", bench.sha(raw)):
                    with self.assertRaisesRegex(ValueError, "addendum registration|retained candidate-B evidence"):
                        bench.load_canonical_addendum()

    def test_candidate_d_scope_is_fixed_to_commit_hash_and_exact_bytes(self):
        raw = bench.DERIVED_ADDENDUM.read_bytes()
        self.assertEqual(bench.DERIVED_ADDENDUM_COMMIT, "0e933580a2a7d28f24b0ac7a8a2f5db4acfb762d")
        self.assertEqual(bench.DERIVED_ADDENDUM_SHA256,
                         "3b065b437405b4a4f19a610dbcd29209513e351da7d7ce98e8b371dbd7dc8329")
        self.assertEqual(bench.sha(raw), bench.DERIVED_ADDENDUM_SHA256)
        with patch.object(bench, "git", return_value=raw) as git:
            self.assertEqual(bench.load_derived_addendum(), json.loads(raw))
            git.assert_called_once_with("show", bench.DERIVED_ADDENDUM_COMMIT +
                                        ":benchmarks/experiments/round5-derived-map-addendum.json")
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "derived.json"
            path.write_bytes(raw + b" ")
            with patch.object(bench, "DERIVED_ADDENDUM", path), patch.object(bench, "git", return_value=raw):
                with self.assertRaisesRegex(ValueError, "registered candidate-D addendum changed"):
                    bench.load_derived_addendum()
            with patch.object(bench, "DERIVED_ADDENDUM", path), patch.object(bench, "git", return_value=raw + b" "):
                with self.assertRaisesRegex(ValueError, "Candidate-D addendum hash differs"):
                    bench.load_derived_addendum()
        with patch.object(bench, "git", return_value=raw + b" "):
            with self.assertRaisesRegex(ValueError, "registered candidate-D addendum changed"):
                bench.load_derived_addendum()

    def test_candidate_d_scope_keeps_three_registrations_and_retained_c_evidence(self):
        original = json.loads(bench.DERIVED_ADDENDUM.read_bytes())
        mutations = (lambda x: x.update(status="registered-after-measurement"),
                     lambda x: x.update(original_plan_commit="0" * 40),
                     lambda x: x.update(materialization_addendum_commit="0" * 40),
                     lambda x: x.update(canonical_addendum_commit="0" * 40),
                     lambda x: x.update(prior_candidate_commit="0" * 40),
                     lambda x: x.update(prior_candidate_runtime_sha256="0" * 64),
                     lambda x: x.update(prior_evidence_commit="0" * 40),
                     lambda x: x["evidence"].update(profile_audit_sha256="0" * 64),
                     lambda x: x["evidence"].update(paired_audit_sha256="0" * 64),
                     lambda x: x["evidence"].update(profile_pairs=4731),
                     lambda x: x["evidence"].update(paired_calls=4095),
                     lambda x: x["evidence"].update(paired_payload_pairs=2047))
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "derived.json"
            for mutate in mutations:
                changed = copy.deepcopy(original)
                mutate(changed)
                raw = bench.json_bytes(changed)
                path.write_bytes(raw)
                with patch.object(bench, "DERIVED_ADDENDUM", path), patch.object(bench, "git", return_value=raw), \
                        patch.object(bench, "DERIVED_ADDENDUM_SHA256", bench.sha(raw)):
                    with self.assertRaisesRegex(ValueError, "addendum registration|retained candidate-C evidence"):
                        bench.load_derived_addendum()

    def test_registered_matrix_and_seed_are_the_new_round_five_axes(self):
        plan = json.loads(bench.PLAN.read_bytes())
        formal = plan["candidate"]["formal"]
        self.assertEqual(formal["configs"], list(bench.CONFIGURATIONS))
        self.assertEqual(formal["calls"], (168 + 1015) * 7 * 2 * 4)
        self.assertEqual(formal["gate"], bench.GATES)
        self.assertEqual(bench.BASELINE, "692fb959ddf8934c5f516ba3d74ceb4385a2fa82")
        self.assertEqual(bench.BASELINE_HASH, "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93")
        self.assertEqual(bench.query_order(list(range(12)), 2, 5), [0, 5, 4, 6, 11, 8, 10, 1, 3, 9, 2, 7])
        self.assertEqual(bench.CONFIGURATIONS[1], {"id": "native-char100000", "surface": "native",
                         "budget_chars": 100000, "budget_tokens": None})

    def test_changed_gate_or_configuration_is_rejected_before_binding(self):
        original = json.loads(bench.PLAN.read_bytes())
        mutations = (lambda p: p["candidate"]["formal"]["gate"].update(minimum_geomean_pooled_p95_improvement_percent=9),
                     lambda p: p["candidate"]["formal"]["configs"].pop(1),
                     lambda p: p["candidate"]["formal"].update(calls=56784),
                     lambda p: p["candidate"]["formal"].update(query_order="unregistered seed"),
                     lambda p: p["baseline"].update(commit="b" * 40))
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "plan.json"
            for mutation in mutations:
                changed = copy.deepcopy(original)
                mutation(changed)
                raw = bench.json_bytes(changed)
                path.write_bytes(raw)
                with patch.object(bench, "PLAN", path), patch.object(bench, "git", return_value=raw):
                    with self.assertRaises(ValueError):
                        bench.load_plan()

    def test_new_and_immutable_runtime_fixtures_are_bound_and_run_in_workflow(self):
        names = (*bench.RUNTIME_FIXTURES, "tests/test_round5_materialization.py", "tests/test_round5_performance.py")
        hashes = bench.file_hashes()
        workflow = (bench.ROOT / ".github/workflows/round5-performance.yml").read_text()
        self.assertEqual(len(bench.EVALUATORS), len(set(bench.EVALUATORS)))
        self.assertIn("benchmarks/experiments/round5-plan.json", bench.EVALUATORS)
        self.assertIn("benchmarks/experiments/round5-materialization-addendum.json", bench.EVALUATORS)
        self.assertEqual(hashes["benchmarks/experiments/round5-materialization-addendum.json"], bench.ADDENDUM_SHA256)
        self.assertIn("benchmarks/experiments/round5-canonical-row-addendum.json", bench.EVALUATORS)
        self.assertEqual(hashes["benchmarks/experiments/round5-canonical-row-addendum.json"],
                         bench.CANONICAL_ADDENDUM_SHA256)
        self.assertIn("benchmarks/experiments/round5-derived-map-addendum.json", bench.EVALUATORS)
        self.assertEqual(hashes["benchmarks/experiments/round5-derived-map-addendum.json"],
                         bench.DERIVED_ADDENDUM_SHA256)
        self.assertNotIn("scripts/round4_performance.py", bench.EVALUATORS)
        for name in names:
            self.assertIn(name, bench.EVALUATORS)
            self.assertEqual(hashes[name], bench.sha((bench.ROOT / name).read_bytes()))
            self.assertIn(name.removesuffix(".py").replace("/", "."), workflow)

    def test_binding_requires_exact_plan_sources_evaluator_and_committed_bytes(self):
        report = fixture()
        documents = {name: (bench.ROOT / name).read_bytes() for name in bench.EVALUATORS}
        hashes = {name: bench.sha(raw) for name, raw in documents.items()}
        value = {"status": "frozen-before-formal-timing", "evaluator": bench.VERSION,
            "plan_commit": bench.PLAN_COMMIT, "plan_sha256": bench.sha(bench.PLAN.read_bytes()),
            "addendum_commit": bench.ADDENDUM_COMMIT, "addendum_sha256": bench.ADDENDUM_SHA256,
            "canonical_addendum_commit": bench.CANONICAL_ADDENDUM_COMMIT,
            "canonical_addendum_sha256": bench.CANONICAL_ADDENDUM_SHA256,
            "derived_addendum_commit": bench.DERIVED_ADDENDUM_COMMIT,
            "derived_addendum_sha256": bench.DERIVED_ADDENDUM_SHA256,
            "evaluator_files": hashes, "packages": bench.PACKAGES,
            "sources": report["run"]["binding"]["sources"], "evaluator_commit": "f" * 40}
        with tempfile.TemporaryDirectory() as directory:
            root, path = Path(directory), Path(directory) / "binding.json"
            raw = bench.json_bytes(value)
            path.write_bytes(raw)
            def git(*args):
                if args == ("show", "HEAD:binding.json"):
                    return raw
                prefix = "f" * 40 + ":"
                if len(args) == 2 and args[0] == "show" and args[1].startswith(prefix):
                    return documents[args[1][len(prefix):]]
                raise AssertionError(args)
            with patch.object(bench, "ROOT", root), patch.object(bench, "file_hashes", return_value=hashes), \
                    patch.object(bench, "git", side_effect=git):
                self.assertEqual(bench.load_binding(path), value)
                mutations = (lambda x: x.update(plan_commit="0" * 40),
                             lambda x: x.update(plan_sha256="0" * 64),
                             lambda x: x.update(addendum_commit="0" * 40),
                             lambda x: x.update(addendum_sha256="0" * 64),
                             lambda x: x.pop("addendum_commit"),
                             lambda x: x.pop("addendum_sha256"),
                             lambda x: x.update(canonical_addendum_commit="0" * 40),
                             lambda x: x.update(canonical_addendum_sha256="0" * 64),
                             lambda x: x.pop("canonical_addendum_commit"),
                             lambda x: x.pop("canonical_addendum_sha256"),
                             lambda x: x.update(derived_addendum_commit="0" * 40),
                             lambda x: x.update(derived_addendum_sha256="0" * 64),
                             lambda x: x.pop("derived_addendum_commit"),
                             lambda x: x.pop("derived_addendum_sha256"),
                             lambda x: x["sources"]["baseline"].update(commit="a" * 40),
                             lambda x: x["packages"].update(tiktoken="other"))
                for mutate in mutations:
                    changed = copy.deepcopy(value)
                    mutate(changed)
                    path.write_bytes(bench.json_bytes(changed))
                    with self.assertRaises(ValueError):
                        bench.load_binding(path)
                for name in bench.EVALUATORS:
                    for missing in (True, False):
                        changed = copy.deepcopy(value)
                        if missing:
                            del changed["evaluator_files"][name]
                        else:
                            changed["evaluator_files"][name] = "0" * 64
                        path.write_bytes(bench.json_bytes(changed))
                        with self.subTest(name=name, missing=missing), self.assertRaisesRegex(ValueError, "Plan/evaluator/packages"):
                            bench.load_binding(path)
                path.write_bytes(raw + b" ")
                with self.assertRaisesRegex(ValueError, "Commit the exact source binding"):
                    bench.load_binding(path)

    def test_new_binding_records_original_plan_and_all_candidate_addenda(self):
        plan = json.loads(bench.PLAN.read_bytes())
        sources = fixture()["run"]["binding"]["sources"]
        documents = {name: (bench.ROOT / name).read_bytes() for name in bench.EVALUATORS}
        hashes = {name: bench.sha(raw) for name, raw in documents.items()}
        tool_commit = "f" * 40
        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return (tool_commit + "\n").encode()
            if len(args) == 2 and args[0] == "show":
                commit, name = args[1].split(":", 1)
                self.assertIn(commit, (tool_commit, bench.BASELINE))
                if commit == bench.BASELINE:
                    self.assertIn(name, (*bench.HELPERS, *bench.RUNTIME_FIXTURES))
                return documents[name]
            raise AssertionError(args)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binding.json"
            args = SimpleNamespace(baseline_src=Path("baseline"), candidate_src=Path("candidate"), bind=path)
            with patch.object(bench, "load_plan", return_value=plan) as registration, \
                    patch.object(bench, "source_identity", side_effect=lambda path: sources[path.name]), \
                    patch.object(bench, "file_hashes", return_value=hashes), \
                    patch.object(bench, "git", side_effect=git), patch("builtins.print"):
                bench.bind(args)
            registration.assert_called_once_with()
            value = json.loads(path.read_bytes())
            self.assertEqual(value["plan_commit"], bench.PLAN_COMMIT)
            self.assertEqual(value["addendum_commit"], bench.ADDENDUM_COMMIT)
            self.assertEqual(value["addendum_sha256"], bench.ADDENDUM_SHA256)
            self.assertEqual(value["canonical_addendum_commit"], bench.CANONICAL_ADDENDUM_COMMIT)
            self.assertEqual(value["canonical_addendum_sha256"], bench.CANONICAL_ADDENDUM_SHA256)
            self.assertEqual(value["derived_addendum_commit"], bench.DERIVED_ADDENDUM_COMMIT)
            self.assertEqual(value["derived_addendum_sha256"], bench.DERIVED_ADDENDUM_SHA256)
            self.assertEqual(value["evaluator_files"], hashes)
            self.assertEqual(value["sources"], sources)

    def test_report_registration_and_audit_reject_coherent_plan_rewrite(self):
        for target in ("report", "binding"):
            report = fixture()
            container = report if target == "report" else report["run"]["binding"]
            container["plan_commit"] = "a" * 40
            self.assertIn("registered_plan_commit_changed", bench.validation(report)["issues"])
        report = fixture()
        original = copy.deepcopy(report["plan"])
        report["plan"]["candidate"]["hypothesis"] = "unregistered replacement"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.json.gz"
            bench.save_report(output, report)
            self.assertTrue(report["validation"]["passed"])
            with patch.object(bench, "load_plan", return_value=original), \
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]), \
                    patch.object(bench, "resume_prefix") as retrieval:
                with self.assertRaisesRegex(ValueError, "original registered plan/evaluator"):
                    bench.audit(output, Path(directory) / "not-created-state")
                retrieval.assert_not_called()

    def test_report_and_saved_audit_reject_coherent_addendum_rewrite(self):
        for target in ("report", "binding"):
            for field, changed in (("addendum_commit", "0" * 40), ("addendum_sha256", "0" * 64)):
                report = fixture()
                container = report if target == "report" else report["run"]["binding"]
                container[field] = changed
                self.assertIn("registered_materialization_addendum_changed", bench.validation(report)["issues"])
        for field, changed in (("addendum_commit", "0" * 40), ("addendum_sha256", "0" * 64)):
            report = fixture()
            report[field] = report["run"]["binding"][field] = changed
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "fixture.json.gz"
                bench.save_report(output, report)
                with patch.object(bench, "load_plan", return_value=report["plan"]), \
                        patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]), \
                        patch.object(bench, "resume_prefix") as retrieval:
                    with self.assertRaisesRegex(ValueError, "Report candidate-B addendum"):
                        bench.audit(output, Path(directory) / "not-created-state")
                    retrieval.assert_not_called()

    def test_report_and_saved_audit_reject_coherent_c_scope_rewrite(self):
        mutations = (("canonical_addendum_commit", "0" * 40), ("canonical_addendum_sha256", "0" * 64))
        for target in ("report", "binding"):
            for field, changed in mutations:
                report = fixture()
                container = report if target == "report" else report["run"]["binding"]
                container[field] = changed
                self.assertIn("registered_canonical_row_addendum_changed", bench.validation(report)["issues"])
        for field, changed in mutations:
            report = fixture()
            report[field] = report["run"]["binding"][field] = changed
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "fixture.json.gz"
                bench.save_report(output, report)
                with patch.object(bench, "load_plan", return_value=report["plan"]), \
                        patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]), \
                        patch.object(bench, "resume_prefix") as retrieval:
                    with self.assertRaisesRegex(ValueError, "Report candidate-C addendum"):
                        bench.audit(output, Path(directory) / "not-created-state")
                    retrieval.assert_not_called()

    def test_report_and_saved_audit_reject_missing_or_coherent_d_scope_rewrite(self):
        mutations = (("derived_addendum_commit", "0" * 40), ("derived_addendum_sha256", "0" * 64),
                     ("derived_addendum_commit", None), ("derived_addendum_sha256", None))
        for target in ("report", "binding"):
            for field, changed in mutations:
                report = fixture()
                container = report if target == "report" else report["run"]["binding"]
                if changed is None:
                    container.pop(field)
                else:
                    container[field] = changed
                self.assertIn("registered_derived_map_addendum_changed", bench.validation(report)["issues"])
        for field, changed in mutations:
            report = fixture()
            for container in (report, report["run"]["binding"]):
                if changed is None:
                    container.pop(field)
                else:
                    container[field] = changed
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "fixture.json.gz"
                bench.save_report(output, report)
                with patch.object(bench, "load_plan", return_value=report["plan"]), \
                        patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]), \
                        patch.object(bench, "resume_prefix") as retrieval:
                    with self.assertRaisesRegex(ValueError, "Report candidate-D addendum"):
                        bench.audit(output, Path(directory) / "not-created-state")
                    retrieval.assert_not_called()

    def test_long_character_cell_is_retained_in_regression_gate(self):
        report = fixture(.8)
        for worker in report["workers"]:
            if worker["label"] == "candidate" and worker["cohort"] == "public1015":
                config = next(c for c in worker["configurations"] if c["id"] == "native-char100000")
                for row in config["rows"]:
                    row["wall_ms"] *= 1.06 / .8
                config["latency"] = bench.latency_summary([row["wall_ms"] for row in config["rows"]])
                worker["ledger_sha256"] = bench.sha(ledger_bytes(worker))
        report["validation"] = bench.validation(report)
        self.assertTrue(report["validation"]["passed"])
        result = bench.acceptance(report, bench.comparisons(report))
        self.assertGreater(result["geometric_mean_p95_improvement_percent"], 10)
        self.assertFalse(result["accepted"])
        self.assertEqual({r["config"] for r in result["regressions_above_five_percent"]}, {"native-char100000"})






    def test_complete_abba_matrix_first_repeat_and_sorted_roundtrip(self):
        report = fixture()
        self.assertTrue(report["validation"]["passed"], report["validation"])
        self.assertEqual(report["validation"]["timed_calls"], 280)
        self.assertEqual(len(report["workers"]), 16)
        self.assertEqual([w["label"] for w in report["run"]["schedule"] if w["cohort"] == "synthetic61"],
                         ["baseline", "candidate", "candidate", "baseline", "candidate", "baseline", "baseline", "candidate"])
        compared = bench.comparisons(report)
        self.assertEqual(len(compared), 14)
        self.assertEqual(compared[0]["baseline"]["first_round_latency"]["samples"], 2)
        self.assertEqual(compared[0]["baseline"]["repeat_rounds_latency"]["samples"], 6)
        self.assertTrue(bench.acceptance(report, compared)["accepted"])
        saved = json.loads(json.dumps(report, sort_keys=True))
        self.assertEqual(compared, bench.comparisons(saved))
        self.assertEqual(report["validation"], bench.validation(saved))

    def test_no_best_round_selection_or_missing_duplicate_worker(self):
        for mutation in (lambda r: r["workers"].pop(),
                         lambda r: r["workers"].append(copy.deepcopy(r["workers"][0])),
                         lambda r: r["workers"].reverse()):
            report = fixture()
            mutation(report)
            self.assertFalse(bench.validation(report)["passed"])

    def test_unchanged_context_cannot_hide_metadata_or_envelope_change(self):
        for field in ("payload_sha256", "native_payload_sha256", "envelope_sha256"):
            report = fixture()
            report["workers"][-1]["configurations"][2]["rows"][0][field] = "0" * 64
            self.assertFalse(bench.validation(report)["passed"], field)

    def test_drop_duplicate_order_cache_scope_budget_source_and_nan_fail(self):
        mutations = [lambda w: w["configurations"][0]["rows"].pop(),
            lambda w: w["configurations"][0]["rows"].reverse(),
            lambda w: w["configurations"][0]["rows"][0].update(cache_rows_before=1),
            lambda w: w["configurations"][0]["rows"][0]["invariants"].update(source_scope_errors=1),
            lambda w: w["configurations"][3]["rows"][0]["tokens"]["cl100k_base"].update(context=513),
            lambda w: w["configurations"][0]["rows"][0].update(engine_source_sha256="changed"),
            lambda w: w["configurations"][0]["rows"][0].update(wall_ms=float("nan")),
            lambda w: w["configurations"][0]["rows"][0].update(wall_ms=0),
            lambda w: w.update(indexed_content_after_calls={"pages": "changed"}),
            lambda w: w["source_after"].update(commit="another"),
            lambda w: w["configurations"][0]["latency"].update(p95_ms=0)]
        for mutation in mutations:
            report = fixture()
            mutation(report["workers"][-1])
            self.assertFalse(bench.validation(report)["passed"])

    def test_valid_performance_loss_is_retained_and_not_accepted(self):
        report = fixture(.98)
        compared = bench.comparisons(report)
        self.assertTrue(report["validation"]["passed"])
        result = bench.acceptance(report, compared)
        self.assertFalse(result["numeric_gate_passed"])
        self.assertAlmostEqual(result["geometric_mean_p95_improvement_percent"], 2)
        compared[0]["candidate_change_percent"]["p95_ms"] = 6
        result = bench.acceptance(fixture(), compared)
        self.assertEqual(len(result["regressions_above_five_percent"]), 1)
        self.assertFalse(result["accepted"])

    def test_resource_increase_requires_review_even_when_latency_passes(self):
        report = fixture()
        for worker in report["workers"]:
            if worker["label"] == "candidate":
                worker["mcp_server_memory_after_calls"]["rss_bytes"] *= 1.2
        result = bench.acceptance(report, bench.comparisons(report))
        self.assertTrue(result["numeric_gate_passed"])
        self.assertFalse(result["accepted"])
        self.assertEqual(len(result["resource_review"]), 2)

    def test_all_three_numeric_gates_are_independently_required(self):
        def result(base_factor, overrides):
            report = fixture(base_factor)
            for worker in report["workers"]:
                if worker["label"] != "candidate":
                    continue
                for config in worker["configurations"]:
                    factor = overrides.get((worker["cohort"], config["id"]), base_factor)
                    for row in config["rows"]:
                        row["wall_ms"] *= factor / base_factor
                    config["latency"] = bench.latency_summary([row["wall_ms"] for row in config["rows"]])
                worker["ledger_sha256"] = bench.sha(ledger_bytes(worker))
            report["validation"] = bench.validation(report)
            self.assertTrue(report["validation"]["passed"], report["validation"])
            return bench.acceptance(report, bench.comparisons(report))

        native_not_fast_enough = result(.8, {("public1015", "native-char4000"): .91})
        self.assertGreater(native_not_fast_enough["geometric_mean_p95_improvement_percent"], 10)
        self.assertGreater(native_not_fast_enough["public_mcp_char4000_p95_improvement_percent"], 5)
        self.assertFalse(native_not_fast_enough["numeric_gate_passed"])
        mcp_not_fast_enough = result(.8, {("public1015", "mcp-char4000"): .96})
        self.assertGreater(mcp_not_fast_enough["geometric_mean_p95_improvement_percent"], 10)
        self.assertGreater(mcp_not_fast_enough["public_native_char4000_p95_improvement_percent"], 10)
        self.assertFalse(mcp_not_fast_enough["numeric_gate_passed"])
        matrix_not_fast_enough = result(.98, {("public1015", "native-char4000"): .85,
                                             ("public1015", "mcp-char4000"): .90})
        self.assertLess(matrix_not_fast_enough["geometric_mean_p95_improvement_percent"], 10)
        self.assertFalse(matrix_not_fast_enough["numeric_gate_passed"])
        self.assertTrue(result(.85, {})["accepted"])
        self.assertTrue(result(.8, {("public1015", "native-char4000"): .9,
                                   ("public1015", "mcp-char4000"): .95})["accepted"])

    def test_token_mcp_session_startup_and_rss_require_separate_resource_review(self):
        for field in ("mcp_startup_to_initialize_ms", "mcp_server_memory_after_calls.rss_bytes"):
            report = fixture()
            for worker in report["workers"]:
                if worker["label"] == "candidate":
                    session = worker["mcp_sessions"]["mcp-token1024"]
                    parent, _, key = field.rpartition(".")
                    target = session[parent] if parent else session
                    target[key] *= 1.2
            self.assertTrue(bench.validation(report)["passed"])
            result = bench.acceptance(report, bench.comparisons(report))
            self.assertTrue(result["numeric_gate_passed"])
            self.assertFalse(result["accepted"])
            self.assertEqual(len(result["resource_review"]), 2)
            self.assertTrue(all("mcp-token1024" in item["metric"] for item in result["resource_review"]))

    def test_both_actual_mcp_token_metadata_surfaces_and_native_pair_are_required(self):
        for surface in ("native", "response"):
            for field in bench.TOKEN_METADATA_FIELDS:
                report = fixture()
                row = report["workers"][0]["configurations"][-1]["rows"][0]
                row["token_metadata"][surface][field] = "wrong"
                self.assertFalse(bench.validation(report)["passed"], (surface, field))
        report = fixture()
        report["workers"][0]["configurations"][-1]["rows"][0]["native_payload_sha256"] = "0" * 64
        self.assertFalse(bench.validation(report)["passed"])
        for mutation in (lambda worker: worker["mcp_sessions"].pop("mcp-token1024"),
                         lambda worker: worker["mcp_sessions"]["mcp-token1024"].update(mcp_tool_schema_sha256="wrong")):
            report = fixture()
            mutation(report["workers"][0])
            self.assertFalse(bench.validation(report)["passed"])

    def test_attempt_ledger_must_match_every_started_and_finished_row(self):
        report = fixture()
        worker = report["workers"][0]
        ledger = ledger_bytes(worker)
        self.assertEqual(bench.verify_worker(worker, report["run"], report["plan"], ledger=ledger), 14)
        for damaged in (ledger.splitlines(keepends=True)[0], ledger + ledger.splitlines(keepends=True)[0]):
            worker["ledger_sha256"] = bench.sha(damaged)
            with self.assertRaisesRegex(ValueError, "attempt ledger"):
                bench.verify_worker(worker, report["run"], report["plan"], ledger=damaged)

    def test_resume_skips_only_original_complete_prefix_and_refuses_interruption(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for worker in report["workers"][:2]:
                save_worker(state, worker, report["run"])
            values = bench.resume_prefix(state, report["run"], report["plan"])
            self.assertEqual([v["key"] for v in values], [w["key"] for w in report["workers"][:2]])
            pending = report["run"]["schedule"][2]
            bench.exclusive(state / "workers" / (pending["key"] + ".started.json"),
                            {"worker": pending, "run_identity_sha256": bench.digest(report["run"])})
            with self.assertRaisesRegex(ValueError, "do not remeasure"):
                bench.resume_prefix(state, report["run"], report["plan"])
            changed = copy.deepcopy(report["run"])
            changed["host"]["boot"] = "different-boot"
            with self.assertRaises(ValueError):
                bench.resume_prefix(state, changed, report["plan"])

    def test_resume_rejects_holes_or_tampered_complete_ledger(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            save_worker(state, report["workers"][1], report["run"])
            with self.assertRaisesRegex(ValueError, "scheduled prefix"):
                bench.resume_prefix(state, report["run"], report["plan"])
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            save_worker(state, report["workers"][0], report["run"])
            path = state / "workers" / (report["workers"][0]["key"] + ".attempts.jsonl")
            path.write_bytes(path.read_bytes() + b"{}\n")
            with self.assertRaisesRegex(ValueError, "do not remeasure"):
                bench.resume_prefix(state, report["run"], report["plan"])

    def test_saved_summary_and_compressed_hash_are_recomputed_without_retrieval(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.json.gz"
            state = Path(directory) / "state"
            bench.exclusive(state / "run.json", report["run"])
            for worker in report["workers"]:
                save_worker(state, worker, report["run"])
            report["worker_artifacts_sha256"] = bench.artifact_hashes(state, report["run"])
            bench.save_report(output, report)
            with patch.object(bench, "load_plan", return_value=report["plan"]), \
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]):
                self.assertEqual(bench.audit(output, state)["retrieval_calls_executed"], 0)
                summary = output.with_name("fixture.summary.json")
                value = json.loads(summary.read_bytes())
                value["full_report_sha256"] = "bad"
                summary.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Summary or raw hashes"):
                    bench.audit(output, state)


    def test_zero_or_partial_workers_preserve_failure_report_and_all_fourteen_cells(self):
        for count in (0, 1, 5):
            report = fixture()
            report["workers"] = report["workers"][:count]
            report["error"] = {"type": "FixtureInterruption", "message": "preserve"}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "partial.json.gz"
                bench.save_report(path, report)
                saved = json.loads(gzip.decompress(path.read_bytes()))
                self.assertFalse(saved["validation"]["passed"])
                self.assertEqual(saved["error"], report["error"])
                self.assertEqual(len(saved["comparisons"]), 14)
                self.assertFalse(saved["acceptance"]["accepted"])
                self.assertTrue(path.with_name("partial.summary.json").is_file())

    def test_public_copy_retains_both_ledgers_and_is_directly_auditable(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state, public = Path(directory) / "state", Path(directory) / "public"
            output = public / "report.json.gz"
            bench.exclusive(state / "run.json", report["run"])
            bench.exclusive(state / "controller-attempts/0001.started.json", {"fixture": "started"})
            for worker in report["workers"]:
                save_worker(state, worker, report["run"])
            report["worker_artifacts_sha256"] = bench.artifact_hashes(state, report["run"])
            bench.save_report(output, report)
            args = SimpleNamespace(state_dir=state, output=output)
            bench.export_checkpoint(args)
            bench.export_checkpoint(args)  # Existing completed copies remain identical.
            self.assertEqual(bench.artifact_hashes(public, report["run"]), report["worker_artifacts_sha256"])
            self.assertEqual(len(list((public / "workers").glob("*.attempts.jsonl"))), 16)
            self.assertEqual(len(list((public / "workers").glob("*.attempts.jsonl.gz"))), 16)
            self.assertTrue((public / "controller-attempts/0001.started.json").is_file())
            with patch.object(bench, "load_plan", return_value=report["plan"]), \
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]):
                self.assertEqual(bench.audit(output, public)["retrieval_calls_executed"], 0)

    def test_public_copy_refuses_overwrite_and_retains_truncated_ledger_bytes(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state, public = Path(directory) / "state", Path(directory) / "public"
            worker = report["workers"][0]
            save_worker(state, worker, report["run"])
            args = SimpleNamespace(state_dir=state, output=public / "report.json.gz")
            bench.export_checkpoint(args)
            destination = public / "workers" / (worker["key"] + ".json.gz")
            destination.write_bytes(b"preserve previously published divergent bytes")
            with self.assertRaisesRegex(ValueError, "Never overwrite"):
                bench.export_checkpoint(args)
            self.assertEqual(destination.read_bytes(), b"preserve previously published divergent bytes")
        with tempfile.TemporaryDirectory() as directory:
            state, public = Path(directory) / "state", Path(directory) / "public"
            path = state / "workers/unfinished.attempts.jsonl"
            raw = b'{"event":"started","seq":0}\n{"event":"fin'
            bench.exclusive_bytes(path, raw)
            bench.export_checkpoint(SimpleNamespace(state_dir=state, output=public / "report.json.gz"))
            self.assertEqual((public / "workers" / path.name).read_bytes(), raw)

    def test_unpublished_formal_controllers_stop_before_loading_or_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "new-parent/state"
            args = SimpleNamespace(publish_branch=None, state_dir=state)
            with patch.object(bench, "load_plan") as plan, \
                    patch.object(bench, "load_binding") as binding, \
                    patch.object(bench, "host_identity") as host, \
                    patch.object(bench, "source_identity") as source, \
                    patch.object(bench, "dataset") as dataset, \
                    patch.object(bench, "claim_execution") as claim:
                for launch in (lambda: bench.main(["--binding", "unused.json"]),
                               lambda: bench.controller(args, {}, {}),
                               lambda: bench.controller_locked(args, {}, {})):
                    with self.assertRaisesRegex(ValueError, "requires --publish-branch"):
                        launch()
                for operation in (plan, binding, host, source, dataset, claim):
                    operation.assert_not_called()
            self.assertFalse(state.parent.exists())

    def test_formal_controller_requires_canonical_state_before_runtime_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication = {"run_id": "123", "run_attempt": "1"}
            args = SimpleNamespace(publish_branch="validation/v033-round5-performance-123-1",
                baseline_src=root / "baseline", candidate_src=root / "candidate",
                locomo_path=root / "fixture", output=root / "public/report.json.gz",
                state_dir=root / "arbitrary-new-state")
            with patch.object(bench, "ROOT", root), \
                    patch.object(bench, "publication_identity", return_value=publication), \
                    patch.object(bench, "host_identity") as host, \
                    patch.object(bench, "source_identity") as source, \
                    patch.object(bench, "dataset") as dataset, \
                    patch.object(bench, "claim_execution") as claim:
                with self.assertRaisesRegex(ValueError, "canonical claimed run directory"):
                    bench.controller_locked(args, {}, {})
                for operation in (host, source, dataset, claim):
                    operation.assert_not_called()
            self.assertFalse(args.state_dir.exists())

    def test_direct_worker_without_claim_stops_before_source_load_or_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            bench.exclusive(state / "run.json", {"publication": None, "execution_claim": None})
            args = SimpleNamespace(state_dir=state, worker="unclaimed-worker")
            with patch.object(bench, "host_identity") as host, \
                    patch.object(bench, "source_identity") as source, \
                    patch.object(bench, "dataset") as dataset, \
                    patch.object(bench.time, "perf_counter_ns") as timer:
                with self.assertRaisesRegex(ValueError, "preserved hosted publication and execution claim"):
                    bench.worker(args, {}, {})
                for operation in (host, source, dataset, timer):
                    operation.assert_not_called()
            self.assertEqual(list(state.iterdir()), [state / "run.json"])

    def test_claimed_worker_requires_exact_published_next_intent_and_no_prior_evidence(self):
        # The valid case only checks receipts. No worker, input loader, runtime,
        # timing or Git write is executed by this artificial fixture.
        cases = {"valid": None, "alternate-state": "canonical claimed run directory",
            "missing-claim-ref": "not preserved remotely", "claim-bytes": "committed original",
            "claim-parent": "directly from the frozen", "remote-head": "exact published result head",
            "published-run": "published controller state", "missing-intent": "published controller start intent",
            "already-complete": "next worker", "failed-checkpoint": "next worker",
            "existing-ledger": "never remeasure", "local-compressed-ledger": "never repeat",
            "publication-failed": "Failed publication"}
        for mutation, error_message in cases.items():
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = json.loads(bench.PLAN.read_bytes())
                binding = {"fixture": "frozen"}
                binding_path = root / "binding.json"
                binding_path.write_bytes(bench.json_bytes(binding))
                fingerprint = bench.sha(binding_path.read_bytes())
                public = "benchmarks/reports/round5-performance-123-1"
                publication = {"branch": "validation/v033-round5-performance-123-1", "directory": public,
                    "workflow_commit": "d" * 40, "run_id": "123", "run_attempt": "1"}
                claim_path = public + "/execution-claim.json"
                claim_raw = bench.json_bytes({"schema_version": 1, "status": "claimed-before-measurement",
                    "workflow_commit": publication["workflow_commit"], "binding_sha256": fingerprint,
                    "run_id": "123", "run_attempt": "1", "claimed_at": "fixture"})
                bench.exclusive_bytes(root / claim_path, claim_raw)
                claim = {"branch": "validation/v033-round5-performance-claim-" + fingerprint,
                    "commit": "c" * 40, "path": claim_path, "sha256": bench.sha(claim_raw)}
                run = {"publication": publication, "execution_claim": claim,
                    "output": str(root / public / "report.json.gz"), "workflow_commit": "d" * 40,
                    "binding": binding, "binding_sha256": fingerprint,
                    "plan_sha256": bench.sha(bench.PLAN.read_bytes()), "evaluator_files": {"fixture": "hash"},
                    "schedule": bench.schedule(plan)}
                state = root / ".artifacts/round5-performance-123-1"
                args = SimpleNamespace(state_dir=state, binding=binding_path, worker=run["schedule"][0]["key"])
                run_raw = bench.json_bytes(run)
                bench.exclusive_bytes(state / "run.json", run_raw)
                intent_path = "workers/" + args.worker + ".started.json"
                intent_raw = bench.json_bytes({"worker": run["schedule"][0], "run_identity_sha256": bench.digest(run)})
                bench.exclusive_bytes(state / intent_path, intent_raw)
                checkpoint = {"run_identity_sha256": bench.digest(run), "status": "running",
                              "error": None, "completed_workers": []}
                head = "e" * 40
                responses = {
                    ("show", claim["commit"] + ":" + claim_path): claim_raw,
                    ("rev-parse", claim["commit"] + "^"): ("d" * 40 + "\n").encode(),
                    ("ls-remote", "--heads", "origin", "refs/heads/" + claim["branch"]):
                        (claim["commit"] + "\trefs/heads/" + claim["branch"] + "\n").encode(),
                    ("rev-parse", "HEAD"): (head + "\n").encode(),
                    ("ls-remote", "--heads", "origin", "refs/heads/" + publication["branch"]):
                        (head + "\trefs/heads/" + publication["branch"] + "\n").encode(),
                    ("show", head + ":" + public + "/run.json"): run_raw,
                    ("show", head + ":" + public + "/" + intent_path): intent_raw,
                }
                if mutation == "alternate-state":
                    args.state_dir = root / "fresh-replay-directory"
                elif mutation == "missing-claim-ref":
                    responses[("ls-remote", "--heads", "origin", "refs/heads/" + claim["branch"])] = b""
                elif mutation == "claim-bytes":
                    (root / claim_path).write_bytes(claim_raw + b" ")
                elif mutation == "claim-parent":
                    responses[("rev-parse", claim["commit"] + "^")] = b"f" * 40 + b"\n"
                elif mutation == "remote-head":
                    responses[("ls-remote", "--heads", "origin", "refs/heads/" + publication["branch"])] = b"moved"
                elif mutation == "published-run":
                    responses[("show", head + ":" + public + "/run.json")] = b"{}\n"
                elif mutation == "missing-intent":
                    responses[("show", head + ":" + public + "/" + intent_path)] = b"{}\n"
                elif mutation == "already-complete":
                    checkpoint["completed_workers"] = [args.worker]
                elif mutation == "failed-checkpoint":
                    checkpoint.update(status="failed_or_interrupted", error={"type": "fixture"})
                elif mutation == "local-compressed-ledger":
                    bench.exclusive_bytes(state / "workers" / (args.worker + ".attempts.jsonl.gz"),
                                          b"preserve an interrupted compressed ledger")
                elif mutation == "publication-failed":
                    bench.exclusive(root / public / "publication-failure.json", {"fixture": "preserved"})
                responses[("show", head + ":" + public + "/checkpoint.json")] = bench.json_bytes(checkpoint)
                def git(*values):
                    if values[0] == "ls-tree":
                        return b"existing.attempts.jsonl\n" if mutation == "existing-ledger" else b""
                    return responses[values]
                with patch.object(bench, "ROOT", root), \
                        patch.object(bench, "publication_identity", return_value=publication), \
                        patch.object(bench, "file_hashes", return_value={"fixture": "hash"}), \
                        patch.object(bench, "git", side_effect=git), \
                        patch.object(bench.subprocess, "run") as command, \
                        patch.object(bench, "dataset") as dataset:
                    if error_message is None:
                        self.assertEqual(bench.verify_worker_claim(args, run, plan, binding), claim)
                    else:
                        with self.assertRaisesRegex(ValueError, error_message):
                            bench.verify_worker_claim(args, run, plan, binding)
                    command.assert_not_called()
                    dataset.assert_not_called()

    def test_binding_claim_refuses_duplicates_and_never_retries_ambiguous_push(self):
        for already_claimed in (True, False):
            with self.subTest(already_claimed=already_claimed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = SimpleNamespace(binding=root / "binding.json", state_dir=root / "state",
                    output=root / "benchmarks/reports/round5-performance-123-1/report.json.gz", resume=False)
                args.binding.write_bytes(b'{"fixture":"frozen"}\n')
                publication = {"workflow_commit": "d" * 40, "run_id": "123", "run_attempt": "1"}
                calls = []
                def git(*values):
                    if values[0] == "ls-remote":
                        return b"already claimed" if already_claimed else b""
                    if values[0] == "rev-parse":
                        committed = any("commit" in argv for argv in calls)
                        return (b"c" if committed else b"d") * 40 + b"\n"
                    return b""
                def command(argv, **kwargs):
                    calls.append(argv)
                    if argv[1] == "push":
                        raise subprocess.CalledProcessError(1, argv)
                with patch.object(bench, "ROOT", root), patch.object(bench, "git", side_effect=git), \
                        patch.object(bench.subprocess, "run", side_effect=command):
                    with self.assertRaises(bench.CheckpointPublicationError):
                        bench.claim_execution(args, publication)
                    self.assertTrue((args.output.parent / "publication-failure.json").is_file())
                    self.assertEqual(sum(argv[1] == "push" for argv in calls), int(not already_claimed))
                    count = len(calls)
                    with self.assertRaisesRegex(ValueError, "no automatic retry"):
                        bench.claim_execution(args, publication)
                    self.assertEqual(len(calls), count)
                self.assertFalse(any("--force" in argv or "--force-with-lease" in argv for argv in calls))

    def test_publication_is_limited_to_original_workflow_and_this_run_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = "benchmarks/reports/round5-performance-123-1"
            args = SimpleNamespace(publish_branch="validation/v033-round5-performance-123-1",
                                   output=root / relative / "report.json.gz")
            environment = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                           "GITHUB_SHA": "d" * 40, "GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book",
                           "GITHUB_EVENT_NAME": "push", "GITHUB_REF": bench.TRIGGER}
            changed = [relative + "/report.json.gz"]
            def git(*values):
                if values[0] == "remote":
                    return b"https://github.com/Afloat16/AI-Memory-Book.git\n"
                if values[0] == "merge-base":
                    return b""
                return ("\n".join(changed) + "\n").encode()
            with patch.object(bench, "ROOT", root), patch.dict(os.environ, environment), \
                    patch.object(bench, "git", side_effect=git):
                identity = bench.publication_identity(args)
                self.assertEqual(identity["workflow_commit"], environment["GITHUB_SHA"])
                args.publish_branch = "main"
                with self.assertRaisesRegex(ValueError, "exact Actions attempt"):
                    bench.publication_identity(args)
                args.publish_branch = identity["branch"]
                changed[:] = ["src/memory_book/store.py"]
                with self.assertRaisesRegex(ValueError, "only this attempt"):
                    bench.publication_identity(args)
                changed[:] = [relative + "/report.json.gz"]
                with patch.dict(os.environ, {"GITHUB_REPOSITORY": "someone/else"}):
                    with self.assertRaisesRegex(ValueError, "authorized repository"):
                        bench.publication_identity(args)

    def test_publication_refuses_unrelated_staging_and_does_not_retry_push(self):
        identity = {"branch": "validation/v033-round5-performance-123-1",
                    "directory": "benchmarks/reports/round5-performance-123-1"}
        args, run = SimpleNamespace(), {"publication": identity}
        with patch.object(bench, "publication_identity", return_value=identity), \
                patch.object(bench, "export_checkpoint"), \
                patch.object(bench, "git", return_value=b"README.md\n"), \
                patch.object(bench.subprocess, "run") as command:
            with self.assertRaisesRegex(bench.CheckpointPublicationError, "Unrelated staged"):
                bench.publish_checkpoint(args, run, "fixture")
            command.assert_not_called()
        calls = []
        def command(argv, **kwargs):
            calls.append(argv)
            if argv[1] == "push":
                raise subprocess.CalledProcessError(1, argv)
        with patch.object(bench, "publication_identity", return_value=identity), \
                patch.object(bench, "export_checkpoint"), \
                patch.object(bench, "git", side_effect=[b"", b"result\n"]), \
                patch.object(bench.subprocess, "run", side_effect=command):
            with self.assertRaisesRegex(bench.CheckpointPublicationError, "publication failed"):
                bench.publish_checkpoint(args, run, "fixture")
        self.assertEqual(sum(argv[1] == "push" for argv in calls), 1)
        self.assertFalse(any("--force" in argv or "--force-with-lease" in argv for argv in calls))

    def test_failed_start_or_complete_checkpoint_stops_before_next_worker(self):
        for fail_phase in ("started", "completed"):
            original = fixture()
            plan, binding = original["plan"], original["run"]["binding"]
            with self.subTest(phase=fail_phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = SimpleNamespace(baseline_src=root / "baseline", candidate_src=root / "candidate",
                    locomo_path=root / "artificial-input", binding=root / "binding.json",
                    output=root / "public/report.json.gz",
                    state_dir=root / ".artifacts/round5-performance-123-1", resume=False,
                    publish_branch="validation/v033-round5-performance-123-1")
                args.locomo_path.write_bytes(b"artificial data; never parsed")
                args.binding.write_bytes(bench.json_bytes(binding))
                publication = {"branch": args.publish_branch, "workflow_commit": "d" * 40,
                               "run_id": "123", "run_attempt": "1"}
                events = []
                def dataset(plan, name, path):
                    spec = original["run"]["cohorts"][name]
                    return SimpleNamespace(fingerprint=spec["sha256"],
                        queries=[SimpleNamespace(id=identity) for identity in spec["query_ids_original_order"]])
                def publish(arguments, run, phase):
                    events.append(phase)
                    key, state = phase.rsplit(" ", 1)
                    prefix = arguments.state_dir / "workers" / key
                    self.assertTrue(Path(str(prefix) + ".started.json").is_file())
                    if state == "completed":
                        self.assertTrue(Path(str(prefix) + ".attempts.jsonl.gz").is_file())
                    if state == fail_phase:
                        raise bench.CheckpointPublicationError("artificial push failure")
                def spawn(command, **kwargs):
                    key = command[command.index("--worker") + 1]
                    events.append(key + " launched")
                    run = json.loads((args.state_dir / "run.json").read_bytes())
                    worker = copy.deepcopy(next(w for w in original["workers"] if w["key"] == key))
                    worker["run_identity_sha256"] = bench.digest(run)
                    prefix = args.state_dir / "workers" / key
                    bench.atomic(Path(str(prefix) + ".json.gz"), worker, compressed=True)
                    ledger = ledger_bytes(worker)
                    Path(str(prefix) + ".attempts.jsonl").write_bytes(ledger)
                    Path(str(prefix) + ".attempts.jsonl.gz").write_bytes(gzip.compress(ledger, mtime=0))
                with patch.object(bench, "ROOT", root), \
                        patch.object(bench, "host_identity", return_value={"packages": bench.PACKAGES, "boot": "fixture"}), \
                        patch.object(bench, "source_identity", side_effect=lambda path: binding["sources"][path.name]), \
                        patch.object(bench, "dataset", side_effect=dataset), \
                        patch.object(bench, "file_hashes", return_value=original["run"]["evaluator_files"]), \
                        patch.object(bench, "publication_identity", return_value=publication), \
                        patch.object(bench, "claim_execution", return_value={"fixture": "claimed"}), \
                        patch.object(bench, "publish_checkpoint", side_effect=publish) as publisher, \
                        patch.object(bench.subprocess, "run", side_effect=spawn) as process, \
                        patch.dict(os.environ, {"GITHUB_SHA": "d" * 40}):
                    self.assertEqual(bench.controller_locked(args, plan, binding), 2)
                completed = int(fail_phase == "completed")
                self.assertEqual(process.call_count, completed)
                self.assertEqual(publisher.call_count, 1 + completed)
                saved = json.loads(gzip.decompress(args.output.read_bytes()))
                self.assertEqual(len(saved["workers"]), completed)
                self.assertEqual(saved["error"]["type"], "CheckpointPublicationError")
                self.assertEqual(saved["run"]["workflow_commit"], "d" * 40)
                self.assertFalse(saved["validation"]["passed"])
                self.assertFalse(saved["acceptance"]["accepted"])
                self.assertEqual(len(list((args.state_dir / "workers").glob("*.started.json"))), 1)
                self.assertTrue((args.output.parent / "controller-attempts/0001.finished.json").is_file())
                key = original["workers"][0]["key"]
                expected = [key + " started"] + ([key + " launched", key + " completed"] if completed else [])
                self.assertEqual(events, expected)

    def test_full_source_projection_rejects_invented_excerpt_and_wrong_scope(self):
        case = SimpleNamespace(id="fixture", category="fixture", query="alpha", project="p")
        text = "USER: alpha"
        native = {"query": "alpha", "context": "[page] p / s\n" + text,
            "context_chars": len("[page] p / s\n" + text), "budget_chars": 4000,
            "cache_hit": False, "results": [{"id": "page", "text": text,
                "breadcrumb": [{"id": "p"}], "excerpt_spans": [[0, len(text)]],
                "source_refs": [{"project": "p", "session_id": "s", "turn_index": 0,
                                 "turn_start": 0, "turn_end": len(text)}]}]}
        counters = {name: SimpleNamespace(count=len) for name in bench.ENCODINGS}
        config = {"surface": "native", "budget_chars": 4000, "budget_tokens": None}
        def measure():
            return bench.make_row(case, native, 1, bench.dump(native), None, native, config,
                counters, {("p", "s", 0): text}, {"page": text}, 0, 0, bench.BASELINE_HASH)
        self.assertFalse(any(measure()["invariants"].values()))
        # Registered synthetic cases also contain unscoped queries. None
        # permits genuine project references without disabling source checks.
        case.project = None
        self.assertFalse(any(measure()["invariants"].values()))
        case.project = "p"
        native["results"][0]["text"] += " invented"
        self.assertTrue(measure()["invariants"]["page_projection_errors"])
        native["results"][0]["source_refs"][0]["project"] = "foreign"
        self.assertTrue(measure()["invariants"]["source_scope_errors"])




if __name__ == "__main__":
    unittest.main()
