"""One registered historical resource diagnostic; no replacement scoring run.

The observer lives outside each fresh worker. Product workers use only the
standard library and the pinned Book runtime; the evaluator has its own worker.
Every worker intent and its source-free traces are committed before advancing.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/round5-resource-plan.json"
SCRIPT = "scripts/round5_resource_diagnostic.py"
TRIGGER = "refs/heads/ci/v033-round5-resource-diagnostic"
REPOSITORY = "Afloat16/AI-Memory-Book"
ORDER = (("v031", "v032"), ("v032", "v031"), ("v032", "v031"), ("v031", "v032"))
SOURCES = {
    "v031": {"commit": "7b7a5d7336b9350a128f5e0a888811b1b3015e68", "version": "0.3.1",
        "runtime_sha256": "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46"},
    "v032": {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82", "version": "0.3.2",
        "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"},
}


class DiagnosticError(ValueError):
    """Only source-free, predefined diagnostic checks use this error type."""


def require(value, message):
    if not value:
        raise DiagnosticError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_normalized_inputs(sessions, queries, frozen):
    """Check against the once-recorded preparation identity; never rebind it."""
    require(file_hash(sessions) == frozen["sessions_sha256"]
        and file_hash(queries) == frozen["queries_sha256"],
        "Normalized private input differs from its original preparation identity")


def download_verified(url, destination, expected_hash, expected_bytes):
    from urllib.request import Request, urlopen
    require(not destination.exists(), "Preserve prior diagnostic downloads")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    require(not temporary.exists(), "Preserve interrupted download")
    size, hasher = 0, hashlib.sha256()
    request = Request(url, headers={"User-Agent": "AI-Memory-Book-registered-resource-diagnostic"})
    with urlopen(request, timeout=90) as response, temporary.open("xb") as stream:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            size += len(block)
            require(size <= expected_bytes, "Artifact exceeds its frozen size")
            hasher.update(block)
            stream.write(block)
    require(size == expected_bytes and hasher.hexdigest() == expected_hash, "Downloaded artifact differs from its frozen identity")
    temporary.replace(destination)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(canonical(value) + b"\n")
    temporary.replace(path)


def actions_identity():
    run, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == TRIGGER and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and run.isdigit() and attempt == "1", "Require the registered first-attempt hosted push")
    return run + "-" + attempt


def validate_plan(plan):
    require(plan["schema_version"] == 1 and plan["protocol"] == "round5-historical-resource-attribution-v1",
            "Unregistered resource protocol")
    require(plan["sources"] == SOURCES and plan["product"]["engine_order"] == [list(x) for x in ORDER],
            "Source/order identity changed")
    require(plan["product"]["workers"] == 8 and plan["product"]["calls_per_worker"] == 32
        and plan["product"]["total_recall_calls"] == 256 and plan["corpus"]["query_count"] == 32,
        "Registered call counts changed")
    require(plan["product"]["budget_chars"] == 100000 and plan["product"]["limit"] == 5
        and plan["product"]["cache_size"] == 0 and plan["product"]["use_cache"] is False
        and plan["product"]["semantic"] is False and plan["product"]["coverage"] is False,
        "Registered product route changed")
    require(plan["sampling"]["target_interval_ms"] == 20 and plan["execution"]["trigger"] == TRIGGER,
            "Registered observer/trigger changed")


def selected_ids(manifest, plan):
    ids = manifest["selected_ids"]
    require(len(ids) == len(set(ids)) == 256, "Require the entire old round-four ID set")
    prefix = plan["corpus"]["selection_prefix"]
    chosen = sorted(ids, key=lambda value: (hashlib.sha256((prefix + value).encode()).hexdigest(), value))[:32]
    require(digest(chosen) == plan["corpus"]["selected_ids_sha256"], "Registered old-ID subset changed")
    return chosen


def parse_kib_fields(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1].isdigit() and fields[2] == "kB":
            result[fields[0].removesuffix(":")] = int(fields[1]) * 1024
    return result


def parse_stat(text):
    """Linux comm may contain spaces and parentheses; fields after its last ')' are stable."""
    close = text.rfind(")")
    require(close >= 0, "Invalid proc stat")
    fields = text[close + 1:].split()
    require(len(fields) >= 20, "Truncated proc stat")
    return {"ppid": int(fields[1]), "start_ticks": int(fields[19])}


def process_record(pid, proc=Path("/proc")):
    path = proc / str(pid)
    try:
        before = parse_stat((path / "stat").read_text())
        status = parse_kib_fields((path / "status").read_text())
        if "VmRSS" not in status:
            return None
        comm = (path / "comm").read_text().strip()
        role = "git" if comm == "git" else "python" if comm.startswith("python") else "other"
        try:
            detail = parse_kib_fields((path / "smaps_rollup").read_text())
            pss = detail.get("Pss")
            private = (sum(detail.get(key, 0) for key in ("Private_Clean", "Private_Dirty", "Private_Hugetlb"))
                       if "Private_Clean" in detail and "Private_Dirty" in detail else None)
            unavailable = None if pss is not None else "missing_pss_field"
        except OSError as error:
            pss = private = None
            unavailable = "permission_denied" if error.errno in (1, 13) else "process_exited_or_unreadable"
        after = parse_stat((path / "stat").read_text())
        if before != after:
            return None
        return {"pid": pid, **after, "comm_role": role, "rss_bytes": status["VmRSS"],
                "pss_bytes": pss, "private_bytes": private, "pss_unavailable_reason": unavailable}
    except (OSError, ValueError, IndexError):
        return None


def tree_sample(pid, proc=Path("/proc"), root_start_ticks=None):
    started = time.monotonic_ns()
    pending, seen, records, errors = [(pid, None)], set(), [], []
    def discovery_error(current, operation, reason, tid=None):
        errors.append({"pid": current, "tid": tid, "operation": operation, "reason": reason})
    while pending:
        current, parent = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        record = process_record(current, proc)
        if record is None:
            discovery_error(current, "process_record", "unreadable_or_changed_identity")
            continue
        if ((parent is not None and record["ppid"] != parent)
                or (current == pid and root_start_ticks is not None and record["start_ticks"] != root_start_ticks)):
            discovery_error(current, "process_identity", "parent_or_start_identity_changed")
            continue
        records.append(record)
        try:
            if parse_stat((proc / str(current) / "stat").read_text())["start_ticks"] != record["start_ticks"]:
                discovery_error(current, "post_record_identity", "start_identity_changed")
                continue
        except (OSError, ValueError, IndexError) as error:
            discovery_error(current, "post_record_identity", type(error).__name__)
            continue
        try:
            threads = list((proc / str(current) / "task").iterdir())
        except OSError as error:
            discovery_error(current, "task_enumeration", type(error).__name__)
            continue
        if not threads:
            discovery_error(current, "task_enumeration", "empty_task_directory")
        for thread in threads:
            try:
                children = [int(value) for value in (thread / "children").read_text().split()]
                require(all(value > 0 for value in children), "Invalid child PID")
                pending.extend((value, current) for value in children)
            except (OSError, ValueError) as error:
                discovery_error(current, "thread_children", type(error).__name__, thread.name)
    records.sort(key=lambda value: value["pid"])
    root = next((record for record in records if record["pid"] == pid), None)
    complete = not errors and len(records) == len(seen)
    all_pss = bool(records) and complete and all(record["pss_bytes"] is not None for record in records)
    return {"started_monotonic_ns": started, "finished_monotonic_ns": time.monotonic_ns(),
        "enumerated_pids": sorted(seen), "processes": records,
        "discovery_complete": complete, "discovery_errors": errors,
        "root_pid": pid, "root_rss_bytes": root["rss_bytes"] if root else None,
        "root_pss_bytes": root["pss_bytes"] if root else None,
        "tree_rss_bytes": sum(record["rss_bytes"] for record in records) if records else None,
        "descendant_rss_bytes": sum(record["rss_bytes"] for record in records if record["pid"] != pid),
        "tree_pss_bytes": sum(record["pss_bytes"] for record in records) if all_pss else None,
        "pss_complete": all_pss}


def phase_at(sample, events):
    if sample.get("boundary"):
        return sample["phase"]
    start, end = sample["started_monotonic_ns"], sample["finished_monotonic_ns"]
    markers = [event for event in events if event["event"] in {"phase_start", "phase_end"}]
    if any(start < event["monotonic_ns"] <= end for event in markers):
        return "transition"
    prior = [event for event in markers if event["monotonic_ns"] <= start]
    if not prior:
        return "spawn"
    last = prior[-1]
    return last["phase"] if last["event"] == "phase_start" else "between_phases"


def summarize_trace(path, events):
    phases = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for sequence, line in enumerate(stream):
            sample = json.loads(line)
            phase = phase_at(sample, events)
            entry = phases.setdefault(phase, {"samples": 0, "root_unreadable": 0, "incomplete_discovery_samples": 0,
                "complete_pss_samples": 0, "max_observed_processes": 0, "peaks": {}})
            entry["samples"] += 1
            entry["root_unreadable"] += sample["root_rss_bytes"] is None
            entry["incomplete_discovery_samples"] += not sample.get("discovery_complete", True)
            entry["complete_pss_samples"] += sample["pss_complete"]
            entry["max_observed_processes"] = max(entry["max_observed_processes"], len(sample["processes"]))
            for metric in ("root_rss_bytes", "root_pss_bytes", "tree_rss_bytes", "descendant_rss_bytes", "tree_pss_bytes"):
                value = sample[metric]
                if value is not None and (metric not in entry["peaks"] or value > entry["peaks"][metric]["bytes"]):
                    entry["peaks"][metric] = {"bytes": value, "sample_index": sequence,
                        "processes": sample["processes"], "boundary": sample.get("boundary")}
    return phases


def validate_events(events, phases, product, plan):
    expected = plan["product" if product else "evaluator_only"]["phases"]
    markers = [(event["event"], event.get("phase")) for event in events if event["event"].startswith("phase_")]
    require(markers == [(kind, phase) for phase in expected for kind in ("phase_start", "phase_end")],
            "Missing, reordered or unfinished phase")
    for phase in expected:
        require(phase in phases and phases[phase]["samples"] >= 2 and phases[phase]["root_unreadable"] == 0,
                "A registered phase lacks readable root RSS/boundary samples")
    starts = [event["id"] for event in events if event["event"] == "query_start"]
    finished = [event for event in events if event["event"] == "query_finish"]
    require(len(starts) == len(finished) == (32 if product else 0) and starts == [row["id"] for row in finished],
            "Incomplete or repeated recall")
    require(len(set(starts)) == len(starts) and len([event for event in events if event["event"] == "done"]) == 1,
            "Repeated query or missing worker completion")
    require(events[-1]["event"] == "done" and not any(event["event"] == "failed" for event in events),
            "Worker reports a failure or post-completion event")
    query_events = [(event["event"], event["id"]) for event in events if event["event"].startswith("query_")]
    require(query_events == [(kind, identity) for identity in starts for kind in ("query_start", "query_finish")],
            "Unpaired query intent/completion")
    current = None
    for event in events:
        if event["event"] == "phase_start":
            current = event["phase"]
        elif event["event"] == "phase_end":
            current = None
        elif event["event"].startswith("query_"):
            require(current == "product_queries", "Recall event outside its registered phase")
    require(all(re.fullmatch("[0-9a-f]{64}", row.get("payload_sha256", "")) for row in finished),
            "Missing complete-output identity")
    return finished


def emit(kind, **values):
    print(json.dumps({"event": kind, "monotonic_ns": time.monotonic_ns(), "pid": os.getpid(), **values}), flush=True)


def worker_high_water():
    import resource  # Hosted workers are Linux; offline fixtures never call this.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


@contextmanager
def phase(name):
    # Boundary acknowledgements make even a sub-20ms close phase observable.
    # They are explicit pauses, not latency samples or allocator interventions.
    emit("phase_start", phase=name)
    require(sys.stdin.readline() == "continue\n", "Observer lost before phase")
    try:
        yield
    finally:
        emit("phase_end", phase=name)
        require(sys.stdin.readline() == "continue\n", "Observer lost after phase")


def worker_guard(args):
    actions_identity()
    require(re.fullmatch("[0-9a-f]{40}", args.claim or "")
        and os.environ.get("ROUND5_RESOURCE_CLAIM") == args.claim
        and os.environ.get("ROUND5_RESOURCE_WORKER") == args.name, "Worker lacks its controller identity")


def product_worker(args):
    worker_guard(args)
    with phase("product_input_verification"):
        verify_normalized_inputs(args.sessions, args.queries,
            {"sessions_sha256": args.sessions_sha256, "queries_sha256": args.queries_sha256})
        queries = [json.loads(line) for line in args.queries.read_text().splitlines()]
        require(len(queries) == 32 and len({query["id"] for query in queries}) == 32, "Invalid query input")
    with phase("product_initialization"):
        sys.path.insert(0, str(args.source))
        import memory_book
        require(Path(memory_book.__file__).resolve().parent == args.source.resolve() / "memory_book"
            and memory_book.__version__ == SOURCES[args.version]["version"], "Wrong imported runtime")
        require(not args.database.exists(), "Never reuse a product database")
        book = memory_book.MemoryBook(args.database, max_page_chars=900, cache_size=0)
    try:
        with phase("product_ingestion"):
            count = 0
            with args.sessions.open() as stream:
                for line in stream:
                    book.ingest(json.loads(line))
                    count += 1
            stats = book.stats()
            require(count == 2548 and stats["turns"] == 10693 and stats["pages"] == 3953,
                    "Incomplete normalized corpus ingestion")
        with phase("product_queries"):
            for query in queries:
                emit("query_start", id=query["id"])
                response = book.recall(query["query"], project=query["project"], limit=5,
                    budget_chars=100000, use_cache=False, coverage=False, semantic=False)
                require(response["cache_hit"] is False and not response.get("semantic", False)
                    and len(response["context"]) <= 100000 and len(response["results"]) <= 5,
                    "Product route/budget invariant failed")
                response.pop("latency_ms")
                emit("query_finish", id=query["id"], payload_sha256=digest(response))
                del response
    finally:
        with phase("product_close"):
            book.close()
    emit("done", source_version=args.version, sessions=count, pages=stats["pages"], recalls=32,
         worker_peak_rss_bytes=worker_high_water())


def evaluator_worker(args):
    worker_guard(args)
    sys.path.insert(0, str(ROOT))
    with phase("evaluator_corpus_loading"):
        from scripts.round4_data import load
        data = load(args.parquet, ROOT / "benchmarks/experiments/round4-validation-binding.json",
                    ROOT / "benchmarks/experiments/round4-hotpot256-manifest.json")
        require(data.fingerprint == "fb3cd70ea58fafa5bd9cef0f04dba7399aaafba76f5f92605eee9e516f115e1b",
                "Evaluator corpus changed")
    with phase("evaluator_reference_tokenizers"):
        from benchmarks.token_compare import ENCODINGS, TokenCounter
        counters = [TokenCounter(name) for name in ENCODINGS]
        for counter in counters:
            counter.count("readiness")
    with phase("evaluator_git_provenance"):
        from benchmarks.token_compare import checkout_provenance
        from scripts.round4_comparison import frozen_inputs
        for label in SOURCES:
            identity = checkout_provenance(args.snapshots / label / "src/memory_book")
            require(identity["commit_identifies_source"] and identity["git_commit"] == SOURCES[label]["commit"],
                    "Runtime provenance changed")
        _, binding = frozen_inputs()
    with phase("evaluator_legacy_model_hash"):
        from scripts.round4_comparison import verify_model
        verify_model(args.model, binding["model"]["identity"])
    with phase("evaluator_release_references"):
        del data, counters
    emit("done", recalls=0, embedding_inference_calls=0, generative_model_calls=0,
         worker_peak_rss_bytes=worker_high_water())


def terminate_process_group(process, grace_seconds=1.0):
    """Bounded cleanup of our start_new_session group, even after leader exit."""
    result = {"pgid": process.pid, "term_sent": False, "kill_sent": False, "errors": []}
    def present():
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError as error:
            result["errors"].append({"operation": "probe_group", "errno": error.errno})
            return True
    def send(number, key):
        try:
            os.killpg(process.pid, number)
            result[key] = True
        except ProcessLookupError:
            pass
        except OSError as error:
            result["errors"].append({"operation": key, "errno": error.errno})
    if present():
        send(signal.SIGTERM, "term_sent")
        deadline = time.monotonic() + grace_seconds
        while present() and time.monotonic() < deadline:
            process.poll()
            time.sleep(.01)
        if present():
            send(signal.SIGKILL, "kill_sent")
    try:
        process.wait(timeout=.5)
    except subprocess.TimeoutExpired:
        result["errors"].append({"operation": "reap_leader", "reason": "timeout"})
    result["leader_reaped"] = process.returncode is not None
    # A surviving group entry can be an already-dead orphan awaiting reaping.
    result["group_present_after_cleanup"] = present()
    return result


def observe(command, prefix, plan, product, environment, timeout):
    trace_path, events_path, summary_path = (prefix.with_suffix(suffix) for suffix in (".trace.jsonl.gz", ".events.jsonl", ".summary.json"))
    require(not any(path.exists() for path in (trace_path, events_path, summary_path)), "Never replay an existing worker")
    events, pending = [], b""
    begin, active = time.monotonic(), "spawn"
    # Raw nonblocking pipes have no reader thread or buffered-reader close lock.
    process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, start_new_session=True)
    os.set_blocking(process.stdout.fileno(), False)
    os.set_blocking(process.stdin.fileno(), False)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    failure, failure_check, eof, leader_exited = None, None, False, None
    cleanup = None
    try:
        root_start_ticks = parse_stat(Path("/proc", str(process.pid), "stat").read_text())["start_ticks"]
    except (OSError, ValueError, IndexError):
        root_start_ticks = None
    with gzip.open(trace_path, "xt", encoding="utf-8") as trace, events_path.open("x") as event_stream:
        def sample(boundary=None):
            value = tree_sample(process.pid, root_start_ticks=root_start_ticks)
            value.update(phase=active, boundary=boundary)
            trace.write(json.dumps(value, separators=(",", ":")) + "\n")
            trace.flush()
        def accept(data, acknowledge):
            nonlocal pending, active
            pending += data
            require(len(pending) <= 1024 * 1024, "Worker output exceeds its bounded protocol buffer")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                event = json.loads(line)
                require(event["event"] in {"phase_start", "phase_end", "query_start", "query_finish", "done", "failed"}
                    and event["pid"] == process.pid, "Unexpected worker output")
                events.append(event)
                event_stream.write(json.dumps(event, separators=(",", ":")) + "\n")
                event_stream.flush()
                if event["event"] == "phase_start":
                    active = event["phase"]
                    if acknowledge:
                        sample("start")
                        require(os.write(process.stdin.fileno(), b"continue\n") == 9, "Incomplete observer acknowledgement")
                elif event["event"] == "phase_end":
                    if acknowledge:
                        sample("end")
                    active = "between_phases"
                    if acknowledge:
                        require(os.write(process.stdin.fileno(), b"continue\n") == 9, "Incomplete observer acknowledgement")
        def read_ready(acknowledge):
            nonlocal eof
            try:
                data = os.read(process.stdout.fileno(), 65536)
            except BlockingIOError:
                return
            if data:
                accept(data, acknowledge)
            else:
                eof = True
                selector.unregister(process.stdout)
        next_sample = time.monotonic()
        try:
            while process.poll() is None or not eof:
                clock = time.monotonic()
                require(clock - begin < timeout, "Worker diagnostic timeout; no replacement run")
                if process.returncode is not None and not eof:
                    leader_exited = clock if leader_exited is None else leader_exited
                    require(clock - leader_exited < 1.0, "Exited worker left stdout open in a descendant")
                if clock >= next_sample and process.returncode is None:
                    sample()
                    next_sample = time.monotonic() + .02
                for _key, _mask in selector.select(timeout=.005):
                    read_ready(True)
            require(not pending, "Unterminated worker protocol output")
        except BaseException as error:
            failure = type(error).__name__
            failure_check = str(error) if isinstance(error, DiagnosticError) else "external_observer_error"
        finally:
            # Never condition group cleanup on process.poll(): the leader can
            # exit while a descendant still owns stdout. No blocking reader
            # owns these raw pipes, and all cleanup waits have fixed bounds.
            cleanup = terminate_process_group(process)
            drain_deadline = time.monotonic() + .2
            while not eof and time.monotonic() < drain_deadline:
                if not selector.select(timeout=0):
                    break
                try:
                    read_ready(False)
                except (ValueError, KeyError, TypeError, OSError):
                    break
            selector.close()
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError as error:
                    cleanup["errors"].append({"operation": "close_raw_pipe", "errno": error.errno})
    phases = summarize_trace(trace_path, events)
    finished = [event for event in events if event["event"] == "query_finish"]
    try:
        require(failure is None and process.returncode == 0 and cleanup["leader_reaped"],
                "Worker did not complete normally")
        finished = validate_events(events, phases, product, plan)
    except (ValueError, KeyError) as error:
        failure = failure or type(error).__name__
        failure_check = failure_check or (str(error) if isinstance(error, DiagnosticError) else "external_summary_error")
    result = {"schema_version": 1, "name": prefix.name, "status": "failed-incomplete" if failure else "completed",
        "exit_code": process.returncode, "failure_type": failure, "failure_check": failure_check, "root_pid": process.pid,
        "target_sampling_interval_ms": 20, "boundary_samples": "Start/end barriers acknowledged by observer; these pauses are not latency measurements.",
        "phases": phases, "query_results": finished, "cleanup": cleanup, "trailing_stdout_bytes": len(pending),
        "calls_started": sum(event["event"] == "query_start" for event in events), "calls_finished": len(finished),
        "worker_peak_rss_bytes": next((event.get("worker_peak_rss_bytes") for event in events if event["event"] == "done"), None),
        "trace_sha256": file_hash(trace_path), "events_sha256": file_hash(events_path),
        "wall_seconds_including_observer_barriers": time.monotonic() - begin}
    atomic(summary_path, result)
    return result

def assess(results, ids, plan):
    require(len(results) == 9 and all(result["status"] == "completed" for result in results), "Incomplete diagnostic stages")
    names = ["evaluator"] + [f"r{index}-{label}" for index, pair in enumerate(ORDER) for label in pair]
    require([result["name"] for result in results] == names, "Worker order or identity changed")
    require(results[0]["calls_started"] == results[0]["calls_finished"] == 0, "Evaluator executed retrieval")
    reference = None
    for result in results[1:]:
        require(result["calls_started"] == result["calls_finished"] == 32, "Incomplete product call ledger")
        rows = result["query_results"]
        require([row["id"] for row in rows] == ids, "Registered query order changed")
        hashes = [row["payload_sha256"] for row in rows]
        require(reference is None or hashes == reference, "Full non-timing outputs differ")
        reference = hashes
    return {"status": "complete-verified", "workers": 9, "product_workers": 8, "product_calls": 256,
        "complete_payload_pairs": 128, "selected_ids_sha256": digest(ids), "all_output_hashes_equal": True,
        "pss_missing_samples": sum(value["samples"] - value["complete_pss_samples"]
            for result in results for value in result["phases"].values()),
        "boundary": "Historical attribution diagnostic only. No quality scoring, inference, formal speed claim or retrospective replacement of round-four RSS."}


def run():
    run_id = actions_identity()
    sys.path.insert(0, str(ROOT))
    from scripts.run_round4_comparison import git, public_commit, snapshot, authorized_origin
    from benchmarks.run import engine_source_hash
    from benchmarks.token_compare import checkout_provenance
    plan = json.loads(PLAN.read_bytes())
    validate_plan(plan)
    authorized_origin()
    source = git("rev-parse", "HEAD")
    require(source == os.environ.get("GITHUB_SHA"), "Diagnostic source differs from trigger")
    require(PLAN.read_bytes() == subprocess.check_output(["git", "show", source + ":" + str(PLAN.relative_to(ROOT))], cwd=ROOT, timeout=30),
            "Commit resource plan before execution")
    require(file_hash(ROOT / "benchmarks/experiments/round5-plan.json") == plan["parent_plan_sha256"], "Parent registration changed")
    require(sys.version_info[:2] == (3, 12), "Registered Python minor differs")
    for name, expected in plan["environment"]["packages"].items():
        require(importlib.metadata.version(name) == expected, "Diagnostic dependency changed: " + name)
    for kind in ("manifest", "binding"):
        require(file_hash(ROOT / plan["corpus"][kind]) == plan["corpus"][kind + "_sha256"], "Old corpus binding changed")
    fingerprint = file_hash(PLAN)
    claim_ref = "refs/heads/validation/round5-resource-claim-" + fingerprint
    require(not git("ls-remote", "--heads", "origin", claim_ref), "Plan already has an execution claim; never replay it")
    claim_path = ROOT / "benchmarks/reports" / ("round5-resource-claim-" + fingerprint + ".json")
    require(not claim_path.exists(), "Preserve prior claim")
    bound_names = [SCRIPT, str(PLAN.relative_to(ROOT)), ".github/workflows/round5-resource-diagnostic.yml",
                   "tests/test_round5_resource_diagnostic.py"]
    evaluator_files = {name: file_hash(ROOT / name) for name in bound_names}
    for name in bound_names:
        require((ROOT / name).read_bytes() == subprocess.check_output(["git", "show", source + ":" + name], cwd=ROOT, timeout=30),
                "Commit the diagnostic implementation before execution")
    def verify_evaluator():
        require(evaluator_files == {name: file_hash(ROOT / name) for name in bound_names},
                "Diagnostic plan/implementation changed during execution")
    atomic(claim_path, {"schema_version": 1, "run_id": run_id, "claimed_at": now(), "source_commit": source,
        "plan_sha256": fingerprint, "evaluator_files": evaluator_files,
        "status": "claimed-before-preparation", "sources": SOURCES})
    parent = public_commit([claim_path], source, "bench: claim historical resource attribution once")
    git("push", "origin", parent + ":" + claim_ref)
    claim_commit = parent
    directory = ROOT / ".artifacts/round5-resources" / run_id
    output = ROOT / "benchmarks/reports" / ("round5-resources-" + run_id)
    require(not directory.exists() and not output.exists(), "Never resume a prior resource worker directory")
    directory.mkdir(parents=True)
    output.mkdir(parents=True)
    checkpoint_path = output / "checkpoint.json"
    checkpoint = {"schema_version": 1, "status": "preparing", "run_id": run_id, "source_commit": source,
        "claim_commit": claim_commit, "plan_sha256": fingerprint, "started_at": now(), "stages": [],
        "host": {"python": sys.version, "platform": sys.platform, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                 "packages": {name: importlib.metadata.version(name) for name in plan["environment"]["packages"]}}}
    result_ref = "refs/heads/validation/round5-resources-" + run_id
    def persist():
        nonlocal parent
        atomic(checkpoint_path, checkpoint)
        existing = git("ls-remote", "--heads", "origin", result_ref)
        require(not existing or existing.split()[0] == parent, "Result branch advanced; never force push")
        next_parent = public_commit(sorted(path for path in output.iterdir() if path.is_file()) + [claim_path],
                                    parent, "bench: preserve resource trace and worker checkpoint")
        git("push", "origin", next_parent + ":" + result_ref)
        parent = next_parent
    deadline = time.monotonic() + plan["execution"]["wall_time_seconds"]
    results = []
    try:
        persist()
        snapshots = directory / "sources"
        snapshots.mkdir()
        for label, expected in SOURCES.items():
            snapshot(snapshots / label, expected["commit"])
        def verify_sources():
            for label, expected in SOURCES.items():
                package = snapshots / label / "src/memory_book"
                provenance = checkout_provenance(package)
                require(provenance["git_commit"] == expected["commit"] and provenance["commit_identifies_source"]
                    and engine_source_hash(package) == expected["runtime_sha256"], "Pinned runtime source changed")
        verify_sources()
        old_source = json.loads((ROOT / "benchmarks/hotpot_manifest.json").read_bytes())
        parquet = directory / "hotpot.parquet"
        download_verified(old_source["source_url"], parquet, old_source["upstream_sha256"], old_source["upstream_bytes"])
        binding = json.loads((ROOT / plan["corpus"]["binding"]).read_bytes())
        model = directory / "model"
        for item in binding["model"]["identity"]["files"]:
            path = model / item["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            identity = binding["model"]["identity"]
            download_verified("https://huggingface.co/" + identity["repository"] + "/resolve/" + identity["revision"] + "/" + item["path"],
                             path, item["sha256"], item["bytes"])
        from scripts.round4_data import load
        data = load(parquet, ROOT / plan["corpus"]["binding"], ROOT / plan["corpus"]["manifest"])
        require(data.fingerprint == plan["corpus"]["dataset_sha256"] and len(data.sessions) == 2548, "Old corpus changed")
        ids = selected_ids(json.loads((ROOT / plan["corpus"]["manifest"]).read_bytes()), plan)
        by_id = {case.id: case for case in data.queries}
        sessions, queries = directory / "sessions.jsonl", directory / "queries.jsonl"
        with sessions.open("x") as stream:
            for session in data.sessions:
                stream.write(canonical(session).decode() + "\n")
        with queries.open("x") as stream:
            for identity in ids:
                case = by_id[identity]
                stream.write(canonical({"id": case.id, "query": case.query, "project": case.project}).decode() + "\n")
        frozen_normalized = {"sessions_sha256": file_hash(sessions), "queries_sha256": file_hash(queries),
            "selected_ids_sha256": digest(ids), "sessions": 2548, "queries": 32, "dataset_sha256": data.fingerprint}
        checkpoint["normalized_input"] = dict(frozen_normalized)
        del data, by_id
        checkpoint["status"] = "prepared"
        persist()
        stages = [("evaluator", None)] + [(f"r{index}-{label}", label) for index, pair in enumerate(ORDER) for label in pair]
        for name, label in stages:
            require(time.monotonic() < deadline - 180, "No time for another complete diagnostic worker")
            verify_evaluator()
            verify_sources()
            verify_normalized_inputs(sessions, queries, frozen_normalized)
            if label is None:
                command = [sys.executable, "-u", str(ROOT / SCRIPT), "evaluator-worker", "--name", name,
                    "--claim", claim_commit, "--parquet", str(parquet), "--model", str(model), "--snapshots", str(snapshots)]
            else:
                command = [sys.executable, "-u", str(ROOT / SCRIPT), "product-worker", "--name", name,
                    "--claim", claim_commit, "--version", label, "--source", str(snapshots / label / "src"),
                    "--database", str(directory / (name + ".db")), "--sessions", str(sessions), "--queries", str(queries),
                    "--sessions-sha256", frozen_normalized["sessions_sha256"],
                    "--queries-sha256", frozen_normalized["queries_sha256"]]
            record = {"name": name, "status": "intent-before-launch", "argv": command, "at": now(),
                      "source": SOURCES[label] if label else None}
            checkpoint["stages"].append(record)
            persist()
            record["intent_commit"] = parent
            environment = {**os.environ, "ROUND5_RESOURCE_CLAIM": claim_commit, "ROUND5_RESOURCE_WORKER": name,
                           "PYTHONDONTWRITEBYTECODE": "1", "ORT_DISABLE_TELEMETRY": "1"}
            result = observe(command, output / name, plan, label is not None, environment,
                             plan["execution"]["worker_timeout_seconds"])
            results.append(result)
            verify_normalized_inputs(sessions, queries, frozen_normalized)
            verify_evaluator()
            verify_sources()
            record.update(status=result["status"], finished_at=now(), outputs={path.name: file_hash(path)
                for path in output.glob(name + ".*") if path.is_file()})
            persist()
            require(result["status"] == "completed", "A diagnostic worker failed; no retry or later worker")
        assessment = assess(results, ids, plan)
        atomic(output / "assessment.json", assessment)
        checkpoint["status"] = assessment["status"]
    except BaseException as error:
        checkpoint.update(status="failed-incomplete", failure_type=type(error).__name__,
                          failure_check=str(error) if isinstance(error, DiagnosticError) else "external_controller_error")
    finally:
        checkpoint["finished_at"] = now()
        persist()
    print(json.dumps({"run_id": run_id, "status": checkpoint["status"], "result_commit": parent,
                      "result_branch": result_ref, "product_calls_finished": sum(result["calls_finished"] for result in results)}))
    return 0 if checkpoint["status"] == "complete-verified" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "product-worker", "evaluator-worker"))
    for name in ("name", "claim", "version", "sessions-sha256", "queries-sha256"):
        parser.add_argument("--" + name)
    for name in ("source", "sessions", "queries", "database", "parquet", "model", "snapshots"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        return run()
    try:
        (product_worker if args.mode == "product-worker" else evaluator_worker)(args)
        return 0
    except BaseException as error:
        emit("failed", error_type=type(error).__name__,
             check=str(error) if isinstance(error, DiagnosticError) else "external_worker_error")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
