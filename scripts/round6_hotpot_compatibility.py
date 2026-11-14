"""Final-source compatibility with all 2304 saved published-v0.3.3 outputs.

This historical hash check does not select new questions, load an embedding
model, run a competitor, or establish a timing/quality improvement. All input
and reference dependencies are preflighted before importing the product.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round6_performance as protocol
from scripts import round4_data as historical
from benchmarks.round2_eval import documents_from
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.semantic_eval import page_projection_errors, source_snapshot
from benchmarks.native_budget_eval import source_errors
from benchmarks.token_compare import TokenCounter, evidence_blocks

NAMESPACE = "round6-hotpot-compatibility"
REFERENCE = "benchmarks/reports/round5-c7-hotpot-regression.json.gz"
REFERENCE_LEDGER = "benchmarks/reports/round5-c7-hotpot-regression.attempts.jsonl.gz"
CONFIGS = [{"budget_chars": 8000, "tokenizer": name, "budget_tokens": cap}
           for name in ("cl100k_base", "o200k_base") for cap in (512, 1024, 2048)]


def required_inputs():
    old_binding = json.loads((ROOT / historical.BINDING).read_bytes())
    names = {historical.BINDING, historical.MANIFEST, REFERENCE, REFERENCE_LEDGER, *old_binding["evaluator_files"],
             historical.PLAN, historical.ADDENDUM, historical.COUNTING_ADDENDUM, historical.HISTORICAL,
             historical.ORIGINAL, historical.PRIOR, historical.PRIOR_ROUND3, historical.MODEL_PLAN}
    commits = {historical.PLAN_COMMIT, historical.ADDENDUM_COMMIT, historical.COUNTING_ADDENDUM_COMMIT,
               historical.BASELINE, old_binding["evaluator_commit"], old_binding["candidate"]["commit"], protocol.BASELINE["commit"], protocol.PLAN_COMMIT}
    return {"paths": sorted(names), "git_commits": sorted(commits),
            "zero_product_calls": True, "models_or_competitor_binaries_required": False}


def verify_reference(old, ledger, data):
    protocol.require(old["status"] == "passed" and old["expected_calls"] == 2304 and len(old["rows"]) == 2304
            and old["candidate"]["runtime_sha256"] == old["runtime_sha256_after"] == protocol.BASELINE["runtime_sha256"],
            "Published compatibility reference is incomplete or belongs to another runtime")
    protocol.require(old["dataset"]["fingerprint"] == data.fingerprint and old["dataset"]["queries"] == len(data.queries) == 256,
                     "Historical dataset identity differs")
    cases = {case.id for case in data.queries}
    expected = Counter(("native", identity, 0, protocol.digest(config)) for config in CONFIGS for identity in cases)
    expected.update(("component", identity, rep, protocol.digest({"budget_chars": 100000})) for rep in range(3) for identity in cases)
    observed = Counter((r["stage"], r["id"], r["repetition"], protocol.digest(r["configuration"])) for r in old["rows"])
    protocol.require(expected == observed and all(row["status"] == "match" and row["actual_payload_sha256"] == row["expected_payload_sha256"] for row in old["rows"]),
                     "Published complete-output matrix differs")
    events = [json.loads(line) for line in ledger.splitlines()]
    protocol.require(protocol.sha(ledger) == old["attempt_ledger_sha256"] and len(events) == 4608, "Published attempt ledger changed")
    for sequence, row in enumerate(old["rows"]):
        start, finish = events[2 * sequence:2 * sequence + 2]
        protocol.require(row["sequence"] == sequence and start["event"] == "started" and finish["event"] == "finished"
            and all(row[k] == v for k, v in start.items() if k != "event")
            and {k: v for k, v in finish.items() if k != "event"} == row, "Published attempt/response mismatch")


def preflight(args):
    inputs = required_inputs()
    missing = [name for name in inputs["paths"] if not (ROOT / name).is_file()]
    protocol.require(not missing, "Missing local dependencies before any product import/call: " + ", ".join(missing))
    for commit in inputs["git_commits"]:
        protocol.require(protocol.git("rev-parse", commit + "^{commit}").decode().strip() == commit, "Missing historical Git provenance")
    binding = protocol.load_binding(args.binding)
    protocol.require(binding["stage"] in ("development-native", "development-mcp"), "Compatibility uses the pre-formal frozen candidate binding")
    source = protocol.source_identity(args.candidate_src)
    protocol.require(source == binding["sources"]["candidate"], "Final candidate source differs from its frozen binding")
    packages = {name: importlib.metadata.version(name) for name in ("tiktoken", "pyarrow")}
    protocol.require(packages == {"tiktoken": "0.12.0", "pyarrow": "26.0.1"}, "Historical package pins differ")
    data = historical.load(args.parquet, ROOT / historical.BINDING)
    references = {}
    for name in (REFERENCE, REFERENCE_LEDGER):
        raw = (ROOT / name).read_bytes()
        protocol.require(raw == protocol.git("show", protocol.BASELINE["commit"] + ":" + name), "Published reference bytes differ")
        references[name] = protocol.sha(raw)
    old = json.loads(gzip.decompress((ROOT / REFERENCE).read_bytes()))
    ledger = gzip.decompress((ROOT / REFERENCE_LEDGER).read_bytes())
    verify_reference(old, ledger, data)
    return binding, source, data, old, {"paths_sha256": {name: protocol.sha((ROOT / name).read_bytes()) for name in inputs["paths"]},
        "references": references, "git_commits": inputs["git_commits"], "packages": packages, "product_calls": 0,
        "parquet_sha256": protocol.sha(args.parquet.read_bytes()), "parquet_bytes": args.parquet.stat().st_size}


def save(path, value):
    protocol.atomic(path, value, compressed=True)


def audit_saved(path):
    value = protocol.read_json(path)
    ledger_path = path.with_suffix("").with_suffix(".attempts.jsonl.gz")
    ledger = gzip.decompress(ledger_path.read_bytes())
    protocol.require(value["status"] == "passed" and value["expected_calls"] == len(value["rows"]) == 2304,
                     "Incomplete final-source compatibility")
    protocol.require(value["runtime_sha256_after"] == value["candidate"]["runtime_sha256"], "Compatibility runtime changed")
    protocol.require(value["archive_before"] == value["archive_after"], "Compatibility source/index/archive changed")
    events = [json.loads(line) for line in ledger.splitlines()]
    protocol.require(len(events) == 4608 and protocol.sha(ledger) == value["attempt_ledger_sha256"], "Compatibility ledger changed")
    for sequence, row in enumerate(value["rows"]):
        start, finish = events[sequence * 2:sequence * 2 + 2]
        protocol.require(row["sequence"] == sequence and row["status"] == "match" and not any(row["invariants"].values())
            and row["actual_payload_sha256"] == row["expected_payload_sha256"] and start["event"] == "started" and finish["event"] == "finished"
            and all(row[k] == v for k, v in start.items() if k != "event")
            and {k: v for k, v in finish.items() if k != "event"} == row, "Compatibility attempt/hash/invariant differs")
    original = json.loads(gzip.decompress(protocol.git("show", protocol.BASELINE["commit"] + ":" + REFERENCE)))
    protocol.require([(r["stage"], r["id"], r["repetition"], r["configuration"], r["expected_payload_sha256"]) for r in value["rows"]]
        == [(r["stage"], r["id"], r["repetition"], r["configuration"], r["actual_payload_sha256"]) for r in original["rows"]], "Reference matrix changed")
    return {"schema_version": 1, "audit": NAMESPACE + "-saved-audit-1", "passed": True, "no_new_measurements": True,
        "calls": 2304, "events": 4608, "report_sha256": protocol.sha(path.read_bytes()), "ledger_sha256": protocol.sha(ledger), "candidate": value["candidate"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binding", "candidate-src", "parquet", "state", "report", "audit", "audit-output"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--list-inputs", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    if args.list_inputs:
        print(json.dumps(required_inputs(), indent=2))
        return 0
    if args.audit:
        result = audit_saved(args.audit)
        if args.audit_output:
            protocol.exclusive(args.audit_output, result)
        print(json.dumps(result))
        return 0
    protocol.require(all((args.binding, args.candidate_src, args.parquet, args.state, args.report)), "Explicit frozen source/binding/data/state/report paths required")
    protocol.require(args.report.name.startswith(NAMESPACE) and args.report.name.endswith(".json.gz")
                     and not args.report.exists() and not args.state.exists(), "Use a fresh round-six attempt namespace")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.state.mkdir(parents=True)
    ledger_path = args.report.with_suffix("").with_suffix(".attempts.jsonl")
    report = {"schema_version": 1, "evaluator": NAMESPACE + "-1", "status": "preflight", "started_at": protocol.now(),
        "expected_calls": 2304, "rows": [], "baseline": protocol.BASELINE, "semantic": False, "coverage": False,
        "use_cache": False, "result_limit": 5, "helper_sha256": protocol.sha(Path(__file__).read_bytes()),
        "boundary": "Historical 256 questions, all 2304 published default payloads; exclude only latency_ms. No new quality or performance claim."}
    save(args.report, report)
    try:
        binding, source, data, old, inputs = preflight(args)
        report.update(candidate=source, preflight=inputs, binding_sha256=protocol.sha(args.binding.read_bytes()),
            dataset={"fingerprint": data.fingerprint, "queries": len(data.queries), "selected_ids_sha256": protocol.digest([case.id for case in data.queries])})
        if args.preflight_only:
            report["status"] = "preflight_completed_zero_calls"
            return 0
        claim_path = ROOT / (".artifacts/round6-hotpot-claims/" + source["runtime_sha256"] + ".json")
        protocol.exclusive(claim_path, {"candidate": source, "report": str(args.report.resolve()), "created_at": protocol.now(), "policy": "One actual compatibility attempt per frozen source; zero-call preflights do not claim."})
        sys.path.insert(0, str(args.candidate_src.resolve()))
        import memory_book
        from memory_book import MemoryBook
        protocol.require(Path(memory_book.__file__).resolve().parent == args.candidate_src.resolve() / "memory_book", "Imported runtime differs")
        report["status"] = "running"
        save(args.report, report)
        cases = {case.id: case for case in data.queries}
        source_turns = original_turn_texts(data)
        counters = {name: TokenCounter(name) for name in ("cl100k_base", "o200k_base")}
        with ledger_path.open("x", encoding="utf-8") as ledger, MemoryBook(args.state / "book.db", max_page_chars=900, cache_size=0) as book:
            for session in data.sessions:
                book.ingest(session)
            def archive():
                return {"source_snapshot_sha256": source_snapshot(book.db), "source_semantics": protocol.source_semantics(book.db),
                    "indexed_content": protocol.indexed_content(book.db), "documents_sha256": protocol.digest(documents_from(book)),
                    "cache_entries": book.stats()["cache_entries"]}
            report["archive_before"] = archive()
            protocol.require(report["archive_before"]["indexed_content"] == old["archive_before"]["indexed_content"]
                and report["archive_before"]["documents_sha256"] == old["archive_before"]["documents_sha256"]
                and report["archive_before"]["cache_entries"] == 0, "Source/index/documents differ from published reference")
            pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
            for sample in old["rows"]:
                case, config = cases[sample["id"]], sample["configuration"]
                row = {"sequence": len(report["rows"]), "stage": sample["stage"], "id": case.id,
                    "repetition": sample["repetition"], "configuration": config, "expected_payload_sha256": sample["actual_payload_sha256"]}
                ledger.write(json.dumps({**row, "event": "started"}, sort_keys=True) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
                try:
                    response = book.recall(case.query, project=case.project, limit=5, use_cache=False, semantic=False, coverage=False, **config)
                    protocol.require("latency_ms" in response, "Response lacks sole excluded latency field")
                    response.pop("latency_ms")
                    try:
                        evidence_blocks(response)
                        reconstruction = False
                    except ValueError:
                        reconstruction = True
                    invariants = {"source_span_errors": source_errors(response, source_turns), "page_projection_errors": page_projection_errors(response, pages),
                        "context_reconstruction_error": reconstruction, "result_limit_error": len(response["results"]) > 5,
                        "cache_error": response.get("cache_hit") is not False or book.stats()["cache_entries"] != 0,
                        "character_budget_error": len(response["context"]) > config["budget_chars"], "token_budget_error": False}
                    if config.get("budget_tokens") is not None:
                        count = counters[config["tokenizer"]].count(response["context"])
                        invariants["token_budget_error"] = count > config["budget_tokens"] or response.get("context_tokens") != count
                    row.update(actual_payload_sha256=protocol.digest(response), invariants=invariants)
                    row["status"] = "match" if row["actual_payload_sha256"] == row["expected_payload_sha256"] and not any(invariants.values()) else "mismatch"
                except Exception as error:
                    row.update(status="error", error_type=type(error).__name__, error=str(error))
                report["rows"].append(row)
                ledger.write(json.dumps({**row, "event": "finished"}, sort_keys=True) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
                if len(report["rows"]) % 256 == 0:
                    save(args.report, report)
                    print(json.dumps({"completed_calls": len(report["rows"]), "statuses": dict(Counter(r["status"] for r in report["rows"]))}), flush=True)
            report["archive_after"] = archive()
            protocol.require(report["archive_after"] == report["archive_before"], "Archive changed during compatibility retrieval")
        report["runtime_sha256_after"] = engine_source_hash(args.candidate_src.resolve() / "memory_book")
        protocol.require(report["runtime_sha256_after"] == source["runtime_sha256"], "Source changed during compatibility check")
        report["status"] = "passed" if len(report["rows"]) == 2304 and all(r["status"] == "match" for r in report["rows"]) else "failed"
    except BaseException as error:
        report.update(status="error", error_type=type(error).__name__, error=str(error))
    finally:
        report["finished_at"] = protocol.now()
        report["counts"] = {stage: dict(Counter(r["status"] for r in report["rows"] if r["stage"] == stage)) for stage in ("native", "component")}
        if ledger_path.exists():
            ledger = ledger_path.read_bytes()
            report["attempt_ledger_sha256"] = protocol.sha(ledger)
            protocol.exclusive_bytes(ledger_path.with_suffix(".jsonl.gz"), gzip.compress(ledger, mtime=0))
        save(args.report, report)
        print(json.dumps({k: report[k] for k in ("status", "counts", "expected_calls")}), flush=True)
    return 0 if report["status"] in ("passed", "preflight_completed_zero_calls") else 1


if __name__ == "__main__":
    raise SystemExit(main())
