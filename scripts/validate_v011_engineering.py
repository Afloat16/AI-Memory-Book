"""Replay the unchanged engineering fixture on two explicit runtime snapshots.

This is a development/regression quality comparison. Diagnostic timers are
retained, but this single replay is not a performance or third-party rerun.
Both runtimes execute the original evaluators and independent score checker.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "234891619d7bed88ddf3fae37e7f3e1b14a808b6"
PROTOCOL = "v011-engineering-regression-v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def identity(package):
    source = {p.relative_to(package).as_posix(): sha(p.read_bytes())
              for p in sorted(package.rglob("*"))
              if p.is_file() and p.suffix in {".py", ".c", ".h"}}
    binaries = {p.name: sha(p.read_bytes()) for p in sorted(package.glob("_native*"))
                if p.suffix in {".so", ".pyd"}}
    return {"files": source, "native_extensions": binaries,
            "sha256": sha(json.dumps(source, sort_keys=True).encode())}


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def worker(output):
    sys.path.append(str(ROOT))
    import memory_book
    from memory_book._text_backend import BACKEND_NAME
    from benchmarks import engineering_workflow as workflow, memory_systems
    from scripts.verify_current_readme_results import independent_scores, quality
    package = Path(memory_book.__file__).resolve().parent
    before = identity(package)
    output.mkdir(parents=True, exist_ok=False)
    proof = {"status": "started", "runtime": before, "package_path": str(package),
             "version": memory_book.__version__, "backend": BACKEND_NAME,
             "python": sys.version, "platform": platform.platform()}
    write(output / "runtime.json", proof)
    try:
        native = workflow.run(output / "native", budgets=(1200, 2400), repeats=1)
        common = memory_systems.run(output / "common-block", output / "cache",
                                    budgets=(1200, 2400), repeats=1, backends=("book",))
        actual = rows(output / "native/raw.jsonl") + rows(output / "common-block/raw.jsonl")
        if len(actual) != 800:
            raise ValueError("Expected exactly 640 native and 160 common-block responses")
        independent = independent_scores(actual, workflow.workload())
        if independent["failures"] or native["status"] != "completed" or common["status"] != "completed":
            raise ValueError("Replay or independent evidence/source/budget scoring failed")
        proof.update(status="completed", independent_scores=independent,
                     native_quality=quality(actual[:640]), common_quality=quality(actual[640:]),
                     runtime_unchanged=before == identity(package))
        if not proof["runtime_unchanged"]:
            raise ValueError("Runtime changed during replay")
    except Exception as error:
        proof.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        write(output / "runtime.json", proof)


def compare(before, after):
    key = lambda row: (row["case_id"], row["backend"], row["budget_chars"])
    old, new = {key(row): row for row in before}, {key(row): row for row in after}
    if len(old) != len(before) or len(new) != len(after) or old.keys() != new.keys():
        raise ValueError("Response matrix changed or contains duplicates")
    changes, regressions = [], []
    for cell, row in new.items():
        prior = old[cell]
        if prior["score"] != row["score"]:
            changes.append({"case": cell, "before": prior["score"], "after": row["score"]})
        a, b = prior["score"], row["score"]
        # Preserve every answerable case and required support, not just totals.
        loss = (b["matched_evidence"] < a["matched_evidence"]
                or (a["complete_evidence"] and not b["complete_evidence"])
                or (not a["stale_only"] and b["stale_only"])
                or (a.get("fixed_consumer", {}).get("all_passed") is True
                    and b.get("fixed_consumer", {}).get("all_passed") is not True))
        if loss:
            regressions.append({"case": cell, "before": a, "after": b})
    return {"responses": len(after), "score_changes": changes, "regressions": regressions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--candidate-source", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args.output.resolve())
        return
    if args.baseline_source is None:
        parser.error("--baseline-source is required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline = args.baseline_source.resolve()
    expected = git("ls-tree", "-r", "--name-only", BASELINE, "src/memory_book").decode().splitlines()
    for path in expected:
        if (baseline / path).read_bytes() != git("show", BASELINE + ":" + path):
            raise ValueError("Baseline source differs: " + path)
    candidate = args.candidate_source.resolve()
    candidate_commit = args.candidate_commit or git("rev-parse", "HEAD").decode().strip()
    candidate_files = git("ls-tree", "-r", "--name-only", candidate_commit, "src/memory_book").decode().splitlines()
    for path in candidate_files:
        if (candidate / path).read_bytes() != git("show", candidate_commit + ":" + path):
            raise ValueError("Candidate source differs from the committed snapshot: " + path)
    for source, names in ((baseline, expected), (candidate, candidate_files)):
        actual = {p.relative_to(source).as_posix() for p in (source / "src/memory_book").rglob("*")
                  if p.is_file() and p.suffix in {".py", ".c", ".h"}}
        if actual != {name for name in names if Path(name).suffix in {".py", ".c", ".h"}}:
            raise ValueError("Runtime source inventory differs from its Git snapshot")
    report = {"protocol": PROTOCOL, "status": "started", "baseline_commit": BASELINE,
              "candidate_commit": candidate_commit,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "driver_sha256": sha(Path(__file__).read_bytes()),
              "scope": "Fixed authored development/regression fixture; no external engine rerun, no latency claim",
              "settings": {"budgets": [1200, 2400], "repeats": 1, "expected_responses_per_runtime": 800},
              "attempts": []}
    write(output / "comparison.json", report)
    try:
        for label, source in (("baseline", baseline), ("candidate", candidate)):
            attempt = {"label": label, "status": "started"}
            report["attempts"].append(attempt)
            write(output / "comparison.json", report)
            env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(source / "src"), str(ROOT))),
                   "PYTHONDONTWRITEBYTECODE": "1", "MEMORY_BOOK_TEXT_BACKEND": "native"}
            with (output / (label + ".log")).open("w", encoding="utf-8") as log:
                result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                                         "--output", str(output / label)], cwd=ROOT,
                                        env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            attempt.update(returncode=result.returncode, status="completed" if result.returncode == 0 else "failed")
            write(output / "comparison.json", report)
            if result.returncode:
                raise RuntimeError(label + " replay failed; retain its log and partial responses")
        report["comparisons"] = {name: compare(rows(output / "baseline" / name / "raw.jsonl"),
                                               rows(output / "candidate" / name / "raw.jsonl"))
                                 for name in ("native", "common-block")}
        report["accepted"] = all(not item["regressions"] for item in report["comparisons"].values())
        report["status"] = "completed"
    except Exception as error:
        report.update(status="failed", accepted=False,
                      error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        manifest = {}
        for path in sorted(output.rglob("*.jsonl")):
            raw = path.read_bytes()
            compressed = path.with_suffix(path.suffix + ".gz")
            compressed.write_bytes(gzip.compress(raw, mtime=0))
            manifest[path.relative_to(output).as_posix()] = {
                "bytes": len(raw), "sha256": sha(raw),
                "stored_as": compressed.relative_to(output).as_posix(),
                "stored_sha256": sha(compressed.read_bytes())}
            path.unlink()
        report["raw_manifest"] = manifest
        write(output / "comparison.json", report)
    print(json.dumps({"status": report["status"], "accepted": report["accepted"], "output": str(output)}))


if __name__ == "__main__":
    main()
