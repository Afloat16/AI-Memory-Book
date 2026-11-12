"""Registered old-data screen of one opt-in project-statistics candidate.

No new selection, threshold search, semantic model or generated answer is used.
Each cohort/mode has a fresh sequential process and archive. Every recall call
is journalled before execution; complete workers can be resumed without a new
call, but an interrupted worker is retained and cannot be silently rerun.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.native_budget_eval import block_ids, source_errors
from benchmarks.semantic_eval import diagnostics, page_projection_errors, paired_changes, source_snapshot
from benchmarks.run import engine_source_hash, original_turn_texts, percentile
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
                                     latency_summary, score_row, summarize_rows)
from scripts.benchmark_default_recall import indexed_content, rss, storage
from scripts.run_novelty_probe import dataset_for as old_dataset_for, prepare_data

PLAN = ROOT / "benchmarks/experiments/round3-plan.json"
BINDING = ROOT / "benchmarks/experiments/round3-project-stats-binding.json"
CLARIFICATION = ROOT / "benchmarks/experiments/round3-project-stats-scope-clarification.json"
HISTORICAL = ROOT / "benchmarks/experiments/novelty-cap-qualification-binding.json"
PROTOCOL = "round3-project-local-statistics-old-screen-v1"
BASELINE_COMMIT = "dd2f88be742ed330269e7dd5915b6f75089d7fef"
BASELINE_HASH = "d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57"
CANDIDATE_COMMIT = "2b51f72b63ff14053c92713858347edb2d572971"
CANDIDATE_HASH = "bb1e20c278cb3e50082134bdde529d552e46688b80f626c8c7f8fd7ef4c35fa7"
MODES = ("global_default", "project_local_fts_statistics")
COHORTS = ("synthetic61", "authored36", "public1015", "hotpot128")
BUDGETS = (512, 1024, 2048)
GROUPS = ("low_lexical_overlap_le_0.25", "multiple_required_evidence", "cross_session", "cross_chapter")
CORPORA = {"synthetic61": ("synthetic", "development"), "authored36": ("transfer", "development"),
           "public1015": ("locomo", "heldout"), "hotpot128": ("hotpotqa", "heldout")}
INVARIANTS = ("token_budget_violation", "source_span_errors", "page_projection_errors",
              "token_metadata_error", "scope_errors", "semantic_metadata_error", "cache_hit_error",
              "statistics_metadata_error", "character_budget_violation")
DEPENDENCIES = ("scripts/round3_project_stats.py", "tests/test_round3_project_stats.py",
    "benchmarks/experiments/round3-project-stats-scope-clarification.json",
    "scripts/run_novelty_probe.py", "scripts/benchmark_default_recall.py",
    "benchmarks/experiments/round3-plan.json", "benchmarks/experiments/novelty-cap-qualification-binding.json",
    "benchmarks/native_budget_eval.py", "benchmarks/semantic_eval.py", "benchmarks/component_eval.py",
    "benchmarks/token_compare.py", "benchmarks/run.py", "benchmarks/data.py", "benchmarks/long_data.py",
    "benchmarks/public_data.py", "benchmarks/transfer_data.py", "benchmarks/hotpot_data.py",
    "benchmarks/query_guard.py", "benchmarks/resume.py", "benchmarks/prepare_native_data.py",
    "benchmarks/locomo_split.json", "benchmarks/hotpot_manifest.json",
    "benchmarks/transfer_manifest.json", "benchmarks/transfer_cases.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha(canonical(value).encode())


def write_json(path, value, *, compressed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (canonical(value) + "\n").encode()
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(gzip.compress(raw, mtime=0) if compressed else raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return raw


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, timeout=30)


def helper_hashes():
    historical = json.loads(HISTORICAL.read_text())["historical_files_sha256"]
    require(len(historical) == 58, "The historical helper set must remain the same 58 files")
    actual = {name: sha((ROOT / name).read_bytes()) for name in historical}
    require(actual == historical, "A historical evaluator/helper has changed")
    return {**actual, **{name: sha((ROOT / name).read_bytes()) for name in DEPENDENCIES}}


def plan():
    value = json.loads(PLAN.read_text())
    quality = value["quality_candidate"]
    axes = quality["development"]
    require(value["baseline"]["commit"] == BASELINE_COMMIT
            and value["baseline"]["runtime_sha256"] == BASELINE_HASH, "Baseline registration differs")
    require(quality["name"] == MODES[1] and quality["candidates"] == 1, "Exactly one registered candidate is allowed")
    expected = {"cohorts": list(COHORTS), "modes": list(MODES), "token_budgets": list(BUDGETS),
        "tokenizers": ["cl100k_base"], "budget_chars": 8000, "limit": 5, "repeats": 1,
        "calls": 8082, "cache_size": 0, "use_cache": False, "semantic": False, "coverage": False}
    require(all(axes[k] == v for k, v in expected.items()) and axes["primary_groups"] == list(GROUPS),
            "Registered quality axes differ")
    require([c["name"] for c in value["cohorts"]] == list(COHORTS)
            and [c["queries"] for c in value["cohorts"]] == [168, 36, 1015, 128], "Old cohorts differ")
    scope = json.loads(CLARIFICATION.read_text())
    require(scope["parent_plan_sha256"] == sha(PLAN.read_bytes())
            and (scope["baseline_calls"], scope["candidate_calls"], scope["candidate_applied_calls"],
                 scope["candidate_unscoped_global_calls"], scope["total_calls"]) == (4041, 4041, 4017, 24, 8082),
            "Unscoped-query clarification differs")
    return value


def committed_runtime(commit):
    names = git("ls-tree", "-r", "--name-only", commit, "--", "src/memory_book").decode().splitlines()
    files, hasher = {}, hashlib.sha256()
    for name in sorted(n for n in names if n.endswith(".py")):
        raw = git("show", commit + ":" + name)
        files[name] = sha(raw)
        hasher.update(name.removeprefix("src/memory_book/").encode() + b"\0" + raw + b"\0")
    return {"commit": commit, "source_sha256": hasher.hexdigest(), "runtime_files_sha256": files}


def make_binding(path):
    require(not path.exists(), "Preserve an existing binding")
    declaration = plan()
    modes = {MODES[0]: committed_runtime(BASELINE_COMMIT), MODES[1]: committed_runtime(CANDIDATE_COMMIT)}
    require([modes[m]["source_sha256"] for m in MODES] == [BASELINE_HASH, CANDIDATE_HASH], "Frozen source bytes differ")
    changed = git("diff", "--name-only", BASELINE_COMMIT, CANDIDATE_COMMIT, "--", "src").decode().splitlines()
    require(changed == ["src/memory_book/scoped.py", "src/memory_book/store.py"], "Candidate includes another runtime change")
    binding = {"schema_version": 1, "protocol": PROTOCOL, "created_at": now(),
        "plan_sha256": sha(PLAN.read_bytes()), "modes": modes, "evaluator_files_sha256": helper_hashes(),
        "calls": declaration["quality_candidate"]["development"]["calls"],
        "status": "bound-before-any-project-statistics-quality-scoring"}
    write_json(path, binding)
    print(canonical({"binding": str(path), "sha256": sha(path.read_bytes()), "source_commits": [BASELINE_COMMIT, CANDIDATE_COMMIT]}))


def registered(binding_path, *, committed=True):
    declaration = plan()
    binding = json.loads(binding_path.read_text())
    require(binding["protocol"] == PROTOCOL and binding["plan_sha256"] == sha(PLAN.read_bytes())
            and binding["calls"] == 8082 and set(binding["modes"]) == set(MODES), "Binding/plan changed")
    require([(binding["modes"][m]["commit"], binding["modes"][m]["source_sha256"]) for m in MODES]
            == [(BASELINE_COMMIT, BASELINE_HASH), (CANDIDATE_COMMIT, CANDIDATE_HASH)], "Runtime pins changed")
    require(binding["evaluator_files_sha256"] == helper_hashes(), "Bound evaluators changed")
    if committed:
        relative = binding_path.resolve().relative_to(ROOT).as_posix()
        require(git("show", "HEAD:" + relative) == binding_path.read_bytes(), "Commit the binding before scoring")
        for name, expected in binding["evaluator_files_sha256"].items():
            require(sha(git("show", "HEAD:" + name)) == expected, "Commit every evaluator before scoring: " + name)
    return declaration, binding


def verify_source(source, mode, binding):
    package = source.resolve() / "memory_book"
    provenance = checkout_provenance(package)
    expected = binding["modes"][mode]
    actual = {"src/memory_book/" + p.relative_to(package).as_posix(): sha(p.read_bytes()) for p in package.rglob("*.py")}
    require(provenance["commit_identifies_source"] and provenance["git_commit"] == expected["commit"]
            and engine_source_hash(package) == expected["source_sha256"]
            and actual == expected["runtime_files_sha256"], "Worker source does not match its frozen commit")
    return {"source_sha256": expected["source_sha256"], "provenance": provenance}


def dataset_for(name, directory, declaration):
    # Reuse only the existing old-cohort loader. It filters old Hotpot IDs
    # before conversion and never imports a round2/new-selection loader.
    adapted = {"cohorts": [{**c, "corpus": CORPORA[c["name"]][0], "split": CORPORA[c["name"]][1]}
                            for c in declaration["cohorts"]]}
    return old_dataset_for(name, directory, adapted)


def scope_state(book, mode):
    if mode == MODES[1]:
        from memory_book.scoped import state
        return state(book.db)
    pages = book.db.execute("PRAGMA temp.page_count").fetchone()[0]
    size = book.db.execute("PRAGMA temp.page_size").fetchone()[0]
    free = book.db.execute("PRAGMA temp.freelist_count").fetchone()[0]
    return {"initialized": False, "policy_version": None, "project": None, "revision": None,
        "page_count": 0, "builds": 0, "switches": 0, "last_build_ms": 0.0, "total_build_ms": 0.0,
        "temporary_storage": {"page_count": pages, "page_size": size, "freelist_count": free,
            "allocated_bytes": pages * size, "live_bytes": (pages - free) * size,
            "temp_store_pragma": book.db.execute("PRAGMA temp_store").fetchone()[0],
            "boundary": "Whole SQLite TEMP database; allocated includes free pages; not process RSS or physical disk bytes."}}


def scope_event(before, after, mode, *, needed=True, applied=True):
    count = after["builds"] - before["builds"]
    require(count in (0, 1), "Unexpected number of derived-index builds in one recall")
    if mode == MODES[0]:
        require(before["builds"] == after["builds"] == 0, "Default path built scoped indexes")
        kind = "disabled"
    elif not applied:
        require(count == 0 and before == after, "Unscoped global recall changed the derived project state")
        kind = "unscoped_global"
    elif count:
        kind = ("cold_build" if not before["initialized"] else
                "project_switch" if before["project"] != after["project"] else "revision_rebuild")
    else:
        kind = "reuse" if needed else "not_used"
    return {"kind": kind, "builds": count, "build_ms": after["last_build_ms"] if count else 0.0,
            "before": before, "after": after}


def summarize(rows):
    groups, events = defaultdict(list), defaultdict(list)
    for row in rows:
        for group in row["diagnostic_groups"]:
            groups[group].append(row)
        events[row["scope_cost"]["kind"]].append(row)
    return {"metrics": summarize_rows(rows),
        "by_group": {name: summarize_rows(values) for name, values in sorted(groups.items())},
        "latency": {**latency_summary([r["elapsed_ms"] for r in rows]), "p99_ms": percentile([r["elapsed_ms"] for r in rows], .99)} if rows else None,
        "mean_returned_payload_tokens": {e: statistics.fmean(r["returned_payload_tokens"][e] for r in rows) for e in ENCODINGS} if rows else None,
        "unsupported_nonempty": sum(not r["answerable"] and r["nonempty"] for r in rows),
        "invariants": {key: sum(r[key] for r in rows) for key in INVARIANTS},
        "scope_costs": {"builds": sum(r["scope_cost"]["builds"] for r in rows),
            "build_ms": sum(r["scope_cost"]["build_ms"] for r in rows),
            "by_event": {name: {"calls": len(values), "recall_latency": latency_summary([r["elapsed_ms"] for r in values]),
                "build_ms": sum(r["scope_cost"]["build_ms"] for r in values)} for name, values in sorted(events.items())},
            "peak_allocated_temp_bytes": max((r["scope_cost"]["after"]["temporary_storage"]["allocated_bytes"] for r in rows), default=0),
            "peak_observed_rss_bytes": max((r["memory_after"]["rss_bytes"] for r in rows), default=0),
            "process_hwm_bytes": max((r["memory_after"]["hwm_bytes"] for r in rows), default=0)}}


class Ledger:
    def __init__(self, path):
        require(not path.exists(), "Never overwrite a worker attempt ledger")
        self.stream = path.open("x", encoding="utf-8")
        self.sequence = 0

    def append(self, event):
        self.stream.write(canonical({"sequence": self.sequence, "at": now(), **event}) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.sequence += 1

    def close(self):
        self.stream.close()


def worker(args):
    declaration, binding = registered(args.binding)
    source = verify_source(args.engine_src, args.mode, binding)
    sys.path.insert(0, str(args.engine_src.resolve()))
    import memory_book
    from memory_book import MemoryBook
    from memory_book.text import query_terms
    require(Path(memory_book.__file__).resolve().parent == (args.engine_src / "memory_book").resolve(), "Wrong runtime was imported")
    data = dataset_for(args.cohort, args.data_dir, declaration)
    started = time.perf_counter_ns()
    counters = {encoding: TokenCounter(encoding) for encoding in ENCODINGS}
    tokenizer_ms = (time.perf_counter_ns() - started) / 1e6
    require({counter.version for counter in counters.values()} == {"0.12.0"}, "Unexpected tokenizer version")
    hashes = helper_hashes()
    sources = original_turn_texts(data)
    report = {"mode": args.mode, "cohort": args.cohort, "status": "running", "started_at": now(),
        "source": source, "dataset": data.description(), "query_ids": sorted(c.id for c in data.queries),
        "query_ids_original_order": [c.id for c in data.queries], "evaluator_hashes": hashes,
        "configurations": [], "error": None, "tokenizer_initialize_ms": tokenizer_ms,
        "binding_sha256": sha(args.binding.read_bytes())}
    write_json(args.output, report, compressed=True)
    ledger = Ledger(args.ledger)
    try:
        with tempfile.TemporaryDirectory(prefix="round3-project-stats-") as temporary:
            database = Path(temporary) / "memory.db"
            started = time.perf_counter_ns()
            book = MemoryBook(database, max_page_chars=900, cache_size=0)
            report["fresh_connection_initialize_ms"] = (time.perf_counter_ns() - started) / 1e6
            with book:
                report["memory_after_connection"] = rss()
                started = time.perf_counter_ns()
                for session in data.sessions:
                    book.ingest(session)
                report["ingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["memory_after_ingestion"] = rss()
                report["storage_after_ingestion"] = storage(book.db, database)
                report["indexed_content"] = indexed_content(book.db)
                original = source_snapshot(book.db)
                environment = {**os.environ, "PYTHONPATH": str(args.engine_src.resolve()), "PYTHONDONTWRITEBYTECODE": "1"}
                environment.pop("GH_TOKEN", None)
                environment.pop("GITHUB_TOKEN", None)
                started = time.perf_counter_ns()
                cli = subprocess.run([sys.executable, "-m", "memory_book", "--db", str(database), "stats"],
                    cwd=temporary, env=environment, check=True, capture_output=True, timeout=60)
                report["cli_stats_process_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["cli_stats_stdout_sha256"] = sha(cli.stdout)
                report["cli_boundary"] = "One real stats command: Python startup/import, new connection and stats; no recall or scoped-index construction. The research opt-in has no CLI/MCP parameter."
                pages = {r["id"]: r["content"] for r in book.db.execute("SELECT id,content FROM pages")}
                chapters = [tuple(r) for r in book.db.execute("SELECT project_id,external_id,chapter_id FROM sessions")]
                groups = {case.id: diagnostics(case, chapters) for case in data.queries}
                query_has_terms = {case.id: bool(query_terms(case.query)) for case in data.queries}
                report["scope_initial"] = scope_state(book, args.mode)
                for budget in BUDGETS:
                    config = {"budget_chars": 8000, "budget_tokens": budget, "tokenizer": "cl100k_base", "rows": []}
                    report["configurations"].append(config)
                    cases = list(data.queries)
                    random.Random(31061).shuffle(cases)
                    for case in cases:
                        attempt = {"query_id": case.id, "budget_tokens": budget, "status": "started"}
                        report["last_attempt"] = attempt
                        ledger.append(attempt)
                        before = scope_state(book, args.mode)
                        require(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0, "Result cache is not empty")
                        applied = args.mode == MODES[1] and case.project is not None
                        options = {"project_local_fts_statistics": True} if applied else {}
                        started = time.perf_counter_ns()
                        response = book.recall(case.query, project=case.project, budget_chars=8000,
                            budget_tokens=budget, tokenizer="cl100k_base", limit=5,
                            use_cache=False, coverage=False, semantic=False, **options)
                        elapsed = (time.perf_counter_ns() - started) / 1e6
                        after = scope_state(book, args.mode)
                        row = score_row(case, response, sources, counters, public=True)
                        context_tokens = row["context_tokens"]["cl100k_base"]
                        payload = canonical(response)
                        row.update(groups[case.id], elapsed_ms=elapsed,
                            context_sha256=sha(response["context"].encode()), block_hashes=block_ids(response),
                            payload_sha256=sha(payload.encode()), non_timing_payload_sha256=digest({k: v for k, v in response.items() if k != "latency_ms"}),
                            returned_payload_tokens={e: c.count(payload) for e, c in counters.items()},
                            scope_cost=scope_event(before, after, args.mode, needed=query_has_terms[case.id], applied=applied), memory_after=rss(),
                            statistics_applied=applied,
                            query_has_terms=query_has_terms[case.id], archive_revision=response["revision"],
                            token_budget_violation=context_tokens > budget,
                            character_budget_violation=len(response["context"]) > 8000,
                            source_span_errors=source_errors(response, sources), page_projection_errors=page_projection_errors(response, pages),
                            token_metadata_error=any((response.get("context_tokens") != context_tokens,
                                response.get("tokenizer") != "cl100k_base", response.get("budget_tokens") != budget,
                                response.get("tokenizer_version") != "0.12.0")),
                            semantic_metadata_error="semantic" in response,
                            statistics_metadata_error=(response.get("project_local_fts_statistics", False) is not applied)
                                or (applied and query_has_terms[case.id] and
                                    (after["project"] != case.project or after["revision"] != response["revision"] or after["policy_version"] != 1)),
                            cache_hit_error=bool(response.get("cache_hit")) or book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] != 0,
                            scope_errors=(sum(ref["project"] != case.project for item in response["results"] for ref in item["source_refs"])
                                + sum(r["breadcrumb"][0]["id"] != case.project for r in response["results"]))
                                if case.project is not None else 0)
                        config["rows"].append(row)
                        report["last_attempt"] = {**attempt, "status": "completed"}
                        ledger.append({**attempt, "status": "completed", "row_sha256": digest(row)})
                        require(not any(row[k] for k in INVARIANTS) and not row["budget_violation"]
                                and row["context_size_consistent"], "A source, scope, budget, cache or mode invariant failed")
                        if len(config["rows"]) % 25 == 0:
                            write_json(args.output, report, compressed=True)
                    config.update(summarize(config["rows"]))
                    write_json(args.output, report, compressed=True)
                    print(canonical({"cohort": args.cohort, "mode": args.mode, "budget_tokens": budget, "completed": len(config["rows"])}), flush=True)
                report["originals_unchanged"] = original == source_snapshot(book.db)
                report["indexed_content_after"] = indexed_content(book.db)
                report["cache_rows"] = book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0]
                report["scope_final"] = scope_state(book, args.mode)
                report["storage_after_calls"] = storage(book.db, database)
                report["memory_after_calls"] = rss()
        report["source_sha256_after"] = engine_source_hash(args.engine_src / "memory_book")
        report["evaluator_unchanged"] = hashes == helper_hashes()
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__})
        raise
    finally:
        ledger.close()
        report["ledger_sha256"] = sha(args.ledger.read_bytes())
        report["finished_at"] = now()
        write_json(args.output, report, compressed=True)
    return report


def expected_order():
    return [(cohort, mode) for index, cohort in enumerate(COHORTS)
            for mode in (MODES if index % 2 == 0 else tuple(reversed(MODES)))]


def ledger_errors(worker, path):
    issues = []
    if not path.exists() or sha(path.read_bytes()) != worker.get("ledger_sha256"):
        return ["ledger_hash_or_missing"]
    events = [json.loads(line) for line in path.read_text().splitlines()]
    rows = [(config["budget_tokens"], row) for config in worker["configurations"] for row in config["rows"]]
    if len(events) != len(rows) * 2 or [e["sequence"] for e in events] != list(range(len(events))):
        return ["ledger_attempt_count"]
    for index, (budget, row) in enumerate(rows):
        started, completed = events[2 * index:2 * index + 2]
        common = {"query_id": row["id"], "budget_tokens": budget}
        if (any(started.get(k) != v or completed.get(k) != v for k, v in common.items())
                or started.get("status") != "started" or completed.get("status") != "completed"
                or completed.get("row_sha256") != digest(row)):
            issues.append("ledger_attempt_identity")
    return sorted(set(issues))


def validate(report, *, ledger_root=None):
    declaration, binding = report["plan"], report["binding"]
    issues, common, cases, unscoped = [], {}, {}, {}
    workers = report["workers"]
    observed = [(w["cohort"], w["mode"]) for w in workers]
    if observed != expected_order():
        issues.append("worker_matrix_or_order")
    if report.get("error") or not report.get("evaluator_unchanged"):
        issues.append("incomplete_or_changed_evaluator")
    for w in workers:
        name, mode = w["cohort"], w["mode"]
        identity = name + "/" + mode
        if name not in COHORTS or mode not in MODES:
            issues.append("unknown_worker")
            continue
        if w["status"] != "completed" or w.get("worker_exit_code") != 0:
            issues.append(identity + ":incomplete")
            continue
        registered_cohort = next(c for c in declaration["cohorts"] if c["name"] == name)
        source = binding["modes"][mode]
        if (w["source"]["source_sha256"] != source["source_sha256"]
                or w["source_sha256_after"] != source["source_sha256"]
                or w["source"]["provenance"]["git_commit"] != source["commit"]
                or not w["source"]["provenance"]["commit_identifies_source"]):
            issues.append(identity + ":source")
        if (w["dataset"]["sha256"] != registered_cohort["sha256"]
                or w["dataset"]["queries"] != registered_cohort["queries"]
                or len(w["query_ids"]) != registered_cohort["queries"]
                or len(set(w["query_ids"])) != registered_cohort["queries"]
                or sorted(w["query_ids_original_order"]) != w["query_ids"]):
            issues.append(identity + ":corpus")
        if (not w["originals_unchanged"] or w["indexed_content"] != w["indexed_content_after"]
                or w["cache_rows"] != 0 or not w["evaluator_unchanged"]
                or w["evaluator_hashes"] != report["evaluator_hashes"]
                or w["binding_sha256"] != report["binding_sha256"]):
            issues.append(identity + ":source_index_cache_or_evaluator")
        archive = {k: w[k] for k in ("query_ids", "query_ids_original_order", "indexed_content")}
        if name in common and common[name] != archive:
            issues.append(identity + ":different_common_archive")
        common.setdefault(name, archive)
        if [c["budget_tokens"] for c in w["configurations"]] != list(BUDGETS):
            issues.append(identity + ":budget_matrix")
        order = list(w["query_ids_original_order"])
        random.Random(31061).shuffle(order)
        previous = w["scope_initial"]
        if previous["initialized"] or previous["builds"] != 0:
            issues.append(identity + ":scope_was_prewarmed")
        for config in w["configurations"]:
            if (config["budget_chars"] != 8000 or config["tokenizer"] != "cl100k_base"
                    or [r["id"] for r in config["rows"]] != order):
                issues.append(identity + ":query_or_configuration")
            measured = summarize(config["rows"])
            if any(config.get(k) != value for k, value in measured.items()):
                issues.append(identity + ":aggregate")
            if (any(measured["invariants"].values()) or measured["metrics"]["budget_violations"]
                    or measured["metrics"]["context_size_mismatches"]):
                issues.append(identity + ":invariant")
            for row in config["rows"]:
                case_fields = ("id", "project", "category", "answerable", "required_evidence",
                               "diagnostic_groups", "query_has_terms", "required_chapters",
                               "query_term_coverage_by_required_text")
                case_identity = {key: row.get(key) for key in case_fields}
                case_key = (name, row["id"])
                if case_key in cases and cases[case_key] != case_identity:
                    issues.append(identity + ":case_or_group_identity")
                cases.setdefault(case_key, case_identity)
                ranks = row["evidence_ranks"]
                found = [rank for rank in ranks if rank is not None]
                if (row["required_evidence"] != len(ranks) or row["matched_evidence"] != len(found)
                        or row["complete"] != (bool(ranks) and len(ranks) == len(found))
                        or row["reciprocal_rank"] != (1 / min(found) if found else 0.0)
                        or any(type(rank) is not int or not 1 <= rank <= 5 for rank in found)):
                    issues.append(identity + ":evidence_count")
                if (not math.isfinite(row["elapsed_ms"]) or row["elapsed_ms"] < 0 or "query" in row
                        or row["context_tokens"]["cl100k_base"] > config["budget_tokens"]
                        or row["returned_characters"] > 8000 or row["result_count"] > 5):
                    issues.append(identity + ":timing_budget_or_publication")
                cost = row["scope_cost"]
                applied = mode == MODES[1] and row["project"] is not None
                if row["statistics_applied"] is not applied:
                    issues.append(identity + ":statistics_option")
                if cost["before"] != previous or cost != scope_event(cost["before"], cost["after"], mode, needed=row["query_has_terms"], applied=applied):
                    issues.append(identity + ":scope_cost_sequence")
                if row["project"] is None:
                    pair = (name, config["budget_tokens"], row["id"])
                    if pair in unscoped and row["non_timing_payload_sha256"] != unscoped[pair]:
                        issues.append(identity + ":unscoped_payload_changed")
                    unscoped.setdefault(pair, row["non_timing_payload_sha256"])
                after = cost["after"]
                if after["total_build_ms"] != previous["total_build_ms"] + cost["build_ms"]:
                    issues.append(identity + ":scope_build_total")
                for field in ("last_build_ms", "total_build_ms"):
                    if not isinstance(after[field], (int, float)) or not math.isfinite(after[field]) or after[field] < 0:
                        issues.append(identity + ":scope_timing")
                expected_switch = int(bool(cost["builds"]) and previous["initialized"] and previous["project"] != after["project"])
                if after["switches"] != previous["switches"] + expected_switch:
                    issues.append(identity + ":scope_switch_count")
                temporary = after["temporary_storage"]
                if (any(type(temporary[key]) is not int or temporary[key] < 0 for key in
                        ("page_count", "page_size", "freelist_count", "allocated_bytes", "live_bytes"))
                        or temporary["freelist_count"] > temporary["page_count"]
                        or temporary["allocated_bytes"] != temporary["page_count"] * temporary["page_size"]
                        or temporary["live_bytes"] != (temporary["page_count"] - temporary["freelist_count"]) * temporary["page_size"]
                        or any(type(row["memory_after"][key]) is not int or row["memory_after"][key] < 0
                               for key in ("rss_bytes", "hwm_bytes"))):
                    issues.append(identity + ":memory_or_temp_storage")
                if (applied and row["query_has_terms"] and
                        (after["project"] != row["project"] or after["revision"] != row["archive_revision"]
                         or after["policy_version"] != 1 or not after["initialized"])):
                    issues.append(identity + ":scope_identity")
                previous = after
        if previous != w["scope_final"]:
            issues.append(identity + ":scope_final")
        if ledger_root is not None:
            issues.extend(identity + ":" + item for item in ledger_errors(w, ledger_root / w["ledger_file"]))
    applied_calls = sum(row["statistics_applied"] for worker in workers for config in worker["configurations"] for row in config["rows"])
    candidate_unscoped = sum(row["project"] is None for worker in workers if worker["mode"] == MODES[1]
                            for config in worker["configurations"] for row in config["rows"])
    # The recorded plan fixes the real counts. Smaller fabricated fixtures use
    # this same validator without pretending to be the 8,082-call experiment.
    if [c["queries"] for c in declaration["cohorts"]] == [168, 36, 1015, 128] and len(workers) == 8:
        if applied_calls != 4017 or candidate_unscoped != 24:
            issues.append("applied_or_unscoped_call_counts")
    return {"passed": not issues, "issues": sorted(set(issues)), "workers": len(workers), "expected_workers": 8,
        "calls": sum(len(c["rows"]) for w in workers for c in w["configurations"]),
        "expected_calls": sum(c["queries"] for c in declaration["cohorts"]) * 3 * 2,
        "candidate_applied_calls": applied_calls, "candidate_unscoped_global_calls": candidate_unscoped}


def comparisons(report):
    result = []
    workers = {(w["cohort"], w["mode"]): w for w in report["workers"] if w["status"] == "completed"}
    for cohort in COHORTS:
        if any((cohort, mode) not in workers for mode in MODES):
            continue
        old = {c["budget_tokens"]: c for c in workers[(cohort, MODES[0])]["configurations"]}
        new = {c["budget_tokens"]: c for c in workers[(cohort, MODES[1])]["configurations"]}
        for budget in BUDGETS:
            if budget not in old or budget not in new:
                continue
            before, after = old[budget], new[budget]
            require(set(before["by_group"]) == set(after["by_group"]), "Paired groups differ")
            fields = ("metrics", "latency", "mean_returned_payload_tokens", "unsupported_nonempty", "scope_costs")
            result.append({"cohort": cohort, "budget_tokens": budget,
                "baseline": {k: before[k] for k in fields}, "candidate": {k: after[k] for k in fields},
                "by_group": {g: {"before": before["by_group"][g], "after": after["by_group"][g]} for g in sorted(before["by_group"])},
                "paired_changes": paired_changes(before["rows"], after["rows"])})
    return result


def screen(cells, *, valid):
    if not valid:
        return {"status": "incomplete_or_invalid", "qualified": False, "losses": [], "gains": []}
    require(len(cells) == 12 and {(c["cohort"], c["budget_tokens"]) for c in cells}
            == {(cohort, cap) for cohort in COHORTS for cap in BUDGETS}, "Need all 12 registered cells")
    losses, gains = [], []
    for cell in cells:
        axis = {k: cell[k] for k in ("cohort", "budget_tokens")}
        for metric in ("complete_evidence_rate", "evidence_recall"):
            before, after = cell["baseline"]["metrics"][metric], cell["candidate"]["metrics"][metric]
            if before is not None:
                require(after is not None, "Candidate lost a defined metric")
                if after < before:
                    losses.append({**axis, "group": "all", "metric": metric, "before": before, "after": after})
                if after > before:
                    gains.append({**axis, "metric": metric, "before": before, "after": after})
        if cell["candidate"]["unsupported_nonempty"] > cell["baseline"]["unsupported_nonempty"]:
            losses.append({**axis, "group": "unsupported", "metric": "nonempty_count",
                "before": cell["baseline"]["unsupported_nonempty"], "after": cell["candidate"]["unsupported_nonempty"]})
        if cell["budget_tokens"] == 512:
            for group in GROUPS:
                values = cell["by_group"].get(group)
                if values is None or values["before"]["queries"] < 10:
                    continue
                for metric in ("complete_evidence_rate", "evidence_recall"):
                    before, after = values["before"][metric], values["after"][metric]
                    if before is not None and after < before:
                        losses.append({**axis, "group": group, "metric": metric, "before": before, "after": after})
    qualified = not losses and bool(gains)
    return {"status": "qualified_for_independent_validation" if qualified else "rejected_loss_or_no_gain",
        "qualified": qualified, "losses": losses, "gains": gains, "individual_zero_loss_required": False,
        "default_changed": False, "development_timing_is_not_a_speed_claim": True}


def summary(report, raw, compressed):
    value = {k: v for k, v in report.items() if k != "workers"}
    value["workers"] = [{**{k: v for k, v in w.items() if k not in ("configurations", "query_ids", "query_ids_original_order")},
        "configurations": [{k: v for k, v in config.items() if k != "rows"} for config in w["configurations"]]}
        for w in report["workers"]]
    return {**value, "full_report_sha256": sha(raw), "compressed_report_sha256": sha(compressed)}


def markdown(report):
    lines = ["# Project-local FTS statistics: registered old-data screen", "",
        "One opt-in candidate; unchanged global default. Four old development/regression cohorts, "
        "8,000 characters, top 5 and cl100k_base token limits. These are strict source-evidence measurements, "
        "not answer accuracy or a new-domain/generalization claim. The eight unscoped synthetic queries "
        "remain in every budget and use the unchanged global path in both modes; no project is inferred.", "",
        "Integrity: **" + ("PASS" if report["validation"]["passed"] else "INCOMPLETE / FAIL") + "**. "
        "Gate: **" + report["screening"]["status"] + "**.", "",
        "| Cohort | Tokens | Complete global / local | Evidence global / local | Complete gains / losses | Annotation gains / losses | p50 global / local ms | p95 global / local ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cell in report["comparisons"]:
        old, new, changes = cell["baseline"], cell["candidate"], cell["paired_changes"]
        percentage = lambda key: f"{old['metrics'][key]:.2%} / {new['metrics'][key]:.2%}"
        lines.append(f"| {cell['cohort']} | {cell['budget_tokens']} | {percentage('complete_evidence_rate')} | "
            f"{percentage('evidence_recall')} | {len(changes['complete_question_gains'])} / {len(changes['complete_question_losses'])} | "
            f"{len(changes['annotation_gains'])} / {len(changes['annotation_losses'])} | "
            f"{old['latency']['p50_ms']:.3f} / {new['latency']['p50_ms']:.3f} | "
            f"{old['latency']['p95_ms']:.3f} / {new['latency']['p95_ms']:.3f} |")
    lines += ["", "## Costs and their boundaries", "",
        "Recall wall time includes every cold build, switch/rebuild and marker update. Diagnostic build times "
        "exclude the final marker write/savepoint release; complete recall timing includes them. Tokenizers are "
        "initialized before calls. All states, individual call times and small/negative groups remain in raw records. "
        "This one-pass quality development run is not formal performance evidence.", "",
        "Native payload tokens count the complete canonical JSON response, including latency/cache metadata and "
        "the opt-in flag. Context tokens remain separate; neither is an MCP envelope or provider bill. "
        "CLI stats is a real new-process startup/connection/stats measurement, not an opt-in recall command. "
        "TEMP bytes mean SQLite logical allocated/live pages, not physical disk or process RSS.", "",
        "| Cohort | Mode | Connection ms | CLI stats ms | Ingestion ms | Derived builds / switches | Total build ms | Peak TEMP allocated bytes | Process HWM bytes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for worker in report["workers"]:
        if worker["status"] != "completed":
            continue
        configs, final = worker["configurations"], worker["scope_final"]
        lines.append(f"| {worker['cohort']} | {worker['mode']} | {worker['fresh_connection_initialize_ms']:.3f} | "
            f"{worker['cli_stats_process_ms']:.3f} | {worker['ingestion_ms']:.3f} | "
            f"{final['builds']} / {final['switches']} | {final['total_build_ms']:.3f} | "
            f"{max(c['scope_costs']['peak_allocated_temp_bytes'] for c in configs)} | {worker['memory_after_calls']['hwm_bytes']} |")
    lines += ["", "## Registered decision", "",
        "Every one of the 12 cells must preserve complete evidence and annotation recall; unsupported nonempty "
        "responses cannot increase. At 512 tokens, primary groups with at least 10 questions must also preserve both "
        "metrics. At least one aggregate metric must improve. Per-question losses are retained and are not silently "
        "cancelled in reporting; the registered rule is an aggregate/group gate, not individual zero-loss.", "",
        f"Declared loss checks: {len(report['screening']['losses'])}; aggregate improvements: {len(report['screening']['gains'])}.",
        "A rejection ends this candidate under the registered protocol. No new threshold, novelty variant, "
        "source update or new-selection inspection is permitted by this runner.", ""]
    return "\n".join(lines)


def result_paths(output):
    prefix = str(output).removesuffix(".json.gz")
    return (output, Path(prefix + ".summary.json"), Path(prefix + ".md"))


def save_report(output, report):
    report["validation"] = validate(report, ledger_root=output.parent)
    report["comparisons"] = comparisons(report)
    report["screening"] = screen(report["comparisons"], valid=report["validation"]["passed"])
    raw = write_json(output, report, compressed=True)
    _, summary_path, markdown_path = result_paths(output)
    write_json(summary_path, summary(report, raw, output.read_bytes()))
    markdown_path.write_text(markdown(report), encoding="utf-8")


def worker_paths(output, cohort, mode):
    prefix = output.name.removesuffix(".json.gz") + "-" + cohort + "-" + mode
    return output.with_name(prefix + ".worker.json.gz"), output.with_name(prefix + ".ledger.jsonl")


def publish(output, report, branch):
    require(branch.startswith("validation/round3-project-stats-"), "Publish only a new round3 project-statistics result branch")
    require(git("remote", "get-url", "origin").decode().strip() in
            ("https://github.com/Afloat16/AI-Memory-Book", "https://github.com/Afloat16/AI-Memory-Book.git",
             "git@github.com:Afloat16/AI-Memory-Book.git"), "Publication origin is not the authorized repository")
    subprocess.run(["git", "check-ref-format", "--branch", branch], cwd=ROOT, check=True, capture_output=True)
    paths = list(result_paths(output))
    for cohort, mode in expected_order():
        paths.extend(p for p in worker_paths(output, cohort, mode) if p.exists())
    relative = [p.resolve().relative_to(ROOT).as_posix() for p in paths]
    require(all(p.startswith("benchmarks/reports/round3-project-stats-") for p in relative), "Publication path is outside this experiment")
    staged = set(git("diff", "--cached", "--name-only").decode().splitlines())
    require(staged <= set(relative), "Unrelated staged changes must not enter a result commit")
    subprocess.run(["git", "add", "--", *relative], cwd=ROOT, check=True)
    if git("diff", "--cached", "--name-only").strip():
        subprocess.run(["git", "-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m",
            "bench: preserve registered project-statistics quality checkpoint"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + branch], cwd=ROOT, check=True)


def adopt_worker(raw_path, ledger_path, exit_code):
    compressed = raw_path.read_bytes()
    worker = json.loads(gzip.decompress(compressed))
    worker["files"] = {"raw": raw_path.name, "raw_sha256": sha(compressed), "ledger": ledger_path.name}
    worker["ledger_file"] = ledger_path.name
    worker["worker_exit_code"] = exit_code
    return worker


def verify_worker_files(worker, directory):
    files = worker["files"]
    require(all(Path(files[key]).name == files[key] and "\\" not in files[key] for key in ("raw", "ledger")),
            "Worker artifact name is not a local filename")
    raw_path, ledger_path = directory / files["raw"], directory / files["ledger"]
    raw = raw_path.read_bytes()
    require(sha(raw) == files["raw_sha256"], "Saved worker gzip changed")
    value = {k: v for k, v in worker.items() if k not in ("files", "ledger_file", "worker_exit_code")}
    require(json.loads(gzip.decompress(raw)) == value, "Aggregated worker differs from its original gzip")
    require(not ledger_errors(worker, ledger_path), "Worker attempt ledger differs from raw rows")


def audit(output, binding_path):
    declaration, binding = registered(binding_path)
    compressed = output.read_bytes()
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    require(report["plan"] == declaration and report["binding"] == binding
            and report["binding_sha256"] == sha(binding_path.read_bytes())
            and report["evaluator_hashes"] == helper_hashes(), "Recorded protocol/source/helper identity differs")
    for worker in report["workers"]:
        verify_worker_files(worker, output.parent)
    validation = validate(report, ledger_root=output.parent)
    require(report["validation"] == validation and validation["passed"], "Saved matrix is incomplete or invalid")
    require(report["comparisons"] == comparisons(report), "Paired comparison changed")
    require(report["screening"] == screen(report["comparisons"], valid=True), "Saved quality gate changed")
    _, summary_path, markdown_path = result_paths(output)
    require(json.loads(summary_path.read_text()) == summary(report, raw, compressed), "Saved summary/hash changed")
    require(markdown_path.read_text() == markdown(report), "Saved Markdown changed")
    print(canonical({"audit": "passed", "calls": validation["calls"], "workers": validation["workers"],
                     "screen": report["screening"]["status"], "full_report_sha256": sha(raw)}))


def run(args):
    declaration, binding = registered(args.binding)
    paths = {MODES[0]: args.baseline_src.resolve(), MODES[1]: args.candidate_src.resolve()}
    sources = {mode: verify_source(path, mode, binding) for mode, path in paths.items()}
    hashes = helper_hashes()
    if args.resume:
        require(args.output.exists(), "No checkpoint exists to resume")
        report = json.loads(gzip.decompress(args.output.read_bytes()))
        require(report["plan"] == declaration and report["binding"] == binding
                and report["binding_sha256"] == sha(args.binding.read_bytes())
                and report["evaluator_hashes"] == hashes and report["sources"] == sources,
                "Resume cannot change sources, data axes or evaluator")
        observed = [(w["cohort"], w["mode"]) for w in report["workers"]]
        require(observed == expected_order()[:len(observed)] and not report.get("error"),
                "Resume requires an intact completed prefix, not a failed/repeated attempt")
        for saved in report["workers"]:
            require(saved["status"] == "completed" and saved["worker_exit_code"] == 0, "Do not rerun a failed worker")
            verify_worker_files(saved, args.output.parent)
        report.setdefault("resume_events", []).append({"at": now(), "preserved_complete_workers": len(observed)})
    else:
        require(not args.output.exists(), "Preserve previous results; explicitly resume a complete prefix or use a new authorized attempt")
        require(not any(p.exists() for cohort, mode in expected_order() for p in worker_paths(args.output, cohort, mode)),
                "Worker artifacts already exist for this prefix")
        report = {"protocol": PROTOCOL, "started_at": now(), "plan": declaration, "binding": binding,
            "binding_sha256": sha(args.binding.read_bytes()), "sources": sources, "evaluator_hashes": hashes,
            "evaluator_unchanged": False, "evaluator_commit": git("rev-parse", "HEAD").decode().strip(),
            "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                "platform": platform.platform(), "cpu_count": os.cpu_count(), "tiktoken": importlib.metadata.version("tiktoken")},
            "workers": [], "attempted_workers": [], "error": None,
            "cost_boundary": "Complete native recall wall time, including every TEMP build/switch/rebuild. Source scoring, state/RSS reads, token recounting, ledger/checkpoint I/O and ingestion are outside call timing. Both encodings count full canonical native JSON including latency/cache metadata; no MCP or provider-billing claim.",
            "data_boundary": "Only the four registered old cohorts. The old Hotpot128 loader validates and loads only the previously filtered rows. No new selection is loaded.",
            "cold_boundary": "No derived-index prewarming. Reading the initial diagnostic state may initialize empty SQLite TEMP bookkeeping, but creates no derived FTS tables. Tokenizers are loaded separately. No OS-cold-cache claim."}
    save_report(args.output, report)
    try:
        for cohort, mode in expected_order()[len(report["workers"]):]:
            raw_path, ledger_path = worker_paths(args.output, cohort, mode)
            require(not raw_path.exists() and not ledger_path.exists(), "Unadopted worker attempt exists; preserve it for explicit recovery")
            attempt = {"cohort": cohort, "mode": mode, "status": "started", "started_at": now()}
            report["attempted_workers"].append(attempt)
            save_report(args.output, report)
            exit_code = None
            try:
                environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
                environment.pop("GH_TOKEN", None)
                environment.pop("GITHUB_TOKEN", None)
                process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker",
                    "--binding", str(args.binding.resolve()), "--engine-src", str(paths[mode]), "--mode", mode,
                    "--cohort", cohort, "--data-dir", str(args.data_dir.resolve()), "--output", str(raw_path.resolve()),
                    "--ledger", str(ledger_path.resolve())], env=environment, cwd=ROOT)
                exit_code = process.returncode
                attempt["exit_code"] = exit_code
                attempt["status"] = "completed" if exit_code == 0 else "failed"
            finally:
                if exit_code is None:
                    attempt.update(status="interrupted", exit_code=None)
                attempt["finished_at"] = now()
                if raw_path.exists():
                    report["workers"].append(adopt_worker(raw_path, ledger_path, exit_code))
                save_report(args.output, report)
                if args.publish_branch:
                    publish(args.output, report, args.publish_branch)
            require(exit_code == 0, "Worker failed; preserve the attempt and stop without rerunning it")
    except BaseException as error:
        report["error"] = {"type": type(error).__name__}
    report["evaluator_unchanged"] = hashes == helper_hashes()
    report["finished_at"] = now()
    save_report(args.output, report)
    if args.publish_branch:
        publish(args.output, report, args.publish_branch)
    print(canonical({"validation": report["validation"], "screen": report["screening"]["status"]}))
    return 0 if report["validation"]["passed"] and report["screening"]["qualified"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bind", "check", "prepare-data", "worker", "run", "audit"))
    parser.add_argument("--binding", type=Path, default=BINDING)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--engine-src", type=Path)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--cohort", choices=COHORTS)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--publish-branch")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "bind":
        make_binding(args.binding)
    elif args.command == "check":
        _, binding = registered(args.binding)
        print(canonical({"checked": True, "helper_files": len(binding["evaluator_files_sha256"]),
                         "source_commits": [binding["modes"][mode]["commit"] for mode in MODES]}))
    elif args.command == "prepare-data":
        require(args.data_dir is not None, "Require --data-dir")
        prepare_data(args.data_dir)
    elif args.command == "audit":
        require(args.output is not None, "Require --output")
        audit(args.output, args.binding)
    else:
        require(args.output is not None and args.output.name.endswith(".json.gz") and args.data_dir is not None,
                "Require a .json.gz --output and --data-dir")
        if args.command == "worker":
            require(all(value is not None for value in (args.engine_src, args.mode, args.cohort, args.ledger)), "Worker arguments missing")
            require(not args.output.exists() and not args.ledger.exists(), "Never replace worker artifacts")
            worker(args)
        else:
            require(args.baseline_src is not None and args.candidate_src is not None, "Use explicit pinned source worktrees")
            return run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
