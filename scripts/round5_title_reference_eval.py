"""Registered T1 development: 5,438 calls, eight cells, no fresh holdout.

Commit the reviewed runtime, this evaluator and its tests before --bind. Commit
the resulting binding before --run. --pause-after-cells allows remote Git
checkpointing between cells. Started partial cells are preserved, never replayed.
The evaluator exports source identities/counts/hashes, never corpus text.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.native_budget_eval import source_errors
from benchmarks.resume import _lock
from benchmarks.run import _evidence_rank, engine_source_hash, original_turn_texts
from benchmarks.semantic_eval import page_projection_errors, source_snapshot
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
    evidence_blocks, latency_summary, score_row, summarize_rows)
from scripts.benchmark_default_recall import dataset as old_dataset, indexed_content

PLAN = "benchmarks/experiments/round5-title-reference-plan.json"
PLAN_COMMIT = "8f8703f9025faf1902000d8f4ceb3730e287eee6"
OLD_BINDING = "benchmarks/experiments/round4-validation-binding.json"
OLD_MANIFEST = "benchmarks/experiments/round4-hotpot256-manifest.json"
VERSION = "round5-title-reference-t1-development-evaluator-1"
MODES = ("candidate_default", "candidate_follow_titles")
ERRORS = ("source", "projection", "scope", "chars", "tokens", "metadata", "cache", "policy", "limit", "reconstruction", "title_provenance")


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(raw(value).rstrip(b"\n")).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    value = Path(path).read_bytes()
    return json.loads(gzip.decompress(value) if str(path).endswith(".gz") else value)


def save(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = raw(value)
    if path.suffix == ".gz":
        data = gzip.compress(data, mtime=0)
    temporary = path if exclusive else path.with_name(path.name + ".partial")
    with temporary.open("xb" if exclusive else "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30, stderr=subprocess.DEVNULL)


def relative(path):
    path = Path(path).resolve()
    result = path.relative_to(ROOT).as_posix()
    require(path != ROOT and not Path(result).is_absolute(), "Expected a file/directory inside this checkout")
    return result


def committed(path):
    require(Path(path).read_bytes() == git("show", "HEAD:" + relative(path)), "Commit before scoring: " + relative(path))


def source(path):
    package = Path(path).resolve() / "memory_book"
    value = checkout_provenance(package)
    require(value["commit_identifies_source"], "Runtime must match an exact committed source")
    return {"commit": value["git_commit"], "runtime_sha256": engine_source_hash(package)}


def host():
    return {"boot_sha256": sha(Path("/proc/sys/kernel/random/boot_id")),
        "machine_sha256": hashlib.sha256(platform.node().encode()).hexdigest(),
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in ("tiktoken", "pyarrow")}}


def registry():
    # Include transitive pure evaluators. These bytes are bound, not rewritten.
    names = {p.relative_to(ROOT).as_posix() for p in (ROOT / "benchmarks").glob("*.py")}
    names.update({"scripts/round4_data.py", "scripts/benchmark_default_recall.py",
        "scripts/round5_title_reference_eval.py", "tests/test_round5_title_reference_eval.py",
        PLAN, OLD_BINDING, OLD_MANIFEST, "benchmarks/locomo_split.json",
        "benchmarks/experiments/round4-plan.json", "benchmarks/hotpot_manifest.json",
        "benchmarks/round2_hotpot256_manifest.json", "benchmarks/experiments/round3-hotpot256-manifest.json"})
    return {name: sha(ROOT / name) for name in sorted(names)}


def registered():
    require((ROOT / PLAN).read_bytes() == git("show", PLAN_COMMIT + ":" + PLAN), "Registered T1 scope changed")
    plan = read(ROOT / PLAN)
    require(plan["development"]["calls_total"] == 5438 and plan["development"]["repetitions"] == 1,
            "Registered call count changed")
    return plan


def schedule(plan):
    result = []
    for cohort in plan["development"]["cohorts"]:
        for config in cohort["configurations"]:
            result.append({"index": len(result), "cohort": cohort["id"], "queries": cohort["queries"], **config})
    require(len(result) == 8 and sum(c["queries"] * 2 for c in result) == 5438, "Wrong development matrix")
    return result


def data_for(name, locomo, parquet):
    if name != "round4-hotpot256":
        return old_dataset(name, locomo)
    from scripts.round4_data import load
    return load(parquet, ROOT / OLD_BINDING, ROOT / OLD_MANIFEST)


def query_schedule(ids, cell):
    ordered = list(ids)
    random.Random(61313 + cell["index"]).shuffle(ordered)
    return [(identity, mode) for pos, identity in enumerate(ordered)
            for mode in (MODES if pos % 2 == 0 else tuple(reversed(MODES)))]


def bind(args):
    plan = registered()
    require(args.source and args.locomo_path and args.parquet and args.state and args.output,
            "Binding needs reviewed source, both old inputs, fresh state and output directories")
    require(not args.state.exists() and not args.output.exists(), "Bind fresh attempt directories")
    files = registry()
    for name in files:
        committed(ROOT / name)
    datasets = {}
    for cohort in plan["development"]["cohorts"]:
        data = data_for(cohort["id"], args.locomo_path, args.parquet)
        ids = [q.id for q in data.queries]
        require(len(ids) == len(set(ids)) == cohort["queries"], "Incomplete/duplicate cohort")
        require(all(type(q.answerable) is bool and q.answerable == bool(q.required) for q in data.queries),
                "Registered cohort answerability must agree with required annotations")
        datasets[cohort["id"]] = {"sha256": data.fingerprint, "ids": ids}
    value = {"version": VERSION, "status": "frozen-before-development-calls", "created_at": now(),
        "plan_commit": PLAN_COMMIT, "plan_sha256": sha(ROOT / PLAN), "source": source(args.source),
        "evaluator_commit": git("rev-parse", "HEAD").decode().strip(), "evaluator_files": files,
        "datasets": datasets, "inputs": {"locomo_sha256": sha(args.locomo_path), "parquet_sha256": sha(args.parquet)},
        "schedule": schedule(plan), "expected_calls": 5438, "host": host(),
        "state": relative(args.state), "output": relative(args.output),
        "scope": "Registered old-data T1 development only; no fresh validation or default speed claim."}
    require(value["host"]["packages"]["tiktoken"] == "0.12.0", "Wrong reference tokenizer")
    save(args.bind, value, exclusive=True)
    print(json.dumps({"binding": str(args.bind), "next": "Commit and publish the binding before --run."}), flush=True)


def load_binding(path):
    committed(path)
    bound = read(path)
    registered()
    require(bound["version"] == VERSION and bound["status"] == "frozen-before-development-calls"
        and bound["plan_commit"] == PLAN_COMMIT and bound["plan_sha256"] == sha(ROOT / PLAN)
        and bound["evaluator_files"] == registry() and bound["schedule"] == schedule(registered()), "Binding differs from registered evaluator")
    for name, expected in bound["evaluator_files"].items():
        require(hashlib.sha256(git("show", bound["evaluator_commit"] + ":" + name)).hexdigest() == expected,
                "Evaluator was not committed before binding: " + name)
    return bound


def annotated_pages(case, response, originals):
    """Score every returned page, including later duplicate-supporting pages."""
    return [{"id": page["id"], "session_id": (page.get("source_refs") or [{}])[0].get("session_id"),
             "annotations": [index for index, annotation in enumerate(case.required)
                if _evidence_rank(annotation, [page], response["context"], case.project, originals) is not None]}
            for page in response["results"]]


def title_provenance(response, enabled, case, page_rows, originals):
    provenance = response.get("title_reference")
    if not enabled:
        require("title_reference" not in response, "Disabled T1 changed the native response")
        return None
    require(isinstance(provenance, dict) and provenance.get("version") == 1
            and type(provenance.get("active")) is bool and type(provenance.get("applied")) is bool
            and isinstance(provenance.get("reason"), str), "Missing real T1 shipping provenance")
    if not provenance["applied"]:
        require(provenance.get("target") is None
                and provenance.get("target_initial_page_in_pool") is None
                and provenance.get("target_initial_session_in_pool") is None, "Unexamined membership must be absent/null")
        return provenance
    require(provenance["active"] and case.project is not None, "Applied T1 lacks scoped activation")
    anchor, target, mention = provenance["anchor"], provenance["target"], provenance["mention"]
    for item in (anchor, target):
        page = page_rows[item["page_id"]]
        require(page["session_id"] == item["session_id"] and page["session_pk"] == item["session_pk"]
                and page["project_id"] == case.project, "T1 source identity/scope changed")
    require(anchor["session_pk"] != target["session_pk"], "T1 followed its own source")
    for field in ("target_initial_page_in_pool", "target_initial_session_in_pool"):
        require(type(provenance[field]) is bool, "Chosen target membership must be a strict boolean")
    require(not provenance["target_initial_page_in_pool"] or provenance["target_initial_session_in_pool"], "Page membership contradicts source membership")
    require(target["route"] in ("lexical", "title_reference"), "Unknown T1 route")
    require((target["route"] == "lexical") == provenance["target_initial_page_in_pool"], "T1 route/membership differ")
    lo, hi = mention["page_span"]
    a, b = mention["turn_span"]
    page = page_rows[anchor["page_id"]]
    require(all(type(x) is int for x in (lo, hi, a, b, mention["turn_index"]))
            and 0 <= lo < hi <= min(4096, len(page["content"])), "Invalid mention span")
    original = originals[(case.project, anchor["session_id"], mention["turn_index"])]
    require(0 <= a < b <= len(original) and page["content"][lo:hi] == original[a:b], "Mention is not original source text")
    require(any(ref["turn_index"] == mention["turn_index"] and ref["start"] <= lo < hi <= ref["end"]
            and a == ref["turn_start"] + lo - ref["start"] and b == ref["turn_start"] + hi - ref["start"]
            for ref in json.loads(page["source_refs"])), "Mention crosses source references")
    normalize = lambda text: " ".join(text.casefold().split())
    require(normalize(original[a:b]) == normalize(page_rows[target["page_id"]]["session_title"]), "Mention does not equal complete target title")
    return provenance


def scored(case, response, elapsed, enabled, config, counters, originals, page_rows, cache_rows, page_texts=None):
    response = dict(response)
    response.pop("latency_ms")
    row = score_row(case, response, originals, counters, public=True)
    row["wall_ms"] = elapsed
    row["native_payload_sha256"] = digest(response)
    row["context_sha256"] = hashlib.sha256(response["context"].encode()).hexdigest()
    row["response_utf8_bytes"] = len(raw(response).rstrip(b"\n"))
    row["response_tokens"] = {name: counter.count(raw(response).decode().rstrip("\n")) for name, counter in counters.items()}
    row["annotated_pages"] = annotated_pages(case, response, originals)
    row["annotated_page_hits"] = sum(bool(p["annotations"]) for p in row["annotated_pages"])
    row["annotated_page_precision"] = row["annotated_page_hits"] / row["result_count"] if row["result_count"] else None
    try:
        evidence_blocks(response)
        reconstruction = 0
    except ValueError:
        reconstruction = 1
    try:
        row["title_reference"] = title_provenance(response, enabled, case, page_rows, originals)
        provenance_error = 0
    except (ValueError, KeyError, TypeError, IndexError):
        row["title_reference"] = response.get("title_reference")
        provenance_error = 1
    row["errors"] = {
        "source": source_errors(response, originals),
        "projection": page_projection_errors(response, page_texts if page_texts is not None else {key: p["content"] for key, p in page_rows.items()}),
        "scope": sum(int(case.project is not None and item["breadcrumb"][0]["id"] != case.project)
            + sum(ref.get("project") != item["breadcrumb"][0]["id"] for ref in item["source_refs"])
            for item in response["results"]),
        "chars": int(len(response["context"]) > 8000),
        "tokens": int(row["context_tokens"][config["tokenizer"]] > config["budget_tokens"]),
        "metadata": int(response.get("context_chars") != len(response["context"])
            or response.get("budget_chars") != 8000 or response.get("budget_tokens") != config["budget_tokens"]
            or response.get("tokenizer") != config["tokenizer"] or response.get("tokenizer_version") != "0.12.0"
            or response.get("context_tokens") != row["context_tokens"][config["tokenizer"]] or response.get("query") != case.query),
        "cache": int(cache_rows != 0 or response.get("cache_hit") is not False),
        "policy": int(bool(response.get("semantic") or response.get("project_local_fts_statistics"))),
        "limit": int(len(response["results"]) > 5 or len(set(row["result_ids"])) != len(row["result_ids"])),
        "reconstruction": reconstruction, "title_provenance": provenance_error}
    return row


def paired_changes(off, on):
    """Native payload differences include ON-only metadata; they are diagnostic, not quality."""
    old = {p["id"]: p for p in off["annotated_pages"]}
    new = {p["id"]: p for p in on["annotated_pages"]}
    introduced, displaced = [new[k] for k in new if k not in old], [old[k] for k in old if k not in new]
    old_sessions = {p["session_id"] for p in old.values()}
    provenance = on["title_reference"]
    target = provenance.get("target") if provenance else None
    return {"id": off["id"], "annotation_gains": [i for i, (a, b) in enumerate(zip(off["evidence_ranks"], on["evidence_ranks"], strict=True)) if a is None and b is not None],
        "annotation_losses": [i for i, (a, b) in enumerate(zip(off["evidence_ranks"], on["evidence_ranks"], strict=True)) if a is not None and b is None],
        "complete_gain": not off["complete"] and on["complete"], "complete_loss": off["complete"] and not on["complete"],
        "introduced": introduced, "displaced": displaced,
        "introduced_existing_session_pages": sum(p["session_id"] in old_sessions for p in introduced),
        "introduced_new_session_pages": sum(p["session_id"] not in old_sessions for p in introduced),
        "target_returned": bool(target and target["page_id"] in new),
        "unsupported_changed": not off["answerable"] and (off["context_sha256"] != on["context_sha256"]),
        "native_payload_changed": off["native_payload_sha256"] != on["native_payload_sha256"]}


def metrics(rows):
    result = summarize_rows(rows)
    pages = sum(r["result_count"] for r in rows)
    hits = sum(r["annotated_page_hits"] for r in rows)
    ratios = [r["annotated_page_precision"] for r in rows if r["annotated_page_precision"] is not None]
    result.update(annotated_pages=hits, returned_pages=pages,
        annotated_page_precision=hits / pages if pages else None,
        macro_annotated_page_precision=statistics.fmean(ratios) if ratios else None,
        macro_precision_queries=len(ratios), zero_page_queries=sum(not r["result_count"] for r in rows),
        latency=latency_summary([r["wall_ms"] for r in rows]),
        mean_response_tokens={name: statistics.fmean(r["response_tokens"][name] for r in rows) for name in ENCODINGS},
        mean_response_utf8_bytes=statistics.fmean(r["response_utf8_bytes"] for r in rows))
    return result


def assess_cell(cell, plan):
    rows = {mode: [r["score"] for r in cell["rows"] if r["mode"] == mode] for mode in MODES}
    off, on = ({r["id"]: r for r in rows[mode]} for mode in MODES)
    require(set(off) == set(on), "Missing paired query")
    before, after = metrics(rows[MODES[0]]), metrics(rows[MODES[1]])
    changes = [paired_changes(off[identity], on[identity]) for identity in off]
    introduced = [p for row in changes for p in row["introduced"]]
    displaced = [p for row in changes for p in row["displaced"]]
    hit_rate = lambda pages: sum(bool(p["annotations"]) for p in pages) / len(pages) if pages else None
    intro_rate, displaced_rate = hit_rate(introduced), hit_rate(displaced)
    deltas = {name: after[name] - before[name] if after[name] is not None and before[name] is not None else None
              for name in ("complete_evidence_rate", "evidence_recall", "annotated_page_precision", "mrr")}
    primary = cell["configuration"]["cohort"] == "round4-hotpot256" and cell["configuration"]["tokenizer"] == "cl100k_base" and cell["configuration"]["budget_tokens"] == 1024
    threshold = plan["development"]["gate"]
    losses = sum(row["complete_loss"] for row in changes)
    p95_ms = after["latency"]["p95_ms"] - before["latency"]["p95_ms"]
    p95_percent = 100 * p95_ms / before["latency"]["p95_ms"]
    failed = []
    if primary:
        for name, key in (("complete_evidence_rate", "complete_rate_gain_minimum_pp"),
                          ("evidence_recall", "annotation_recall_gain_minimum_pp"),
                          ("annotated_page_precision", "annotated_page_precision_gain_minimum_pp")):
            if deltas[name] is None or 100 * deltas[name] + 1e-9 < threshold[key]:
                failed.append(name + "_primary_gain")
        if losses / len(off) > threshold["primary_complete_loss_rate_maximum"] + 1e-9:
            failed.append("primary_complete_losses")
        if intro_rate is None or intro_rate + 1e-9 < threshold["introduced_page_annotation_hit_rate_minimum"]:
            failed.append("introduced_page_hit_rate")
        if displaced_rate is not None and (intro_rate is None or intro_rate + 1e-9 < displaced_rate):
            failed.append("introduced_vs_displaced")
    else:
        for name in ("complete_evidence_rate", "evidence_recall", "annotated_page_precision"):
            if deltas[name] is None or deltas[name] < -0.01 - 1e-9:
                failed.append(name + "_regression")
    if deltas["mrr"] is None or deltas["mrr"] < -threshold["mrr_maximum_decline"] - 1e-9:
        failed.append("mrr_regression")
    if cell["configuration"]["cohort"] == "round4-hotpot256" and cell["configuration"]["budget_tokens"] == 512 and (deltas["complete_evidence_rate"] is None or deltas["complete_evidence_rate"] < -1e-9):
        failed.append("hotpot512_complete_decline")
    if p95_ms > 1 + 1e-9 or p95_percent > 20 + 1e-9:
        failed.append("p95_cost")
    if any(any(row["errors"].values()) for mode_rows in rows.values() for row in mode_rows):
        failed.append("integrity")
    provenance = [r["title_reference"] for r in rows[MODES[1]]]
    return {"configuration": cell["configuration"], "primary": primary, "off": before, "on": after,
        "deltas": deltas, "complete_gain_ids": [r["id"] for r in changes if r["complete_gain"]],
        "complete_loss_ids": [r["id"] for r in changes if r["complete_loss"]], "paired_changes": changes,
        "introduced_pages": len(introduced), "introduced_hit_rate": intro_rate,
        "displaced_pages": len(displaced), "displaced_hit_rate": displaced_rate,
        "activation_reasons": dict(Counter(p["reason"] for p in provenance if p)),
        "applied_queries": sum(bool(p and p["applied"]) for p in provenance),
        "target_initial_page_in_pool": dict(Counter(str(p.get("target_initial_page_in_pool")) for p in provenance if p and p["applied"])),
        "target_initial_session_in_pool": dict(Counter(str(p.get("target_initial_session_in_pool")) for p in provenance if p and p["applied"])),
        "p95_increase_ms": p95_ms, "p95_increase_percent": p95_percent,
        "passed": not failed, "failed_gates": failed}


def cell_paths(bound, index):
    output = ROOT / bound["output"] / f"cell-{index:02d}.json.gz"
    return output, output.with_name(output.name + ".attempts.jsonl"), ROOT / bound["state"] / f"cell-{index:02d}"


def verify_cell(value, ledger, bound, cell):
    require(value["status"] == "completed" and value["configuration"] == cell
            and value["binding_sha256"] == digest(bound) and value["source"] == bound["source"]
            and value["source_after"] == bound["source"] and value["host"] == bound["host"], "Incomplete or changed cell")
    require(value["dataset_sha256"] == bound["datasets"][cell["cohort"]]["sha256"]
            and value["source_snapshot_before"] == value["source_snapshot_after"]
            and value["index_before"] == value["index_after"], "Data/source/index changed")
    expected = query_schedule(bound["datasets"][cell["cohort"]]["ids"], cell)
    require([(r["score"]["id"], r["mode"]) for r in value["rows"]] == expected, "Missing, duplicate or reordered calls")
    require(value["started"] == value["finished"] == len(expected), "Call ledger is incomplete")
    events = [json.loads(line) for line in ledger.splitlines()]
    require(hashlib.sha256(ledger).hexdigest() == value["ledger_sha256"] and len(events) == 2 * len(expected), "Attempt ledger differs")
    for number, row in enumerate(value["rows"]):
        start, finish = events[2 * number:2 * number + 2]
        require(start == {"event": "started", "seq": number, "id": row["score"]["id"], "mode": row["mode"]}
                and finish == {"event": "finished", "seq": number, "row": row}, "Ledger differs from saved calls")
        score = row["score"]
        require(type(score["wall_ms"]) in (float, int) and math.isfinite(score["wall_ms"]) and score["wall_ms"] > 0,
                "Invalid timing sample")
        require(set(score["errors"]) == set(ERRORS) and not any(score["errors"].values()), "Integrity failure")
        require(type(score["answerable"]) is bool and type(score["required_evidence"]) is int
                and score["required_evidence"] >= 0 and score["answerable"] == bool(score["required_evidence"]),
                "Answerability and required annotations differ")
        require(score["required_evidence"] == len(score["evidence_ranks"])
            and score["matched_evidence"] == sum(r is not None for r in score["evidence_ranks"])
            and score["result_ids"] == [p["id"] for p in score["annotated_pages"]]
            and score["result_count"] == len(score["annotated_pages"])
            and score["annotated_page_hits"] == sum(bool(p["annotations"]) for p in score["annotated_pages"]), "Evidence/page accounting differs")
        for page in score["annotated_pages"]:
            require(page["annotations"] == sorted(set(page["annotations"])) and all(type(i) is int and 0 <= i < score["required_evidence"] for i in page["annotations"]), "Invalid per-page annotations")
        page_ranks = [next((rank for rank, page in enumerate(score["annotated_pages"], 1) if annotation in page["annotations"]), None)
                      for annotation in range(score["required_evidence"])]
        require(score["evidence_ranks"] == page_ranks, "Independent page annotations and first matching evidence ranks differ")
        found = [rank for rank in page_ranks if rank is not None]
        require(score["complete"] == (bool(page_ranks) and len(found) == len(page_ranks))
                and score["reciprocal_rank"] == (1 / min(found) if found else 0.0)
                and score["annotated_page_precision"] == (score["annotated_page_hits"] / score["result_count"] if score["result_count"] else None),
                "Stored complete/MRR/page precision differs")
    require(value["assessment"] == assess_cell(value, registered()), "Saved assessment differs")


def worker(args):
    bound = load_binding(args.binding)
    require(host() == bound["host"] and source(args.source) == bound["source"], "Source/host differs from binding")
    require(sha(args.locomo_path) == bound["inputs"]["locomo_sha256"] and sha(args.parquet) == bound["inputs"]["parquet_sha256"], "Input bytes differ")
    cell = bound["schedule"][args.worker]
    output, ledger_path, state = cell_paths(bound, args.worker)
    require(len(completed_prefix(bound)) == args.worker, "Only the next never-started cell can run")
    require(not output.exists() and not ledger_path.exists() and not state.exists(), "Never replay a started cell")
    data = data_for(cell["cohort"], args.locomo_path, args.parquet)
    require(data.fingerprint == bound["datasets"][cell["cohort"]]["sha256"], "Dataset fingerprint differs")
    state.mkdir(parents=True)
    sys.path.insert(0, str(args.source.resolve()))
    import memory_book
    require(Path(memory_book.__file__).resolve().parent == args.source.resolve() / "memory_book", "Imported another runtime")
    report = {"version": VERSION, "status": "running", "configuration": cell, "binding_sha256": digest(bound),
        "source": bound["source"], "host": bound["host"], "dataset_sha256": data.fingerprint,
        "created_at": now(), "rows": [], "started": 0, "finished": 0, "error": None}
    save(output, report)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ledger_path.open("x", encoding="utf-8") as ledger, memory_book.MemoryBook(state / "book.db", max_page_chars=900, cache_size=0) as book:
            def event(value):
                ledger.write(raw(value).decode())
                ledger.flush()
                os.fsync(ledger.fileno())
            for session in data.sessions:
                book.ingest(session)
            report["source_snapshot_before"] = source_snapshot(book.db)
            report["index_before"] = indexed_content(book.db)
            originals = original_turn_texts(data)
            pages = {r["id"]: dict(r) for r in book.db.execute("SELECT p.*,s.external_id session_id,s.title session_title FROM pages p JOIN sessions s ON s.id=p.session_pk")}
            page_texts = {key: page["content"] for key, page in pages.items()}
            counters = {name: TokenCounter(name) for name in ENCODINGS}
            for counter in counters.values():
                require(counter.version == "0.12.0", "Wrong reference tokenizer")
                counter.count("Prewarm both reference tokenizers before retrieval.")
            cases = {q.id: q for q in data.queries}
            for seq, (identity, mode) in enumerate(query_schedule(bound["datasets"][cell["cohort"]]["ids"], cell)):
                case = cases[identity]
                require(book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0] == 0, "Cache not empty before call")
                event({"event": "started", "seq": seq, "id": identity, "mode": mode})
                report["started"] += 1
                enabled = mode == MODES[1]
                begin = time.perf_counter_ns()
                response = book.recall(case.query, project=case.project, budget_chars=8000,
                    budget_tokens=cell["budget_tokens"], tokenizer=cell["tokenizer"], limit=5,
                    use_cache=False, coverage=False, semantic=False, follow_titles=enabled)
                elapsed = (time.perf_counter_ns() - begin) / 1e6
                count = book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0]
                row = {"mode": mode, "score": scored(case, response, elapsed, enabled, cell, counters, originals, pages, count, page_texts)}
                event({"event": "finished", "seq": seq, "row": row})
                report["rows"].append(row)
                report["finished"] += 1
                require(not any(row["score"]["errors"].values()), "T1 source/scope/budget/provenance invariant failed")
                if report["finished"] % 64 == 0:
                    save(output, report)
            report["source_snapshot_after"] = source_snapshot(book.db)
            report["index_after"] = indexed_content(book.db)
        report["source_after"] = source(args.source)
        require(report["source_after"] == report["source"], "Runtime changed during scoring")
        report["assessment"] = assess_cell(report, registered())
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed_or_interrupted", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if ledger_path.exists():
            report["ledger_sha256"] = sha(ledger_path)
        report["finished_at"] = now()
        save(output, report)
    verify_cell(report, ledger_path.read_bytes(), bound, cell)


def completed_prefix(bound):
    result, gap = [], False
    for cell in bound["schedule"]:
        output, ledger, state = cell_paths(bound, cell["index"])
        if not any(p.exists() for p in (output, ledger, state)):
            gap = True
            continue
        # Completed source-free rows/ledgers suffice for offline audit. The
        # private per-cell SQLite database need not be retained or published.
        require(not gap and output.exists() and ledger.exists(), "Preserve incomplete/out-of-order cell; do not replay")
        value = read(output)
        verify_cell(value, ledger.read_bytes(), bound, cell)
        result.append(value)
    return result


def summary_value(bound, cells):
    complete = len(cells) == len(bound["schedule"]) and sum(c["finished"] for c in cells) == bound["expected_calls"]
    value = {"version": VERSION, "binding_sha256": digest(bound), "status": "complete" if complete else "partial",
        "completed_calls": sum(c["finished"] for c in cells), "expected_calls": bound["expected_calls"],
        "accepted": complete and all(c["assessment"]["passed"] for c in cells),
        "cells": [{"path": relative(cell_paths(bound, c["configuration"]["index"])[0]),
                   "sha256": sha(cell_paths(bound, c["configuration"]["index"])[0]), **c["assessment"]} for c in cells],
        "limits": "One-repeat old-data development screen. Annotation precision is not exhaustive relevance; no generated-answer claim. Native payload change is diagnostic only: ON adds title_reference metadata even without a retrieval change. Target-only provenance does not establish all missing annotations' candidate-pool reachability. A failed gate rejects this fixed T1 hypothesis."}
    return value


def summarize(bound, cells):
    value = summary_value(bound, cells)
    save(ROOT / bound["output"] / "summary.json", value)
    return value


def run(args):
    bound = load_binding(args.binding)
    require(args.source and args.locomo_path and args.parquet, "Run needs exact source and both data paths")
    lock = ROOT / bound["state"]
    lock.parent.mkdir(parents=True, exist_ok=True)
    with _lock(lock):
        cells = completed_prefix(bound)
        done = 0
        for cell in bound["schedule"][len(cells):]:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(cell["index"]),
                "--binding", str(args.binding.resolve()), "--source", str(args.source.resolve()),
                "--locomo-path", str(args.locomo_path.resolve()), "--parquet", str(args.parquet.resolve())]
            subprocess.run(command, check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            cells = completed_prefix(bound)
            summarize(bound, cells)
            print(json.dumps({"checkpoint": cell["index"], "completed_calls": sum(c["finished"] for c in cells),
                              "output": bound["output"]}), flush=True)
            done += 1
            if args.pause_after_cells and done >= args.pause_after_cells:
                break
        summary = summarize(bound, cells)
    print(json.dumps({"status": summary["status"], "accepted": summary["accepted"], "completed_calls": summary["completed_calls"]}), flush=True)
    return 0 if summary["status"] == "partial" or summary["accepted"] else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--parquet", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--pause-after-cells", type=int, default=0)
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.bind:
        bind(args)
        return 0
    require(args.binding is not None, "An exact committed binding is required")
    if args.worker is not None:
        require(0 <= args.worker < 8, "Unregistered cell")
        worker(args)
        return 0
    if args.audit:
        bound = load_binding(args.binding)
        cells = completed_prefix(bound)
        require(len(cells) == 8, "Incomplete attempt; preserve it")
        expected = read(ROOT / bound["output"] / "summary.json")
        actual = summary_value(bound, cells)
        require(actual == expected, "Stored summary differs from original cells")
        print(json.dumps({"verified": True, "retrieval_calls_executed": 0, "accepted": actual["accepted"]}))
        return 0
    require(args.run, "Choose --bind, --run or --audit")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
