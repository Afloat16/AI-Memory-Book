"""Frozen fresh T1 native validation: five workers, 15,360 native calls.

This CLI separates binding, metadata-only selection, selected-data binding,
published one-use worker intents, worker execution and read-only audit. Never
run --select/--prepare-data/--worker until the preceding artifact is published.
Import and artificial tests execute no data selection, retrieval or models.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_title_reference_fresh_data_v2 as d
from scripts import round5_title_reference_eval_v2 as scoring
from scripts.round5_source_content_snapshot import source_content_snapshot, verify_content_snapshot
from scripts.benchmark_default_recall import indexed_content
from benchmarks.run import original_turn_texts
from benchmarks.semantic_eval import source_snapshot
from benchmarks.token_compare import ENCODINGS, TokenCounter, latency_summary
from benchmarks.round2_resources import storage

require, read, save, raw, sha, digest, now = d.require, d.read, d.save, d.raw, d.sha, d.digest, d.now


def paths(bound, index):
    stem = "worker-" + str(index).zfill(2)
    public, private = ROOT / bound["output"], ROOT / bound["state"]
    return {"report": public / (stem + ".json.gz"), "ledger": public / (stem + ".attempts.jsonl"),
            "archive": public / (stem + ".attempts.jsonl.gz"), "intent": public / (stem + ".intent.json"),
            "state": private / stem, "ticket": private / "tickets" / (stem + ".ticket")}


def atomic_bytes(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("wb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def ledger_bytes(locations):
    original = locations["ledger"].read_bytes() if locations["ledger"].exists() else None
    archived = gzip.decompress(locations["archive"].read_bytes()) if locations["archive"].exists() else None
    require(original is not None or archived is not None, "Missing original/compressed ledger")
    require(original is None or archived is None or original == archived, "Ledger archive differs from original")
    return original if original is not None else archived


def call_schedule(bound, selected_ids):
    return [(config["index"], identity) for config in bound["configurations"]
            for identity in d.query_order(selected_ids, config)]


def verify_score(score, config, expected, enabled):
    require(type(score["wall_ms"]) in (int, float) and math.isfinite(score["wall_ms"]) and score["wall_ms"] > 0,
            "Invalid native timing")
    scoring.verify_metadata_diagnostics(score, config)
    require(set(score["errors"]) == set(scoring.ERRORS) and not any(score["errors"].values()), "Native integrity failure")
    require(type(score["returned_characters"]) is int and 0 <= score["returned_characters"] <= 8000
            and set(score["context_tokens"]) == set(score["response_tokens"]) == set(ENCODINGS)
            and all(type(value) is int and value >= 0 for counts in (score["context_tokens"], score["response_tokens"])
                    for value in counts.values())
            and score["context_tokens"][config["tokenizer"]] <= config["budget_tokens"]
            and score["budget_violation"] is False and score["context_size_consistent"] is True,
            "Recorded actual context violates its character/token boundary")
    require(score["answerable"] is True and score["required_evidence"] == expected["required_evidence"]
            and score["project"] == expected["project"] and score["category"] == expected["category"]
            and score["metadata_diagnostics"]["input_query"] == expected["input_query"]
            and score["metadata_diagnostics"]["expected"]["query"] == expected["expected_query"], "Saved question/annotation identity differs")
    require(type(score["required_evidence"]) is int and score["required_evidence"] > 0, "Invalid required annotation count")
    pages = score["annotated_pages"]
    ids = [page["id"] for page in pages]
    require(ids == score["result_ids"] and len(ids) == len(set(ids)) == score["result_count"] <= 5,
            "Returned page identity/limit differs")
    for page in pages:
        require(page["annotations"] == sorted(set(page["annotations"]))
                and all(type(i) is int and 0 <= i < score["required_evidence"] for i in page["annotations"]), "Invalid actual-page annotations")
    ranks = [next((rank for rank, page in enumerate(pages, 1) if annotation in page["annotations"]), None)
             for annotation in range(score["required_evidence"])]
    found = [rank for rank in ranks if rank is not None]
    hits = sum(bool(page["annotations"]) for page in pages)
    require(score["evidence_ranks"] == ranks and score["matched_evidence"] == len(found)
            and score["complete"] == (len(found) == len(ranks))
            and score["reciprocal_rank"] == (1 / min(found) if found else 0.0)
            and score["annotated_page_hits"] == hits
            and score["annotated_page_precision"] == (hits / len(pages) if pages else None), "Independent page/rank accounting differs")
    require(isinstance(score["native_payload_sha256"], str) and len(score["native_payload_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in score["native_payload_sha256"]), "Invalid complete payload digest")
    provenance = score["title_reference"]
    require((isinstance(provenance, dict) and provenance.get("version") == 1
             and type(provenance.get("active")) is bool and type(provenance.get("applied")) is bool
             and isinstance(provenance.get("reason"), str)) if enabled else provenance is None,
            "Shipping provenance does not match the worker mode")


def verify_intent(intent, bound, binding_path, spec):
    require(intent["version"] == d.VERSION and intent["status"] == "intent-before-single-use-launch"
            and intent["worker"] == spec and intent["binding_sha256"] == sha(binding_path)
            and intent["selection_sha256"] == sha(ROOT / bound["selection"])
            and intent["data_binding_sha256"] == sha(ROOT / bound["data_binding"])
            and intent["completed_prefix"] == list(range(spec["index"])) and intent["host"] == bound["host"]
            and re.fullmatch("[0-9a-f]{40}", intent["prior_publication_commit"])
            and re.fullmatch("[0-9a-f]{64}", intent["ticket_sha256"]), "Worker intent differs")


def verify_source_identity(report):
    verify_content_snapshot(report["source_content_before"])
    require(report["source_snapshot_before"] == report["source_snapshot_after"],
            "Full source snapshot changed within the worker")
    require(report["source_content_before"] == report["source_content_after"],
            "Deterministic source content changed within the worker")


def verify_cross_worker_sources(reports):
    require(len(reports) == 5, "All five original native workers are required")
    for report in reports:
        verify_source_identity(report)
    require(all(report["source_content_before"] == reports[0]["source_content_before"]
                and report["index_before"] == reports[0]["index_before"] for report in reports),
            "Workers did not use identical deterministic source content and lexical index contents")


def verify_worker(report, ledger, bound, binding_path, selection, data_binding, spec):
    require(report["version"] == d.VERSION and report["status"] == "completed" and report["worker"] == spec
            and report["binding_sha256"] == sha(binding_path)
            and report["selection_sha256"] == sha(ROOT / bound["selection"])
            and report["data_binding_sha256"] == sha(ROOT / bound["data_binding"])
            and report["source"] == report["source_after"] == bound["sources"][spec["source"]]
            and report["host"] == bound["host"] and report["error"] is None, "Incomplete worker or changed source/binding/host")
    intent_path = paths(bound, spec["index"])["intent"]
    intent = read(intent_path)
    verify_intent(intent, bound, binding_path, spec)
    require(report["intent_sha256"] == sha(intent_path)
            and re.fullmatch("[0-9a-f]{40}", report["intent_publication_commit"])
            and intent_path.read_bytes() == d.git("show", report["intent_publication_commit"] + ":" + d.relative(intent_path)),
            "Worker intent was not preserved at its recorded pre-launch checkpoint")
    require(report["dataset_sha256"] == data_binding["dataset_sha256"]
            and report["source_snapshot_before"] == report["source_snapshot_after"]
            and report["index_before"] == report["index_after"], "Data/source/index changed")
    verify_source_identity(report)
    ordered = call_schedule(bound, selection["selected_ids"])
    require(len(ordered) == report["started"] == report["finished"] == 3072
            and [(r["configuration"], r["score"]["id"]) for r in report["rows"]] == ordered, "Missing/reordered/duplicate native calls")
    require(ledger.endswith(b"\n") and hashlib.sha256(ledger).hexdigest() == report["ledger_sha256"], "Truncated/changed ledger")
    events = [json.loads(line) for line in ledger.splitlines()]
    require(len(events) == 6144, "Incomplete attempt events")
    for sequence, row in enumerate(report["rows"]):
        config = bound["configurations"][row["configuration"]]
        require(events[2 * sequence] == {"event": "started", "seq": sequence,
                "configuration": config["index"], "id": row["score"]["id"], "worker": spec["id"]}
                and events[2 * sequence + 1] == {"event": "finished", "seq": sequence, "row": row}, "Ledger does not preserve original calls")
        verify_score(row["score"], config, data_binding["queries"][row["score"]["id"]], spec["follow_titles"])


def completed_prefix(bound, binding_path, selection, data_binding):
    reports, gap = [], False
    for spec in bound["workers"]:
        location = paths(bound, spec["index"])
        if not any(location[key].exists() for key in ("report", "ledger", "archive", "state")):
            gap = True
            continue
        require(not gap and location["report"].exists(), "Preserve incomplete/out-of-order worker; never replay")
        report = read(location["report"])
        verify_worker(report, ledger_bytes(location), bound, binding_path, selection, data_binding, spec)
        reports.append(report)
    return reports


def context(args):
    bound = d.load_binding(args.binding)
    selection = d.load_selection(bound, args.binding)
    data_binding = d.frozen_data(bound, args.binding, selection)
    return bound, selection, data_binding


def published_prefix_paths(bound, binding_path, completed):
    result = [binding_path, ROOT / bound["selection"], ROOT / bound["data_binding"]]
    for report in completed:
        location = paths(bound, report["worker"]["index"])
        result.extend(location[key] for key in ("intent", "report", "archive"))
    return result


def create_intent(args):
    bound, selection, data_binding = context(args)
    (ROOT / bound["state"]).parent.mkdir(parents=True, exist_ok=True)
    with scoring._lock(ROOT / bound["state"]):
        done = completed_prefix(bound, args.binding, selection, data_binding)
        require(args.intent == len(done) and 0 <= args.intent < 5, "Only the next never-started worker may obtain an intent")
        require(d.host() == bound["host"], "Resume requires the original host/boot")
        d.published(bound, args.published_commit, published_prefix_paths(bound, args.binding, done))
        spec, location = bound["workers"][args.intent], paths(bound, args.intent)
        require(not any(path.exists() for path in location.values()), "Preserve any prior intent/ticket/attempt")
        remote_path = d.git("ls-tree", args.published_commit, "--", d.relative(location["intent"]))
        require(not remote_path, "Remote intent already exists; do not recreate a lost launch ticket")
        ticket = secrets.token_hex(32).encode()
        location["ticket"].parent.mkdir(parents=True, exist_ok=True)
        with location["ticket"].open("xb") as stream:
            stream.write(ticket)
            stream.flush()
            os.fsync(stream.fileno())
        intent = {"version": d.VERSION, "status": "intent-before-single-use-launch", "worker": spec,
            "binding_sha256": sha(args.binding), "selection_sha256": sha(ROOT / bound["selection"]),
            "data_binding_sha256": sha(ROOT / bound["data_binding"]), "host": bound["host"],
            "prior_publication_commit": args.published_commit, "completed_prefix": [r["worker"]["index"] for r in done],
            "ticket_sha256": hashlib.sha256(ticket).hexdigest(), "created_at": now(),
            "policy": "Publish this intent, then consume the private ticket once. A lost/consumed ticket or started partial worker must never be replaced."}
        save(location["intent"], intent, exclusive=True)
    print(json.dumps({"intent": d.relative(location["intent"]), "next": "Publish intent before --worker; keep the private launch ticket local."}), flush=True)


def process_snapshot():
    status = Path("/proc/self/status").read_text()
    fields = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in status.splitlines()
              if line.startswith(("VmRSS:", "VmHWM:"))}
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {"rss_bytes": fields.get("VmRSS"), "hwm_bytes": fields.get("VmHWM"),
            "process_hwm_bytes": usage.ru_maxrss * 1024, "user_cpu_seconds": usage.ru_utime,
            "system_cpu_seconds": usage.ru_stime}


def consume_ticket(location, intent):
    require(location["ticket"].is_file() and not location["state"].exists()
            and not any(location[key].exists() for key in ("report", "ledger", "archive")), "Missing/consumed ticket or existing attempt; never replay")
    require(sha(location["ticket"]) == intent["ticket_sha256"], "Private launch ticket differs")
    location["state"].mkdir(parents=True)
    location["ticket"].unlink()


@contextmanager
def retain_attempt(report, location):
    """Preserve even a failed final validation as a non-replayable outcome."""
    try:
        yield
    except BaseException as error:
        report.update(status="failed_or_interrupted", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if location["ledger"].exists():
            ledger = location["ledger"].read_bytes()
            report["ledger_sha256"] = hashlib.sha256(ledger).hexdigest()
            atomic_bytes(location["archive"], gzip.compress(ledger, mtime=0))
        report["finished_at"] = now()
        save(location["report"], report)


def worker(args):
    bound, selection, data_binding = context(args)
    require(0 <= args.worker < 5 and args.source and args.parquet, "Worker needs exact source and pinned Parquet")
    spec, location = bound["workers"][args.worker], paths(bound, args.worker)
    (ROOT / bound["state"]).parent.mkdir(parents=True, exist_ok=True)
    with scoring._lock(ROOT / bound["state"]):
        done = completed_prefix(bound, args.binding, selection, data_binding)
        require(len(done) == args.worker and d.host() == bound["host"], "Wrong next worker or host/boot")
        require(scoring.source(args.source) == bound["sources"][spec["source"]], "Runtime differs from the final frozen source")
        intent = read(location["intent"])
        verify_intent(intent, bound, args.binding, spec)
        d.published(bound, args.published_commit, [*published_prefix_paths(bound, args.binding, done), location["intent"]])
        consume_ticket(location, intent)
        report = {"version": d.VERSION, "status": "running", "worker": spec, "binding_sha256": sha(args.binding),
            "selection_sha256": sha(ROOT / bound["selection"]), "data_binding_sha256": sha(ROOT / bound["data_binding"]),
            "intent_sha256": sha(location["intent"]), "intent_publication_commit": args.published_commit,
            "source": bound["sources"][spec["source"]], "host": bound["host"], "created_at": now(),
            "rows": [], "started": 0, "finished": 0, "error": None, "resources": {}}
        save(location["report"], report)
        with retain_attempt(report, location):
            data = d.load_dataset(args.parquet, bound, selection)
            require(data.fingerprint == data_binding["dataset_sha256"], "Selected data fingerprint changed")
            report["dataset_sha256"] = data.fingerprint
            report["resources"]["before_runtime_import"] = process_snapshot()
            begin = time.perf_counter_ns()
            sys.path.insert(0, str(args.source.resolve()))
            import memory_book
            require(Path(memory_book.__file__).resolve().parent == args.source.resolve() / "memory_book", "Imported another runtime")
            report["resources"]["runtime_import_ms"] = (time.perf_counter_ns() - begin) / 1e6
            report["resources"]["after_runtime_import"] = process_snapshot()
            with location["ledger"].open("x", encoding="utf-8") as ledger, memory_book.MemoryBook(
                    location["state"] / "book.db", max_page_chars=900, cache_size=0) as book:
                def event(value):
                    ledger.write(raw(value).decode())
                    ledger.flush()
                    os.fsync(ledger.fileno())
                report["resources"]["before_ingestion"] = process_snapshot()
                begin = time.perf_counter_ns()
                for session in data.sessions:
                    book.ingest(session)
                report["resources"]["ingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["resources"]["after_ingestion"] = process_snapshot()
                report["source_snapshot_before"] = source_snapshot(book.db)
                report["source_content_before"] = source_content_snapshot(book.db)
                report["index_before"] = indexed_content(book.db)
                originals = original_turn_texts(data)
                pages = {r["id"]: dict(r) for r in book.db.execute("SELECT p.*,s.external_id session_id,s.title session_title FROM pages p JOIN sessions s ON s.id=p.session_pk")}
                page_texts = {key: page["content"] for key, page in pages.items()}
                counters = {name: TokenCounter(name) for name in ENCODINGS}
                for counter in counters.values():
                    require(counter.version == "0.12.0", "Reference tokenizer changed")
                    counter.count("Prewarm both reference tokenizers outside native timing.")
                report["resources"]["after_reference_preparation"] = process_snapshot()
                cases = {q.id: q for q in data.queries}
                phase_start = time.perf_counter_ns()
                for sequence, (config_index, identity) in enumerate(call_schedule(bound, selection["selected_ids"])):
                    config, case = bound["configurations"][config_index], cases[identity]
                    require(book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0] == 0, "Cache not empty before call")
                    event({"event": "started", "seq": sequence, "configuration": config_index, "id": identity, "worker": spec["id"]})
                    report["started"] += 1
                    options = {"project": case.project, "budget_chars": 8000, "budget_tokens": config["budget_tokens"],
                        "tokenizer": config["tokenizer"], "limit": 5, "use_cache": False, "coverage": False, "semantic": False}
                    if spec["source"] == "candidate":
                        options["follow_titles"] = spec["follow_titles"]
                    begin = time.perf_counter_ns()
                    response = book.recall(case.query, **options)
                    elapsed = (time.perf_counter_ns() - begin) / 1e6
                    cache_rows = book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0]
                    score = scoring.scored(case, response, elapsed, spec["follow_titles"], config, counters,
                        originals, pages, cache_rows, page_texts)
                    row = {"configuration": config_index, "score": score}
                    event({"event": "finished", "seq": sequence, "row": row})
                    report["rows"].append(row)
                    report["finished"] += 1
                    verify_score(score, config, data_binding["queries"][identity], spec["follow_titles"])
                    if report["finished"] % 64 == 0:
                        save(location["report"], report)
                report["resources"]["query_phase_including_offline_evaluation_ms"] = (time.perf_counter_ns() - phase_start) / 1e6
                report["resources"]["after_calls"] = process_snapshot()
                report["source_snapshot_after"] = source_snapshot(book.db)
                report["source_content_after"] = source_content_snapshot(book.db)
                report["index_after"] = indexed_content(book.db)
            report["source_after"] = scoring.source(args.source)
            report["resources"]["after_finalization"] = process_snapshot()
            report["storage"] = storage(location["state"])
            require(report["source_after"] == report["source"]
                    and report["index_before"] == report["index_after"]
                    and report["source_snapshot_before"] == report["source_snapshot_after"]
                    and report["source_content_before"] == report["source_content_after"], "Source/runtime/index changed during calls")
            report["status"] = "completed"
            ledger = location["ledger"].read_bytes()
            report["ledger_sha256"] = hashlib.sha256(ledger).hexdigest()
            verify_worker(report, ledger, bound, args.binding, selection, data_binding, spec)
    print(json.dumps({"completed_worker": args.worker, "calls": report["finished"],
                      "next": "Publish report, lossless ledger archive and intent before creating the next worker intent."}), flush=True)


def exact_discordance(gains, losses):
    require(type(gains) is int and type(losses) is int and gains >= 0 and losses >= 0, "Invalid discordance counts")
    count = gains + losses
    denominator = 1 << count
    numerator = min(denominator, 2 * sum(math.comb(count, k) for k in range(min(gains, losses) + 1)))
    return {"gains": gains, "losses": losses, "discordant_pairs": count, "numerator": numerator,
            "denominator": denominator, "two_sided_p": numerator / denominator,
            "p_le_0_05": 20 * numerator <= denominator}


def quality_cell(off_rows, on_rows, config, scope):
    off, on = ({r["id"]: r for r in rows} for rows in (off_rows, on_rows))
    require(len(off) == len(off_rows) == len(on) == len(on_rows) == 512 and set(off) == set(on), "Quality needs the single complete first OFF/ON pair")
    before, after = scoring.metrics(off_rows), scoring.metrics(on_rows)
    changes = [scoring.paired_changes(off[identity], on[identity]) for identity in off]
    gains = [r["id"] for r in changes if r["complete_gain"]]
    losses = [r["id"] for r in changes if r["complete_loss"]]
    introduced = [p for r in changes for p in r["introduced"]]
    displaced = [p for r in changes for p in r["displaced"]]
    rate = lambda pages: sum(bool(p["annotations"]) for p in pages) / len(pages) if pages else None
    intro_rate, displaced_rate = rate(introduced), rate(displaced)
    delta = {name: after[name] - before[name] if before[name] is not None and after[name] is not None else None
             for name in ("complete_evidence_rate", "evidence_recall", "annotated_page_precision", "mrr")}
    gate = scope["quality_gates"]
    primary = config["tokenizer"] == gate["primary_tokenizer"] and config["budget_tokens"] == gate["primary_budget_tokens"]
    paired, failures = exact_discordance(len(gains), len(losses)), []
    if primary:
        for name, threshold in (("complete_evidence_rate", gate["complete_gain_minimum_pp"]),
                ("evidence_recall", gate["annotation_recall_gain_minimum_pp"]),
                ("annotated_page_precision", gate["annotated_page_precision_gain_minimum_pp"])):
            if delta[name] is None or 100 * delta[name] + 1e-9 < threshold:
                failures.append(name + "_primary_gain")
        if len(gains) - len(losses) < gate["net_complete_gains_minimum"]:
            failures.append("net_complete_gains")
        if len(losses) > gate["complete_losses_maximum"]:
            failures.append("complete_losses")
        if not paired["p_le_0_05"]:
            failures.append("exact_paired_discordance")
        if intro_rate is None or intro_rate + 1e-9 < gate["introduced_page_annotation_hit_rate_minimum"]:
            failures.append("introduced_page_hit_rate")
        if displaced_rate is not None and (intro_rate is None or intro_rate + 1e-9 < displaced_rate):
            failures.append("introduced_vs_displaced")
    else:
        for name in ("complete_evidence_rate", "evidence_recall", "annotated_page_precision"):
            if delta[name] is None or 100 * delta[name] < -gate["other_cells_maximum_decline_pp"] - 1e-9:
                failures.append(name + "_regression")
    if delta["mrr"] is None or delta["mrr"] < -gate["mrr_maximum_decline"] - 1e-9:
        failures.append("mrr_regression")
    if config["budget_tokens"] == 512 and (delta["complete_evidence_rate"] is None or delta["complete_evidence_rate"] < -1e-9):
        failures.append("hotpot512_complete_decline")
    provenance = [row["title_reference"] for row in on_rows]
    reasons = sorted({item["reason"] for item in provenance})
    activation = {"queries": len(provenance), "active": sum(item["active"] is True for item in provenance),
        "applied": sum(item["applied"] is True for item in provenance),
        "reasons": {reason: sum(item["reason"] == reason for item in provenance) for reason in reasons},
        "chosen_target_returned": sum(item["target_returned"] for item in changes),
        "initial_pool_membership": {field: {
            "true": sum(item.get(field) is True for item in provenance),
            "false": sum(item.get(field) is False for item in provenance),
            "unexamined": sum(item.get(field) is None for item in provenance)}
            for field in ("target_initial_page_in_pool", "target_initial_session_in_pool")},
        "introduced_existing_session_pages": sum(item["introduced_existing_session_pages"] for item in changes),
        "introduced_new_session_pages": sum(item["introduced_new_session_pages"] for item in changes),
        "limits": "Pool membership describes only the chosen target; introduced session counts compare actual OFF/ON returned pages."}
    return {"configuration": config, "primary": primary, "off": before, "on": after, "deltas": delta,
            "complete_gain_ids": gains, "complete_loss_ids": losses, "paired_discordance": paired,
            "introduced_pages": len(introduced), "introduced_hit_rate": intro_rate,
            "displaced_pages": len(displaced), "displaced_hit_rate": displaced_rate,
            "on_activation": activation, "paired_changes": changes, "failed_gates": failures, "passed": not failures}


def cost_cell(partitions, scope):
    require(set(partitions) == {1, 2, 3, 4} and all(len(v) == 512 for v in partitions.values()), "Each cost cell needs 512 samples from every final worker")
    first_repeat = {str(index): latency_summary(samples) for index, samples in partitions.items()}
    pooled = {"off": latency_summary(partitions[1] + partitions[4]),
              "on": latency_summary(partitions[2] + partitions[3])}
    changes, failures = {}, []
    for metric in ("p50_ms", "p95_ms"):
        before, after = pooled["off"][metric], pooled["on"][metric]
        require(before > 0 and after > 0, "Zero clock percentile cannot support cost acceptance")
        ms, percent = after - before, 100 * (after / before - 1)
        changes[metric] = {"increase_ms": ms, "increase_percent": percent}
        gate = scope["cost_gates"]
        if ms > gate["maximum_increase_ms"] + 1e-9 or percent > gate["maximum_increase_percent"] + 1e-9:
            failures.append(metric + "_cost")
    return {"pooled": pooled, "first_repeat_workers": first_repeat, "changes": changes,
            "passed": not failures, "failed_gates": failures}


def assess(reports, bound, scope):
    require([r["worker"]["index"] for r in reports] == list(range(5)), "All five fixed workers are required")
    cells, failures = [], []
    for config in bound["configurations"]:
        modes = {index: [r["score"] for r in report["rows"] if r["configuration"] == config["index"]]
                 for index, report in enumerate(reports)}
        indexed = {index: {r["id"]: r for r in rows} for index, rows in modes.items()}
        require(all(len(rows) == len(indexed[index]) == 512 for index, rows in modes.items())
                and all(set(values) == set(indexed[0]) for values in indexed.values()), "Incomplete per-worker cell")
        mismatches = [{"id": identity, "workers": [left, right]} for identity in indexed[0]
            for left, right in ((0, 1), (0, 4), (2, 3))
            if indexed[left][identity]["native_payload_sha256"] != indexed[right][identity]["native_payload_sha256"]]
        quality = quality_cell(modes[1], modes[2], config, scope)
        cost = cost_cell({index: [r["wall_ms"] for r in modes[index]] for index in (1, 2, 3, 4)}, scope)
        cell_failures = [*quality["failed_gates"], *cost["failed_gates"], *(["complete_payload_parity_or_repeat"] if mismatches else [])]
        cells.append({"configuration": config, "quality": quality, "cost": cost,
                      "payload_mismatches": mismatches, "failed_gates": cell_failures, "passed": not cell_failures})
        failures.extend({"configuration": config["index"], "gate": failure} for failure in cell_failures)
    return {"version": d.VERSION, "status": "native-measurements-complete", "calls": 15360,
            "native_gate_passed": not failures, "failed_gates": failures, "cells": cells,
            "quality_workers": [1, 2], "cost_workers": [1, 2, 3, 4],
            "limits": "Fresh native evidence/quality/cost only. Source-free digests and online invariant records are retained; actual private response text is not published. External supplied-page comparison, all original default fourteen-cell performance/resource gates, compatibility and release checks remain separate requirements."}


def audit(args):
    bound, selection, data_binding = context(args)
    reports = completed_prefix(bound, args.binding, selection, data_binding)
    require(len(reports) == 5, "Attempt incomplete; preserve it without replay")
    verify_cross_worker_sources(reports)
    summary = assess(reports, bound, d.registered())
    summary.update(source_content_snapshot=reports[0]["source_content_before"],
        full_source_snapshots=[r["source_snapshot_before"] for r in reports],
        binding_sha256=sha(args.binding), selection_sha256=sha(ROOT / bound["selection"]),
        data_binding_sha256=sha(ROOT / bound["data_binding"]),
        worker_files=[{"worker": r["worker"]["index"], "report_sha256": sha(paths(bound, r["worker"]["index"])["report"]),
                       "ledger_sha256": r["ledger_sha256"], "archive_sha256": sha(paths(bound, r["worker"]["index"])["archive"])} for r in reports])
    target = ROOT / bound["output"] / "summary.json.gz"
    if args.write_summary:
        require(not target.exists(), "Never replace a summary; use read-only audit")
        save(target, summary, exclusive=True)
    else:
        require(read(target) == summary, "Published summary differs from original worker rows")
    print(json.dumps({"verified": True, "native_gate_passed": summary["native_gate_passed"], "retrieval_calls_executed": 0}), flush=True)
    return 0 if summary["native_gate_passed"] else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bind", type=Path)
    group.add_argument("--select", action="store_true")
    group.add_argument("--prepare-data", action="store_true")
    group.add_argument("--intent", type=int)
    group.add_argument("--worker", type=int)
    group.add_argument("--audit", action="store_true")
    for name in ("binding", "baseline-src", "candidate-src", "source", "parquet", "selection", "data-binding", "state", "output", "comparators", "additional-exclusions"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--publication-ref")
    parser.add_argument("--published-commit")
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args(argv)
    if args.bind:
        d.bind(args)
    else:
        require(args.binding is not None, "An exact committed prospective binding is required")
        if args.select:
            d.select(args)
        elif args.prepare_data:
            d.prepare_data(args)
        elif args.intent is not None:
            create_intent(args)
        elif args.worker is not None:
            worker(args)
        else:
            return audit(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
