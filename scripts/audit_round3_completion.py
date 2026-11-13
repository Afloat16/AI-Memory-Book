"""Read-only final audit of the already measured round-three evidence.

No worker, retriever, tokenizer, model, dataset loader or timing function runs.
Original frozen auditors recompute consistency from saved rows only. Historical
rejections and the separate documented startup decision remain unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUNTIME = "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46"
CANDIDATE = "2d199b93f650eccd3dd239178822b31001b880e3"
BASE = "e62322accbfa675def889a5e178d7a01f71b3c24"
PERFORMANCE = "benchmarks/reports/round3-performance-43246417515-1"
QUALITY = "benchmarks/reports/round3-project-stats-recovery-43266603949-1"
STARTUP = "benchmarks/reports/round3-startup-review-43266672875-1"
COMPARISON = "benchmarks/results/round3-comparison-43267797247-1"
CHECKPOINT = "benchmarks/reports/round3-comparison-43267797247-1-checkpoint.json"
DECISION = "benchmarks/experiments/round3-startup-resource-decision.json"
QUALITY_REPORT = QUALITY + "/round3-project-stats-20261112-1.json.gz"
PINS = {
    PERFORMANCE: "35b8618a078fe377ecd6c5acc331c1281dbf61e7",
    QUALITY: "f0f6a5eeaa797c01fcba12e17882c9089f44df87",
    STARTUP: "a129e324fb4af9e821325a797edb882beecc30a4",
    DECISION: BASE,
    COMPARISON: "c99f20531053b1c164fc5a5d3fa8e0c831eeb4de",
    CHECKPOINT: "c99f20531053b1c164fc5a5d3fa8e0c831eeb4de",
    "benchmarks/reports/round3-comparison-claim-740361f1767a942887bdb7639b1be0223ae1c6dc2fc3b941f845d038884f842f.json":
        "c99f20531053b1c164fc5a5d3fa8e0c831eeb4de",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def local(root, name):
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts
            and relative.as_posix() == name, "Noncanonical input path: " + name)
    path = root / name
    require(path.resolve() == root.resolve() / name and path.is_file() and not path.is_symlink(),
            "Missing or unsafe input: " + name)
    return path


def read(name):
    return json.loads(local(ROOT, name).read_bytes())


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=60)


def tree(ref, *paths):
    result = {}
    for entry in git("ls-tree", "-r", "-z", ref, "--", *paths).split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode().split()
        require(kind == "blob" and mode in {"100644", "100755"}, "Nonregular tracked input")
        result[name.decode()] = object_id
    return result


def snapshot(root, entries):
    result = {}
    for name, expected in sorted(entries.items()):
        raw = local(root, name).read_bytes()
        require(blob(raw) == expected, "Working bytes differ from audited HEAD: " + name)
        result[name] = {"sha256": sha(raw), "git_blob_sha": expected, "bytes": len(raw)}
    return result


def selected_inputs(head_tree):
    prefixes = (PERFORMANCE + "/", QUALITY + "/", STARTUP + "/", COMPARISON + "/")
    names = {name for name in head_tree if name.startswith(
        ("src/memory_book/", "scripts/", "tests/", ".github/workflows/") + prefixes)
        or (name.startswith("benchmarks/") and not name.startswith(
            ("benchmarks/reports/", "benchmarks/results/")))}
    names.add(CHECKPOINT)
    names.add("benchmarks/reports/round3-comparison-claim-740361f1767a942887bdb7639b1be0223ae1c6dc2fc3b941f845d038884f842f.json")
    binding = read("benchmarks/experiments/round3-validation-binding.json")
    names.update(binding["evaluator_files"])
    require(all(name in head_tree for name in names), "An audit input is missing from HEAD")
    require(any(name.startswith(COMPARISON + "/") for name in names), "New comparison is absent")
    return {name: head_tree[name] for name in sorted(names)}


def verify_pin(current, expected, label):
    require(bool(expected) and current == expected,
            "Historical artifact inventory/blob changed: " + label)


def historical_pins(head_tree):
    result = {}
    for path, commit in PINS.items():
        expected = tree(commit, path)
        current = {name: value for name, value in head_tree.items()
                   if name == path or name.startswith(path + "/")}
        verify_pin(current, expected, path)
        result[path] = {"commit": commit, "files": len(expected), "git_blobs_verified": True}
    return result


class ReadOnlyGuard:
    """Fail closed on accidental worker/network/write paths inside the auditors."""
    def __init__(self):
        self.active = False
        self.blocked_operations = []

    def __call__(self, event, args):
        if not self.active:
            return
        blocked = event.startswith("socket.") or event in {
            "os.system", "os.posix_spawn", "os.fork", "os.exec", "os.remove",
            "os.rename", "os.mkdir", "os.rmdir", "os.truncate", "os.chmod",
            "os.chown", "os.link", "os.symlink",
        }
        if event == "open":
            mode, flags = args[1], args[2]
            blocked = bool(mode and any(letter in mode for letter in "wax+"))
            blocked = blocked or bool(isinstance(flags, int) and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if event == "subprocess.Popen":
            executable, command = args[:2]
            blocked = not (
                isinstance(command, (list, tuple)) and len(command) >= 2
                and command[0] == executable == "git"
                and command[1] in {"show", "ls-tree", "rev-parse"})
        if event == "import":
            blocked = args[0].split(".")[0] in {
                "memory_book", "tiktoken", "onnxruntime", "tokenizers", "pyarrow", "numpy"}
        if blocked:
            self.blocked_operations.append(event)
            raise RuntimeError("Read-only audit blocked operation: " + event)


def runtime_audit():
    paths = sorted((ROOT / "src/memory_book").rglob("*.py"))
    tracked = tree("HEAD", "src/memory_book")
    require([p.relative_to(ROOT).as_posix() for p in paths]
            == sorted(name for name in tracked if name.endswith(".py")),
            "Untracked, ignored or missing Python runtime file")
    hasher = hashlib.sha256()
    for path in paths:
        hasher.update(path.relative_to(ROOT / "src/memory_book").as_posix().encode()
                      + b"\0" + path.read_bytes() + b"\0")
    require(hasher.hexdigest() == RUNTIME, "Final runtime differs from the frozen measured candidate")
    binding = read("benchmarks/experiments/round3-validation-binding.json")
    require(binding["candidate"] == {"commit": CANDIDATE, "source_sha256": RUNTIME}
            and binding["optional_project_statistics"] is False,
            "Final comparison candidate or rejected optional axis changed")
    return {"runtime_sha256": RUNTIME, "measured_source_commit": CANDIDATE, "python_files": len(paths)}


def performance_audit():
    from scripts import round3_performance as frozen
    binding = frozen.load_binding(ROOT / "benchmarks/experiments/round3-performance-binding.json")
    require(binding["sources"]["candidate"] == {"commit": CANDIDATE, "runtime_sha256": RUNTIME},
            "Formal performance candidate differs")
    result = frozen.audit(ROOT / PERFORMANCE / "report.json.gz", ROOT / PERFORMANCE)
    summary = read(PERFORMANCE + "/report.summary.json")
    require(result["verified"] is True and result["validation"]["passed"] is True
            and result["validation"]["timed_calls"] == 47320
            and result["validation"]["workers"] == 16
            and result["accepted"] is False and result["retrieval_calls_executed"] == 0
            and summary["acceptance"]["numeric_gate_passed"] is True,
            "Original formal evidence or retained resource-review result differs")
    return result


def quality_decision(value):
    require(value["validation_passed"] is True and value["calls"] == 8082
            and value["workers"] == 8 and value["qualified"] is False
            and value["status"] == "rejected_loss_or_no_gain"
            and value["action"] == "keep_out_of_release_and_new_cohort"
            and value["original_evaluator_audit"] == "passed"
            and value["new_measurement_calls"] == 0
            and (value["loss_checks"], value["gain_checks"]) == (14, 10),
            "Original rejected quality decision changed")


def quality_audit():
    from scripts import round3_project_stats as frozen
    captured = io.StringIO()
    with redirect_stdout(captured):
        frozen.audit(ROOT / QUALITY_REPORT, frozen.BINDING)
    result = json.loads(captured.getvalue())
    decision = read(QUALITY + "/decision.json")
    quality_decision(decision)
    manifest = read(QUALITY + "/recovery-manifest.json")
    require(result["audit"] == "passed" and result["calls"] == 8082 and result["workers"] == 8
            and result["screen"] == decision["status"]
            and result["full_report_sha256"] == manifest["reconstructed_report_sha256"]
            and sha((ROOT / QUALITY_REPORT).read_bytes()) == manifest["reconstructed_gzip_sha256"]
            and manifest["new_measurement_calls"] == 0,
            "Recovered quality audit/manifest differ")
    return {**result, "qualified": False, "loss_checks": 14, "gain_checks": 10,
            "original_complete_aggregate_available": False,
            "basis": "Intact original workers and ledgers; recovered aggregate and preserved partial prefix."}


def startup_decision(value):
    require(value["status"] == "accepted-with-documented-resource-review"
            and value["accepted"] is True and value["original_report_accepted"] is False
            and value["original_numeric_gate_passed"] is True
            and value["original_resource_review_retained"] is True
            and value["unchanged_formal_report"] is True and value["retrieval_calls_repeated"] == 0
            and value["inputs"]["candidate"] == {"commit": CANDIDATE, "runtime_sha256": RUNTIME},
            "Documented startup decision or original rejection changed")


def startup_audit(inputs):
    decision = read(DECISION)
    startup_decision(decision)
    diagnosis, original = decision["diagnosis"], decision["original_result"]
    require(diagnosis["commit"] == PINS[STARTUP] and diagnosis["path"] == STARTUP + "/report.json"
            and original["commit"] == PINS[PERFORMANCE]
            and original["path"] == PERFORMANCE + "/report.json.gz",
            "Startup review references different original evidence")
    require(inputs[diagnosis["path"]]["sha256"] == diagnosis["sha256"]
            and inputs[original["path"]]["sha256"] == original["compressed_sha256"]
            and sha(gzip.decompress((ROOT / original["path"]).read_bytes())) == original["raw_sha256"],
            "Startup/original report SHA256 differs")
    completion = read(STARTUP + "/completion.json")
    files = {name.removeprefix(STARTUP + "/"): value["sha256"]
             for name, value in inputs.items() if name.startswith(STARTUP + "/")
             and name != STARTUP + "/completion.json"}
    require(completion["status"] == "completed" and completion["diagnostic_outcome"] == "success"
            and files == completion["files_sha256"] and len(files) == 163,
            "The complete original startup artifact inventory changed")
    report = read(diagnosis["path"])
    registration = read(STARTUP + "/registration.json")
    require(report["status"] == "completed" and report["registration"] == registration
            and report["validation"] == diagnosis["validation"]
            and report["validation"]["passed"] is True and report["validation"]["workers"] == 80
            and len(report["samples"]) == 80
            and read(diagnosis["summary_path"]) == {k: v for k, v in report.items() if k != "samples"},
            "Startup raw rows/registration/summary differ")
    for index, row in enumerate(report["samples"]):
        phase = "plain" if index < 64 else "instrumented"
        label = ("baseline", "candidate", "candidate", "baseline")[index % 4]
        key = f"{index:03d}-{phase}-{label}"
        intent = read(STARTUP + "/workers/" + key + ".started.json")
        worker = read(STARTUP + "/workers/" + key + ".json")
        require(row == {**intent, **worker} and row["index"] == index
                and row["phase"] == phase and row["label"] == label
                and row["status"] == "completed" and row["source"] == decision["inputs"][label],
                "Startup sample/intent differs: " + key)
    require(registration["plan_sha256"] == diagnosis["plan_sha256"]
            == inputs["benchmarks/experiments/round3-startup-review-plan.json"]["sha256"]
            and registration["script_sha256"] == diagnosis["evaluator_sha256"]
            == inputs["scripts/round3_startup_review.py"]["sha256"]
            and registration["startup_code_identity"] == diagnosis["startup_code_identity"]
            and registration["original_formal_report"]["accepted"] is False
            and registration["original_formal_report"]["resource_review"] == decision["original_resource_review"]
            and report["summary"] == [diagnosis["plain_summary"], diagnosis["instrumented_summary"]],
            "Startup plan/evaluator/source or disclosed measurements changed")
    return {"workers": 80, "artifact_hashes_verified": len(files),
            "decision": decision["status"], "accepted": True, "original_report_accepted": False,
            "diagnosis_sha256": diagnosis["sha256"], "new_timing_measurements": 0,
            "causal_limits": decision["cause_and_limits"]}


def comparison_audit():
    from scripts import round3_comparison as frozen
    result = frozen.assess(ROOT / CHECKPOINT, verify_existing=True)
    require(result["status"] == "complete-verified" and result["validation"]["passed"] is True
            and len(result["verified_stages"]) == 10
            and result["native_calls"] == result["component_search_calls"] == 4608
            and result["default_payload_equivalence"]["passed"] is True
            and result["project_statistics_gate"] == {"status": "not-included", "qualified": None},
            "Independent comparison is incomplete or rejected optional quality was included")
    return {"status": result["status"], "source_commit": result["source_commit"],
            "verified_stages": result["verified_stages"], "native_calls": result["native_calls"],
            "component_search_calls": result["component_search_calls"],
            "default_payload_equivalence": result["default_payload_equivalence"],
            "project_statistics_gate": result["project_statistics_gate"],
            "mode": "assess(verify_existing=True); saved assessment and Markdown unchanged"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    require(output.parent == ROOT / "benchmarks/reports"
            and re.fullmatch(r"round3-final-audit-[1-9][0-9]*-[1-9][0-9]*\.json", output.name)
            and not output.exists(), "Use a new run-specific final audit JSON path")
    result = {"schema_version": 1, "protocol": "round3-final-read-only-evidence-audit-v1",
              "created_at": datetime.now(timezone.utc).isoformat(), "expected_head": args.expected_head,
              "exact_head": git("rev-parse", "HEAD").decode().strip(),
              "retrieval_calls_executed": 0, "generative_model_calls": 0,
              "embedding_model_calls": 0, "dataset_selections": 0, "timing_measurements": 0,
              "checks": {}, "input_files": {}, "limitations": [
                  "This audits saved evidence; it performs no new measurements or quality scoring.",
                  "Original formal accepted=false and rejected optional quality remain preserved.",
                  "The separate startup decision accepts a disclosed cost; it does not prove the OS cause of the historical outlier.",
              ]}
    def check(name, operation):
        try:
            details = operation()
            result["checks"][name] = {"passed": True, "details": details}
        except Exception as error:
            result["checks"][name] = {"passed": False, "error": type(error).__name__ + ": " + str(error)}
        print(json.dumps({"check": name, **result["checks"][name]}, sort_keys=True), flush=True)
        return result["checks"][name]["passed"]

    guard = ReadOnlyGuard()
    entries = {}
    def prepare():
        nonlocal entries
        require(re.fullmatch(r"[0-9a-f]{40}", args.expected_head)
                and result["exact_head"] == args.expected_head, "Checkout is not the requested exact HEAD")
        require(git("rev-parse", "--is-shallow-repository").strip() == b"false",
                "Historical bindings require fetch-depth: 0")
        head_tree = tree(result["exact_head"])
        entries = selected_inputs(head_tree)
        result["input_files"] = snapshot(ROOT, entries)
        return historical_pins(head_tree)

    if check("committed_inputs_and_original_blobs", prepare):
        sys.addaudithook(guard)
        guard.active = True
        try:
            check("frozen_runtime", runtime_audit)
            check("formal_performance_original_auditor", performance_audit)
            check("restored_quality_original_auditor", quality_audit)
            check("startup_raw_and_documented_decision", lambda: startup_audit(result["input_files"]))
            check("independent_comparison_verify_existing", comparison_audit)
        finally:
            guard.active = False
        def unchanged():
            require(git("rev-parse", "HEAD").decode().strip() == result["exact_head"]
                    and snapshot(ROOT, entries) == result["input_files"],
                    "An audited input or HEAD changed during read-only verification")
            require(not guard.blocked_operations, "A forbidden operation was attempted")
            return {"files": len(entries), "original_reports_unchanged": True}
        check("inputs_unchanged", unchanged)
    result["blocked_operations"] = guard.blocked_operations
    result["passed"] = len(result["checks"]) == 7 and all(item["passed"] for item in result["checks"].values())
    result["status"] = "complete-verified" if result["passed"] else "failed"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "exact_head": result["exact_head"],
                      "audit_path": output.relative_to(ROOT).as_posix(),
                      "audit_sha256": sha(output.read_bytes()), "retrieval_calls_executed": 0}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
