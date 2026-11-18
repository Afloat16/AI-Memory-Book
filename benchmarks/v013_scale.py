"""Run the preregistered v0.13 long-history experiment in isolated processes.

Before formal measurement, commit this file, v013_workload.py, the JSON plan
and test_v013_scale.py, and save that commit remotely. Example (paths explicit)::

    python benchmarks/v013_scale.py describe
    python benchmarks/v013_scale.py run --protocol-commit COMMIT \
      --baseline-root /path/to/baseline --candidate-root /path/to/candidate \
      --candidate-commit COMMIT --backend native --output /path/to/new-attempt

Only ``run`` executes formal queries. Integrity tests and ``describe`` do not.
Every worker has a runtime-specific PYTHONPATH. Arms never overlap, and every
arm starts from a restored baseline-built database, even if a candidate adds
indexes during initialization. Large working snapshots are reproducible and
prunable; original response and timing journals are permanent run evidence.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import time
import traceback

try:
    import resource
except ImportError:  # Pure integrity tests remain importable on Windows.
    resource = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.v013_workload import (SEED, TARGETS, cases, checkpoints, digest,
                                      encoded, sessions, source_for, source_turn)

PLAN_RELATIVE = "benchmarks/experiments/v013-long-history-plan.json"
FROZEN_FILES = (PLAN_RELATIVE, "benchmarks/v013_workload.py",
                "benchmarks/v013_scale.py", "tests/test_v013_scale.py")
SOURCE_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")
HOST_COLUMNS = {"projects": {"created_at", "updated_at"},
                "chapters": {"updated_at"}, "sessions": {"updated_at"}}


def now():
    return datetime.now(timezone.utc).isoformat()


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def append_json(path, value):
    with Path(path).open("ab") as stream:
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def plan():
    value = json.loads((ROOT / PLAN_RELATIVE).read_text(encoding="utf-8"))
    if value["protocol"] != "v013-long-history-scale-1" or value["seed"] != SEED:
        raise ValueError("Unknown frozen protocol/seed")
    if value["measurement"].get("expected_primary_counts") != measurement_counts(value, len(checkpoints())):
        raise ValueError("Registered call counts do not match executable loops")
    return value


def measurement_counts(configuration, checkpoint_count):
    settings = configuration["measurement"]
    queries = {row["id"]: row for row in cases()}
    selected = [queries[name] for name in settings["performance_query_ids"]]
    recall = sum(row["surface"] == "recall" for row in selected)
    directory = len(selected) - recall
    orders = settings["arm_order_by_round"]
    if any(sorted(order) != ["baseline", "candidate"] for order in orders):
        raise ValueError("Every round must include exactly one block per version")
    repetitions = settings["repetitions_per_query_per_round"]
    warm = settings["warm_result_cache_calls_per_cold_call"]
    per_block = repetitions * (recall * (1 + warm) + directory)
    per_checkpoint = per_block * sum(map(len, orders))
    quality = 2 * len(queries)
    return {"checkpoints": checkpoint_count, "arm_blocks_per_checkpoint": sum(map(len, orders)),
            "performance_calls_per_arm_block": per_block, "performance_calls_per_checkpoint": per_checkpoint,
            "quality_calls_per_checkpoint": quality, "performance_calls_total": per_checkpoint * checkpoint_count,
            "quality_calls_total": quality * checkpoint_count,
            "api_measurements_total": (per_checkpoint + quality) * checkpoint_count,
            "cold_samples_per_query_per_arm_per_checkpoint": len(orders) * repetitions,
            "warm_samples_per_query_per_arm_per_checkpoint": len(orders) * repetitions * warm,
            "directory_samples_per_query_per_arm_per_checkpoint": len(orders) * repetitions}


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def runtime_identity(repo, expected=None):
    repo = Path(repo).resolve()
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    if expected is not None and commit != expected:
        raise ValueError(f"Runtime HEAD {commit} differs from bound {expected}")
    status = git(repo, "status", "--porcelain", "--untracked-files=no", "--", "src/memory_book").decode()
    if status:
        raise ValueError("Runtime source is dirty: " + status)
    names = git(repo, "ls-files", "src/memory_book").decode().splitlines()
    unknown_python = sorted(p.relative_to(repo).as_posix() for p in (repo / "src/memory_book").rglob("*.py")
                            if "__pycache__" not in p.parts and p.relative_to(repo).as_posix() not in names)
    if unknown_python:
        raise ValueError("Untracked Python modules are outside the runtime commit: " + ", ".join(unknown_python))
    hashes = {name: file_sha(repo / name) for name in names}
    if not hashes:
        raise ValueError("Runtime source checkout is missing")
    extensions = {p.name: file_sha(p) for pattern in ("_native*.so", "_native*.pyd")
                  for p in (repo / "src/memory_book").glob(pattern)}
    return {"commit": commit, "tracked_runtime_sha256": digest(hashes), "files": hashes,
            "native_extension_files": extensions, "repo_root": str(repo)}


def frozen_identity(commit):
    hashes = {}
    for name in FROZEN_FILES:
        raw = (ROOT / name).read_bytes()
        if raw != git(ROOT, "show", commit + ":" + name):
            raise ValueError("Protocol file differs from committed freeze: " + name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    return {"commit": commit, "files": hashes}


def worker_environment(repo, backend):
    env = os.environ.copy()
    env.update(plan()["measurement"]["runtime_environment"])
    env["PYTHONPATH"] = os.pathsep.join((str(Path(repo).resolve() / "src"), str(ROOT)))
    env["MEMORY_BOOK_TEXT_BACKEND"] = backend
    return env


def load_runtime(repo, backend):
    # Import only inside a fresh worker, after its PYTHONPATH was set by run().
    import memory_book
    from memory_book import MemoryBook, _text_backend
    origin = Path(memory_book.__file__).resolve()
    if not origin.is_relative_to(Path(repo).resolve() / "src"):
        raise ValueError("Imported runtime is outside the requested repo-root")
    if _text_backend.BACKEND_NAME != backend:
        raise ValueError("Requested backend did not load; fallback is not a measurement")
    extension = _text_backend.NATIVE
    return MemoryBook, {"package_file": str(origin), "backend": _text_backend.BACKEND_NAME,
                        "extension_sha256": file_sha(extension.__file__) if extension else None,
                        "extension_file": str(extension.__file__) if extension else None}


def host_identity():
    cpu = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {"platform": platform.platform(), "python": sys.version,
            "sqlite": sqlite3.sqlite_version, "machine": platform.machine(), "cpu": cpu,
            "logical_cpu_count": os.cpu_count(),
            "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "pid": os.getpid()}


def process_resources():
    if resource is None:
        return {"available": False, "reason": "resource module is unavailable on this host"}
    usage = resource.getrusage(resource.RUSAGE_SELF)
    unit = 1 if sys.platform == "darwin" else 1024
    return {"process_lifetime_peak_rss_bytes": int(usage.ru_maxrss * unit),
            "process_user_seconds": usage.ru_utime, "process_system_seconds": usage.ru_stime,
            "minor_page_faults": usage.ru_minflt, "major_page_faults": usage.ru_majflt}


def storage(path, db=None):
    path = Path(path)
    files = {suffix or "main": Path(str(path) + suffix).stat().st_size
             if Path(str(path) + suffix).exists() else 0 for suffix in ("", "-wal", "-shm")}
    result = {"files_bytes": files, "total_file_bytes": sum(files.values()),
              "free_bytes": shutil.disk_usage(path.parent).free}
    if db is not None:
        result.update({key: db.execute("PRAGMA " + key).fetchone()[0]
                       for key in ("page_count", "page_size", "freelist_count")})
        result["schema_indexes"] = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")]
    return result


class ResourceLimit(RuntimeError):
    pass


def enforce_resources(path, limits, *, extra_bytes=0):
    observed = storage(path)
    if observed["free_bytes"] - extra_bytes < limits["minimum_free_bytes"]:
        raise ResourceLimit("Free-space floor would be crossed: " + json.dumps(observed))
    if observed["total_file_bytes"] > limits["maximum_database_bytes"]:
        raise ResourceLimit("Database size limit reached: " + json.dumps(observed))
    return observed


def _hash_rows(rows):
    value = hashlib.sha256()
    count = 0
    for row in rows:
        value.update(encoded(list(row)) + b"\n")
        count += 1
    return {"rows": count, "sha256": value.hexdigest()}


def source_fingerprint(db):
    """Stream original tables; avoid loading the archive into Python memory."""
    tables = {}
    for table in SOURCE_TABLES:
        columns = [r[1] for r in db.execute("PRAGMA table_info(" + table + ")")]
        columns = [c for c in columns if c not in HOST_COLUMNS.get(table, set())]
        # rid is physical placement, intentionally different in the layout control.
        if table == "pages":
            columns.remove("rid")
        sql = "SELECT " + ",".join('"' + c + '"' for c in columns) + " FROM " + table + " ORDER BY id"
        tables[table] = {"columns": columns, **_hash_rows(db.execute(sql))}
    payload, age_invariant, dates = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    for row in db.execute("SELECT project_id,external_id,raw_json FROM sessions ORDER BY project_id,external_id"):
        source = json.loads(row[2])
        payload.update(encoded(source) + b"\n")
        created = source.pop("created_at")
        age_invariant.update(encoded(source) + b"\n")
        dates.update(encoded([row[0], row[1], created]) + b"\n")
    layout = _hash_rows(db.execute("SELECT rid,id,project_id,session_pk FROM pages ORDER BY rid"))
    target_layout = {}
    for target in TARGETS:
        low, high, count = db.execute("SELECT MIN(rid),MAX(rid),COUNT(*) FROM pages WHERE project_id=?",
                                      (target["project"],)).fetchone()
        target_layout[target["project"]] = {"pages": count, "min_rowid": low, "max_rowid": high,
                                           "rowid_density": count / (high - low + 1) if count else None}
    return {"source_tables": tables, "source_tables_sha256": digest(tables),
            "logical_sources_sha256": payload.hexdigest(),
            "age_invariant_sources_sha256": age_invariant.hexdigest(),
            "source_dates_sha256": dates.hexdigest(), "physical_page_layout": layout,
            "page_ids": _hash_rows(db.execute("SELECT id FROM pages ORDER BY id")),
            "target_layout": target_layout}


def answer_projection(response):
    """Evidence-only projection for age controls, without dates/scores/cache timing."""
    return [{"id": hit.get("id"), "text": hit.get("text", hit.get("content", "")),
             "source_refs": [{key: ref.get(key) for key in
                              ("project", "session_id", "turn_index", "start", "end", "turn_start", "turn_end")}
                             for ref in hit.get("source_refs", [])]}
            for hit in response.get("results", [])]


def stable_response(raw):
    if isinstance(raw, dict):
        return {key: stable_response(value) for key, value in raw.items()
                if key not in {"latency_ms", "cache_hit"}}
    if isinstance(raw, list):
        return [stable_response(value) for value in raw]
    return raw


def score(response, case, spec, budget=2400):
    """Validate every excerpt against reconstructed sources before counting gold."""
    errors, references = [], []
    hits = response.get("results", [])
    context = response.get("context", "")
    if len(context) > budget:
        errors.append("context_budget_exceeded")
    for number, hit in enumerate(hits):
        text = hit.get("text", "")
        covered = [False] * len(text)
        if text not in context:
            errors.append(f"hit-{number}:absent_from_context")
        refs = hit.get("source_refs", [])
        if not refs:
            errors.append(f"hit-{number}:missing_source_refs")
        for ref in refs:
            references.append(ref)
            if ref.get("project") != case["project"]:
                errors.append(f"hit-{number}:cross_project_source")
            try:
                original = source_for(spec, ref["project"], ref["session_id"])
                turn = source_turn(original["messages"], ref["turn_index"])
                lo, hi = ref["turn_start"], ref["turn_end"]
                if (type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(turn)
                        or ref.get("end", 0) - ref.get("start", 0) != hi - lo):
                    raise ValueError("invalid source coordinates")
                if ref.get("created_at") != original["created_at"]:
                    raise ValueError("wrong source timestamp")
                fragment = turn[lo:hi]
                start = text.find(fragment)
                if start < 0:
                    raise ValueError("original source slice absent from excerpt")
                for position in range(start, start + len(fragment)):
                    covered[position] = True
            except (KeyError, ValueError, TypeError, IndexError) as exc:
                errors.append(f"hit-{number}:source_mismatch:{exc}")
        if any(not present and not char.isspace() and char != "…"
               for present, char in zip(covered, text)):
            errors.append(f"hit-{number}:unsupported_excerpt_text")
        breadcrumb = hit.get("breadcrumb", [])
        if breadcrumb and breadcrumb[0].get("id") != case["project"]:
            errors.append(f"hit-{number}:cross_project_breadcrumb")
    if case["surface"] == "directory":
        expected_context = "\n\n".join(hit.get("text", "") for hit in hits)
    else:
        blocks = []
        for hit in hits:
            ref = next(iter(hit.get("source_refs", [])), {})
            header = f"[{hit.get('id')}] {ref.get('project')} / {ref.get('session_id')} | {ref.get('created_at')}\n"
            blocks.append(header + hit.get("text", ""))
        expected_context = "\n\n".join(blocks)
    if context != expected_context:
        errors.append("context_not_excerpts_plus_source_citations")

    def rank(required):
        for number, hit in enumerate(hits, 1):
            if required["quote"] not in hit.get("text", "") or required["quote"] not in context:
                continue
            for ref in hit.get("source_refs", []):
                if (ref.get("project"), ref.get("session_id"), ref.get("turn_index")) != (
                        case["project"], required["session_id"], required["turn_index"]):
                    continue
                original = source_for(spec, case["project"], required["session_id"])
                text = source_turn(original["messages"], required["turn_index"])
                lo, hi = ref.get("turn_start"), ref.get("turn_end")
                if type(lo) is int and type(hi) is int and required["quote"] in text[lo:hi]:
                    return number
        return None

    ranks = [rank(item) for item in case["required"]]
    stale = [rank(item) for item in case["stale"]]
    answerable = bool(case["required"])
    # Current-policy evidence is explicitly the first required source. A
    # boundary source ranked first must not count as current-policy-first.
    first = ranks[0] if ranks else None
    stale_first = min((r for r in stale if r is not None), default=None)
    return {"answerable": answerable, "required_spans": len(ranks),
            "covered_spans": sum(r is not None for r in ranks) if not errors else 0,
            "complete": (all(r is not None for r in ranks) and not errors) if answerable else None,
            "required_ranks": ranks, "stale_ranks": stale,
            "current_source_first": (first == 1 and not errors) if case["stale"] else None,
            "stale_before_current": bool(stale_first is not None and (first is None or stale_first < first)),
            "returned_context_for_missing": bool(context) if not answerable else None,
            "source_errors": errors, "context_chars": len(context), "source_refs": references,
            "evidence_projection_sha256": digest(answer_projection(response))}


def page_identity_errors(book, response, project):
    errors = []
    for hit in response.get("results", []):
        row = book.db.execute("SELECT project_id,source_refs FROM pages WHERE id=?", (hit.get("id"),)).fetchone()
        if row is None or row[0] != project:
            errors.append("returned_page_id_missing_or_foreign")
            continue
        originals = {(ref["project"], ref["session_id"], ref["turn_index"])
                     for ref in json.loads(row[1])}
        if any((ref.get("project"), ref.get("session_id"), ref.get("turn_index")) not in originals
               for ref in hit.get("source_refs", [])):
            errors.append("returned_page_id_does_not_own_source_reference")
    return errors


def directory_read(book, query, project, options, trace=None):
    """Bounded discovery then original reads; no access to expected IDs/quotes."""
    trace = {} if trace is None else trace
    trace.update(directory=None, sections=[], reads=[], pending_call="search_directory")
    found = book.search_directory(query, project=project, limit=options["chapter_limit"])
    trace["directory"] = found
    trace["pending_call"] = None
    hits, blocks, used = [], [], 0
    for chapter in found["results"]:
        for section in chapter["sections"][:options["sections_per_chapter"]]:
            trace["pending_call"] = {"surface": "section", "id": section["id"]}
            details = book.section(section["id"], project=project, limit=options["pages_per_section"])
            trace["sections"].append(details)
            trace["pending_call"] = None
            for page in details["pages"]:
                separator = 2 if blocks else 0
                remaining = options["total_original_evidence_budget_chars"] - used - separator
                if remaining <= 0:
                    continue
                trace["pending_call"] = {"surface": "read", "id": page["id"]}
                original = book.read(page["id"], project=project,
                                     limit=min(options["read_limit_chars"], remaining))
                trace["reads"].append(original)
                trace["pending_call"] = None
                blocks.append(original["content"])
                used += separator + len(original["content"])
                hits.append({"id": original["id"], "text": original["content"],
                             "source_refs": original["source_refs"], "breadcrumb": original["breadcrumb"]})
    response = {"context": "\n\n".join(blocks), "results": hits}
    return response, trace


@contextmanager
def deadline(seconds):
    previous = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise TimeoutError(f"Registered soft call deadline of {seconds} seconds exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Recorder:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.observations = self.directory / "observations.jsonl"
        self.raw = self.directory / "responses.jsonl.gz"
        self.events = self.directory / "events.jsonl"
        for path in (self.observations, self.raw, self.events):
            with path.open("xb"):
                pass
        self.sequence = 0

    def event(self, value):
        append_json(self.events, {"at_utc": now(), **value})

    def record(self, observation, raw):
        self.sequence += 1
        observation["sequence"] = self.sequence
        packet = {"sequence": self.sequence, "observation": observation, "original_response": raw}
        # Each record is a complete gzip member. An interrupted next write
        # cannot invalidate the earlier, independently completed records.
        member = gzip.compress(encoded(packet) + b"\n", compresslevel=3, mtime=0)
        with self.raw.open("ab") as stream:
            offset = stream.tell()
            stream.write(member)
            stream.flush()
            os.fsync(stream.fileno())
        observation.update(raw_gzip_offset=offset, raw_gzip_bytes=len(member), raw_sha256=digest(raw))
        append_json(self.observations, observation)


def measure_case(book, case, spec, mode, identity, recorder, configuration):
    recorder.event({"event": "call_started", "case": case["id"], "mode": mode, **identity})
    raw, normalized, error = None, None, None
    if case["surface"] == "directory":
        raw = {}  # Retains every earlier successful API response if a later call fails.
    wall_ns = cpu_ns = None
    try:
        with deadline(configuration["limits"]["call_timeout_seconds"]):
            wall = time.perf_counter_ns()
            cpu = time.process_time_ns()
            try:
                if case["surface"] == "directory":
                    normalized, raw = directory_read(book, case["query"], case["project"], configuration["directory"], trace=raw)
                else:
                    normalized = raw = book.recall(case["query"], project=case["project"],
                        budget_chars=configuration["retrieval"]["budget_chars"],
                        limit=configuration["retrieval"]["limit"], strategy="book", temporal="auto",
                        coverage=False, semantic=False, use_cache=mode != "quality")
            finally:
                cpu_ns, wall_ns = time.process_time_ns() - cpu, time.perf_counter_ns() - wall
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    # All validation, serialization, file I/O and resource inspection is outside
    # the measured API duration. The raw API response is retained unmodified.
    if book.db.in_transaction:
        book.db.execute("ROLLBACK")
    scored = score(normalized, case, spec, configuration["retrieval"]["budget_chars"]) if normalized else None
    if scored is not None:
        page_errors = page_identity_errors(book, normalized, case["project"])
        if page_errors:
            scored["source_errors"].extend(page_errors)
            scored["covered_spans"] = 0
            if scored["answerable"]:
                scored["complete"] = False
            if scored["current_source_first"] is not None:
                scored["current_source_first"] = False
    cache_valid = True
    if case["surface"] == "recall" and normalized is not None:
        if mode == "cold-result-cache":
            cache_valid = normalized.get("cache_hit") is False
        elif mode == "warm-result-cache":
            cache_valid = normalized.get("cache_hit") is True
    observation = {"case": case["id"], "surface": case["surface"], "lifecycle": case["lifecycle"],
                   "mode": mode, **identity, "wall_ns": wall_ns, "process_cpu_ns": cpu_ns,
                   "error": error, "cache_mode_valid": cache_valid, "score": scored,
                   "stable_response_sha256": digest(stable_response(raw)) if raw is not None else None,
                   "resources": process_resources()}
    recorder.record(observation, raw)
    return observation


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize_observations(path):
    grouped = defaultdict(list)
    quality = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            value = json.loads(line)
            if value["mode"] == "quality":
                quality.append({key: value[key] for key in ("case", "surface", "error", "score", "stable_response_sha256")})
            else:
                grouped[value["case"], value["mode"]].append(value)
    timings = []
    for (case_id, mode), samples in sorted(grouped.items()):
        valid = [s for s in samples if s["error"] is None and s["cache_mode_valid"]]
        metric = {}
        for field in ("wall_ns", "process_cpu_ns"):
            values = [s[field] for s in valid]
            metric[field] = {"n": len(values), "p50": statistics.median(values) if values else None,
                             "p95_nearest_rank": percentile(values, .95),
                             "min": min(values) if values else None, "max": max(values) if values else None}
        timings.append({"case": case_id, "mode": mode, "attempted": len(samples),
                        "errors": sum(s["error"] is not None for s in samples),
                        "cache_mode_mismatches": sum(not s["cache_mode_valid"] for s in samples),
                        "incomplete_answerable_outputs": sum(s["score"] is not None and s["score"]["complete"] is False for s in samples),
                        **metric})
    return {"quality": quality, "timings": timings}


def build_worker(args):
    configuration = plan()
    frozen_identity(args.protocol_commit)
    spec = json.loads(args.spec)
    output = Path(args.worker_output)
    output.mkdir(parents=True, exist_ok=False)
    identity = runtime_identity(args.repo_root, args.runtime_commit)
    if digest(identity) != args.runtime_identity_sha256:
        raise ValueError("Builder runtime or native extension changed after binding")
    MemoryBook, imported = load_runtime(args.repo_root, args.backend)
    started, calls, skipped = time.perf_counter(), 0, 0
    ingestion_hash = hashlib.sha256()
    result = {"status": "running", "spec": spec, "imported": imported, "host": host_identity(),
              "started_at_utc": now(), "resume_existing_database": Path(args.database).exists()}
    atomic_json(output / "result.json", result)
    try:
        with MemoryBook(args.database, segmentation="turn", max_page_chars=900,
                        min_page_chars=0, cache_size=128) as book:
            for source in sessions(spec):
                if calls % 16 == 0:
                    enforce_resources(args.database, configuration["limits"])
                if time.perf_counter() - started > configuration["limits"]["build_timeout_seconds"]:
                    raise TimeoutError("Registered build time limit exceeded")
                ingestion_hash.update(encoded(source) + b"\n")
                saved = book.ingest(source)
                if saved["pages"] != len(source["messages"]) // 2:
                    raise AssertionError("Real ingest did not produce one stored page per source turn")
                calls += 1
                skipped += bool(saved["skipped"])
                if calls % 32 == 0:
                    book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    append_json(output / "build-progress.jsonl", {"calls": calls, "skipped": skipped,
                        "elapsed_seconds": time.perf_counter() - started, "last_project": source["project"],
                        "last_session": source["session_id"], "storage": storage(args.database, book.db),
                        "resources": process_resources()})
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            actual = book.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            if actual != spec["total_pages"]:
                raise AssertionError(f"Actual stored pages {actual} differ from {spec['total_pages']}")
            result.update(status="completed", actual_pages=actual,
                          fingerprint=source_fingerprint(book.db), storage=storage(args.database, book.db))
    except Exception as exc:
        result.update(status="incomplete", error={"type": type(exc).__name__, "message": str(exc),
                                                 "traceback": traceback.format_exc()})
    result.update(ingest_calls=calls, skipped_unchanged_sessions=skipped,
                  ingestion_order_sha256=ingestion_hash.hexdigest(), finished_at_utc=now(),
                  elapsed_seconds=time.perf_counter() - started, resources=process_resources())
    atomic_json(output / "result.json", result)
    print(json.dumps({"status": result["status"], "result": str(output / "result.json")}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


def measurement_worker(args):
    configuration = plan()
    frozen_identity(args.protocol_commit)
    spec = json.loads(args.spec)
    output = Path(args.worker_output)
    output.mkdir(parents=True, exist_ok=False)
    identity = runtime_identity(args.repo_root, args.runtime_commit)
    if digest(identity) != args.runtime_identity_sha256:
        raise ValueError("Measurement runtime or native extension changed after binding")
    MemoryBook, imported = load_runtime(args.repo_root, args.backend)
    recorder = Recorder(output)
    result = {"status": "running", "started_at_utc": now(), "runtime": identity,
              "imported": imported, "host": host_identity(), "spec": spec,
              "arm": args.arm, "round": args.round, "quality_included": args.quality}
    atomic_json(output / "result.json", result)
    started = time.perf_counter_ns()
    try:
        with MemoryBook(args.database, segmentation="turn", max_page_chars=900,
                        min_page_chars=0, cache_size=128) as book:
            result["initialization_wall_ns"] = time.perf_counter_ns() - started
            result["storage_before"] = storage(args.database, book.db)
            book.db.execute("DELETE FROM recall_cache")
            selected = {row["id"]: row for row in cases(spec["revision"])}
            if args.quality:
                for case in selected.values():
                    enforce_resources(args.database, configuration["limits"])
                    measure_case(book, case, spec, "quality", {"arm": args.arm, "round": args.round},
                                 recorder, configuration)
            for case_id in configuration["measurement"]["performance_query_ids"]:
                case = selected[case_id]
                for repeat in range(configuration["measurement"]["repetitions_per_query_per_round"]):
                    enforce_resources(args.database, configuration["limits"])
                    call = {"arm": args.arm, "round": args.round, "repetition": repeat}
                    if case["surface"] == "directory":
                        measure_case(book, case, spec, "uncached-directory", call, recorder, configuration)
                        continue
                    book.db.execute("DELETE FROM recall_cache")
                    measure_case(book, case, spec, "cold-result-cache", call, recorder, configuration)
                    for warm in range(configuration["measurement"]["warm_result_cache_calls_per_cold_call"]):
                        measure_case(book, case, spec, "warm-result-cache", {**call, "warm_call": warm},
                                     recorder, configuration)
            result["fingerprint_after"] = source_fingerprint(book.db)
            expected = json.loads(Path(args.expected_fingerprint).read_text())["source_tables_sha256"]
            if result["fingerprint_after"]["source_tables_sha256"] != expected:
                raise AssertionError("Runtime changed original source tables")
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            result.update(status="completed", storage_after=storage(args.database, book.db))
    except Exception as exc:
        result.update(status="incomplete", error={"type": type(exc).__name__, "message": str(exc),
                                                 "traceback": traceback.format_exc()})
    result.update(finished_at_utc=now(), resources=process_resources(),
                  observations=recorder.sequence, summary=summarize_observations(recorder.observations))
    atomic_json(output / "result.json", result)
    print(json.dumps({"status": result["status"], "result": str(output / "result.json")}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


def next_attempt(parent, stem, suffix=""):
    number = 1
    while ((Path(parent) / f"{stem}-attempt{number:03d}{suffix}").exists()
           or (Path(parent) / f"{stem}-attempt{number:03d}{suffix}.partial").exists()):
        number += 1
    return Path(parent) / f"{stem}-attempt{number:03d}{suffix}"


def remove_working(path):
    """Only run-owned reproducible working DB files, never evidence journals."""
    path = Path(path)
    if path.name != "working.sqlite":
        raise ValueError("Refuse to remove a non-working database")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def snapshot_database(database, destination, limits):
    database, destination = Path(database), Path(destination)
    enforce_resources(database, limits, extra_bytes=limits["minimum_snapshot_headroom_bytes"])
    if destination.exists():
        raise FileExistsError("Snapshot evidence already exists")
    temporary = destination.with_suffix(destination.suffix + ".partial")
    started = time.perf_counter_ns()
    with database.open("rb") as source, temporary.open("xb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", compresslevel=3, mtime=0) as archive:
            while chunk := source.read(4 * 1024 * 1024):
                enforce_resources(database, limits)
                archive.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, destination)
    return {"path": str(destination), "sha256": file_sha(destination),
            "compressed_bytes": destination.stat().st_size,
            "database_sha256": file_sha(database), "database_bytes": database.stat().st_size,
            "compression_wall_ns": time.perf_counter_ns() - started, "pruned": False}


def restore_snapshot(snapshot, database, limits):
    database = Path(database)
    if database.exists():
        raise FileExistsError("Restoration requires a fresh working database")
    source_path = Path(snapshot["path"])
    if file_sha(source_path) != snapshot["sha256"]:
        raise ValueError("Original compressed snapshot hash differs")
    enforce_resources(database, limits, extra_bytes=snapshot["database_bytes"])
    started = time.perf_counter_ns()
    with gzip.open(source_path, "rb") as source, database.open("xb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)
        output.flush()
        os.fsync(output.fileno())
    if database.stat().st_size != snapshot["database_bytes"] or file_sha(database) != snapshot["database_sha256"]:
        raise ValueError("Restored working database is not byte-identical")
    return {"restoration_wall_ns": time.perf_counter_ns() - started,
            "restored_database_sha256": snapshot["database_sha256"],
            "restored_database_bytes": snapshot["database_bytes"]}


def invoke_worker(command, repo, backend, timeout, directory, lock_fd):
    directory = Path(directory)
    stdout_path = directory.with_name(directory.name + "-stdout.jsonl")
    stderr_path = directory.with_name(directory.name + "-stderr.log")
    started = time.perf_counter_ns()
    timed_out = False
    with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
        process = subprocess.Popen(command, env=worker_environment(repo, backend),
                                   cwd=str(ROOT), stdout=out, stderr=err, pass_fds=(lock_fd,))
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            code = process.wait()
        except BaseException:
            process.kill()
            process.wait()
            raise
    result_path = directory / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {"status": "worker_did_not_finish_initialization"}
    return {"returncode": code, "timed_out": timed_out,
            "subprocess_wall_ns": time.perf_counter_ns() - started,
            "result_path": str(result_path), "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path), "result": result,
            "complete": code == 0 and not timed_out and result.get("status") == "completed"}


def quality_totals(rows):
    totals = {}
    for surface in ("recall", "directory"):
        group = [row for row in rows if row["surface"] == surface]
        scored = [row["score"] for row in group if row["score"] is not None]
        totals[surface] = {"queries": len(group), "errors": sum(row["error"] is not None for row in group),
            "answerable": sum(row["answerable"] for row in scored),
            "complete": sum(row["complete"] is True for row in scored),
            "required_spans": sum(row["required_spans"] for row in scored),
            "covered_spans": sum(row["covered_spans"] for row in scored),
            "source_error_outputs": sum(bool(row["source_errors"]) for row in scored),
            "current_first_eligible": sum(row["current_source_first"] is not None for row in scored),
            "current_source_first": sum(row["current_source_first"] is True for row in scored),
            "stale_before_current": sum(row["stale_before_current"] for row in scored),
            "missing_queries": sum(not row["answerable"] for row in scored),
            "returned_context_for_missing": sum(row["returned_context_for_missing"] is True for row in scored)}
    return totals


def checkpoint_summary(stage):
    observations = defaultdict(list)
    quality = {}
    by_round = {}
    accepted_slots, attempts = set(), []
    for block in stage.get("blocks", []):
        if "execution" not in block:
            continue
        result = block["execution"].get("result", {})
        obs_path = Path(block["execution"]["result_path"]).parent / "observations.jsonl"
        recorded, unreadable = [], []
        if obs_path.exists():
            with obs_path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    try:
                        recorded.append(json.loads(line))
                    except json.JSONDecodeError:
                        unreadable.append({"line": line_number, "sha256": hashlib.sha256(line.encode()).hexdigest()})
        attempts.append({"round": block["round"], "arm": block["arm"],
            "result_path": block["execution"]["result_path"], "completed": block["execution"]["complete"],
            "observations_retained": len(recorded), "unreadable_observation_lines": unreadable,
            "recorded_call_errors": sum(r.get("error") is not None for r in recorded),
            "timed_out": block["execution"].get("timed_out", False),
            "included_in_fixed_sample_statistics": block["execution"]["complete"]})
        if not block["execution"]["complete"]:
            continue
        slot = block["round"], block["arm"]
        if slot in accepted_slots:
            raise AssertionError("More than one completed block for the same registered round/arm")
        if unreadable:
            raise AssertionError("A completed block has malformed original observations")
        accepted_slots.add(slot)
        if result.get("summary", {}).get("quality"):
            quality[block["arm"]] = result["summary"]["quality"]
        for row in recorded:
            if row["mode"] != "quality":
                observations[block["arm"], row["case"], row["mode"]].append(row)
        for row in result.get("summary", {}).get("timings", []):
            by_round[block["round"], block["arm"], row["case"], row["mode"]] = row
    timing_rows = []
    for (arm, case_id, mode), rows in sorted(observations.items()):
        valid = [r for r in rows if r["error"] is None and r["cache_mode_valid"]]
        values = {field: [r[field] for r in valid] for field in ("wall_ns", "process_cpu_ns")}
        timing_rows.append({"arm": arm, "case": case_id, "mode": mode, "attempted": len(rows),
            "errors": sum(r["error"] is not None for r in rows),
            "cache_mode_mismatches": sum(not r["cache_mode_valid"] for r in rows),
            **{field: {"n": len(numbers), "p50": statistics.median(numbers) if numbers else None,
                       "p95_nearest_rank": percentile(numbers, .95), "min": min(numbers) if numbers else None,
                       "max": max(numbers) if numbers else None} for field, numbers in values.items()}})
    ratios = []
    for (round_number, arm, case_id, mode), base in sorted(by_round.items()):
        if arm != "baseline":
            continue
        candidate = by_round.get((round_number, "candidate", case_id, mode))
        if candidate:
            settings = plan()["measurement"]
            expected_n = settings["repetitions_per_query_per_round"] * (
                settings["warm_result_cache_calls_per_cold_call"] if mode == "warm-result-cache" else 1)
            eligible = all(base[field]["n"] == candidate[field]["n"] == expected_n
                           for field in ("wall_ns", "process_cpu_ns"))
            ratios.append({"round": round_number, "case": case_id, "mode": mode,
                "eligible_equal_complete_samples": eligible,
                "baseline_valid_samples": base["wall_ns"]["n"],
                "candidate_valid_samples": candidate["wall_ns"]["n"],
                **{field + "_candidate_over_baseline_p50":
                   candidate[field]["p50"] / base[field]["p50"]
                   if eligible and candidate[field]["p50"] is not None and base[field]["p50"] else None
                   for field in ("wall_ns", "process_cpu_ns")}})
    changed = []
    if set(quality) == {"baseline", "candidate"}:
        base = {row["case"]: row for row in quality["baseline"]}
        for row in quality["candidate"]:
            old = base[row["case"]]
            if old["stable_response_sha256"] != row["stable_response_sha256"]:
                changed.append({"case": row["case"], "baseline_sha256": old["stable_response_sha256"],
                                "candidate_sha256": row["stable_response_sha256"],
                                "baseline_score": old["score"], "candidate_score": row["score"]})
    return {"quality": {arm: quality_totals(rows) for arm, rows in quality.items()},
            "quality_case_records": quality, "changed_quality_outputs": changed,
            "timing": timing_rows, "paired_round_ratios": ratios, "all_attempts": attempts,
            "interpretation": "Measured synthetic workload only. Quality failures remain failures regardless of latency; complete per-query/arm p95 uses 30 cold/directory or 90 warm samples. These are single-host empirical quantiles, not universal service guarantees."}


def check_control(spec, fingerprint, stages):
    if spec["axis"] == "age" and spec["shift_days"]:
        original = stages["age-reference-1024"]["build"]["result"]["fingerprint"]
        matched = all(fingerprint[key] == original[key]
                      for key in ("age_invariant_sources_sha256", "physical_page_layout", "page_ids"))
        if not matched:
            raise AssertionError("Age control changed content, IDs or ingestion layout")
        return {"age_only_source_control": True, "shift_days": spec["shift_days"]}
    if spec["axis"] == "layout":
        original = stages["own-100000"]["build"]["result"]["fingerprint"]
        if any(fingerprint[key] != original[key] for key in ("logical_sources_sha256", "page_ids")):
            raise AssertionError("Layout control changed logical sources or page IDs")
        if fingerprint["physical_page_layout"] == original["physical_page_layout"]:
            raise AssertionError("Layout control did not change physical insertion order")
        return {"same_logical_sources": True, "same_page_ids": True, "different_physical_layout": True}
    return {}


def control_output_changes(stage, reference):
    output = {}
    current = stage["summary"]["quality_case_records"]
    original = reference["summary"]["quality_case_records"]
    for arm in sorted(set(current) & set(original)):
        earlier = {row["case"]: row for row in original[arm]}
        changes = []
        for row in current[arm]:
            old = earlier[row["case"]]
            before = old["score"]["evidence_projection_sha256"] if old["score"] else None
            after = row["score"]["evidence_projection_sha256"] if row["score"] else None
            if before != after:
                changes.append({"case": row["case"], "before_sha256": before, "after_sha256": after,
                                "before_score": old["score"], "after_score": row["score"]})
        output[arm] = {"compared_cases": len(current[arm]), "changed_evidence_projections": changes}
    return output


def pending_cells(manifest, specifications):
    missing = []
    orders = plan()["measurement"]["arm_order_by_round"]
    for spec in specifications:
        stage = manifest["stages"].get(spec["id"], {})
        complete = {(b["round"], b["arm"]) for b in stage.get("blocks", [])
                    if b.get("execution", {}).get("complete")}
        for round_number, order in enumerate(orders):
            for arm in order:
                if (round_number, arm) not in complete:
                    missing.append({"checkpoint": spec["id"], "round": round_number, "arm": arm})
    return missing


def run(args):
    if os.name != "posix" or resource is None or not hasattr(signal, "SIGALRM"):
        raise RuntimeError("Formal timing runner requires a POSIX host with resource and SIGALRM; no fallback measurements")
    configuration = plan()
    out = Path(args.output).resolve()
    if args.resume:
        if not (out / "manifest.json").is_file():
            raise ValueError("Resume requires this attempt's original manifest")
    else:
        out.mkdir(parents=True, exist_ok=False)
    # POSIX lock prevents this runner's own arm/builder processes from overlap
    # with another invocation. It does not assert an otherwise idle host.
    import fcntl
    lock = (out / "run.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sources = {"baseline": runtime_identity(args.baseline_root, configuration["baseline_commit"]),
               "candidate": runtime_identity(args.candidate_root, args.candidate_commit)}
    binding = {"protocol": frozen_identity(args.protocol_commit), "runtimes": sources,
               "profile": args.profile, "backend": args.backend, "python": str(Path(args.python).resolve())}
    manifest_path = out / "manifest.json"
    if args.resume:
        manifest = json.loads(manifest_path.read_text())
        if manifest["binding"] != binding:
            raise ValueError("Resume would change frozen runtime/protocol/profile identity")
    else:
        manifest = {"protocol": configuration["protocol"], "binding": binding, "started_at_utc": now(),
                    "status": "running", "host": host_identity(), "stages": {}, "interruptions": []}
    specifications = checkpoints(args.profile)
    working = out / "working.sqlite"
    start = time.monotonic()
    atomic_json(manifest_path, manifest)
    try:
        for spec in specifications:
            if time.monotonic() - start > configuration["limits"]["run_timeout_seconds"]:
                raise TimeoutError("Registered wall-time limit for this invocation reached")
            stage = manifest["stages"].setdefault(spec["id"], {"spec": spec, "blocks": []})
            if stage.get("status") == "completed":
                continue
            directory = out / spec["id"]
            directory.mkdir(exist_ok=True)
            print(json.dumps({"event": "checkpoint_started", "checkpoint": spec["id"], "pages": spec["total_pages"]}), flush=True)
            if "snapshot" not in stage:
                # Interrupted build DBs are reused only for that exact checkpoint.
                resume_build = manifest.get("working_owner") == {"stage": spec["id"], "role": "builder"} and working.exists()
                if not resume_build:
                    remove_working(working)
                    if spec["parent"] is not None:
                        restore_snapshot(manifest["stages"][spec["parent"]]["snapshot"], working, configuration["limits"])
                manifest["working_owner"] = {"stage": spec["id"], "role": "builder"}
                atomic_json(manifest_path, manifest)
                attempt = next_attempt(directory, "build")
                command = [args.python, str(Path(__file__).resolve()), "worker-build", "--repo-root", args.baseline_root,
                    "--runtime-commit", sources["baseline"]["commit"], "--backend", args.backend,
                    "--database", str(working), "--spec", json.dumps(spec), "--worker-output", str(attempt),
                    "--protocol-commit", args.protocol_commit,
                    "--runtime-identity-sha256", digest(sources["baseline"])]
                execution = invoke_worker(command, args.baseline_root, args.backend,
                    min(configuration["limits"]["build_timeout_seconds"] + 120,
                        max(1, configuration["limits"]["run_timeout_seconds"] - (time.monotonic() - start))),
                    attempt, lock.fileno())
                stage.setdefault("build_attempts", []).append(execution)
                stage["build"] = execution
                atomic_json(manifest_path, manifest)
                if not execution["complete"]:
                    raise RuntimeError("Build incomplete; retained raw checkpoint: " + spec["id"])
                fingerprint = execution["result"]["fingerprint"]
                stage["control_checks"] = check_control(spec, fingerprint, manifest["stages"])
                atomic_json(directory / "fingerprint.json", fingerprint)
                snap_path = next_attempt(directory, "source", ".sqlite.gz")
                stage["snapshot"] = snapshot_database(working, snap_path, configuration["limits"])
                remove_working(working)
                manifest["working_owner"] = None
                atomic_json(manifest_path, manifest)
            for round_number, order in enumerate(configuration["measurement"]["arm_order_by_round"]):
                for arm in order:
                    if any(b["round"] == round_number and b["arm"] == arm and b.get("execution", {}).get("complete")
                           for b in stage["blocks"]):
                        continue
                    if time.monotonic() - start > configuration["limits"]["run_timeout_seconds"]:
                        raise TimeoutError("Registered wall-time limit for this invocation reached")
                    remove_working(working)
                    restoration = restore_snapshot(stage["snapshot"], working, configuration["limits"])
                    manifest["working_owner"] = {"stage": spec["id"], "role": "measurement", "round": round_number, "arm": arm}
                    atomic_json(manifest_path, manifest)
                    attempt = next_attempt(directory, f"round{round_number}-{arm}")
                    repo = args.baseline_root if arm == "baseline" else args.candidate_root
                    command = [args.python, str(Path(__file__).resolve()), "worker-measure", "--repo-root", repo,
                        "--runtime-commit", sources[arm]["commit"], "--backend", args.backend,
                        "--database", str(working), "--spec", json.dumps(spec), "--worker-output", str(attempt),
                        "--expected-fingerprint", str(directory / "fingerprint.json"), "--arm", arm, "--round", str(round_number),
                        "--protocol-commit", args.protocol_commit,
                        "--runtime-identity-sha256", digest(sources[arm])]
                    if round_number == 0:
                        command.append("--quality")
                    execution = invoke_worker(command, repo, args.backend,
                        min(configuration["limits"]["worker_timeout_seconds"],
                            max(1, configuration["limits"]["run_timeout_seconds"] - (time.monotonic() - start))),
                        attempt, lock.fileno())
                    stage["blocks"].append({"round": round_number, "arm": arm,
                                            "restoration": restoration, "execution": execution})
                    remove_working(working)
                    manifest["working_owner"] = None
                    stage["summary"] = checkpoint_summary(stage)
                    atomic_json(directory / "summary.json", stage["summary"])
                    atomic_json(manifest_path, manifest)
                    print(json.dumps({"event": "arm_finished", "checkpoint": spec["id"], "round": round_number,
                                      "arm": arm, "completed": execution["complete"]}), flush=True)
                    if not execution["complete"]:
                        raise RuntimeError("Arm incomplete; partial observations retained")
            stage["status"] = "completed"
            stage["finished_at_utc"] = now()
            if spec["axis"] == "layout" or (spec["axis"] == "age" and spec["shift_days"]):
                reference = "own-100000" if spec["axis"] == "layout" else "age-reference-1024"
                stage["control_output_changes"] = control_output_changes(stage, manifest["stages"][reference])
            # Do not retain multiple large DBs. Original result journals, hashes
            # and the deterministic source specification always remain.
            future_parents = {s["parent"] for s in specifications[specifications.index(spec) + 1:]}
            for prior_id, prior in manifest["stages"].items():
                snapshot = prior.get("snapshot")
                if (snapshot and not snapshot["pruned"] and prior_id not in future_parents
                        and prior_id != spec["id"]):
                    Path(snapshot["path"]).unlink()
                    snapshot.update(pruned=True, pruned_at_utc=now(),
                                    pruning_reason="All dependent checkpoints and original observations saved; deterministic rebuild remains available")
            atomic_json(manifest_path, manifest)
        manifest["status"] = "measurements_completed"
    except BaseException as exc:
        manifest["status"] = "incomplete"
        manifest["interruptions"].append({"at_utc": now(), "type": type(exc).__name__,
                                          "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        manifest["unexecuted_or_incomplete_cells"] = pending_cells(manifest, specifications)
        attached = set()
        for stage in manifest["stages"].values():
            attached.update(attempt["result_path"] for attempt in stage.get("build_attempts", []))
            attached.update(block["execution"]["result_path"] for block in stage.get("blocks", []))
        manifest["unattached_attempt_directories"] = [str(p.parent) for p in sorted(out.glob("*/*-attempt*/result.json"))
                                                      if str(p) not in attached]
        manifest["last_saved_at_utc"] = now()
        atomic_json(manifest_path, manifest)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path),
                      "unexecuted_or_incomplete_cells": len(manifest["unexecuted_or_incomplete_cells"])}), flush=True)
    return 0 if manifest["status"] == "measurements_completed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("describe", help="Print the frozen matrix without importing a runtime or executing queries")
    command = sub.add_parser("run")
    command.add_argument("--protocol-commit", required=True)
    command.add_argument("--baseline-root", required=True)
    command.add_argument("--candidate-root", required=True)
    command.add_argument("--candidate-commit", required=True)
    command.add_argument("--backend", choices=("native", "python"), default="native")
    command.add_argument("--profile", choices=("main", "expanded"), default="main")
    command.add_argument("--output", required=True)
    command.add_argument("--python", default=sys.executable)
    command.add_argument("--resume", action="store_true")
    for name in ("worker-build", "worker-measure"):
        worker = sub.add_parser(name, help=argparse.SUPPRESS)
        for option in ("repo-root", "runtime-commit", "database", "spec", "worker-output", "protocol-commit", "runtime-identity-sha256"):
            worker.add_argument("--" + option, required=True)
        worker.add_argument("--backend", choices=("native", "python"), required=True)
        if name == "worker-measure":
            worker.add_argument("--expected-fingerprint", required=True)
            worker.add_argument("--arm", choices=("baseline", "candidate"), required=True)
            worker.add_argument("--round", type=int, required=True)
            worker.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    if args.action == "describe":
        configuration = plan()
        print(json.dumps({"protocol": configuration["protocol"], "checkpoints": checkpoints(),
                          "queries": len(cases()), "recall_queries": sum(c["surface"] == "recall" for c in cases()),
                          "directory_queries": sum(c["surface"] == "directory" for c in cases()),
                          "performance_query_ids": configuration["measurement"]["performance_query_ids"],
                          "derived_main_call_counts": measurement_counts(configuration, len(checkpoints())),
                          "requires_protocol_commit_before_run": True}, ensure_ascii=False, indent=2))
        return 0
    return {"run": run, "worker-build": build_worker, "worker-measure": measurement_worker}[args.action](args)


if __name__ == "__main__":
    raise SystemExit(main())

