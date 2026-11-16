"""Build both frozen native sources and execute the native-core matrix once."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import native_core_performance as perf

PLAN = ROOT / "benchmarks/experiments/native_core_formal_plan.json"
WORK = ROOT / ".artifacts/native-core-formal"
OUTPUT = ROOT / "benchmarks/reports/native-core/formal-run-1"
BRANCH = "validation/native-core-formal-1"
LOCOMO_URL = "https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json"
LOCOMO_SHA256 = "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
LOCOMO_BYTES = 2805274


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def checkpoint(stage, **details):
    WORK.mkdir(parents=True, exist_ok=True)
    value = {"stage": stage,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_commit": os.environ.get("GITHUB_SHA"), **details}
    with (WORK / "preparation.events.jsonl").open("ab") as events:
        events.write((perf.dump(value) + "\n").encode())
        events.flush()
        os.fsync(events.fileno())
    perf.write(WORK / "preparation.json", value)


def materialize(commit, destination):
    destination.mkdir()
    names = git("ls-tree", "-r", "--name-only", commit, "src/memory_book",
                "pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in", "README.md", "LICENSE").decode().splitlines()
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git("show", commit + ":" + name))


def build_input_identity(destination, specification):
    names = git("ls-tree", "-r", "--name-only", specification["commit"],
                "src/memory_book", *perf.BUILD_FILES).decode().splitlines()
    configurations, native_sources = {}, {}
    for name in names:
        if name not in perf.BUILD_FILES and not (
                name.startswith("src/memory_book/") and Path(name).suffix in {".c", ".h"}):
            continue
        raw = (destination / name).read_bytes()
        perf.require(raw == git("show", specification["commit"] + ":" + name),
                     "Build input differs before compilation: " + name)
        target = configurations if name in perf.BUILD_FILES else native_sources
        target[name] = perf.sha(raw)
    perf.require("setup.py" in configurations and "src/memory_book/_native.c" in native_sources,
                 "Missing required native build inputs")
    return configurations, native_sources


def build_sources(plan):
    environment = os.environ.copy()
    environment.update(MEMORY_BOOK_BUILD_NATIVE="1", CC="gcc", PYTHONDONTWRITEBYTECODE="1")
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    command = [sys.executable, "setup.py", "build_ext", "--inplace"]
    compiler = subprocess.check_output(["gcc", "--version"], text=True)
    flags = {"extra_compile_args": ["-O3"], "CC": "gcc", "MEMORY_BOOK_BUILD_NATIVE": "1",
             "sysconfig": {key: sysconfig.get_config_var(key) for key in ("CC", "CFLAGS", "CCSHARED", "LDSHARED", "EXT_SUFFIX")},
             "environment": {key: environment.get(key) for key in ("CFLAGS", "CPPFLAGS", "LDFLAGS")}}
    manifest = {"schema_version": 3, "status": "preparing", "builds": {},
        "host_preparation_sha256": perf.sha(Path(__file__).read_bytes()),
        "python": platform.python_version(), "platform": platform.platform(),
        "workflow_run_id": os.environ["GITHUB_RUN_ID"], "workflow_run_attempt": 1,
        "workflow_commit": os.environ["GITHUB_SHA"]}
    perf.write(WORK / "build-manifest.json", manifest)
    for label, specification in plan["sources"].items():
        checkpoint("building", label=label)
        destination = WORK / label
        configurations, native_sources = build_input_identity(destination, specification)
        record = {"status": "started", "source_commit": specification["commit"], "backend": "native",
                  "command": command, "compiler": compiler, "flags": flags,
                  "build_inputs": configurations, "native_source_inputs": native_sources}
        manifest["builds"][label] = record
        perf.write(WORK / "build-manifest.json", manifest)
        with (destination / "build.log").open("xb") as log:
            result = subprocess.run(command, cwd=destination, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=120)
        record.update(status="completed" if result.returncode == 0 else "failed", returncode=result.returncode,
                      build_log_sha256=perf.sha((destination / "build.log").read_bytes()))
        if result.returncode == 0:
            record["native_binaries"] = perf.source_manifest(destination / "src", specification)["native_binaries"]
        perf.write(WORK / "build-manifest.json", manifest)
        perf.require(result.returncode == 0, "Forced native build failed; retained " + label + "/build.log")
        checkpoint("probing", label=label)
        with (destination / "probe.json").open("xb") as output, (destination / "probe.log").open("xb") as log:
            probe = subprocess.run([sys.executable, "scripts/native_core_performance.py",
                "--plan", str(PLAN), "--probe-label", label, "--source", str(destination / "src")],
                cwd=ROOT, env=environment, stdout=output, stderr=log, timeout=120)
        record["probe_returncode"] = probe.returncode
        perf.write(WORK / "build-manifest.json", manifest)
        perf.require(probe.returncode == 0, "Native helper preflight failed; retained " + label + "/probe.log")
        identity = perf.read(destination / "probe.json")
        perf.require(identity["binary_sha256"] in record["native_binaries"].values(), "Preflight loaded the wrong native binary")
        record["probe_sha256"] = perf.sha((destination / "probe.json").read_bytes())
        perf.write(WORK / "build-manifest.json", manifest)
    probes = [perf.read(WORK / label / "probe.json") for label in plan["sources"]]
    perf.require(probes[0]["dispatch_probe"]["outputs_sha256"] == probes[1]["dispatch_probe"]["outputs_sha256"],
                 "Public-wrapper preflight outputs differ")
    manifest["status"] = "completed"
    perf.write(WORK / "build-manifest.json", manifest)


def main():
    perf.require(os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
        and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH
        and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "Use the dedicated first-attempt hosted execution")
    perf.require(git("rev-parse", "HEAD").decode().strip() == os.environ.get("GITHUB_SHA"), "Checkout differs from workflow commit")
    perf.require(not WORK.exists() and not OUTPUT.exists(), "Never replace an earlier experiment directory")
    try:
        checkpoint("validating_frozen_plan")
        plan = perf.validate_plan(perf.read(PLAN))
        perf.evaluator_manifest(PLAN)
        for label, specification in plan["sources"].items():
            checkpoint("materializing", label=label, source_commit=specification["commit"])
            subprocess.run(["git", "fetch", "--depth=1", "origin", specification["commit"]], cwd=ROOT, check=True)
            materialize(specification["commit"], WORK / label)
        build_sources(plan)
        checkpoint("loading_pinned_input")
        with urlopen(LOCOMO_URL, timeout=60) as response:
            raw = response.read(LOCOMO_BYTES + 1)
        perf.require(len(raw) == LOCOMO_BYTES and hashlib.sha256(raw).hexdigest() == LOCOMO_SHA256,
                     "Pinned public input size or SHA-256 differs")
        locomo = WORK / "locomo10.json"
        locomo.write_bytes(raw)
        import tiktoken
        perf.require(tiktoken.__version__ == "0.12.0", "Unexpected reference tokenizer")
        tiktoken.get_encoding("cl100k_base").encode("Prepare vocabulary before timed workers.")
        checkpoint("measuring")
        subprocess.run([sys.executable, "-u", "scripts/native_core_performance.py",
            "--plan", str(PLAN), "--baseline-src", str(WORK / "baseline/src"),
            "--candidate-src", str(WORK / "candidate/src"), "--build-manifest", str(WORK / "build-manifest.json"),
            "--locomo-path", str(locomo), "--output", str(OUTPUT)], cwd=ROOT, check=True)
        checkpoint("auditing")
        subprocess.run([sys.executable, "scripts/native_core_performance.py", "--audit", str(OUTPUT)], cwd=ROOT, check=True)
        checkpoint("completed")
    except BaseException as error:
        previous = perf.read(WORK / "preparation.json") if (WORK / "preparation.json").exists() else {}
        checkpoint("failed", last_stage=previous, error={"type": type(error).__name__, "message": str(error)})
        raise


if __name__ == "__main__":
    main()
