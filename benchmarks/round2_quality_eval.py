"""Frozen Q1 fusion experiment on old development/regression data only.

The three modes share one archive, one model/index, disabled caches and the
same token assembler. No new blind-validation data is accepted by this runner.
Exported rows contain identifiers, source coordinates and metrics, never text.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import gzip
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import subprocess
import sys
import time

from benchmarks import semantic_eval as common
from benchmarks.native_budget_eval import block_ids, dataset_for, source_errors
from benchmarks.resume import _lock, _save
from benchmarks.run import engine_source_hash, original_turn_texts, percentile
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
                                      score_row)

digest, utc_now = common.digest, common.utc_now
diagnostics, page_projection_errors = common.diagnostics, common.page_projection_errors
source_snapshot, paired_changes = common.source_snapshot, common.paired_changes
ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/round2-quality-plan.json"
VERSION = "round2-quality-q1-1"
MODES = ("lexical_native_token_budget", "legacy_rrf_k60", "q1_score_075")
BASELINE = "cb7486b4937a3ecb7ccbf94a746c0bbbf44eb41f"
RRF_K = 60
PUBLIC_ROW_FIELDS = frozenset({
    "id", "category", "project", "answerable", "required_evidence", "matched_evidence",
    "complete", "reciprocal_rank", "evidence_ranks", "stale_ranks", "stale_only", "stale_before_current",
    "nonempty", "returned_characters", "returned_utf8_bytes", "reported_context_chars",
    "context_size_consistent", "budget_violation", "estimated_tokens", "candidate_count", "result_count",
    "duplicate_source_characters", "result_ids", "context_tokens", "diagnostic_groups",
    "query_term_coverage_by_required_text", "required_chapters", "context_sha256", "block_hashes",
    "token_budget_violation", "source_span_errors", "page_projection_errors", "token_metadata_error",
    "semantic_metadata_error", "query_encoding_operations", "cache_hit_error", "returned_payload_tokens", "scope_errors"})


class Progress(common.Progress):
    def fail(self, seq, exc):
        super().fail(seq, exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            self.db.execute("UPDATE samples SET status='interrupted' WHERE seq=?", (seq,))
            self.db.commit()


def legacy_rrf(lexical: list[dict], semantic: list[dict]) -> list[dict]:
    """Registered equal-weight rank fusion; no answer labels or thresholds."""
    combined: dict[str, dict] = {}
    for route in (lexical, semantic):
        for rank, row in enumerate(route, 1):
            page_id = row["id"]
            if page_id not in combined:
                combined[page_id] = {**row, "score": 0.0}
            combined[page_id]["score"] += 1 / (RRF_K + rank)
            if "semantic_similarity" in row:
                combined[page_id]["semantic_similarity"] = row["semantic_similarity"]
    return sorted(combined.values(), key=lambda row: (-row["score"], row["id"]))


def function_body(source, name):
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.dump(ast.Module(body=function.body, type_ignores=[]), include_attributes=False)


def verify_reference():
    result = subprocess.run(["git", "show", BASELINE + ":src/memory_book/semantic.py"],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("The immutable legacy reference Git object is required")
    baseline = result.stdout
    expected = function_body(baseline, "fuse_candidates")
    if expected != function_body(inspect.getsource(legacy_rrf), "legacy_rrf"):
        raise ValueError("Legacy fusion differs from the original baseline function body")
    constants = {node.targets[0].id: ast.literal_eval(node.value)
                 for node in ast.parse(baseline).body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "RRF_K"}
    if constants != {"RRF_K": RRF_K}:
        raise ValueError("Legacy rank constant differs from the original baseline")
    return {"commit": BASELINE, "semantic_file_sha256": hashlib.sha256(baseline.encode()).hexdigest(),
            "fusion_ast_sha256": hashlib.sha256(expected.encode()).hexdigest(), "rrf_k": RRF_K,
            "control_scope": "Original RRF function inside the shared candidate runtime; not a separate whole-runtime comparison."}


def require_source(engine_src, imported_file):
    actual = Path(imported_file).resolve().parent
    expected = (Path(engine_src) / "memory_book").resolve()
    if actual != expected:
        raise RuntimeError("Imported engine is not the requested source checkout")
    return actual


def validate_arguments(args):
    plan = json.loads(PLAN.read_text())
    observed = {key: getattr(args, key) for key in
                ("budget_chars", "token_budgets", "tokenizers", "limit", "repeats")}
    expected = {key: plan["parameters"][key] for key in observed}
    if observed != expected or (args.seed, args.projects, args.max_queries) != (61, 8, 0):
        raise ValueError("All registered Q1 configuration axes must remain unchanged")
    cohorts = [cohort for cohort in plan["development_cohorts"] if cohort["corpus"] == args.corpus]
    if len(cohorts) != 1:
        raise ValueError("Only the four registered old development cohorts are accepted")
    cohort = cohorts[0]
    if (args.expected_queries, args.expected_dataset_sha256, args.split) != (
            cohort["queries"], cohort["sha256"], cohort.get("split", "development")):
        raise ValueError("Selected cohort differs from the old development registration")


def evaluator_sources():
    files = common.evaluator_sources()
    for name in ("round2_quality_eval.py", "experiments/round2-quality-plan.json",
                 "locomo_split.json", "hotpot_manifest.json", "transfer_manifest.json", "transfer_cases.json"):
        files[name] = hashlib.sha256((ROOT / "benchmarks" / name).read_bytes()).hexdigest()
    return files


def mode_order(position, repetition):
    offset = (position + repetition) % len(MODES)
    return MODES[offset:] + MODES[:offset]


@contextmanager
def fusion_mode(book, mode):
    import memory_book.semantic as semantic
    if mode not in MODES:
        raise ValueError("Unregistered fusion mode")
    original_fuser = semantic.fuse_candidates
    model = book._semantic_model
    original_encode = model.encode_query
    counter = [0]

    def counted_encode(query):
        counter[0] += 1
        return original_encode(query)

    try:
        if mode == MODES[1]:
            semantic.fuse_candidates = legacy_rrf
        model.encode_query = counted_encode
        yield counter
    finally:
        semantic.fuse_candidates = original_fuser
        model.encode_query = original_encode


def measured_recall(book, case, config, mode):
    # Policy selection and checkpoint I/O are outside the timed call. Counting
    # an actual encode_query operation adds the same increment to both hybrids.
    with fusion_mode(book, mode) as counter:
        start = time.perf_counter_ns()
        response = book.recall(case.query, project=case.project, **config,
                               use_cache=False, semantic=mode != MODES[0])
        elapsed = (time.perf_counter_ns() - start) / 1e6
    return response, elapsed, counter[0]


def payload_tokens(response, counters):
    # Stable full returned JSON, including the repeated result text/metadata.
    # Runtime latency and cache-hit diagnostics are excluded from token cost.
    payload = json.dumps({key: value for key, value in response.items()
                          if key not in {"latency_ms", "cache_hit"}},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {name: counter.count(payload) for name, counter in counters.items()}


def summarize_samples(samples, query_ids, repeats):
    result = common.summarize_samples(samples, query_ids, repeats)
    rows = result["query_results"]
    for key, selected in (("latency", samples),
                          ("first_pass_latency", [s for s in samples if s["repetition"] == 0]),
                          ("repeat_pass_latency", [s for s in samples if s["repetition"] > 0])):
        result[key]["p99_ms"] = percentile([s["elapsed_ms"] for s in selected], .99)
    result["metrics"]["mean_returned_payload_tokens"] = {
        name: statistics.fmean(row["returned_payload_tokens"][name] for row in rows) for name in ENCODINGS}
    result["invariants"]["cache_hit_error"] = sum(json.loads(s["row_json"])["cache_hit_error"] for s in samples)
    result["query_encoding_operations"] = sum(json.loads(s["row_json"])["query_encoding_operations"] for s in samples)
    return result


def build_report(progress, data, configs, args, source_after, evaluator_after, originals_after):
    identity = progress.get("identity")
    samples = [dict(row) for row in progress.db.execute("SELECT * FROM samples WHERE status='completed' ORDER BY seq")]
    failures, configurations = [], []
    expected_keys = {(digest(config), repetition, case.id, mode) for config in configs
                     for repetition in range(args.repeats) for case in data.queries for mode in MODES}
    if {(s["configuration"], s["repetition"], s["query_id"], s["mode"]) for s in samples} != expected_keys:
        raise ValueError("Incomplete or unexpected three-mode measurement matrix")
    for config in configs:
        modes = []
        for mode in MODES:
            selected = [s for s in samples if s["configuration"] == digest(config) and s["mode"] == mode]
            item = {"mode": mode, **summarize_samples(selected, [c.id for c in data.queries], args.repeats)}
            for name, value in {**item["invariants"], "repeat_context_mismatches": item["repeat_context_mismatches"],
                                **{k: item["metrics"][k] for k in ("budget_violations", "context_size_mismatches")}}.items():
                if value:
                    failures.append({**config, "mode": mode, "check": name, "observed": value})
            if mode == MODES[0] and item["query_encoding_operations"]:
                failures.append({**config, "mode": mode, "check": "lexical_must_not_encode_query"})
            modes.append(item)
        configurations.append({**config, "modes": modes, "paired_changes": {
            "q1_vs_lexical": paired_changes(modes[0]["query_results"], modes[2]["query_results"]),
            "q1_vs_legacy_rrf": paired_changes(modes[1]["query_results"], modes[2]["query_results"])}})
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
            "completed_samples": len(samples), "expected_samples": len(expected_keys), "configurations": configurations,
            "source_sha256_after": source_after, "evaluator_files_after": evaluator_after,
            "originals_sha256_after": originals_after,
            "validation": {"passed": not failures, "failures": failures},
            "methodology": json.loads(PLAN.read_text()),
            "interpretation": "Old development/regression cohorts; evidence retrieval only. Both semantic routes share the candidate runtime/index. No answer generation or new-domain generalization claim."}


def markdown(report):
    lines = ["# Q1 score fusion: old development/regression comparison", "",
             "Measurement validation: **" + ("PASS" if report["validation"]["passed"] else "FAIL") + "**.", "",
             "All three modes share the model/index, archive and assembler. Lexical remains the product default.", "",
             "| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for config in report["configurations"]:
        for mode in config["modes"]:
            metrics, latency = mode["metrics"], mode["latency"]
            lines.append(f"| {mode['mode']} | {config['budget_tokens']} | {metrics['evidence_recall']:.2%} | {metrics['complete_evidence_rate']:.2%} | "
                         f"{metrics['mean_context_tokens'][config['tokenizer']]:.1f} | {metrics['mean_returned_payload_tokens'][config['tokenizer']]:.1f} | "
                         f"{latency['p50_ms']:.3f} | {latency['p95_ms']:.3f} | {latency['p99_ms']:.3f} |")
    lines.extend(["", "## Paired gains and losses", "",
                  "| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |",
                  "|---|---:|---:|---:|---:|---:|"])
    for config in report["configurations"]:
        for name, changes in config["paired_changes"].items():
            lines.append(f"| {name} | {config['budget_tokens']} | {len(changes['annotation_gains'])} | {len(changes['annotation_losses'])} | "
                         f"{len(changes['complete_question_gains'])} | {len(changes['complete_question_losses'])} |")
    preparation = report["preparation"]
    index = preparation["semantic_index"]
    lines.extend(["", "## Preparation and limits", "",
                  f"Ingestion {preparation['ingestion_ms']:.1f} ms; model load {index['model_load_ms']:.1f} ms; "
                  f"index build {index['build_ms']:.1f} ms; {index['windows']} windows, {index['vector_bytes']} vector bytes.", "",
                  "Query timings exclude setup, scoring, export and checkpoint I/O; both semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.", "",
                  "The model/index fingerprint remains v1. Fusion cache version 2 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.", "",
                  "Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.", ""])
    return "\n".join(lines)


def compressed_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(gzip.compress(raw, mtime=0))
    temporary.replace(path)
    return hashlib.sha256(raw).hexdigest()


def write_report(report, output):
    checksum = compressed_json(Path(str(output) + ".json.gz"), report)
    summary = json.loads(json.dumps(report))
    for config in summary["configurations"]:
        for mode in config["modes"]:
            mode.pop("query_results")
    summary["full_report_sha256"] = checksum
    _save(Path(str(output) + ".summary.json"), summary)
    target = Path(str(output) + ".md")
    temporary = target.with_name(target.name + ".partial")
    temporary.write_text(markdown(report), encoding="utf-8")
    temporary.replace(target)


def export_checkpoint(state_dir, output, status="interrupted"):
    """Read only the metric ledger; never open the source archive or call a model.

    Incomplete output is explicitly an attempt ledger, not a completed comparison
    and not enough to replay generation (this experiment does no generation).
    """
    path = Path(state_dir) / "progress.sqlite3"
    if not path.exists():
        return None
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        metadata = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM metadata")}
        attempts = [dict(row) for row in db.execute(
            "SELECT seq,configuration,repetition,query_id,mode,status,started_at,finished_at,elapsed_ms,error FROM samples ORDER BY seq")]
        for item in attempts:
            error = item.pop("error")
            item["error_sha256"] = hashlib.sha256(error.encode()).hexdigest() if error else None
            if item["status"] == "running":
                item["status"] = "in_flight_unknown" if status == "running" else "interrupted_unknown"
        metrics = [{"seq": row["seq"], "metrics": {key: value for key, value in json.loads(row["row_json"]).items()
                                                    if key in PUBLIC_ROW_FIELDS}}
                   for row in db.execute("SELECT seq,row_json FROM samples WHERE status='completed' ORDER BY seq")]
        counts = {name: sum(row["status"] == name for row in attempts) for name in sorted({row["status"] for row in attempts})}
        ledger = {"schema_version": 1, "evaluator": VERSION, "status": status, "created_at_utc": utc_now(),
                  "identity": metadata.get("identity"), "preparation": metadata.get("preparation"),
                  "preparation_attempts": metadata.get("preparation_attempts", []),
                  "process_segments": metadata.get("process_segments", []), "attempt_counts": counts,
                  "complete_comparison": status == "completed",
                  "warning": "Uncommitted work has unknown latency and evidence outcome. No missing row is imputed, replayed or counted as complete."}
    ledger["attempts_sha256"] = compressed_json(Path(str(output) + ".attempts.json.gz"),
                                                {"attempts": attempts, "completed_metrics": metrics})
    _save(Path(str(output) + ".checkpoint.json"), ledger)
    return ledger

def run(args):
    validate_arguments(args)
    data = dataset_for(args)  # Wrong cohorts fail before loading any engine/model.
    if len({case.id for case in data.queries}) != len(data.queries):
        raise ValueError("Semantic evaluation requires unique query IDs")
    sys.path.insert(0, str(args.engine_src.resolve()))
    from memory_book import MemoryBook
    from memory_book.semantic import verify_model_files
    import memory_book.semantic as semantic
    import memory_book
    source = require_source(args.engine_src, memory_book.__file__)
    reference = verify_reference()
    if (semantic.SEMANTIC_VERSION, semantic.FUSION_VERSION, semantic.LEXICAL_WEIGHT) != (1, 2, .75):
        raise ValueError("Candidate policy differs from the registered Q1 policy")
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    if {c.version for c in counters.values()} != {"0.12.0"}:
        raise ValueError("Frozen semantic protocol requires tiktoken==0.12.0")
    configs = [{"budget_chars": args.budget_chars, "budget_tokens": tokens,
                "tokenizer": encoding, "limit": args.limit}
               for encoding in args.tokenizers for tokens in args.token_budgets]
    identity = {"evaluator": VERSION, "dataset_sha256": data.fingerprint,
                "reference": reference, "modes": list(MODES), "fusion_version": semantic.FUSION_VERSION,
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
        export_checkpoint(args.state_dir, args.output, "running")
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
                            modes = mode_order(position, repetition)
                            for mode in modes:
                                sample_key = (key, repetition, case.id, mode)
                                if sample_key in completed:
                                    continue
                                seq = progress.start(key, repetition, case.id, mode)
                                try:
                                    response, elapsed_ms, encoding_calls = measured_recall(book, case, config, mode)
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
                                                   if mode != MODES[0] else "semantic" in response,
                                               query_encoding_operations=encoding_calls,
                                               cache_hit_error=bool(response.get("cache_hit")),
                                               returned_payload_tokens=payload_tokens(response, counters),
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
                    export_checkpoint(args.state_dir, args.output, "running")
                segment["finished_at"] = utc_now()
                progress.set("process_segments", segments)
                report = build_report(progress, data, configs, args, engine_source_hash(source), evaluator_sources(),
                                      source_snapshot(book.db))
                write_report(report, args.output)
                export_checkpoint(args.state_dir, args.output, "completed" if report["validation"]["passed"] else "completed_with_failures")
                print(markdown(report), flush=True)
                return 0 if report["validation"]["passed"] else 2
        except BaseException as exc:
            export_checkpoint(args.state_dir, args.output,
                              "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed")
            raise
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
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(json.dumps({"event": "interrupted", "exception_type": "KeyboardInterrupt"}), flush=True)
        raise SystemExit(130) from None
    except Exception as exc:
        # Third-party errors can contain source text; only disclose their type.
        print(json.dumps({"event": "failed", "exception_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
