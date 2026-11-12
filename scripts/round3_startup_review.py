"""Fixed supplemental startup diagnostic; never reruns formal recall."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import gzip
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

VERSION = "round3-startup-cause-diagnostic-v1"
ORDER = ["baseline", "candidate", "candidate", "baseline"]
PHASES = (("plain", 16), ("instrumented", 4))
EXPECTED = {
    "baseline": ("dd2f88be742ed330269e7dd5915b6f75089d7fef", "d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57"),
    "candidate": ("2d199b93f650eccd3dd239178822b31001b880e3", "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46"),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def source_hash(package):
    hasher = hashlib.sha256()
    for path in sorted(Path(package).rglob("*.py")):
        hasher.update(path.relative_to(package).as_posix().encode() + b"\0")
        hasher.update(path.read_bytes() + b"\0")
    return hasher.hexdigest()


def source_identity(src, label):
    src = Path(src).resolve()
    package = src / "memory_book"
    commit = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    result = {"commit": commit, "runtime_sha256": source_hash(package)}
    if (commit, result["runtime_sha256"]) != EXPECTED[label]:
        raise ValueError("Runtime source does not match the original formal binding: " + label)
    return result


def unchanged_startup(baseline, candidate):
    """Compare all top-level definitions and class methods outside recall."""
    def view(source):
        module = ast.parse(source)
        result = {}
        for node in module.body:
            if isinstance(node, ast.ClassDef) and node.name == "MemoryBook":
                for member in node.body:
                    name = getattr(member, "name", None)
                    if name in {"recall", "_project_rowid_bounds"}:
                        continue
                    key = "MemoryBook." + (name or ast.dump(member, include_attributes=False))
                    result[key] = ast.dump(member, include_attributes=False)
            else:
                key = getattr(node, "name", None) or str(len(result))
                result[key] = ast.dump(node, include_attributes=False)
        return result
    left, right = view(baseline), view(candidate)
    if left != right:
        different = sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))
        raise ValueError("Startup/store code outside the registered recall change differs: " + repr(different))
    return {"passed": True, "unchanged_ast_components": len(left), "ast_sha256": digest(canonical(left)),
            "scope": "All store top-level definitions and MemoryBook members except recall/_project_rowid_bounds."}


class SQLRecorder:
    """Instrumentation is used only in the separate diagnostic phase."""
    def __init__(self):
        self.events = []
        self.trace = []
        self.origin = time.perf_counter_ns()
        self.original_connect = sqlite3.connect

    def connect(self, *args, **kwargs):
        recorder = self

        class Connection(sqlite3.Connection):
            def execute(self, sql, *arguments):
                return recorder.measure("execute", sql, lambda: super(Connection, self).execute(sql, *arguments))

            def executescript(self, sql):
                return recorder.measure("executescript", sql, lambda: super(Connection, self).executescript(sql))

        kwargs["factory"] = Connection
        connection = self.measure("connect", None, lambda: self.original_connect(*args, **kwargs))
        connection.set_trace_callback(lambda sql: self.trace.append({
            "sql": sql, "offset_ms": (time.perf_counter_ns() - self.origin) / 1e6}))
        return connection

    def measure(self, method, sql, callback):
        wall, cpu = time.perf_counter_ns(), time.process_time_ns()
        try:
            return callback()
        finally:
            wall_ms = (time.perf_counter_ns() - wall) / 1e6
            cpu_ms = (time.process_time_ns() - cpu) / 1e6
            self.events.append({"method": method, "sql": sql if method == "execute" else None,
                                "sql_sha256": digest(sql.encode()) if sql else None,
                                "wall_ms": wall_ms, "cpu_ms": cpu_ms,
                                "wall_minus_cpu_ms": wall_ms - cpu_ms})


def worker(args):
    label, phase = args.worker_label, args.worker_phase
    identity = source_identity(args.worker_src, label)
    sys.path.insert(0, str(Path(args.worker_src).resolve()))
    from memory_book import MemoryBook
    import memory_book
    if Path(memory_book.__file__).resolve().parent != Path(args.worker_src).resolve() / "memory_book":
        raise ValueError("Wrong imported source")
    recorder = SQLRecorder() if phase == "instrumented" else None
    if recorder is not None:
        sqlite3.connect = recorder.connect
    result = {"label": label, "phase": phase, "source": identity, "started_at": now()}
    try:
        with tempfile.TemporaryDirectory(prefix="round3-startup-", dir=args.workspace) as directory:
            path = Path(directory) / "memory.db"
            wall, cpu = time.perf_counter_ns(), time.process_time_ns()
            with MemoryBook(path, cache_size=0) as book:
                # Exclude verification, closing and report serialization from timing.
                wall_ms = (time.perf_counter_ns() - wall) / 1e6
                cpu_ms = (time.process_time_ns() - cpu) / 1e6
                events = list(recorder.events) if recorder else None
                trace = list(recorder.trace) if recorder else None
                schema = book.db.execute("SELECT name,type,sql FROM sqlite_master ORDER BY name,type").fetchall()
                pages = book.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
                cache = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                revision = book.revision
                if (pages, cache, revision) != (0, 0, 0):
                    raise ValueError("Startup diagnostic unexpectedly populated the database")
                result.update({"wall_ms": wall_ms, "cpu_ms": cpu_ms, "wall_minus_cpu_ms": wall_ms - cpu_ms,
                               "sqlite_events": events, "sqlite_trace": trace,
                               "schema_sha256": digest(canonical([list(row) for row in schema])),
                               "counts": {"pages": pages, "recall_cache": cache, "revision": revision}})
        if source_identity(args.worker_src, label) != identity:
            raise ValueError("Runtime changed during diagnostic")
        result.update({"status": "completed", "finished_at": now()})
        save(args.worker_output, result)
    finally:
        if recorder is not None:
            sqlite3.connect = recorder.original_connect


def stats(values):
    ordered = sorted(values)
    position = (len(ordered) - 1) * .95
    index = int(position)
    p95 = ordered[index] + (ordered[min(index + 1, len(ordered) - 1)] - ordered[index]) * (position - index)
    return {"samples": len(values), "mean": statistics.fmean(values), "p50": statistics.median(values),
            "p95": p95, "min": min(values), "max": max(values)}


def summarize(rows):
    result = []
    for phase, _ in PHASES:
        groups = {}
        for label in ORDER[:2]:
            selected = [row for row in rows if row["phase"] == phase and row["label"] == label]
            groups[label] = {metric: stats([row[metric] for row in selected])
                             for metric in ("wall_ms", "cpu_ms", "wall_minus_cpu_ms")}
            if phase == "instrumented":
                events = [event for row in selected for event in row["sqlite_events"]
                          if event["method"] == "executescript"]
                groups[label]["schema_executescript"] = {
                    metric: stats([event[metric] for event in events])
                    for metric in ("wall_ms", "cpu_ms", "wall_minus_cpu_ms")}
        result.append({"phase": phase, **groups,
                       "mean_wall_change_percent": 100 * (groups["candidate"]["wall_ms"]["mean"] /
                                                           groups["baseline"]["wall_ms"]["mean"] - 1)})
    return result


def read_plan(path):
    plan = json.loads(Path(path).read_bytes())
    if plan["protocol"] != VERSION or plan["schedule"] != {
            "order": ORDER, "plain_blocks": 16, "instrumented_blocks": 4, "total_processes": 80}:
        raise ValueError("The fixed diagnostic schedule changed")
    if plan["sources"] != {label: {"commit": value[0], "runtime_sha256": value[1]} for label, value in EXPECTED.items()}:
        raise ValueError("Diagnostic sources differ from original formal sources")
    return plan


def run(args):
    plan = read_plan(args.plan)
    original_bytes = args.original_report.read_bytes()
    original_raw = gzip.decompress(original_bytes)
    original = json.loads(original_raw)
    if digest(original_raw) != plan["original"]["report_sha256"] or not original["validation"]["passed"] or not original["acceptance"]["numeric_gate_passed"] or original["acceptance"]["accepted"] is not False:
        raise ValueError("Original formal performance evidence differs")
    original_digest = digest(original_bytes)
    sources = {label: Path(path).resolve() for label, path in
               (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    identities = {label: source_identity(path, label) for label, path in sources.items()}
    compatibility = unchanged_startup(*[(sources[label] / "memory_book/store.py").read_text() for label in ORDER[:2]])
    state = args.output_dir.resolve()
    # An existing or interrupted run is immutable; there is no retry/overwrite flag.
    state.mkdir(parents=True, exist_ok=False)
    (state / "databases").mkdir()
    registration = {
        "protocol": VERSION, "created_at": now(), "plan": plan,
        "plan_sha256": digest(args.plan.read_bytes()), "script_sha256": digest(Path(__file__).read_bytes()),
        "sources": identities, "startup_code_identity": compatibility,
        "original_formal_report": {"raw_sha256": digest(original_raw), "compressed_sha256": original_digest,
                                 "accepted": original["acceptance"]["accepted"],
                                 "numeric_gate_passed": original["acceptance"]["numeric_gate_passed"],
                                 "resource_review": original["acceptance"]["resource_review"]},
        "host": {"python": sys.version, "sqlite": sqlite3.sqlite_version, "platform": platform.platform(),
                 "cpu_count": os.cpu_count(), "run_id": os.environ.get("GITHUB_RUN_ID"),
                 "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                 "workflow_commit": os.environ.get("GITHUB_SHA")},
        "interpretation": plan["decision"],
    }
    save(state / "registration.json", registration)
    rows = []
    try:
        for phase, blocks in PHASES:
            for block in range(blocks):
                for label in ORDER:
                    index = len(rows)
                    key = f"{index:03d}-{phase}-{label}"
                    output = state / "workers" / (key + ".json")
                    intent = {"index": index, "phase": phase, "block": block, "label": label,
                              "source": identities[label], "started_at": now()}
                    save(state / "workers" / (key + ".started.json"), intent)
                    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker-label", label,
                               "--worker-phase", phase, "--worker-src", str(sources[label]),
                               "--workspace", str(state / "databases"), "--worker-output", str(output)]
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if completed.returncode:
                        save(state / "workers" / (key + ".failed.json"),
                             {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr})
                        raise RuntimeError("Startup diagnostic worker failed: " + key)
                    row = json.loads(output.read_bytes())
                    if row["source"] != identities[label] or row["label"] != label or row["phase"] != phase or row["status"] != "completed":
                        raise ValueError("Worker identity/status differs")
                    rows.append({**intent, **row})
        if len(rows) != 80 or len({row["schema_sha256"] for row in rows}) != 1:
            raise ValueError("Missing workers or unequal database schemas")
        traces = {digest(canonical([item["sql"] for item in row["sqlite_trace"]]))
                  for row in rows if row["phase"] == "instrumented"}
        if len(traces) != 1:
            raise ValueError("Instrumented startup SQL sequences differ")
        if identities != {label: source_identity(path, label) for label, path in sources.items()}:
            raise ValueError("Source changed during run")
        if digest(args.original_report.read_bytes()) != original_digest:
            raise ValueError("Original formal report changed during diagnostic")
        report = {"protocol": VERSION, "status": "completed", "finished_at": now(),
                  "registration": registration, "samples": rows, "summary": summarize(rows),
                  "validation": {"passed": True, "workers": 80, "equal_schema": True,
                                 "equal_startup_sql": True, "sql_trace_sha256": next(iter(traces)),
                                 "original_formal_report_unchanged": True},
                  "decision": "Independent resource review required; original accepted=false is not overridden."}
        save(state / "report.json", report)
        save(state / "summary.json", {key: value for key, value in report.items() if key != "samples"})
        print(json.dumps({"status": "completed", "workers": len(rows), "output_dir": str(state)}))
    except BaseException as error:
        save(state / "failure.json", {"status": "failed", "finished_at": now(), "completed_workers": len(rows),
                                     "error": type(error).__name__ + ": " + str(error)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--original-report", type=Path)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--worker-label", choices=ORDER[:2], help=argparse.SUPPRESS)
    parser.add_argument("--worker-phase", choices=[phase for phase, _ in PHASES], help=argparse.SUPPRESS)
    parser.add_argument("--worker-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_label:
        return worker(args)
    if not all((args.plan, args.original_report, args.baseline_src, args.candidate_src, args.output_dir)):
        parser.error("Controller needs --plan, --original-report, --baseline-src, --candidate-src and --output-dir")
    return run(args)


if __name__ == "__main__":
    main()
