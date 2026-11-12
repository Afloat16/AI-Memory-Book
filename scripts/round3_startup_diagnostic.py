"""Fixed, startup-only investigation of round three's retained resource flag.

The 47,320-call performance report is immutable. This program neither reads nor
rewrites its acceptance result. Run only after committing this script and plan.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/round3-startup-diagnostic-plan.json"
SCRIPT = Path(__file__).resolve()
VERSION = "round3-startup-resource-review-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def exclusive(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def runtime_hash(src):
    package = src.resolve() / "memory_book"
    files = sorted(package.rglob("*.py"))
    require(files, "No runtime Python source files")
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(package)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def initialization_identity(src):
    raw = (src / "memory_book/store.py").read_bytes()
    module = ast.parse(raw)
    cls = next(item for item in module.body if isinstance(item, ast.ClassDef) and item.name == "MemoryBook")
    methods = {item.name: sha(ast.dump(item, include_attributes=False).encode())
               for item in cls.body if isinstance(item, ast.FunctionDef)
               and item.name in ("__init__", "__enter__")}
    require(set(methods) == {"__init__", "__enter__"}, "Missing startup methods")
    return {"methods_ast_sha256": methods,
            "unchanged_prefix_598_lines_sha256": sha(b"\n".join(raw.split(b"\n")[:598]))}


def load_plan():
    plan = json.loads(PLAN.read_bytes())
    require(plan["protocol"] == VERSION, "Different diagnostic protocol")
    design = plan["design"]
    require(design["blocks"] == 16 and design["timed_starts"] == 64
            and design["starts_per_engine"] == 32
            and design["order_per_block"] == ["baseline", "candidate", "candidate", "baseline"],
            "The fixed diagnostic schedule changed")
    require(plan["original_measurement"]["timed_recall_calls"] == 47320
            and plan["original_measurement"]["accepted"] is False,
            "Original report must remain pending its independent resource review")
    for path, expected in plan["corpus"]["helper_sha256"].items():
        require(sha((ROOT / path).read_bytes()) == expected, "Corpus helper changed: " + path)
    return plan


def worker(args, plan):
    src = (args.baseline_src if args.label == "baseline" else args.candidate_src).resolve()
    expected = plan["sources"][args.label]
    require(runtime_hash(src) == expected["runtime_sha256"], "Worker source bytes differ")
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(src))
    import memory_book
    from memory_book import MemoryBook
    from memory_book import store
    from benchmarks.public_data import load_locomo
    require(Path(memory_book.__file__).parent.resolve() == src / "memory_book", "Wrong runtime imported")
    require(sha(args.locomo_path.read_bytes()) == plan["corpus"]["source_file_sha256"], "Wrong LoCoMo source")
    data = load_locomo(args.locomo_path, split="heldout", max_queries=0)
    require(len(data.queries) == plan["corpus"]["query_count"]
            and data.fingerprint == plan["corpus"]["dataset_sha256"], "Wrong parsed public1015 cohort")
    row = {"label": args.label, "source": expected, "pid": os.getpid(),
           "queries_retained": len(data.queries), "mode": args.worker,
           "schema_sha256": sha(store.SCHEMA.encode())}
    sql = []
    if args.worker == "trace":
        connect = sqlite3.connect

        def traced_connect(*values, **options):
            db = connect(*values, **options)
            db.set_trace_callback(sql.append)
            return db

        sqlite3.connect = traced_connect
    with tempfile.TemporaryDirectory(prefix="round3-startup-", dir=args.temp_dir) as directory:
        db_path = Path(directory) / "memory.db"
        usage_before = resource.getrusage(resource.RUSAGE_SELF)
        cpu_start = time.process_time_ns()
        wall_start = time.perf_counter_ns()
        with MemoryBook(db_path, cache_size=0) as book:
            wall_ns = time.perf_counter_ns() - wall_start
            cpu_ns = time.process_time_ns() - cpu_start
            usage_after = resource.getrusage(resource.RUSAGE_SELF)
            # Snapshot the trace before diagnostic assertions or close run SQL.
            startup_sql = list(sql)
            require(book.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 0,
                    "Startup unexpectedly ingested pages")
        if args.worker == "sample":
            row.update(wall_ms=wall_ns / 1e6, cpu_ms=cpu_ns / 1e6,
                       wall_minus_cpu_ms=(wall_ns - cpu_ns) / 1e6,
                       rusage_delta={name: getattr(usage_after, name) - getattr(usage_before, name)
                                     for name in ("ru_inblock", "ru_oublock", "ru_nvcsw", "ru_nivcsw")})
        else:
            row.update(sql=startup_sql, sql_sha256=sha(encoded(startup_sql)), statements=len(startup_sql))
    row["initialization"] = initialization_identity(src)
    require(runtime_hash(src) == expected["runtime_sha256"], "Worker runtime changed")
    row["status"] = "completed"
    print(encoded(row).decode(), end="")


def numeric(values):
    values = sorted(values)
    n = len(values)
    if not n:
        return {"samples": 0}

    def quantile(q):
        location = (n - 1) * q
        lo = int(location)
        hi = min(lo + 1, n - 1)
        return values[lo] + (values[hi] - values[lo]) * (location - lo)

    return {"samples": n, "mean": statistics.fmean(values), "p50": quantile(.5),
            "p95": quantile(.95), "min": values[0], "max": values[-1],
            "sample_standard_deviation": statistics.stdev(values) if n > 1 else None}


def controller(args, plan):
    require(args.output.suffix == ".json", "Output must end in .json")
    args.temp_dir.mkdir(parents=True, exist_ok=True)
    # Require the review inputs to be durable before measuring.
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for path in (PLAN, SCRIPT):
        committed = subprocess.check_output(["git", "show", commit + ":" + str(path.relative_to(ROOT))], cwd=ROOT)
        require(committed == path.read_bytes(), "Commit the diagnostic script and plan before measuring")
    sources = {"baseline": args.baseline_src.resolve(), "candidate": args.candidate_src.resolve()}
    for label, src in sources.items():
        require(runtime_hash(src) == plan["sources"][label]["runtime_sha256"], "Wrong source: " + label)
    identities = {label: initialization_identity(src) for label, src in sources.items()}
    require(identities["baseline"] == identities["candidate"], "Startup source is not identical")
    require(sha(args.locomo_path.read_bytes()) == plan["corpus"]["source_file_sha256"], "Wrong public1015 input")
    schedule = [{"ordinal": block * 4 + offset, "block": block, "position": offset, "label": label}
                for block in range(16) for offset, label in enumerate(plan["design"]["order_per_block"])]
    started = args.output.with_suffix(".started.json")
    ledger = args.output.with_suffix(".jsonl")
    require(not any(path.exists() for path in (args.output, started, ledger)),
            "An attempt already exists; do not repeat or overwrite it")
    manifest = {"protocol": VERSION, "created_at": now(), "commit": commit,
                "plan_sha256": sha(PLAN.read_bytes()), "script_sha256": sha(SCRIPT.read_bytes()),
                "plan": plan, "source_paths": {k: str(v) for k, v in sources.items()},
                "initialization": identities, "schedule": schedule,
                "corpus_file_sha256": sha(args.locomo_path.read_bytes()),
                "host": {"platform": platform.platform(), "python": platform.python_version(),
                         "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count(),
                         "temporary_directory": str(args.temp_dir or Path(tempfile.gettempdir()))},
                "scope": "A separate startup-only diagnosis; original formal measurement is immutable."}
    exclusive(started, manifest)
    samples, traces, failures = [], [], []
    status = "running"
    try:
        with ledger.open("xb") as journal:
            for item in [dict(row, mode="sample") for row in schedule] + [
                {"ordinal": 64 + i, "label": label, "mode": "trace"}
                for i, label in enumerate(("baseline", "candidate"))]:
                intent = {"event": "started", "at": now(), "worker": item}
                journal.write(encoded(intent)); journal.flush(); os.fsync(journal.fileno())
                command = [sys.executable, str(SCRIPT), "--worker", item["mode"], "--label", item["label"],
                           "--baseline-src", str(sources["baseline"]), "--candidate-src", str(sources["candidate"]),
                           "--locomo-path", str(args.locomo_path.resolve())]
                if args.temp_dir:
                    command.extend(["--temp-dir", str(args.temp_dir.resolve())])
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=90,
                                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                    require(result.returncode == 0, "Worker failed: " + result.stderr[-4000:])
                    row = json.loads(result.stdout)
                    require(row["label"] == item["label"] and row["mode"] == item["mode"]
                            and row["status"] == "completed", "Worker identity/status mismatch")
                    row.update(item)
                    (samples if item["mode"] == "sample" else traces).append(row)
                    event = {"event": "completed", "at": now(), "worker": item, "result": row}
                except BaseException as exc:
                    event = {"event": "failed", "at": now(), "worker": item,
                             "error": type(exc).__name__ + ": " + str(exc)}
                    failures.append(event)
                    journal.write(encoded(event)); journal.flush(); os.fsync(journal.fileno())
                    raise
                journal.write(encoded(event)); journal.flush(); os.fsync(journal.fileno())
        status = "completed"
    finally:
        summary = {label: {field: numeric([row[field] for row in samples if row["label"] == label])
                           for field in ("wall_ms", "cpu_ms", "wall_minus_cpu_ms")}
                   for label in sources}
        changes = {}
        if all(summary[label]["wall_ms"]["samples"] for label in sources):
            changes = {field: {metric: 100 * (summary["candidate"][field][metric] /
                            summary["baseline"][field][metric] - 1)
                            if summary["baseline"][field][metric] else None
                              for metric in ("mean", "p50", "p95")}
                       for field in ("wall_ms", "cpu_ms")}
        report = {"protocol": VERSION, "status": status, "finished_at": now(), "manifest": manifest,
                  "timed_samples": len(samples), "samples": samples, "traces": traces, "failures": failures,
                  "summary": summary, "candidate_change_percent": changes,
                  "startup_source_equal": identities["baseline"] == identities["candidate"],
                  "startup_sql_equal": len(traces) == 2 and traces[0]["sql"] == traces[1]["sql"],
                  "ledger_sha256": sha(ledger.read_bytes()) if ledger.exists() else None,
                  "acceptance_override": False,
                  "interpretation": plan["interpretation"]}
        exclusive(args.output, report)
        print(json.dumps({key: report[key] for key in ("status", "timed_samples", "startup_source_equal",
                                                     "startup_sql_equal", "candidate_change_percent")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, required=True)
    parser.add_argument("--locomo-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/reports/round3-startup-diagnostic.json")
    parser.add_argument("--temp-dir", type=Path, default=ROOT / ".artifacts/round3-startup-temp")
    parser.add_argument("--worker", choices=("sample", "trace"))
    parser.add_argument("--label", choices=("baseline", "candidate"))
    args = parser.parse_args()
    plan = load_plan()
    if args.worker:
        require(args.label is not None, "Worker requires an engine label")
        worker(args, plan)
    else:
        controller(args, plan)


if __name__ == "__main__":
    main()
