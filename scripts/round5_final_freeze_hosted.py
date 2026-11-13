"""Source-free hosted certificate and formal-binding preparation.

This controller never loads a corpus, calls recall, ingests, or runs a model.
It preserves the existing registered generators and publishes each prerequisite.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ATTEMPT = "round5-final-freeze-hosted-1"
BRANCH = "validation/v033-final-freeze-hosted-1"
TRIGGER = "refs/heads/ci/v033-final-freeze-hosted-1"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SELECTION = ROOT / "benchmarks/experiments/round5-selected-runtime.json"
SCOPE = ROOT / "benchmarks/experiments/round5-final-freeze-hosted-scope.json"
CERTIFICATE = ROOT / "benchmarks/experiments/round5-final-interface-certificate.json"
BINDING = ROOT / "benchmarks/experiments/round5-performance-v2-binding.json"
BASELINE = {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
    "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"}
FILES = ("scripts/round5_final_freeze_hosted.py", "tests/test_round5_final_freeze_hosted.py",
    ".github/workflows/round5-final-freeze-hosted.yml",
    "benchmarks/experiments/round5-final-freeze-hosted-scope.json")


class PublicationError(RuntimeError):
    pass


class StageError(RuntimeError):
    def __init__(self, stage, published_head):
        super().__init__("Source-free stage failed: " + stage)
        self.published_head = published_head


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT,
                                   timeout=120, text=True).strip()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def validate_selection(value):
    require(type(value) is dict and value.get("schema_version") == 1
        and value.get("status") == "selected-after-development-before-final-evaluation",
        "A reviewed, committed final runtime selection is required")
    require(value.get("baseline") == BASELINE, "Published v0.3.2 baseline changed")
    candidate = value.get("candidate", {})
    require(type(candidate) is dict and set(candidate) == {"commit", "runtime_sha256"}
        and re.fullmatch(r"[0-9a-f]{40}", candidate.get("commit", ""))
        and re.fullmatch(r"[0-9a-f]{64}", candidate.get("runtime_sha256", "")),
        "Invalid final candidate identity")
    files = value.get("candidate_files_sha256")
    require(type(files) is dict and files and all(
        type(path) is str and path.startswith("src/memory_book/")
        and ".." not in Path(path).parts and re.fullmatch(r"[0-9a-f]{64}", checksum)
        for path, checksum in files.items()), "Complete candidate file inventory is required")
    for key in ("development_evidence", "independent_source_review"):
        evidence = value.get(key)
        require(type(evidence) is list and evidence, "Missing source-selection evidence: " + key)
        for item in evidence:
            require(type(item) is dict and set(item) == {"commit", "path", "sha256"}
                and re.fullmatch(r"[0-9a-f]{40}", item.get("commit", ""))
                and type(item.get("path")) is str
                and item["path"].startswith("benchmarks/reports/")
                and ".." not in Path(item["path"]).parts
                and re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")),
                "Invalid immutable selection evidence")
    require(value.get("fresh_metadata_selected") is False
        and value.get("fresh_content_decoded") is False
        and value.get("formal_measurement_started") is False,
        "Final source must be selected before fresh/formal execution")
    return value


def parse_remote(raw):
    values = raw.split()
    if not values:
        return None
    if len(values) != 2 or values[1] != "refs/heads/" + BRANCH or not re.fullmatch(r"[0-9a-f]{40}", values[0]):
        raise PublicationError("Unexpected result-ref response")
    return values[0]


def remote_head():
    return parse_remote(git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH))


def allowed(path):
    return path.startswith(relative(PUBLIC) + "/") or path in (relative(CERTIFICATE), relative(BINDING))


def publish(message, expected):
    try:
        if remote_head() != expected:
            raise PublicationError("Result branch changed or attempt is already owned")
        if expected is not None and git("rev-parse", "HEAD") != expected:
            raise PublicationError("Local ancestry changed")
        if git("diff", "--cached", "--name-only"):
            raise PublicationError("Unrelated staged files")
        targets = [relative(PUBLIC)]
        targets.extend(relative(path) for path in (CERTIFICATE, BINDING) if path.exists())
        subprocess.run(["git", "add", "--sparse", "--", *targets], cwd=ROOT, check=True)
        staged = git("diff", "--cached", "--name-only").splitlines()
        if not staged or not all(allowed(path) for path in staged):
            raise PublicationError("Missing or unrelated checkpoint changes")
        subprocess.run(["git", "commit", "-m", message + " [skip ci]"], cwd=ROOT, check=True)
        head = git("rev-parse", "HEAD")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        observed = remote_head()
        if pushed.returncode or observed != head:
            raise PublicationError("Push did not verify at its exact new head; returncode=" + str(pushed.returncode))
        print(json.dumps({"checkpoint": head, "branch": BRANCH, "message": message}), flush=True)
        return head
    except BaseException as error:
        marker = PUBLIC / "publication-failure.json"
        if not marker.exists():
            save(marker, {"at": stamp(), "expected_previous": expected,
                "error": type(error).__name__ + ": " + str(error),
                "policy": "No write or generation retry; preserve through the workflow artifact."})
        raise


def committed(path, commit="HEAD"):
    require(path.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":" + relative(path)], cwd=ROOT, timeout=60),
        "Commit exact file before generation: " + relative(path))


def fetch(commit):
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", commit], cwd=ROOT, check=True, timeout=120)


def prepare_source(label, identity, files=None):
    fetch(identity["commit"])
    location = STATE / "sources" / label
    location.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "worktree", "add", "--no-checkout", "--detach",
                    str(location), identity["commit"]], cwd=ROOT, check=True)
    subprocess.run(["git", "-C", str(location), "sparse-checkout", "set", "src"], check=True)
    subprocess.run(["git", "-C", str(location), "read-tree", "-mu", "HEAD"], check=True)
    from scripts.round5_performance_v2 import source_identity
    require(source_identity(location / "src") == identity, "Exported runtime source/provenance changed")
    if files is not None:
        actual = {path.relative_to(location).as_posix(): sha(path)
                  for path in sorted((location / "src/memory_book").rglob("*")) if path.is_file()}
        require(actual == files, "Candidate source inventory changed")
    return location / "src"


def command_stage(name, command, expected, artifacts=()):
    save(PUBLIC / (name + ".intent.json"), {"status": "intent-before-single-use-launch",
        "at": stamp(), "argv": command, "prior_publication_commit": expected,
        "retrieval_calls_executed": 0})
    expected = publish("bench: claim source-free " + name, expected)
    result, failure = None, None
    try:
        with (PUBLIC / (name + ".log")).open("xb") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log,
                stderr=subprocess.STDOUT, timeout=300).returncode
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)
    attempt_root = ROOT / ".artifacts/round5-interface-certificate"
    if name == "interface" and attempt_root.exists():
        shutil.copytree(attempt_root, PUBLIC / "interface-attempts")
    save(PUBLIC / (name + ".exit.json"), {"at": stamp(), "returncode": result, "error": failure,
        "outputs_sha256": {relative(path): sha(path) for path in artifacts if path.exists()},
        "retrieval_calls_executed": 0, "policy": "Keep all observations; never replay this stage."})
    expected = publish("bench: preserve source-free " + name + " outcome", expected)
    if result != 0 or failure is not None:
        raise StageError(name, expected)
    return expected


def run():
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and os.environ.get("GITHUB_REF") == TRIGGER,
        "Only the registered first hosted attempt may run")
    selection = validate_selection(read(SELECTION))
    committed(SELECTION)
    for name in FILES:
        committed(ROOT / name)
    require(not PUBLIC.exists() and not STATE.exists() and not CERTIFICATE.exists() and not BINDING.exists(),
        "Existing attempt, certificate or binding must not be overwritten")
    require(remote_head() is None, "Final freeze attempt is already claimed")
    STATE.mkdir(parents=True)
    PUBLIC.mkdir(parents=True)
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    expected = None
    stage = "claim"
    try:
        save(PUBLIC / "attempt.intent.json", {"status": "claimed", "at": stamp(),
            "attempt": ATTEMPT, "workflow_commit": os.environ["GITHUB_SHA"],
            "run_id": os.environ["GITHUB_RUN_ID"], "selection_sha256": sha(SELECTION),
            "controller_files_sha256": {name: sha(ROOT / name) for name in FILES},
            "selection": selection, "retrieval_calls_executed": 0})
        expected = publish("bench: claim source-free final runtime freeze", expected)
        stage = "verify-evidence-and-source"
        for items in (selection["development_evidence"], selection["independent_source_review"]):
            for item in items:
                fetch(item["commit"])
                content = subprocess.check_output(["git", "show", item["commit"] + ":" + item["path"]], cwd=ROOT, timeout=60)
                require(hashlib.sha256(content).hexdigest() == item["sha256"], "Selection evidence bytes changed")
        from scripts import round5_performance_v2 as performance
        for commit in (performance.PLAN_COMMIT, performance.ADDENDUM_COMMIT,
                       performance.CANONICAL_ADDENDUM_COMMIT, performance.DERIVED_ADDENDUM_COMMIT):
            fetch(commit)
        sources = {"baseline": prepare_source("baseline", selection["baseline"]),
                   "candidate": prepare_source("candidate", selection["candidate"], selection["candidate_files_sha256"])}
        performance.load_plan()
        stage = "interface"
        expected = command_stage(stage, [sys.executable, "scripts/round5_interface_certificate.py",
            "--baseline-src", str(sources["baseline"]), "--candidate-src", str(sources["candidate"]),
            "--output", str(CERTIFICATE)], expected, (CERTIFICATE,))
        committed(CERTIFICATE)
        stage = "formal-binding"
        expected = command_stage(stage, [sys.executable, "scripts/round5_performance_v2.py",
            "--bind", str(BINDING), "--baseline-src", str(sources["baseline"]),
            "--candidate-src", str(sources["candidate"])], expected, (BINDING,))
        committed(BINDING)
        performance.load_binding(BINDING)
        save(PUBLIC / "completion.json", {"status": "completed", "at": stamp(),
            "sources": {"baseline": selection["baseline"], "candidate": selection["candidate"]},
            "certificate_sha256": sha(CERTIFICATE), "binding_sha256": sha(BINDING),
            "retrieval_calls_executed": 0, "formal_measurement_started": False,
            "fresh_metadata_selected": False, "release_accepted": False})
        publish("bench: complete source-free final runtime freeze", expected)
    except BaseException as error:
        if isinstance(error, StageError):
            expected = error.published_head
        if PUBLIC.exists() and not (PUBLIC / "failure.json").exists():
            save(PUBLIC / "failure.json", {"status": "failed_or_incomplete", "at": stamp(), "stage": stage,
                "error": type(error).__name__ + ": " + str(error),
                "retrieval_calls_executed": 0, "policy": "No automatic generation or publication retry."})
        if PUBLIC.exists() and not (PUBLIC / "publication-failure.json").exists():
            publish("bench: preserve source-free final freeze failure", expected)
        raise


if __name__ == "__main__":
    run()
