"""Bind the frozen row comparator to explicit baseline/candidate identities.

This adds no score, ranking, fixture or packing changes. It rejects a comparison
of different backends, two baseline runs, or falsely relabelled runtime bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from benchmarks import v012_revision_eval as evaluation


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def arm_identity(path, expected_commit):
    audit = evaluation.audit(path)
    report_file = path / "report.json"
    report = json.loads(report_file.read_text(encoding="utf-8"))
    source = report["source_before"]
    if source != report["source_after"] or source["commit"] != expected_commit:
        raise ValueError("Comparison arm is not the requested immutable commit")
    checkout = Path(report["imported_package"]).resolve().parents[2]
    package = checkout / "src/memory_book"
    if Path(report["imported_package"]).resolve() != package / "__init__.py":
        raise ValueError("Unexpected imported package path")
    names = subprocess.check_output(["git", "-C", str(checkout), "ls-tree", "-r", "--name-only",
                                     expected_commit, "src/memory_book"]).decode().splitlines()
    expected = {name: sha(subprocess.check_output(["git", "-C", str(checkout), "show", expected_commit + ":" + name]))
                for name in names}
    if not expected or source["files"] != expected:
        raise ValueError("Recorded runtime bytes differ from the requested Git source")
    loaded = report["loaded_native"]
    if report["backend"] == "native":
        if not loaded:
            raise ValueError("Native comparison arm did not record its loaded extension")
        binary = Path(loaded["path"])
        if binary.parent != package or source["native_extensions"].get(binary.name) != loaded["sha256"]:
            raise ValueError("Loaded native identity differs from the source snapshot record")
    elif report["backend"] != "python" or loaded is not None:
        raise ValueError("Comparison arm is not an explicit Python reference/native execution")
    return {"commit": expected_commit, "backend": report["backend"], "source": source,
            "imported_package": report["imported_package"], "loaded_native": loaded,
            "python": report["python"], "platform": report["platform"],
            "evaluator": report["evaluator"], "responses": audit["responses"],
            "report_sha256": sha(report_file.read_bytes()),
            "raw_archive_sha256": sha((path / "raw.jsonl.gz").read_bytes()), "summary": audit["summary"]}


def paired(baseline, candidate, candidate_commit):
    if candidate_commit == evaluation.BASELINE:
        raise ValueError("A second baseline execution is not a candidate comparison")
    before = arm_identity(baseline, evaluation.BASELINE)
    after = arm_identity(candidate, candidate_commit)
    if (before["backend"] != after["backend"] or before["python"] != after["python"]
            or before["platform"] != after["platform"] or before["evaluator"] != after["evaluator"]):
        raise ValueError("Comparison changes backend, interpreter, platform or frozen evaluator")
    return {"protocol": "v012-source-bound-pair-audit-v1", "status": "verified",
            "baseline": before, "candidate": after,
            "comparison": evaluation.compare(baseline, candidate),
            "scope": "Same-backend authored development comparison; no independent holdout or latency claim",
            "auditor_sha256": sha(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new result path; previous audits remain intact")
    result = paired(args.baseline.resolve(), args.candidate.resolve(), args.candidate_commit)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    comparison = result["comparison"]
    print(json.dumps({"status": result["status"], "backend": result["candidate"]["backend"],
                      "responses_per_arm": comparison["responses_per_arm"],
                      "regressions": len(comparison["regressions"]),
                      "relevance_payload_changes": len(comparison["relevance_payload_changes"])}))


if __name__ == "__main__":
    main()
