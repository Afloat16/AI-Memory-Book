"""Audit existing observation-01 only; never import the product or run retrieval."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import pstats
import sqlite3
import subprocess

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]
OUTPUT = DIRECTORY / "observation-01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def load(path):
    return json.loads(path.read_bytes())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def snapshot(path):
    wal = Path(str(path) + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True) as db:
        source = digest({table: [list(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
                         for table in ("projects", "chapters", "sessions", "turns", "sections", "pages")})
        queries = {
            "pages": "SELECT * FROM pages ORDER BY rid",
            "sections": "SELECT * FROM sections ORDER BY id",
            "turns": "SELECT * FROM turns ORDER BY id",
            "chapters": "SELECT id,project_id,task_id,title,summary FROM chapters ORDER BY id",
            "sessions": "SELECT id,external_id,project_id,chapter_id,title,created_at,content_hash,raw_json,segmentation,message_count,turn_count,content_chars,settings_json FROM sessions ORDER BY id",
            "pages_fts": "SELECT rowid,title,question,body,directory FROM pages_fts ORDER BY rowid",
            "pages_stem_fts": "SELECT rowid,title,question,body,directory FROM pages_stem_fts ORDER BY rowid",
        }
        indexed = {}
        for name, query in queries.items():
            rows = [list(row) for row in db.execute(query)]
            indexed[name] = {"rows": len(rows), "sha256": digest(rows)}
        return {"source": source, "indexed": indexed,
                "revision": db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0],
                "cache_rows": db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}


def main():
    assert not (OUTPUT / "summary.json").exists() and not (OUTPUT / "saved-data-audit.json").exists()
    plan = load(DIRECTORY / "plan.json")
    raw_files = {str(p.relative_to(OUTPUT)): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                 for p in OUTPUT.iterdir() if p.is_file()}
    for name, expected in plan["input_files"].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    for name, expected in plan["diagnostic_files"].items():
        assert sha((DIRECTORY / name).read_bytes()) == expected, name
    for name, expected in plan["environment_files"].items():
        assert sha(Path(name).read_bytes()) == expected, name
    assert load(OUTPUT / "started.json")["plan_sha256"] == sha((DIRECTORY / "plan.json").read_bytes())
    failure = load(OUTPUT / "failure.json")
    assert failure == {"status": "failed-no-retry", "type": "AssertionError", "error": ""}
    worker = json.loads(gzip.decompress((ROOT / plan["reference_worker"]).read_bytes()))
    config = next(c for c in worker["configurations"] if c["id"] == "mcp-token1024")
    assert worker["source"] == plan["source"] and worker["dataset_sha256"] == plan["dataset_sha256"]
    ledger = lines(OUTPUT / "attempts.jsonl")
    assert len(ledger) == 2030 and len(config["rows"]) == plan["calls"] == 1015
    actual_rows = []
    keys = ("payload_sha256", "native_payload_sha256", "envelope_sha256", "context_sha256", "token_metadata", "tokens")
    for i, expected in enumerate(config["rows"], 1):
        start, finish = ledger[(i - 1) * 2:i * 2]
        assert start == {"event": "call_started", "query_id": expected["query_id"], "sequence": i}
        assert finish["event"] == "call_finished"
        row = finish["row"]
        assert row["sequence"] == i and row["query_id"] == expected["query_id"]
        assert "wall_ms" not in row and not any(row["invariants"].values())
        assert all(row[key] == expected[key] for key in keys)
        assert row["cache_rows_before"] == 0 and row["cache_rows_after"] == 1
        assert row["engine_source_sha256"] == plan["source"]["runtime_sha256"]
        assert row["context_chars"] <= 8000 and row["result_count"] <= 5
        assert row["token_metadata"]["native"] == row["token_metadata"]["response"]
        assert row["token_metadata"]["native"]["context_tokens"] == row["tokens"]["cl100k_base"]["context"] <= 1024
        actual_rows.append(row)
    assert digest([row["query_id"] for row in actual_rows]) == plan["query_order_sha256"]
    events = lines(OUTPUT / "observer-events.jsonl")
    finished = [event for event in events if event["event"] == "observer_finished"]
    assert len(finished) == 1
    observed = finished[0]
    assert (observed["server_count"], observed["tool_calls"], observed["tool_errors"]) == (1, 1015, 0)
    for name in ("tool_started", "tool_finished"):
        selected = [event for event in events if event["event"] == name]
        assert [event["sequence"] for event in selected] == list(range(1, 1016))
        if name == "tool_finished":
            assert all(event["error"] is None for event in selected)
    transport = observed["transport_counts"]
    assert transport == {"sdk_stdout_flush": 1017, "sdk_stdout_write": 1017,
        "to_thread_run_sync:other:TextIOWrapper.readline": 1019,
        "to_thread_run_sync:sdk_stdout:TextIOWrapper.flush": 1017,
        "to_thread_run_sync:sdk_stdout:TextIOWrapper.write": 1017}
    profiles = {}
    for label, calls in (("first-call", 1), ("all-calls", 1015)):
        stored = load(OUTPUT / (label + ".functions.json"))
        binary = OUTPUT / (label + ".pstats")
        assert sha(binary.read_bytes()) == stored["pstats_sha256"] and stored["tool_calls_included"] == calls
        saved_stats = pstats.Stats(str(binary)).stats
        assert len(saved_stats) == len(stored["functions"])
        for entry in stored["functions"]:
            key = (entry["filename"], entry["line"], entry["name"])
            raw = saved_stats[key]
            assert tuple(entry[k] for k in ("primitive_calls", "total_calls", "profile_self_seconds", "profile_cumulative_seconds")) == raw[:4]
            callers = {(r["filename"], r["line"], r["name"]): tuple(r["stats"]) if isinstance(r["stats"], list) else r["stats"] for r in entry["callers"]}
            assert callers == raw[4]
        for name, suffix in (("recall", "/store.py"), ("recall_payload", "/mcp_server.py")):
            matched = [r for r in stored["functions"] if r["name"] == name and r["filename"].endswith(suffix)]
            assert len(matched) == 1 and matched[0]["total_calls"] == calls
        profiles[label] = stored
    all_functions = profiles["all-calls"]["functions"]
    roots = [r for r in all_functions if r["name"] == "recall_memory"]
    assert len(roots) == 1 and roots[0]["primitive_calls"] == 0 and roots[0]["total_calls"] == 391 and roots[0]["profile_cumulative_seconds"] == 0
    assert not any(r["name"] == "recall_memory" for r in profiles["first-call"]["functions"])
    before, after = snapshot(ROOT / plan["database_path"]), snapshot(OUTPUT / "book.db")
    assert before == after and after["indexed"] == worker["indexed_content"] and after["cache_rows"] == 0
    package = Path(plan["source_path"]) / "memory_book"
    value = hashlib.sha256()
    for p in sorted(package.rglob("*.py")):
        value.update(str(p.relative_to(package)).encode() + b"\0" + p.read_bytes() + b"\0")
    assert value.hexdigest() == plan["source"]["runtime_sha256"]
    assert subprocess.check_output(["git", "-C", plan["source_path"], "rev-parse", "HEAD"], text=True).strip() == plan["source"]["commit"]
    plain = lambda row: {k: v for k, v in row.items() if k != "callers"}
    useful = [r for r in all_functions if r["name"] != "recall_memory"]
    summary = {"schema_version": 1, "status": "complete-calls-validated-with-preserved-diagnostic-finalization-failure",
        "source": plan["source"], "reference_worker": plan["reference_worker"],
        "reference_worker_sha256": plan["reference_worker_sha256"], "plan_sha256": sha((DIRECTORY / "plan.json").read_bytes()),
        "registration_commit": "592e2abc0b3176a25fe070453f7f5ea403a95409", "calls": 1015, "attempt_events": 2030,
        "all_payload_envelope_and_native_hashes_equal": True, "all_recorded_invariants_passed": True,
        "query_order_sha256": plan["query_order_sha256"], "observer_finished": observed,
        "source_and_index_offline_comparison": {"pinned_base": before, "completed_observation": after,
            "boundary": "Read-only immutable SQLite projections after execution; no MemoryBook construction or recall. Original script also asserted before==after before the failing final root-count assertion."},
        "failure_preserved": {"path": "failure.json", **raw_files["failure.json"], "value": failure},
        "profile_boundary_anomaly": {"root": roots[0], "root_absent_in_first_call_snapshot": True,
            "interpretation": "The profiler was repeatedly enabled/disabled at the tool boundary; the saved root node and its caller edges do not account for complete calls. The precise profiler-internal cause was not established. Do not use this root node to infer missing tool executions or end-to-end duration.",
            "independent_completion_evidence": "1015 ordered observer starts/finishes with zero errors; 1015 saved SDK outputs; interior store.recall and recall_payload each report 1015 invocations.",
            "invalidated_claims": ["Original diagnostic exit success", "Complete root call graph", "Root inclusive time", "Any formal latency, transport-time subtraction or speedup conclusion"]},
        "diagnostic_hotspots": {"boundary": "Instrumented interior attribution only; caller edges to the root are incomplete and instrumentation overhead remains included.",
            "top_self": [plain(r) for r in sorted(useful, key=lambda r: r["profile_self_seconds"], reverse=True)[:30]],
            "top_cumulative": [plain(r) for r in sorted(useful, key=lambda r: r["profile_cumulative_seconds"], reverse=True)[:25]]},
        "transport_conclusion": "The unchanged SDK makes 1017 stdout writes and 1017 flushes, each with a separate worker dispatch. Coalescing each write/flush pair could remove 1017 dispatches; no duration or speedup was measured for transport.",
        "raw_files": raw_files, "retrieval_calls_during_audit": 0, "timing_runs_during_audit": 0,
        "limits": ["No original files, failure status or profiler counters were repaired or overwritten.",
            "Saved hashes and invariant flags validate recorded observations; omitted response bodies cannot be independently re-tokenized in this audit.",
            "Local instrumented profile times are not hosted performance evidence. C6 remains formally rejected; no threshold changes or same-source reruns are authorized by this supplement."]}
    summary_raw = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode()
    with (OUTPUT / "summary.json").open("xb") as stream:
        stream.write(summary_raw)
    receipt = {"status": "saved-data-audit-passed-original-diagnostic-failure-retained",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "audit_script_sha256": sha(Path(__file__).read_bytes()),
        "summary_sha256": sha(summary_raw), "raw_files": raw_files, "source": plan["source"],
        "call_rows_verified": 1015, "ledger_events_verified": 2030, "complete_pstats_json_agree": True,
        "original_exit": "failure", "additional_retrieval_calls": 0, "additional_profile_or_timing_runs": 0}
    with (OUTPUT / "saved-data-audit.json").open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "summary_sha256": sha(summary_raw),
        "audit_receipt_sha256": sha((OUTPUT / "saved-data-audit.json").read_bytes()),
        "audit_script_sha256": receipt["audit_script_sha256"], "additional_retrieval_calls": 0}))


if __name__ == "__main__":
    main()
