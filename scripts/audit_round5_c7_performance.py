"""Independent read-only arithmetic and complete-output audit for round-five C7.

Only Python's standard library is imported. No runtime, evaluator helper,
retrieval, tokenizer, model, test or timing workload is executed. Source Git
objects and the original saved reports/ledgers are read without modification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Intentionally blocked: C7 transport policy, preregistration and final source
# have not been frozen. Preserve every previous complete rejection; do not infer
# C7 identities or approval from a development or historical candidate.
C7_PROVENANCE_BOUND = False
C7_REGISTRATION_PROTOCOL = None
C7_REGISTRATION_STATUS = None
C7_POLICY_KEY = None
C7_POLICY = None
C7_EVALUATOR_FILE_COUNT = 60
KNOWN_C5_REJECTION = {'source': {'commit': '8dc6604fa32df18d53286110b215fc6657243656', 'runtime_sha256': '6af876ef5ddc851f4fff56ba3dc4f20e76b2cfc9f5e31d0cc8d1a0ec20e954be'}, 'binding_path': 'benchmarks/experiments/round5-c5-performance-binding.json', 'binding_sha256': 'bd395da21848cc01656ab45bc211a388b43b4ae63edb8690b2eabe2958d3781a', 'summary_path': 'benchmarks/reports/round5-c5-performance-43552372788-1/report.summary.json', 'summary_sha256': '930a28c40913b2eea3e38b7ce5bc04e673e288396fccb67bf16e59d42e996f25', 'result_commit': '3982ceab2bdce0e9a189135ce261445a3a38d779', 'formal_run': '43552372788-1', 'accepted': False, 'numeric_gate_passed': False}
KNOWN_C6_REJECTION = {'source': {'commit': '1bd97221e31e8e975498ece00f4bbfb3e0426aac', 'runtime_sha256': 'cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78'}, 'binding_path': 'benchmarks/experiments/round5-c6-performance-binding.json', 'binding_sha256': '2b57caea5b3d7f12b38aba9472d798e846a5231b936551784f0963259e2a715a', 'summary_path': 'benchmarks/reports/round5-c6-performance-43557136276-1/report.summary.json', 'summary_sha256': 'f05d011e3477eee69953ab3a5097e3d69f5657c12c6692d4d96af4f87cb6ad9e', 'result_commit': 'c6b384778e12ce9c72771911af37bbb2c5d3474f', 'formal_run': '43557136276-1', 'accepted': False, 'numeric_gate_passed': False}

SOURCES = {
    "baseline": {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
                 "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"},
    "candidate": {"commit": None, "runtime_sha256": None},
}
CONTINUATION_PATH = "benchmarks/experiments/round5-c7-addendum.json"
CONTINUATION_COMMIT = None
CONTINUATION_SHA256 = None
C3_SOURCE = {"commit": "1c9a6d3f611608e8dbce8e729fdd3099513d80e6",
    "runtime_sha256": "7a927601b5ce710059d5a2640b3642c58a2bd4985d9ccdc48f69159938ee3623"}
C3_BINDING_PATH = "benchmarks/experiments/round5-performance-binding.json"
C3_BINDING_SHA256 = "790ca15f3fbe2a5ba19fe08f83ab663bdb313a8569bfb1ee7677456ca4817c40"
C3_SUMMARY_PATH = "benchmarks/reports/round5-performance-43547085915-1/report.summary.json"
C3_SUMMARY_SHA256 = "5103a9d5bf26451e6eed2425c75c21663eedc51cc7d8462446373d9fcdd2b321"
C3_RESULT_COMMIT = "e0c30deb7cdae18bb19c83534646630dfb3f673b"
C4_SOURCE = {"commit": "0141adf1dde6cd69cf96d8eea23f4b6ebab36477",
    "runtime_sha256": "1c7c644c5187332e6fb5034fef0e232b5c1ae1e5f352b53fea90f7fd8acc4fb3"}
C4_ARCHIVE_COMMIT = "e439c226cc2d422b44007dedd25aa750a62f88a9"
C4_SUMMARY_PATH = "benchmarks/reports/round5-development/candidate-c4-full/summary.json"
C4_SUMMARY_SHA256 = "c53fcd0c379888b91da3a46ed609ad50df07a0661dc21bc0701bda04b3d56d38"
DEVELOPMENT_PLAN_PATH = "benchmarks/experiments/round5-c7-development-plan.json"
DEVELOPMENT_PLAN_SHA256 = None
C7_BINDING_PATH = "benchmarks/experiments/round5-c7-performance-binding.json"
MEMO_LIMITS = {"entry_limit": 2048, "text_byte_limit": 2097152}
MEMO_COUNTERS = ("hits", "misses", "evictions", "invalidations",
                 "oversized_bypasses", "uncertified_bypasses")
MEMO_DYNAMIC = ("allocated", "entries", "text_bytes", *MEMO_COUNTERS)
MEMO_BASELINE = {"available": False, "reason": "published-v0.3.2-has-no-derived-token-count-memo"}
MEMO_BOUNDARY = ("Read-only native snapshots outside timing. Same book retains exact token counts "
    "across native configurations; actual MCP uses fresh server processes and measured RSS "
    "without private memo counters.")
COHORTS = {
    "synthetic61": (168, "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26"),
    "public1015": (1015, "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"),
}
CONFIGS = (
    {"id": "native-char4000", "surface": "native", "budget_chars": 4000, "budget_tokens": None},
    {"id": "mcp-char4000", "surface": "official-sdk-mcp-stdio", "budget_chars": 4000, "budget_tokens": None},
    {"id": "native-token512", "surface": "native", "budget_chars": 8000, "budget_tokens": 512, "tokenizer": "cl100k_base"},
    {"id": "native-token1024", "surface": "native", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
    {"id": "native-token2048", "surface": "native", "budget_chars": 8000, "budget_tokens": 2048, "tokenizer": "cl100k_base"},
    {"id": "mcp-token1024", "surface": "official-sdk-mcp-stdio", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
)
ORDERS = (("baseline", "candidate"), ("candidate", "baseline"),
          ("candidate", "baseline"), ("baseline", "candidate"))
PACKAGES = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}
INVARIANTS = {"cache_error", "source_span_errors", "source_scope_errors", "page_projection_errors",
    "context_reconstruction_error", "metadata_error", "character_budget_error", "token_budget_error",
    "token_metadata_error", "mcp_projection_error", "result_limit_error", "unexpected_policy"}
RESOURCE_FIELDS = (
    "runtime_import_ms", "native_open_ms", "fresh_ingestion_ms", "unchanged_reingestion_ms",
    "mcp_startup_to_initialize_ms", "native_memory_after_ingestion.rss_bytes",
    "native_memory_after_ingestion.hwm_bytes", "native_memory_after_calls.rss_bytes",
    "native_memory_after_calls.hwm_bytes", "mcp_server_memory_after_calls.rss_bytes",
    "mcp_server_memory_after_calls.hwm_bytes",
    "mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms",
    "mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes",
    "mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes",
)
THRESHOLDS = {"geometric_mean_p95_improvement": 10,
    "at_least_one_public_native_token_p95_improvement": 15,
    "public_mcp_token1024_p95_improvement": 10, "maximum_pooled_p50_p95_regression": 5,
    "resource_mean_increase_review": 10}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, timeout=30)


def source_hash(commit):
    prefix = "src/memory_book/"
    names = git("ls-tree", "-r", "--name-only", commit, prefix).decode().splitlines()
    names = sorted(name for name in names if name.endswith(".py"))
    require(bool(names), "Source Git tree has no Python files")
    value = hashlib.sha256()
    for name in names:
        value.update(name.removeprefix(prefix).encode() + b"\0")
        value.update(git("show", commit + ":" + name) + b"\0")
    return value.hexdigest()


def quantile(values, proportion):
    """Independent linear interpolation at (N - 1) * proportion."""
    ordered = sorted(values)
    require(bool(ordered), "Empty sample set")
    position = (len(ordered) - 1) * proportion
    left = int(math.floor(position))
    right = int(math.ceil(position))
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def mean(values):
    return math.fsum(values) / len(values)


def latency(values):
    return {"samples": len(values), "p50_ms": quantile(values, .5),
            "p95_ms": quantile(values, .95), "mean_ms": mean(values)}


def numeric(values):
    return {"samples": len(values), "mean": mean(values), "p50": quantile(values, .5),
            "p95": quantile(values, .95), "min": min(values), "max": max(values)}


def close(actual, expected, path="value"):
    """Tolerate only floating-point summation roundoff, never missing fields."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        require(actual.keys() == expected.keys(), "Mapping fields differ: " + path)
        for key in expected:
            close(actual[key], expected[key], path + "." + key)
    elif isinstance(actual, list) and isinstance(expected, list):
        require(len(actual) == len(expected), "List length differs: " + path)
        for index, (left, right) in enumerate(zip(actual, expected)):
            close(left, right, path + f"[{index}]")
    elif type(actual) in (int, float) and type(expected) in (int, float):
        require(math.isfinite(actual) and math.isfinite(expected)
                and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-9),
                "Arithmetic differs: " + path)
    else:
        require(actual == expected, "Value differs: " + path)


def nested(value, path):
    for field in path.split("."):
        value = value[field]
    return value


def stable(row):
    return {key: value for key, value in row.items() if key not in ("wall_ms", "engine_source_sha256")}


def require_frozen_source():
    require(C7_PROVENANCE_BOUND is True,
            "C7 provenance is not frozen; registration and final source are intentionally blocked")
    require(isinstance(CONTINUATION_COMMIT, str)
            and re.fullmatch(r"[0-9a-f]{40}", CONTINUATION_COMMIT) is not None
            and isinstance(CONTINUATION_SHA256, str)
            and re.fullmatch(r"[0-9a-f]{64}", CONTINUATION_SHA256) is not None
            and isinstance(DEVELOPMENT_PLAN_SHA256, str)
            and re.fullmatch(r"[0-9a-f]{64}", DEVELOPMENT_PLAN_SHA256) is not None
            and isinstance(C7_REGISTRATION_PROTOCOL, str) and C7_REGISTRATION_PROTOCOL
            and isinstance(C7_REGISTRATION_STATUS, str) and C7_REGISTRATION_STATUS
            and isinstance(C7_POLICY_KEY, str) and C7_POLICY_KEY
            and type(C7_POLICY) is dict and C7_POLICY,
            "C7 registered transport policy or immutable identities are not frozen")
    candidate = SOURCES["candidate"]
    require(isinstance(candidate["commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", candidate["commit"]) is not None
            and isinstance(candidate["runtime_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", candidate["runtime_sha256"]) is not None,
            "C7 candidate source is not frozen; final audit is intentionally blocked")


def audit_native_memo(worker):
    """Check saved native observations; never call or import a runtime counter."""
    observation = worker["native_token_count_memo"]
    require(set(observation) == {*MEMO_LIMITS, "boundary", "configurations"}
            and all(type(observation[name]) is int and observation[name] == value
                    for name, value in MEMO_LIMITS.items())
            and observation["boundary"] == MEMO_BOUNDARY,
            "Native memo policy or measurement boundary differs: " + worker["key"])
    expected_ids = [config["id"] for config in CONFIGS if config["surface"] == "native"]
    observed = observation["configurations"]
    native = [config for config in worker["configurations"] if config["surface"] == "native"]
    require([config["id"] for config in native] == expected_ids
            and [record["id"] for record in observed] == expected_ids,
            "Missing, extra or reordered native memo observations: " + worker["key"])
    previous = None
    records = []
    for position, (config, record) in enumerate(zip(native, observed, strict=True)):
        path = worker["key"] + ":" + record["id"]
        require(set(record) == {"id", "first_query_id", "before", "after_first_call", "after"}
                and record["first_query_id"] == config["rows"][0]["query_id"],
                "Native memo first-call observation is not the retained first row: " + path)
        snapshots = [record[name] for name in ("before", "after_first_call", "after")]
        for snapshot in snapshots:
            if worker["label"] == "baseline":
                require(snapshot == MEMO_BASELINE, "Baseline memo availability is misrepresented: " + path)
                continue
            require(worker["label"] == "candidate" and snapshot.get("available") is True
                    and set(snapshot) == {"available", *MEMO_LIMITS, *MEMO_DYNAMIC},
                    "Candidate native memo fields differ: " + path)
            require(all(type(snapshot[name]) is int and snapshot[name] >= 0
                        for name in (*MEMO_LIMITS, *MEMO_DYNAMIC))
                    and all(snapshot[name] == value for name, value in MEMO_LIMITS.items())
                    and snapshot["allocated"] in (0, 1)
                    and snapshot["entries"] <= MEMO_LIMITS["entry_limit"]
                    and snapshot["text_bytes"] <= MEMO_LIMITS["text_byte_limit"],
                    "Native memo exceeds its registered bounds or has invalid counters: " + path)
            require(snapshot["allocated"] == 1 or not any(snapshot[name] for name in MEMO_DYNAMIC),
                    "Unallocated native memo is not empty: " + path)
        require(previous is None or previous == snapshots[0],
                "Native memo state changed between configurations: " + path)
        if worker["label"] == "candidate":
            if position == 0:
                require(not any(snapshots[0][name] for name in MEMO_DYNAMIC),
                        "Fresh MemoryBook did not begin with an empty unallocated memo: " + path)
            if record["id"] == "native-char4000":
                require(snapshots[0] == snapshots[1] == snapshots[2],
                        "Character recalls allocated or warmed the token memo: " + path)
            for earlier, later in zip(snapshots, snapshots[1:]):
                require(later["allocated"] >= earlier["allocated"]
                        and all(later[name] >= earlier[name] for name in MEMO_COUNTERS),
                        "Native memo cumulative counters decreased: " + path)
            records.append({"id": record["id"], "first_query_id": record["first_query_id"],
                "before": snapshots[0], "after_first_call": snapshots[1], "after": snapshots[2],
                "retained_entries_at_start": snapshots[0]["entries"],
                "later_native_configuration": position > 1,
                "first_call_counter_delta": {name: snapshots[1][name] - snapshots[0][name]
                                             for name in MEMO_COUNTERS},
                "configuration_counter_delta": {name: snapshots[2][name] - snapshots[0][name]
                                                for name in MEMO_COUNTERS}})
        previous = snapshots[-1]
    return {"worker": worker["key"], "label": worker["label"],
        "available": worker["label"] == "candidate", "limits": MEMO_LIMITS,
        "empty_connection_start_verified": worker["label"] == "candidate",
        "native_configurations": records,
        "boundary": MEMO_BOUNDARY,
        "memory_boundary": "The 2 MiB cap counts retained str object sizes after encoding; key/container/encoder overhead and other process allocations are outside this cap and remain subject to the original RSS review."}


def audit_rejected_c5(binding, plan, document, read):
    """Read C5's immutable negative result and retain all 42 frozen inputs."""
    known = KNOWN_C5_REJECTION
    prior_raw = read(ROOT / known["binding_path"])
    summary_raw = read(ROOT / known["summary_path"])
    require(sha(prior_raw) == known["binding_sha256"]
            and sha(summary_raw) == known["summary_sha256"]
            and summary_raw == git("show", known["result_commit"] + ":" + known["summary_path"]),
            "Original C5 binding or committed rejected summary differs")
    prior, summary = json.loads(prior_raw), json.loads(summary_raw)
    require(prior["evaluator"] == summary["evaluator"] == summary["run"]["evaluator"]
                == "round5-c5-default-performance-1"
            and prior["status"] == "frozen-before-formal-timing"
            and prior["sources"] == {"baseline": SOURCES["baseline"], "candidate": known["source"]}
            and prior["packages"] == PACKAGES and prior["plan_sha256"] == binding["plan_sha256"]
            and sha(canonical(prior) + b"\n") == known["binding_sha256"]
            and summary["plan"] == plan and summary["run"]["binding"] == prior
            and summary["run"]["binding_sha256"] == known["binding_sha256"],
            "C5 original source, evaluator or same-gate binding differs")
    require(summary["status"] == "measurements_completed" and summary["error"] is None
            and summary["evaluator_unchanged"] is True
            and summary["validation"] == {"passed": True, "issues": [], "workers": 16,
                "expected_workers": 16, "timed_calls": 56784, "expected_calls": 56784}
            and summary["run"]["publication"] == {"run_id": "43552372788", "run_attempt": "1",
                "branch": "validation/v033-round5-c5-performance-43552372788-1",
                "claim_branch": "validation/v033-round5-c5-claim-" + known["binding_sha256"]},
            "C5 must remain its complete valid first-attempt formal experiment")
    accepted, recorded = summary["acceptance"], document["rejected_c5"]
    require({key: recorded[key] for key in known["source"]} == known["source"]
            and recorded["formal_run"] == known["formal_run"]
            and recorded["result_commit"] == known["result_commit"]
            and recorded["binding_sha256"] == known["binding_sha256"]
            and recorded["summary_sha256"] == known["summary_sha256"]
            and recorded["accepted"] is False and recorded["numeric_gate_passed"] is False
            and recorded["decision"] == "Preserve the complete valid C5 formal rejection. Do not rerun the same source to select a faster sample.",
            "C7 registration does not preserve C5's complete identity and rejection")
    require(accepted["accepted"] is False and accepted["numeric_gate_passed"] is False
            and accepted["thresholds_percent"] == {
                key: value for key, value in THRESHOLDS.items() if key != "resource_mean_increase_review"}
            and accepted["geometric_mean_p95_improvement_percent"]
                == recorded["aggregate_p95_gain_percent"] == 15.220791446446002
            and accepted["best_public_native_token_p95_improvement_percent"]
                == recorded["public_native_best_gain_percent"] == 15.422173278138885
            and accepted["public_mcp_token1024_p95_improvement_percent"]
                == recorded["public_mcp_token1024_gain_percent"] == 6.673181339995871
            and accepted["regressions_above_five_percent"] == [] and accepted["resource_review"] == [],
            "C5's sole failed actual-MCP improvement gate must remain rejected")
    frozen = prior["evaluator_files"]
    require(len(frozen) == 42, "Original C5 frozen evaluator input count differs")
    for name, expected in frozen.items():
        require(binding["evaluator_files"].get(name) == expected
                and sha(git("show", prior["evaluator_commit"] + ":" + name)) == expected,
                "C7 did not preserve a frozen C5 evaluator input: " + name)
    for name, expected in ((known["binding_path"], known["binding_sha256"]),
                           (known["summary_path"], known["summary_sha256"])):
        require(binding["evaluator_files"].get(name) == expected, "C7 C5-rejection input differs: " + name)
    registration = {"rejected_c5_binding_sha256": known["binding_sha256"],
        "rejected_c5_summary_sha256": known["summary_sha256"],
        "rejected_c5_result_commit": known["result_commit"], "frozen_c5_evaluator_files": frozen}
    evidence = {"source": known["source"], "result_commit": known["result_commit"],
        "binding_sha256": known["binding_sha256"], "summary_sha256": known["summary_sha256"],
        "valid_calls": 56784, "original_accepted": False, "original_numeric_gate_passed": False,
        "aggregate_p95_gain_percent": accepted["geometric_mean_p95_improvement_percent"],
        "public_native_best_gain_percent": accepted["best_public_native_token_p95_improvement_percent"],
        "public_mcp_token1024_gain_percent": accepted["public_mcp_token1024_p95_improvement_percent"],
        "boundary": "Original committed C5 summary and rejection verified; C5 retrieval and raw-ledger arithmetic are not rerun by this C7 audit."}
    return registration, evidence


def audit_rejected_c6(binding, plan, document, read):
    """Retain the complete valid C6 rejection and its 51 frozen inputs."""
    known = KNOWN_C6_REJECTION
    prior_raw = read(ROOT / known["binding_path"])
    summary_raw = read(ROOT / known["summary_path"])
    require(sha(prior_raw) == known["binding_sha256"]
            and sha(summary_raw) == known["summary_sha256"]
            and summary_raw == git("show", known["result_commit"] + ":" + known["summary_path"]),
            "Original C6 binding or committed rejected summary differs")
    prior, summary = json.loads(prior_raw), json.loads(summary_raw)
    require(prior["evaluator"] == summary["evaluator"] == summary["run"]["evaluator"]
                == "round5-c6-default-performance-1"
            and prior["status"] == "frozen-before-formal-timing"
            and prior["sources"] == {"baseline": SOURCES["baseline"], "candidate": known["source"]}
            and prior["packages"] == PACKAGES and prior["plan_sha256"] == binding["plan_sha256"]
            and sha(canonical(prior) + b"\n") == known["binding_sha256"]
            and summary["plan"] == plan and summary["run"]["binding"] == prior
            and summary["run"]["binding_sha256"] == known["binding_sha256"],
            "C6 original source, evaluator or same-gate binding differs")
    require(summary["status"] == "measurements_completed" and summary["error"] is None
            and summary["evaluator_unchanged"] is True
            and summary["validation"] == {"passed": True, "issues": [], "workers": 16,
                "expected_workers": 16, "timed_calls": 56784, "expected_calls": 56784}
            and summary["run"]["publication"] == {"run_id": "43557136276", "run_attempt": "1",
                "branch": "validation/v033-round5-c6-performance-43557136276-1",
                "claim_branch": "validation/v033-round5-c6-claim-" + known["binding_sha256"]},
            "C6 must remain its complete valid first-attempt formal experiment")
    accepted, recorded = summary["acceptance"], document["rejected_c6"]
    require({key: recorded[key] for key in known["source"]} == known["source"]
            and recorded["formal_run"] == known["formal_run"]
            and recorded["result_commit"] == known["result_commit"]
            and recorded["binding_sha256"] == known["binding_sha256"]
            and recorded["summary_sha256"] == known["summary_sha256"]
            and recorded["accepted"] is False and recorded["numeric_gate_passed"] is False
            and recorded["decision"] == "Preserve the complete valid C6 formal rejection. Do not rerun the same source to select a faster sample.",
            "C7 registration does not preserve C6's complete identity and rejection")
    require(accepted["accepted"] is False and accepted["numeric_gate_passed"] is False
            and accepted["thresholds_percent"] == {
                key: value for key, value in THRESHOLDS.items() if key != "resource_mean_increase_review"}
            and accepted["geometric_mean_p95_improvement_percent"]
                == recorded["aggregate_p95_gain_percent"] == 14.91917268891384
            and accepted["best_public_native_token_p95_improvement_percent"]
                == recorded["public_native_best_gain_percent"] == 16.286785133390612
            and accepted["public_mcp_token1024_p95_improvement_percent"]
                == recorded["public_mcp_token1024_gain_percent"] == 5.7989107559001996
            and accepted["regressions_above_five_percent"] == [] and accepted["resource_review"] == [],
            "C6's failed actual-MCP improvement gate must remain rejected")
    frozen = prior["evaluator_files"]
    require(len(frozen) == 51, "Original C6 frozen evaluator input count differs")
    for name, expected in frozen.items():
        require(binding["evaluator_files"].get(name) == expected
                and sha(git("show", prior["evaluator_commit"] + ":" + name)) == expected,
                "C7 did not preserve a frozen C6 evaluator input: " + name)
    for name, expected in ((known["binding_path"], known["binding_sha256"]),
                           (known["summary_path"], known["summary_sha256"])):
        require(binding["evaluator_files"].get(name) == expected, "C7 C6-rejection input differs: " + name)
    registration = {"rejected_c6_binding_sha256": known["binding_sha256"],
        "rejected_c6_summary_sha256": known["summary_sha256"],
        "rejected_c6_result_commit": known["result_commit"], "frozen_c6_evaluator_files": frozen}
    evidence = {"source": known["source"], "result_commit": known["result_commit"],
        "binding_sha256": known["binding_sha256"], "summary_sha256": known["summary_sha256"],
        "valid_calls": 56784, "original_accepted": False, "original_numeric_gate_passed": False,
        "aggregate_p95_gain_percent": accepted["geometric_mean_p95_improvement_percent"],
        "public_native_best_gain_percent": accepted["best_public_native_token_p95_improvement_percent"],
        "public_mcp_token1024_gain_percent": accepted["public_mcp_token1024_p95_improvement_percent"],
        "boundary": "Original committed C6 summary and rejection verified; C6 retrieval and raw-ledger arithmetic are not rerun by this C7 audit."}
    return registration, evidence


def audit_c7_registered_scope(document):
    """No transport-policy schema is guessed before actual preregistration."""
    require(isinstance(C7_POLICY_KEY, str) and C7_POLICY_KEY
            and type(C7_POLICY) is dict and C7_POLICY,
            "C7 registered transport-policy schema is not frozen")
    require(document.get(C7_POLICY_KEY) == C7_POLICY,
            "C7 registered transport policy differs")


def audit_continuation(run, plan, execution, report_path, state, read):
    """Verify C7 registration and retained C3/C4/C5/C6 evidence without any runner import."""
    binding = run["binding"]
    registration_raw = read(ROOT / CONTINUATION_PATH)
    require(sha(registration_raw) == CONTINUATION_SHA256
            and registration_raw == git("show", CONTINUATION_COMMIT + ":" + CONTINUATION_PATH),
            "Committed C7 preregistration differs")
    document = json.loads(registration_raw)
    require(document["schema_version"] == 1
            and document["protocol"] == C7_REGISTRATION_PROTOCOL
            and document["status"] == C7_REGISTRATION_STATUS
            and document["baseline"] == plan["baseline"] == {"release": "v0.3.2", **SOURCES["baseline"]},
            "C7 preregistration identity differs")
    formal = document["formal_protocol"]
    require(formal["matrix_plan"] == "benchmarks/experiments/round5-plan.json"
            and formal["calls"] == 56784 and formal["rounds"] == 4
            and formal["order"] == ["AB", "BA", "BA", "AB"]
            and formal["thresholds_percent"] == THRESHOLDS == plan["thresholds_percent"],
            "C7 continuation changed the registered matrix or a gate")
    policy = document["cache_policy"]
    require(policy["kind"] == "derived-exact-token-count-only"
            and policy["entry_limit"] == MEMO_LIMITS["entry_limit"]
            and policy["retained_text_object_byte_limit"] == MEMO_LIMITS["text_byte_limit"]
            and policy["ownership"] == "one MemoryBook connection; both encoders share limits",
            "C7 registered cache kind, ownership or fixed capacity differs")
    audit_c7_registered_scope(document)
    development_raw = read(ROOT / DEVELOPMENT_PLAN_PATH)
    require(sha(development_raw) == DEVELOPMENT_PLAN_SHA256
            and development_raw == git("show", CONTINUATION_COMMIT + ":" + DEVELOPMENT_PLAN_PATH),
            "Committed C7 development preregistration differs")
    development = json.loads(development_raw)
    require(document["development_protocol"]["plan"] == DEVELOPMENT_PLAN_PATH
            and document["development_protocol"]["calls"] == development["calls"] == 18928
            and document["development_protocol"]["version_pairs"] == development["version_pairs"] == 9464
            and development["rounds"] == 2
            and development["engine_order"] == [["baseline", "candidate"], ["candidate", "baseline"]],
            "C7 registered development matrix differs")
    rejected = document["rejected_c3"]
    require({key: rejected[key] for key in C3_SOURCE} == C3_SOURCE
            and rejected["formal_run"] == "43547085915-1"
            and rejected["result_commit"] == C3_RESULT_COMMIT,
            "Rejected C3 source/run identity differs")
    prior_raw = read(ROOT / C3_BINDING_PATH)
    summary_raw = read(ROOT / C3_SUMMARY_PATH)
    require(sha(prior_raw) == C3_BINDING_SHA256 and sha(summary_raw) == C3_SUMMARY_SHA256
            and summary_raw == git("show", C3_RESULT_COMMIT + ":" + C3_SUMMARY_PATH),
            "Original C3 binding or committed rejected summary differs")
    prior, summary = json.loads(prior_raw), json.loads(summary_raw)
    require(prior["evaluator"] == summary["evaluator"] == summary["run"]["evaluator"]
            == "round5-default-performance-1"
            and prior["status"] == "frozen-before-formal-timing"
            and prior["sources"] == {"baseline": SOURCES["baseline"], "candidate": C3_SOURCE}
            and prior["packages"] == PACKAGES
            and prior["plan_sha256"] == binding["plan_sha256"]
            and summary["plan"] == plan and summary["run"]["binding"] == prior
            and summary["run"]["binding_sha256"] == C3_BINDING_SHA256
            and sha(canonical(prior) + b"\n") == C3_BINDING_SHA256,
            "Original C3 source, evaluator or same-gate binding differs")
    require(summary["status"] == "measurements_completed" and summary["error"] is None
            and summary["evaluator_unchanged"] is True
            and summary["validation"] == {"passed": True, "issues": [], "workers": 16,
                "expected_workers": 16, "timed_calls": 56784, "expected_calls": 56784}
            and summary["run"]["publication"] == {
                "run_id": "43547085915", "run_attempt": "1",
                "branch": "validation/v033-round5-performance-43547085915-1",
                "claim_branch": "validation/v033-round5-claim-" + C3_BINDING_SHA256},
            "C3 must remain the original complete, valid 56,784-call experiment")
    acceptance = summary["acceptance"]
    require(acceptance["accepted"] is False and acceptance["numeric_gate_passed"] is False
            and acceptance["thresholds_percent"] == {
                key: value for key, value in THRESHOLDS.items() if key != "resource_mean_increase_review"}
            and acceptance["geometric_mean_p95_improvement_percent"]
                == rejected["aggregate_p95_gain_percent"] >= 10
            and acceptance["best_public_native_token_p95_improvement_percent"]
                == rejected["public_native_best_gain_percent"] < 15
            and acceptance["public_mcp_token1024_p95_improvement_percent"]
                == rejected["public_mcp_token1024_gain_percent"] < 10
            and acceptance["resource_review"] == [],
            "C3's original two failed numerical gates must remain rejected")
    for name, expected in prior["evaluator_files"].items():
        require(binding["evaluator_files"].get(name) == expected
                and sha(git("show", prior["evaluator_commit"] + ":" + name)) == expected,
                "C7 did not preserve a frozen C3 evaluator input: " + name)
    c4_raw = read(ROOT / C4_SUMMARY_PATH)
    require(sha(c4_raw) == C4_SUMMARY_SHA256
            and c4_raw == git("show", C4_ARCHIVE_COMMIT + ":" + C4_SUMMARY_PATH),
            "Original committed C4 development summary differs")
    c4 = json.loads(c4_raw)
    recorded_c4 = document["prior_c4"]
    require({name: recorded_c4[name] for name in C4_SOURCE} == C4_SOURCE
            and recorded_c4["development_report"] == C4_SUMMARY_PATH
            and recorded_c4["development_archive_commit"] == C4_ARCHIVE_COMMIT
            and recorded_c4["calls"] == c4["total_calls"] == 18928
            and recorded_c4["version_pairs"] == c4["complete_payload_pairs"] == 9464
            and c4["status"] == "completed" and c4["payload_mismatches"] == []
            and c4["all_invariants_passed"] is True
            and c4["source_index_revision_unchanged"] is True
            and c4["cross_source_archive_projections_identical"] is True
            and c4["candidate_source_commit"] == C4_SOURCE["commit"]
            and c4["candidate_runtime_sha256"] == C4_SOURCE["runtime_sha256"]
            and c4["baseline_source_commit"] == SOURCES["baseline"]["commit"],
            "C4 development evidence was changed or misidentified as C7")
    c4_names = set(prior["evaluator_files"]) | {
        "scripts/round5_c4_performance.py", "tests/test_round5_c4_performance.py",
        "tests/test_round5_candidate_c4.py", ".github/workflows/round5-c4-performance.yml",
        "benchmarks/experiments/round5-c4-addendum.json", C3_BINDING_PATH, C3_SUMMARY_PATH}
    frozen_c4 = {name: sha(git("show", C4_ARCHIVE_COMMIT + ":" + name)) for name in sorted(c4_names)}
    require(len(frozen_c4) == 30, "Retained C4 evaluator input count differs")
    for name, expected in frozen_c4.items():
        require(binding["evaluator_files"].get(name) == expected,
                "C7 did not preserve a frozen C4 evaluator input: " + name)
    for name in ("scripts/round5_c7_performance.py", "scripts/round5_c7_development_pair.py",
                 "tests/test_round5_c7_performance.py", "tests/test_round5_candidate_c7.py",
                 ".github/workflows/round5-c7-performance.yml"):
        require(name in binding["evaluator_files"], "Missing new C7 evaluator provenance: " + name)
    for name, expected in ((CONTINUATION_PATH, CONTINUATION_SHA256),
                           (C3_BINDING_PATH, C3_BINDING_SHA256), (C3_SUMMARY_PATH, C3_SUMMARY_SHA256),
                           (C4_SUMMARY_PATH, C4_SUMMARY_SHA256),
                           (DEVELOPMENT_PLAN_PATH, DEVELOPMENT_PLAN_SHA256)):
        require(binding["evaluator_files"].get(name) == expected, "C7 continuation input checksum differs: " + name)
    c5_registration, c5_evidence = audit_rejected_c5(binding, plan, document, read)
    c6_registration, c6_evidence = audit_rejected_c6(binding, plan, document, read)
    require(len(binding["evaluator_files"]) == C7_EVALUATOR_FILE_COUNT,
            "C7 exact frozen evaluator input count differs")
    expected_registration = {"path": CONTINUATION_PATH, "commit": CONTINUATION_COMMIT,
        "sha256": CONTINUATION_SHA256, "document": document,
        "rejected_c3_binding_sha256": C3_BINDING_SHA256,
        "rejected_c3_summary_sha256": C3_SUMMARY_SHA256,
        "frozen_c3_evaluator_files": prior["evaluator_files"],
        "prior_c4_summary_sha256": C4_SUMMARY_SHA256, "prior_c4_archive_commit": C4_ARCHIVE_COMMIT,
        "frozen_c4_evaluator_files": frozen_c4, "development_plan_sha256": DEVELOPMENT_PLAN_SHA256,
        **c5_registration, **c6_registration}
    require(binding["continuation_registration"] == expected_registration,
            "C7 binding does not retain the exact registered continuation")
    binding_raw = read(ROOT / C7_BINDING_PATH)
    require(binding_raw == canonical(binding) + b"\n" and sha(binding_raw) == run["binding_sha256"]
            and binding["evaluator"] == execution["evaluator"] == "round5-c7-default-performance-1"
            and SOURCES["candidate"]["runtime_sha256"] not in
                (SOURCES["baseline"]["runtime_sha256"], C3_SOURCE["runtime_sha256"], C4_SOURCE["runtime_sha256"],
                 KNOWN_C5_REJECTION["source"]["runtime_sha256"],
                 KNOWN_C6_REJECTION["source"]["runtime_sha256"]),
            "C7 binding namespace or materially changed source identity differs")
    publication = run["publication"]
    run_id = publication["run_id"]
    require(isinstance(run_id, str) and re.fullmatch(r"[0-9]+", run_id) is not None,
            "Invalid C7 hosted run identity")
    suffix = "round5-c7-performance-" + run_id + "-1"
    require(publication == {"run_id": run_id, "run_attempt": "1",
                "branch": "validation/v033-" + suffix,
                "claim_branch": "validation/v033-round5-c7-claim-" + run["binding_sha256"]}
            and report_path.name == "report.json.gz" and report_path.parent.name == state.name == suffix
            and Path(execution["state_dir"]).parts[-2:] == (".artifacts", suffix)
            and Path(execution["output"]).parts[-4:] == ("benchmarks", "reports", suffix, "report.json.gz"),
            "C7 report, worker state, result branch or exclusive claim namespace differs")
    return {"preregistration": {"path": CONTINUATION_PATH, "commit": CONTINUATION_COMMIT,
                "sha256": CONTINUATION_SHA256},
        "same_original_plan_and_all_gates_verified": True,
        "frozen_c3_evaluator_inputs_retained": len(prior["evaluator_files"]),
        "frozen_c4_evaluator_inputs_retained": len(frozen_c4),
        "frozen_c5_evaluator_inputs_retained": len(c5_registration["frozen_c5_evaluator_files"]),
        "rejected_c5": c5_evidence,
        "frozen_c6_evaluator_inputs_retained": len(c6_registration["frozen_c6_evaluator_files"]),
        "rejected_c6": c6_evidence,
        "registered_c7_policy": {"key": C7_POLICY_KEY, "policy": document[C7_POLICY_KEY]},
        "registered_memo_policy": policy,
        "development_plan_sha256": DEVELOPMENT_PLAN_SHA256,
        "prior_c4": {"source": C4_SOURCE, "archive_commit": C4_ARCHIVE_COMMIT,
            "summary_path": C4_SUMMARY_PATH, "summary_sha256": C4_SUMMARY_SHA256,
            "development_calls": c4["total_calls"], "development_pairs": c4["complete_payload_pairs"],
            "boundary": "Original complete development summary verified. C4 formal runner was never bound or executed; no C4 formal acceptance is inferred and development arithmetic is not rerun here."},
        "rejected_c3": {"source": C3_SOURCE, "result_commit": C3_RESULT_COMMIT,
            "binding_sha256": C3_BINDING_SHA256, "summary_sha256": C3_SUMMARY_SHA256,
            "status": summary["status"], "valid_calls": summary["validation"]["timed_calls"],
            "original_accepted": acceptance["accepted"], "original_numeric_gate_passed": acceptance["numeric_gate_passed"],
            "aggregate_p95_gain_percent": acceptance["geometric_mean_p95_improvement_percent"],
            "public_native_best_gain_percent": acceptance["best_public_native_token_p95_improvement_percent"],
            "public_mcp_token1024_gain_percent": acceptance["public_mcp_token1024_p95_improvement_percent"],
            "boundary": "Original committed summary and rejection verified; C3 retrieval and raw-ledger arithmetic are not rerun by this C7 audit."},
        "binding_path": C7_BINDING_PATH, "publication": publication}


def audit(report_path, state):
    require_frozen_source()
    files = {}

    def read(path):
        raw = path.read_bytes()
        files[str(path.resolve())] = {"bytes": len(raw), "sha256": sha(raw)}
        return raw

    compressed = read(report_path)
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    run, plan = report["run"], report["plan"]
    binding = run["binding"]
    require(report["evaluator"] == run["evaluator"] == "round5-c7-default-performance-1", "Wrong evaluator")
    require(report["error"] is None and report["status"] == "measurements_completed", "Incomplete formal run")
    require(report["evaluator_unchanged"] is True, "Measurement reports changed evaluator")
    require(binding["sources"] == SOURCES and binding["packages"] == run["host"]["packages"] == PACKAGES,
            "Source or dependency binding differs")
    require(binding["status"] == "frozen-before-formal-timing", "Candidate was not frozen")
    require(sha(canonical(binding) + b"\n") == run["binding_sha256"], "Canonical binding checksum differs")
    require(json.loads(read(state / "run.json")) == run, "Public run identity differs")
    execution = json.loads(read(state / "execution.json"))
    require(execution["binding_sha256"] == run["binding_sha256"]
            and execution["run_identity_sha256"] == digest(run) and execution["host"] == run["host"],
            "Execution claim differs")
    require(run["publication"]["run_attempt"] == "1"
            and run["publication"]["claim_branch"] == "validation/v033-round5-c7-claim-" + run["binding_sha256"],
            "Hosted first-attempt claim identity differs")
    for name, source in SOURCES.items():
        require(source_hash(source["commit"]) == source["runtime_sha256"], "Committed runtime differs: " + name)
    require(binding["evaluator_files"] == run["evaluator_files"], "Evaluator file mappings differ")
    for name, expected in binding["evaluator_files"].items():
        require(sha(git("show", binding["evaluator_commit"] + ":" + name)) == expected,
                "Committed evaluator differs: " + name)
    original_plan = git("show", binding["evaluator_commit"] + ":benchmarks/experiments/round5-plan.json")
    require(json.loads(original_plan) == plan
            and sha(original_plan) == run["plan_sha256"] == binding["plan_sha256"], "Registered plan differs")
    require(plan["thresholds_percent"] == THRESHOLDS, "Registered numerical gates differ")
    formal = plan["performance_candidate"]["formal"]
    require(formal["rounds"] == 4 and formal["calls"] == 56784
            and formal["configs"] == list(CONFIGS) and formal["cohorts"] == list(COHORTS)
            and formal["engine_order"] == [list(order) for order in ORDERS], "Formal matrix differs")
    continuation = audit_continuation(run, plan, execution, report_path, state, read)
    expected_schedule = [{"key": f"r{r}-{cohort}-{label}", "round": r, "cohort": cohort, "label": label}
                         for r, order in enumerate(ORDERS) for cohort in COHORTS for label in order]
    require(run["schedule"] == expected_schedule, "ABBA worker schedule differs")
    require(len(report["workers"]) == 16, "Expected 16 workers")
    expected_names = {item["key"] for item in expected_schedule}
    for suffix in (".json.gz", ".started.json", ".attempts.jsonl.gz"):
        actual_names = {p.name.removesuffix(suffix) for p in (state / "workers").glob("*" + suffix)}
        require(actual_names == expected_names, "Missing or extra worker artifacts: " + suffix)
    for cohort, (count, fingerprint) in COHORTS.items():
        description = run["cohorts"][cohort]
        ids = description["query_ids_original_order"]
        require(description["queries"] == count and description["sha256"] == fingerprint
                and len(ids) == len(set(ids)) == count and sorted(ids) == description["query_ids"],
                "Cohort identity/count differs: " + cohort)
    canonical_rows, paired, worker_rows, logical = {}, {}, {}, {}
    calls = event_count = negative_timings = zero_timings = invalid_timings = 0
    source_payloads, native_memo_observations = [], []
    for spec, worker in zip(expected_schedule, report["workers"]):
        key = spec["key"]
        require(all(worker[field] == value for field, value in spec.items()), "Worker identity differs: " + key)
        require(worker["status"] == "completed" and worker["error"] is None
                and worker["source"] == worker["source_after"] == SOURCES[spec["label"]]
                and worker["run_identity_sha256"] == digest(run), "Worker source/status differs: " + key)
        require(worker["dataset_sha256"] == COHORTS[spec["cohort"]][1], "Worker data differs: " + key)
        require(worker["all_replayed_sessions_skipped"] and worker["native_recall_cache_rows"] == 0
                and worker["indexed_content"] == worker["indexed_content_after_calls"], "Index/cache/replay differs: " + key)
        source_payloads.append({"worker": key, "source": worker["source"],
                                "indexed_content_sha256": digest(worker["indexed_content"])})
        for field in ("indexed_content", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256",
                      "mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            identity = (spec["cohort"], field)
            require(identity not in logical or logical[identity] == worker[field], "Stable setup field differs: " + key + ":" + field)
            logical.setdefault(identity, worker[field])
        require(worker["mcp_server_memory_after_calls"]["available"] is True
                and set(worker["mcp_sessions"]) == {"mcp-char4000", "mcp-token1024"}, "Missing actual MCP sessions")
        for name, session in worker["mcp_sessions"].items():
            require(session["mcp_server_memory_after_calls"]["available"] is True, "Missing MCP process RSS")
            for field in ("mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
                require(session[field] == worker[field], "MCP session setup differs: " + name)
        prefix = state / "workers" / key
        saved_worker = json.loads(gzip.decompress(read(Path(str(prefix) + ".json.gz"))))
        require(saved_worker == worker, "Worker differs from aggregate: " + key)
        native_memo_observations.append(audit_native_memo(worker))
        started = json.loads(read(Path(str(prefix) + ".started.json")))
        require(started == {"worker": spec, "run_identity_sha256": digest(run)}, "Worker start marker differs")
        ledger_bytes = gzip.decompress(read(Path(str(prefix) + ".attempts.jsonl.gz")))
        require(sha(ledger_bytes) == worker["ledger_sha256"], "Original ledger checksum differs")
        ledger = [json.loads(line) for line in ledger_bytes.splitlines()]
        raw_ledger = Path(str(prefix) + ".attempts.jsonl")
        if raw_ledger.exists():
            require(read(raw_ledger) == ledger_bytes, "Raw and compressed ledger differ")
        require(len(worker["configurations"]) == 6, "Missing or extra configuration")
        position = 0
        for config_index, (config, configured) in enumerate(zip(CONFIGS, worker["configurations"])):
            require({name: configured[name] for name in config} == config, "Configuration differs")
            order = list(run["cohorts"][spec["cohort"]]["query_ids_original_order"])
            random.Random(41061 + 1009 * spec["round"] + config_index).shuffle(order)
            require([row["query_id"] for row in configured["rows"]] == order, "Query order/count differs")
            times = []
            for row in configured["rows"]:
                elapsed = row["wall_ms"]
                invalid_timings += type(elapsed) not in (int, float) or not math.isfinite(elapsed)
                negative_timings += isinstance(elapsed, (int, float)) and elapsed < 0
                zero_timings += elapsed == 0
                require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0, "Invalid timing sample")
                require(row["engine_source_sha256"] == SOURCES[spec["label"]]["runtime_sha256"], "Row source differs")
                require(set(row["invariants"]) == INVARIANTS and not any(row["invariants"].values()), "Recorded invariant failure")
                mcp = config["surface"] == "official-sdk-mcp-stdio"
                require(row["cache_rows_before"] == 0 and row["cache_rows_after"] == int(mcp), "Result cache policy differs")
                require(0 <= row["context_chars"] <= config["budget_chars"] and 0 <= row["result_count"] <= 5,
                        "Recorded result/character budget differs")
                for field in ("payload_sha256", "native_payload_sha256", "context_sha256"):
                    require(re.fullmatch(r"[0-9a-f]{64}", row[field]) is not None, "Invalid complete payload digest")
                require((isinstance(row["envelope_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", row["envelope_sha256"]))
                        if mcp else row["envelope_sha256"] is None, "Envelope digest boundary differs")
                require(set(row["tokens"]) == {"cl100k_base", "o200k_base"}, "Reference encodings differ")
                for token_counts in row["tokens"].values():
                    require(set(token_counts) == {"context", "response_text", "response_envelope_json"}, "Token surfaces differ")
                    require(all(type(token_counts[field]) is int and token_counts[field] >= 0
                                for field in ("context", "response_text")), "Invalid token counts")
                    envelope_count = token_counts["response_envelope_json"]
                    require((type(envelope_count) is int and envelope_count >= 0) if mcp else envelope_count is None,
                            "Envelope token boundary differs")
                if config["budget_tokens"] is not None:
                    count = row["tokens"]["cl100k_base"]["context"]
                    expected = {"budget_tokens": config["budget_tokens"], "tokenizer": "cl100k_base",
                                "tokenizer_version": "0.12.0", "context_tokens": count}
                    require(count <= config["budget_tokens"] and row["token_metadata"] == {"native": expected, "response": expected},
                            "Recorded token budget/count metadata differs")
                else:
                    require(row["token_metadata"] is None, "Unexpected token metadata")
                identity = (spec["cohort"], config["id"], row["query_id"])
                unchanged = stable(row)
                require(identity not in canonical_rows or canonical_rows[identity] == unchanged,
                        "Full stable row/payload mismatch: " + repr(identity))
                canonical_rows.setdefault(identity, unchanged)
                pair_key = (spec["round"], *identity)
                paired.setdefault(pair_key, {})[spec["label"]] = unchanged
                worker_rows[(key, config["id"], row["query_id"])] = row
                require(position * 2 + 1 < len(ledger), "Truncated call ledger")
                first, last = ledger[position * 2:position * 2 + 2]
                require(first["event"] == "started" and last["event"] == "finished"
                        and first["seq"] == last["seq"] == position
                        and first["config"] == last["config"] == config["id"]
                        and first["query_id"] == row["query_id"] and last["row"] == row,
                        "Call ledger does not match saved response")
                position += 1
                calls += 1
                times.append(elapsed)
            close(configured["latency"], latency(times), key + ":" + config["id"])
        require(len(ledger) == position * 2, "Extra or interrupted ledger events")
        event_count += len(ledger)
    require(calls == 56784 and len(paired) == 28392 and len(canonical_rows) == 7098,
            "Incomplete call/pair matrix")
    require(all(set(pair) == {"baseline", "candidate"} and pair["baseline"] == pair["candidate"]
                for pair in paired.values()), "Complete output pair differs")
    native_mcp_pairs = 0
    for spec in expected_schedule:
        for suffix in ("char4000", "token1024"):
            for identity in run["cohorts"][spec["cohort"]]["query_ids_original_order"]:
                native = worker_rows[(spec["key"], "native-" + suffix, identity)]
                mcp = worker_rows[(spec["key"], "mcp-" + suffix, identity)]
                require(native["native_payload_sha256"] == mcp["native_payload_sha256"], "MCP provenance differs from native")
                native_mcp_pairs += 1
    require(native_mcp_pairs == 18928, "Native/MCP pair count differs")
    cells, adverse, per_round_adverse = [], [], []
    for cohort in COHORTS:
        for config in CONFIGS:
            cell = {"cohort": cohort, **config}
            original = next(c for c in report["comparisons"] if c["cohort"] == cohort and c["id"] == config["id"])
            for label in SOURCES:
                rows_by_round = [[row["wall_ms"] for worker in report["workers"]
                    if worker["cohort"] == cohort and worker["label"] == label and worker["round"] == repetition
                    for found in worker["configurations"] if found["id"] == config["id"] for row in found["rows"]]
                    for repetition in range(4)]
                combined = [value for row in rows_by_round for value in row]
                cell[label] = {"latency": latency(combined), "first_round_latency": latency(rows_by_round[0]),
                    "repeat_rounds_latency": latency([value for row in rows_by_round[1:] for value in row]),
                    "by_round": [latency(row) for row in rows_by_round]}
                for field in ("latency", "first_round_latency", "repeat_rounds_latency"):
                    close(original[label][field], cell[label][field], cohort + ":" + config["id"] + ":" + label + ":" + field)
            changes = {field: 100 * (cell["candidate"]["latency"][field] / cell["baseline"]["latency"][field] - 1)
                       for field in ("p50_ms", "p95_ms", "mean_ms")}
            cell["candidate_change_percent"] = changes
            close(original["candidate_change_percent"], changes, "Pooled change")
            for metric, change in changes.items():
                if change > 0:
                    adverse.append({"cohort": cohort, "config": config["id"], "metric": metric, "change_percent": change})
            for repetition in range(4):
                for label in SOURCES:
                    close(original["rounds"][repetition][label], cell[label]["by_round"][repetition], "Round latency")
                for metric in ("p50_ms", "p95_ms", "mean_ms"):
                    change = 100 * (cell["candidate"]["by_round"][repetition][metric] /
                                    cell["baseline"]["by_round"][repetition][metric] - 1)
                    if change > 0:
                        per_round_adverse.append({"cohort": cohort, "config": config["id"], "round": repetition,
                                                  "metric": metric, "change_percent": change})
            cells.append(cell)
    require(len(cells) == len(report["comparisons"]) == 12, "Comparison cell count differs")
    geometric_gain = 100 * (1 - math.exp(mean([math.log(cell["candidate"]["latency"]["p95_ms"] /
                                                      cell["baseline"]["latency"]["p95_ms"]) for cell in cells])))
    best_public = max(-cell["candidate_change_percent"]["p95_ms"] for cell in cells
                      if cell["cohort"] == "public1015" and cell["surface"] == "native" and cell["budget_tokens"] is not None)
    mcp_gain = next(-cell["candidate_change_percent"]["p95_ms"] for cell in cells
                   if cell["cohort"] == "public1015" and cell["id"] == "mcp-token1024")
    disallowed = [row for row in adverse if row["metric"] in ("p50_ms", "p95_ms") and row["change_percent"] > 5 + 1e-9]
    resources, review, storage = [], [], []
    for cohort in COHORTS:
        for field in RESOURCE_FIELDS:
            by_label = {label: [nested(worker, field) for worker in report["workers"]
                               if worker["cohort"] == cohort and worker["label"] == label] for label in SOURCES}
            require(all(len(values) == 4 and all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                        for v in values) for values in by_label.values()), "Invalid resource samples: " + field)
            old, new = mean(by_label["baseline"]), mean(by_label["candidate"])
            change = 100 * (new / old - 1) if old else (0.0 if new == 0 else None)
            row = {"cohort": cohort, "metric": field, "baseline": numeric(by_label["baseline"]),
                   "candidate": numeric(by_label["candidate"]), "mean_change_percent": change}
            resources.append(row)
            if change is None or change > 10 + 1e-9:
                review.append(row)
        for phase in ("storage_after_ingestion_live", "storage_after_mcp_live", "storage_after_checkpoint"):
            by_label = {label: [nested(worker, phase + ".logical_db_bytes") for worker in report["workers"]
                               if worker["cohort"] == cohort and worker["label"] == label] for label in SOURCES}
            old, new = mean(by_label["baseline"]), mean(by_label["candidate"])
            storage.append({"cohort": cohort, "phase": phase, "baseline_bytes": numeric(by_label["baseline"]),
                "candidate_bytes": numeric(by_label["candidate"]), "mean_difference_bytes": new - old,
                "mean_change_percent": 100 * (new / old - 1) if old else None,
                "boundary": "SQLite logical page count times page size; not an index-only storage estimate."})
    numeric_pass = geometric_gain >= 10 - 1e-9 and best_public >= 15 - 1e-9 and mcp_gain >= 10 - 1e-9 and not disallowed
    computed_acceptance = {"accepted": numeric_pass and not review, "numeric_gate_passed": numeric_pass,
        "geometric_mean_p95_improvement_percent": geometric_gain,
        "best_public_native_token_p95_improvement_percent": best_public,
        "public_mcp_token1024_p95_improvement_percent": mcp_gain,
        "thresholds_percent": {key: value for key, value in THRESHOLDS.items() if key != "resource_mean_increase_review"},
        "regressions_above_five_percent": disallowed, "resource_comparisons": resources, "resource_review": review,
        "resource_rule": "Any increase above 10% requires an explicit cause and independent review; no automatic override."}
    close(report["acceptance"], computed_acceptance, "Acceptance")
    expected_validation = {"passed": True, "issues": [], "workers": 16, "expected_workers": 16,
                           "timed_calls": 56784, "expected_calls": 56784}
    require(report["validation"] == expected_validation, "Saved validation summary differs")
    summary_path = report_path.with_name(report_path.name.removesuffix(".json.gz") + ".summary.json")
    summary = json.loads(read(summary_path))
    expected_summary = {key: value for key, value in report.items() if key not in ("workers", "run")}
    expected_summary["run"] = {key: value for key, value in run.items() if key != "cohorts"}
    expected_summary["run"]["cohorts"] = {name: {key: value for key, value in cohort.items() if not key.startswith("query_ids")}
                                         for name, cohort in run["cohorts"].items()}
    expected_summary["workers"] = [{key: value for key, value in worker.items() if key != "configurations"}
                                   for worker in report["workers"]]
    expected_summary.update(full_report_sha256=sha(raw), compressed_report_sha256=sha(compressed))
    require(summary == expected_summary, "Saved summary does not match the complete original report")
    return {"schema_version": 1, "status": "verified_saved_measurements", "audit_passed": True,
        "created_at": datetime.now(timezone.utc).isoformat(), "retrieval_calls_executed": 0,
        "models_or_tokenizers_executed": 0, "tests_or_timing_runs_executed": 0,
        "sources": SOURCES, "source_git_hashes_independently_verified": True,
        "evaluator_commit": binding["evaluator_commit"], "evaluator_files_verified": len(binding["evaluator_files"]),
        "binding_sha256": run["binding_sha256"], "plan_sha256": run["plan_sha256"],
        "continuation_provenance": continuation,
        "native_token_count_memo_audit": native_memo_observations,
        "full_report_sha256": sha(raw), "compressed_report_sha256": sha(compressed),
        "audit_script_sha256": sha(Path(__file__).read_bytes()),
        "counts": {"workers": 16, "cells": 12, "timed_calls": calls, "ledger_events": event_count,
            "baseline_candidate_pairs": len(paired), "unique_query_configuration_pairs": len(canonical_rows),
            "native_mcp_provenance_pairs": native_mcp_pairs, "complete_output_differences": 0,
            "recorded_invariant_failures": 0, "negative_timing_samples": negative_timings,
            "zero_timing_samples": zero_timings, "nonfinite_or_invalid_timing_samples": invalid_timings},
        "cells": cells, "acceptance_recomputed": computed_acceptance,
        "resource_review_required": bool(review), "logical_storage": storage,
        "all_pooled_adverse_latency_metrics": adverse, "all_per_round_adverse_latency_metrics": per_round_adverse,
        "source_and_index_records": source_payloads, "saved_file_checksums": files,
        "sample_retention": "All 16 workers, all 56,784 calls and 113,568 start/finish events were checked in original order. No sample, round, adverse value or failed gate was dropped; no measurement was repeated.",
        "limitations": ["Independent arithmetic and digest/ledger/provenance audit of saved measurements; source text, tokenization and returned payload bodies are not rerun.",
            "The hashes compare complete stored non-timing responses and recorded invariant fields; this is not a new retrieval-quality evaluation.",
            "One host and old regression queries; no statistical-significance, new-domain or whole-product competitor-speed claim.",
            "Native memo snapshots include each retained first query and natural reuse across later native configurations. No query is added or omitted. They do not establish MCP memo hit rates or a whole-process 2 MiB memory limit.",
            "A resource-review flag remains a release decision requiring explicit evidence assessment, not an automatic waiver."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require_frozen_source()  # Refuse before creating even a failed-audit output while blocked.
    require(not args.output.exists(), "Preserve prior audit; use a new output path")
    try:
        result = audit(args.report, args.state_dir or args.report.parent)
    except Exception as error:
        result = {"schema_version": 1, "audit_passed": False, "status": "audit_failed",
            "error_type": type(error).__name__, "error": str(error),
            "report": str(args.report), "retrieval_calls_executed": 0,
            "audit_script_sha256": sha(Path(__file__).read_bytes())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items()
                     if key in ("status", "audit_passed", "counts", "resource_review_required", "error")}))
    return 0 if result["audit_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
