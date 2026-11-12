"""Execute the registered native claude-mem supplied-source FTS experiment."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

from benchmarks.component_eval import canonical_json, shared_response
from benchmarks.competitors.claude_mem import ClaudeMemFTS, LOCK_PATH
from benchmarks.public_data import load_locomo
from benchmarks.run import original_turn_texts
from benchmarks.token_compare import (ENCODINGS, TokenCounter, latency_summary,
    pack_whole_blocks, score_row, summarize_rows, validation_status)

HERE = Path(__file__).resolve().parent
PLAN = HERE / "experiments/claude-mem-component-plan.json"
VERSION = "claude-mem-supplied-fts-1.0"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def append(path, value):
    with Path(path).open("ab") as stream:
        stream.write((canonical_json(value) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def verify_bundle(bundle, dataset, plan):
    expected = plan["corpus"]
    documents = bundle["documents"]
    if (len(dataset.queries) != expected["queries"]
            or sum(q.answerable for q in dataset.queries) != expected["answerable_queries"]
            or dataset.fingerprint != expected["dataset_sha256"]
            or bundle["dataset"]["sha256"] != dataset.fingerprint):
        raise ValueError("Registered public cohort/count mismatch")
    if (len(documents) != expected["documents"]
            or len({d["id"] for d in documents}) != len(documents)
            or sha(canonical_json(documents).encode()) != expected["documents_sha256"]
            or bundle["documents_sha256"] != expected["documents_sha256"]):
        raise ValueError("Supplied pages differ from the historical comparison")
    if (bundle["source_sha256_before"] != expected["exporter_source_sha256"]
            or bundle["source_sha256_after"] != expected["exporter_source_sha256"]
            or bundle["source_provenance"]["git_commit"] != expected["exporter_commit"]
            or not bundle["source_unchanged"]):
        raise ValueError("Exporter is not the registered original source")
    return {doc["id"]: doc for doc in documents}


def export_bundle(args):
    bundle = args.state_dir / "supplied-pages.json"
    metadata = args.state_dir / "export-metadata.json"
    database = args.state_dir / "export.db"
    command = [
        sys.executable, "-m", "benchmarks.component_eval",
        "--baseline-src", str(args.exporter_src.resolve()),
        "--baseline-label", "first-round-recall",
        "--candidate-label", "unused-export-only",
        "--cache", str(args.cache.resolve()),
        "--worker", "export", "--engine-src", str(args.exporter_src.resolve()),
        "--bundle", str(bundle), "--database", str(database), "--output", str(metadata),
        "--corpus", "locomo", "--split", "heldout", "--max-queries", "0",
        "--locomo-path", str(args.locomo_path.resolve()), "--seed", "61", "--projects", "8"]
    subprocess.run(command, check=True)
    return json.loads(bundle.read_text()), command


def historical_rows(plan):
    path = Path(plan["corpus"]["historical_report"])
    data = path.read_bytes()
    blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if blob_sha != plan["corpus"]["historical_report_git_blob_sha"]:
        raise ValueError("Historical report bytes differ from the registered Git blob")
    report = json.loads(gzip.decompress(data))
    frozen = report["frozen_corpus"]
    if (frozen["documents_sha256"] != plan["corpus"]["documents_sha256"]
            or frozen["dataset"]["sha256"] != plan["corpus"]["dataset_sha256"]
            or not report["validation"]["passed"]):
        raise ValueError("Historical baseline failed the same-pages guard")
    result = []
    expected_axes = {(n, b) for n in ENCODINGS for b in (512, 1024, 2048)}
    for original in report["engines"]:
        if original["dataset"]["sha256"] != plan["corpus"]["dataset_sha256"]:
            raise ValueError("Historical engine cohort mismatch")
        axes = {(c["tokenizer"], c["budget_tokens"]) for c in original["packed_configurations"]}
        if axes != expected_axes:
            raise ValueError("Historical shared-packing axes mismatch")
        engine = {key: copy.deepcopy(original[key]) for key in (
            "label", "metadata", "kernel_or_native_search_latency", "adapter_roundtrip_latency",
            "native_costs")}
        engine["measurement_status"] = "historical, separate host/process run and boundary"
        engine["packed_configurations"] = [
            {key: copy.deepcopy(c[key]) for key in
             ("tokenizer", "budget_tokens", "metrics", "by_category", "token_budget_violations")}
            for c in original["packed_configurations"]]
        result.append(engine)
    return {"path": str(path), "compressed_sha256": sha(data),
            "created_at_utc": report["created_at_utc"], "runtime": report["runtime"],
            "engines": result}


def markdown(report):
    lines = ["# claude-mem supplied-source SQLite FTS component", "",
        "**Scope:** unchanged native SessionSearch over supplied original source pages. "
        "Observer, Chroma, native worker/MCP and generated answers are not measured.", "",
        "Validation: **" + ("PASS" if report["validation"]["passed"] else "FAIL — diagnostic only") + "**.", "",
        "| Component | Tokenizer | Cap | Evidence recall | Complete evidence | Mean context tokens |",
        "|---|---|---:|---:|---:|---:|"]
    for engine in [report["engine"], *report["historical_comparison"]["engines"]]:
        for c in engine["packed_configurations"]:
            m = c["metrics"]
            lines.append(f"| {engine['label']} | {c['tokenizer']} | {c['budget_tokens']} | "
                f"{m['evidence_recall']:.2%} | {m['complete_evidence_rate']:.2%} | "
                f"{m['mean_context_tokens'][c['tokenizer']]:.1f} |")
    engine = report["engine"]
    lines += ["", "## Observed component costs", "",
        "| Boundary | p50 ms | p95 ms | Mean ms |", "|---|---:|---:|---:|"]
    for key in ("kernel_or_native_search_latency", "adapter_roundtrip_latency",
                "first_pass_roundtrip_latency", "repeat_roundtrip_latency"):
        m = engine[key]
        lines.append(f"| {key} | {m['p50_ms']:.3f} | {m['p95_ms']:.3f} | {m['mean_ms']:.3f} |")
    lines += ["", "Startup, schema creation, supplied-page loading, DB sizes and RSS are recorded "
        "separately in the JSON summary. They are not complete-product ingestion costs.", "",
        "Historical Book/Billion/ai-memory rows reuse the exact matched pages and packing policy; "
        "their transport boundaries and original host remain separately attributed. No full-product "
        "latency ranking or generated-answer conclusion follows from this table.", "",
        "This is previously observed LoCoMo regression data. Quality counts complete original "
        "annotated evidence and source spans, not answer generation. All failed attempts remain in "
        "the ledger and invalidate successful measurement claims.", ""]
    return "\n".join(lines)


def write_report(report, prefix):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    compressed = gzip.compress(raw, mtime=0)
    full = Path(str(prefix) + ".json.gz")
    temp = full.with_suffix(full.suffix + ".tmp")
    temp.write_bytes(compressed)
    os.replace(temp, full)
    summary = copy.deepcopy(report)
    summary["engine"].pop("native_query_costs", None)
    summary["engine"].pop("timing_rows", None)
    for config in summary["engine"]["packed_configurations"]:
        config.pop("query_results", None)
    summary["full_report_sha256"] = sha(raw)
    atomic(Path(str(prefix) + ".summary.json"), summary)
    Path(str(prefix) + ".md").write_text(markdown(report), encoding="utf8")


def smoke(args):
    docs = [
        {"id":"alpha", "project":"A", "title":"Expiry", "text":"Cache expiry is forty-five seconds.",
         "created_at":"2024-01-01T00:00:00+00:00"},
        {"id":"beta", "project":"B", "title":"Expiry", "text":"Cache expiry is seventeen minutes.",
         "created_at":"2024-01-02T00:00:00+00:00"},
        {"id":"cjk", "project":"A", "title":"中文", "text":"苹果在阴凉棚散热两小时。",
         "created_at":"2024-01-03T00:00:00+00:00"}]
    engine = ClaudeMemFTS(docs, args.cache, args.state_dir / "native", offline=args.offline)
    try:
        if engine.search("expiry", "A")["hit_ids"] != ["alpha"]:
            raise AssertionError("native scope/source smoke failed")
        if "cjk" not in engine.search("散热", "A")["hit_ids"]:
            raise AssertionError("native unsegmented-script smoke failed")
        if engine.search("expiry", "absent")["hit_ids"]:
            raise AssertionError("empty project scope leaked")
        engine.search('cache "expiry" OR nope', "A")
    finally:
        engine.close()
    if not engine.metadata["source_unchanged"] or engine.metadata["native_process_exit_code"]:
        raise AssertionError("native integrity/exit smoke failed")
    atomic(args.state_dir / "smoke.json", {"status":"passed", "scope":"three fictional source pages, no benchmark scores",
                                         "metadata":engine.metadata})
    print("Native claude-mem FTS scope/source/CJK smoke passed.")


def run(args):
    plan = json.loads(PLAN.read_bytes())
    dataset = load_locomo(args.locomo_path, split="heldout", max_queries=0)
    bundle, command = export_bundle(args)
    documents = verify_bundle(bundle, dataset, plan)
    historical = historical_rows(plan)
    sources = original_turn_texts(dataset)
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    ledger = args.state_dir / "queries.jsonl"
    files = [Path(__file__), HERE/"competitors/claude_mem.py",
             HERE/"competitors/claude_mem_bridge.ts", LOCK_PATH, PLAN,
             HERE/"component_eval.py", HERE/"token_compare.py", HERE/"run.py",
             HERE/"data.py", HERE/"public_data.py"]
    input_hashes = {str(p.relative_to(HERE.parent)): sha(p.read_bytes()) for p in files}
    atomic(args.state_dir / "registration.json", {
        "version":VERSION, "plan":plan, "file_sha256":input_hashes,
        "export_command":command, "documents_sha256":bundle["documents_sha256"],
        "dataset":dataset.description(), "historical_report_sha256":historical["compressed_sha256"]})
    responses, native, timings, failures = {}, {}, [], []
    engine = ClaudeMemFTS(bundle["documents"], args.cache, args.state_dir/"native", offline=args.offline)
    try:
        for repetition in range(3):
            cases = list(dataset.queries)
            random.Random(61 + 1009 * repetition).shuffle(cases)
            for case in cases:
                append(ledger, {"event":"started", "repetition":repetition, "query_id":case.id})
                try:
                    response = engine.search(case.query, case.project, 5)
                    ids = response["hit_ids"]
                    timing = {key:response[key] for key in (
                        "search_ms","bridge_ms","native_cpu_user_us","native_cpu_system_us")}
                    timing.update(id=case.id, repetition=repetition)
                    timings.append(timing)
                    payload = canonical_json(response["native_payload"])
                    record = {"id":case.id, "hit_ids":ids, "payload_sha256":sha(payload.encode()),
                        "search_payload_bytes":len(payload.encode()),
                        "search_payload_tokens":{n:c.count(payload) for n,c in counters.items()},
                        "read_calls":0, "read_ms":0, "status":"ok"}
                except Exception as error:
                    ids = []
                    record = {"id":case.id, "hit_ids":[], "status":"failed",
                              "error_type":type(error).__name__, "error_sha256":sha(str(error).encode())}
                    append(ledger, {"event":"error_detail", "repetition":repetition,
                                    "query_id":case.id, "error":str(error)})
                    failures.append({"repetition":repetition, **record})
                append(ledger, {"event":"finished", "repetition":repetition, **record})
                if repetition == 0:
                    responses[case.id] = shared_response(ids, documents)
                    native[case.id] = record
    finally:
        engine.close()
    configs = []
    for name, counter in counters.items():
        for budget in (512,1024,2048):
            rows, packing_ms = [], []
            for case in dataset.queries:
                start = time.perf_counter()
                packed = pack_whole_blocks(responses[case.id], budget, counter)
                packing_ms.append((time.perf_counter()-start)*1000)
                row = score_row(case, packed, sources, counters, public=True)
                row["token_budget_violation"] = row["context_tokens"][name] > budget
                rows.append(row)
            groups = defaultdict(list)
            for row in rows:
                groups[row["category"]].append(row)
            configs.append({"tokenizer":name, "budget_tokens":budget, "metrics":summarize_rows(rows),
                "by_category":{key:summarize_rows(v) for key,v in sorted(groups.items())},
                "token_budget_violations":sum(r["token_budget_violation"] for r in rows),
                "packing_latency":latency_summary(packing_ms), "query_results":rows})
    okay = [row for row in native.values() if row["status"] == "ok"]
    measured = {"label":"claude-mem supplied-source native FTS", "metadata":engine.metadata,
        "dataset":dataset.description(), "packed_configurations":configs,
        "kernel_or_native_search_latency":latency_summary([r["search_ms"] for r in timings]),
        "adapter_roundtrip_latency":latency_summary([r["bridge_ms"] for r in timings]),
        "first_pass_roundtrip_latency":latency_summary([r["bridge_ms"] for r in timings if r["repetition"]==0]),
        "repeat_roundtrip_latency":latency_summary([r["bridge_ms"] for r in timings if r["repetition"]>0]),
        "native_costs":{"queries":len(native), "successful_queries":len(okay),
            "mean_search_payload_tokens":{n:statistics.fmean(r["search_payload_tokens"][n] for r in okay)
                                          if okay else None for n in ENCODINGS},
            "mean_search_payload_bytes":statistics.fmean(r["search_payload_bytes"] for r in okay) if okay else None,
            "policy":"Native component returns full observation rows; no native MCP/read/observer calls. "
                     "Failed cost observations remain unknown; successful-only mean is labeled.",
            "known_generative_calls_in_component":0, "full_workflow_model_calls":None},
        "native_query_costs":list(native.values()), "timing_rows":timings}
    validation = validation_status([bundle, measured])
    if failures:
        validation["failures"].append({"check":"native_query_errors","count":len(failures)})
    if len(timings) != 3 * plan["corpus"]["queries"]:
        validation["failures"].append({"check":"complete_timing_matrix","actual":len(timings)})
    if engine.metadata["native_process_exit_code"]:
        validation["failures"].append({"check":"native_exit_code","actual":engine.metadata["native_process_exit_code"]})
    after = {str(p.relative_to(HERE.parent)): sha(p.read_bytes()) for p in files}
    if after != input_hashes:
        validation["failures"].append({"check":"evaluator_source_unchanged"})
    validation["passed"] = not validation["failures"]
    report = {"schema_version":1, "evaluator_version":VERSION,
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "runtime":{"python":platform.python_version(),"platform":platform.platform(),
                   "machine":platform.machine(),"cpu_count":os.cpu_count()},
        "tokenizer":{"library":"tiktoken","version":counters[ENCODINGS[0]].version,"encodings":list(ENCODINGS)},
        "plan":plan, "input_sha256":input_hashes,
        "frozen_corpus":{k:v for k,v in bundle.items() if k!="documents"},
        "engine":measured, "historical_comparison":historical,
        "failures":failures, "validation":validation, "ledger_sha256":sha(ledger.read_bytes())}
    write_report(report,args.output)
    atomic(args.state_dir/"completed.json",{"validation":validation,"report_prefix":str(args.output)})
    print(json.dumps({"validation":validation,"output":str(args.output)},indent=2))
    return 0 if validation["passed"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exporter-src",type=Path,default=Path(".artifacts/claude-mem-baseline/src"))
    parser.add_argument("--locomo-path",type=Path,default=Path(".artifacts/data/locomo10.json"))
    parser.add_argument("--cache",type=Path,default=Path(".artifacts/competitors/claude-mem"))
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("benchmarks/results/claude-mem-components-public"))
    parser.add_argument("--offline",action="store_true")
    parser.add_argument("--smoke",action="store_true")
    args = parser.parse_args()
    if args.state_dir.exists():
        parser.error("--state-dir must be fresh; preserve interrupted runs separately")
    if not args.smoke and any(Path(str(args.output)+s).exists() for s in (".json.gz",".summary.json",".md")):
        parser.error("output already exists; use a new prefix rather than replacing evidence")
    args.state_dir = args.state_dir.resolve()
    args.state_dir.mkdir(parents=True)
    try:
        if args.smoke:
            smoke(args)
            return 0
        return run(args)
    except BaseException as error:
        atomic(args.state_dir/"failed.json",{"status":"failed","error":str(error),"evaluator_version":VERSION})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
