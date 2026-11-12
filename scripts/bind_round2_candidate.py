"""Bind one committed candidate after development, before any new cohort score."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.round2_eval import BINDING, PLAN, UPSTREAM_LOCKS, atomic, evaluator_sources, now, sha
from benchmarks.round2_data import MANIFEST
from benchmarks.run import engine_source_hash
from benchmarks.token_compare import checkout_provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-src", type=Path, required=True)
    parser.add_argument("--optional-semantic", action="store_true")
    args = parser.parse_args()
    if BINDING.exists():
        raise FileExistsError("Preserve the existing binding; this cohort is not a tuning loop")
    source = args.candidate_src.resolve() / "memory_book"
    provenance = checkout_provenance(source)
    if provenance["git_commit"] != args.candidate_commit or provenance["commit_identifies_source"] is not True:
        raise ValueError("Candidate source must exactly identify a committed runtime")
    files = evaluator_sources()
    subprocess.run(["git", "ls-files", "--error-unmatch", "--", *files], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", *files], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    value = {"schema_version": 1, "status": "frozen-before-scoring", "frozen_at": now(),
        "candidate": {"commit": args.candidate_commit, "source_sha256": engine_source_hash(source)},
        "optional_semantic": args.optional_semantic, "coverage": False,
        "upstream_locks": UPSTREAM_LOCKS,
        "plan_sha256": sha(PLAN), "cohort_manifest_sha256": sha(MANIFEST),
        "evaluator_sha256": files,
        "policy": "Candidate and optional-mode choice fixed before new heldout retrieval. No new questions or single-case results were used for implementation."}
    atomic(BINDING, value)
    print(json.dumps({"candidate": value["candidate"], "optional_semantic": args.optional_semantic,
                      "binding_sha256": sha(BINDING), "next": "Commit this binding before any scoring workflow."}))


if __name__ == "__main__":
    main()
