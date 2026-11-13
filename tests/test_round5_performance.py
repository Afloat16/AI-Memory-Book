"""Artificial audit/transport failure fixtures; no benchmark or timing run."""
import copy
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts import round5_performance as bench


def ledger_bytes(worker):
    events = []
    for cell in worker["configurations"]:
        for row in cell["rows"]:
            seq = len(events) // 2
            events.extend([{"event": "started", "seq": seq, "config": cell["id"],
                            "query_id": row["query_id"], "at": "fixture"},
                           {"event": "finished", "seq": seq, "config": cell["id"], "row": row, "at": "fixture"}])
    return b"".join(bench.raw_json(event) for event in events)


def operations_bytes(worker):
    events = []
    for phase, field in (("fresh", "fresh_ingestion"), ("unchanged", "unchanged_reingestion")):
        events.extend([{"event": "started", "phase": phase, "at": "fixture", "sessions": worker["session_count"]},
                       {"event": "finished", "phase": phase, "at": "fixture", "sessions": worker["session_count"],
                        "wall_ms": worker[field + "_ms"], "results_sha256": worker[field + "_results_sha256"]}])
    return b"".join(bench.raw_json(event) for event in events)


def fixture():
    sources = {label: {"commit": letter * 40, "runtime_sha256": letter * 64, "python_files": 1}
               for label, letter in (("baseline", "a"), ("candidate", "b"))}
    run = {"protocol": bench.VERSION, "binding_sha256": bench.digest("binding"),
           "binding": {"sources": sources, "evaluator_files": {"fixture": bench.digest("script")}},
           "schedule": bench.schedule(), "host": {"boot": "same"},
           "cohorts": {name: {"sha256": bench.digest(name), "queries": len(ids), "sessions": 2,
                               "query_ids_original_order": ids}
                       for name, ids in (("synthetic61", ["b", "a"]), ("public1015", ["c", "z", "x"]))}}
    workers = []
    for item in run["schedule"]:
        cohort = run["cohorts"][item["cohort"]]
        w = {**item, "status": "completed", "error": None, "source": sources[item["label"]],
             "source_after": sources[item["label"]], "evaluator_files_after": run["binding"]["evaluator_files"],
             "host_after": run["host"], "run_identity_sha256": bench.digest(run),
             "dataset_sha256": cohort["sha256"], "session_count": cohort["sessions"],
             "all_replayed_sessions_skipped": True, "native_recall_cache_rows": 0,
             "indexed_content": {"pages": {"rows": 2, "sha256": bench.digest(item["cohort"])}},
             "fresh_ingestion_results_sha256": bench.digest([item["cohort"], "fresh"]),
             "unchanged_reingestion_results_sha256": bench.digest([item["cohort"], "unchanged"]),
             "native_memory_after_ingestion": {"available": True, "rss_bytes": 100, "hwm_bytes": 200},
             "native_memory_after_calls": {"available": True, "rss_bytes": 110, "hwm_bytes": 210},
             "configurations": [], "mcp_sessions": {}}
        w["indexed_content_after_replay"] = copy.deepcopy(w["indexed_content"])
        w["indexed_content_after_calls"] = copy.deepcopy(w["indexed_content"])
        for field in bench.RESOURCE_FIELDS:
            w[field] = 1.0
        w["unchanged_reingestion_ms"] = 0.6 if item["label"] == "candidate" else 1.0
        for name in ("mcp-char4000", "mcp-token1024"):
            w["mcp_sessions"][name] = {"startup_to_initialize_ms": 1.0,
                "tool_schema_sha256": bench.digest("schema"), "instructions_sha256": bench.digest("instructions"),
                "initialization_tokens": {name: {"tool_schema": 10, "instructions": 10} for name in bench.ENCODINGS},
                "memory_after_calls": {"available": True, "rss_bytes": 200, "hwm_bytes": 300}, "storage_live": {"db": 4096}}
        for index, config in enumerate(bench.CONFIGURATIONS):
            rows = []
            mcp = config["surface"] != "native"
            for position, identity in enumerate(bench.query_order(cohort["query_ids_original_order"], item["round"], index)):
                metadata = {"budget_tokens": config["budget_tokens"], "tokenizer": "cl100k_base",
                            "tokenizer_version": "0.12.0", "context_tokens": 10}
                row = {"query_id": identity, "category": "artificial", "wall_ms": (10 + position * .01 + item["round"] * .001)
                       * (.9 if item["label"] == "candidate" else 1),
                       "engine_source_sha256": sources[item["label"]]["runtime_sha256"],
                       "payload_sha256": bench.digest([identity, config["id"]]),
                       "native_payload_sha256": bench.digest([identity, config["id"].replace("mcp-", "native-")]),
                       "context_sha256": bench.digest(identity), "envelope_sha256": bench.digest(["envelope", identity]) if mcp else None,
                       "context_chars": 20, "result_count": 1, "response_utf8_bytes": 30,
                       "envelope_utf8_bytes": 40 if mcp else None, "cache_rows_before": 0, "cache_rows_after": int(mcp),
                       "tokens": {name: {"context": 10, "response_text": 20, "response_envelope_json": 30 if mcp else None}
                                  for name in bench.ENCODINGS},
                       "token_metadata": {"native": metadata, "response": metadata} if config["budget_tokens"] is not None else None,
                       "invariants": {key: False for key in bench.INVARIANTS}}
                rows.append(row)
            w["configurations"].append({**config, "rows": rows,
                                         "latency": bench.latency_summary([r["wall_ms"] for r in rows])})
        w["ledger_sha256"] = bench.sha(ledger_bytes(w))
        w["operations_sha256"] = bench.sha(operations_bytes(w))
        workers.append(w)
    return run, workers


def save_worker(state, run, w):
    directory = state / "workers"
    directory.mkdir(exist_ok=True)
    stem = w["key"]
    item = next(x for x in run["schedule"] if x["key"] == stem)
    bench.exclusive(directory / (stem + ".claimed.json"), bench.claim_value(item, run))
    bench.exclusive(directory / (stem + ".started.json"), {"claim": bench.claim_value(item, run), "at": "fixture", "pid": 1})
    report = bench.write_archive(directory, stem + ".json", bench.raw_json(w))
    ledger = bench.write_archive(directory, stem + ".attempts.jsonl", ledger_bytes(w))
    operations = bench.write_archive(directory, stem + ".operations.jsonl", operations_bytes(w))
    summary = {"key": stem, "status": "completed", "error": None, "calls": sum(len(c["rows"]) for c in w["configurations"]),
               "run_identity_sha256": bench.digest(run), "report_archive": report,
               "ledger_archive": ledger, "operations_archive": operations}
    bench.exclusive(directory / (stem + ".summary.json"), summary)


class Round5PerformanceTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("mcp") and importlib.util.find_spec("tiktoken"),
                         "Optional SDK/reference tokenizer are not installed")
    def test_actual_sdk_artificial_source_and_token_requests_match_native(self):
        # Two artificial requests exercise the exact new worker helper, its
        # normal cache writes and the official SDK. They are not corpus timing.
        import memory_book
        from memory_book import MemoryBook
        source = Path(memory_book.__file__).resolve().parent
        case = SimpleNamespace(id="round5-sdk-fixture", category="fixture", query="violet ledger", project="fixture")
        data = SimpleNamespace(queries=[case], sessions=[{"project": "fixture", "session_id": "one",
            "created_at": "2026-01-01T00:00:00Z", "messages": [
                {"role": "user", "content": "Where is the violet ledger?"},
                {"role": "assistant", "content": "The violet ledger is on shelf nine. Keep its original sources."}]}])
        counters = {name: bench.TokenCounter(name) for name in bench.ENCODINGS}
        with tempfile.TemporaryDirectory() as directory:
            work, db_path = Path(directory), Path(directory) / "fixture.db"
            with MemoryBook(db_path, cache_size=0) as book:
                book.ingest(data.sessions[0])
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                report = {"source": {"runtime_sha256": bench.engine_source_hash(source)}, "mcp_sessions": {}}
                ledger = bench.Ledger(work / "attempts.jsonl")
                try:
                    for config in bench.CONFIGURATIONS[-2:]:
                        options = {"budget_chars": config["budget_chars"], "limit": 5, "use_cache": False}
                        if config["budget_tokens"] is not None:
                            options.update(budget_tokens=config["budget_tokens"], tokenizer="cl100k_base")
                        native = book.recall(case.query, project=case.project, **options)
                        native.pop("latency_ms")
                        rows = asyncio.run(bench.mcp_configuration(data, config, [case.id], db_path, work,
                            source.parent, counters, bench.original_turn_texts(data), pages, report, ledger))
                        self.assertEqual(len(rows), 1)
                        self.assertFalse(any(rows[0]["invariants"].values()), rows[0]["invariants"])
                        self.assertEqual(rows[0]["native_payload_sha256"], bench.digest(native))
                        self.assertEqual(rows[0]["cache_rows_before"], 0)
                        self.assertEqual(rows[0]["cache_rows_after"], 1)
                        self.assertEqual(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 0)
                finally:
                    ledger.close()
            self.assertEqual(len((work / "attempts.jsonl").read_bytes().splitlines()), 4)
            self.assertEqual(set(report["mcp_sessions"]), {"mcp-char4000", "mcp-token1024"})

    def test_schedule_is_full_fixed_abba_matrix(self):
        items = bench.schedule()
        self.assertEqual(len(items), 16)
        self.assertEqual(sum(bench.COHORTS[x["cohort"]]["queries"] * len(bench.CONFIGURATIONS) for x in items), 66248)
        for r, labels in enumerate(bench.ORDERS):
            for cohort in bench.COHORTS:
                self.assertEqual([x["label"] for x in items if x["round"] == r and x["cohort"] == cohort], list(labels))

    def test_complete_artificial_matrix_and_descriptive_target(self):
        run, workers = fixture()
        for w in workers:
            bench.verify_worker(w, run, ledger_bytes(w), operations_bytes(w))
        result = bench.assess(workers, run)
        self.assertEqual(result["status"], "complete-verified")
        self.assertEqual(result["calls"], 280)
        self.assertEqual(len(result["cells"]), 14)
        self.assertEqual(len(result["per_round"]), 56)
        self.assertEqual(result["unchanged_import_20pct_target_by_cohort"], {"synthetic61": True, "public1015": True})
        self.assertNotIn("accepted", result)

    def test_missing_duplicate_reordered_query_and_false_latency_fail(self):
        run, workers = fixture()
        for mode in ("missing", "duplicate", "order", "latency", "nan"):
            w = copy.deepcopy(workers[0])
            cell = w["configurations"][0]
            if mode == "missing":
                cell["rows"].pop()
            elif mode == "duplicate":
                cell["rows"][1] = copy.deepcopy(cell["rows"][0])
            elif mode == "order":
                cell["rows"].reverse()
            elif mode == "latency":
                cell["latency"]["p95_ms"] += 1
            else:
                cell["rows"][0]["wall_ms"] = float("nan")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                bench.verify_worker(w, run, ledger_bytes(workers[0]), operations_bytes(workers[0]))

    def test_bad_source_scope_budget_cache_metadata_and_hash_fail(self):
        run, workers = fixture()
        mutations = [lambda w: w.update(source_after={}),
                     lambda w: w["configurations"][0]["rows"][0]["invariants"].update(source_span_errors=1),
                     lambda w: w["configurations"][0]["rows"][0]["invariants"].update(source_scope_errors=1),
                     lambda w: w["configurations"][0]["rows"][0].update(cache_rows_before=1),
                     lambda w: w["configurations"][0]["rows"][0].update(context_chars=4001),
                     lambda w: w["configurations"][2]["rows"][0]["tokens"]["cl100k_base"].update(context=513),
                     lambda w: w["configurations"][0]["rows"][0].update(native_payload_sha256="missing")]
        for mutation in mutations:
            w = copy.deepcopy(workers[0])
            mutation(w)
            with self.assertRaises(ValueError):
                bench.verify_worker(w, run, ledger_bytes(workers[0]), operations_bytes(workers[0]))

    def test_incomplete_or_modified_attempt_ledger_fails(self):
        run, workers = fixture()
        w = workers[0]
        raw = ledger_bytes(w)
        variants = [b"\n".join(raw.splitlines()[:-1]) + b"\n", raw + raw.splitlines()[0] + b"\n",
                    raw.replace(b'"seq":0', b'"seq":900', 1)]
        for changed in variants:
            modified = copy.deepcopy(w)
            modified["ledger_sha256"] = bench.sha(changed)
            with self.assertRaises(ValueError):
                bench.verify_worker(modified, run, changed, operations_bytes(w))

    def test_ingestion_duration_hash_denominator_and_event_tampering_fail(self):
        run, workers = fixture()
        w = workers[0]
        for mode in ("duration", "hash", "denominator", "event", "missing"):
            events = [json.loads(line) for line in operations_bytes(w).splitlines()]
            if mode == "duration":
                events[3]["wall_ms"] = .001
            elif mode == "hash":
                events[1]["results_sha256"] = "0" * 64
            elif mode == "denominator":
                events[1]["sessions"] -= 1
            elif mode == "event":
                events[2]["event"] = "finished"
            else:
                events.pop()
            raw = b"".join(bench.raw_json(event) for event in events)
            changed = copy.deepcopy(w)
            changed["operations_sha256"] = bench.sha(raw)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                bench.verify_worker(changed, run, ledger_bytes(w), raw)

    def test_exact_native_and_mcp_payload_and_schema_mismatch_fail(self):
        run, workers = fixture()
        changed = copy.deepcopy(workers)
        changed[1]["configurations"][0]["rows"][0]["payload_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "non-timing output"):
            bench.assess(changed, run)
        changed = copy.deepcopy(workers)
        changed[1]["mcp_sessions"]["mcp-char4000"]["tool_schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "schema"):
            bench.assess(changed, run)

    def test_unknown_memory_is_explicit_and_false_available_is_rejected(self):
        run, workers = fixture()
        w = workers[0]
        w["mcp_sessions"]["mcp-char4000"]["memory_after_calls"] = {
            "available": False, "reason": "procfs unavailable", "rss_bytes": None, "hwm_bytes": None}
        bench.verify_worker(w, run, ledger_bytes(w), operations_bytes(w))
        result = bench.assess(workers, run)
        self.assertFalse(result["resource_evidence_complete"])
        self.assertEqual(len(result["missing_memory_samples"]), 1)
        w["mcp_sessions"]["mcp-char4000"]["memory_after_calls"]["available"] = True
        with self.assertRaisesRegex(ValueError, "byte counts"):
            bench.verify_worker(w, run, ledger_bytes(w), operations_bytes(w))

    def test_transport_chunks_reassemble_and_reject_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bench, "CHUNK_CHARS", 64):
            raw = os.urandom(1000)
            manifest = bench.write_archive(directory, "fixture.json", raw)
            self.assertGreater(len(manifest["parts"]), 1)
            self.assertEqual(bench.read_archive(directory, manifest), raw)
            part = Path(directory) / manifest["parts"][0]["path"]
            part.write_bytes(part.read_bytes().replace(b"A", b"B", 1) + b" ")
            with self.assertRaises(ValueError):
                bench.read_archive(directory, manifest)
            with self.assertRaises(FileExistsError):
                bench.write_archive(directory, "fixture.json", raw)

    def test_completed_prefix_loads_archives_but_started_suffix_blocks_replay(self):
        run, workers = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            save_worker(state, run, workers[0])
            self.assertEqual(len(bench.completed_prefix(state, run)), 1)
            second = run["schedule"][1]
            bench.exclusive(state / "workers" / (second["key"] + ".claimed.json"), bench.claim_value(second, run))
            self.assertEqual(len(bench.completed_prefix(state, run)), 1)
            bench.exclusive(state / "workers" / (second["key"] + ".started.json"), {"claim": bench.claim_value(second, run)})
            with self.assertRaisesRegex(ValueError, "never remeasure"):
                bench.completed_prefix(state, run)

    def test_missing_operation_archive_fails_offline_load(self):
        run, workers = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            save_worker(state, run, workers[0])
            summary = json.loads((state / "workers" / (workers[0]["key"] + ".summary.json")).read_bytes())
            (state / "workers" / summary["operations_archive"]["parts"][0]["path"]).unlink()
            with self.assertRaises(FileNotFoundError):
                bench.load_worker(state, run["schedule"][0], run)

    def test_second_execution_registration_for_same_binding_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding_file, data_file = root / "binding.json", root / "data.json"
            binding_file.write_bytes(b"binding")
            data_file.write_bytes(b"artificial")
            binding = {"locomo_path": str(data_file), "locomo_sha256": bench.sha(data_file.read_bytes()),
                       "cohorts": {name: {"query_ids_original_order": [name]} for name in bench.COHORTS}}
            with patch.object(bench, "ROOT", root), patch.object(bench, "load_binding", return_value=binding), \
                    patch.object(bench, "host_identity", return_value={"boot": "fixture"}), \
                    patch.object(bench, "dataset", side_effect=lambda name, _: SimpleNamespace(queries=[SimpleNamespace(id=name)])):
                bench.init(SimpleNamespace(binding=binding_file, state_dir=root / "first"))
                with self.assertRaises(FileExistsError):
                    bench.init(SimpleNamespace(binding=binding_file, state_dir=root / "second"))
            self.assertFalse((root / "second").exists())

    def test_publication_requires_canonical_claim_and_actual_commit_bytes(self):
        run, _ = fixture()
        item = run["schedule"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "reports"
            (state / "workers").mkdir(parents=True)
            run["registration_path"] = "registration.json"
            run["state_path"] = "reports"
            (state / "run.json").write_bytes(bench.raw_json(run))
            (root / "registration.json").write_bytes(bench.raw_json(bench.registration_value(run)))
            path = state / "workers" / (item["key"] + ".claimed.json")
            path.write_bytes(bench.raw_json(bench.claim_value(item, run)))
            commit = "c" * 40

            def committed(*args):
                if args == ("rev-parse", "HEAD"):
                    return commit.encode() + b"\n"
                return (root / args[1].split(":", 1)[1]).read_bytes()

            with patch.object(bench, "ROOT", root), patch.object(bench, "git", side_effect=committed):
                result = bench.verify_publication(state, run, [], item, commit, path.relative_to(root).as_posix())
                self.assertEqual(len(result["verified_committed_files"]), 3)
                with self.assertRaises(ValueError):
                    bench.verify_publication(state, run, [], item, commit, "wrong.json")
            with patch.object(bench, "ROOT", root), patch.object(bench, "git", side_effect=lambda *a: commit.encode() if a[0] == "rev-parse" else b"different"):
                with self.assertRaisesRegex(ValueError, "not exactly committed"):
                    bench.verify_publication(state, run, [], item, commit, path.relative_to(root).as_posix())

    def test_offline_source_identity_uses_git_not_original_snapshot(self):
        commit, content = "d" * 40, b"value = 1\n"
        blob = __import__("hashlib").sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        def saved_git(*args):
            if args[0] == "ls-tree":
                return f"100644 blob {blob}\tsrc/memory_book/__init__.py\0".encode()
            self.assertEqual(args, ("show", commit + ":src/memory_book/__init__.py"))
            return content
        with patch.object(bench, "git", side_effect=saved_git):
            value = bench.committed_source_identity(commit)
        self.assertEqual(value["runtime_sha256"], bench.sha(b"__init__.py\0" + content + b"\0"))
        self.assertEqual(value["python_files"], 1)

    def test_partial_audit_has_no_complete_target_and_full_audit_refuses(self):
        run, workers = fixture()
        result = bench.assess(workers[:2], run, partial=True)
        self.assertEqual(result["status"], "verified-prefix")
        self.assertEqual(result["unchanged_import_20pct_target_by_cohort"], {})
        with self.assertRaisesRegex(ValueError, "every registered worker"):
            bench.assess(workers[:2], run)


if __name__ == "__main__":
    unittest.main()
