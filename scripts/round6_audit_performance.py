"""Independent stdlib-only audit of saved round-six observations; never retrieves.

Source Git blobs, frozen evaluator/plan bytes, worker attempts, complete-output
identities, every numeric sample and every resource trigger are checked without
importing the benchmark runner or the product runtime.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "round6-default-performance-1"
PLAN_PATH = "benchmarks/experiments/round6-plan.json"
PLAN_COMMIT = "afbb3233e16b80b3c0e5e76ab19466188abf41b4"
BASELINE = {"commit": "796cedfd1f5368144037a1fb72292b8d13884b8c",
    "runtime_sha256": "55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45"}
COHORTS = {"synthetic61": {"queries": 168,
    "sha256": "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26"},
    "public1015": {"queries": 1015,
    "sha256": "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"}}
CONFIGS = [
    {"id": "native-char4000", "surface": "native", "budget_chars": 4000, "budget_tokens": None},
    {"id": "mcp-char4000", "surface": "official-sdk-mcp-stdio", "budget_chars": 4000, "budget_tokens": None},
    {"id": "native-token512", "surface": "native", "budget_chars": 8000, "budget_tokens": 512, "tokenizer": "cl100k_base"},
    {"id": "native-token1024", "surface": "native", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
    {"id": "native-token2048", "surface": "native", "budget_chars": 8000, "budget_tokens": 2048, "tokenizer": "cl100k_base"},
    {"id": "mcp-token1024", "surface": "official-sdk-mcp-stdio", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"}]
ORDERS = [["baseline", "candidate"], ["candidate", "baseline"], ["candidate", "baseline"], ["baseline", "candidate"]]
PACKAGES = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}
THRESHOLDS = {"geometric_mean_p95_improvement": 10,
    "at_least_one_public_native_token_p95_improvement": 15,
    "public_mcp_token1024_p95_improvement": 10,
    "maximum_pooled_p50_p95_regression": 5, "resource_mean_increase_review": 10}
HELPERS = ("scripts/benchmark_default_recall.py", "benchmarks/__init__.py", "benchmarks/native_budget_eval.py",
    "benchmarks/semantic_eval.py", "benchmarks/component_eval.py", "benchmarks/token_compare.py", "benchmarks/run.py",
    "benchmarks/data.py", "benchmarks/public_data.py", "benchmarks/long_data.py", "benchmarks/transfer_data.py",
    "benchmarks/hotpot_data.py", "benchmarks/query_guard.py", "benchmarks/resume.py", "benchmarks/locomo_split.json",
    "scripts/round4_performance.py")
NEW_FILES = ("scripts/round6_performance.py", "scripts/round6_audit_performance.py", "scripts/round6_host.py",
    "scripts/round6_hotpot_compatibility.py", "tests/test_round6_benchmark.py", "tests/test_round6_benchmark_audit.py",
    ".github/workflows/round6-development.yml", ".github/workflows/round6-performance.yml")
INVARIANTS = {"cache_error", "source_span_errors", "source_scope_errors", "page_projection_errors",
    "context_reconstruction_error", "metadata_error", "character_budget_error", "token_budget_error",
    "token_metadata_error", "mcp_projection_error", "result_limit_error", "unexpected_policy"}
SOURCE_COLUMNS = {
    "projects": ["id", "name"],
    "chapters": ["id", "project_id", "task_id", "title", "summary"],
    "sessions": ["id", "external_id", "project_id", "chapter_id", "title", "created_at", "content_hash", "raw_json",
                 "segmentation", "message_count", "turn_count", "content_chars", "settings_json"],
    "turns": ["id", "session_pk", "ordinal", "question", "content", "message_indices"],
    "sections": ["id", "session_pk", "chapter_id", "title", "summary", "ordinal"],
    "pages": ["rid", "id", "section_id", "session_pk", "chapter_id", "project_id", "title", "question", "content", "source_refs", "ordinal"]}
EXCLUDED = {"projects": ["created_at", "updated_at"], "chapters": ["updated_at"], "sessions": ["updated_at"]}
MEMO_FIELDS = ("allocated", "entry_limit", "text_byte_limit", "entries", "text_bytes", "hits", "misses", "evictions",
               "invalidations", "oversized_bypasses", "uncertified_bypasses")
SESSION_FIELDS = {"mcp_startup_to_initialize_ms", "mcp_tool_schema_sha256", "mcp_instructions_sha256",
                  "mcp_initialization_tokens", "mcp_server_memory_after_calls", "storage_after_mcp_live"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def source_hash(commit):
    prefix = "src/memory_book/"
    names = sorted(n for n in git("ls-tree", "-r", "--name-only", commit, prefix).decode().splitlines() if n.endswith(".py"))
    require(bool(names), "No source Python files in bound Git tree")
    result = hashlib.sha256()
    for name in names:
        result.update(name.removeprefix(prefix).encode() + b"\0")
        result.update(git("show", commit + ":" + name) + b"\0")
    return result.hexdigest()


def quantile(values, proportion):
    ordered = sorted(values)
    require(bool(ordered), "Empty latency population")
    position = (len(ordered) - 1) * proportion
    left, right = math.floor(position), math.ceil(position)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def mean(values):
    return math.fsum(values) / len(values)


def latency(values):
    return {"samples": len(values), "p50_ms": quantile(values, .5), "p95_ms": quantile(values, .95), "mean_ms": mean(values)}


def numeric(values):
    return {"samples": len(values), "mean": mean(values), "p50": quantile(values, .5),
            "p95": quantile(values, .95), "min": min(values), "max": max(values)}


def close(actual, expected, path="value"):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), path + ": dictionary fields differ")
        for key in expected:
            close(actual[key], expected[key], path + "." + key)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), path + ": list lengths differ")
        for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
            close(a, e, path + f"[{index}]")
    elif isinstance(expected, float):
        require(type(actual) in (int, float) and math.isfinite(actual)
                and math.isclose(actual, expected, abs_tol=1e-9, rel_tol=1e-12), path + ": numeric value differs")
    else:
        require(type(actual) is type(expected) and actual == expected, path + ": exact value differs")


def nested(value, path):
    for key in path.split("."):
        value = value[key]
    return value


def valid_number(value, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def stable(row):
    return {key: value for key, value in row.items() if key not in ("wall_ms", "engine_source_sha256")}


def matrix(stage):
    require(stage in ("formal", "development-native", "development-mcp"), "Unknown stage")
    if stage == "formal":
        return list(COHORTS), CONFIGS, ORDERS, 56784
    if stage == "development-native":
        return list(COHORTS), [c for c in CONFIGS if c["surface"] == "native"], ORDERS[:2], 18928
    return ["public1015"], [CONFIGS[-1]], ORDERS[:2], 4060


def resources_for(configs):
    fields = ["runtime_import_ms", "native_open_ms", "fresh_ingestion_ms", "unchanged_reingestion_ms",
        "native_memory_after_ingestion.rss_bytes", "native_memory_after_ingestion.hwm_bytes",
        "native_memory_after_calls.rss_bytes", "native_memory_after_calls.hwm_bytes"]
    stores = ["storage_after_ingestion_live", "storage_after_checkpoint"]
    for config in configs:
        if config["surface"] == "official-sdk-mcp-stdio":
            prefix = "mcp_sessions." + config["id"] + "."
            fields.extend(prefix + name for name in ("mcp_startup_to_initialize_ms", "mcp_server_memory_after_calls.rss_bytes", "mcp_server_memory_after_calls.hwm_bytes"))
            stores.append(prefix + "storage_after_mcp_live")
    for prefix in stores:
        fields += [prefix + ".logical_db_bytes", *(prefix + ".files_bytes." + name for name in ("db", "wal", "shm"))]
    return fields


def verify_memo(worker, configs):
    record = worker["native_token_count_memo"]
    require(record["entry_limit"] == 2048 and record["text_byte_limit"] == 2097152, "Memo observation limit changed")
    native = [c for c in configs if c["surface"] == "native"]
    require([r["id"] for r in record["configurations"]] == [c["id"] for c in native], "Memo observation axis differs")
    previous = None
    for spec, item in zip(native, record["configurations"], strict=True):
        config = next(c for c in worker["configurations"] if c["id"] == spec["id"])
        require(item["first_query_id"] == config["rows"][0]["query_id"], "Memo first query mismatch")
        snapshots = [item[k] for k in ("before", "after_first_call", "after")]
        for snapshot in snapshots:
            require(set(snapshot) == {"available", *MEMO_FIELDS} and snapshot["available"] is True, "Memo diagnostic fields differ")
            require(all(type(snapshot[k]) is int and snapshot[k] >= 0 for k in MEMO_FIELDS), "Invalid memo counter")
            require(snapshot["allocated"] in (0, 1) and snapshot["entry_limit"] == 2048 and snapshot["text_byte_limit"] == 2097152
                    and snapshot["entries"] <= 2048 and snapshot["text_bytes"] <= 2097152, "Memo limit exceeded")
            require(snapshot["allocated"] == 1 or all(snapshot[k] == 0 for k in MEMO_FIELDS if k not in ("entry_limit", "text_byte_limit")), "Unallocated memo not empty")
        require(snapshots[0] == previous if previous is not None else snapshots[0]["allocated"] == 0, "Memo artificially warmed/reset")
        if spec["budget_tokens"] is None:
            require(snapshots[0] == snapshots[1] == snapshots[2], "Character calls warmed memo")
        for before, after in zip(snapshots, snapshots[1:]):
            require(after["allocated"] >= before["allocated"] and all(after[k] >= before[k] for k in MEMO_FIELDS[5:]), "Memo counters decreased")
        previous = snapshots[-1]


def verify_row(row, spec, source):
    require(valid_number(row["wall_ms"], True) and row["engine_source_sha256"] == source["runtime_sha256"], "Invalid call timing/source")
    require(set(row["invariants"]) == INVARIANTS and not any(row["invariants"].values()), "Response/cache/provenance invariant failed")
    mcp = spec["surface"] == "official-sdk-mcp-stdio"
    require(row["cache_rows_before"] == 0 and row["cache_rows_after"] == (1 if mcp else 0), "Wrong cache boundary")
    require(type(row["context_chars"]) is int and 0 <= row["context_chars"] <= spec["budget_chars"]
            and type(row["result_count"]) is int and 0 <= row["result_count"] <= 5, "Output exceeds bounds")
    for name in ("payload_sha256", "native_payload_sha256", "context_sha256"):
        require(valid_hash(row[name]), "Missing full payload/provenance hash")
    require(valid_hash(row["envelope_sha256"]) if mcp else row["envelope_sha256"] is None, "Wrong envelope boundary")
    require(type(row["response_utf8_bytes"]) is int and row["response_utf8_bytes"] >= 0, "Invalid output bytes")
    require((type(row["envelope_utf8_bytes"]) is int and row["envelope_utf8_bytes"] >= 0) if mcp else row["envelope_utf8_bytes"] is None, "Wrong envelope bytes")
    require(set(row["tokens"]) == {"cl100k_base", "o200k_base"}, "Tokenizer axis differs")
    for costs in row["tokens"].values():
        require(set(costs) == {"context", "response_text", "response_envelope_json"}, "Token surface axis differs")
        require(all(type(costs[k]) is int and costs[k] >= 0 for k in ("context", "response_text")), "Invalid token count")
        require((type(costs["response_envelope_json"]) is int and costs["response_envelope_json"] >= 0)
                if mcp else costs["response_envelope_json"] is None, "Token envelope boundary differs")
    if spec["budget_tokens"] is not None:
        count = row["tokens"]["cl100k_base"]["context"]
        metadata = {"budget_tokens": spec["budget_tokens"], "tokenizer": spec["tokenizer"], "tokenizer_version": "0.12.0", "context_tokens": count}
        require(count <= spec["budget_tokens"] and row["token_metadata"] == {"native": metadata, "response": metadata}, "Budget/count metadata differs")
    else:
        require(row["token_metadata"] is None, "Unexpected token-budget metadata")


def verify_ledger(raw, expected_rows):
    events = [json.loads(line) for line in raw.splitlines()]
    require(len(events) == 2 * len(expected_rows), "Missing, duplicate or unfinished attempt")
    for sequence, (config_id, row) in enumerate(expected_rows):
        start, finish = events[sequence * 2:sequence * 2 + 2]
        require(start["event"] == "started" and finish["event"] == "finished" and start["seq"] == finish["seq"] == sequence
                and start["config"] == finish["config"] == config_id and start["query_id"] == row["query_id"]
                and finish["row"] == row, "Original ledger differs from saved observation")
    return len(events)


def verify_archive(worker):
    require(valid_hash(worker["source_snapshot_before"]) and worker["source_snapshot_before"] == worker["source_snapshot_after"], "Original archive mutated")
    require(worker["source_semantics_before"] == worker["source_semantics_after"], "Original source semantics mutated")
    require(set(worker["source_semantics_before"]) == set(SOURCE_COLUMNS), "Incomplete source tables")
    for table, item in worker["source_semantics_before"].items():
        require(item["columns"] == SOURCE_COLUMNS[table] and item["excluded_host_columns"] == EXCLUDED.get(table, [])
                and type(item["rows"]) is int and item["rows"] >= 0 and valid_hash(item["sha256"]), "Undeclared source projection omission")
    require(worker["indexed_content"] == worker["indexed_content_after_calls"] and set(worker["indexed_content"]) ==
            {"pages", "sections", "turns", "chapters", "sessions", "pages_fts", "pages_stem_fts"}, "Indexed source projection differs")
    for item in worker["indexed_content"].values():
        require(type(item["rows"]) is int and item["rows"] >= 0 and valid_hash(item["sha256"]), "Invalid indexed source hash")
    require(worker["all_replayed_sessions_skipped"] is True and worker["native_recall_cache_rows"] == 0, "Ingestion/replay/cache policy differs")
    require(valid_hash(worker["fresh_ingestion_results_sha256"]) and valid_hash(worker["unchanged_reingestion_results_sha256"]), "Missing ingestion result identity")


def recompute_comparisons(workers, cohorts, configs, rounds):
    result = []
    for cohort in cohorts:
        for spec in configs:
            engines = {}
            for label in ("baseline", "candidate"):
                groups = [(w["round"], c["rows"]) for w in workers if w["cohort"] == cohort and w["label"] == label
                          for c in w["configurations"] if c["id"] == spec["id"]]
                rows = [r for _, group in groups for r in group]
                engines[label] = {"latency": latency([r["wall_ms"] for r in rows]),
                    "first_round_latency": latency([r["wall_ms"] for rep, group in groups if rep == 0 for r in group]),
                    "repeat_rounds_latency": latency([r["wall_ms"] for rep, group in groups if rep != 0 for r in group]),
                    "response_utf8_bytes": numeric([r["response_utf8_bytes"] for r in rows]),
                    "context_chars": numeric([r["context_chars"] for r in rows]),
                    "tokens": {name: {field: numeric([r["tokens"][name][field] for r in rows]) if rows[0]["tokens"][name][field] is not None else None
                        for field in ("context", "response_text", "response_envelope_json")} for name in ("cl100k_base", "o200k_base")}}
            by_round = [{"round": rep, **{w["label"]: latency([r["wall_ms"] for r in c["rows"]])
                for w in workers if w["cohort"] == cohort and w["round"] == rep
                for c in w["configurations"] if c["id"] == spec["id"]}} for rep in range(rounds)]
            changes = {metric: 100 * (engines["candidate"]["latency"][metric] / engines["baseline"]["latency"][metric] - 1)
                       for metric in ("p50_ms", "p95_ms", "mean_ms")}
            result.append({"cohort": cohort, **spec, **engines, "candidate_change_percent": changes, "rounds": by_round})
    return result


def recompute_acceptance(stage, workers, cohorts, configs, compared):
    improvement = 100 * (1 - math.exp(mean([math.log(c["candidate"]["latency"]["p95_ms"] / c["baseline"]["latency"]["p95_ms"]) for c in compared])))
    native = [-c["candidate_change_percent"]["p95_ms"] for c in compared
        if c["cohort"] == "public1015" and c["surface"] == "native" and c["budget_tokens"] is not None]
    mcp = [-c["candidate_change_percent"]["p95_ms"] for c in compared if c["cohort"] == "public1015" and c["id"] == "mcp-token1024"]
    regressions = [{"cohort": c["cohort"], "config": c["id"], "metric": key, "change_percent": c["candidate_change_percent"][key]}
        for c in compared for key in ("p50_ms", "p95_ms") if c["candidate_change_percent"][key] > 5 + 1e-9]
    resources, review = [], []
    for cohort in cohorts:
        for field in resources_for(configs):
            values = {label: [nested(w, field) for w in workers if w["cohort"] == cohort and w["label"] == label] for label in ("baseline", "candidate")}
            old, new = (mean(values[label]) for label in ("baseline", "candidate"))
            change = 100 * (new / old - 1) if old else (0.0 if new == 0 else None)
            row = {"cohort": cohort, "metric": field, "baseline": numeric(values["baseline"]), "candidate": numeric(values["candidate"]), "mean_change_percent": change}
            resources.append(row)
            if change is None or change > 10 + 1e-9:
                review.append(row)
    formal = stage == "formal"
    passed = formal and improvement >= 10 - 1e-9 and max(native) >= 15 - 1e-9 and mcp[0] >= 10 - 1e-9 and not regressions
    return {"accepted": passed and not review, "numeric_gate_passed": passed if formal else None,
        "formal_acceptance_evaluated": formal, "geometric_mean_p95_improvement_percent": improvement,
        "best_public_native_token_p95_improvement_percent": max(native) if native else None,
        "public_mcp_token1024_p95_improvement_percent": mcp[0] if mcp else None, "thresholds_percent": THRESHOLDS,
        "regressions_above_five_percent": regressions, "resource_comparisons": resources, "resource_review": review,
        "resource_rule": "Any increase above 10% requires explicit cause assessment and independent review; no automatic override.",
        "scope": "Formal preregistered gates" if formal else "Diagnostic observations only; no release acceptance or speed gate."}


def audit(report_path, state, result_commit=None):
    checked_files = {}
    def read(path):
        path = Path(path)
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT), "Missing/unsafe audit artifact")
        relative = path.resolve().relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        if result_commit:
            require(raw == git("show", result_commit + ":" + relative), "Artifact differs from original result commit: " + relative)
        checked_files[relative] = sha(raw)
        return raw
    raw = read(report_path)
    report = json.loads(gzip.decompress(raw))
    run, plan, workers = report["run"], report["plan"], report["workers"]
    binding, stage = run["binding"], run["stage"]
    cohorts, configs, orders, calls = matrix(stage)
    require(report["evaluator"] == run["evaluator"] == binding["evaluator"] == VERSION,
            "Evaluator identity changed")
    require(report["status"] == "measurements_completed" and report["error"] is None and report["evaluator_unchanged"] is True,
            "Incomplete, interrupted or changed evaluator")
    plan_raw = read(ROOT / PLAN_PATH)
    require(plan_raw == git("show", PLAN_COMMIT + ":" + PLAN_PATH) and json.loads(plan_raw) == plan
            and run["plan_sha256"] == binding["plan_sha256"] == sha(plan_raw) and binding["plan_commit"] == PLAN_COMMIT,
            "Preregistered plan identity changed")
    require(plan["thresholds_percent"] == THRESHOLDS and {k: plan["baseline"][k] for k in BASELINE} == BASELINE,
            "Acceptance thresholds/baseline differ")
    formal = plan["performance_candidate"]["formal"]
    require(formal["cohorts"] == list(COHORTS) and formal["configs"] == CONFIGS and formal["rounds"] == 4
            and formal["engine_order"] == ORDERS and formal["calls"] == 56784, "Formal registered axes differ")
    require({c["name"]: {k: c[k] for k in ("queries", "sha256")} for c in plan["cohorts"]} == COHORTS, "Cohort registration differs")
    expected_spec = {**formal, "cohorts": cohorts, "configs": configs, "rounds": len(orders), "engine_order": orders, "calls": calls}
    require(run["measurement"] == binding["measurement"] == expected_spec and binding["stage"] == stage, "Stage matrix changed")
    require(binding["schema_version"] == 1 and binding["status"] == "frozen-before-measurement", "Unfrozen binding")
    binding_raw = read(ROOT / run["binding_path"])
    require(json.loads(binding_raw) == binding and sha(binding_raw) == run["binding_sha256"], "Original binding bytes differ")
    sources = binding["sources"]
    require(set(sources) == {"baseline", "candidate"} and sources["baseline"] == BASELINE
            and sources["candidate"]["runtime_sha256"] != BASELINE["runtime_sha256"], "Bound source pair differs")
    for source in sources.values():
        require(re.fullmatch(r"[0-9a-f]{40}", source["commit"]) is not None
                and source_hash(source["commit"]) == source["runtime_sha256"], "Measured source Git bytes differ")
    require(binding["packages"] == run["host"]["packages"] == PACKAGES, "Package versions differ")
    require(set(binding["evaluator_files"]) == set(HELPERS) | set(NEW_FILES)
            and binding["evaluator_files"] == run["evaluator_files"], "Frozen evaluator closure differs")
    for path, expected in binding["evaluator_files"].items():
        require(sha(read(ROOT / path)) == expected and sha(git("show", binding["evaluator_commit"] + ":" + path)) == expected,
                "Evaluator Git/local bytes differ: " + path)
        if path in HELPERS:
            require(sha(git("show", BASELINE["commit"] + ":" + path)) == expected, "Historical helper changed: " + path)
    require(set(binding["evidence"]) == ({"development-native", "development-mcp", "compatibility"} if stage == "formal" else set()), "Formal prerequisites missing")
    for evidence_stage, group in binding["evidence"].items():
        values = {}
        for kind, record in group.items():
            content = read(ROOT / record["path"])
            require(sha(content) == record["sha256"] and sha(git("show", binding["evaluator_commit"] + ":" + record["path"])) == record["sha256"], "Prerequisite evidence bytes changed")
            if kind != "ledger":
                values[kind] = json.loads(gzip.decompress(content) if record["path"].endswith(".gz") else content)
        prerequisite = values["report"]
        if evidence_stage != "compatibility":
            independent = values["audit"]
            require(prerequisite["status"] == "measurements_completed" and prerequisite["validation"]["passed"]
                    and prerequisite["run"]["stage"] == evidence_stage and prerequisite["run"]["binding"]["sources"] == sources
                    and independent["passed"] is True and independent["audit"] == "round6-independent-saved-observations-1"
                    and independent["sources"] == sources and independent["no_new_measurements"] is True
                    and independent["timed_calls"] == matrix(evidence_stage)[3]
                    and independent["complete_output_pairs"] == matrix(evidence_stage)[3] // 2
                    and independent["ledger_events"] == 2 * matrix(evidence_stage)[3]
                    and prerequisite["validation"]["timed_calls"] == matrix(evidence_stage)[3]
                    and independent["report_sha256"] == group["report"]["sha256"] and independent["stage"] == evidence_stage,
                    "Diagnostic prerequisite belongs to another source/report or failed")
        else:
            require(prerequisite["status"] == "passed" and prerequisite["expected_calls"] == 2304 and len(prerequisite["rows"]) == 2304
                    and {k: prerequisite["candidate"][k] for k in sources["candidate"]} == sources["candidate"]
                    and prerequisite["runtime_sha256_after"] == sources["candidate"]["runtime_sha256"]
                    and all(r["status"] == "match" and r["actual_payload_sha256"] == r["expected_payload_sha256"] for r in prerequisite["rows"]),
                    "Historical compatibility prerequisite differs")
            ledger = gzip.decompress(read(ROOT / group["ledger"]["path"]))
            require(sha(ledger) == prerequisite["attempt_ledger_sha256"] and len(ledger.splitlines()) == 4608,
                    "Compatibility attempt evidence differs")
    host = run["host"]
    require(valid_hash(host["boot_sha256"]) and valid_hash(host["machine_sha256"]) and host["github_run_id"].isdigit()
            and host["github_run_attempt"] == "1", "Hosted machine/run identity absent")
    suffix = ("performance" if stage == "formal" else stage) + "-" + host["github_run_id"] + "-1"
    pair_key = digest({"stage": stage, "sources": {k: v["runtime_sha256"] for k, v in sources.items()}})
    workflow_commit = run["publication"]["workflow_commit"]
    require(isinstance(workflow_commit, str) and re.fullmatch(r"[0-9a-f]{40}", workflow_commit) is not None
            and git("show", workflow_commit + ":" + run["binding_path"]) == binding_raw, "Trigger commit does not identify the exact original binding")
    expected_publication = {"run_id": host["github_run_id"], "run_attempt": "1", "workflow_commit": workflow_commit, "branch": "validation/v034-round6-" + suffix,
        "claim_branch": "validation/v034-round6-claim-" + pair_key, "source_pair_stage_sha256": pair_key}
    require(run["publication"] == expected_publication, "Exclusive source-pair/stage claim differs")
    require(json.loads(read(state / "run.json")) == run, "Saved run identity differs")
    claim = json.loads(read(state / "execution.json"))
    require(claim["evaluator"] == VERSION and claim["binding_sha256"] == run["binding_sha256"]
            and claim["run_identity_sha256"] == digest(run) and claim["host"] == host and claim["output"] == run["output"], "Execution claim differs")
    preflight = json.loads(read(state / "resource-preflight.json"))
    require(preflight["product_calls"] == preflight["sdk_sessions"] == 0 and preflight["observation"]["available"] is True
            and valid_number(preflight["observation"]["rss_bytes"], True) and valid_number(preflight["observation"]["hwm_bytes"], True), "Missing zero-call resource preflight")
    expected_schedule = [{"key": f"r{rep}-{cohort}-{label}", "round": rep, "cohort": cohort, "label": label}
        for rep, labels in enumerate(orders) for cohort in cohorts for label in labels]
    require(run["schedule"] == expected_schedule and [w["key"] for w in workers] == [w["key"] for w in expected_schedule], "Missing/duplicate/reordered worker")
    require(set(run["cohorts"]) == set(cohorts), "Cohort axis changed")
    locomo = json.loads(read(ROOT / "benchmarks/locomo_split.json"))
    require(run["locomo_file_sha256"] == locomo["sha256"], "Public input bytes changed")
    for name, cohort in run["cohorts"].items():
        require({k: cohort[k] for k in ("queries", "sha256")} == COHORTS[name]
                and len(cohort["query_ids_original_order"]) == len(set(cohort["query_ids_original_order"])) == COHORTS[name]["queries"]
                and sorted(cohort["query_ids_original_order"]) == cohort["query_ids"], "Query identities/count differs")
    total, events, provenance_pairs, canonical_rows, semantic = 0, 0, 0, {}, {}
    for worker, item in zip(workers, expected_schedule, strict=True):
        require(all(worker[k] == v for k, v in item.items()) and worker["run_identity_sha256"] == digest(run)
                and worker["source"] == worker["source_after"] == sources[item["label"]]
                and worker["status"] == "completed" and worker["error"] is None, "Worker identity/completion differs")
        require(worker["dataset_sha256"] == COHORTS[item["cohort"]]["sha256"], "Worker dataset differs")
        prefix = state / "workers" / item["key"]
        require(json.loads(gzip.decompress(read(Path(str(prefix) + ".json.gz")))) == worker, "Worker original bytes differ")
        require(json.loads(read(Path(str(prefix) + ".started.json"))) == {"worker": item, "run_identity_sha256": digest(run)}, "Worker start intent differs")
        verify_archive(worker)
        verify_memo(worker, configs)
        for field in ("indexed_content", "source_semantics_before", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256"):
            key = (item["cohort"], field)
            require(key not in semantic or semantic[key] == worker[field], "Cross-source or cross-round source semantics differ")
            semantic.setdefault(key, worker[field])
        require(len(worker["configurations"]) == len(configs), "Worker configuration count differs")
        attempted = []
        for index, (config, spec) in enumerate(zip(worker["configurations"], configs, strict=True)):
            require({k: config[k] for k in spec} == spec, "Configuration altered")
            ids = list(run["cohorts"][item["cohort"]]["query_ids_original_order"])
            random.Random(41061 + 1009 * item["round"] + index).shuffle(ids)
            require([r["query_id"] for r in config["rows"]] == ids, "Missing/extra/reordered query")
            close(config["latency"], latency([r["wall_ms"] for r in config["rows"]]), "worker latency")
            for row in config["rows"]:
                verify_row(row, spec, sources[item["label"]])
                key = (item["cohort"], spec["id"], row["query_id"])
                require(key not in canonical_rows or canonical_rows[key] == stable(row), "Full stable output differs across source/round")
                canonical_rows.setdefault(key, stable(row))
                attempted.append((spec["id"], row))
        raw_ledger = gzip.decompress(read(Path(str(prefix) + ".attempts.jsonl.gz")))
        require(sha(raw_ledger) == worker["ledger_sha256"], "Ledger hash differs")
        events += verify_ledger(raw_ledger, attempted)
        total += len(attempted)
        for suffix_id in ("char4000", "token1024"):
            pair = {c["id"].split("-", 1)[0]: c for c in worker["configurations"] if c["id"] in ("native-" + suffix_id, "mcp-" + suffix_id)}
            if len(pair) == 2:
                native = {r["query_id"]: r["native_payload_sha256"] for r in pair["native"]["rows"]}
                require(all(native[r["query_id"]] == r["native_payload_sha256"] for r in pair["mcp"]["rows"]), "Actual MCP provenance differs from native")
                provenance_pairs += len(native)
        expected_sessions = {c["id"] for c in configs if c["surface"] == "official-sdk-mcp-stdio"}
        require(set(worker["mcp_sessions"]) == expected_sessions, "Missing/extra actual MCP session")
        for config_id, session in worker["mcp_sessions"].items():
            require(set(session) == SESSION_FIELDS and session["mcp_server_memory_after_calls"]["available"] is True, "Actual MCP startup/RSS evidence missing")
            for field in ("mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
                key = (item["cohort"], "mcp", field)
                require(key not in semantic or semantic[key] == session[field], "Actual MCP schema/instructions boundary differs")
                semantic.setdefault(key, session[field])
            if config_id == "mcp-char4000":
                require(all(worker[field] == session[field] for field in SESSION_FIELDS), "Legacy session fields changed")
        for field in resources_for(configs):
            require(valid_number(nested(worker, field)), "Missing/invalid resource sample: " + field)
    require(total == calls and events == 2 * calls, "Call/event matrix differs")
    expected_validation = {"passed": True, "issues": [], "workers": len(workers), "expected_workers": len(workers), "timed_calls": calls, "expected_calls": calls}
    require(report["validation"] == expected_validation, "Original validation verdict differs")
    compared = recompute_comparisons(workers, cohorts, configs, len(orders))
    close(report["comparisons"], compared, "pooled/per-round comparison")
    accepted = recompute_acceptance(stage, workers, cohorts, configs, compared)
    close(report["acceptance"], accepted, "raw acceptance")
    summary_raw = read(report_path.with_name("report.summary.json"))
    summary = json.loads(summary_raw)
    require(summary["compressed_report_sha256"] == sha(raw) and summary["full_report_sha256"] == sha(gzip.decompress(raw))
            and summary["validation"] == report["validation"] and summary["acceptance"] == report["acceptance"]
            and summary["comparisons"] == report["comparisons"], "Compact summary differs from raw evidence")
    adverse, per_round = [], []
    for cell in compared:
        for metric, change in cell["candidate_change_percent"].items():
            if change > 0:
                adverse.append({"cohort": cell["cohort"], "config": cell["id"], "metric": metric, "change_percent": change})
        for round_ in cell["rounds"]:
            for metric in ("p50_ms", "p95_ms", "mean_ms"):
                change = 100 * (round_["candidate"][metric] / round_["baseline"][metric] - 1)
                if change > 0:
                    per_round.append({"cohort": cell["cohort"], "config": cell["id"], "round": round_["round"], "metric": metric, "change_percent": change})
    return {"schema_version": 1, "audit": "round6-independent-saved-observations-1", "passed": True,
        "stage": stage, "original_result_commit": result_commit, "report_sha256": sha(raw), "summary_sha256": sha(summary_raw),
        "sources": sources, "binding_sha256": run["binding_sha256"], "no_new_measurements": True,
        "workers": len(workers), "timed_calls": total, "complete_output_pairs": total // 2, "ledger_events": events,
        "unique_query_configurations": len(canonical_rows), "native_actual_mcp_provenance_pairs": provenance_pairs,
        "original_automatic_accepted": report["acceptance"]["accepted"], "numeric_gate_passed": accepted["numeric_gate_passed"],
        "acceptance_recomputed": accepted, "all_pooled_adverse_changes": adverse, "all_per_round_adverse_changes": per_round,
        "checked_file_sha256": checked_files,
        "limits": "One-host balanced repeated observations; no significance/cold-OS claim. Stored payload hashes certify exact outputs only within the frozen evaluator/provenance trust boundary; no new retrieval was run. Resource review is separate from this numerical audit."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--result-commit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Preserve any prior independent audit receipt")
    try:
        result = audit(args.report, args.state_dir or args.report.parent, args.result_commit)
    except Exception as error:
        result = {"schema_version": 1, "audit": "round6-independent-saved-observations-1", "passed": False,
            "no_new_measurements": True, "original_result_commit": args.result_commit,
            "report_sha256": sha(args.report.read_bytes()) if args.report.is_file() else None,
            "error_type": type(error).__name__, "error": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode() + b"\n")
    print(json.dumps({k: result[k] for k in ("passed", "stage", "timed_calls", "ledger_events", "numeric_gate_passed", "error") if k in result}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
