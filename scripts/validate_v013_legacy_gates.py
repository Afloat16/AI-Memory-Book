"""Source-bound v0.13 correctness replays of unchanged legacy gates.

This wrapper changes no fixture, scoring rule, or historical evaluator. The
engineering gate uses validate_v012_engineering.worker/compare with the v0.12
baseline selected explicitly. Timers retained by those evaluators are diagnostic
only: these sequential local replays support no performance or product claim.
Each invocation requires a fresh output directory and preserves failed attempts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
BASELINE = "8044e4bafe18e73ea422af5eeb47ef961e65246c"
sys.path.insert(0, str(ROOT))
from scripts.validate_v011_revision_recovery import source_identity

ENGINEERING_INPUTS = (
    "benchmarks/__init__.py", "benchmarks/engineering_workflow.py",
    "benchmarks/engineering_components.py", "benchmarks/memory_systems.py",
    "benchmarks/competitors/__init__.py", "benchmarks/competitors/billion.py",
    "benchmarks/competitors/billion_bridge.mjs", "benchmarks/competitors/compile_billion.mjs",
    "benchmarks/competitors/download.py", "benchmarks/competitors/billion-round2-lock.json",
    "benchmarks/competitors/claude_mem.py", "benchmarks/competitors/claude_mem_bridge.ts",
    "benchmarks/competitors/claude-mem-round2-lock.json", "benchmarks/competitors/memory_systems.py",
    "benchmarks/competitors/memory_systems_worker.py", "benchmarks/competitors/memory-systems-lock.json",
    "benchmarks/competitors/memory-systems-plan.md", "benchmarks/competitors/memory-systems-requirements.in",
    "benchmarks/competitors/memory-systems-requirements.txt", "scripts/validate_v012_engineering.py",
    "scripts/verify_current_readme_results.py", "scripts/audit_project_scope_native_replay.py",
)
SHORT_INPUTS = (
    "benchmarks/v012_short_page_guard_eval.py", "benchmarks/engineering_workflow.py",
    "benchmarks/reports/v0.12-development/evaluation/short-page-review-attempt1.json",
    "benchmarks/experiments/v012-short-page-review-probe.py", "tests/test_current_turn_recall.py",
)
DIRECTORY_INPUTS = (
    "benchmarks/directory_navigation.py",
    "benchmarks/experiments/v011-directory-navigation-protocol-v2.json",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def bound_files(root, commit, names):
    """Verify exact Git blob bytes and retain SHA256 for independently read files."""
    if git(root, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ValueError("This repository's existing source identities require SHA1 Git objects")
    entries = {}
    for entry in git(root, "ls-tree", "-rz", commit).split(b"\0"):
        if entry:
            meta, name = entry.split(b"\t", 1)
            mode, kind, oid = meta.split()
            entries[name.decode()] = (mode, kind, oid.decode())
    result = {}
    for name in sorted(set(names)):
        path = root / name
        if path.is_symlink() or not path.is_file() or name not in entries:
            raise ValueError("Missing or symlinked committed input: " + str(path))
        mode, kind, oid = entries[name]
        raw = path.read_bytes()
        actual_oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if kind != b"blob" or mode not in (b"100644", b"100755") or actual_oid != oid:
            raise ValueError("Input differs from pinned Git snapshot: " + name)
        result[name] = {"bytes": len(raw), "sha256": sha(raw), "git_blob": oid}
    return {"commit": commit, "files": result}


def evaluator_binding(gate, source, commit):
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    result = {"driver": bound_files(ROOT, head, [SELF.relative_to(ROOT).as_posix(),
                                               "scripts/validate_v011_revision_recovery.py"])}
    if gate == "full-suite":
        names = git(source, "ls-tree", "-r", "--name-only", commit,
                    "tests", "benchmarks", "scripts", "pyproject.toml", "setup.py", "MANIFEST.in").decode().splitlines()
        materialized = [name for name in names if (source / name).is_file()]
        if any(name.startswith("tests/") and name not in materialized for name in names):
            raise ValueError("All committed test files must be materialized")
        result["test_inputs"] = bound_files(source, commit, materialized)
        result["unmaterialized_tracked_inputs"] = sorted(set(names) - set(materialized))
        result["selection"] = "All tests and all materialized tracked benchmark/script/build inputs; absent historical artifacts are disclosed."
    else:
        names = {"engineering": ENGINEERING_INPUTS, "short-page": SHORT_INPUTS,
                 "directory": DIRECTORY_INPUTS}[gate]
        result["unchanged_legacy_inputs"] = bound_files(
            ROOT, BASELINE, (*names, "scripts/validate_v011_revision_recovery.py"))
    return result


def loaded_runtime(source, commit, backend):
    import memory_book
    import memory_book.store as store
    from memory_book._text_backend import BACKEND_NAME, NATIVE
    package = source / "src/memory_book"
    if (Path(memory_book.__file__).resolve().parent != package
            or Path(store.__file__).resolve() != package / "store.py" or BACKEND_NAME != backend):
        raise ValueError("Imported runtime path/backend differs from selected source")
    native = None
    if backend == "native":
        if NATIVE is None or Path(NATIVE.__file__).resolve().parent != package:
            raise ValueError("Native extension is not loaded from the selected worktree")
        binary = Path(NATIVE.__file__).resolve()
        native = {"path": str(binary), "sha256": sha(binary.read_bytes())}
    return {"source": source_identity(source, commit), "package": str(package),
            "backend": BACKEND_NAME, "version": memory_book.__version__, "native": native}


def worker(args):
    source, output = args.candidate_source.resolve(), args.output.resolve()
    proof = loaded_runtime(source, args.candidate_commit, args.backend)
    if args.worker == "probe":
        write(output, proof)
        return 0
    if args.worker == "engineering":
        from scripts.validate_v012_engineering import worker as original_worker
        try:
            original_worker(output)
        finally:
            if output.is_dir():
                write(output / "loaded-runtime.json", proof)
        return 0
    output.mkdir(parents=True, exist_ok=False)
    write(output / "loaded-runtime.json", proof)
    # Test imports must resolve their helpers from the selected candidate tree.
    sys.path.insert(0, str(source))
    suite = unittest.defaultTestLoader.discover(str(source / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    write(output / "result.json", {
        "successful": result.wasSuccessful(), "tests_run": result.testsRun,
        "failures": [{"test": str(test), "traceback": tb} for test, tb in result.failures],
        "errors": [{"test": str(test), "traceback": tb} for test, tb in result.errors],
        "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
        "expected_failures": [str(test) for test, _ in result.expectedFailures],
        "unexpected_successes": [str(test) for test in result.unexpectedSuccesses],
    })
    return 0 if result.wasSuccessful() else 1


def command_env(source, backend, gate):
    roots = (source / "src", source if gate == "full-suite" else ROOT, ROOT)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(map(str, roots)),
            "PYTHONDONTWRITEBYTECODE": "1", "MEMORY_BOOK_TEXT_BACKEND": backend,
            "CC": "gcc"}


def run_command(command, cwd, env, log_path, timeout):
    receipt = {"command": command, "cwd": str(cwd), "timeout_seconds": timeout,
               "started_at": datetime.now(timezone.utc).isoformat(),
               "environment": {key: env[key] for key in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE",
                                "MEMORY_BOOK_TEXT_BACKEND", "CC", "TIKTOKEN_CACHE_DIR") if key in env},
               "log": log_path.name, "timed_out": False}
    with log_path.open("xb") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            receipt["returncode"] = process.wait(timeout=timeout)
        except BaseException as error:
            receipt["timed_out"] = isinstance(error, subprocess.TimeoutExpired)
            receipt["interruption"] = {"type": type(error).__name__, "message": str(error)}
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            receipt["returncode"] = process.returncode
            if not isinstance(error, subprocess.TimeoutExpired):
                write(log_path.with_suffix(".exit.json"), receipt)
                raise
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    write(log_path.with_suffix(".exit.json"), receipt)
    return receipt


def preserve(output):
    """Compress logs/JSONL losslessly; retain byte hashes and all failed prefixes."""
    compressed = {}
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.suffix not in (".log", ".jsonl"):
            continue
        raw = path.read_bytes()
        destination = path.with_name(path.name + ".gz")
        with destination.open("xb") as handle:
            handle.write(gzip.compress(raw, mtime=0))
        stored = destination.read_bytes()
        if gzip.decompress(stored) != raw:
            raise ValueError("Lossless artifact compression failed")
        compressed[path.relative_to(output).as_posix()] = {
            "bytes": len(raw), "sha256": sha(raw),
            "stored_as": destination.relative_to(output).as_posix(), "stored_sha256": sha(stored)}
        path.unlink()
    return compressed


def run(args):
    source, output = args.candidate_source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "v013-unchanged-legacy-gate-v1", "gate": args.gate,
              "status": "started", "accepted": False, "candidate_commit": args.candidate_commit,
              "baseline_commit": BASELINE if args.gate == "engineering" else None,
              "scope": "Authored correctness/compatibility replay; no third-party rerun or performance claim.",
              "started_at": datetime.now(timezone.utc).isoformat(), "attempts": [],
              "environment": {"python": sys.version, "executable": sys.executable,
                              "platform": platform.platform(), "sqlite": sqlite3.sqlite_version}}
    write(output / "execution.json", report)
    sources = {"candidate": (source, args.candidate_commit)}
    if args.gate == "engineering":
        if args.baseline_source is None:
            raise ValueError("Engineering gate requires --baseline-source")
        sources = {"baseline": (args.baseline_source.resolve(), BASELINE), **sources}
    try:
        report["source_before"] = {label: source_identity(path, commit) for label, (path, commit) in sources.items()}
        report["inputs_before"] = evaluator_binding(args.gate, source, args.candidate_commit)
        report["environment"]["dependencies"] = {}
        for name in ("mcp", "tiktoken", "numpy", "tomlkit", "build", "setuptools", "wheel"):
            try:
                report["environment"]["dependencies"][name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                report["environment"]["dependencies"][name] = None
        if args.gate == "full-suite" and any(report["environment"]["dependencies"][name] is None
                                             for name in ("mcp", "tiktoken", "numpy", "tomlkit", "build")):
            raise ValueError("Required full-suite optional dependencies are missing")
        write(output / "execution.json", report)

        def execute(label, path, commit, backend, command, timeout=600):
            env = command_env(path, backend, args.gate)
            probe = [sys.executable, str(SELF), "--worker", "probe", "--candidate-source", str(path),
                     "--candidate-commit", commit, "--backend", backend, "--output", str(output / (label + "-import.json"))]
            probe_receipt = run_command(probe, path, env, output / (label + "-import.log"), 60)
            if probe_receipt["returncode"] != 0 or probe_receipt["timed_out"]:
                raise ValueError("Actual runtime/native import check failed: " + label)
            receipt = run_command(command, path, env, output / (label + ".log"), timeout)
            report["attempts"].append({"label": label, "backend": backend, **receipt})
            write(output / "execution.json", report)
            if receipt["returncode"] != 0 or receipt["timed_out"]:
                raise ValueError("Gate failed; original log and partial responses preserved: " + label)

        if args.gate == "engineering":
            from scripts.validate_v012_engineering import compare, rows
            for label, (path, commit) in sources.items():
                execute(label, path, commit, "native", [sys.executable, str(SELF), "--worker", "engineering",
                        "--candidate-source", str(path), "--candidate-commit", commit,
                        "--backend", "native", "--output", str(output / label)])
            report["comparisons"] = {name: compare(rows(output / "baseline" / name / "raw.jsonl"),
                                                    rows(output / "candidate" / name / "raw.jsonl"))
                                     for name in ("native", "common-block")}
            if [report["comparisons"][name]["responses"] for name in ("native", "common-block")] != [640, 160]:
                raise ValueError("The unchanged 800-response matrix is incomplete")
            report["accepted"] = all(not value["regressions"] for value in report["comparisons"].values())
        elif args.gate in ("short-page", "directory"):
            report["summaries"] = {}
            for backend in ("python", "native"):
                target = output / backend
                if args.gate == "short-page":
                    command = [sys.executable, str(ROOT / "benchmarks/v012_short_page_guard_eval.py"),
                               "--source", str(source), "--commit", args.candidate_commit,
                               "--backend", backend, "--output", str(target)]
                else:
                    command = [sys.executable, str(ROOT / "benchmarks/directory_navigation.py"),
                               "--protocol-v2", "--output", str(target)]
                execute(backend, source, args.candidate_commit, backend, command)
                saved = json.loads((target / "report.json").read_bytes())
                report["summaries"][backend] = saved["summary"]
                if args.gate == "short-page":
                    from benchmarks.v012_short_page_guard_eval import validate_rows
                    raw = gzip.decompress((target / "raw.jsonl.gz").read_bytes())
                    if sha(raw) != saved["raw_sha256"] or sha((target / "raw.jsonl.gz").read_bytes()) != saved["archive_sha256"]:
                        raise ValueError("Short-page raw evidence hash differs")
                    checked = validate_rows([json.loads(line) for line in raw.splitlines()])
                    if checked != saved["summary"] or saved["status"] != "completed" or saved["accepted"] is not True:
                        raise ValueError("Short-page saved-response gate differs or failed")
                elif saved["status"] != "passed" or saved["summary"]["logical_cases"] != 119:
                    raise ValueError("Original directory-v2 gate failed or is incomplete")
            report["accepted"] = True
        else:
            execute("unittest", source, args.candidate_commit, "native", [sys.executable, str(SELF),
                    "--worker", "unittest", "--candidate-source", str(source),
                    "--candidate-commit", args.candidate_commit, "--backend", "native",
                    "--output", str(output / "unittest")], timeout=1200)
            report["summary"] = json.loads((output / "unittest/result.json").read_bytes())
            report["accepted"] = report["summary"]["successful"]
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", accepted=False, error={"type": type(error).__name__, "message": str(error)})
    finally:
        try:
            report["source_after"] = {label: source_identity(path, commit) for label, (path, commit) in sources.items()}
            report["inputs_after"] = evaluator_binding(args.gate, source, args.candidate_commit)
            report["source_unchanged"] = report.get("source_before") == report["source_after"]
            report["inputs_unchanged"] = report.get("inputs_before") == report["inputs_after"]
            if not report["source_unchanged"] or not report["inputs_unchanged"]:
                raise ValueError("Source or evaluator/test inputs changed")
        except BaseException as error:
            report.update(status="failed", accepted=False,
                          final_identity_error={"type": type(error).__name__, "message": str(error)})
        report["compression_manifest"] = preserve(output)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(output / "execution.json", report)
    print(json.dumps({"status": report["status"], "accepted": report["accepted"], "output": str(output)}))
    return 0 if report["accepted"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=("engineering", "short-page", "directory", "full-suite"), default="engineering")
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=("engineering", "probe", "unittest"))
    parser.add_argument("--backend", choices=("python", "native"), default="native")
    args = parser.parse_args()
    return worker(args) if args.worker else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
