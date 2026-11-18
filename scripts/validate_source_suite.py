"""Preserve an exact-source unittest execution, including failures and skips.

This records the existing suite without changing its discovery or expectations.
Use a fresh output directory for every execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_v011_revision_recovery import source_identity


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(source, commit):
    names = subprocess.check_output(
        ["git", "-C", str(source), "ls-tree", "-r", "--name-only", commit,
         "tests", "scripts", "benchmarks", "pyproject.toml", "setup.py"]
    ).decode().splitlines()
    result = {}
    for name in names:
        if Path(name).suffix != ".py" and name not in {"pyproject.toml", "setup.py"}:
            continue
        expected = subprocess.check_output(["git", "-C", str(source), "show", commit + ":" + name])
        actual = (source / name).read_bytes()
        if actual != expected:
            raise ValueError("Test/build/evaluator source differs from commit: " + name)
        result[name] = sha(actual)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "started", "commit": args.commit,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "runner_sha256": sha(Path(__file__).read_bytes())}
    destination = output / "report.json"
    def save():
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save()
    try:
        report["source_before"] = source_identity(source, args.commit)
        report["test_inputs_before"] = inventory(source, args.commit)
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        environment = {"CC": "gcc", "PYTHONPATH": str(source / "src"),
                       "MEMORY_BOOK_TEXT_BACKEND": "native",
                       "TIKTOKEN_CACHE_DIR": str(source / ".artifacts/tokenizer-cache")}
        report.update(command=command, environment=environment)
        cache = Path(environment["TIKTOKEN_CACHE_DIR"])
        report["tokenizer_cache_files"] = {p.name: sha(p.read_bytes()) for p in sorted(cache.glob("*")) if p.is_file()}
        save()
        log = output / "unittest.log"
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=source, env={**os.environ, **environment},
                                    stdout=stream, stderr=subprocess.STDOUT)
        raw = log.read_bytes()
        text = raw.decode("utf-8")
        report["source_after"] = source_identity(source, args.commit)
        report["test_inputs_after"] = inventory(source, args.commit)
        report["source_unchanged"] = report["source_before"] == report["source_after"]
        report["test_inputs_unchanged"] = report["test_inputs_before"] == report["test_inputs_after"]
        summaries = re.findall(r"^Ran (\d+) tests? in ([0-9.]+)s$", text, re.M)
        outcomes = re.findall(r"^(?:OK(?: \([^\n]*\))?|FAILED \([^\n]*\))$", text, re.M)
        report.update(returncode=result.returncode, summaries=summaries, outcomes=outcomes,
                      skips=re.findall(r"^.*\.\.\. skipped .*$", text, re.M),
                      raw_log=log.name, raw_sha256=sha(raw))
        stored = gzip.compress(raw, mtime=0)
        (output / "unittest.log.gz").write_bytes(stored)
        report.update(stored_log="unittest.log.gz", stored_sha256=sha(stored))
        report["status"] = "passed" if (result.returncode == 0 and len(summaries) == 1
            and len(outcomes) == 1 and outcomes[0].startswith("OK")
            and report["source_unchanged"] and report["test_inputs_unchanged"]) else "failed"
        # Keep the losslessly compressed original and its independent digest.
        log.unlink()
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({key: report[key] for key in ("status", "commit", "returncode", "summaries", "outcomes")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
