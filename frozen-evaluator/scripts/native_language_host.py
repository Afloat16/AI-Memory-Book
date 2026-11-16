"""Prepare pinned sources and run the first native-language paired experiment."""

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
PLAN = ROOT / "benchmarks/experiments/native_language_formal_plan.json"
WORK = ROOT / ".artifacts/native-language-formal"
OUTPUT = ROOT / "benchmarks/reports/native-language/formal-run-1"
LOCOMO_URL = "https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json"
LOCOMO_SHA256 = "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
LOCOMO_BYTES = 2805274


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def materialize(commit, destination):
    destination.mkdir()
    names = git("ls-tree", "-r", "--name-only", commit, "src/memory_book",
                "pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in", "README.md", "LICENSE").decode().splitlines()
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git("show", commit + ":" + name))


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/validation/native-language-formal-1"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "Use the dedicated first-attempt hosted execution")
    require(not WORK.exists() and not OUTPUT.exists(), "Never replace an earlier experiment directory")
    plan = json.loads(PLAN.read_text())
    WORK.mkdir(parents=True)
    for label, specification in plan["sources"].items():
        commit = specification["commit"]
        subprocess.run(["git", "fetch", "--depth=1", "origin", commit], cwd=ROOT, check=True)
        materialize(commit, WORK / label)
    environment = os.environ.copy()
    environment.update(MEMORY_BOOK_BUILD_NATIVE="1", CC="gcc", PYTHONDONTWRITEBYTECODE="1")
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    command = [sys.executable, "setup.py", "build_ext", "--inplace"]
    build = subprocess.run(command, cwd=WORK / "candidate", env=environment,
                           capture_output=True, text=True, timeout=120)
    (WORK / "build.log").write_text(build.stdout + build.stderr)
    require(build.returncode == 0, "Forced native build failed; retained build.log")
    compiler = subprocess.check_output(["gcc", "--version"], text=True)
    manifest = {
        "command": command, "compiler": compiler,
        "flags": {"extra_compile_args": ["-O3"], "CC": "gcc", "MEMORY_BOOK_BUILD_NATIVE": "1",
                  "sysconfig": {key: sysconfig.get_config_var(key) for key in ("CC", "CFLAGS", "CCSHARED", "LDSHARED", "EXT_SUFFIX")},
                  "environment": {key: environment.get(key) for key in ("CFLAGS", "CPPFLAGS", "LDFLAGS")}},
        "build_log_sha256": hashlib.sha256((WORK / "build.log").read_bytes()).hexdigest(),
        "host_preparation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": platform.python_version(), "platform": platform.platform(),
        "workflow_run_id": os.environ["GITHUB_RUN_ID"], "workflow_run_attempt": 1,
        "workflow_commit": os.environ["GITHUB_SHA"],
    }
    (WORK / "build-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with urlopen(LOCOMO_URL, timeout=60) as response:
        raw = response.read(LOCOMO_BYTES + 1)
    require(len(raw) == LOCOMO_BYTES and hashlib.sha256(raw).hexdigest() == LOCOMO_SHA256,
            "Pinned public input size or SHA-256 differs")
    locomo = WORK / "locomo10.json"
    locomo.write_bytes(raw)
    import tiktoken
    require(tiktoken.__version__ == "0.12.0", "Unexpected reference tokenizer")
    tiktoken.get_encoding("cl100k_base").encode("Prepare vocabulary before timed workers.")
    subprocess.run([sys.executable, "-u", "scripts/native_language_performance.py",
                    "--plan", str(PLAN), "--baseline-src", str(WORK / "baseline/src"),
                    "--candidate-src", str(WORK / "candidate/src"), "--build-manifest", str(WORK / "build-manifest.json"),
                    "--locomo-path", str(locomo), "--output", str(OUTPUT)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/native_language_performance.py", "--audit", str(OUTPUT)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
