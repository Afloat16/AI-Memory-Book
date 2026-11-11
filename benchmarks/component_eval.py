"""Actual upstream retrieval components on a frozen shared page corpus.

All rankers get the same presegmented source pages. One independent assembler
and whole-block token packer scores their selected IDs. Native response/read
costs are measured separately; this is not a complete product comparison.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from benchmarks.run import _normalized, engine_source_hash, original_turn_texts
from benchmarks.token_compare import (ENCODINGS, TokenCounter, latency_summary,
    checkout_provenance, load_dataset, pack_whole_blocks, score_row, summarize_rows,
    validation_markdown, validation_status)


BASELINE_ENGINES = frozenset({"baseline", "v0.2.1"})


def component_label(args) -> str:
    """Keep legacy CLI engine selectors separate from measured version labels."""
    if args.engine in BASELINE_ENGINES:
        return args.baseline_label
    if args.engine == "candidate":
        return args.candidate_label
    return args.engine


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def shared_response(ids: list[str], documents: dict[str, dict]) -> dict:
    """Assemble whole source pages with identical citation overhead for all engines."""
    if any(identity not in documents for identity in ids) or len(ids) != len(set(ids)):
        raise ValueError("Backend returned an unknown or duplicate shared document ID")
    results, blocks = [], []
    for identity in ids:
        doc = documents[identity]
        results.append({"id": identity, "title": doc["title"], "text": doc["text"],
                        "source_refs": copy.deepcopy(doc["source_refs"]),
                        "breadcrumb": copy.deepcopy(doc["breadcrumb"])})
        blocks.append(f"[{identity}] {doc['project']} | {doc['created_at']}\n{doc['text']}")
    context = "\n\n".join(blocks)
    return {"context": context, "context_chars": len(context), "results": results,
            "budget_chars": max(1, len(context)), "truncated": False}


def dataset_for(args):
    return load_dataset(args.corpus, args.seed, args.split, args.projects,
                        args.locomo_path, args.max_queries)


def evidence_attainability(dataset, documents: list[dict]) -> dict:
    """Check that a single-hit strict evidence metric can attain every label.

    A long annotation may span multiple continuation pages. The current strict
    evaluator does not union those pages; report that limitation explicitly and
    detect affected labels before interpreting measured coverage.
    """
    sources = original_turn_texts(dataset)
    index = defaultdict(list)
    for doc in documents:
        for ref in doc["source_refs"]:
            index[(doc["project"], ref["session_id"], ref["turn_index"])].append((doc, ref))
    missing, total, max_chars = [], 0, 0
    for case in dataset.queries:
        for evidence in case.required + case.stale:
            total += 1
            max_chars = max(max_chars, len(evidence.needle))
            needle = _normalized(evidence.needle)
            keys = [(case.project, evidence.session_id, evidence.turn_index)] if case.project is not None else [
                key for key in index if key[1:] == (evidence.session_id, evidence.turn_index)]
            matched = any(needle in _normalized(doc["text"])
                          and needle in _normalized(sources[key][ref["turn_start"]:ref["turn_end"]])
                          for key in keys for doc, ref in index[key])
            if not matched:
                missing.append({"query_id": case.id, "session_id": evidence.session_id,
                                "turn_index": evidence.turn_index, "annotation_chars": len(evidence.needle)})
    return {"evidence_labels_checked": total, "max_annotation_chars": max_chars,
            "unattainable_single_page_labels": missing,
            "metric_limit": "each complete annotation must fit one page and matching original source span; cross-page union is not scored"}


def export_frozen(args) -> dict:
    sys.path.insert(0, str(args.engine_src.resolve()))
    from memory_book import MemoryBook, __version__
    import memory_book
    source_root = Path(memory_book.__file__).parent
    before = engine_source_hash(source_root)
    dataset = dataset_for(args)
    start = time.perf_counter_ns()
    with MemoryBook(args.database, max_page_chars=900, cache_size=0) as book:
        for session in dataset.sessions:
            book.ingest(session)
        ingest_ms = (time.perf_counter_ns() - start) / 1e6
        documents = []
        for row in book.db.execute("SELECT id,project_id FROM pages ORDER BY id").fetchall():
            page = book.read(row["id"], limit=100000)
            if page["next_offset"] is not None:
                raise ValueError("Frozen page exceeds the full-read cap")
            documents.append({"id": page["id"], "project": row["project_id"],
                              "title": page["title"], "text": page["content"],
                              "source_refs": page["source_refs"], "breadcrumb": page["breadcrumb"],
                              "created_at": page["created_at"]})
        stats = book.stats()
    after = engine_source_hash(source_root)
    bundle = {"documents": documents, "dataset": dataset.description(),
              "label": args.baseline_label, "engine_version": __version__,
              "source_provenance": checkout_provenance(source_root),
              "source_sha256_before": before, "source_sha256_after": after,
              "source_unchanged": before == after,
              "frozen_source_sha256": before, "stats": stats, "ingestion_ms": ingest_ms,
              "evidence_attainability": evidence_attainability(dataset, documents),
              "documents_sha256": hashlib.sha256(canonical_json(documents).encode()).hexdigest()}
    args.bundle.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    return {key: value for key, value in bundle.items() if key != "documents"}


class CoreBook:
    def __init__(self, args, documents):
        sys.path.insert(0, str(args.engine_src.resolve()))
        from memory_book import MemoryBook, __version__
        import memory_book
        self.source_root = Path(memory_book.__file__).parent
        self.source_hash = engine_source_hash(self.source_root)
        self.book = MemoryBook(args.database, max_page_chars=900, cache_size=0)
        self.metadata = {"name": component_label(args), "version": __version__,
                         "source_sha256": self.source_hash,
                         "source_provenance": checkout_provenance(self.source_root),
                         "comparison_scope": "shared-page retrieval component",
                         "latency_scope": "in-process recall including native context assembly; no IPC",
                         "result_cache": "disabled", "input_character_cap": 100000,
                         "ranking_metadata": "native book hierarchy and FTS fields retained"}

    def search(self, query, project, limit):
        start = time.perf_counter_ns()
        response = self.book.recall(query, project=project, limit=limit,
                                    budget_chars=100000, use_cache=False)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        return {"results": response["results"], "hit_ids": [hit["id"] for hit in response["results"]],
                "native_payload": response, "native_text": response["context"],
                "search_ms": elapsed, "bridge_ms": elapsed}

    def close(self):
        self.book.close()
        after = engine_source_hash(self.source_root)
        self.metadata.update(source_sha256_after=after,
                             source_unchanged=self.source_hash == after)


def measure_component(args) -> dict:
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    documents = {doc["id"]: doc for doc in bundle["documents"]}
    dataset = dataset_for(args)
    if dataset.fingerprint != bundle["dataset"]["sha256"]:
        raise ValueError("Component and frozen page export use different datasets")
    source_texts = original_turn_texts(dataset)
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    if args.engine == "candidate" or args.engine in BASELINE_ENGINES:
        engine = CoreBook(args, documents)
    elif args.engine == "billion-context":
        from benchmarks.competitors.billion import BillionKernel
        engine = BillionKernel(bundle["documents"], args.cache / "billion-context", offline=args.offline)
    else:
        from benchmarks.competitors.ai_memory import AiMemoryNative
        mode = "hybrid" if args.engine == "ai-memory-hybrid" else "fts"
        engine = AiMemoryNative(bundle["documents"], args.cache, offline=args.offline, retrieval=mode)
    responses, native_rows, kernel_ms, bridge_ms, first_ms, repeat_ms = {}, {}, [], [], [], []
    try:
        for repetition in range(args.repeats):
            cases = list(dataset.queries)
            random.Random(args.seed + 1009 * repetition).shuffle(cases)
            for case in cases:
                response = engine.search(case.query, case.project, args.limit)
                ids = response.get("hit_ids")
                if ids is None:
                    ids = [hit["ref"] for hit in response["results"]]
                # Native systems may expose generated metadata pages. They
                # consume top-k slots and payload tokens but earn no evidence.
                unmapped = sum(identity not in documents for identity in ids)
                mapped_ids = [identity for identity in ids if identity in documents]
                kernel_ms.append(response["search_ms"])
                bridge_ms.append(response["bridge_ms"])
                (first_ms if repetition == 0 else repeat_ms).append(response["bridge_ms"])
                if repetition:
                    continue
                responses[case.id] = shared_response(mapped_ids, documents)
                native_payload = response.get("native_payload", response["results"])
                native_text = response.get("native_text")
                reads = []
                if args.engine.startswith("ai-memory"):
                    for identity in mapped_ids:
                        read = engine.read(identity)
                        # Credit only exact complete pages actually fetched.
                        if read["result"].get("truncated") or read["result"].get("body") != documents[identity]["text"]:
                            raise ValueError("Native full read did not return the exact complete shared page")
                        reads.append(read)
                payload_text = canonical_json(native_payload)
                read_payloads = [canonical_json(read.get("native_payload", read["result"])) for read in reads]
                native_rows[case.id] = {
                    "id": case.id, "hit_ids": mapped_ids, "unmapped_native_hit_count": unmapped,
                    "search_payload_tokens": {name: counter.count(payload_text) for name, counter in counters.items()},
                    "search_content_tokens": {name: counter.count(native_text) for name, counter in counters.items()} if native_text is not None else None,
                    "read_payload_tokens": {name: sum(counter.count(text) for text in read_payloads) for name, counter in counters.items()},
                    "read_content_tokens": {name: sum(counter.count(read.get("native_text", canonical_json(read["result"]))) for read in reads) for name, counter in counters.items()},
                    "read_calls": len(reads), "read_ms": sum(read["read_ms"] for read in reads),
                    "global_fts_only": response.get("global_fts_only", False)}
        metadata = engine.metadata
        if args.engine == "ai-memory-hybrid":
            # A separate, untimed diagnostic proves which native streams ran;
            # explain fields never enter measured search payload token counts.
            probe = next((case for case in dataset.queries if case.project), None)
            if probe is not None:
                diagnostic = engine.search_mcp(probe.query, probe.project, args.limit, explain=True)
                metadata["post_measurement_stream_diagnostic"] = {
                    "query_id": probe.id,
                    "streams_active": diagnostic["decoded_native"].get("streams_active")}
    finally:
        engine.close()
    packed_configs = []
    for name, counter in counters.items():
        for budget in args.token_budgets:
            rows, timings = [], []
            for case in dataset.queries:
                start = time.perf_counter_ns()
                packed = pack_whole_blocks(responses[case.id], budget, counter)
                timings.append((time.perf_counter_ns() - start) / 1e6)
                row = score_row(case, packed, source_texts, counters, public=args.corpus != "synthetic")
                row["token_budget_violation"] = row["context_tokens"][name] > budget
                rows.append(row)
            categories = defaultdict(list)
            for row in rows:
                categories[row["category"]].append(row)
            packed_configs.append({"tokenizer": name, "budget_tokens": budget,
                "metrics": summarize_rows(rows), "packing_latency": latency_summary(timings),
                "token_budget_violations": sum(row["token_budget_violation"] for row in rows),
                "by_category": {key: summarize_rows(value) for key, value in sorted(categories.items())},
                "query_results": rows})
    native = list(native_rows.values())
    return {"label": component_label(args), "engine_selector": args.engine,
            "metadata": metadata, "dataset": dataset.description(),
            "kernel_or_native_search_latency": latency_summary(kernel_ms),
            "adapter_roundtrip_latency": latency_summary(bridge_ms),
            "first_pass_roundtrip_latency": latency_summary(first_ms),
            "repeat_roundtrip_latency": latency_summary(repeat_ms),
            "native_costs": {"queries": len(native),
                "read_policy": ("search + full read of every mapped top-k page, even if preview already contains evidence; fixed policy, not minimum or token-budget-adaptive cost"
                                if args.engine.startswith("ai-memory") else
                                "No native full-read API calls measured; shared expansion is a separate harness policy"),
                "mean_read_calls": statistics.fmean(row["read_calls"] for row in native),
                "mean_read_ms": statistics.fmean(row["read_ms"] for row in native),
                "mean_search_payload_tokens": {name: statistics.fmean(row["search_payload_tokens"][name] for row in native) for name in ENCODINGS},
                "mean_search_content_tokens": {name: statistics.fmean(row["search_content_tokens"][name] for row in native) for name in ENCODINGS}
                    if all(row["search_content_tokens"] is not None for row in native) else None,
                "mean_full_read_payload_tokens": {name: statistics.fmean(row["read_payload_tokens"][name] for row in native) for name in ENCODINGS},
                "mean_full_read_content_tokens": {name: statistics.fmean(row["read_content_tokens"][name] for row in native) for name in ENCODINGS},
                "unmapped_native_hits": sum(row["unmapped_native_hit_count"] for row in native),
                "global_fts_only_queries": sum(row["global_fts_only"] for row in native)},
            "native_query_costs": native, "packed_configurations": packed_configs}


def markdown(report):
    lines = ["# Shared-page retrieval component comparison", "",
             "Actual upstream kernels/executables; no generated answers. Scope and transport differ as documented below.", "",
             *validation_markdown(report.get("validation", validation_status(
                 [report.get("frozen_corpus", {}), *report["engines"]]))),
             "| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean context tokens | Adapter p50 ms | Adapter p95 ms |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for engine in report["engines"]:
        for config in engine["packed_configurations"]:
            m = config["metrics"]
            recall = "n/a" if m["evidence_recall"] is None else f"{m['evidence_recall']:.2%}"
            complete = "n/a" if m["complete_evidence_rate"] is None else f"{m['complete_evidence_rate']:.2%}"
            latency = engine["adapter_roundtrip_latency"]
            lines.append(f"| {engine['label']} | {config['tokenizer']} | {config['budget_tokens']} | {recall} | {complete} | {m['mean_context_tokens'][config['tokenizer']]:.1f} | {latency['p50_ms']:.3f} | {latency['p95_ms']:.3f} |")
    lines += ["", "## Interpretation and limits", ""]
    lines += ["- " + note for note in report["methodology"]]
    return "\n".join(lines) + "\n"


def write_report(report, prefix):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    Path(str(prefix) + ".json.gz").write_bytes(gzip.compress(raw, mtime=0))
    summary = copy.deepcopy(report)
    for engine in summary["engines"]:
        engine.pop("native_query_costs")
        for config in engine["packed_configurations"]:
            config.pop("query_results")
    summary["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    Path(str(prefix) + ".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    Path(str(prefix) + ".md").write_text(markdown(report), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--baseline-label", default="baseline",
                        help="Display label for the frozen source and baseline ranker; version/source identity are recorded separately")
    parser.add_argument("--candidate-label", default="candidate")
    parser.add_argument("--engines", nargs="+", default=["candidate", "billion-context", "ai-memory-hybrid"],
                        choices=["baseline", "v0.2.1", "candidate", "billion-context", "ai-memory-fts", "ai-memory-hybrid"],
                        help="Rankers to run; v0.2.1 is retained as a legacy alias for baseline, not a version assertion")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--corpus", choices=["synthetic", "locomo"], default="synthetic")
    parser.add_argument("--locomo-path")
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--seed", type=int, default=61)
    parser.add_argument("--projects", type=int, default=8)
    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--token-budgets", type=int, nargs="+", default=[512, 1024, 2048])
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/components"))
    parser.add_argument("--worker", choices=["export", "measure"], help=argparse.SUPPRESS)
    parser.add_argument("--engine", help=argparse.SUPPRESS)
    parser.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--bundle", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--database", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1 or args.limit < 1 or min(args.token_budgets) < 1:
        parser.error("repeats, limit and budgets must be positive")
    if not args.baseline_label.strip() or not args.candidate_label.strip() or args.baseline_label == args.candidate_label:
        parser.error("baseline and candidate labels must be distinct and nonempty")
    if len(BASELINE_ENGINES.intersection(args.engines)) > 1:
        parser.error("baseline and v0.2.1 select the same ranker; use only one")
    if args.worker:
        result = export_frozen(args) if args.worker == "export" else measure_component(args)
        result["validation"] = validation_status([result])
        args.output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return 0 if result["validation"]["passed"] else 2
    common = ["--baseline-src", str(args.baseline_src.resolve()), "--cache", str(args.cache.resolve()),
              "--baseline-label", args.baseline_label, "--candidate-label", args.candidate_label,
              "--corpus", args.corpus, "--split", args.split, "--seed", str(args.seed),
              "--projects", str(args.projects), "--max-queries", str(args.max_queries),
              "--limit", str(args.limit), "--repeats", str(args.repeats),
              "--token-budgets", *map(str, args.token_budgets)]
    if args.locomo_path:
        common += ["--locomo-path", str(Path(args.locomo_path).resolve())]
    if args.offline:
        common.append("--offline")
    engines = []
    with tempfile.TemporaryDirectory(prefix="shared-memory-components-", dir=Path.cwd().parent) as directory:
        root = Path(directory)
        bundle, frozen_db, output = root / "pages.json", root / "frozen.db", root / "worker.json"
        command = [sys.executable, "-m", "benchmarks.component_eval", *common,
                   "--bundle", str(bundle), "--database", str(frozen_db), "--output", str(output)]
        completed = subprocess.run([*command, "--worker", "export", "--engine-src", str(args.baseline_src.resolve())], check=False)
        frozen = json.loads(output.read_text())
        frozen["worker_exit_code"] = getattr(completed, "returncode", 0)
        # A changed exporter cannot supply a valid common corpus. Preserve its
        # record and skip rankers instead of discarding the diagnostic on exit.
        for name in args.engines if validation_status([frozen])["passed"] else []:
            database = root / (name + ".db")
            shutil.copyfile(frozen_db, database)
            source = args.baseline_src if name in BASELINE_ENGINES else args.candidate_src
            output.unlink()
            completed = subprocess.run([*command, "--worker", "measure", "--engine", name,
                            "--engine-src", str(source.resolve()), "--database", str(database)], check=False)
            result = json.loads(output.read_text())
            result["worker_exit_code"] = getattr(completed, "returncode", 0)
            engines.append(result)
            print(f"{name}: measured {engines[-1]['dataset']['queries']} shared-page queries", file=sys.stderr, flush=True)
    report = {"schema_version": 1, "evaluator_version": "shared-components-1.0",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": platform.python_version(), "platform": platform.platform()},
              "tokenizer": {"library": "tiktoken", "version": TokenCounter(ENCODINGS[0]).version, "encodings": list(ENCODINGS)},
              "frozen_corpus": frozen, "engines": engines,
              "methodology": [
                  f"Every component receives identical adaptive-900 pages exported once from the supplied frozen baseline ({args.baseline_label}), with the same queries, project scope, and top-k limit. Its actual package version, source hash and checkout provenance are recorded in frozen_corpus. No answer labels enter a backend.",
                  "Display labels and legacy engine selectors do not establish source identity. Git base commits, source roots, checkout/source dirty flags and measured source hashes identify the executed core; a dirty source tree is not the base commit.",
                  "A common assembler expands selected IDs to complete original pages, adds identical citations, and applies identical rank-order whole-block token packing. Quality and context tokens describe this shared policy, not each product's native preview behavior.",
                  "Book ranking retains its native hierarchy/FTS fields; external backends receive each page's title/body/project. Equal granularity does not mean identical indexed features or complete product workflows.",
                  "Native metadata pages absent from the shared corpus consume top-k slots and search payload tokens but earn no evidence; they are counted as unmapped hits and excluded from harness full-page expansion.",
                  "AI-Memory-Book latency is in-process recall including its own context assembly; Billion reports both native searchBlocks kernel time and JSON IPC roundtrip; ai-memory reports actual persistent loopback HTTP/MCP roundtrip. These transport boundaries differ.",
                  "All native feature/embedding caches may warm naturally. First-pass and repeated-query latencies are separate; no OS cold-cache or process-startup claims are made.",
                  "Billion executes pinned upstream searchBlocks only, not its summarization/proxy workflow. ai-memory uses the pinned official native binary; hybrid uses its default local MiniLM with embedding backfill complete. Upstream global hybrid requests are FTS-only.",
                  "Native search payloads and actual ai-memory full-page reads are counted separately. Canonical JSON payload counts exclude tool definitions, initialization, requests, model inference, and provider chat wrappers; they are not billed tokens or an equal-cap native product comparison.",
                  "The fixed ai-memory cost policy reads every mapped top-k page even when its preview already contains enough evidence. It is not a minimum-read strategy or a token-budget-adaptive native policy; a preview-only consumer can spend less.",
                  "Common full-page expansion for Billion is a harness-side lookup; it does not pretend to measure a native fetch API. ai-memory native reads are executed and checked against the shared page text before evidence is scored.",
                  "The two measured tiktoken encodings are references, not every provider's tokenizer. Packing and full-read costs are additional to retrieval and separately reported.",
                  "Evidence coverage requires complete annotated text and source identity/span. It is not generated-answer accuracy, semantic equivalence, or a hallucination metric.",
                  "Public LoCoMo data remains outside git under CC BY-NC 4.0. Published reports contain IDs and metrics only. Synthetic heldout templates are not an independent domain test."]}
    report["validation"] = validation_status([frozen, *engines])
    write_report(report, args.output)
    print(markdown(report))
    return 0 if report["validation"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
