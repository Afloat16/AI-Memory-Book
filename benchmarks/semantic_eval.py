"""Paired local semantic-versus-lexical retrieval, with durable query checkpoints.

Both modes use the same source runtime, token assembly and archive. Only the
explicit semantic candidate route differs. Source texts and queries stay in the
ignored state directory; exported reports contain IDs, metrics and hashes.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import sqlite3
import sys
import time

from benchmarks.native_budget_eval import block_ids, dataset_for, source_errors
from benchmarks.resume import _lock, _save
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
                                      latency_summary, score_row, summarize_rows)


VERSION = "semantic-paired-1"
MODES = ("lexical_native_token_budget", "semantic_native_token_budget")
PLAN = Path(__file__).with_name("semantic-final-plan.json")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def evaluator_sources():
    root = Path(__file__).parent
    names = ("semantic_eval.py", "native_budget_eval.py", "token_compare.py", "run.py",
             "component_eval.py", "data.py", "long_data.py", "public_data.py",
             "hotpot_data.py", "transfer_data.py", "query_guard.py", "resume.py",
             "semantic-final-plan.json", "experiments/semantic-local-plan.json")
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def source_snapshot(db):
    """Hash originals and source addresses, excluding caches and derived indexes."""
    return digest({table: [list(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
                   for table in ("projects", "chapters", "sessions", "turns", "sections", "pages")})


def page_projection_errors(response, pages):
    """Every returned excerpt must be a complete original page slice.

    Source-ref substring checks alone would allow extra invented text alongside
    one valid span. The runtime currently renders one contiguous excerpt per
    result, with optional boundary ellipses. Check all of it, not just a needle.
    """
    errors = 0
    for item in response["results"]:
        original = pages.get(item["id"])
        spans = item.get("excerpt_spans", [])
        if original is None or len(spans) != 1:
            errors += 1
            continue
        start, end = spans[0]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original):
            errors += 1
            continue
        source = original[start:end]
        rendered = ("…" if start else "") + source + ("…" if end < len(original) else "")
        if item["text"] not in (source, rendered):
            errors += 1
    return errors


def diagnostics(case, chapter_map):
    # Labels are only used by this evaluator, after recall. They never enter
    # ingestion, the embedding model, ranking, excerpt selection, or packing.
    from memory_book.text import terms
    query_terms = set(terms(case.query, query=True))
    evidence_terms = set(terms(" ".join(item.needle for item in case.required)))
    overlap = len(query_terms & evidence_terms) / len(query_terms) if query_terms and case.required else None
    chapters = {chapter for item in case.required
                for project, sid, chapter in chapter_map
                if sid == item.session_id and (case.project is None or project == case.project)}
    groups = ["all", "category:" + case.category]
    if overlap is not None and overlap <= .25:
        groups.append("low_lexical_overlap_le_0.25")
    if len(case.required) >= 2:
        groups.append("multiple_required_evidence")
    if len({item.session_id for item in case.required}) >= 2:
        groups.append("cross_session")
    if len(chapters) >= 2:
        groups.append("cross_chapter")
    return {"diagnostic_groups": groups, "query_term_coverage_by_required_text": overlap,
            "required_chapters": len(chapters)}


class Progress:
    """A committed SQLite row per attempt; interrupted work cannot look complete."""

    def __init__(self, path, identity):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS samples(
                seq INTEGER PRIMARY KEY, configuration TEXT NOT NULL, repetition INTEGER NOT NULL,
                query_id TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, elapsed_ms REAL, row_json TEXT, error TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS completed_sample ON samples(configuration,repetition,query_id,mode)
                WHERE status='completed';""")
        old = self.get("identity")
        if old is None:
            self.set("identity", identity)
        elif old != identity:
            self.db.close()
            raise RuntimeError("Semantic checkpoint identity changed; retain it and choose a new state directory")
        self.db.execute("UPDATE samples SET status='interrupted',finished_at=?,error=? WHERE status='running'",
                        (utc_now(), "Prior process ended before committing this sample; no latency inferred"))
        self.db.commit()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def completed(self):
        return {(r["configuration"], r["repetition"], r["query_id"], r["mode"])
                for r in self.db.execute("SELECT * FROM samples WHERE status='completed'")}

    def start(self, config, repetition, query_id, mode):
        cursor = self.db.execute("INSERT INTO samples(configuration,repetition,query_id,mode,status,started_at) VALUES(?,?,?,?,?,?)",
                                 (config, repetition, query_id, mode, "running", utc_now()))
        self.db.commit()
        return cursor.lastrowid

    def finish(self, seq, elapsed_ms, row):
        self.db.execute("UPDATE samples SET status='completed',finished_at=?,elapsed_ms=?,row_json=? WHERE seq=? AND status='running'",
                        (utc_now(), elapsed_ms, json.dumps(row, ensure_ascii=False), seq))
        self.db.commit()

    def fail(self, seq, exc):
        # Do not serialize exception text: a third-party tokenizer error could
        # include a query or a source passage. Type and attempt ID suffice.
        self.db.execute("UPDATE samples SET status='failed',finished_at=?,error=? WHERE seq=?",
                        (utc_now(), type(exc).__name__, seq))
        self.db.commit()

    def close(self):
        self.db.close()


def paired_changes(old_rows, new_rows):
    old = {row["id"]: row for row in old_rows}
    if old.keys() != {row["id"] for row in new_rows}:
        raise ValueError("Paired semantic modes have different query IDs")
    result = {key: [] for key in ("annotation_gains", "annotation_losses", "complete_question_gains",
                                 "complete_question_losses", "changed_contexts")}
    for row in new_rows:
        before = old[row["id"]]
        for index, (a, b) in enumerate(zip(before["evidence_ranks"], row["evidence_ranks"], strict=True)):
            if a is None and b is not None:
                result["annotation_gains"].append({"id": row["id"], "annotation": index})
            if a is not None and b is None:
                result["annotation_losses"].append({"id": row["id"], "annotation": index})
        if row["complete"] and not before["complete"]:
            result["complete_question_gains"].append(row["id"])
        if before["complete"] and not row["complete"]:
            result["complete_question_losses"].append(row["id"])
        if before["context_sha256"] != row["context_sha256"]:
            result["changed_contexts"].append(row["id"])
    return result


def summarize_samples(samples, query_ids, repeats):
    grouped = defaultdict(list)
    for sample in samples:
        grouped[sample["query_id"]].append(sample)
    if set(grouped) != set(query_ids) or any({x["repetition"] for x in values} != set(range(repeats))
                                           or len(values) != repeats for values in grouped.values()):
        raise ValueError("Incomplete or duplicated semantic measurement matrix")
    rows = [json.loads(next(s["row_json"] for s in grouped[qid] if s["repetition"] == 0)) for qid in query_ids]
    for row in rows:
        row["measurements"] = [{key: sample[key] for key in
                                ("seq", "repetition", "started_at", "finished_at", "elapsed_ms")}
                               for sample in sorted(grouped[row["id"]], key=lambda s: s["repetition"])]
    groups = defaultdict(list)
    for row in rows:
        for group in row["diagnostic_groups"]:
            groups[group].append(row)
    invariant_keys = ("token_budget_violation", "source_span_errors", "page_projection_errors", "token_metadata_error",
                      "scope_errors", "semantic_metadata_error")
    return {"metrics": summarize_rows(rows),
            "latency": latency_summary([s["elapsed_ms"] for s in samples]),
            "first_pass_latency": latency_summary([s["elapsed_ms"] for s in samples if s["repetition"] == 0]),
            "repeat_pass_latency": latency_summary([s["elapsed_ms"] for s in samples if s["repetition"] > 0]),
            "by_group": {group: summarize_rows(value) for group, value in sorted(groups.items())},
            "repeat_context_mismatches": sum(len({json.loads(s["row_json"])["context_sha256"] for s in values}) != 1
                                             for values in grouped.values()),
            "invariants": {key: sum(json.loads(s["row_json"])[key] for s in samples) for key in invariant_keys},
            "query_results": rows}


def build_report(progress, data, configs, args, source_after, evaluator_after, originals_after):
    identity = progress.get("identity")
    samples = [dict(row) for row in progress.db.execute("SELECT * FROM samples WHERE status='completed' ORDER BY seq")]
    failures = []
    configurations = []
    for config in configs:
        key = digest(config)
        modes = []
        for mode in MODES:
            selected = [s for s in samples if s["configuration"] == key and s["mode"] == mode]
            item = {"mode": mode, **summarize_samples(selected, [c.id for c in data.queries], args.repeats)}
            for name, value in {**item["invariants"], "repeat_context_mismatches": item["repeat_context_mismatches"],
                                **{k: item["metrics"][k] for k in ("budget_violations", "context_size_mismatches")}}.items():
                if value:
                    failures.append({**config, "mode": mode, "check": name, "observed": value})
            modes.append(item)
        configurations.append({**config, "modes": modes,
                               "paired_changes": paired_changes(modes[0]["query_results"], modes[1]["query_results"])})
    for name, same in (("source_unchanged", source_after == identity["runtime_source_sha256"]),
                       ("evaluator_unchanged", evaluator_after == identity["evaluator_files"]),
                       ("originals_unchanged", originals_after == progress.get("preparation")["originals_sha256"])):
        if not same:
            failures.append({"check": name})
    attempts = [dict(row) for row in progress.db.execute(
        "SELECT seq,configuration,repetition,query_id,mode,status,started_at,finished_at,error FROM samples WHERE status!='completed' ORDER BY seq")]
    return {"schema_version": 1, "evaluator": VERSION, "created_at_utc": utc_now(), "identity": identity,
            "dataset": data.description(), "preparation": progress.get("preparation"),
            "preparation_attempts": progress.get("preparation_attempts", []),
            "process_segments": progress.get("process_segments", []), "preserved_incomplete_attempts": attempts,
            "completed_samples": len(samples), "configurations": configurations,
            "source_sha256_after": source_after, "evaluator_files_after": evaluator_after,
            "originals_sha256_after": originals_after,
            "validation": {"passed": not failures, "failures": failures},
            "methodology": json.loads(PLAN.read_text())["methodology"]}


def markdown(report):
    lines = ["# Paired local semantic retrieval", "", f"Measurement validation: **{'PASS' if report['validation']['passed'] else 'FAIL'}**.", "",
             "The two modes share runtime, archive, budget assembly and source labels. Only the explicit semantic candidate route differs.", "",
             "| Mode | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | p50 ms | p95 ms |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for config in report["configurations"]:
        for mode in config["modes"]:
            m, latency = mode["metrics"], mode["latency"]
            lines.append(f"| {mode['mode']} | {config['tokenizer']} | {config['budget_tokens']} | {m['evidence_recall']:.2%} | {m['complete_evidence_rate']:.2%} | {m['mean_context_tokens'][config['tokenizer']]:.1f} | {latency['p50_ms']:.3f} | {latency['p95_ms']:.3f} |")
    lines.extend(["", "## Paired changes", "", "| Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |",
                  "|---:|---:|---:|---:|---:|"])
    for config in report["configurations"]:
        changes = config["paired_changes"]
        lines.append(f"| {config['budget_tokens']} | {len(changes['annotation_gains'])} | {len(changes['annotation_losses'])} | {len(changes['complete_question_gains'])} | {len(changes['complete_question_losses'])} |")
    preparation = report["preparation"]
    index = preparation["semantic_index"]
    lines.extend(["", "## Costs and interpretation", "",
                  f"Ingestion: {preparation['ingestion_ms']:.1f} ms. Model load: {index['model_load_ms']:.1f} ms. "
                  f"Index build: {index['build_ms']:.1f} ms; {index['windows']} windows, {index['vector_bytes']} vector bytes before SQLite overhead.", "",
                  "Query timings exclude model load, index construction, scoring and checkpoint I/O. Caches are disabled; first-pass timings follow explicit model loading/indexing, so they are not disk-cold latency. Resume segments are retained.", "",
                  "Low overlap and cross-chapter groups are evaluator diagnostics declared before scoring. Evidence metrics do not measure generated answers, semantic correctness, broad generalization or complete competitor workflows.", ""])
    return "\n".join(lines)


def write_report(report, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    compressed = Path(str(output) + ".json.gz")
    temporary = compressed.with_name(compressed.name + ".partial")
    temporary.write_bytes(gzip.compress(raw, mtime=0))
    temporary.replace(compressed)
    summary = json.loads(raw)
    for config in summary["configurations"]:
        for mode in config["modes"]:
            mode.pop("query_results")
    summary["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    _save(Path(str(output) + ".summary.json"), summary)
    target = Path(str(output) + ".md")
    temporary = target.with_name(target.name + ".partial")
    temporary.write_text(markdown(report), encoding="utf-8")
    temporary.replace(target)


def run(args):
    data = dataset_for(args)  # Fail on a wrong cohort before loading any engine/model.
    if len({case.id for case in data.queries}) != len(data.queries):
        raise ValueError("Semantic evaluation requires unique query IDs")
    sys.path.insert(0, str(args.engine_src.resolve()))
    from memory_book import MemoryBook
    from memory_book.semantic import verify_model_files
    import memory_book
    source = Path(memory_book.__file__).parent
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    if {c.version for c in counters.values()} != {"0.12.0"}:
        raise ValueError("Frozen semantic protocol requires tiktoken==0.12.0")
    configs = [{"budget_chars": args.budget_chars, "budget_tokens": tokens,
                "tokenizer": encoding, "limit": args.limit}
               for encoding in args.tokenizers for tokens in args.token_budgets]
    identity = {"evaluator": VERSION, "dataset_sha256": data.fingerprint,
                "runtime_source_sha256": engine_source_hash(source), "evaluator_files": evaluator_sources(),
                "model": verify_model_files(args.model_dir), "configurations": configs,
                "repeats": args.repeats, "seed": args.seed,
                "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                            "platform": platform.platform(), "packages": {name: importlib.metadata.version(name)
                            for name in ("tiktoken", "onnxruntime", "tokenizers", "numpy")}}}
    args.state_dir.mkdir(parents=True, exist_ok=True)
    sources = original_turn_texts(data)
    with _lock(args.state_dir / "semantic-evaluation"):
        progress = Progress(args.state_dir / "progress.sqlite3", identity)
        try:
            with MemoryBook(args.state_dir / "memory.db", max_page_chars=900, cache_size=0,
                            semantic_model_dir=args.model_dir) as book:
                segments = progress.get("process_segments", [])
                segment = {"started_at": utc_now(), "source_provenance": checkout_provenance(source)}
                segments.append(segment)
                progress.set("process_segments", segments)
                preparation = progress.get("preparation")
                if preparation is None:
                    attempts = progress.get("preparation_attempts", [])
                    if attempts and attempts[-1]["status"] == "running":
                        attempts[-1]["status"] = "interrupted"
                    attempt = {"status": "running", "started_at": utc_now()}
                    attempts.append(attempt)
                    progress.set("preparation_attempts", attempts)
                    start = time.perf_counter_ns()
                    for session in data.sessions:
                        book.ingest(session)
                    ingestion_ms = (time.perf_counter_ns() - start) / 1e6
                    originals = source_snapshot(book.db)
                    index = book.build_semantic_index()
                    if source_snapshot(book.db) != originals:
                        raise ValueError("Semantic indexing changed original rows or source addresses")
                    preparation = {"ingestion_ms": ingestion_ms, "semantic_index": index,
                                   "originals_sha256": originals, "engine_stats": book.stats(),
                                   "configured_summary_model_calls": 0, "ingestion_is_resume": len(attempts) > 1}
                    progress.set("preparation", preparation)
                    attempt.update(status="completed", finished_at=utc_now())
                    progress.set("preparation_attempts", attempts)
                else:
                    if source_snapshot(book.db) != preparation["originals_sha256"]:
                        raise RuntimeError("Persisted source archive changed; do not mix checkpoint measurements")
                    from memory_book.semantic import check_index
                    model = book._semantic_encoder()
                    check_index(book.db, book.revision, model)
                    segment["resumed_model_load_ms"] = model.load_ms
                    progress.set("process_segments", segments)
                chapters = [tuple(row) for row in book.db.execute("SELECT project_id,external_id,chapter_id FROM sessions")]
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                groups = {case.id: diagnostics(case, chapters) for case in data.queries}
                completed = progress.completed()
                for config in configs:
                    key = digest(config)
                    counter = counters[config["tokenizer"]]
                    for repetition in range(args.repeats):
                        cases = list(data.queries)
                        random.Random(args.seed + 1009 * repetition).shuffle(cases)
                        for position, case in enumerate(cases):
                            modes = MODES if (position + repetition) % 2 == 0 else MODES[::-1]
                            for mode in modes:
                                sample_key = (key, repetition, case.id, mode)
                                if sample_key in completed:
                                    continue
                                seq = progress.start(key, repetition, case.id, mode)
                                try:
                                    started = time.perf_counter_ns()
                                    response = book.recall(case.query, project=case.project, **config, use_cache=False,
                                                           semantic=mode == MODES[1])
                                    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
                                    row = score_row(case, response, sources, counters, public=True)
                                    row.update(groups[case.id], context_sha256=hashlib.sha256(response["context"].encode()).hexdigest(),
                                               block_hashes=block_ids(response),
                                               token_budget_violation=counter.count(response["context"]) > config["budget_tokens"],
                                               source_span_errors=source_errors(response, sources),
                                               page_projection_errors=page_projection_errors(response, pages),
                                               token_metadata_error=any((response.get("context_tokens") != counter.count(response["context"]),
                                                   response.get("tokenizer") != config["tokenizer"],
                                                   response.get("budget_tokens") != config["budget_tokens"],
                                                   response.get("tokenizer_version") != counter.version)),
                                               semantic_metadata_error=(response.get("semantic") is not True or
                                                   response.get("semantic_model_fingerprint") != book._semantic_model.fingerprint)
                                                   if mode == MODES[1] else "semantic" in response,
                                               scope_errors=sum(item["breadcrumb"][0]["id"] != case.project for item in response["results"])
                                                   if case.project is not None else 0)
                                    progress.finish(seq, elapsed_ms, row)
                                    completed.add(sample_key)
                                except BaseException as exc:
                                    progress.fail(seq, exc)
                                    raise
                            if position % 100 == 0:
                                print(json.dumps({"configuration": config, "repetition": repetition,
                                                  "position": position, "completed_samples": len(completed)}), flush=True)
                segment["finished_at"] = utc_now()
                progress.set("process_segments", segments)
                report = build_report(progress, data, configs, args, engine_source_hash(source), evaluator_sources(),
                                      source_snapshot(book.db))
                write_report(report, args.output)
                print(markdown(report), flush=True)
                return 0 if report["validation"]["passed"] else 2
        finally:
            progress.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-src", type=Path, default=Path("src"))
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--corpus", choices=("synthetic", "locomo", "transfer", "hotpotqa"), required=True)
    parser.add_argument("--split", choices=("development", "heldout"), default="development")
    parser.add_argument("--seed", type=int, default=61)
    parser.add_argument("--projects", type=int, default=8)
    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--locomo-path")
    parser.add_argument("--hotpot-path")
    parser.add_argument("--expected-queries", type=int, required=True)
    parser.add_argument("--expected-dataset-sha256", required=True)
    parser.add_argument("--budget-chars", type=int, default=8000)
    parser.add_argument("--token-budgets", type=int, nargs="+", default=[512, 1024, 2048])
    parser.add_argument("--tokenizers", choices=ENCODINGS, nargs="+", default=["cl100k_base"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.budget_chars < 128 or min(args.token_budgets) < 1 or args.repeats < 1 or not 1 <= args.limit <= 50:
        parser.error("Character cap >=128, positive token caps/repeats, and limit 1..50 are required")
    if len(set(args.token_budgets)) != len(args.token_budgets) or len(set(args.tokenizers)) != len(args.tokenizers):
        parser.error("Duplicate configurations are not allowed")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
