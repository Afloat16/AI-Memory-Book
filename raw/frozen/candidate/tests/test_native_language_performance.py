"""Evaluator contracts and one tiny real MCP protocol smoke, not timings."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import native_language_performance as perf


def plan():
    return {"schema_version": 1, "protocol": perf.PROTOCOL,
            "sources": {"baseline": {"commit": perf.BASELINE, "backend": "python"},
                        "candidate": {"commit": "a" * 40, "backend": "native"}},
            "engine_order": copy.deepcopy(perf.ORDERS), "repetitions_per_worker": 3,
            "cohorts": ["synthetic61"], "configurations": ["native-char2400", "mcp-char2400"],
            "query_seed": 110061, "limit": 5, "excluded_native_response_fields": ["latency_ms"],
            "result_cache": "disabled-native-cleared-before-each-mcp-call"}


def fixture(directory):
    specification = plan()
    identities = [f"q{i}" for i in range(perf.COHORTS["synthetic61"]["queries"])]
    manifests = {"baseline": {"backend": "python", "native_binaries": {}},
                 "candidate": {"backend": "native", "native_binaries": {"src/memory_book/_native.test.so": "f" * 64}}}
    run = {"plan": specification, "schedule": perf.schedule(specification), "sources": manifests,
           "query_ids": {"synthetic61": identities}, "cohorts": {"synthetic61": {"fixture": True}}}
    reports = []
    for item in run["schedule"]:
        backend = manifests[item["label"]]["backend"]
        report = {**item, "status": "completed", "source_unchanged": True, "run_sha256": perf.digest(run),
                  "source_manifest_sha256": perf.digest(manifests[item["label"]]),
                  "backend": {"requested": backend, "actual": backend, "binary_sha256": "f" * 64,
                      "dispatch_probe": {"native_helper_calls": dict.fromkeys(perf.NATIVE_HELPERS, 1 if backend == "native" else 0),
                                         "outputs_sha256": "d" * 64, "instrumentation_restored": True}},
                  "dataset": {"fixture": True}, "archive_before": {"fixture": "same"}, "archive_after": {"fixture": "same"},
                  "ingestion_sha256": "0" * 64, "unchanged_reingestion_sha256": "1" * 64,
                  "configurations": []}
        ledger = perf.Ledger(directory / (item["key"] + ".attempts.jsonl.gz"))
        for index, config_id in enumerate(specification["configurations"]):
            order = perf.query_order(identities, item["round"], index)
            rows = []
            for attempt in order:
                row = {**attempt, "category": "fixture", "wall_ms": 1.0, "calling_process_cpu_ms": 0.5,
                       "payload_sha256": "2" * 64, "native_payload_sha256": "3" * 64,
                       "context_sha256": "4" * 64, "envelope_sha256": None if index == 0 else "5" * 64,
                       "context_chars": 12, "context_tokens": None, "result_count": 1,
                       "invariants": {key: 0 for key in perf.INVARIANT_KEYS}}
                rows.append(row)
                ledger.event("started", config_id, row["query_id"], row["repetition"])
                ledger.event("finished", config_id, row["query_id"], row["repetition"], row)
            report["configurations"].append({"id": config_id, **perf.CONFIGS[config_id], "rows": rows,
                "query_order_sha256": perf.digest(order), "latency": perf.summary([1.0] * len(rows)),
                "resources": {"tool_schema_sha256": "a" * 64, "instructions_sha256": "b" * 64}})
        ledger.close()
        report["ledger_sha256"] = perf.sha((directory / (item["key"] + ".attempts.jsonl.gz")).read_bytes())
        reports.append(report)
    return run, reports


class PlanAndSourceTests(unittest.TestCase):
    def test_plan_rejects_changed_exclusions_order_and_repetitions(self):
        self.assertEqual(perf.validate_plan(plan()), plan())
        for key, value in (("repetitions_per_worker", 1), ("excluded_native_response_fields", ["latency_ms", "source_refs"]),
                           ("engine_order", [["baseline", "candidate"]] * 4), ("configurations", ["native-char2400"])):
            changed = plan()
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                perf.validate_plan(changed)

    def test_three_passes_have_unique_attempts_and_balanced_schedule(self):
        order = perf.query_order(["a", "b", "c"], 0, 0)
        self.assertEqual(len(order), 9)
        self.assertEqual(len({(row["repetition"], row["query_id"]) for row in order}), 9)
        self.assertEqual(order, perf.query_order(["a", "b", "c"], 0, 0))
        counts = {name: 0 for name in ("baseline", "candidate")}
        for item in perf.schedule(plan()):
            counts[item["label"]] += 1
        self.assertEqual(counts, {"baseline": 4, "candidate": 4})

    def test_imported_native_module_with_guard_fallback_is_rejected(self):
        native = SimpleNamespace(**{name: (lambda *args: None) for name in perf.NATIVE_HELPERS})
        text = SimpleNamespace(_NATIVE=native, terms=lambda *args, **kwargs: [],
                               _fold_excerpt_source=lambda *args: ("", []), _evidence_units=lambda *args: [])
        with self.assertRaisesRegex(ValueError, "all five native helpers"):
            perf.dispatch_probe(text, native)
        self.assertIs(text._NATIVE, native)

    def test_c_source_build_configuration_and_binary_are_bound(self):
        blobs = {"src/memory_book/__init__.py": b"# package\n",
                 "src/memory_book/_native.c": b"/* native source */\n", "setup.py": b"# build flags\n"}
        def fake_git(*args):
            if args[0] == "ls-tree":
                return ("\n".join(blobs) + "\n").encode()
            return blobs[args[1].split(":", 1)[1]]
        with tempfile.TemporaryDirectory() as temporary, patch.object(perf, "git", fake_git):
            root = Path(temporary)
            for name, raw in blobs.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            binary = root / "src/memory_book/_native.test.so"
            binary.write_bytes(b"binary fixture")
            source = root / "src"
            manifest = perf.source_manifest(source, {"commit": "a" * 40, "backend": "native"})
            self.assertEqual(manifest["source_files"]["src/memory_book/_native.c"], perf.sha(blobs["src/memory_book/_native.c"]))
            self.assertEqual(manifest["native_binaries"]["src/memory_book/_native.test.so"], perf.sha(b"binary fixture"))
            perf.verify_source(source, manifest)
            binary.write_bytes(b"another binary")
            with self.assertRaisesRegex(ValueError, "binary changed"):
                perf.verify_source(source, manifest)
            binary.write_bytes(b"binary fixture")
            (root / "src/memory_book/_native.c").write_bytes(b"different source")
            with self.assertRaisesRegex(ValueError, "differs from source commit"):
                perf.source_manifest(source, {"commit": "a" * 40, "backend": "native"})


class EvidenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.bound_run, cls.reports = fixture(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_evidence_passes_and_recomputes_counts(self):
        for report in self.reports:
            perf.verify_worker(report, self.bound_run, self.directory)
        result = perf.comparisons(self.reports, self.bound_run)
        self.assertTrue(result["complete_output_and_archive_equivalence"])
        self.assertTrue(all(cell["baseline"]["samples"] == 2016 for cell in result["cells"]))

    def test_missing_duplicate_or_incomplete_attempt_fails(self):
        for mutation in ("missing", "duplicate", "incomplete", "silent_fallback"):
            report = copy.deepcopy(self.reports[0])
            if mutation == "missing":
                report["configurations"][0]["rows"].pop()
            elif mutation == "duplicate":
                report["configurations"][0]["rows"][1] = report["configurations"][0]["rows"][0]
            elif mutation == "silent_fallback":
                report["backend"]["actual"] = "native"
            else:
                report["status"] = "failed"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                perf.verify_worker(report, self.bound_run, self.directory)

    def test_payload_edit_cannot_pass_the_original_attempt_ledger(self):
        report = copy.deepcopy(self.reports[0])
        report["configurations"][0]["rows"][0]["payload_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "attempt ledger differs"):
            perf.verify_worker(report, self.bound_run, self.directory)

    def test_repeated_output_change_and_archive_change_are_visible(self):
        for field in ("payload", "archive"):
            reports = copy.deepcopy(self.reports)
            if field == "payload":
                reports[1]["configurations"][0]["rows"][-1]["native_payload_sha256"] = "8" * 64
            else:
                reports[1]["archive_before"] = {"fixture": "changed"}
            result = perf.comparisons(reports, self.bound_run)
            self.assertFalse(result["complete_output_and_archive_equivalence"])
            self.assertTrue(result["differences"])

    def test_compressed_ledger_hash_is_verified(self):
        report = copy.deepcopy(self.reports[0])
        report["ledger_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "ledger bytes differ"):
            perf.verify_worker(report, self.bound_run, self.directory)

    def test_summary_tamper_is_rejected(self):
        report = copy.deepcopy(self.reports[0])
        report["configurations"][0]["latency"]["p95_ms"] = 0.01
        with self.assertRaisesRegex(ValueError, "summary differs"):
            perf.verify_worker(report, self.bound_run, self.directory)


class ActualProtocolSmoke(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "linux" and importlib.util.find_spec("mcp") is not None,
                         "The real protocol fixture requires Linux and the optional MCP SDK")
    def test_small_fixture_real_sdk_roundtrip_and_source_checks(self):
        code = textwrap.dedent('''
            import asyncio, json, os, pathlib, tempfile
            from types import SimpleNamespace
            from scripts import native_language_performance as perf
            from memory_book import MemoryBook
            from benchmarks.run import original_turn_texts
            # Some managed test sandboxes omit /proc/<pid>/task/<tid>/children.
            # Still exercise the real SDK transport, but explicitly stub only
            # its resource observation in this tiny non-performance fixture.
            # The production controller retains its strict procfs requirement.
            real_procfs = pathlib.Path(f"/proc/self/task/{os.getpid()}/children").exists()
            if not real_procfs:
                perf.server_pid = lambda db: None
                perf.usage = lambda pid: {"available": False, "reason": "protocol fixture: sandbox omits child procfs"}
            class Events:
                def __init__(self): self.rows = []
                def event(self, *values): self.rows.append(values)
            session = {"project": "smoke", "session_id": "fixture", "title": "Timeout policy",
                "created_at": "2025-01-01T00:00:00+00:00", "messages": [
                {"role": "user", "content": "What is the timeout?"},
                {"role": "assistant", "content": "The timeout is 37 seconds and belongs only to this project."}]}
            case = SimpleNamespace(id="protocol-smoke", category="fixture", project="smoke", query="timeout")
            data = SimpleNamespace(sessions=[session], queries=[case])
            with tempfile.TemporaryDirectory() as temporary:
                work = pathlib.Path(temporary)
                db = work / "memory.db"
                with MemoryBook(db, cache_size=0) as book:
                    book.ingest(session)
                    native = book.recall(case.query, project=case.project, budget_chars=2400, use_cache=False)
                    native.pop("latency_ms")
                    assert native["results"]
                    sources = original_turn_texts(data)
                    pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                    errors, _ = perf.validate_response(case, native, perf.CONFIGS["native-char2400"], sources, pages, None)
                    assert not any(errors.values()), errors
                    ledger = Events()
                    rows, resource = asyncio.run(perf.mcp_calls(data, "mcp-char2400",
                        [{"query_id": case.id, "repetition": 0}], db, work, perf.ROOT / "src", "python",
                        sources, pages, None, ledger))
                    assert len(rows) == 1 and len(ledger.rows) == 2
                    assert rows[0]["native_payload_sha256"] == perf.digest(native)
                    assert rows[0]["envelope_sha256"] and not any(rows[0]["invariants"].values())
                    if real_procfs:
                        assert resource["server_after_calls"]["rss_bytes"] > 0
                    else:
                        assert resource["server_after_calls"]["available"] is False
                    assert book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0
                    native["results"][0]["excerpt_spans"][0][1] += 10000
                    errors, _ = perf.validate_response(case, native, perf.CONFIGS["native-char2400"], sources, pages, None)
                    assert errors["page_projection"] > 0
            print("Protocol fixture passed; no performance result published.")
        ''')
        environment = {**os.environ, "PYTHONPATH": str(perf.ROOT / "src"),
                       "MEMORY_BOOK_TEXT_BACKEND": "python", "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-c", code], cwd=perf.ROOT, env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Protocol fixture passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
