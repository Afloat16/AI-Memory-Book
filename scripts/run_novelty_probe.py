"""One-pass, old-data-only probe of two predeclared lexical novelty policies.

Frozen product/evaluator files are imported unchanged. Each runtime executes
in an isolated process from its exact committed source; no monkeypatching,
new held-out data, generated answers, or query-result caching is used.
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
                                     latency_summary, load_dataset, score_row, summarize_rows)
from scripts.benchmark_default_recall import indexed_content

PLAN = ROOT / "benchmarks/experiments/novelty-probe-plan.json"
BINDING = ROOT / "benchmarks/experiments/novelty-probe-binding.json"
MODES = ("default", "no_novelty", "capped_novelty_025")
COHORTS = ("synthetic61", "authored36", "public1015", "hotpot128")
BUDGETS = (512, 1024, 2048)
ORIGINAL = '1 + len(matched[pending[i]["rid"]] - covered) / len(qset)'
EXPRESSIONS = {"default": ORIGINAL, "no_novelty": "1 + 0.0",
    "capped_novelty_025": '1 + min(0.25, len(matched[pending[i]["rid"]] - covered) / len(qset))'}
INVARIANTS = ("token_budget_violation", "source_span_errors", "page_projection_errors",
              "token_metadata_error", "scope_errors", "semantic_metadata_error", "cache_hit_error")
DEPENDENCIES = ("benchmarks/native_budget_eval.py", "benchmarks/semantic_eval.py",
    "benchmarks/component_eval.py", "benchmarks/token_compare.py", "benchmarks/run.py",
    "benchmarks/data.py", "benchmarks/long_data.py", "benchmarks/public_data.py",
    "benchmarks/transfer_data.py", "benchmarks/hotpot_data.py", "benchmarks/query_guard.py",
    "benchmarks/resume.py", "benchmarks/prepare_native_data.py", "benchmarks/locomo_split.json",
    "benchmarks/hotpot_manifest.json", "benchmarks/transfer_manifest.json", "benchmarks/transfer_cases.json",
    "scripts/benchmark_default_recall.py", "benchmarks/experiments/novelty-probe-plan.json",
    "benchmarks/experiments/novelty-probe-binding.json")


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
    temporary.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
    temporary.replace(path)
    return raw


def evaluator_hashes():
    return {path: sha((ROOT / path).read_bytes()) for path in (*DEPENDENCIES, "scripts/run_novelty_probe.py")}


def registered():
    plan, binding = json.loads(PLAN.read_text()), json.loads(BINDING.read_text())
    require([m["name"] for m in plan["modes"]] == list(MODES), "Novelty modes differ from registration")
    require([c["name"] for c in plan["cohorts"]] == list(COHORTS), "Cohort axes differ from registration")
    require(plan["parameters"] == {"seed": 61, "projects": 8, "max_queries": 0, "budget_chars": 8000,
        "token_budgets": list(BUDGETS), "tokenizers": ["cl100k_base"], "limit": 5, "repeats": 1,
        "max_page_chars": 900, "cache_size": 0, "use_cache": False, "semantic": False, "coverage": False},
        "Frozen development parameters changed")
    require(set(binding["modes"]) == set(MODES), "Runtime binding has an extra or missing candidate")
    return plan, binding


def verify_source(source, mode, binding):
    package = source.resolve() / "memory_book"
    provenance = checkout_provenance(package)
    expected = binding["modes"][mode]
    require(provenance["commit_identifies_source"] and provenance["git_commit"] == expected["commit"]
            and engine_source_hash(package) == expected["source_sha256"], "Runtime source identity differs")
    reference = subprocess.check_output(["git", "show", binding["modes"]["default"]["commit"]
        + ":src/memory_book/store.py"], cwd=source.parent, text=True)
    require(reference.count(ORIGINAL) == 1, "Original novelty expression is not unique")
    require((package / "store.py").read_text() == reference.replace(ORIGINAL, EXPRESSIONS[mode]),
            "Candidate is not the sole registered novelty expression change")
    changed = subprocess.check_output(["git", "diff", "--name-only", binding["modes"]["default"]["commit"],
        expected["commit"], "--", "src"], cwd=source.parent, text=True).splitlines()
    require(changed == ([] if mode == "default" else ["src/memory_book/store.py"]),
            "Runtime changed outside the registered expression")
    return {"source_sha256": expected["source_sha256"], "provenance": provenance,
            "changed_runtime_files": changed}


def prepare_data(directory):
    """Filter the pinned Parquet before constructing any question Dataset."""
    from benchmarks.prepare_native_data import checked_download, normalize_hotpot
    import pyarrow.dataset as ds
    directory.mkdir(parents=True, exist_ok=True)
    locomo = json.loads((ROOT / "benchmarks/locomo_split.json").read_text())
    checked_download(locomo["url"], directory / "locomo10.json", locomo["sha256"], locomo["bytes"])
    manifest_path = ROOT / "benchmarks/hotpot_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest["expected_queries"] == 128, "Only the old 128-query Hotpot cohort is permitted")
    parquet = directory / "old-hotpot-source.parquet"
    checked_download(manifest["source_url"], parquet, manifest["upstream_sha256"], manifest["upstream_bytes"])
    selected = ds.dataset(parquet, format="parquet").to_table(
        filter=ds.field("id").isin(manifest["selected_ids"])).to_pylist()
    require(len(selected) == 128 and {r["id"] for r in selected} == set(manifest["selected_ids"]),
            "Old-ID Parquet filter selected another cohort")
    value = {"old_manifest_sha256": sha(manifest_path.read_bytes()),
        "upstream_sha256": manifest["upstream_sha256"], "items": json.loads(normalize_hotpot(selected))}
    destination = directory / "hotpot128-only.json"
    if destination.exists():
        require(json.loads(destination.read_text()) == value, "Preserve different existing filtered data")
    else:
        write_json(destination, value)
    print(json.dumps({"prepared_old_hotpot_queries": 128, "new_cohort_manifest_accessed": False,
                      "old_manifest_sha256": value["old_manifest_sha256"]}))


def dataset_for(name, directory, plan):
    cohort = next(c for c in plan["cohorts"] if c["name"] == name)
    if name == "hotpot128":
        from benchmarks.hotpot_data import convert_hotpot
        manifest_path = ROOT / "benchmarks/hotpot_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        prepared = json.loads((directory / "hotpot128-only.json").read_text())
        require(prepared["old_manifest_sha256"] == sha(manifest_path.read_bytes())
                and prepared["upstream_sha256"] == manifest["upstream_sha256"], "Filtered old-source identity changed")
        items, ids = prepared["items"], manifest["selected_ids"]
        require(len(items) == len(ids) == 128 and {r["_id"] for r in items} == set(ids),
                "Only the old registered 128 question rows may be loaded")
        data = convert_hotpot(items, ids, {key: manifest[key] for key in (
            "dataset", "source_url", "source_revision", "upstream_sha256", "canonical_sha256", "license")})
    else:
        data = load_dataset(cohort["corpus"], 61, cohort["split"], 8,
                            str(directory / "locomo10.json"), 0)
    require(len(data.queries) == cohort["queries"] and data.fingerprint == cohort["sha256"],
            "Dataset differs from the old pre-registered cohort count or fingerprint")
    return data


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        for group in row["diagnostic_groups"]:
            groups[group].append(row)
    return {"metrics": summarize_rows(rows),
        "by_group": {group: summarize_rows(values) for group, values in sorted(groups.items())},
        "latency": {**latency_summary([row["elapsed_ms"] for row in rows]),
                    "p99_ms": percentile([row["elapsed_ms"] for row in rows], .99)},
        "mean_returned_payload_tokens": {e: statistics.fmean(r["returned_payload_tokens"][e] for r in rows)
                                          for e in ENCODINGS} if rows else None,
        "unsupported_nonempty": sum(not r["answerable"] and r["nonempty"] for r in rows),
        "invariants": {key: sum(row[key] for row in rows) for key in INVARIANTS}}


def worker(args):
    plan, binding = registered()
    data = dataset_for(args.cohort, args.data_dir, plan)
    sys.path.insert(0, str(args.engine_src.resolve()))
    import memory_book
    from memory_book import MemoryBook
    require(Path(memory_book.__file__).resolve().parent == (args.engine_src / "memory_book").resolve(),
            "Worker imported a different runtime")
    source = verify_source(args.engine_src, args.mode, binding)
    counters = {e: TokenCounter(e) for e in ENCODINGS}
    require({counter.version for counter in counters.values()} == {"0.12.0"}, "Unexpected tokenizer version")
    hashes = evaluator_hashes()
    sources = original_turn_texts(data)
    report = {"mode": args.mode, "cohort": args.cohort, "status": "running", "started_at": now(),
        "source": source, "dataset": data.description(), "query_ids": sorted(c.id for c in data.queries),
        "query_ids_original_order": [c.id for c in data.queries], "evaluator_hashes": hashes,
        "configurations": [], "error": None}
    write_json(args.output, report, compressed=True)
    try:
        with tempfile.TemporaryDirectory(prefix="novelty-old-worker-") as temporary:
            with MemoryBook(Path(temporary) / "memory.db", max_page_chars=900, cache_size=0) as book:
                started = time.perf_counter_ns()
                for session in data.sessions:
                    book.ingest(session)
                report["ingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["indexed_content"] = indexed_content(book.db)
                original = source_snapshot(book.db)
                pages = {r["id"]: r["content"] for r in book.db.execute("SELECT id,content FROM pages")}
                chapters = [tuple(r) for r in book.db.execute("SELECT project_id,external_id,chapter_id FROM sessions")]
                groups = {case.id: diagnostics(case, chapters) for case in data.queries}
                for budget in BUDGETS:
                    config = {"budget_chars": 8000, "budget_tokens": budget, "tokenizer": "cl100k_base",
                              "rows": []}
                    report["configurations"].append(config)
                    cases = list(data.queries)
                    random.Random(61).shuffle(cases)
                    for case in cases:
                        report["last_attempt"] = {"query_id": case.id, "budget_tokens": budget, "status": "started"}
                        started = time.perf_counter_ns()
                        response = book.recall(case.query, project=case.project, budget_chars=8000,
                            budget_tokens=budget, tokenizer="cl100k_base", limit=5, use_cache=False,
                            coverage=False, semantic=False)
                        elapsed = (time.perf_counter_ns() - started) / 1e6
                        row = score_row(case, response, sources, counters, public=True)
                        context_tokens = row["context_tokens"]["cl100k_base"]
                        payload = canonical({k: v for k, v in response.items() if k not in {"latency_ms", "cache_hit"}})
                        row.update(groups[case.id], elapsed_ms=elapsed,
                            context_sha256=sha(response["context"].encode()), block_hashes=block_ids(response),
                            token_budget_violation=context_tokens > budget,
                            source_span_errors=source_errors(response, sources),
                            page_projection_errors=page_projection_errors(response, pages),
                            token_metadata_error=any((response.get("context_tokens") != context_tokens,
                                response.get("tokenizer") != "cl100k_base", response.get("budget_tokens") != budget,
                                response.get("tokenizer_version") != "0.12.0")),
                            semantic_metadata_error="semantic" in response, cache_hit_error=bool(response.get("cache_hit")),
                            returned_payload_tokens={e: c.count(payload) for e, c in counters.items()},
                            scope_errors=sum(r["breadcrumb"][0]["id"] != case.project for r in response["results"])
                                if case.project is not None else 0)
                        config["rows"].append(row)
                        report["last_attempt"]["status"] = "completed"
                        if len(config["rows"]) % 100 == 0:
                            write_json(args.output, report, compressed=True)
                    config.update(summarize(config["rows"]))
                    write_json(args.output, report, compressed=True)
                    print(json.dumps({"cohort": args.cohort, "mode": args.mode, "budget_tokens": budget,
                                      "completed": len(config["rows"])}), flush=True)
                report["originals_unchanged"] = original == source_snapshot(book.db)
                report["indexed_content_after"] = indexed_content(book.db)
                report["cache_rows"] = book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0]
        report["source_sha256_after"] = engine_source_hash(args.engine_src / "memory_book")
        report["evaluator_unchanged"] = hashes == evaluator_hashes()
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__})
        raise
    finally:
        report["finished_at"] = now()
        write_json(args.output, report, compressed=True)
    return report


def validate(report):
    plan, binding = registered()
    issues, by_cohort = [], {}
    expected = {(c, m) for c in COHORTS for m in MODES}
    observed = [(w["cohort"], w["mode"]) for w in report["workers"]]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        issues.append("worker_matrix")
    if report["plan"] != plan or report["binding"] != binding:
        issues.append("registration")
    for w in report["workers"]:
        name, mode = w["cohort"], w["mode"]
        identity = name + "/" + mode
        registered_cohort = next(c for c in plan["cohorts"] if c["name"] == name)
        if w["status"] != "completed":
            issues.append(identity + ":incomplete")
            continue
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
                or w["evaluator_hashes"] != report["evaluator_hashes"]):
            issues.append(identity + ":source_index_cache_or_evaluator")
        common = {key: w[key] for key in ("query_ids", "query_ids_original_order", "indexed_content")}
        if name in by_cohort and common != by_cohort[name]:
            issues.append(identity + ":different_common_archive_or_queries")
        by_cohort.setdefault(name, common)
        axes = [c["budget_tokens"] for c in w["configurations"]]
        if len(axes) != len(set(axes)) or set(axes) != set(BUDGETS):
            issues.append(identity + ":budget_matrix")
        order = list(w["query_ids_original_order"])
        random.Random(61).shuffle(order)
        for c in w["configurations"]:
            if (c["budget_chars"] != 8000 or c["tokenizer"] != "cl100k_base"
                    or [r["id"] for r in c["rows"]] != order):
                issues.append(identity + ":query_or_configuration")
            measured = summarize(c["rows"])
            if any(c[key] != value for key, value in measured.items()):
                issues.append(identity + ":aggregate")
            if (any(measured["invariants"].values()) or measured["metrics"]["budget_violations"]
                    or measured["metrics"]["context_size_mismatches"]):
                issues.append(identity + ":invariant")
            if any(not math.isfinite(r["elapsed_ms"]) or r["elapsed_ms"] < 0 or "query" in r for r in c["rows"]):
                issues.append(identity + ":timing_or_publication")
    if report.get("error") or not report.get("evaluator_unchanged"):
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(observed), "expected_workers": len(expected),
            "query_configuration_mode_samples": sum(len(c["rows"]) for w in report["workers"] for c in w["configurations"]),
            "expected_samples": sum(c["queries"] for c in plan["cohorts"]) * len(BUDGETS) * len(MODES)}


def comparisons(report):
    result = []
    lookup = {(w["cohort"], w["mode"]): w for w in report["workers"] if w["status"] == "completed"}
    for cohort in COHORTS:
        if (cohort, "default") not in lookup:
            continue
        baseline = lookup[(cohort, "default")]
        for mode in MODES[1:]:
            if (cohort, mode) not in lookup:
                continue
            for old, new in zip(baseline["configurations"], lookup[(cohort, mode)]["configurations"], strict=True):
                require(old["budget_tokens"] == new["budget_tokens"], "Paired budget mismatch")
                groups = {name: {"before": old["by_group"][name], "after": new["by_group"][name]}
                          for name in sorted(old["by_group"])}
                require(set(groups) == set(new["by_group"]), "Diagnostic group identities changed")
                result.append({"cohort": cohort, "mode": mode, "budget_tokens": old["budget_tokens"],
                    "baseline": {k: old[k] for k in ("metrics", "latency", "unsupported_nonempty", "mean_returned_payload_tokens")},
                    "candidate": {k: new[k] for k in ("metrics", "latency", "unsupported_nonempty", "mean_returned_payload_tokens")},
                    "by_group": groups, "paired_changes": paired_changes(old["rows"], new["rows"])})
    return result


def screen(comparisons, *, complete):
    if not complete:
        return {"status": "incomplete_no_selection", "candidates": {}}
    plan, _ = registered()
    decisions = {}
    for mode in MODES[1:]:
        cells = [c for c in comparisons if c["mode"] == mode]
        require(len(cells) == 12, "Incomplete candidate screen")
        losses, gains = [], []
        for c in cells:
            axis = {k: c[k] for k in ("cohort", "budget_tokens")}
            for metric in ("complete_evidence_rate", "evidence_recall"):
                before, after = c["baseline"]["metrics"][metric], c["candidate"]["metrics"][metric]
                if before is not None and after < before:
                    losses.append({**axis, "group": "all", "metric": metric, "before": before, "after": after})
                if before is not None and after > before:
                    gains.append({**axis, "metric": metric, "before": before, "after": after})
            if c["candidate"]["unsupported_nonempty"] > c["baseline"]["unsupported_nonempty"]:
                losses.append({**axis, "group": "unsupported", "metric": "nonempty_count"})
            if c["budget_tokens"] == 512:
                for group in plan["primary_diagnostic_groups"]:
                    values = c["by_group"].get(group)
                    if values is None or values["before"]["queries"] < 10:
                        continue
                    for metric in ("complete_evidence_rate", "evidence_recall"):
                        before, after = values["before"][metric], values["after"][metric]
                        if before is not None and after < before:
                            losses.append({**axis, "group": group, "metric": metric, "before": before, "after": after})
        decisions[mode] = {"worth_further_validation": not losses and bool(gains),
            "declared_screen_losses": losses, "aggregate_gains": gains}
    return {"status": "followup_candidate_exists" if any(v["worth_further_validation"] for v in decisions.values())
            else "stop_both_candidates_rejected_or_no_gain", "candidates": decisions,
            "product_default_changed": False, "latency_is_development_only": True}


def summary(report, raw, compressed):
    value = {k: v for k, v in report.items() if k != "workers"}
    value["workers"] = [{**{k: v for k, v in w.items() if k not in {"configurations", "query_ids", "query_ids_original_order"}},
        "configurations": [{k: v for k, v in c.items() if k != "rows"} for c in w["configurations"]]}
        for w in report["workers"]]
    return {**value, "full_report_sha256": sha(raw), "compressed_report_sha256": sha(compressed)}


def markdown(report):
    lines = ["# Bounded novelty: old-data development probe", "",
        "One pass, default lexical recall, 8,000 characters, cl100k_base; source-evidence retrieval only. "
        "Development timings are not a final latency comparison. Product default and the preceding frozen evaluation are unchanged.", "",
        "Measurement integrity: **" + ("PASS" if report["validation"]["passed"] else "INCOMPLETE / FAIL") + "**.", "",
        "| Cohort | Candidate | Cap | Complete before / after | Evidence before / after | Complete gains / losses | p95 before / after ms |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for c in report["comparisons"]:
        old, new = c["baseline"], c["candidate"]
        changes = c["paired_changes"]
        pair = lambda metric: f"{old['metrics'][metric]:.2%} / {new['metrics'][metric]:.2%}"
        lines.append(f"| {c['cohort']} | {c['mode']} | {c['budget_tokens']} | {pair('complete_evidence_rate')} | "
            f"{pair('evidence_recall')} | {len(changes['complete_question_gains'])} / {len(changes['complete_question_losses'])} | "
            f"{old['latency']['p95_ms']:.3f} / {new['latency']['p95_ms']:.3f} |")
    lines += ["", "## Predeclared follow-up screen", "", "Status: `" + report["screening"]["status"] + "`.", "",
        "All groups, including small groups and negative cases, remain in the JSON; each original per-question "
        "score, elapsed sample and paired gain/loss is retained in the gzip. The screen is conservative and is not a statistical test.", ""]
    for mode, decision in report["screening"]["candidates"].items():
        lines.append(f"- {mode}: further validation = {decision['worth_further_validation']}; "
            f"declared loss checks = {len(decision['declared_screen_losses'])}; aggregate improved metrics = {len(decision['aggregate_gains'])}.")
    return "\n".join(lines) + "\n"


def save_report(output, report):
    report["validation"] = validate(report)
    report["comparisons"] = comparisons(report)
    report["screening"] = screen(report["comparisons"], complete=report["validation"]["passed"])
    raw = write_json(output, report, compressed=True)
    prefix = str(output).removesuffix(".json.gz")
    write_json(Path(prefix + ".summary.json"), summary(report, raw, output.read_bytes()))
    Path(prefix + ".md").write_text(markdown(report))


def publish(output, branch):
    prefix = str(output.resolve().relative_to(ROOT)).removesuffix(".json.gz")
    paths = [prefix + suffix for suffix in (".json.gz", ".summary.json", ".md")]
    for command in (["git", "add", "--", *paths],
                    ["git", "commit", "-m", "bench: preserve bounded novelty development checkpoint"],
                    ["git", "push", "origin", "HEAD:refs/heads/" + branch]):
        subprocess.run(command, cwd=ROOT, check=True)


def audit(output):
    compressed = output.read_bytes()
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    require(report["evaluator_hashes"] == evaluator_hashes(), "Auditor dependencies differ from measured source")
    require(report["validation"] == validate(report) and report["validation"]["passed"], "Incomplete or invalid saved matrix")
    require(report["comparisons"] == comparisons(report), "Saved paired comparisons changed")
    require(report["screening"] == screen(report["comparisons"], complete=True), "Saved screen changed")
    expected = summary(report, raw, compressed)
    prefix = str(output).removesuffix(".json.gz")
    require(json.loads(Path(prefix + ".summary.json").read_text()) == expected, "Summary or original gzip bytes changed")
    require(Path(prefix + ".md").read_text() == markdown(report), "Markdown differs from recorded aggregates")
    print(json.dumps({"audit": "passed", "samples": report["validation"]["query_configuration_mode_samples"],
                      "screening": report["screening"]["status"], "full_report_sha256": sha(raw)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-data", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--sources-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--publish-branch")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=MODES, help=argparse.SUPPRESS)
    parser.add_argument("--cohort", choices=COHORTS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prepare_data:
        prepare_data(args.prepare_data)
        return
    if args.audit:
        audit(args.audit)
        return
    require(args.output is not None and args.data_dir is not None and args.output.name.endswith(".json.gz"),
            "Require --data-dir and a new .json.gz output")
    require(not args.output.exists(), "Preserve prior attempts; choose a new output path")
    if args.mode:
        require(args.engine_src is not None and args.cohort is not None, "Worker requires source and cohort")
        worker(args)
        return
    require(args.sources_root is not None, "Controller requires all three committed source worktrees")
    plan, binding = registered()
    hashes = evaluator_hashes()
    paths = {mode: args.sources_root.resolve() / mode / "src" for mode in MODES}
    sources = {mode: verify_source(path, mode, binding) for mode, path in paths.items()}
    report = {"protocol": plan["protocol"], "started_at": now(), "plan": plan, "binding": binding,
        "sources": sources, "evaluator_hashes": hashes, "evaluator_unchanged": False,
        "evaluator_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(), "cpu_count": os.cpu_count(),
            "tiktoken": importlib.metadata.version("tiktoken")}, "workers": [], "attempted_workers": [], "error": None,
        "cost_boundary": "Native full recall and token assembly wall time only. Original-source scoring, reference token recounting, checkpoint writing and ingestion excluded. Payload-token counts use complete native JSON excluding latency_ms/cache_hit diagnostics; no MCP wire or provider billing claim.",
        "data_boundary": "Four pinned old development/regression cohorts only; old128 Parquet filter occurs before question conversion. No new256 manifest, query set or results are accessed."}
    save_report(args.output, report)
    try:
        with tempfile.TemporaryDirectory(prefix="novelty-probe-controller-") as temporary:
            for index, cohort in enumerate(COHORTS):
                offset = index % len(MODES)
                for mode in MODES[offset:] + MODES[:offset]:
                    output = Path(temporary) / (cohort + "-" + mode + ".json.gz")
                    attempt = {"cohort": cohort, "mode": mode, "started_at": now(), "status": "started"}
                    report["attempted_workers"].append(attempt)
                    try:
                        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--engine-src", str(paths[mode]),
                            "--mode", mode, "--cohort", cohort, "--data-dir", str(args.data_dir.resolve()),
                            "--output", str(output)], check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                "PYTHONHASHSEED": "0"})
                        attempt["status"] = "completed"
                    finally:
                        attempt["finished_at"] = now()
                        if output.exists():
                            report["workers"].append(json.loads(gzip.decompress(output.read_bytes())))
                        save_report(args.output, report)
                        if args.publish_branch:
                            publish(args.output, args.publish_branch)
    except BaseException as error:
        report["error"] = {"type": type(error).__name__}
    report["evaluator_unchanged"] = hashes == evaluator_hashes()
    report["finished_at"] = now()
    save_report(args.output, report)
    if args.publish_branch:
        publish(args.output, args.publish_branch)
    print(json.dumps({"validation": report["validation"], "screening": report["screening"]["status"]}))
    require(report["validation"]["passed"], "Probe did not complete the registered matrix")


if __name__ == "__main__":
    main()
