"""Explicitly bind the one registered fixed-candidate infrastructure recovery."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.round2_eval import (BINDING, INITIAL_BINDING_SHA256, PLAN, RECOVERY,
    RECOVERY_STATUS, atomic, evaluator_sources, now, recovery_inputs, sha)
from benchmarks.run import engine_source_hash
from benchmarks.token_compare import checkout_provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-src", type=Path, required=True)
    args = parser.parse_args()
    if sha(BINDING) != INITIAL_BINDING_SHA256:
        raise ValueError("This recovery may replace only the byte-identical initial binding, once")
    plan = json.loads(PLAN.read_bytes())
    original, _ = recovery_inputs(plan)
    source = args.candidate_src.resolve() / "memory_book"
    provenance = checkout_provenance(source)
    if (provenance["git_commit"] != original["candidate"]["commit"]
            or provenance["commit_identifies_source"] is not True
            or engine_source_hash(source) != original["candidate"]["source_sha256"]):
        raise ValueError("Recovery must execute exactly the original candidate commit and bytes")
    files = evaluator_sources()
    subprocess.run(["git", "ls-files", "--error-unmatch", "--", *files], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", *files], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    value = copy.deepcopy(original)
    value.pop("frozen_at")
    value.update(status=RECOVERY_STATUS, bound_at=now(), candidate_first_frozen_at=original["frozen_at"],
        initial_binding_sha256=INITIAL_BINDING_SHA256, recovery_registration_sha256=sha(RECOVERY),
        evaluator_sha256=files,
        policy="Fixed candidate and every registered parameter from the original pre-scoring binding. The selection was already scored by an incomplete run. Only the registered native response contract and recovery audit changed; rerun the entire matrix on one new host, never pool timings or select the faster run.")
    recovery_inputs(plan, value)
    atomic(BINDING, value)
    print(json.dumps({"status": value["status"], "candidate": value["candidate"],
        "binding_sha256": sha(BINDING), "initial_binding_sha256": INITIAL_BINDING_SHA256,
        "next": "Save and review this recovery binding before updating the measurement trigger branch."}))


if __name__ == "__main__":
    main()
