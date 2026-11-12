"""Audit saved round-three quality evidence without invoking retrieval.

The interrupted upload has no manifest. Complete gzip members and matching
row-hashed ledgers can still be identified by their embedded cohort/mode and
the frozen binding. This creates a separate recovery record; it never repairs
the old aggregate, invents process exit codes, or launches a missing worker.
"""
from __future__ import annotations

import argparse
import codecs
from collections import defaultdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts import round3_project_stats as frozen

EVIDENCE_COMMIT = "2bd5f27d1ae478c1735f36b5354fddd81114182b"
PREFIX = "benchmarks/reports/round3-project-stats-20261112-1-"
TRANSFER = "benchmarks/transfers/round3-project-stats-20261112-1/chunks/"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    # Evidence blobs must be fetched explicitly, without an unbounded promisor
    # network request hidden inside an offline audit.
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=45,
                                   env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


def check(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(commit):
    paths = git("ls-tree", "-r", "--name-only", commit, "--",
                "benchmarks/reports", TRANSFER).decode().splitlines()
    return sorted(p for p in paths if (p.startswith(PREFIX) and
                  p.endswith((".worker.json.gz", ".ledger.jsonl"))) or p.startswith(TRANSFER))


def read_controller_prefix(raw):
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    decoded = inflater.decompress(raw)
    check(not inflater.eof, "Expected an incomplete aggregate gzip member")
    text = codecs.getincrementaldecoder("utf-8")().decode(decoded, final=False)
    check(text.startswith("{"), "Expected a canonical JSON object")
    decoder, values, position = json.JSONDecoder(), {}, 1
    while True:
        key, position = decoder.raw_decode(text, position)
        check(isinstance(key, str) and key not in values and text[position] == ":",
              "Invalid or duplicate controller metadata key")
        position += 1
        if key == "workers":
            check(text[position] == "[", "Expected the original worker array")
            return values, decoded
        value, position = decoder.raw_decode(text, position)
        values[key] = value
        check(text[position] == ",", "Truncated controller metadata")
        position += 1


def recover_bytes(commit):
    files, originals, grouped = [], [], defaultdict(list)
    for path in inventory(commit):
        raw = git("show", commit + ":" + path)
        files.append({"path": path, "bytes": len(raw), "sha256": sha(raw),
                      "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()})
        if path.startswith(TRANSFER):
            match = re.fullmatch(r"(\d{2})-(\d{3})\.bin", Path(path).name)
            check(match is not None, "Unexpected transfer path: " + path)
            grouped[match[1]].append((int(match[2]), path, raw))
        else:
            originals.append((path, [path], raw))
    sources = list(originals)
    for group, parts in sorted(grouped.items()):
        parts.sort()
        check([n for n, _, _ in parts] == list(range(len(parts))), "Noncontiguous transfer group " + group)
        sources.append(("transfer-group-" + group, [p for _, p, _ in parts], b"".join(b for _, _, b in parts)))
    workers, ledgers, decoded, controllers = {}, {}, [], []
    for label, paths, raw in sources:
        item = {"source": label, "paths": paths, "bytes": len(raw), "sha256": sha(raw)}
        try:
            content = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
        except (EOFError, OSError) as error:
            item.update(kind="incomplete_or_invalid_gzip", error_type=type(error).__name__)
            try:
                prefix = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, 256)
                key = re.match(rb'\{"([^"\\]+)":', prefix)
                item["first_json_key_in_unverified_prefix"] = key[1].decode() if key else None
            except zlib.error:
                item["first_json_key_in_unverified_prefix"] = None
            if label == "transfer-group-08":
                metadata, prefix = read_controller_prefix(raw)
                controllers.append((metadata, prefix, item))
            decoded.append(item)
            continue
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            events = [json.loads(line) for line in content.splitlines()]
            check(events and all(e.get("status") in ("started", "completed") for e in events),
                  "Unrecognized ledger: " + label)
            check(content == raw, "Compressed ledger requires an explicit format declaration")
            ledgers[sha(raw)] = (events, item)
            item.update(kind="ledger", events=len(events))
        else:
            check(isinstance(value, dict) and all(k in value for k in ("cohort", "mode", "configurations")),
                  "Unrecognized complete JSON artifact: " + label)
            identity = (value["cohort"], value["mode"])
            if identity in workers:
                check(workers[identity][1]["sha256"] == sha(raw), "Conflicting saved worker: " + str(identity))
            workers[identity] = (value, item)
            item.update(kind="worker", cohort=value["cohort"], mode=value["mode"], recorded_status=value["status"],
                        recorded_calls=sum(len(c["rows"]) for c in value["configurations"]))
        decoded.append(item)
    return files, decoded, workers, ledgers, controllers


def audit_worker(worker, ledger, declaration, binding, binding_hash):
    """Verify complete worker content, with no assumption about process exit."""
    cohort, mode = worker["cohort"], worker["mode"]
    expected = next(c for c in declaration["cohorts"] if c["name"] == cohort)
    source = binding["modes"][mode]
    check(worker["status"] == "completed" and worker.get("error") is None, "Worker recording is incomplete")
    check(worker["source"]["source_sha256"] == source["source_sha256"] == worker["source_sha256_after"]
          and worker["source"]["provenance"]["git_commit"] == source["commit"]
          and worker["source"]["provenance"]["commit_identifies_source"], "Source identity mismatch")
    check(worker["dataset"]["sha256"] == expected["sha256"] and worker["dataset"]["queries"] == expected["queries"]
          and len(worker["query_ids"]) == len(set(worker["query_ids"])) == expected["queries"]
          and sorted(worker["query_ids_original_order"]) == worker["query_ids"], "Cohort identity mismatch")
    check(worker["binding_sha256"] == binding_hash and worker["evaluator_hashes"] == binding["evaluator_files_sha256"]
          and worker["evaluator_unchanged"] and worker["originals_unchanged"]
          and worker["indexed_content"] == worker["indexed_content_after"] and worker["cache_rows"] == 0,
          "Binding, evaluator, source, index or cache invariant mismatch")
    check([c["budget_tokens"] for c in worker["configurations"]] == list(frozen.BUDGETS), "Budget matrix mismatch")
    order = list(worker["query_ids_original_order"])
    random.Random(31061).shuffle(order)
    events, evidence = ledger
    row_pairs = [(c["budget_tokens"], r) for c in worker["configurations"] for r in c["rows"]]
    check(len(events) == 2 * len(row_pairs) and [e["sequence"] for e in events] == list(range(len(events))),
          "Ledger sequence or call count mismatch")
    for index, (budget, row) in enumerate(row_pairs):
        start, end = events[2 * index:2 * index + 2]
        check(start["status"] == "started" and end["status"] == "completed"
              and all(e["query_id"] == row["id"] and e["budget_tokens"] == budget for e in (start, end))
              and end["row_sha256"] == frozen.digest(row), "Ledger-to-row digest mismatch")
    previous = worker["scope_initial"]
    check(not previous["initialized"] and previous["builds"] == 0, "Derived state was prewarmed")
    for config in worker["configurations"]:
        check(config["budget_chars"] == 8000 and config["tokenizer"] == "cl100k_base"
              and [r["id"] for r in config["rows"]] == order, "Configuration or query order mismatch")
        measured = frozen.summarize(config["rows"])
        check(all(config[k] == v for k, v in measured.items()), "Recorded aggregate does not match saved rows")
        check(not any(measured["invariants"].values()) and not measured["metrics"]["budget_violations"]
              and not measured["metrics"]["context_size_mismatches"], "A recorded retrieval invariant failed")
        for row in config["rows"]:
            ranks = row["evidence_ranks"]
            found = [r for r in ranks if r is not None]
            check(row["required_evidence"] == len(ranks) and row["matched_evidence"] == len(found)
                  and row["complete"] == (bool(ranks) and len(ranks) == len(found))
                  and row["reciprocal_rank"] == (1 / min(found) if found else 0.0)
                  and all(type(r) is int and 1 <= r <= 5 for r in found), "Evidence accounting mismatch")
            check(math.isfinite(row["elapsed_ms"]) and row["elapsed_ms"] >= 0 and "query" not in row
                  and row["context_tokens"]["cl100k_base"] <= config["budget_tokens"]
                  and row["returned_characters"] <= 8000 and row["result_count"] <= 5,
                  "Timing, source publication or budget mismatch")
            cost = row["scope_cost"]
            applied = mode == frozen.MODES[1] and row["project"] is not None
            check(row["statistics_applied"] is applied and cost["before"] == previous
                  and cost == frozen.scope_event(cost["before"], cost["after"], mode,
                      needed=row["query_has_terms"], applied=applied), "Derived state sequence mismatch")
            after = cost["after"]
            check(after["total_build_ms"] == previous["total_build_ms"] + cost["build_ms"]
                  and all(math.isfinite(after[k]) and after[k] >= 0 for k in ("last_build_ms", "total_build_ms")),
                  "Derived build time mismatch")
            switched = int(bool(cost["builds"]) and previous["initialized"] and previous["project"] != after["project"])
            check(after["switches"] == previous["switches"] + switched, "Derived switch count mismatch")
            temp = after["temporary_storage"]
            check(all(type(temp[k]) is int and temp[k] >= 0 for k in
                      ("page_count", "page_size", "freelist_count", "allocated_bytes", "live_bytes"))
                  and temp["freelist_count"] <= temp["page_count"]
                  and temp["allocated_bytes"] == temp["page_count"] * temp["page_size"]
                  and temp["live_bytes"] == (temp["page_count"] - temp["freelist_count"]) * temp["page_size"]
                  and all(type(row["memory_after"][k]) is int and row["memory_after"][k] >= 0
                          for k in ("rss_bytes", "hwm_bytes")), "Memory or temporary-storage accounting mismatch")
            if applied and row["query_has_terms"]:
                check(after["initialized"] and after["project"] == row["project"]
                      and after["revision"] == row["archive_revision"] and after["policy_version"] == 1,
                      "Derived index identity mismatch")
            previous = after
    check(previous == worker["scope_final"], "Final derived state mismatch")
    return {"cohort": cohort, "mode": mode, "worker_recording": "complete_and_verified",
            "calls": len(row_pairs), "ledger_sha256": evidence["sha256"],
            "original_process_exit_code": worker.get("worker_exit_code"),
            "original_process_exit_code_known": "worker_exit_code" in worker}


def paired_invariants(workers):
    cases, archives, unscoped = {}, {}, {}
    fields = ("id", "project", "category", "answerable", "required_evidence", "diagnostic_groups",
              "query_has_terms", "required_chapters", "query_term_coverage_by_required_text")
    for worker in workers:
        cohort = worker["cohort"]
        archive = {k: worker[k] for k in ("query_ids", "query_ids_original_order", "indexed_content")}
        check(cohort not in archives or archives[cohort] == archive, "Paired archive mismatch")
        archives[cohort] = archive
        for config in worker["configurations"]:
            for row in config["rows"]:
                key = cohort, row["id"]
                identity = {k: row.get(k) for k in fields}
                check(key not in cases or cases[key] == identity, "Paired query/group identity mismatch")
                cases[key] = identity
                if row["project"] is None:
                    pair = cohort, config["budget_tokens"], row["id"]
                    check(pair not in unscoped or unscoped[pair] == row["non_timing_payload_sha256"],
                          "Unscoped payload changed")
                    unscoped[pair] = row["non_timing_payload_sha256"]


def observed_losses(cells):
    """Necessary non-regression conditions also apply to a verified subset."""
    losses = []
    for cell in cells:
        axis = {k: cell[k] for k in ("cohort", "budget_tokens")}
        for metric in ("complete_evidence_rate", "evidence_recall"):
            before, after = (cell[m]["metrics"][metric] for m in ("baseline", "candidate"))
            if before is not None and after < before:
                losses.append({**axis, "group": "all", "metric": metric, "before": before, "after": after})
        if cell["candidate"]["unsupported_nonempty"] > cell["baseline"]["unsupported_nonempty"]:
            losses.append({**axis, "group": "unsupported", "metric": "nonempty_count",
                "before": cell["baseline"]["unsupported_nonempty"], "after": cell["candidate"]["unsupported_nonempty"]})
        if cell["budget_tokens"] == 512:
            for group in frozen.GROUPS:
                values = cell["by_group"].get(group)
                if values is None or values["before"]["queries"] < 10:
                    continue
                for metric in ("complete_evidence_rate", "evidence_recall"):
                    before, after = values["before"][metric], values["after"][metric]
                    if before is not None and after < before:
                        losses.append({**axis, "group": group, "metric": metric, "before": before, "after": after})
    return losses


def recover(commit):
    check(git("rev-parse", commit + "^{commit}").decode().strip() == EVIDENCE_COMMIT,
          "Use the frozen interrupted-upload commit")
    declaration = frozen.plan()
    binding_raw = frozen.BINDING.read_bytes()
    binding = json.loads(binding_raw)
    check(frozen.helper_hashes() == binding["evaluator_files_sha256"], "Frozen evaluators changed")
    check(sha(frozen.PLAN.read_bytes()) == binding["plan_sha256"], "Frozen plan changed")
    files, decoded, artifacts, ledgers, controllers = recover_bytes(commit)
    check(len(controllers) == 1, "Require the saved incomplete aggregate prefix")
    metadata, prefix, partial = controllers[0]
    check(metadata["protocol"] == frozen.PROTOCOL and metadata["plan"] == declaration
          and metadata["binding"] == binding and metadata["binding_sha256"] == sha(binding_raw)
          and metadata["evaluator_hashes"] == binding["evaluator_files_sha256"],
          "Controller metadata does not match the frozen source and evaluator binding")
    attempts = metadata["attempted_workers"]
    check([(a["cohort"], a["mode"]) for a in attempts] == frozen.expected_order()
          and all(a["status"] == "completed" and a["exit_code"] == 0 for a in attempts)
          and metadata["error"] is None and metadata["evaluator_unchanged"],
          "Controller completion metadata is incomplete or invalid")
    attempt_by_identity = {(a["cohort"], a["mode"]): a for a in attempts}
    ordered, audits = [], []
    for identity in frozen.expected_order():
        if identity not in artifacts:
            continue
        worker, source = artifacts[identity]
        check(worker["ledger_sha256"] in ledgers, "Missing matching worker ledger: " + str(identity))
        result = audit_worker(worker, ledgers[worker["ledger_sha256"]], declaration, binding, sha(binding_raw))
        result.update(original_process_exit_code=attempt_by_identity[identity]["exit_code"],
                      original_process_exit_code_known=True,
                      process_status_source="original controller metadata in incomplete gzip prefix")
        audits.append({**result, "record_source": source["source"], "record_sha256": source["sha256"]})
        ordered.append(worker)
    check(len(ordered) == len(artifacts), "Unexpected saved worker identity")
    paired_invariants(ordered)
    cells = frozen.comparisons({"workers": ordered})
    losses = observed_losses(cells)
    complete = len(ordered) == 8
    original_gate = frozen.screen(cells, valid=True) if complete else None
    if complete:
        check(original_gate["losses"] == losses, "Recovery decision differs from the frozen gate")
        check(sum(a["calls"] for a in audits) == 8082, "Full worker count does not cover registered calls")
        adopted = []
        for worker, attempt in zip(ordered, attempts):
            identity = worker["cohort"], worker["mode"]
            stem = "round3-project-stats-20261112-1-" + "-".join(identity)
            adopted.append({**worker,
                "files": {"raw": stem + ".worker.json.gz", "raw_sha256": artifacts[identity][1]["sha256"],
                          "ledger": stem + ".ledger.jsonl"},
                "ledger_file": stem + ".ledger.jsonl", "worker_exit_code": attempt["exit_code"]})
        aggregate = {**metadata, "workers": adopted}
        validation = frozen.validate(aggregate)
        check(validation == metadata["validation"] and validation["passed"], "Original full validation differs")
        check(cells == metadata["comparisons"] and original_gate == metadata["screening"],
              "Original controller metrics or gate differ from recovered rows")
        reconstructed = (frozen.canonical(aggregate) + "\n").encode()
        check(reconstructed.startswith(prefix), "Reconstruction differs from the original decompressed prefix")
        controller_audit = {"passed": True, "original_attempts": attempts,
            "original_finished_at": metadata["finished_at"], "validation": validation,
            "compressed_prefix_sha256": partial["sha256"], "compressed_prefix_bytes": partial["bytes"],
            "decoded_prefix_sha256": sha(prefix), "decoded_prefix_bytes": len(prefix),
            "all_available_decoded_bytes_match": True, "reconstructed_report_sha256": sha(reconstructed)}
    else:
        controller_audit = {"passed": False, "reason": "Some recorded workers are unavailable"}
    decision = "rejected_registered_non_regression_failure" if losses else "not_qualified_by_partial_recovery"
    if complete and original_gate["qualified"]:
        decision = "worker_evidence_passed_requires_controller_reconciliation"
    # The authoritative reconstruction retains every row and per-question
    # gain/loss. Keep this independent audit small enough to checkpoint as one
    # text blob while binding all omitted detail with canonical hashes.
    audit_cells = []
    group_metrics = ("queries", "answerable_queries", "complete_evidence_rate", "evidence_recall", "mrr")
    for cell in cells:
        changes = cell["paired_changes"]
        audit_cells.append({**{k: cell[k] for k in ("cohort", "budget_tokens", "baseline", "candidate")},
            "by_group": {group: {side: {k: metrics[k] for k in group_metrics if k in metrics}
                                  for side, metrics in sides.items()} for group, sides in cell["by_group"].items()},
            "paired_change_counts": {k: len(v) for k, v in changes.items() if isinstance(v, list)},
            "paired_changes_sha256": frozen.digest(changes), "complete_comparison_sha256": frozen.digest(cell)})
    return {"schema_version": 1, "status": "verified_recovery_from_partial_transfer" if complete else "partial_transfer_recovery",
        "evidence_commit": EVIDENCE_COMMIT, "plan_sha256": binding["plan_sha256"], "binding_sha256": sha(binding_raw),
        "candidate": binding["modes"][frozen.MODES[1]], "baseline": binding["modes"][frozen.MODES[0]],
        "evaluator_files_sha256": binding["evaluator_files_sha256"],
        "new_retrieval_calls": 0, "new_model_calls": 0,
        "recovered_workers": len(ordered), "expected_workers": 8,
        "verified_recorded_calls": sum(a["calls"] for a in audits), "expected_calls": 8082,
        "all_worker_recordings_recovered": complete, "original_complete_aggregate_gzip_available": False,
        "controller_aggregate_reconstructed": complete,
        "original_controller_completion_verified": controller_audit["passed"],
        "controller_prefix_audit": controller_audit,
        "scope": "Saved worker bytes, recorded metric/invariant values and their matching start/completion ledgers. No re-execution or source-context rescoring; raw responses are represented by their original hashes.",
        "transfer_boundary": "48 of 78 advertised chunks are present; there is no original transfer manifest. Complete gzip members and exact embedded ledger hashes identify recoverable workers. Group 08 is truncated, but all controller metadata precedes the workers array and survives intact. Original exit codes are read from that prefix. The reconstructed complete JSON is checked against every available decompressed prefix byte; the original complete gzip is unavailable.",
        "files": files, "decoded_sources": decoded, "worker_audits": audits,
        "comparisons": audit_cells, "all_complete_comparisons_sha256": frozen.digest(cells),
        "observed_gate_losses": losses, "frozen_gate_on_recovered_rows": original_gate,
        "decision": decision, "ship_project_statistics": False,
        "interpretation": "A verified loss in any required cohort/budget or primary 512-token group is sufficient to reject this single candidate. Recovered timing is development evidence, not a formal speed claim. No other candidate is tuned or scored by this audit."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-ref", default=EVIDENCE_COMMIT)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/reports/round3-quality-independent-audit.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = recover(args.evidence_ref)
    raw = (json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.check:
        check(args.output.read_bytes() == raw, "Saved recovery record differs from its Git evidence")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(raw)
    print(json.dumps({k: report[k] for k in ("status", "recovered_workers", "verified_recorded_calls",
        "all_worker_recordings_recovered", "original_controller_completion_verified", "new_retrieval_calls", "decision")}))


if __name__ == "__main__":
    main()
