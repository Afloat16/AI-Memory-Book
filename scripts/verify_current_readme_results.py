#!/usr/bin/env python3
"""Verify the current released wheel on the unchanged README quality fixtures.

This is one quality/compatibility replay, not a latency experiment. Existing
evaluators and external component records are read unchanged. Run with an
isolated interpreter into which the chosen published native wheel is installed.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = "164f48c42e88bd096bf58827d8b2ba77a9048ae3"
NATIVE_SOURCE = "238c8058f723a203eaca99f94d924ab77de4c0b3"
RUNTIME_SHA256 = "d00d84ef8436c97b45de5e5e5c2b67883ffbc03992cffa10e7f6d35a15e7fd16"
ARCHIVED = "benchmarks/reports/v0.6.0-engineering/hosted/"
PROTOCOL = "current-readme-quality-replay-v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def archived(name, inventory):
    raw = git("show", SOURCE + ":" + ARCHIVED + name)
    inventory[name] = {"commit": SOURCE, "path": ARCHIVED + name, "bytes": len(raw), "sha256": sha(raw)}
    return gzip.decompress(raw) if name.endswith(".gz") else raw


def runtime_proof(wheel, manifest):
    import memory_book
    from memory_book import _native, _text_backend
    metadata = json.loads(manifest.read_bytes())
    require(metadata["version"] == "0.10.0" and metadata["commit"] == SOURCE
            and metadata["runtime_sha256"] == RUNTIME_SHA256, "Published manifest identity differs")
    record = next(row for row in metadata["native_wheels"] if row["filename"] == wheel.name)
    raw = wheel.read_bytes()
    require(len(raw) == record["bytes"] and sha(raw) == record["sha256"], "Published wheel bytes differ")
    require(memory_book.__version__ == importlib.metadata.version("ai-memory-book") == "0.10.0"
            and _text_backend.BACKEND_NAME == "native", "Install the current published native wheel first")
    package = Path(memory_book.__file__).resolve().parent
    files = {}
    hasher = hashlib.sha256()
    names = git("ls-tree", "-r", "--name-only", SOURCE, "src/memory_book").decode().splitlines()
    with zipfile.ZipFile(wheel) as archive:
        for name in names:
            relative = name.removeprefix("src/memory_book/")
            expected = git("show", SOURCE + ":" + name)
            require((package / relative).read_bytes() == expected == archive.read("memory_book/" + relative),
                    "Installed source differs from release commit or wheel: " + name)
            files[name] = sha(expected)
            if Path(name).suffix in (".py", ".c", ".h", ".rs"):
                hasher.update(relative.encode() + b"\0" + expected + b"\0")
        extension = Path(_native.__file__).resolve()
        require(extension.parent == package and extension.read_bytes() == archive.read("memory_book/" + extension.name),
                "Loaded extension differs from published wheel")
    require(hasher.hexdigest() == RUNTIME_SHA256, "Installed runtime aggregate differs")
    retained = [name for name in names if name.startswith("src/memory_book/_native") and name.endswith((".c", ".h"))]
    require(len(retained) == 6, "Unexpected native source inventory")
    for name in retained:
        require(git("show", SOURCE + ":" + name) == git("show", NATIVE_SOURCE + ":" + name), "Native core changed: " + name)
    def methods(commit):
        tree = ast.parse(git("show", commit + ":src/memory_book/store.py"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MemoryBook")
        return {node.name: ast.dump(node, include_attributes=False) for node in cls.body if isinstance(node, ast.FunctionDef)}
    before, current = methods(NATIVE_SOURCE), methods(SOURCE)
    require(before["recall"] == current["recall"], "Recall entry point changed from measured native core")
    return {"version": memory_book.__version__, "source_commit": SOURCE, "runtime_sha256": RUNTIME_SHA256,
            "wheel": {"filename": wheel.name, "bytes": len(raw), "sha256": sha(raw)},
            "manifest_sha256": sha(manifest.read_bytes()), "backend": _text_backend.BACKEND_NAME,
            "native_extension_sha256": sha(extension.read_bytes()), "installed_source_files_sha256": files,
            "retained_native_core": {"measured_source_commit": NATIVE_SOURCE, "byte_identical_native_files": retained,
                "recall_method_ast_identical": True, "changed_memorybook_methods": sorted(name for name in set(before) | set(current) if before.get(name) != current.get(name)),
                "interpretation": "Retained implementation identity; does not rerun or transfer an end-to-end latency measurement to this wheel."}}


def key(row):
    return row["case_id"], row["backend"], row["budget_chars"]


def compare(current, baseline, exclusions):
    old = {key(row): row for row in baseline}
    require(len(old) == len(baseline), "Duplicate archived observation")
    require({key(row) for row in current} == set(old) and len(current) == len(old), "Response matrix differs")
    failures = []
    for row in current:
        previous = old[key(row)]
        left = {name: value for name, value in row["response"].items() if name not in exclusions}
        right = {name: value for name, value in previous["response"].items() if name not in exclusions}
        if json.dumps(left, ensure_ascii=False, separators=(",", ":")) != json.dumps(right, ensure_ascii=False, separators=(",", ":")):
            failures.append({"case": key(row), "kind": "response_or_serialized_order"})
        if row["score"] != previous["score"]:
            failures.append({"case": key(row), "kind": "score"})
    return {"responses": len(current), "matching_responses": len(current) - sum(item["kind"] == "response_or_serialized_order" for item in failures),
            "response_exclusions": sorted(exclusions), "failures": failures}


def independent_scores(rows, dataset):
    from scripts.audit_project_scope_native_replay import expected_score
    from benchmarks import engineering_workflow as workflow
    by_checkpoint = {step["checkpoint"]: step for step in dataset}
    visible, cases, sources = {}, {}, {}
    for checkpoint, step in by_checkpoint.items():
        for session in step["sessions"]:
            visible[(session["project"], session["session_id"])] = session
        sources[checkpoint] = workflow.visible_sources(visible)
        cases.update({case["id"]: case for case in step["cases"]})
    failures = []
    for row in rows:
        derived = expected_score(cases[row["case_id"]], row["response"], sources[row["checkpoint"]], row["budget_chars"])
        if derived != row["score"]:
            failures.append(key(row))
    return {"responses": len(rows), "failures": failures, "scorer": "scripts/audit_project_scope_native_replay.py:expected_score"}


def quality(rows):
    from scripts.audit_project_scope_native_replay import quality_summary
    return [{name: value for name, value in row.items() if name not in ("retrieval_samples", "repeat_output_changes")}
            for row in quality_summary(rows)]


def compress_outputs(output):
    inventory = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in ("verification.json", "raw-manifest.json"):
            raw = path.read_bytes()
            name = path.relative_to(output).as_posix()
            if path.suffix in (".json", ".jsonl", ".md"):
                compressed = path.with_name(path.name + ".gz")
                compressed.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
                require(gzip.decompress(compressed.read_bytes()) == raw, "Lossless compression differs")
                path.unlink()
                inventory[name] = {"bytes": len(raw), "sha256": sha(raw), "stored_as": name + ".gz",
                                   "stored_sha256": sha(compressed.read_bytes())}
            else:
                inventory[name] = {"bytes": len(raw), "sha256": sha(raw), "stored_as": name}
    write(output / "raw-manifest.json", inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"protocol": PROTOCOL, "status": "started", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Current published Book wheel quality/compatibility replay; external engines and performance experiments are not rerun.",
              "timing_policy": "Unchanged evaluators retain diagnostic local timers. One execution per configuration is not a latency benchmark or a stability study; no timing field is used for README claims.",
              "driver_sha256": sha(Path(__file__).read_bytes()), "archived_inputs": {}}
    try:
        from benchmarks import engineering_workflow as workflow, memory_systems
        from scripts.audit_project_scope_native_replay import EVALUATOR_SHA256
        require(sha(Path(workflow.__file__).read_bytes()) == EVALUATOR_SHA256, "Fixed scorer requires unchanged fixture evaluator")
        for name in memory_systems.SOURCE_FILES:
            require((ROOT / name).read_bytes() == git("show", SOURCE + ":" + name), "Frozen evaluator input changed: " + name)
        report["runtime"] = runtime_proof(args.wheel, args.manifest)
        report["environment"] = {"python": sys.version, "platform": platform.platform()}
        native_old = [json.loads(line) for line in archived("native/raw.jsonl.gz", report["archived_inputs"]).splitlines()]
        common_old = [json.loads(line) for line in archived("memory-systems/raw.jsonl.gz", report["archived_inputs"]).splitlines()]
        dataset = json.loads(archived("native/dataset.json", report["archived_inputs"]))
        require(dataset == workflow.workload(), "Fixed workload changed")
        report["dataset_sha256"] = workflow.sha(dataset)
        native = workflow.run(args.output / "native", budgets=(1200, 2400), repeats=1)
        with tempfile.TemporaryDirectory(prefix="readme-components-") as cache:
            common = memory_systems.run(args.output / "common-block", cache, budgets=(1200, 2400), repeats=1, backends=("book",))
        require(native["status"] == common["status"] == "completed", "A current replay did not complete")
        native_rows = [json.loads(line) for line in (args.output / "native/raw.jsonl").read_bytes().splitlines()]
        common_rows = [json.loads(line) for line in (args.output / "common-block/raw.jsonl").read_bytes().splitlines()]
        require(len(native_rows) == 640 and len(common_rows) == 160 and len(common_old) == 1120, "Unexpected response counts")
        report["native_comparison"] = compare(native_rows, native_old, {"latency_ms", "cache_hit"})
        report["common_block_comparison"] = compare(common_rows, [row for row in common_old if row["backend"] == "book"], set())
        report["independent_score_check"] = independent_scores(native_rows + common_rows, dataset)
        report["native_quality"] = quality(native_rows)
        report["common_block_current_book"] = quality(common_rows)
        report["retained_external_components"] = quality([row for row in common_old if row["backend"] != "book"])
        report["current_book_categories"] = {category: quality([row for row in common_rows if row["category"] == category])
                                            for category in sorted({row["category"] for row in common_rows})}
        require(not any(report[name]["failures"] for name in ("native_comparison", "common_block_comparison", "independent_score_check")),
                "Current quality or original response differs; retain and inspect the complete replay")
        require(all(not row["budget_violations"] and not row["source_validation_failures"]
                    for row in report["native_quality"] + report["common_block_current_book"]), "Current source/budget integrity failed")
        require(report["runtime"] == runtime_proof(args.wheel, args.manifest), "Runtime changed during replay")
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        compress_outputs(args.output)
        write(args.output / "verification.json", report)
    print(json.dumps({"status": report["status"], "native_responses": 640, "common_block_responses": 160,
                      "source_commit": SOURCE, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
