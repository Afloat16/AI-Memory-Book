"""Bind the unchanged crowding probe to actual Git worktrees and text backends.

This is authored development/regression evidence, not a holdout or a speed
benchmark. Each backend compares its own baseline/final pair. Original probe
bytes and every response are retained; no source or evaluator is patched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "234891619d7bed88ddf3fae37e7f3e1b14a808b6"
PROBE = ROOT / "benchmarks/experiments/v011-current-route-probe.py"
PROBE_SHA = "0f699741b6c75bb51e9829323e29d8b3ee6f06ba25be6852efa13897ba2d21a8"
PROTOCOL = "v011-bound-revision-recovery-v1"
OLD_TEXT = "ASSISTANT: retry_limit=3. " + "retry_limit. " * 12
NEW_TEXT = "ASSISTANT: retry_limit=7. The short accepted revision replaces the original configuration."


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args])


def source_identity(source, commit):
    source = source.resolve()
    if git(source, "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("Worktree HEAD differs from the requested immutable source")
    names = git(source, "ls-tree", "-r", "--name-only", commit, "src/memory_book").decode().splitlines()
    files = {}
    for name in names:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Runtime source missing or symlinked: " + name)
        raw = path.read_bytes()
        if raw != git(source, "show", commit + ":" + name):
            raise ValueError("Runtime differs from its Git source: " + name)
        files[name] = sha(raw)
    actual = {p.relative_to(source).as_posix() for p in (source / "src/memory_book").rglob("*")
              if p.is_file() and p.suffix in {".py", ".c", ".h", ".rs"}}
    if actual != {name for name in names if Path(name).suffix in {".py", ".c", ".h", ".rs"}}:
        raise ValueError("Unexpected runtime source inventory")
    extensions = {p.name: sha(p.read_bytes()) for p in (source / "src/memory_book").glob("_native*")
                  if p.suffix in {".so", ".pyd"}}
    return {"commit": commit, "files": files, "native_extensions": extensions,
            "source_sha256": sha(json.dumps(files, sort_keys=True).encode())}


def verify_observations(raw):
    expected = {(count, mode, limit, repeat) for count in (4, 100, 1000)
                for mode in ("relevance", "current") for limit in (1, 5) for repeat in range(3)}
    rows = {}
    for row in raw["observations"]:
        key = (row["old_count"], row["mode"], row["limit"], row["repeat"])
        if key not in expected or key in rows:
            raise ValueError("Missing, duplicate or unknown observation identity")
        result = row["result"]
        temporal = result["temporal"]
        if (result["query"] != "retry_limit" or result["budget_chars"] != 2400
                or result["context_chars"] != len(result["context"])
                or result["context_chars"] > 2400 or result["cache_hit"] is not False
                or not 1 <= len(result["results"]) <= row["limit"]
                or temporal["requested"] != row["mode"]
                or temporal["resolved"] != row["mode"]
                or temporal["basis"] != "explicit_override"
                or temporal["preserve_occurrences"] is not False):
            raise ValueError("Query, mode, budget, cache or result-count contract differs")
        ids, sessions = set(), []
        for item in result["results"]:
            if item["id"] in ids or len(item["source_refs"]) != 1:
                raise ValueError("Duplicate page or unexpected source references")
            ids.add(item["id"])
            ref = item["source_refs"][0]
            session = ref["session_id"]
            if session == "new":
                original = NEW_TEXT
            elif session.startswith("old-") and session[4:].isdigit() and 0 <= int(session[4:]) < row["old_count"]:
                original = OLD_TEXT
            else:
                raise ValueError("Unknown original session")
            if (ref["project"] != "workers" or ref["turn_index"] != 0
                    or ref["message_indices"] != [0]
                    or [ref[k] for k in ("start", "end", "turn_start", "turn_end")]
                       != [0, len(original), 0, len(original)]
                    or item["text"] != original or item["truncated"] is not False
                    or item["page_chars"] != len(original)
                    or item["excerpt_spans"] != [[0, len(original)]]
                    or item["breadcrumb"][0]["id"] != "workers"
                    or original not in result["context"]):
                raise ValueError("Original text, coordinates or exact project differs")
            sessions.append(session)
        actual_new = "new" in sessions
        if (row["new_present"] != actual_new or row["first_session"] != sessions[0]
                or ("retry_limit=7" in result["context"]) != actual_new):
            raise ValueError("Producer's claimed recovery differs from original-source evidence")
        rows[key] = row
    if rows.keys() != expected:
        raise ValueError("Incomplete observation matrix")
    return rows


def worker(args):
    import memory_book
    from memory_book._text_backend import BACKEND_NAME
    import memory_book.store as store

    source, output = args.source.resolve(), args.output.resolve()
    if Path(memory_book.__file__).resolve().parent != source / "src/memory_book":
        raise ValueError("Imported package is not the requested source snapshot")
    if Path(store.__file__).resolve() != source / "src/memory_book/store.py" or BACKEND_NAME != args.backend:
        raise ValueError("Actual imported store or text backend differs")
    before = source_identity(source, args.commit)
    loaded = sys.modules.get("memory_book._native")
    loaded_path = Path(loaded.__file__).resolve() if loaded is not None else None
    if args.backend == "native" and (loaded_path is None or loaded_path.parent != source / "src/memory_book"):
        raise ValueError("Native backend was not loaded from the source snapshot")
    proof = {"status": "started", "backend": BACKEND_NAME, "version": memory_book.__version__,
             "recall_version": store.RECALL_VERSION, "import_path": str(Path(store.__file__).resolve()),
             "source_before": before, "python": sys.version,
             "loaded_native": {"path": str(loaded_path), "sha256": sha(loaded_path.read_bytes())} if loaded_path else None}
    write(output / "identity.json", proof)
    try:
        if sha(PROBE.read_bytes()) != PROBE_SHA:
            raise ValueError("Frozen original probe changed")
        sys.argv = [str(PROBE), "--output", str(output / "raw.json"), "--label", args.label]
        runpy.run_path(str(PROBE), run_name="__main__")
        raw = json.loads((output / "raw.json").read_text())
        if (raw["git_head"] != args.commit or raw["backend"] != args.backend
                or raw["store_sha256"] != before["files"]["src/memory_book/store.py"]
                or raw["probe_sha256"] != PROBE_SHA):
            raise ValueError("Probe's recorded identity differs from the independently checked import")
        rows = verify_observations(raw)
        after = source_identity(source, args.commit)
        if before != after or sha(PROBE.read_bytes()) != PROBE_SHA:
            raise ValueError("Source, native binary or evaluator changed during the probe")
        proof.update(status="completed", source_after=after, independently_verified_responses=len(rows),
                     current_calls=18, current_new_present=sum(r["new_present"] for k, r in rows.items() if k[1] == "current"),
                     raw_sha256=sha((output / "raw.json").read_bytes()))
    except Exception as error:
        proof.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        write(output / "identity.json", proof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--candidate-source", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--backend", choices=("python", "native"))
    parser.add_argument("--label")
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if not all((args.baseline_source, args.candidate_source, args.candidate_commit)):
        parser.error("Both immutable Git worktrees and the candidate commit are required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"protocol": PROTOCOL, "status": "started", "started_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Six authored crowding configurations per backend, three repeats; not independent cases or a speed experiment",
              "driver_sha256": sha(Path(__file__).read_bytes()), "probe_sha256": PROBE_SHA,
              "baseline_commit": BASELINE, "candidate_commit": args.candidate_commit,
              "attempts": [], "comparisons": {}}
    write(output / "report.json", report)
    try:
        for backend in ("python", "native"):
            results = {}
            # Alternate arm order across backends; timers still remain diagnostic.
            arms = [("baseline", args.baseline_source, BASELINE), ("candidate", args.candidate_source, args.candidate_commit)]
            for label, source, commit in arms if backend == "python" else reversed(arms):
                source = source.resolve()
                destination = output / (backend + "-" + label)
                destination.mkdir()
                item = {"backend": backend, "arm": label, "status": "started", "commit": commit}
                report["attempts"].append(item)
                write(output / "report.json", report)
                env = {**os.environ, "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1",
                       "MEMORY_BOOK_TEXT_BACKEND": backend}
                with (destination / "worker.log").open("w") as log:
                    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                        "--source", str(source), "--commit", commit, "--backend", backend,
                        "--label", label, "--output", str(destination)], cwd=source, env=env,
                        stdout=log, stderr=subprocess.STDOUT, timeout=300)
                item.update(status="completed" if completed.returncode == 0 else "failed", returncode=completed.returncode)
                write(output / "report.json", report)
                if completed.returncode:
                    raise RuntimeError("Probe failed; preserve its original log and partial records")
                raw = json.loads((destination / "raw.json").read_text())
                results[label] = verify_observations(raw)
            controls = []
            for key, old in results["baseline"].items():
                if key[1] != "relevance":
                    continue
                a, b = dict(old["result"]), dict(results["candidate"][key]["result"])
                a.pop("latency_ms"); b.pop("latency_ms")
                if a != b:
                    controls.append(key)
            recovered = {arm: sum(row["new_present"] for key, row in rows.items() if key[1] == "current")
                         for arm, rows in results.items()}
            report["comparisons"][backend] = {"current_calls_per_arm": 18, "current_new_present": recovered,
                "relevance_calls_per_arm": 18, "relevance_payload_differences_excluding_only_latency": controls}
            if controls or recovered["candidate"] != 18:
                raise ValueError("Candidate recovery or unchanged relevance control failed")
        report.update(status="completed", accepted=True)
    except Exception as error:
        report.update(status="failed", accepted=False, error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(output / "report.json", report)
    print(json.dumps({"status": report["status"], "accepted": report["accepted"], "comparisons": report["comparisons"]}))


if __name__ == "__main__":
    main()
