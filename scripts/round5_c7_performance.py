"""Blocked C7 formal scaffold; preserve every rejected C3/C5/C6 run and C4 development evidence.

The frozen round-four measurement primitives are reused without changing their
bytes. This new controller binds new sources, retains every ABBA sample and
refuses to overwrite or repeat an existing binding claim or worker attempt.
No retrieval is performed by --bind, --audit, or the unit tests.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round4_performance as previous
from scripts.round4_performance import (CONFIGURATIONS, PACKAGES, ENCODINGS,
    Ledger, TokenCounter, atomic, dataset, digest, dump, exclusive,
    exclusive_bytes, git, host_identity, indexed_content, json_bytes,
    latency_summary, make_row, mcp_configuration, now, original_turn_texts,
    query_order, require, rss, schedule, sha, source_identity, stable_row,
    storage, verify_worker)
from benchmarks.resume import _lock

VERSION = "round5-c7-default-performance-1"
PLAN = ROOT / "benchmarks/experiments/round5-plan.json"
BASELINE = {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
            "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"}
C4_TOOLS = (*previous.HELPERS, "scripts/round4_performance.py",
         "scripts/round5_performance.py", "tests/test_round5_performance.py",
         "tests/test_round5_recall_work.py", "tests/test_round5_covering_index.py",
         "benchmarks/experiments/round5-index-addendum.json",
         "benchmarks/experiments/round5-cache-addendum.json",
         ".github/workflows/round5-performance.yml",
         "scripts/round5_c4_performance.py", "tests/test_round5_c4_performance.py",
         "tests/test_round5_candidate_c4.py", ".github/workflows/round5-c4-performance.yml",
         "benchmarks/experiments/round5-c4-addendum.json",
         "benchmarks/experiments/round5-performance-binding.json",
         "benchmarks/reports/round5-performance-43547085915-1/report.summary.json")
C5_TOOLS = (*C4_TOOLS, "scripts/round5_c4_development_pair.py",
         "scripts/audit_round5_c4_performance.py",
         "benchmarks/experiments/round5-c4-development-plan.json",
         "benchmarks/reports/round5-development/candidate-c4-full/summary.json",
         "scripts/round5_c5_performance.py", "scripts/round5_c5_development_pair.py",
         "tests/test_round5_c5_performance.py", "tests/test_round5_candidate_c5.py",
         ".github/workflows/round5-c5-performance.yml",
         "benchmarks/experiments/round5-c5-addendum.json",
         "benchmarks/experiments/round5-c5-development-plan.json",
         "benchmarks/reports/round5-development/c5-preregistration/capacity-extension.json")
C6_TOOLS = (*C5_TOOLS, "scripts/round5_c6_performance.py", "scripts/round5_c6_development_pair.py",
         "tests/test_round5_c6_performance.py",
         ".github/workflows/round5-c6-performance.yml", "tests/test_round5_candidate_c6.py",
         "benchmarks/experiments/round5-c6-addendum.json",
         "benchmarks/experiments/round5-c6-development-plan.json",
         "benchmarks/experiments/round5-c5-performance-binding.json",
         "benchmarks/reports/round5-c5-performance-43552372788-1/report.summary.json")


TOOLS = (*C6_TOOLS, "scripts/round5_c7_performance.py", "scripts/round5_c7_development_pair.py",
         "tests/test_round5_c7_performance.py", "tests/test_round5_candidate_c7.py",
         ".github/workflows/round5-c7-performance.yml",
         "benchmarks/experiments/round5-c7-addendum.json",
         "benchmarks/experiments/round5-c7-development-plan.json",
         "benchmarks/experiments/round5-c6-performance-binding.json",
         "benchmarks/reports/round5-c6-performance-43557136276-1/report.summary.json")


CONTINUATION_PATH = "benchmarks/experiments/round5-c7-addendum.json"
CONTINUATION_COMMIT = '718ce3bbe42e23774e616219bd8ae60d143fb76f'
CONTINUATION_SHA256 = '7dc67e10049bf28ffc57060432442a0bdc371da2cc95506bf373e8381d50afeb'
CONTINUATION_PROTOCOL = 'v033-c7-mcp-stdout-write-flush-continuation-v1'
CONTINUATION_STATUS = 'registered-before-c7-implementation-and-timing'
C6_SOURCE = {"commit": "1bd97221e31e8e975498ece00f4bbfb3e0426aac",
             "runtime_sha256": "cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78"}
C3_BINDING_PATH = "benchmarks/experiments/round5-performance-binding.json"
C3_BINDING_SHA256 = "790ca15f3fbe2a5ba19fe08f83ab663bdb313a8569bfb1ee7677456ca4817c40"
C3_SUMMARY_PATH = "benchmarks/reports/round5-performance-43547085915-1/report.summary.json"
C3_SUMMARY_SHA256 = "5103a9d5bf26451e6eed2425c75c21663eedc51cc7d8462446373d9fcdd2b321"
C3_SOURCE = {"commit": "1c9a6d3f611608e8dbce8e729fdd3099513d80e6",
             "runtime_sha256": "7a927601b5ce710059d5a2640b3642c58a2bd4985d9ccdc48f69159938ee3623"}
C4_SOURCE = {"commit": "0141adf1dde6cd69cf96d8eea23f4b6ebab36477",
             "runtime_sha256": "1c7c644c5187332e6fb5034fef0e232b5c1ae1e5f352b53fea90f7fd8acc4fb3"}
C4_ARCHIVE_COMMIT = "e439c226cc2d422b44007dedd25aa750a62f88a9"
C4_SUMMARY_PATH = "benchmarks/reports/round5-development/candidate-c4-full/summary.json"
C4_SUMMARY_SHA256 = "c53fcd0c379888b91da3a46ed609ad50df07a0661dc21bc0701bda04b3d56d38"
C5_SOURCE = {"commit": "8dc6604fa32df18d53286110b215fc6657243656",
             "runtime_sha256": "6af876ef5ddc851f4fff56ba3dc4f20e76b2cfc9f5e31d0cc8d1a0ec20e954be"}
C5_BINDING_PATH = "benchmarks/experiments/round5-c5-performance-binding.json"
C5_BINDING_SHA256 = "bd395da21848cc01656ab45bc211a388b43b4ae63edb8690b2eabe2958d3781a"
C5_SUMMARY_PATH = "benchmarks/reports/round5-c5-performance-43552372788-1/report.summary.json"
C5_SUMMARY_SHA256 = "930a28c40913b2eea3e38b7ce5bc04e673e288396fccb67bf16e59d42e996f25"
C5_RESULT_COMMIT = "3982ceab2bdce0e9a189135ce261445a3a38d779"
DEVELOPMENT_PLAN_PATH = "benchmarks/experiments/round5-c7-development-plan.json"
DEVELOPMENT_PLAN_SHA256 = 'b6b61348a178cabbc4f787eb8ccd18ebdbeeb11cd18f6f82149b098c1057593c'
DEVELOPMENT_CALLS = 18928
DEVELOPMENT_PAIRS = 9464
DEVELOPMENT_ROUNDS = 2
DEVELOPMENT_ORDER = [["baseline", "candidate"], ["candidate", "baseline"]]
C6_BINDING_PATH = "benchmarks/experiments/round5-c6-performance-binding.json"
C6_BINDING_SHA256 = "2b57caea5b3d7f12b38aba9472d798e846a5231b936551784f0963259e2a715a"
C6_SUMMARY_PATH = "benchmarks/reports/round5-c6-performance-43557136276-1/report.summary.json"
C6_SUMMARY_SHA256 = "f05d011e3477eee69953ab3a5097e3d69f5657c12c6692d4d96af4f87cb6ad9e"
C6_RESULT_COMMIT = "c6b384778e12ce9c72771911af37bbb2c5d3474f"
C7_SOURCE = {"commit": None, "runtime_sha256": None}
C7_POLICY_KEY = 'mcp_stdout_policy'
C7_POLICY = {'sdk_version': '1.30.0',
 'scope': 'serve standard stdio path with verified original SDK methods and a native standard stdout '
          'stream',
 'serialization': 'unchanged official SDK JSONRPCMessage.model_dump_json and newline',
 'encoding': 'same owned native UTF-8 TextIOWrapper over the standard stdout binary buffer',
 'write_and_flush': 'one default anyio.to_thread.run_sync operation calls the original native '
                    'write(data), then flush(), in that order',
 'flush_frequency': 'every successful message is flushed immediately; no batching across responses',
 'followup_flush': 'skip only the immediately following SDK flush already completed successfully by '
                   'that write; standalone flush and a flush after failed write/flush delegate normally',
 'cross_message_text_buffer': False,
 'thread_cancellation': 'preserve default non-abandoning worker behavior; propagate write and flush '
                        'errors; do not change limiters or cancellation options',
 'lifecycle': 'official stdio_server(stdout=adapter), unchanged lowlevel server '
              'initialization/lifespan/context/handlers; no explicit closing of standard process '
              'handles',
 'fallback': 'unknown SDK version, replaced or custom SDK method, unsupported standard-stream identity '
             'or custom stdout uses the original FastMCP.run(transport=stdio) path',
 'unchanged': ['CLI command and arguments',
               'stdin reader',
               'client SDK',
               'tool schema and instructions',
               'JSON framing and response fields',
               'retrieval and source validation',
               'ranking and exact token budgets',
               'normal result-cache lookup/write/revision checks/pruning/transactions',
               'C6 request-local source work',
               'C5 bounded exact-count memo and cold/warm policy',
               'dependencies and database schema']}
C7_BINDING_PATH = "benchmarks/experiments/round5-c7-performance-binding.json"
MEMO_FIELDS = ("allocated", "entry_limit", "text_byte_limit", "entries", "text_bytes",
               "hits", "misses", "evictions", "invalidations", "oversized_bypasses", "uncertified_bypasses")
MEMO_COUNTERS = ("hits", "misses", "evictions", "invalidations", "oversized_bypasses", "uncertified_bypasses")
MEMO_BASELINE = {"available": False, "reason": "published-v0.3.2-has-no-derived-token-count-memo"}


def require_registered_source():
    require(isinstance(CONTINUATION_COMMIT, str)
            and re.fullmatch(r"[0-9a-f]{40}", CONTINUATION_COMMIT) is not None
            and isinstance(CONTINUATION_SHA256, str)
            and re.fullmatch(r"[0-9a-f]{64}", CONTINUATION_SHA256) is not None
            and isinstance(CONTINUATION_PROTOCOL, str) and bool(CONTINUATION_PROTOCOL)
            and isinstance(CONTINUATION_STATUS, str) and bool(CONTINUATION_STATUS)
            and isinstance(DEVELOPMENT_PLAN_SHA256, str)
            and re.fullmatch(r"[0-9a-f]{64}", DEVELOPMENT_PLAN_SHA256) is not None
            and all(type(value) is int and value > 0 for value in
                    (DEVELOPMENT_CALLS, DEVELOPMENT_PAIRS, DEVELOPMENT_ROUNDS))
            and isinstance(DEVELOPMENT_ORDER, list)
            and isinstance(C7_POLICY_KEY, str) and bool(C7_POLICY_KEY)
            and isinstance(C7_POLICY, dict) and bool(C7_POLICY)
            and isinstance(C7_SOURCE["commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", C7_SOURCE["commit"]) is not None
            and isinstance(C7_SOURCE["runtime_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", C7_SOURCE["runtime_sha256"]) is not None,
            "C7 is blocked until its substantive source and exact preregistration/development plan are frozen")
    require(C7_SOURCE["runtime_sha256"] not in {source["runtime_sha256"]
            for source in (BASELINE, C3_SOURCE, C4_SOURCE, C5_SOURCE, C6_SOURCE)},
            "C7 must not replay a prior baseline/C3/C4/C5/C6 runtime")


def rejected_c5_registration():
    """Preserve C5's complete, valid run and its single failed MCP numerical gate."""
    prior_raw = (ROOT / C5_BINDING_PATH).read_bytes()
    summary_raw = (ROOT / C5_SUMMARY_PATH).read_bytes()
    require(sha(prior_raw) == C5_BINDING_SHA256 and sha(summary_raw) == C5_SUMMARY_SHA256
            and summary_raw == git("show", C5_RESULT_COMMIT + ":" + C5_SUMMARY_PATH),
            "Original C5 binding or committed rejected summary bytes changed")
    prior, summary = json.loads(prior_raw), json.loads(summary_raw)
    require(prior["evaluator"] == summary["evaluator"] == summary["run"]["evaluator"]
                == "round5-c5-default-performance-1"
            and prior["sources"] == {"baseline": BASELINE, "candidate": C5_SOURCE}
            and prior["status"] == "frozen-before-formal-timing"
            and prior["packages"] == PACKAGES and prior["plan_sha256"] == sha(PLAN.read_bytes())
            and summary["run"]["binding"] == prior
            and summary["run"]["binding_sha256"] == C5_BINDING_SHA256
            and summary["status"] == "measurements_completed" and summary["error"] is None
            and summary["evaluator_unchanged"] is True
            and summary["validation"] == {"passed": True, "issues": [], "workers": 16,
                "expected_workers": 16, "timed_calls": 56784, "expected_calls": 56784}
            and summary["run"]["publication"] == {
                "run_id": "43552372788", "run_attempt": "1",
                "branch": "validation/v033-round5-c5-performance-43552372788-1",
                "claim_branch": "validation/v033-round5-c5-claim-" + C5_BINDING_SHA256},
            "The retained C5 run must remain complete and bound to its original source")
    accepted = summary["acceptance"]
    require(accepted["accepted"] is False and accepted["numeric_gate_passed"] is False
            and accepted["geometric_mean_p95_improvement_percent"] == 15.220791446446002
            and accepted["best_public_native_token_p95_improvement_percent"] == 15.422173278138885
            and accepted["public_mcp_token1024_p95_improvement_percent"] == 6.673181339995871
            and accepted["regressions_above_five_percent"] == [] and accepted["resource_review"] == [],
            "C5's failed actual-MCP numerical gate must not be relabeled as acceptance")
    require(set(prior["evaluator_files"]) == set(C5_TOOLS), "The exact frozen C5 evaluator input set differs")
    for name, expected in prior["evaluator_files"].items():
        require(sha((ROOT / name).read_bytes()) == expected, "A frozen C5 evaluator file changed: " + name)
    return {"rejected_c5_binding_sha256": C5_BINDING_SHA256,
            "rejected_c5_summary_sha256": C5_SUMMARY_SHA256,
            "rejected_c5_result_commit": C5_RESULT_COMMIT,
            "frozen_c5_evaluator_files": prior["evaluator_files"]}


def check_c6_registered_scope(document):
    """Keep source-work reuse local and retain the original complete C5 rejection."""
    require(document["source_work_policy"] == {
        "ownership": "one recall and its original read snapshot only",
        "maximum_batch_pairs": 400,
        "maximum_batch_parameters": 800,
        "sqlite_statement_cache": "unchanged ordinary driver default 128; no enlargement",
        "source_validation": "unchanged full source-map and projected-unit checks",
        "cold_warm_boundary": "unchanged C5 connection/configuration/query-order boundaries and all first calls; no extra warmup",
    } and document["cache_policy"]["continuation"] ==
        "C6 retains the exact C5 token memo. No additional persistent feature or statement cache is introduced.",
        "C6 must retain bounded in-snapshot source work without an additional persistent cache")
    recorded_c5 = document["rejected_c5"]
    require({key: recorded_c5[key] for key in C5_SOURCE} == C5_SOURCE
            and recorded_c5["formal_run"] == "43552372788-1"
            and recorded_c5["result_commit"] == C5_RESULT_COMMIT
            and recorded_c5["binding_sha256"] == C5_BINDING_SHA256
            and recorded_c5["summary_sha256"] == C5_SUMMARY_SHA256
            and recorded_c5["aggregate_p95_gain_percent"] == 15.220791446446002
            and recorded_c5["public_native_best_gain_percent"] == 15.422173278138885
            and recorded_c5["public_mcp_token1024_gain_percent"] == 6.673181339995871
            and recorded_c5["numeric_gate_passed"] is False
            and recorded_c5["accepted"] is False
            and recorded_c5["decision"] ==
                "Preserve the complete valid C5 formal rejection. Do not rerun the same source to select a faster sample.",
            "C6 preregistration must preserve the full rejected C5 identity and original false decision")


def rejected_c6_registration():
    """Preserve C6's complete, valid run and its single failed MCP numerical gate."""
    prior_raw = (ROOT / C6_BINDING_PATH).read_bytes()
    summary_raw = (ROOT / C6_SUMMARY_PATH).read_bytes()
    require(sha(prior_raw) == C6_BINDING_SHA256 and sha(summary_raw) == C6_SUMMARY_SHA256
            and summary_raw == git("show", C6_RESULT_COMMIT + ":" + C6_SUMMARY_PATH),
            "Original C6 binding or committed rejected summary bytes changed")
    prior, summary = json.loads(prior_raw), json.loads(summary_raw)
    require(prior["evaluator"] == summary["evaluator"] == summary["run"]["evaluator"]
                == "round5-c6-default-performance-1"
            and prior["sources"] == {"baseline": BASELINE, "candidate": C6_SOURCE}
            and prior["status"] == "frozen-before-formal-timing"
            and prior["packages"] == PACKAGES and prior["plan_sha256"] == sha(PLAN.read_bytes())
            and summary["run"]["binding"] == prior
            and summary["run"]["binding_sha256"] == C6_BINDING_SHA256
            and summary["status"] == "measurements_completed" and summary["error"] is None
            and summary["evaluator_unchanged"] is True
            and summary["validation"] == {"passed": True, "issues": [], "workers": 16,
                "expected_workers": 16, "timed_calls": 56784, "expected_calls": 56784}
            and summary["run"]["publication"] == {
                "run_id": "43557136276", "run_attempt": "1",
                "branch": "validation/v033-round5-c6-performance-43557136276-1",
                "claim_branch": "validation/v033-round5-c6-claim-" + C6_BINDING_SHA256},
            "The retained C6 run must remain complete and bound to its original source")
    check_c6_registered_scope(prior["continuation_registration"]["document"])
    accepted = summary["acceptance"]
    require(accepted["accepted"] is False and accepted["numeric_gate_passed"] is False
            and accepted["geometric_mean_p95_improvement_percent"] == 14.91917268891384
            and accepted["best_public_native_token_p95_improvement_percent"] == 16.286785133390612
            and accepted["public_mcp_token1024_p95_improvement_percent"] == 5.7989107559001996
            and accepted["regressions_above_five_percent"] == [] and accepted["resource_review"] == [],
            "C6's failed actual-MCP numerical gate must not be relabeled as acceptance")
    require(set(prior["evaluator_files"]) == set(C6_TOOLS), "The exact frozen C6 evaluator input set differs")
    for name, expected in prior["evaluator_files"].items():
        require(sha((ROOT / name).read_bytes()) == expected, "A frozen C6 evaluator file changed: " + name)
    return {"rejected_c6_binding_sha256": C6_BINDING_SHA256,
            "rejected_c6_summary_sha256": C6_SUMMARY_SHA256,
            "rejected_c6_result_commit": C6_RESULT_COMMIT,
            "frozen_c6_evaluator_files": prior["evaluator_files"]}


def check_c7_registered_scope(document):
    """Do not invent the future transport policy before its preregistration."""
    require(isinstance(C7_POLICY_KEY, str) and bool(C7_POLICY_KEY)
            and isinstance(C7_POLICY, dict) and bool(C7_POLICY),
            "C7 transport policy is blocked until its exact preregistration is frozen")
    require(document.get(C7_POLICY_KEY) == C7_POLICY, "C7 registered transport policy changed")
    check_c6_registered_scope(document)
    prior = document["rejected_c6"]
    require({key: prior[key] for key in C6_SOURCE} == C6_SOURCE
            and prior["formal_run"] == "43557136276-1"
            and prior["result_commit"] == C6_RESULT_COMMIT
            and prior["binding_sha256"] == C6_BINDING_SHA256
            and prior["summary_sha256"] == C6_SUMMARY_SHA256
            and prior["aggregate_p95_gain_percent"] == 14.91917268891384
            and prior["public_native_best_gain_percent"] == 16.286785133390612
            and prior["public_mcp_token1024_gain_percent"] == 5.7989107559001996
            and prior["numeric_gate_passed"] is False and prior["accepted"] is False
            and prior["decision"] ==
                "Preserve the complete valid C6 formal rejection. Do not rerun the same source to select a faster sample.",
            "C7 must preserve the original complete C6 source and numerical rejection")


def continuation_registration():
    """Remain blocked until C7 is registered, preserving every earlier outcome."""
    require_registered_source()
    raw = (ROOT / CONTINUATION_PATH).read_bytes()
    require(sha(raw) == CONTINUATION_SHA256
            and raw == git("show", CONTINUATION_COMMIT + ":" + CONTINUATION_PATH),
            "C7 preregistration bytes or commit differ")
    document = json.loads(raw)
    plan = load_plan()
    require(document["protocol"] == CONTINUATION_PROTOCOL
            and document["status"] == CONTINUATION_STATUS
            and document["baseline"] == plan["baseline"], "C7 preregistration identity differs")
    rejected = document["rejected_c3"]
    require({key: rejected[key] for key in C3_SOURCE} == C3_SOURCE
            and rejected["formal_run"] == "43547085915-1"
            and rejected["result_commit"] == "e0c30deb7cdae18bb19c83534646630dfb3f673b",
            "Rejected C3 source/result identity differs")
    formal = document["formal_protocol"]
    require(formal["matrix_plan"] == "benchmarks/experiments/round5-plan.json"
            and formal["calls"] == 56784 and formal["rounds"] == 4
            and formal["order"] == ["AB", "BA", "BA", "AB"]
            and formal["thresholds_percent"] == plan["thresholds_percent"],
            "C7 must preserve the original complete matrix and all numerical gates")
    policy = document["cache_policy"]
    require(policy["kind"] == "derived-exact-token-count-only" and policy["entry_limit"] == 2048
            and policy["retained_text_object_byte_limit"] == 2097152
            and policy["ownership"] == "one MemoryBook connection; both encoders share limits",
            "The registered per-book text-only memo limits changed")
    check_c7_registered_scope(document)
    development_raw = (ROOT / DEVELOPMENT_PLAN_PATH).read_bytes()
    require(sha(development_raw) == DEVELOPMENT_PLAN_SHA256
            and development_raw == git("show", CONTINUATION_COMMIT + ":" + DEVELOPMENT_PLAN_PATH),
            "C7 development plan changed after registration")
    development = json.loads(development_raw)
    require(document["development_protocol"]["plan"] == DEVELOPMENT_PLAN_PATH
            and development["calls"] == DEVELOPMENT_CALLS
            and development["version_pairs"] == DEVELOPMENT_PAIRS
            and development["rounds"] == DEVELOPMENT_ROUNDS
            and development["engine_order"] == DEVELOPMENT_ORDER,
            "C7 registered development matrix changed")
    prior_raw = (ROOT / C3_BINDING_PATH).read_bytes()
    result_raw = (ROOT / C3_SUMMARY_PATH).read_bytes()
    require(sha(prior_raw) == C3_BINDING_SHA256 and sha(result_raw) == C3_SUMMARY_SHA256,
            "Original C3 binding or failed summary bytes changed")
    prior, result = json.loads(prior_raw), json.loads(result_raw)
    require(prior["evaluator"] == "round5-default-performance-1"
            and prior["sources"] == {"baseline": BASELINE, "candidate": C3_SOURCE}
            and result["run"]["binding"] == prior
            and result["run"]["binding_sha256"] == C3_BINDING_SHA256
            and result["status"] == "measurements_completed" and result["error"] is None
            and result["validation"]["passed"] is True
            and result["validation"]["timed_calls"] == 56784
            and result["acceptance"]["numeric_gate_passed"] is False
            and result["acceptance"]["accepted"] is False,
            "The retained C3 experiment must remain complete and numerically rejected")
    for name, expected in prior["evaluator_files"].items():
        require(sha((ROOT / name).read_bytes()) == expected,
                "A frozen C3 evaluator file changed: " + name)
    c4_raw = (ROOT / C4_SUMMARY_PATH).read_bytes()
    require(sha(c4_raw) == C4_SUMMARY_SHA256
            and c4_raw == git("show", C4_ARCHIVE_COMMIT + ":" + C4_SUMMARY_PATH),
            "Original complete C4 development summary changed")
    c4 = json.loads(c4_raw)
    recorded_c4 = document["prior_c4"]
    require({key: recorded_c4[key] for key in C4_SOURCE} == C4_SOURCE
            and recorded_c4["development_report"] == C4_SUMMARY_PATH
            and recorded_c4["development_archive_commit"] == C4_ARCHIVE_COMMIT
            and recorded_c4["calls"] == c4["total_calls"] == 18928
            and recorded_c4["version_pairs"] == c4["complete_payload_pairs"] == 9464
            and c4["status"] == "completed" and c4["payload_mismatches"] == []
            and c4["all_invariants_passed"] is True
            and c4["candidate_source_commit"] == C4_SOURCE["commit"]
            and c4["candidate_runtime_sha256"] == C4_SOURCE["runtime_sha256"],
            "Retain the full C4 development result without treating it as formal acceptance")
    frozen_c4 = {name: sha(git("show", C4_ARCHIVE_COMMIT + ":" + name)) for name in C4_TOOLS}
    for name, expected in frozen_c4.items():
        require(sha((ROOT / name).read_bytes()) == expected, "A retained C4 evaluator file changed: " + name)
    c5 = rejected_c5_registration()
    c6 = rejected_c6_registration()
    return {"path": CONTINUATION_PATH, "commit": CONTINUATION_COMMIT,
            "sha256": CONTINUATION_SHA256, "document": document,
            "rejected_c3_binding_sha256": C3_BINDING_SHA256,
            "rejected_c3_summary_sha256": C3_SUMMARY_SHA256,
            "frozen_c3_evaluator_files": prior["evaluator_files"],
            "prior_c4_summary_sha256": C4_SUMMARY_SHA256, "prior_c4_archive_commit": C4_ARCHIVE_COMMIT,
            "frozen_c4_evaluator_files": frozen_c4, "development_plan_sha256": DEVELOPMENT_PLAN_SHA256,
            **c5, **c6}


def memo_diagnostics():
    return {"entry_limit": 2048, "text_byte_limit": 2097152,
        "boundary": "Read-only native snapshots outside timing. Same book retains exact token counts across native configurations; actual MCP uses fresh server processes and measured RSS without private memo counters.",
        "configurations": []}


def check_memo_snapshot(snapshot, label):
    if label == "baseline":
        require(snapshot == MEMO_BASELINE, "Baseline must disclose that its token-count memo is unavailable")
        return
    require(label == "candidate" and snapshot.get("available") is True
            and set(snapshot) == {"available", *MEMO_FIELDS}, "Missing candidate native memo diagnostics")
    require(all(type(snapshot[name]) is int and snapshot[name] >= 0 for name in MEMO_FIELDS),
            "Native memo diagnostics must be nonnegative integers")
    require(snapshot["allocated"] in (0, 1) and snapshot["entry_limit"] == 2048
            and snapshot["text_byte_limit"] == 2097152
            and snapshot["entries"] <= 2048 and snapshot["text_bytes"] <= 2097152,
            "Native token-count memo exceeded its registered bounds")
    dynamic = [name for name in MEMO_FIELDS if name not in ("entry_limit", "text_byte_limit")]
    require(snapshot["allocated"] == 1 or all(snapshot[name] == 0 for name in dynamic),
            "An unallocated native memo must be empty")


def native_memo_snapshot(book, label):
    if label == "baseline":
        return dict(MEMO_BASELINE)
    method = getattr(book, "_token_memo_snapshot", None)
    require(callable(method), "C5 candidate is missing its read-only native memo observation API")
    snapshot = {"available": True, **method()}
    check_memo_snapshot(snapshot, label)
    return snapshot


def verify_native_memo(report, configurations):
    diagnostics = report["native_token_count_memo"]
    require(diagnostics["entry_limit"] == 2048 and diagnostics["text_byte_limit"] == 2097152,
            "Native memo observation limits differ")
    native = [c for c in configurations if c["surface"] == "native"]
    observed = diagnostics["configurations"]
    require([c["id"] for c in native] == [c["id"] for c in CONFIGURATIONS if c["surface"] == "native"]
            and [c["id"] for c in observed] == [c["id"] for c in native],
            "Native memo configuration order differs")
    previous_snapshot = None
    for config, record in zip(native, observed, strict=True):
        require(record["first_query_id"] == config["rows"][0]["query_id"],
                "Native memo first-call observation differs from the saved query order")
        snapshots = [record[key] for key in ("before", "after_first_call", "after")]
        for snapshot in snapshots:
            check_memo_snapshot(snapshot, report["label"])
        require(previous_snapshot is None or snapshots[0] == previous_snapshot,
                "Native memo was changed between configurations")
        if report["label"] == "candidate":
            if previous_snapshot is None:
                require(snapshots[0]["allocated"] == 0, "Fresh native book must start with an empty unallocated memo")
            if config["id"] == "native-char4000":
                require(snapshots[0] == snapshots[1] == snapshots[2], "Character recalls unexpectedly warmed the native memo")
            for before, after in zip(snapshots, snapshots[1:]):
                require(after["allocated"] >= before["allocated"]
                        and all(after[name] >= before[name] for name in MEMO_COUNTERS),
                        "Native memo cumulative counters decreased")
        previous_snapshot = snapshots[-1]


def file_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in TOOLS}


def load_plan():
    plan = json.loads(PLAN.read_bytes())
    require(plan["protocol"] == "v033-exact-output-performance-v1"
            and plan["baseline"] == {"release": "v0.3.2", **BASELINE},
            "Round-five baseline or protocol changed")
    formal = plan["performance_candidate"]["formal"]
    require(formal["rounds"] == 4 and formal["calls"] == 56784
            and formal["engine_order"] == [["baseline", "candidate"],
                ["candidate", "baseline"], ["candidate", "baseline"], ["baseline", "candidate"]]
            and formal["cohorts"] == ["synthetic61", "public1015"]
            and formal["configs"] == list(CONFIGURATIONS),
            "Registered ABBA matrix changed")
    require(plan["thresholds_percent"] == {
        "geometric_mean_p95_improvement": 10,
        "at_least_one_public_native_token_p95_improvement": 15,
        "public_mcp_token1024_p95_improvement": 10,
        "maximum_pooled_p50_p95_regression": 5,
        "resource_mean_increase_review": 10}, "Registered gates changed")
    return plan


def bind(args):
    require(args.bind.resolve() == (ROOT / C7_BINDING_PATH).resolve(),
            "Use the new C7 binding path; never replace original C3/C4/C5/C6 evidence")
    require_registered_source()
    plan = load_plan()
    continuation = continuation_registration()
    require(args.baseline_src and args.candidate_src, "Both source checkouts are required")
    sources = {label: source_identity(path) for label, path in
               (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == BASELINE, "Use the published v0.3.2 tag as baseline")
    require(sources["candidate"]["runtime_sha256"] not in
            (BASELINE["runtime_sha256"], C3_SOURCE["runtime_sha256"], C4_SOURCE["runtime_sha256"], C5_SOURCE["runtime_sha256"], C6_SOURCE["runtime_sha256"]),
            "C7 requires a materially changed source; do not replay any prior runtime")
    require(sources["candidate"] == C7_SOURCE, "Use only the frozen substantive C7 source")
    commit = git("rev-parse", "HEAD").decode().strip()
    hashes = file_hashes()
    for path, expected in {**hashes, str(PLAN.relative_to(ROOT)): sha(PLAN.read_bytes())}.items():
        require(sha(git("show", commit + ":" + path)) == expected,
                "Commit the exact plan, evaluator and tests before binding: " + path)
    for path in (*previous.HELPERS, "scripts/round4_performance.py"):
        require(sha(git("show", BASELINE["commit"] + ":" + path)) == hashes[path],
                "Historical measurement helper differs from v0.3.2: " + path)
    value = {"schema_version": 1, "evaluator": VERSION,
        "status": "frozen-before-formal-timing", "created_at": now(),
        "plan_sha256": sha(PLAN.read_bytes()), "sources": sources,
        "continuation_registration": continuation,
        "evaluator_commit": commit, "evaluator_files": hashes, "packages": PACKAGES,
        "policy": "One exclusive execution claim per binding; preserve every attempt and sample."}
    exclusive(args.bind, value)
    print(json.dumps({"binding": str(args.bind), "sha256": sha(args.bind.read_bytes()),
                      "next": "Commit this binding, then run the single formal comparison."}))


def load_binding(path):
    require(path.resolve() == (ROOT / C7_BINDING_PATH).resolve(),
            "Use only the separately committed C7 binding")
    require_registered_source()
    value = json.loads(path.read_bytes())
    require(value.get("continuation_registration") == continuation_registration(),
            "C7 binding continuation provenance differs")
    require(value["sources"]["candidate"]["runtime_sha256"] not in
            (BASELINE["runtime_sha256"], C3_SOURCE["runtime_sha256"], C4_SOURCE["runtime_sha256"], C5_SOURCE["runtime_sha256"], C6_SOURCE["runtime_sha256"]),
            "C7 cannot replay the original baseline or prior C3/C4/C5/C6 runtimes")
    require(value["sources"]["candidate"] == C7_SOURCE, "Bound C7 source differs from its fixed identity")
    require(value["evaluator"] == VERSION and value["status"] == "frozen-before-formal-timing",
            "Wrong round-five C7 binding")
    require(value["plan_sha256"] == sha(PLAN.read_bytes())
            and value["evaluator_files"] == file_hashes()
            and value["packages"] == PACKAGES and value["sources"]["baseline"] == BASELINE,
            "Bound plan, evaluators, packages or baseline changed")
    relative = path.resolve().relative_to(ROOT).as_posix()
    require(path.read_bytes() == git("show", "HEAD:" + relative),
            "Commit the exact binding before timing")
    for name, expected in value["evaluator_files"].items():
        require(sha(git("show", value["evaluator_commit"] + ":" + name)) == expected,
                "Evaluator provenance changed: " + name)
    return value


def execution_claim_path(binding):
    return binding.with_name(binding.name + ".execution.json")


def claim_execution(args, run):
    claim = {"schema_version": 1, "evaluator": VERSION, "created_at": now(),
             "binding_sha256": sha(args.binding.read_bytes()),
             "run_identity_sha256": digest(run), "host": run["host"],
             "state_dir": str(args.state_dir.resolve()), "output": str(args.output.resolve())}
    exclusive(execution_claim_path(args.binding), claim)
    return claim


class CheckpointPublicationError(RuntimeError):
    """Stop timing after any rejected or ambiguous Git checkpoint write."""


def publication_identity(args):
    if not getattr(args, "publish_branch", None):
        return None
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(re.fullmatch(r"[0-9]+", run_id) is not None and attempt == "1"
            and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/ci/v033-round5-c7-performance",
            "Publication requires the first-attempt registered hosted trigger")
    expected = "validation/v033-round5-c7-performance-" + run_id + "-" + attempt
    require(args.publish_branch == expected, "Unexpected validation branch")
    public = ROOT / ("benchmarks/reports/round5-c7-performance-" + run_id + "-" + attempt)
    require(args.output.resolve().parent == public.resolve(), "Unexpected public checkpoint directory")
    require(args.state_dir.resolve() != public.resolve(), "Keep mutable worker state separate from public checkpoints")
    require(args.state_dir.resolve() ==
            (ROOT / (".artifacts/round5-c7-performance-" + run_id + "-" + attempt)).resolve(),
            "Use the separate C7 worker state directory")
    require(args.binding.resolve() == (ROOT / C7_BINDING_PATH).resolve(),
            "Use the separate C7 binding for this execution claim")
    return {"run_id": run_id, "run_attempt": attempt, "branch": expected,
            "claim_branch": "validation/v033-round5-c7-claim-" + sha(args.binding.read_bytes())}


def export_checkpoint(args):
    """Publish immutable gzip ledgers; audit accepts them without raw duplication."""
    state, public = args.state_dir.resolve(), args.output.resolve().parent
    public.mkdir(parents=True, exist_ok=True)

    def preserve(destination, raw):
        if destination.exists():
            require(destination.is_file() and not destination.is_symlink()
                    and destination.read_bytes() == raw,
                    "Never replace an immutable exported artifact: " + str(destination))
        else:
            exclusive_bytes(destination, raw)

    if (state / "run.json").is_file():
        preserve(public / "run.json", (state / "run.json").read_bytes())
    if (state / "checkpoint.json").is_file():
        atomic(public / "checkpoint.json", json.loads((state / "checkpoint.json").read_bytes()))
    claim = execution_claim_path(args.binding)
    if claim.is_file():
        preserve(public / "execution.json", claim.read_bytes())
    for source in sorted((state / "workers").glob("*")):
        require(not source.is_symlink(), "Refuse symbolic checkpoint files")
        if source.is_file() and source.name.endswith((".started.json", ".json.gz", ".attempts.jsonl.gz")):
            preserve(public / "workers" / source.name, source.read_bytes())
        elif source.is_file() and source.name.endswith(".attempts.jsonl"):
            compressed = source.with_suffix(".jsonl.gz")
            if not compressed.exists():  # Preserve an abruptly interrupted call ledger verbatim.
                preserve(public / "workers" / compressed.name, gzip.compress(source.read_bytes(), mtime=0))


def publish_checkpoint(args, run, phase):
    publication = run.get("publication")
    if publication is None:
        return
    failure = args.output.resolve().parent / "publication-failure.json"
    require(not failure.exists(), "Prior checkpoint push failed; do not retry automatically")
    try:
        export_checkpoint(args)
        branch_ref = "refs/heads/" + publication["branch"]
        claim_ref = "refs/heads/" + publication["claim_branch"]
        head = git("rev-parse", "HEAD").decode().strip()
        remote = git("ls-remote", "--heads", "origin", branch_ref).decode().split()
        require(not remote or remote == [head, branch_ref], "Another writer advanced the result ref")
        public = args.output.resolve().parent.relative_to(ROOT).as_posix()
        claim = execution_claim_path(args.binding).resolve().relative_to(ROOT).as_posix()
        staged = git("diff", "--cached", "--name-only").decode().splitlines()
        require(all(path == claim or path.startswith(public + "/") for path in staged),
                "Unrelated staged changes must not enter a benchmark checkpoint")
        git("add", "--", public, claim)
        changed = git("diff", "--cached", "--name-only").decode().splitlines()
        require(changed and all(path == claim or path.startswith(public + "/") for path in changed),
                "Checkpoint is empty or includes an unrelated path")
        git("-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "bench: preserve round-five " + phase)
        if phase == "execution claimed":
            # Empty expected ref means create only. A simultaneous checkout or
            # later workflow cannot acquire this same binding a second time.
            git("push", "--force-with-lease=" + claim_ref + ":", "origin", "HEAD:" + claim_ref)
        git("push", "origin", "HEAD:" + branch_ref)
    except BaseException as error:
        if not failure.exists():
            exclusive(failure, {"phase": phase, "status": "publication-failed-no-automatic-retry",
                "error_type": type(error).__name__, "message": str(error), "at": now()})
        raise CheckpointPublicationError("Checkpoint publication failed; stopped before further timing") from error


def load_completed(state, item, run, plan):
    prefix = state / "workers" / item["key"]
    marker = json.loads(Path(str(prefix) + ".started.json").read_bytes())
    require(marker == {"worker": item, "run_identity_sha256": digest(run)}, "Worker start marker differs")
    value = json.loads(gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes()))
    ledger = gzip.decompress(Path(str(prefix) + ".attempts.jsonl.gz").read_bytes())
    raw = Path(str(prefix) + ".attempts.jsonl")
    if raw.exists():
        require(raw.read_bytes() == ledger, "Original and compressed attempt ledgers differ")
    verify_worker(value, run, plan, ledger=ledger)
    verify_native_memo(value, value["configurations"])
    return value


def worker(args, plan, binding):
    require_registered_source()
    require(binding.get("sources") == {"baseline": BASELINE, "candidate": C7_SOURCE},
            "C7 worker must use the exact registered sources")
    state = args.state_dir.resolve()
    run = json.loads((state / "run.json").read_bytes())
    claim = json.loads(execution_claim_path(args.binding).read_bytes())
    require(claim["binding_sha256"] == sha(args.binding.read_bytes())
            and claim["run_identity_sha256"] == digest(run)
            and claim["state_dir"] == str(state), "Worker has no exact execution claim")
    item = next(s for s in run["schedule"] if s["key"] == args.worker)
    require(run["binding_sha256"] == sha(args.binding.read_bytes()) and run["host"] == host_identity(),
            "Worker binding/host differs from controller")
    marker = state / "workers" / (item["key"] + ".started.json")
    require(json.loads(marker.read_bytes()) == {"worker": item, "run_identity_sha256": digest(run)},
            "Worker has no matching controller intent")
    output = state / "workers" / (item["key"] + ".json.gz")
    ledger_path = state / "workers" / (item["key"] + ".attempts.jsonl")
    require(not output.exists() and not ledger_path.exists(), "A worker attempt already exists; never repeat it")
    src = Path(run["source_paths"][item["label"]])
    expected = binding["sources"][item["label"]]
    require(source_identity(src) == expected, "Worker runtime source differs")
    sys.path.insert(0, str(src))
    begin = time.perf_counter_ns()
    import memory_book
    from memory_book import MemoryBook
    imported_ms = (time.perf_counter_ns() - begin) / 1e6
    require(Path(memory_book.__file__).parent.resolve() == (src / "memory_book").resolve(),
            "Worker imported a different runtime")
    data = dataset(plan, item["cohort"], args.locomo_path)
    ids = [case.id for case in data.queries]
    require(ids == run["cohorts"][item["cohort"]]["query_ids_original_order"], "Worker query identities differ")
    report = {**item, "status": "started", "started_at": now(), "source": expected,
        "run_identity_sha256": digest(run), "runtime_import_ms": imported_ms,
        "dataset_sha256": data.fingerprint, "configurations": [], "error": None,
        "native_token_count_memo": memo_diagnostics()}
    ledger = Ledger(ledger_path)
    try:
        with tempfile.TemporaryDirectory(prefix="round5-perf-") as temporary:
            work = Path(temporary)
            db_path = work / "memory.db"
            begin = time.perf_counter_ns()
            with MemoryBook(db_path, cache_size=0) as book:
                report["native_open_ms"] = (time.perf_counter_ns() - begin) / 1e6
                begin = time.perf_counter_ns()
                ingested = [book.ingest(session) for session in data.sessions]
                report["fresh_ingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["fresh_ingestion_results_sha256"] = digest(ingested)
                report["native_memory_after_ingestion"] = rss()
                report["storage_after_ingestion_live"] = storage(book.db, db_path)
                begin = time.perf_counter_ns()
                replayed = [book.ingest(session) for session in data.sessions]
                report["unchanged_reingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["unchanged_reingestion_results_sha256"] = digest(replayed)
                report["all_replayed_sessions_skipped"] = all(row["skipped"] for row in replayed)
                report["indexed_content"] = indexed_content(book.db)
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                sources = original_turn_texts(data)
                begin = time.perf_counter_ns()
                counters = {name: TokenCounter(name) for name in ENCODINGS}
                for counter in counters.values():
                    counter.count("Initialize reference tokenizer before query timing.")
                report["reference_tokenizer_initialization_ms"] = (time.perf_counter_ns() - begin) / 1e6
                cases = {case.id: case for case in data.queries}
                for index, config in enumerate(plan["performance_candidate"]["formal"]["configs"]):
                    order = query_order(ids, item["round"], index)
                    if config["surface"] == "official-sdk-mcp-stdio":
                        rows = asyncio.run(mcp_configuration(data, config, order, db_path, work, src,
                            counters, sources, pages, report, ledger))
                    else:
                        rows = []
                        memo = {"id": config["id"], "before": native_memo_snapshot(book, item["label"]),
                                "first_query_id": None, "after_first_call": None, "after": None}
                        report["native_token_count_memo"]["configurations"].append(memo)
                        for identity in order:
                            case = cases[identity]
                            before = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            require(before == 0, "Native result cache was not empty before timing")
                            options = {"project": case.project, "budget_chars": config["budget_chars"],
                                       "limit": 5, "use_cache": False}
                            if config["budget_tokens"] is not None:
                                options.update(budget_tokens=config["budget_tokens"], tokenizer="cl100k_base")
                            seq = ledger.start(config["id"], identity)
                            begin = time.perf_counter_ns()
                            response = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - begin) / 1e6
                            response.pop("latency_ms")  # The sole excluded native response field.
                            after = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            row = make_row(case, response, elapsed, dump(response), None, response, config,
                                counters, sources, pages, before, after, expected["runtime_sha256"])
                            ledger.finish(seq, config["id"], row)
                            rows.append(row)
                            require(not any(row["invariants"].values()), "Native provenance/budget/cache invariant failed")
                            if len(rows) == 1:
                                memo["first_query_id"] = identity
                                memo["after_first_call"] = native_memo_snapshot(book, item["label"])
                        memo["after"] = native_memo_snapshot(book, item["label"])
                    report["configurations"].append({**config, "rows": rows,
                        "latency": latency_summary([r["wall_ms"] for r in rows])})
                    atomic(output, report, compressed=True)
                report["native_memory_after_calls"] = rss()
                report["native_recall_cache_rows"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                report["indexed_content_after_calls"] = indexed_content(book.db)
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report["storage_after_checkpoint"] = storage(book.db, db_path)
                verify_native_memo(report, report["configurations"])
        report["source_after"] = source_identity(src)
        require(report["source_after"] == expected, "Runtime source changed while measuring")
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        ledger.close()
        raw_ledger = ledger_path.read_bytes()
        ledger_path.with_suffix(".jsonl.gz").write_bytes(gzip.compress(raw_ledger, mtime=0))
        report["ledger_sha256"] = sha(raw_ledger)
        report["finished_at"] = now()
        atomic(output, report, compressed=True)
    return 0


def validation(report):
    issues, canonical, total = [], {}, 0
    run, plan = report["run"], report["plan"]
    workers = report["workers"]
    if [w["key"] for w in workers] != [w["key"] for w in schedule(plan)]:
        issues.append("missing_duplicate_or_reordered_workers")
    for w in workers:
        try:
            total += verify_worker(w, run, plan)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(w.get("key", "unknown") + ":" + str(error))
            continue
        for field in ("indexed_content", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256",
                      "mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            key = (w["cohort"], field)
            if key in canonical and canonical[key] != w[field]:
                issues.append(w["key"] + ":" + field)
            canonical.setdefault(key, w[field])
        for c in w["configurations"]:
            for row in c["rows"]:
                key = (w["cohort"], c["id"], row["query_id"])
                value = stable_row(row)
                if key in canonical and canonical[key] != value:
                    issues.append(w["key"] + ":payload:" + c["id"] + ":" + row["query_id"])
                canonical.setdefault(key, value)
    if total != plan["performance_candidate"]["formal"]["calls"]:
        issues.append("registered_call_count")
    if report["error"] or not report["evaluator_unchanged"]:
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(workers),
            "expected_workers": len(schedule(plan)), "timed_calls": total,
            "expected_calls": plan["performance_candidate"]["formal"]["calls"]}


def save_report(args, report):
    report["evaluator_unchanged"] = (file_hashes() == report["run"]["evaluator_files"]
        and sha(PLAN.read_bytes()) == report["run"]["plan_sha256"])
    report["validation"] = validation(report)
    if report["validation"]["passed"]:
        report["comparisons"] = previous.comparisons(report)
        report["acceptance"] = previous.acceptance(report, report["comparisons"])
    else:
        report["comparisons"] = []
        report["acceptance"] = {"accepted": False, "numeric_gate_passed": False,
            "reason": "incomplete_or_invalid", "resource_review": []}
    raw = atomic(args.output, report, compressed=True)
    compact = previous.summary(report, args.output.read_bytes(), raw)
    atomic(args.output.with_name(args.output.name.removesuffix(".json.gz") + ".summary.json"), compact)
    atomic(args.state_dir / "checkpoint.json", {"run_identity_sha256": digest(report["run"]),
        "status": report["status"], "completed_workers": [w["key"] for w in report["workers"]],
        "report_sha256": sha(args.output.read_bytes()), "at": now()})


def controller(args, plan, binding):
    require(getattr(args, "publish_branch", None),
            "Formal timing requires a hosted binding claim and per-worker remote checkpoints")
    require_registered_source()
    require(binding.get("sources") == {"baseline": BASELINE, "candidate": C7_SOURCE},
            "C7 controller must use the exact registered sources")
    require(args.baseline_src and args.candidate_src and args.locomo_path and args.output and args.state_dir,
            "Both sources, old LoCoMo data, state directory and output are required")
    require(args.output.name.endswith(".json.gz"), "Use a new .json.gz output path")
    state = args.state_dir.resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    with _lock(state.with_name(state.name + ".controller")):
        require(not state.exists() and not args.output.exists(), "Preserve existing execution; no timing rerun")
        host = host_identity()
        require(host["packages"] == PACKAGES, "Install the exact bound dependencies")
        paths = {label: str(path.resolve()) for label, path in
                 (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
        for label, path in paths.items():
            require(source_identity(Path(path)) == binding["sources"][label], "Frozen source differs")
        cohorts = {}
        for name in plan["performance_candidate"]["formal"]["cohorts"]:
            data = dataset(plan, name, args.locomo_path)
            ids = [c.id for c in data.queries]
            require(len(ids) == len(set(ids)), "Duplicate input query IDs")
            cohorts[name] = {"sha256": data.fingerprint, "queries": len(ids),
                "query_ids": sorted(ids), "query_ids_original_order": ids}
        run = {"evaluator": VERSION, "plan_sha256": sha(PLAN.read_bytes()), "binding": binding,
            "binding_sha256": sha(args.binding.read_bytes()), "evaluator_files": file_hashes(),
            "source_paths": paths, "host": host, "cohorts": cohorts, "schedule": schedule(plan),
            "locomo_file_sha256": sha(args.locomo_path.read_bytes()), "output": str(args.output.resolve()),
            "publication": publication_identity(args)}
        claim_execution(args, run)
        exclusive(state / "run.json", run)
        report = {"schema_version": 1, "evaluator": VERSION, "plan": plan, "run": run,
            "started_at": now(), "workers": [], "error": None, "evaluator_unchanged": False,
            "status": "running", "interpretation": {
                "quality": "Old-data regression, complete output equality; no new-domain or generated-answer claim.",
                "native": "Complete API call with query-result cache disabled and a bounded exact-token-count memo naturally retained on each candidate book. Only latency_ms is excluded from equality; native memo observations are outside timing.",
                "mcp": "Actual unchanged SDK stdio call/envelope with empty query-result cache and normal cache-write cost. Each configuration starts a fresh server process; private memo counters are not exposed. Actual process RSS remains measured.",
                "timing": "Four ABBA rounds on one machine; all samples retained, no cold-OS or significance claim.",
                "resources": "Startup, ingest/replay, native and actual MCP process memory measured separately."}}
        try:
            save_report(args, report)
            publish_checkpoint(args, run, "execution claimed")
            for item in run["schedule"]:
                exclusive(state / "workers" / (item["key"] + ".started.json"),
                          {"worker": item, "run_identity_sha256": digest(run)})
                save_report(args, report)
                publish_checkpoint(args, run, item["key"] + " started")
                command = [sys.executable, str(Path(__file__).resolve()), "--worker", item["key"],
                    "--binding", str(args.binding.resolve()), "--state-dir", str(state),
                    "--locomo-path", str(args.locomo_path.resolve())]
                subprocess.run(command, check=True, env={**os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
                report["workers"].append(load_completed(state, item, run, plan))
                save_report(args, report)
                publish_checkpoint(args, run, item["key"] + " completed")
                print(json.dumps({"worker_completed": item["key"], "completed_workers": len(report["workers"]),
                                  "report": str(args.output)}), flush=True)
            report["status"] = "measurements_completed"
        except BaseException as error:
            report["status"] = "failed_or_interrupted"
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            report["finished_at"] = now()
            save_report(args, report)
            if not (args.output.resolve().parent / "publication-failure.json").exists():
                try:
                    publish_checkpoint(args, run, "controller finished")
                except CheckpointPublicationError as error:
                    report["status"] = "failed_or_interrupted"
                    report["error"] = {"type": type(error).__name__, "message": str(error)}
                    save_report(args, report)
            export_checkpoint(args)
        print(json.dumps({"output": str(args.output), "validation": report["validation"],
                          "acceptance": report["acceptance"]}), flush=True)
        return 2 if not report["validation"]["passed"] else (0 if report["acceptance"]["accepted"] else 3)


def audit(path, state):
    raw = gzip.decompress(path.read_bytes())
    report = json.loads(raw)
    run, plan = report["run"], report["plan"]
    require(report["evaluator"] == VERSION and run["evaluator"] == VERSION, "Wrong evaluator")
    require(json.loads((state / "run.json").read_bytes()) == run, "Saved run identity differs")
    require(plan == load_plan() and run["plan_sha256"] == sha(PLAN.read_bytes())
            and run["evaluator_files"] == file_hashes(), "Audit evaluator or plan differs")
    require(run["binding"]["evaluator_files"] == run["evaluator_files"]
            and run["binding"]["sources"]["baseline"] == BASELINE, "Audit binding differs")
    for item, stored in zip(run["schedule"], report["workers"], strict=True):
        worker = load_completed(state, item, run, plan)
        require(worker == stored, "Worker bytes differ from aggregate")
    checked = validation(report)
    require(checked == report["validation"] and checked["passed"], "Invalid or incomplete saved measurements")
    compared = previous.comparisons(report)
    accepted = previous.acceptance(report, compared)
    require(compared == report["comparisons"] and accepted == report["acceptance"],
            "Stored arithmetic or acceptance changed")
    compact_path = path.with_name(path.name.removesuffix(".json.gz") + ".summary.json")
    require(json.loads(compact_path.read_bytes()) == previous.summary(report, path.read_bytes(), raw),
            "Stored summary differs")
    return {"audit_passed": True, "timed_calls": checked["timed_calls"],
            "accepted": accepted["accepted"], "report_sha256": sha(path.read_bytes()),
            "retrieval_calls_during_audit": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--publish-branch", help="First-attempt hosted validation branch; push each immutable checkpoint")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.audit:
        require(args.state_dir is not None, "Audit needs original worker/ledger state")
        print(json.dumps(audit(args.audit, args.state_dir)))
        return 0
    require_registered_source()
    if args.bind:
        bind(args)
        return 0
    require(args.binding is not None, "A committed binding is required")
    plan, binding = load_plan(), load_binding(args.binding)
    return worker(args, plan, binding) if args.worker else controller(args, plan, binding)


if __name__ == "__main__":
    raise SystemExit(main())
