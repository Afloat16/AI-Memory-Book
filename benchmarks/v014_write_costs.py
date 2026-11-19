"""Frozen, source-bound write/resource costs; no retrieval timing is mixed in.

The coordinator starts eight fresh workers in the registered AB/BA order.
Every worker ingests identical original conversations through the public API,
then replays skips, replacements, relinks and deletions. Raw per-operation
observations and source digests survive independently of the final summary.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
try:
    import resource
except ImportError:  # Pure protocol/integrity checks remain importable on Windows.
    resource = None
import sqlite3
import statistics
import subprocess
import sys
import time


PROTOCOL = "v014-write-costs-2"
PROJECTS = 20
SESSIONS_PER_PROJECT = 8
TURNS_PER_SESSION = 32
ORDER = (("baseline", "candidate"), ("candidate", "baseline"),
         ("baseline", "candidate"), ("candidate", "baseline"))
STAGE_PAGES = {"ingest": 5120, "skip": 5120, "replacement": 5120, "relink": 5120,
               "delete_session": 4800, "delete_project": 4544}
PROTOCOL_PATHS = ("benchmarks/v014_write_costs.py",
                  "benchmarks/experiments/v014-write-costs-plan.json",
                  "tests/test_v014_write_costs.py")
SOURCE_COLUMNS = {
    "projects": "id,name",
    "chapters": "id,project_id,task_id,title,summary",
    "sessions": "id,external_id,project_id,chapter_id,title,created_at,content_hash,raw_json,segmentation,message_count,turn_count,content_chars,settings_json",
    "turns": "id,session_pk,ordinal,question,content,message_indices",
    "sections": "id,session_pk,chapter_id,title,summary,ordinal",
    "pages": "rid,id,section_id,session_pk,chapter_id,project_id,title,question,content,source_refs,ordinal",
    "pages_fts": "rowid,title,question,body,directory",
    "pages_stem_fts": "rowid,title,question,body,directory",
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def write_new(path: Path, value):
    """Durably capture one immutable record before discarding working state."""
    with path.open("xb") as stream:
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def append_record(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def interpreter_path():
    # Normalize relative components before changing cwd, but preserve a venv's
    # executable symlink: resolving it can silently select the base interpreter.
    if not sys.executable:
        raise RuntimeError("the active Python interpreter has no executable path")
    return os.path.abspath(sys.executable)


def session(project: int, number: int, *, replacement: bool = False):
    return {
        "project": f"worker-{project:03}", "project_name": "Shared worker engineering project",
        "session_id": f"session-{number:03}", "task_id": f"policy-{number % 3}",
        "task_title": "Worker lease policy 缓存策略", "title": "Engineering maintenance record",
        "created_at": f"2020-03-{number + 1:02}T10:00:00Z",
        "messages": [message for turn in range(TURNS_PER_SESSION) for message in (
            {"role": "user", "content": f"Review production lease_duration and boundary_guard for turn {turn}."},
            {"role": "assistant", "content": (
                f"Approved lease_duration={1000 + project + (5000 if replacement else 0)}. "
                f"boundary_guard=stable_{project:03}. Revision trace={number:03}_{turn:03}. "
                "The original retry policy remains effective. 缓存约束需要保留原始证据。")})],
    }


def initial_sources():
    # Interleave projects while keeping the complete logical corpus identical.
    return [session(project, number) for number in range(SESSIONS_PER_PROJECT)
            for project in range(PROJECTS)]


def operations():
    sources = initial_sources()
    result = [("ingest", "ingest", payload) for payload in sources]
    result.extend(("skip", "ingest", payload) for payload in sources[:20])
    result.extend(("replacement", "ingest", session(project, 0, replacement=True)) for project in range(10))
    result.extend(("relink", "link_session", (f"worker-{project:03}", "session-000",
                   "migration-policy", "Migrated worker lease policy")) for project in range(5))
    result.extend(("delete_session", "delete_session", (f"worker-{project:03}", "session-001"))
                  for project in range(10))
    result.append(("delete_project", "delete_project", ("worker-019",)))
    return result


def git(root: Path, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def source_identity(root: Path):
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError(f"runtime checkout has tracked modifications: {root}")
    files = git(root, "ls-files", "src/memory_book").splitlines()
    if not files or any((root / path).is_symlink() for path in files):
        raise ValueError("runtime source files must be tracked regular files")
    hashes = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in files}
    native = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((root / "src/memory_book").glob("_native*"))
              if path.is_file() and path.suffix in {".so", ".pyd", ".dylib"}}
    return {"commit": git(root, "rev-parse", "HEAD"), "runtime_files": hashes,
            "runtime_sha256": digest(hashes), "native_files": native}


def protocol_identity(commit: str):
    root = Path(__file__).resolve().parents[1]
    commit = git(root, "rev-parse", f"{commit}^{{commit}}")
    files = {}
    for relative in PROTOCOL_PATHS:
        current = (root / relative).read_bytes()
        frozen = subprocess.check_output(["git", "-C", str(root), "show", f"{commit}:{relative}"])
        if current != frozen:
            raise ValueError(f"protocol changed after freeze: {relative}")
        files[relative] = hashlib.sha256(current).hexdigest()
    return {"protocol_commit": commit, "protocol_files": files}


def runtime_proof(root: Path, backend: str):
    import memory_book
    from memory_book._text_backend import BACKEND_NAME, NATIVE
    if Path(memory_book.__file__).resolve().parent != root / "src/memory_book":
        raise RuntimeError("worker loaded another runtime")
    if BACKEND_NAME != backend:
        raise RuntimeError(f"backend mismatch: {BACKEND_NAME} != {backend}")
    identity = source_identity(root)
    native = None
    if NATIVE is not None:
        path = Path(NATIVE.__file__).resolve()
        if path.parent != root / "src/memory_book":
            raise RuntimeError("worker loaded a native binary outside the requested checkout")
        native = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if identity["native_files"].get(path.name) != native["sha256"]:
            raise RuntimeError("loaded native binary differs from the source-bound inventory")
    if bool(native) != (backend == "native"):
        raise RuntimeError("loaded native binary does not match the selected backend")
    return {"source": identity, "backend": backend, "native": native}


def file_sizes(path: Path):
    sizes = {}
    for suffix, label in (("", "main"), ("-wal", "wal"), ("-shm", "shm")):
        current = Path(str(path) + suffix)
        sizes[label] = current.stat().st_size if current.exists() else 0
    sizes["total"] = sum(sizes.values())
    return sizes


def resources(book, path):
    return {"rss_high_water_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_unit": "bytes" if sys.platform == "darwin" else "KiB",
            "files_bytes": file_sizes(path),
            "sqlite_page_bytes": book.db.execute("PRAGMA page_count").fetchone()[0]
            * book.db.execute("PRAGMA page_size").fetchone()[0]}


def source_snapshot(book):
    # Exclude wall-clock maintenance metadata; source bytes and every source
    # coordinate/identity are retained. These reads are outside write timing.
    tables = {}
    for table, selected in SOURCE_COLUMNS.items():
        hasher, count = hashlib.sha256(), 0
        order = "rowid" if table.endswith("fts") else "id"
        for row in book.db.execute(f"SELECT {selected} FROM {table} ORDER BY {order}"):
            hasher.update(encoded(tuple(row)) + b"\n")
            count += 1
        tables[table] = {"rows": count, "sha256": hasher.hexdigest()}
    fts_statistics = {}
    for table in ("pages_fts", "pages_stem_fts"):
        name = "write_cost_audit_" + table
        book.db.execute(f"CREATE VIRTUAL TABLE temp.{name} USING fts5vocab(main,{table},'col')")
        try:
            hasher, count = hashlib.sha256(), 0
            for row in book.db.execute(f"SELECT term,col,doc,cnt FROM {name} ORDER BY term,col"):
                hasher.update(encoded(tuple(row)) + b"\n")
                count += 1
            fts_statistics[table] = {"rows": count, "sha256": hasher.hexdigest()}
        finally:
            book.db.execute(f"DROP TABLE temp.{name}")
    return {"tables": tables, "revision": book.revision,
            "logical_sources_sha256": digest(book.export()),
            "fts_term_column_statistics": fts_statistics,
            "combined_sha256": digest(tables)}


def worker(args):
    if resource is None:
        raise RuntimeError("write-cost measurements require POSIX resource accounting")
    root, output = args.runtime.resolve(), args.output.resolve()
    from memory_book import MemoryBook
    proof = runtime_proof(root, args.backend)
    frozen = protocol_identity(args.protocol_commit)
    if proof["source"]["commit"] != args.commit:
        raise RuntimeError("runtime ref moved after coordinator preflight")
    output.mkdir(parents=True, exist_ok=False)
    path = output / "working.db"
    header = {"protocol": PROTOCOL, "arm": args.arm, "round": args.round,
              **proof, **frozen,
              "environment": {"python": sys.version, "sqlite": sqlite3.sqlite_version,
                              "platform": platform.platform(), "machine": platform.machine(),
                              "cpu_count": os.cpu_count(), "pid": os.getpid(),
                              "executable": interpreter_path(), "prefix": sys.prefix},
              "started_utc": datetime.now(timezone.utc).isoformat()}
    write_new(output / "identity.json", header)
    sequence, stages, book, phase = operations(), [], None, "initialize"
    try:
        with (output / "operations.jsonl").open("x", encoding="utf-8") as journal, \
                (output / "operation-starts.jsonl").open("x", encoding="utf-8") as starts:
            append_record(starts, {"stage": "initialize"})
            wall, cpu = time.perf_counter_ns(), time.process_time_ns()
            try:
                book = MemoryBook(path, segmentation="turn", min_page_chars=0, max_page_chars=900, cache_size=0)
            except BaseException as exc:
                append_record(journal, {"stage": "initialize", "wall_ns": time.perf_counter_ns() - wall,
                    "cpu_ns": time.process_time_ns() - cpu,
                    "error": {"type": type(exc).__name__, "message": str(exc)}})
                raise
            opened = {"stage": "initialize", "wall_ns": time.perf_counter_ns() - wall,
                      "cpu_ns": time.process_time_ns() - cpu, "resources": resources(book, path)}
            append_record(journal, opened)
            for index, (stage, method, payload) in enumerate(sequence):
                phase = f"operation-{index}-{stage}"
                labels = {"index": index, "stage": stage, "method": method, "request_sha256": digest(payload)}
                append_record(starts, labels)
                wall, cpu = time.perf_counter_ns(), time.process_time_ns()
                try:
                    response = (book.ingest(payload) if method == "ingest" else getattr(book, method)(*payload))
                except BaseException as exc:
                    append_record(journal, {**labels, "wall_ns": time.perf_counter_ns() - wall,
                        "cpu_ns": time.process_time_ns() - cpu,
                        "error": {"type": type(exc).__name__, "message": str(exc)}})
                    raise
                elapsed, process = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
                record = {**labels, "wall_ns": elapsed, "cpu_ns": process,
                          "response": response, "resources": resources(book, path)}
                error = response_error(stage, method, payload, response)
                if error:
                    record["contract_error"] = error
                append_record(journal, record)
                if error:
                    raise AssertionError(error)
                if index + 1 == len(sequence) or sequence[index + 1][0] != stage:
                    phase = f"snapshot-{stage}"
                    snapshot = source_snapshot(book)
                    stage_record = {"stage": stage, "after_operation": index,
                                    "source_snapshot": snapshot, "resources": resources(book, path)}
                    if snapshot["tables"]["pages"]["rows"] != STAGE_PAGES[stage]:
                        stage_record["contract_error"] = "unexpected stage page count"
                    stages.append(stage_record)
                    write_new(output / f"source-{stage}.json", stage_record)
                    if "contract_error" in stage_record:
                        raise AssertionError(stage_record["contract_error"])
            summary = {"status": "complete", "protocol": PROTOCOL, "operations": len(sequence),
                       "initial_pages": stages[0]["source_snapshot"]["tables"]["pages"]["rows"],
                       "final_pages": stages[-1]["source_snapshot"]["tables"]["pages"]["rows"],
                       "final_resources_open": resources(book, path)}
            phase = "close"
            append_record(starts, {"stage": "close"})
            wall, cpu = time.perf_counter_ns(), time.process_time_ns()
            try:
                book.close()
            except BaseException as exc:
                append_record(journal, {"stage": "close", "wall_ns": time.perf_counter_ns() - wall,
                    "cpu_ns": time.process_time_ns() - cpu,
                    "error": {"type": type(exc).__name__, "message": str(exc)}})
                raise
            elapsed, process = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
            book = None
            append_record(journal, {"stage": "close", "wall_ns": elapsed, "cpu_ns": process,
                "resources": {"files_bytes": file_sizes(path),
                              "rss_high_water_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}})
        phase = "final-source-binding"
        final = {**runtime_proof(root, args.backend), **protocol_identity(args.protocol_commit)}
        if final != {**proof, **frozen}:
            raise RuntimeError("runtime, native binary or protocol changed during the worker")
        write_new(output / "identity-after.json", final)
        summary["files_bytes_closed"] = file_sizes(path)
        names = ["identity.json", "identity-after.json", "operations.jsonl", "operation-starts.jsonl",
                 *(f"source-{stage}.json" for stage in STAGE_PAGES)]
        summary["evidence_sha256"] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names}
        write_new(output / "complete.json", summary)
        # Only the coordinator may remove a completed database, after all
        # original records, exact sources and paired snapshots are accepted.
    except BaseException as exc:
        write_new(output / "failure.json", {"phase": phase,
            "error": {"type": type(exc).__name__, "message": str(exc)}, "working_database_retained": True})
        raise
    finally:
        if book is not None:
            book.close()


def response_error(stage, method, payload, response):
    if method in {"ingest", "link_session"}:
        if not isinstance(response, dict) or response.get("pages") != TURNS_PER_SESSION:
            return "unexpected real page count or response type"
        project, identity = ((payload["project"], payload["session_id"]) if method == "ingest" else payload[:2])
        if response.get("project") != project or response.get("session_id") != identity:
            return "response source identity differs from the request"
        if response.get("skipped") is not (stage == "skip"):
            return "unexpected skip/replacement/relink outcome"
    elif response is not True:
        return "the selected existing source was not deleted"
    return None


def read_json(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def validate_arm(location: Path, round_index: int, arm: str, binding: dict, sequence: list):
    """Validate retained records against the frozen operations, not just counts."""
    require(not (location / "failure.json").exists(), "failed worker cannot be accepted")
    completion = read_json(location / "complete.json")
    require(completion.get("status") == "complete" and completion.get("protocol") == PROTOCOL
            and completion.get("operations") == len(sequence)
            and completion.get("initial_pages") == STAGE_PAGES["ingest"]
            and completion.get("final_pages") == STAGE_PAGES["delete_project"], "incomplete or mismatched arm")
    names = {"identity.json", "identity-after.json", "operations.jsonl", "operation-starts.jsonl",
             *(f"source-{stage}.json" for stage in STAGE_PAGES)}
    hashes = completion.get("evidence_sha256", {})
    require(set(hashes) == names, "missing or extra captured evidence")
    for name in names:
        require(valid_digest(hashes[name]) and hashlib.sha256((location / name).read_bytes()).hexdigest() == hashes[name],
                f"captured evidence hash differs: {name}")
    before, after = read_json(location / "identity.json"), read_json(location / "identity-after.json")
    require(before.get("protocol") == PROTOCOL and before.get("arm") == arm
            and before.get("round") == round_index, "worker identity differs from schedule")
    environment = before.get("environment", {})
    require(environment.get("executable") == binding["executable"]
            and environment.get("prefix") == binding["python_prefix"]
            and environment.get("python") == binding["python"], "worker interpreter differs from coordinator")
    for proof in (before, after):
        require(proof.get("source") == binding["runtimes"][arm], "runtime source changed or belongs to another arm")
        require(proof.get("backend") == binding["backend"], "worker backend differs")
        require(proof.get("protocol_commit") == binding["protocol_commit"]
                and proof.get("protocol_files") == binding["protocol_files"], "worker protocol differs")
        native = proof.get("native")
        if binding["backend"] == "native":
            require(isinstance(native, dict) and isinstance(native.get("path"), str), "missing native binary proof")
            path = Path(native["path"])
            require(str(path.parent) == str(Path(binding["runtime_roots"][arm]) / "src/memory_book")
                    and proof["source"]["native_files"].get(path.name) == native.get("sha256")
                    and valid_digest(native.get("sha256")), "native binary is not bound to the selected runtime")
        else:
            require(native is None, "Python arm loaded a native backend")
    require(before.get("native") == after.get("native"), "native binary changed during worker")
    records = [json.loads(line) for line in (location / "operations.jsonl").read_text().splitlines()]
    starts = [json.loads(line) for line in (location / "operation-starts.jsonl").read_text().splitlines()]
    require(len(records) == len(starts) == len(sequence) + 2, "missing or extra operation/start record")
    require(starts[0] == {"stage": "initialize"} and starts[-1] == {"stage": "close"}
            and records[0].get("stage") == "initialize" and records[-1].get("stage") == "close",
            "initialization or close boundary differs")
    for row in records:
        require("error" not in row and "contract_error" not in row, "failed operation")
        require(type(row.get("wall_ns")) is int and row["wall_ns"] > 0
                and type(row.get("cpu_ns")) is int and row["cpu_ns"] >= 0, "invalid operation timer")
        require(isinstance(row.get("resources"), dict), "missing operation resource record")
    last, revision = {}, 0
    revisions = {}
    for index, (stage, method, payload) in enumerate(sequence):
        labels = {"index": index, "stage": stage, "method": method, "request_sha256": digest(payload)}
        row = records[index + 1]
        require(starts[index + 1] == labels and all(row.get(key) == value for key, value in labels.items()),
                "operation order, method, stage or request differs from frozen workload")
        require(response_error(stage, method, payload, row.get("response")) is None, "operation response contract differs")
        if stage != "skip":
            revision += 1
        if isinstance(row.get("response"), dict):
            require(row["response"].get("revision") == revision, "mutation response has the wrong revision")
        last[stage], revisions[stage] = index, revision
    require({path.name for path in location.glob("source-*.json")} == {f"source-{stage}.json" for stage in STAGE_PAGES},
            "missing or unexpected source stage snapshot")
    snapshots = {}
    for stage, pages in STAGE_PAGES.items():
        row = read_json(location / f"source-{stage}.json")
        require(row.get("stage") == stage and row.get("after_operation") == last[stage]
                and "contract_error" not in row, "source snapshot has the wrong stage boundary")
        snapshot = row["source_snapshot"]
        tables = snapshot.get("tables", {})
        require(set(tables) == set(SOURCE_COLUMNS), "source snapshot omitted stable source or FTS columns")
        for table, summary in tables.items():
            require(type(summary.get("rows")) is int and summary["rows"] >= 0
                    and valid_digest(summary.get("sha256")), f"invalid source digest: {table}")
        require(all(tables[table]["rows"] == pages for table in ("pages", "turns", "pages_fts", "pages_stem_fts"))
                and tables["sessions"]["rows"] == pages // TURNS_PER_SESSION, "source/FTS stage counts differ")
        require(snapshot.get("revision") == revisions[stage]
                and snapshot.get("combined_sha256") == digest(tables)
                and valid_digest(snapshot.get("logical_sources_sha256")), "source revision or digest differs")
        fts = snapshot.get("fts_term_column_statistics", {})
        require(set(fts) == {"pages_fts", "pages_stem_fts"} and all(
            type(item.get("rows")) is int and item["rows"] >= 0 and valid_digest(item.get("sha256"))
            for item in fts.values()), "missing actual FTS term/column statistics")
        snapshots[stage] = snapshot
    return records, snapshots


def summarize(output: Path):
    binding = read_json(output / "binding.json")
    require(binding.get("protocol") == PROTOCOL and binding.get("order") == [list(pair) for pair in ORDER]
            and binding.get("backend") in {"native", "python"}, "run protocol or order differs")
    require(set(binding.get("protocol_files", {})) == set(PROTOCOL_PATHS)
            and all(valid_digest(value) for value in binding["protocol_files"].values()), "incomplete frozen protocol binding")
    frozen = protocol_identity(binding["protocol_commit"])
    require(frozen["protocol_commit"] == binding["protocol_commit"]
            and frozen["protocol_files"] == binding["protocol_files"], "retained protocol is not the frozen source")
    require(set(binding.get("runtimes", {})) == {"baseline", "candidate"}, "missing runtime binding")
    for identity in binding["runtimes"].values():
        require(identity.get("runtime_files") and identity.get("runtime_sha256") == digest(identity["runtime_files"])
                and all(valid_digest(value) for value in identity["runtime_files"].values()), "invalid runtime source binding")
    sequence = operations()
    groups, snapshots, measurements = {}, {}, {}
    for round_index, order in enumerate(ORDER):
        for arm in order:
            location = output / f"round-{round_index:02}-{arm}"
            receipt = read_json(output / f"receipt-{round_index:02}-{arm}.json")
            require(receipt.get("round") == round_index and receipt.get("arm") == arm
                    and receipt.get("returncode") == 0 and "error" not in receipt, "worker did not complete successfully")
            for label in ("stdout", "stderr"):
                log = output / f"round-{round_index:02}-{arm}.{label}"
                require(receipt.get(label + "_sha256") == hashlib.sha256(log.read_bytes()).hexdigest(), "process log hash differs")
            records, stage_snapshots = validate_arm(location, round_index, arm, binding, sequence)
            for row in records:
                key = (arm, row["stage"])
                groups.setdefault(key, []).append(row["wall_ns"] / 1e6)
                measurements.setdefault((round_index, arm, row["stage"]), []).append(row["wall_ns"] / 1e6)
            for stage, snapshot in stage_snapshots.items():
                snapshots[(round_index, arm, stage)] = snapshot
    mismatches = []
    for (round_index, arm, stage), snapshot in snapshots.items():
        if arm == "baseline" and snapshot != snapshots[(round_index, "candidate", stage)]:
            mismatches.append({"round": round_index, "stage": stage})
    if mismatches:
        raise ValueError(f"original-source mismatch: {mismatches}")
    rows = []
    for (arm, stage), values in sorted(groups.items()):
        ordered = sorted(values)
        rows.append({"arm": arm, "stage": stage, "n": len(values),
                     "p50_ms": statistics.median(values),
                     "p95_ms": ordered[max(0, (95 * len(values) + 99) // 100 - 1)],
                     "min_ms": min(values), "max_ms": max(values), "sum_ms": sum(values)})
    ratios = []
    for round_index in range(len(ORDER)):
        for stage in ("initialize", *STAGE_PAGES, "close"):
            base = statistics.median(measurements[(round_index, "baseline", stage)])
            candidate = statistics.median(measurements[(round_index, "candidate", stage)])
            ratios.append({"round": round_index, "stage": stage,
                           "baseline_median_ms": base, "candidate_median_ms": candidate,
                           "candidate_over_baseline": candidate / base})
    return {"protocol": PROTOCOL, "status": "complete", "operations_per_arm": len(operations()),
            "total_operations": len(operations()) * 2 * len(ORDER),
            "source_equal_stage_pairs": len(snapshots) // 2,
            "wall_time_groups": rows, "paired_round_medians": ratios,
            "limits": ["single-host fresh-process API write observations; not physical-storage cold boot",
                       "RSS is process lifetime high water, not per-operation allocation",
                       "source snapshot reads and resource recording occur outside timed calls",
                       "all working databases are retained until every arm and paired source comparison is accepted; failures retain their databases",
                       "FTS comparison includes stored row content and actual term/column document and occurrence counts; no byte-identical shadow-table or complete posting-position claim",
                       "close and its final WAL checkpoint cost are timed separately from mutation calls",
                       "initialization here creates an empty archive; existing-archive migration is measured separately"]}


def cleanup_databases(output: Path):
    """Never delete failed or unaudited working state, including earlier arms."""
    accepted = summarize(output)
    require(read_json(output / "summary.json") == accepted, "no accepted paired summary; databases retained")
    removed = []
    for round_index, order in enumerate(ORDER):
        for arm in order:
            directory = output / f"round-{round_index:02}-{arm}"
            for suffix in ("", "-wal", "-shm"):
                path = directory / ("working.db" + suffix)
                if path.exists():
                    path.unlink()
                    removed.append(str(path.relative_to(output)))
    write_new(output / "working-databases-removed.json", {
        "after_full_paired_acceptance": True, "summary_sha256": hashlib.sha256((output / "summary.json").read_bytes()).hexdigest(),
        "removed": removed, "retained_database_claim": False})


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    frozen = protocol_identity(args.protocol_commit)
    roots = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    identities = {arm: source_identity(root) for arm, root in roots.items()}
    binding = {"protocol": PROTOCOL, **frozen, "runtimes": identities,
               "runtime_roots": {arm: str(root) for arm, root in roots.items()},
               "backend": args.backend, "order": ORDER,
               "executable": interpreter_path(), "python_prefix": sys.prefix, "python": sys.version}
    write_new(output / "binding.json", binding)
    for round_index, order in enumerate(ORDER):
        for arm in order:
            destination = output / f"round-{round_index:02}-{arm}"
            command = [binding["executable"], str(Path(__file__).resolve()), "worker", "--runtime", str(roots[arm]),
                       "--commit", identities[arm]["commit"], "--output", str(destination),
                       "--protocol-commit", frozen["protocol_commit"],
                       "--backend", args.backend, "--arm", arm, "--round", str(round_index)]
            environment = {**os.environ, "PYTHONPATH": str(roots[arm] / "src"),
                           "PYTHONHASHSEED": "0", "MEMORY_BOOK_TEXT_BACKEND": args.backend,
                           "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
            stdout, stderr = output / f"round-{round_index:02}-{arm}.stdout", output / f"round-{round_index:02}-{arm}.stderr"
            write_new(output / f"started-{round_index:02}-{arm}.json", {
                "round": round_index, "arm": arm, "command": command,
                "started_utc": datetime.now(timezone.utc).isoformat()})
            started = time.monotonic()
            try:
                with stdout.open("xb") as out, stderr.open("xb") as err:
                    process = subprocess.run(command, env=environment, cwd=roots[arm], stdout=out, stderr=err, timeout=900)
            except BaseException as exc:
                write_new(output / f"receipt-{round_index:02}-{arm}.json", {
                    "round": round_index, "arm": arm, "returncode": None,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "timeout_seconds": 900 if isinstance(exc, subprocess.TimeoutExpired) else None,
                    "supervisor_wall_seconds": time.monotonic() - started,
                    "stdout_sha256": hashlib.sha256(stdout.read_bytes()).hexdigest() if stdout.exists() else None,
                    "stderr_sha256": hashlib.sha256(stderr.read_bytes()).hexdigest() if stderr.exists() else None})
                raise RuntimeError(f"write-cost worker interrupted: {destination}; journals and databases retained") from exc
            receipt = {"round": round_index, "arm": arm, "returncode": process.returncode,
                       "supervisor_wall_seconds": time.monotonic() - started,
                       "stdout_sha256": hashlib.sha256(stdout.read_bytes()).hexdigest(),
                       "stderr_sha256": hashlib.sha256(stderr.read_bytes()).hexdigest()}
            write_new(output / f"receipt-{round_index:02}-{arm}.json", receipt)
            if process.returncode:
                raise RuntimeError(f"write-cost worker failed: {destination}; original logs retained")
    summary = summarize(output)
    require({arm: source_identity(root) for arm, root in roots.items()} == identities,
            "runtime checkout changed before final acceptance")
    write_new(output / "summary.json", summary)
    cleanup_databases(output)
    print(json.dumps({"status": summary["status"], "output": str(output),
                      "total_operations": summary["total_operations"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    coordinator = commands.add_parser("run")
    coordinator.add_argument("--baseline", required=True, type=Path)
    coordinator.add_argument("--candidate", required=True, type=Path)
    coordinator.add_argument("--protocol-commit", required=True)
    coordinator.add_argument("--output", required=True, type=Path)
    coordinator.add_argument("--backend", choices=("python", "native"), default="native")
    child = commands.add_parser("worker")
    child.add_argument("--runtime", required=True, type=Path)
    child.add_argument("--commit", required=True)
    child.add_argument("--protocol-commit", required=True)
    child.add_argument("--output", required=True, type=Path)
    child.add_argument("--backend", required=True, choices=("python", "native"))
    child.add_argument("--arm", required=True, choices=("baseline", "candidate"))
    child.add_argument("--round", required=True, type=int)
    args = parser.parse_args()
    (run if args.command == "run" else worker)(args)


if __name__ == "__main__":
    main()
