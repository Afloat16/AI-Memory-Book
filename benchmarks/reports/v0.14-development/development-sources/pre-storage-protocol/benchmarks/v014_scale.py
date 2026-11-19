"""Paired long-history experiment with original-response and work diagnostics.

Run ``python benchmarks/v014_scale.py run --baseline-root BASE --candidate-root
CAND --output NEW_DIRECTORY --profile main --backend python``. Source trees
must be committed. No network, external model or production data is involved.
Runtime/evaluator bytes are bound before any measurement and checked in every
worker. Completed evidence is never overwritten; failures remain in journals.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import v013_scale as common
from benchmarks.v014_workload import (SEED, TARGETS, cases, checkpoints,
    TRANSFER, background_session, core_sources, digest, encoded, sessions, source_for, source_turn)
from benchmarks.v013_workload import FAMILIES

PROTOCOL = "v014-paired-long-history-1"
PLAN = ROOT / "benchmarks/experiments/v014-long-history-plan.json"
FROZEN = ("benchmarks/v014_scale.py", "benchmarks/v014_workload.py",
          "benchmarks/v014_audit.py",
          "benchmarks/experiments/v014-long-history-plan.json", "tests/test_v014_scale.py",
          "benchmarks/v013_scale.py", "benchmarks/v013_workload.py")
PERFORMANCE = (
    "routing-archive:current", "routing-archive:historical", "routing-archive:multi_source",
    "routing-core:current", "routing-core:identifier", "routing-core:multi_source",
    "lease-archive:current", "lease-live:identifier", "compaction-archive:multi_source",
    "routing-archive:directory", "routing-core:directory", "lease-archive:directory",
)
DIRECTORY = {"chapter_limit": 2, "sections_per_chapter": 4,
             "pages_per_section": 2, "read_limit_chars": 900,
             "total_original_evidence_budget_chars": 2400}


def protocol_identity():
    return {"protocol": PROTOCOL, "files": {p: common.file_sha(ROOT / p) for p in FROZEN}}


def fingerprint(book):
    result = common.source_fingerprint(book.db)
    result["target_layout"] = {}
    for target in TARGETS:
        row = book.db.execute("SELECT COUNT(*),MIN(rid),MAX(rid) FROM pages WHERE project_id=?",
                              (target["project"],)).fetchone()
        result["target_layout"][target["project"]] = {"pages": row[0], "min_rowid": row[1], "max_rowid": row[2]}
    return result


def score(response, case, spec, book=None):
    """Check exact source slices, cited page ownership, scope, budget and gold."""
    errors, fragments = [], []
    hits, context = response.get("results", []), response.get("context", "")
    if len(context) > 2400:
        errors.append("context_budget_exceeded")
    expected_blocks = []
    for index, hit in enumerate(hits):
        text = hit.get("text", "")
        refs = hit.get("source_refs", [])
        covered = [False] * len(text)
        if not refs:
            errors.append(f"{index}:missing_source_refs")
        for ref in refs:
            try:
                if ref.get("project") != case["project"]:
                    raise ValueError("cross_project_source")
                original = source_for(spec, ref["project"], ref["session_id"])
                turn = source_turn(original["messages"], ref["turn_index"])
                start, end = ref["turn_start"], ref["turn_end"]
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(turn):
                    raise ValueError("invalid_source_coordinates")
                if ref["end"] - ref["start"] != end - start or ref["created_at"] != original["created_at"]:
                    raise ValueError("source_coordinate_or_timestamp_mismatch")
                fragment = turn[start:end]
                position = text.find(fragment)
                if position < 0:
                    raise ValueError("original_slice_absent_from_excerpt")
                covered[position:position + len(fragment)] = [True] * len(fragment)
                fragments.append((index + 1, ref["session_id"], ref["turn_index"], fragment, text))
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                errors.append(f"{index}:{exc}")
        if any(not present and not char.isspace() and char != "…" for present, char in zip(covered, text)):
            errors.append(f"{index}:unsupported_excerpt_text")
        if hit.get("breadcrumb") and hit["breadcrumb"][0].get("id") != case["project"]:
            errors.append(f"{index}:cross_project_breadcrumb")
        if case["surface"] == "directory":
            expected_blocks.append(text)
        else:
            ref = refs[0] if refs else {}
            expected_blocks.append(f"[{hit.get('id')}] {ref.get('project')} / {ref.get('session_id')} | {ref.get('created_at')}\n" + text)
    if context != "\n\n".join(expected_blocks):
        errors.append("context_not_cited_original_excerpts")
    if book is not None:
        errors.extend(common.page_identity_errors(book, response, case["project"]))

    def rank(item):
        return next((n for n, sid, turn, fragment, text in fragments
                     if (sid, turn) == (item["session_id"], item["turn_index"])
                     and item["quote"] in fragment and item["quote"] in text and item["quote"] in context), None)
    ranks, stale = [rank(r) for r in case["required"]], [rank(r) for r in case["stale"]]
    first = ranks[0] if ranks else None
    stale_first = min((r for r in stale if r is not None), default=None)
    return {"answerable": bool(ranks), "complete": bool(all(r is not None for r in ranks) and not errors) if ranks else None,
            "required_spans": len(ranks), "covered_spans": sum(r is not None for r in ranks) if not errors else 0,
            "required_ranks": ranks, "stale_ranks": stale,
            "current_source_first": first == 1 and not errors if case["stale"] else None,
            "stale_before_current": stale_first is not None and (first is None or stale_first < first),
            "returned_context_for_missing": bool(context) if not ranks else None,
            "source_errors": errors, "context_chars": len(context),
            "evidence_projection_sha256": digest(common.answer_projection(response))}


def required_fields(case):
    if case["category"] == "missing":
        return ["erasure_recovery_quorum" if case["cohort"] == "authored-transfer-v014" else "distributed_all_reduce_bucket_bytes"]
    family = TRANSFER.get(case["family"], FAMILIES.get(case["family"]))
    if case["category"] in {"identifier", "replacement"}:
        return [family["symbol"]]
    if case["category"] in {"current", "multi_source", "chinese"}:
        return [family.get("field", family.get("key"))]
    return []


def invoke_api(book, case, mode, *, fields=None, trace=None):
    if case["surface"] == "directory":
        return common.directory_read(book, case["query"], case["project"], DIRECTORY, trace=trace)
    extra = {"required_fields": fields} if fields is not None else {}
    response = book.recall(case["query"], project=case["project"], budget_chars=2400,
                           limit=5, strategy="book", temporal="auto", coverage=False,
                           semantic=False, use_cache=mode not in {"quality", "required-fields"}, **extra)
    return response, response


def cached_connections(book):
    """Include project-local SQLite connections, not just the parent archive."""
    entries = getattr(getattr(book, "_project_indexes", None), "entries", {})
    return [book.db, *(entry.book.db for entry in entries.values())]


def clear_recall_caches(book):
    for connection in cached_connections(book):
        connection.execute("DELETE FROM recall_cache")


def date_invariant_response(value):
    """Keep decision metadata while removing documented measurement/date fields."""
    if isinstance(value, dict):
        return {key: date_invariant_response(item) for key, item in value.items()
                if key not in {"latency_ms", "cache_hit", "created_at", "preparation_ms", "index_cache_hit", "fingerprint_checked"}}
    if isinstance(value, list):
        return [date_invariant_response(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", "<timestamp>", value)
    return value


def measure(book, case, spec, mode, recorder, identity, *, instrument=False, fields=None):
    raw = response = error = None
    wall_ns = cpu_ns = None
    steps = 0
    def progress():
        nonlocal steps
        steps += 100
        return 0
    instrumented = cached_connections(book) if instrument else []
    for connection in instrumented:
        connection.set_progress_handler(progress, 100)
    if case["surface"] == "directory":
        raw = {}
    recorder.event({"event": "call_started", "case": case["id"], "mode": mode, **identity})
    try:
        with common.deadline(45):
            wall, cpu = time.perf_counter_ns(), time.process_time_ns()
            try:
                response, raw = invoke_api(book, case, mode, fields=fields, trace=raw)
            finally:
                wall_ns, cpu_ns = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        for connection in instrumented:
            connection.set_progress_handler(None, 0)
    judged = score(response, case, spec, book) if response is not None else None
    expected_cache = {"cold": False, "warm": True, "lifecycle-warm": True, "lifecycle-after": False}.get(mode)
    cache_valid = (response is not None and response.get("cache_hit") is expected_cache
                   if case["surface"] == "recall" and expected_cache is not None else True)
    item = {"case": case["id"], "category": case["category"], "cohort": case["cohort"],
            "surface": case["surface"], "mode": mode, **identity, "wall_ns": wall_ns,
            "cpu_ns": cpu_ns, "sqlite_vm_steps_lower_bound": steps if instrument else None,
            "instrumented_sqlite_connections": len(instrumented) if instrument else None,
            "cache_mode_valid": cache_valid, "score": judged, "error": error,
            "required_fields": fields,
            "date_invariant_response_sha256": digest(date_invariant_response(raw)) if raw is not None else None,
            "stable_response_sha256": digest(common.stable_response(raw)) if raw is not None else None}
    recorder.record(item, raw)
    return item


def apply_transition(book, spec, recorder=None, identity=None):
    """Exercise actual runtime cache invalidation before timed final-state reads."""
    if spec["axis"] not in {"source_replacement", "source_deletion"}:
        return []
    preceding = dict(spec, revision=0 if spec["axis"] == "source_replacement" else 1, delete_config=False)
    before_cases = [c for c in cases(preceding) if c["category"] == "identifier"]
    if recorder:
        for case in before_cases:
            measure(book, case, preceding, "lifecycle-before", recorder, identity)
            measure(book, case, preceding, "lifecycle-warm", recorder, identity)
    actions = []
    if spec["axis"] == "source_replacement":
        for source in core_sources(spec):
            if source["session_id"] != "active-config":
                continue
            started = time.perf_counter_ns()
            saved = book.ingest(source)
            actions.append({"operation": "ingest", "project": source["project"], "session": source["session_id"],
                            "wall_ns": time.perf_counter_ns() - started, "result": saved})
    else:
        for target in TARGETS:
            started = time.perf_counter_ns()
            saved = book.delete_session(target["project"], "active-config")
            actions.append({"operation": "delete_session", "project": target["project"], "session": "active-config",
                            "wall_ns": time.perf_counter_ns() - started, "result": saved})
    if recorder:
        for case in (c for c in cases(spec) if c["category"] == "identifier"):
            measure(book, case, spec, "lifecycle-after", recorder, identity)
    return actions


def foreign_write_control(book, spec, recorder, identity):
    """Measure the next old-project read after a real unrelated source rewrite."""
    case = next(c for c in cases(spec) if c["id"] == "routing-archive:current")
    measure(book, case, spec, "foreign-write-before", recorder, identity)
    original = background_session(0, "foreign", spec.get("shift_days", 0))
    changed = json.loads(json.dumps(original))
    changed["messages"][1]["content"] += " Independent monitoring refresh completed."
    started = time.perf_counter_ns()
    update = book.ingest(changed)
    update_ns = time.perf_counter_ns() - started
    try:
        measure(book, case, spec, "after-foreign-write", recorder, identity)
    finally:
        started = time.perf_counter_ns()
        restored = book.ingest(original)
        restore_ns = time.perf_counter_ns() - started
    return {"original_sha256": digest(original), "changed_source": changed,
            "update_wall_ns": update_ns, "update_result": update,
            "restore_wall_ns": restore_ns, "restore_result": restored}


def worker(args):
    bound = json.loads(Path(args.binding).read_text())
    if protocol_identity() != bound["evaluator"]:
        raise ValueError("Evaluator changed after run binding")
    identity = common.runtime_identity(args.repo_root)
    if identity != bound[args.arm]:
        raise ValueError("Runtime changed after run binding")
    MemoryBook, imported = common.load_runtime(args.repo_root, args.backend)
    spec = json.loads(args.spec)
    output = Path(args.worker_output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    result = {"status": "running", "started_at": common.now(), "spec": spec,
              "arm": args.arm, "round": args.round, "runtime": identity,
              "imported": imported, "host": common.host_identity()}
    common.atomic_json(output / "result.json", result)
    try:
        extra = ({"ranking_scope": bound["candidate_ranking_scope"]}
                 if args.arm == "candidate" and bound["candidate_ranking_scope"] != "global" else {})
        with MemoryBook(args.database, segmentation="turn", max_page_chars=900, min_page_chars=0, cache_size=128, **extra) as book:
            result["open_wall_ns"] = time.perf_counter_ns() - started
            result["storage_before"] = common.storage(args.database, book.db)
            if args.action == "worker-build":
                count = skipped = 0
                source_hash = hashlib.sha256()
                if spec["axis"] in {"source_replacement", "source_deletion"}:
                    result["mutations"] = apply_transition(book, spec)
                else:
                    for source in sessions(spec):
                        source_hash.update(encoded(source) + b"\n")
                        saved = book.ingest(source)
                        if saved["pages"] != len(source["messages"]) // 2:
                            raise AssertionError("Ingest did not produce one genuine page per turn")
                        count += 1
                        skipped += bool(saved["skipped"])
                        if count % 128 == 0:
                            common.append_json(output / "progress.jsonl", {"ingest_calls": count, "skipped": skipped,
                                "elapsed_seconds": (time.perf_counter_ns() - started) / 1e9})
                            if shutil.disk_usage(output).free < 1_000_000_000:
                                raise RuntimeError("Run stopped at one-gigabyte free-space floor")
                result.update(ingest_calls=count, skipped=skipped, source_order_sha256=source_hash.hexdigest())
            else:
                recorder = common.Recorder(output)
                call_identity = {"arm": args.arm, "round": args.round, "checkpoint": spec["id"]}
                result["mutations"] = apply_transition(book, spec, recorder if args.round == 0 else None, call_identity)
                selected = {c["id"]: c for c in cases(spec)}
                if spec["axis"] not in {"source_replacement", "source_deletion"}:
                    measure(book, selected["routing-archive:current"], spec, "first-request", recorder, call_identity)
                if args.round == 0:
                    for case in selected.values():
                        measure(book, case, spec, "quality", recorder, call_identity)
                    if args.arm == "candidate" and bound["required_fields_controls"]:
                        for case in selected.values():
                            fields = required_fields(case)
                            if fields:
                                measure(book, case, spec, "required-fields", recorder, call_identity, fields=fields)
                for case_id in PERFORMANCE:
                    case = selected[case_id]
                    for repetition in range(bound["repetitions"]):
                        identity_call = {**call_identity, "repetition": repetition}
                        clear_recall_caches(book)
                        measure(book, case, spec, "directory" if case["surface"] == "directory" else "cold", recorder, identity_call)
                        if case["surface"] == "recall":
                            for warm in range(bound["warm_calls"]):
                                measure(book, case, spec, "warm", recorder, {**identity_call, "warm": warm})
                    if args.round == 0:
                        clear_recall_caches(book)
                        measure(book, case, spec, "work-diagnostic", recorder, call_identity, instrument=True)
                if args.round == 0:
                    result["foreign_write_control"] = foreign_write_control(book, spec, recorder, call_identity)
                result["observations"] = recorder.sequence
            result["fingerprint"] = fingerprint(book)
            actual = book.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            if actual != spec["total_pages"]:
                raise AssertionError(f"Expected {spec['total_pages']} real pages; observed {actual}")
            result["actual_pages"] = actual
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            result["storage_after"] = common.storage(args.database, book.db)
        if common.runtime_identity(args.repo_root) != bound[args.arm] or protocol_identity() != bound["evaluator"]:
            raise ValueError("Bound source changed during worker execution")
        result["status"] = "completed"
    except Exception as exc:
        result.update(status="failed", error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    result.update(finished_at=common.now(), elapsed_seconds=(time.perf_counter_ns() - started) / 1e9,
                  resources=common.process_resources())
    common.atomic_json(output / "result.json", result)
    print(json.dumps({"status": result["status"], "output": str(output)}, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "completed" else 2


def invoke(args, action, repo, arm, spec, database, output, binding, round_number=0):
    env = os.environ.copy()
    env.update(PYTHONHASHSEED="0", MEMORY_BOOK_TEXT_BACKEND=args.backend,
               PYTHONPATH=os.pathsep.join((str(Path(repo).resolve() / "src"), str(ROOT))))
    command = [sys.executable, str(Path(__file__).resolve()), action, "--repo-root", str(repo),
               "--arm", arm, "--backend", args.backend, "--spec", json.dumps(spec),
               "--database", str(database), "--worker-output", str(output), "--binding", str(binding),
               "--round", str(round_number)]
    with output.with_suffix(".stdout").open("xb") as out, output.with_suffix(".stderr").open("xb") as err:
        completed = subprocess.run(command, env=env, stdout=out, stderr=err, timeout=args.worker_timeout)
    path = output / "result.json"
    result = json.loads(path.read_text()) if path.exists() else {"status": "missing_result"}
    if completed.returncode or result["status"] != "completed":
        raise RuntimeError(f"{action} failed; retained evidence: {output}")
    return result


def collect_rows(output):
    for path in sorted(Path(output).glob("measure-*/observations.jsonl")):
        with path.open() as stream:
            for line in stream:
                yield json.loads(line)


def summarize(output):
    output = Path(output)
    grouped, quality, field_controls = defaultdict(list), [], []
    for row in collect_rows(output):
        if row["mode"] == "quality":
            quality.append(row)
        elif row["mode"] == "required-fields":
            field_controls.append(row)
        else:
            grouped[row["checkpoint"], row["case"], row["mode"], row["arm"]].append(row)
    timing, comparison = [], []
    for keys, rows in sorted(grouped.items()):
        valid = [r for r in rows if r["error"] is None and r["cache_mode_valid"]]
        values = [r["wall_ns"] / 1e6 for r in valid]
        item = dict(zip(("checkpoint", "case", "mode", "arm"), keys))
        item.update(attempted=len(rows), n=len(values), errors=sum(r["error"] is not None for r in rows),
                    source_errors=sum(bool(r["score"] and r["score"]["source_errors"]) for r in rows),
                    incomplete=sum(bool(r["score"] and r["score"]["complete"] is False) for r in rows),
                    p50_ms=statistics.median(values) if values else None,
                    p95_ms=common.percentile(values, .95),
                    vm_steps=valid[0]["sqlite_vm_steps_lower_bound"] if valid and keys[2] == "work-diagnostic" else None)
        timing.append(item)
    by_group = defaultdict(dict)
    for item in timing:
        by_group[item["checkpoint"], item["case"], item["mode"]][item["arm"]] = item
    for (checkpoint, case, mode), arms in sorted(by_group.items()):
        if set(arms) != {"baseline", "candidate"}:
            continue
        b, c = arms["baseline"], arms["candidate"]
        ratios = []
        for rnd in sorted({r["round"] for r in grouped[checkpoint, case, mode, "baseline"]}):
            pair = []
            for arm in ("baseline", "candidate"):
                selected = [r["wall_ns"] for r in grouped[checkpoint, case, mode, arm]
                            if r["round"] == rnd and r["error"] is None and r["cache_mode_valid"]]
                pair.append(statistics.median(selected) if selected else None)
            if all(pair):
                ratios.append(pair[1] / pair[0])
        comparison.append({"checkpoint": checkpoint, "case": case, "mode": mode,
                           "baseline_p50_ms": b["p50_ms"], "candidate_p50_ms": c["p50_ms"],
                           "ratio_p50": c["p50_ms"] / b["p50_ms"] if b["p50_ms"] and c["p50_ms"] else None,
                           "baseline_p95_ms": b["p95_ms"], "candidate_p95_ms": c["p95_ms"],
                           "paired_round_ratios": ratios,
                           "median_paired_round_ratio": statistics.median(ratios) if ratios else None})
    quality_groups = []
    for checkpoint, arm, cohort in sorted({(r["checkpoint"], r["arm"], r["cohort"]) for r in quality}):
        rows = [r for r in quality if (r["checkpoint"], r["arm"], r["cohort"]) == (checkpoint, arm, cohort)]
        quality_groups.append({"checkpoint": checkpoint, "arm": arm, "cohort": cohort, "calls": len(rows),
            "answerable": sum(bool(r["score"] and r["score"]["answerable"]) for r in rows),
            "complete": sum(bool(r["score"] and r["score"]["complete"]) for r in rows),
            "required_spans": sum(r["score"]["required_spans"] for r in rows if r["score"]),
            "covered_spans": sum(r["score"]["covered_spans"] for r in rows if r["score"]),
            "missing_returning_context": sum(bool(r["score"] and r["score"]["returned_context_for_missing"]) for r in rows),
            "source_errors": sum(bool(r["score"] and r["score"]["source_errors"]) for r in rows),
            "failed_cases": [r["case"] for r in rows if r["error"] or (r["score"] and r["score"]["complete"] is False)]})
    quality_pairs = defaultdict(dict)
    for row in quality:
        quality_pairs[row["checkpoint"], row["case"]][row["arm"]] = row
    changes = []
    for (checkpoint, case), arms in quality_pairs.items():
        if set(arms) != {"baseline", "candidate"}:
            continue
        b, c = arms["baseline"], arms["candidate"]
        if b["stable_response_sha256"] != c["stable_response_sha256"]:
            changes.append({"checkpoint": checkpoint, "case": case,
                "baseline_score": b["score"], "candidate_score": c["score"],
                "same_evidence_projection": bool(b["score"] and c["score"] and b["score"]["evidence_projection_sha256"] == c["score"]["evidence_projection_sha256"])})
    controls = []
    quality_by_identity = {(r["checkpoint"], r["arm"], r["case"]): r for r in quality}
    for before, after, label in (("reference", "aged", "timestamp_age_only"), ("own_large", "interleaved", "physical_layout")):
        pairs = []
        for key, old in quality_by_identity.items():
            if key[0] != before:
                continue
            new = quality_by_identity.get((after, key[1], key[2]))
            if new is not None:
                pairs.append({"arm": key[1], "case": key[2],
                    "same_evidence": bool(old["score"] and new["score"] and old["score"]["evidence_projection_sha256"] == new["score"]["evidence_projection_sha256"]),
                    "same_metadata_except_dates_and_cache_measurements": old["date_invariant_response_sha256"] == new["date_invariant_response_sha256"]})
        controls.append({"control": label, "pairs": len(pairs),
            "evidence_mismatches": [p for p in pairs if not p["same_evidence"]],
            "metadata_mismatches": [p for p in pairs if not p["same_metadata_except_dates_and_cache_measurements"]]})
    result = {"protocol": PROTOCOL, "quality": quality_groups, "timings": timing,
              "comparisons": comparison, "changed_quality_outputs": changes,
              "controls": controls,
              "required_fields_controls": field_controls,
              "limitations": ["Authored synthetic and transfer development corpus; no real-project holdout or LLM task outcomes.",
                  "Cold means result-cache miss; operating-system and SQLite page caches are not evicted.",
                  "VM-step diagnostics are separate calls; SQLite FTS internal C work is not counted by this counter.",
                  "Quality and timing include failures; no statistical significance is claimed from repeated identical queries."]}
    common.atomic_json(output / "summary.json", result)
    return result


def run(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings = json.loads(PLAN.read_text())
    if settings["protocol"] != PROTOCOL or settings["seed"] != SEED:
        raise ValueError("Protocol identity mismatch")
    bound = {"evaluator": protocol_identity(), "baseline": common.runtime_identity(args.baseline_root),
             "candidate": common.runtime_identity(args.candidate_root), "profile": args.profile,
             "backend": args.backend, "host": common.host_identity(),
             "candidate_ranking_scope": args.candidate_ranking_scope,
             "required_fields_controls": args.required_fields_controls,
             "rounds": 2 if args.profile == "smoke" else settings["rounds"],
             "repetitions": 1 if args.profile == "smoke" else settings["repetitions"],
             "warm_calls": 1 if args.profile == "smoke" else settings["warm_calls"],
             "checkpoints": checkpoints(args.profile), "performance_cases": list(PERFORMANCE)}
    binding = output / "binding.json"
    common.atomic_json(binding, bound)
    for relative in FROZEN:
        destination = output / "protocol" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    manifest = {"status": "running", "started_at": common.now(), "stages": []}
    common.atomic_json(output / "manifest.json", manifest)
    snapshots = output / "snapshots"
    snapshots.mkdir()
    built = {}
    try:
        for spec in checkpoints(args.profile):
            database = snapshots / (spec["id"] + ".sqlite")
            if spec["parent"]:
                shutil.copyfile(built[spec["parent"]]["path"], database)
            print(json.dumps({"event": "build_started", "checkpoint": spec["id"], "pages": spec["total_pages"]}), flush=True)
            result = invoke(args, "worker-build", args.baseline_root, "baseline", spec, database,
                            output / ("build-" + spec["id"]), binding)
            snapshot = {"path": str(database), "sha256": common.file_sha(database),
                        "bytes": database.stat().st_size, "fingerprint": result["fingerprint"]}
            built[spec["id"]] = snapshot
            stage = {"spec": spec, "snapshot": snapshot, "build_elapsed_seconds": result["elapsed_seconds"], "measurements": []}
            manifest["stages"].append(stage)
            common.atomic_json(output / "manifest.json", manifest)
            # Mutation stages start from the preceding snapshot and execute real
            # runtime writes, after priming caches, in each arm independently.
            source = built[spec["parent"]] if spec["axis"] in {"source_replacement", "source_deletion"} else snapshot
            for rnd in range(bound["rounds"]):
                for arm in (("baseline", "candidate") if rnd % 2 == 0 else ("candidate", "baseline")):
                    working = output / "working.sqlite"
                    if working.exists():
                        common.remove_working(working)
                    shutil.copyfile(source["path"], working)
                    if common.file_sha(working) != source["sha256"]:
                        raise ValueError("Restored database bytes differ from bound baseline snapshot")
                    repo = args.baseline_root if arm == "baseline" else args.candidate_root
                    destination = output / f"measure-{spec['id']}-{rnd:02d}-{arm}"
                    measured = invoke(args, "worker-measure", repo, arm, spec, working, destination, binding, rnd)
                    if measured["fingerprint"]["logical_sources_sha256"] != snapshot["fingerprint"]["logical_sources_sha256"]:
                        raise ValueError("Arm did not retain the registered original source payloads")
                    if measured["fingerprint"]["page_ids"] != snapshot["fingerprint"]["page_ids"]:
                        raise ValueError("Arm changed original page identities")
                    if measured["fingerprint"]["source_tables_sha256"] != snapshot["fingerprint"]["source_tables_sha256"]:
                        raise ValueError("Arm changed original source tables or source coordinates")
                    stage["measurements"].append({"arm": arm, "round": rnd, "output": destination.name,
                        "status": measured["status"], "observations": measured["observations"],
                        "open_wall_ns": measured["open_wall_ns"], "storage_before": measured["storage_before"],
                        "storage_after": measured["storage_after"], "resources": measured["resources"]})
                    common.remove_working(working)
                    common.atomic_json(output / "manifest.json", manifest)
                    print(json.dumps({"event": "measurement_finished", "checkpoint": spec["id"], "arm": arm, "round": rnd}), flush=True)
            summarize(output)
        manifest["status"] = "completed"
    except Exception as exc:
        manifest.update(status="incomplete", error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    manifest["finished_at"] = common.now()
    common.atomic_json(output / "manifest.json", manifest)
    summarize(output)
    print(json.dumps({"status": manifest["status"], "output": str(output)}), flush=True)
    return 0 if manifest["status"] == "completed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "run", "summarize", "worker-build", "worker-measure"))
    parser.add_argument("--baseline-root")
    parser.add_argument("--candidate-root")
    parser.add_argument("--output")
    parser.add_argument("--profile", choices=("smoke", "main", "expanded"), default="main")
    parser.add_argument("--backend", choices=("python", "native"), default="python")
    parser.add_argument("--candidate-ranking-scope", choices=("global", "project"), default="global")
    parser.add_argument("--required-fields-controls", action="store_true")
    parser.add_argument("--worker-timeout", type=int, default=1800)
    parser.add_argument("--repo-root")
    parser.add_argument("--arm", choices=("baseline", "candidate"))
    parser.add_argument("--spec")
    parser.add_argument("--database")
    parser.add_argument("--worker-output")
    parser.add_argument("--binding")
    parser.add_argument("--round", type=int, default=0)
    args = parser.parse_args()
    if args.action == "describe":
        print(json.dumps({"protocol": PROTOCOL, "stages": checkpoints(args.profile), "cases": len(cases()),
                          "performance_cases": list(PERFORMANCE)}, indent=2))
        return 0
    if args.action == "summarize":
        summarize(args.output)
        return 0
    return run(args) if args.action == "run" else worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
