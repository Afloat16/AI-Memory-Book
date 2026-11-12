"""Compare native token assembly with two explicitly separated older policies.

The baseline and candidate run in independent processes. Published artifacts
contain IDs, evidence metrics and hashes, never upstream corpus text or answers.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import random
import sqlite3
import subprocess
import sys
import tempfile
import time

from benchmarks.component_eval import shared_response
from benchmarks.query_guard import require_query_count
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
    evidence_blocks, latency_summary, load_dataset, pack_whole_blocks,
    score_row, summarize_rows)


POLICIES = ("historical_whole_page_pack", "native_excerpt_pack", "native_token_budget")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def evaluator_sources():
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in
            ("native_budget_eval.py", "component_eval.py", "token_compare.py", "run.py",
             "data.py", "long_data.py", "public_data.py", "transfer_data.py", "hotpot_data.py", "query_guard.py")}


def dataset_for(args):
    if args.corpus == "hotpotqa":
        from benchmarks.hotpot_data import load_hotpot
        if not args.hotpot_path:
            raise ValueError("--hotpot-path is required")
        data = load_hotpot(Path(args.hotpot_path))
    else:
        data = load_dataset(args.corpus, args.seed, args.split, args.projects,
                            args.locomo_path, args.max_queries)
    require_query_count(data, args.expected_queries)
    expected_sha256 = getattr(args, "expected_dataset_sha256", None)
    if expected_sha256 is not None and data.fingerprint != expected_sha256:
        raise ValueError("Selected dataset fingerprint differs from the frozen manifest")
    return data


def block_ids(response: dict) -> list[str]:
    # Hash text AND source coordinates. The candidate must retain each exact
    # baseline block, not merely repeat the same words from another source.
    return [digest({"block": block, "id": item["id"], "source_refs": item["source_refs"]})
            for block, item in evidence_blocks(response)]


def source_errors(response, source_texts) -> int:
    errors = 0
    for item in response["results"]:
        for ref in item["source_refs"]:
            key = (ref.get("project") or item["breadcrumb"][0]["id"],
                   ref["session_id"], ref["turn_index"])
            source = source_texts.get(key)
            start, end = ref.get("turn_start"), ref.get("turn_end")
            if (source is None or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(source)
                    or source[start:end] not in item["text"]):
                errors += 1
    return errors


def whole_pages(book, response, project):
    documents = {}
    for item in response["results"]:
        page = book.read(item["id"], limit=100000)
        if page["next_offset"] is not None:
            raise ValueError("Historical full page could not be read completely")
        documents[item["id"]] = {"id": item["id"], "title": page["title"],
            "text": page["content"], "source_refs": page["source_refs"],
            "breadcrumb": page["breadcrumb"], "project": page["breadcrumb"][0]["id"],
            "created_at": page["created_at"]}
    return shared_response([item["id"] for item in response["results"]], documents)


def measure_worker(args):
    evaluator_before = evaluator_sources()
    data = dataset_for(args)  # Wrong cohorts stop before importing/building an engine.
    sys.path.insert(0, str(args.engine_src.resolve()))
    import memory_book
    from memory_book import MemoryBook
    counters = {name: TokenCounter(name) for name in args.tokenizers}
    if any(counter.version != "0.12.0" for counter in counters.values()):
        raise ValueError("This frozen protocol requires tiktoken==0.12.0")
    # score_row reports both reference encodings even in a single-encoding run.
    scoring_counters = {name: counters.get(name) or TokenCounter(name) for name in ENCODINGS}
    source = Path(memory_book.__file__).parent
    before = engine_source_hash(source)
    sources = original_turn_texts(data)
    report = {"label": args.label, "source_provenance": checkout_provenance(source),
        "source_sha256_before": before, "dataset": data.description(),
        "configuration": {"budget_chars": args.budget_chars, "token_budgets": args.token_budgets,
            "tokenizers": args.tokenizers, "limit": args.limit, "repeats": args.repeats,
            "semantic": bool(args.semantic_model_dir), "coverage": args.coverage},
        "tokenizer_version": "0.12.0", "configurations": []}
    with tempfile.TemporaryDirectory(prefix="native-budget-", dir=args.output.parent) as temporary:
        init = {"semantic_model_dir": args.semantic_model_dir} if args.semantic_model_dir else {}
        with MemoryBook(Path(temporary) / "memory.db", max_page_chars=900, cache_size=0, **init) as book:
            start = time.perf_counter_ns()
            for session in data.sessions:
                book.ingest(session)
            report["ingestion_ms"] = (time.perf_counter_ns() - start) / 1e6
            if args.semantic_model_dir:
                start = time.perf_counter_ns()
                report["semantic_index"] = book.build_semantic_index()
                report["semantic_index_wall_ms"] = (time.perf_counter_ns() - start) / 1e6
            report["engine_stats"] = book.stats()
            policies = POLICIES if args.worker_kind == "candidate" else POLICIES[:2]
            if args.worker_kind == "candidate":
                policies = ("native_token_budget",)
            # Historical policy has its own 100000-character retrieval boundary;
            # its context is token-capped only, never relabeled as native chars.
            configurations = []
            for policy in policies:
                char_caps = [100000] if policy == POLICIES[0] else args.budget_chars
                for chars in char_caps:
                    for encoding in args.tokenizers:
                        for tokens in args.token_budgets:
                            configurations.append((policy, chars, encoding, tokens))
            for policy, chars, encoding, tokens in configurations:
                counter = counters[encoding]
                rows, timings, retrieval_timings, packing_timings = {}, [], [], []
                first_pass, repeat_pass = [], []
                repeat_mismatches = 0
                for repetition in range(args.repeats):
                    cases = list(data.queries)
                    random.Random(args.seed + 1009 * repetition).shuffle(cases)
                    for case in cases:
                        options = {"budget_chars": chars, "limit": args.limit, "use_cache": False}
                        if policy == POLICIES[2]:
                            options.update(budget_tokens=tokens, tokenizer=encoding)
                            if args.semantic_model_dir:
                                options["semantic"] = True
                            if args.coverage:
                                options["coverage"] = True
                        started = time.perf_counter_ns()
                        response = book.recall(case.query, project=case.project, **options)
                        retrieval_ms = (time.perf_counter_ns() - started) / 1e6
                        if args.semantic_model_dir and "first_semantic_recall" not in report:
                            report["first_semantic_recall"] = {
                                "query_id": case.id, "elapsed_ms": retrieval_ms,
                                "boundary": "First semantic recall after explicit model loading and index construction in this worker; not model-cold or disk-cold."}
                        packing_start = time.perf_counter_ns()
                        if policy == POLICIES[0]:
                            response = whole_pages(book, response, case.project)
                        if policy != POLICIES[2]:
                            response = pack_whole_blocks(response, tokens, counter)
                        packing_ms = (time.perf_counter_ns() - packing_start) / 1e6
                        elapsed = (time.perf_counter_ns() - started) / 1e6
                        timings.append(elapsed)
                        (first_pass if repetition == 0 else repeat_pass).append(elapsed)
                        retrieval_timings.append(retrieval_ms)
                        packing_timings.append(packing_ms)
                        if repetition == 0:
                            row = score_row(case, response, sources, scoring_counters, public=args.corpus != "synthetic")
                            row["block_hashes"] = block_ids(response)
                            row["context_sha256"] = hashlib.sha256(response["context"].encode()).hexdigest()
                            row["token_budget_violation"] = counter.count(response["context"]) > tokens
                            row["source_span_errors"] = source_errors(response, sources)
                            if policy == POLICIES[2]:
                                row["token_metadata_error"] = any((
                                    response.get("context_tokens") != counter.count(response["context"]),
                                    response.get("tokenizer") != encoding,
                                    response.get("budget_tokens") != tokens,
                                    response.get("tokenizer_version") != counter.version))
                            rows[case.id] = row
                        elif hashlib.sha256(response["context"].encode()).hexdigest() != rows[case.id]["context_sha256"]:
                            repeat_mismatches += 1
                ordered = [rows[case.id] for case in data.queries]
                categories = defaultdict(list)
                for row in ordered:
                    categories[row["category"]].append(row)
                config = {"policy": policy, "budget_chars": chars, "tokenizer": encoding,
                    "budget_tokens": tokens, "metrics": summarize_rows(ordered),
                    "latency": latency_summary(timings), "recall_latency": latency_summary(retrieval_timings),
                    "first_pass_latency": latency_summary(first_pass),
                    "repeat_pass_latency": latency_summary(repeat_pass) if repeat_pass else None,
                    "post_recall_packing_latency": latency_summary(packing_timings),
                    "by_category": {key: summarize_rows(value) for key, value in sorted(categories.items())},
                    "token_budget_violations": sum(r["token_budget_violation"] for r in ordered),
                    "source_span_errors": sum(r["source_span_errors"] for r in ordered),
                    "token_metadata_errors": sum(r.get("token_metadata_error", False) for r in ordered),
                    "repeat_context_mismatches": repeat_mismatches,
                    "query_results": ordered}
                report["configurations"].append(config)
                print(json.dumps({"label": args.label, "policy": policy, "chars": chars,
                    "encoding": encoding, "tokens": tokens, "queries": len(ordered),
                    "complete": config["metrics"]["complete_evidence_rate"]}), file=sys.stderr, flush=True)
    report["source_sha256_after"] = engine_source_hash(source)
    report["source_unchanged"] = before == report["source_sha256_after"]
    report["evaluator_files"] = evaluator_before
    report["evaluator_unchanged"] = evaluator_before == evaluator_sources()
    return report


def paired_changes(baseline, candidate):
    comparisons = []
    for new in candidate["configurations"]:
        old = next(c for c in baseline["configurations"] if c["policy"] == POLICIES[1]
                   and all(c[k] == new[k] for k in ("budget_chars", "tokenizer", "budget_tokens")))
        previous = {r["id"]: r for r in old["query_results"]}
        gains, losses, complete_gains, complete_losses, missing_blocks = [], [], [], [], []
        for row in new["query_results"]:
            before = previous[row["id"]]
            for index, (a, b) in enumerate(zip(before["evidence_ranks"], row["evidence_ranks"], strict=True)):
                if a is None and b is not None:
                    gains.append({"id": row["id"], "annotation": index})
                if a is not None and b is None:
                    losses.append({"id": row["id"], "annotation": index})
            if row["complete"] and not before["complete"]:
                complete_gains.append(row["id"])
            if before["complete"] and not row["complete"]:
                complete_losses.append(row["id"])
            missing = sorted(set(before["block_hashes"]) - set(row["block_hashes"]))
            if missing:
                missing_blocks.append({"id": row["id"], "missing_block_hashes": missing})
        comparisons.append({**{k: new[k] for k in ("budget_chars", "tokenizer", "budget_tokens")},
            "annotation_gains": gains, "annotation_losses": losses,
            "complete_question_gains": complete_gains, "complete_question_losses": complete_losses,
            "baseline_block_losses": missing_blocks})
    return comparisons


def validation(engines, changes, *, require_preservation=True):
    failures = []
    if any(engine.get("evaluator_files") != engines[0].get("evaluator_files") for engine in engines):
        failures.append({"check": "evaluator_differs_between_workers"})
    for engine in engines:
        if not engine["source_unchanged"]:
            failures.append({"engine": engine["label"], "check": "source_changed"})
        if not engine["evaluator_unchanged"]:
            failures.append({"engine": engine["label"], "check": "evaluator_changed"})
        for config in engine["configurations"]:
            for key, value in {**{k: config["metrics"][k] for k in
                    ("budget_violations", "context_size_mismatches")},
                    **{k: config[k] for k in ("token_budget_violations", "source_span_errors", "token_metadata_errors", "repeat_context_mismatches")}}.items():
                if value:
                    failures.append({"engine": engine["label"], "policy": config["policy"], "check": key,
                        "observed": value, **{k: config[k] for k in ("budget_chars", "tokenizer", "budget_tokens")}})
    if require_preservation:
        for change in changes:
            if change["baseline_block_losses"]:
                failures.append({"check": "baseline_block_preservation", "observed": len(change["baseline_block_losses"]),
                    **{k: change[k] for k in ("budget_chars", "tokenizer", "budget_tokens")}})
    return {"passed": not failures, "failures": failures,
            "baseline_block_preservation_required": require_preservation}


def markdown(report):
    lines = ["# Native token-budget comparison", "", f"Validation: **{'PASS' if report['validation']['passed'] else 'FAIL'}**.", "",
        "Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.", "",
        "| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |",
        "|---|---:|---|---:|---:|---:|---:|---:|"]
    for engine in report["engines"]:
        for config in engine["configurations"]:
            m = config["metrics"]
            pct = lambda x: "n/a" if x is None else f"{x:.2%}"
            lines.append(f"| {engine['label']} / {config['policy']} | {config['budget_chars']} | {config['tokenizer']} | {config['budget_tokens']} | {pct(m['evidence_recall'])} | {pct(m['complete_evidence_rate'])} | {m['mean_context_tokens'][config['tokenizer']]:.1f} | {config['latency']['p95_ms']:.3f} |")
    lines.extend(["", "## Per-query changes against native excerpt packing", "",
        "| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |",
        "|---:|---|---:|---:|---:|---:|---:|---:|"])
    for c in report["paired_changes"]:
        lines.append(f"| {c['budget_chars']} | {c['tokenizer']} | {c['budget_tokens']} | {len(c['annotation_gains'])} | {len(c['annotation_losses'])} | {len(c['complete_question_gains'])} | {len(c['complete_question_losses'])} | {len(c['baseline_block_losses'])} |")
    return "\n".join(lines) + "\n"


def write_report(report, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    Path(str(output) + ".json.gz").write_bytes(gzip.compress(raw, mtime=0))
    summary = copy.deepcopy(report)
    for engine in summary["engines"]:
        for config in engine["configurations"]:
            config.pop("query_results")
    summary["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    Path(str(output) + ".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    Path(str(output) + ".md").write_text(markdown(report))


def archive_existing_outputs(output, enabled=False):
    """Keep old/partial samples before an explicitly requested resumed attempt."""
    paths = [Path(str(output) + suffix) for suffix in (".json.gz", ".summary.json", ".md")]
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    if not enabled:
        raise ValueError("Output already exists; preserve it and choose a new result prefix")
    if any(not path.is_file() for path in existing):
        raise ValueError("Existing result paths must be files")
    archive_root = Path(str(output) + ".attempts")
    archive_root.mkdir(parents=True, exist_ok=True)
    archive = Path(tempfile.mkdtemp(prefix="previous-", dir=archive_root))
    recorded = []
    for path in existing:
        recorded.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        path.rename(archive / path.name)
    return {"directory": str(archive), "files": recorded,
            "reason": "Existing samples retained before an explicit rerun; see runner checkpoint for stage status."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-src", type=Path)
    p.add_argument("--candidate-src", type=Path, default=Path("src"))
    p.add_argument("--baseline-label", default="prior-default")
    p.add_argument("--candidate-label", default="native-token")
    p.add_argument("--corpus", choices=("synthetic", "locomo", "transfer", "hotpotqa"), default="synthetic")
    p.add_argument("--split", choices=("development", "heldout"), default="development")
    p.add_argument("--seed", type=int, default=61)
    p.add_argument("--projects", type=int, default=8)
    p.add_argument("--locomo-path")
    p.add_argument("--hotpot-path")
    p.add_argument("--max-queries", type=int, default=0)
    p.add_argument("--expected-queries", type=int, required=True)
    p.add_argument("--expected-dataset-sha256")
    p.add_argument("--budget-chars", type=int, nargs="+", default=[2000, 8000])
    p.add_argument("--token-budgets", type=int, nargs="+", default=[512, 1024, 2048])
    p.add_argument("--tokenizers", choices=ENCODINGS, nargs="+", default=list(ENCODINGS))
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--candidate-semantic-model-dir", type=Path)
    p.add_argument("--candidate-coverage", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--archive-existing-output", action="store_true",
                   help="Preserve old or partial outputs in an adjacent attempts directory before rerunning")
    p.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--label", help=argparse.SUPPRESS)
    p.add_argument("--worker-kind", choices=("baseline", "candidate"), help=argparse.SUPPRESS)
    p.add_argument("--semantic-model-dir", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--coverage", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if min(args.budget_chars) < 128 or min(args.token_budgets) < 1 or args.repeats < 1 or not 1 <= args.limit <= 50:
        p.error("Positive token budgets/repeats and limit 1..50; character budgets >=128 required")
    if args.worker_kind:
        report = measure_worker(args)
        args.output.write_text(json.dumps(report, ensure_ascii=False))
        return 0
    if args.baseline_src is None:
        p.error("--baseline-src is required")
    dataset_for(args)
    archived = archive_existing_outputs(args.output, args.archive_existing_output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    engines = []
    with tempfile.TemporaryDirectory(prefix="native-budget-workers-", dir=args.output.parent) as directory:
        for index, (kind, label, source) in enumerate((("baseline", args.baseline_label, args.baseline_src),
                                                       ("candidate", args.candidate_label, args.candidate_src))):
            output = Path(directory) / f"{kind}.json"
            command = [sys.executable, "-m", "benchmarks.native_budget_eval", "--worker-kind", kind,
                "--engine-src", str(source.resolve()), "--label", label, "--corpus", args.corpus,
                "--split", args.split, "--seed", str(args.seed), "--projects", str(args.projects),
                "--max-queries", str(args.max_queries), "--expected-queries", str(args.expected_queries),
                "--limit", str(args.limit), "--repeats", str(args.repeats), "--output", str(output),
                "--budget-chars", *map(str, args.budget_chars), "--token-budgets", *map(str, args.token_budgets),
                "--tokenizers", *args.tokenizers]
            if args.locomo_path:
                command += ["--locomo-path", str(Path(args.locomo_path).resolve())]
            if args.hotpot_path:
                command += ["--hotpot-path", str(Path(args.hotpot_path).resolve())]
            if args.expected_dataset_sha256:
                command += ["--expected-dataset-sha256", args.expected_dataset_sha256]
            if kind == "candidate":
                if args.candidate_semantic_model_dir:
                    command += ["--semantic-model-dir", str(args.candidate_semantic_model_dir.resolve())]
                if args.candidate_coverage:
                    command += ["--coverage"]
            subprocess.run(command, check=True)
            engines.append(json.loads(output.read_text()))
    if engines[0]["dataset"]["sha256"] != engines[1]["dataset"]["sha256"]:
        raise ValueError("Engine corpus fingerprints differ")
    changes = paired_changes(*engines)
    report = {"schema_version": 1, "evaluator": "native-budget-1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "platform": platform.platform()},
        "dataset": engines[0]["dataset"], "engines": engines, "paired_changes": changes,
        "previous_outputs_archived": archived,
        "methodology": "See benchmarks/native_budget_plan.json and docs/native-budget-evaluation.md. Historical common-page has its own 100000-character retrieval boundary; native policies share each declared character cap. No labels enter packing. Final-answer and full-workflow claims are excluded."}
    report["validation"] = validation(engines, changes,
        require_preservation=not (args.candidate_semantic_model_dir or args.candidate_coverage))
    write_report(report, args.output)
    print(markdown(report))
    return 0 if report["validation"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
