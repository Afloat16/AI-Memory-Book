"""Run the registered C7 development checks sequentially on one hosted VM.

This wrapper has no query timer. Original native and actual-SDK helpers own all
measurements. Publication uses a separate Git index and never moves HEAD.
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
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_c7_performance as c7


def call(*args, env=None):
    return subprocess.check_output(args, cwd=ROOT, env=env, text=True).strip()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def identity():
    run = os.environ.get("GITHUB_RUN_ID", "")
    c7.require(re.fullmatch(r"[0-9]+", run) is not None
        and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
        and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
        and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REF") == "refs/heads/ci/v033-round5-c7-development",
        "Only the first attempt of the registered hosted development trigger is supported")
    suffix = run + "-1"
    return (ROOT / ".artifacts" / ("round5-c7-development-" + suffix),
        ROOT / "benchmarks/reports" / ("round5-c7-development-" + suffix),
        "validation/v033-round5-c7-development-" + suffix)


def prepare(state, public):
    c7.require_registered_source()
    c7.require(not state.exists(), "Preserve the existing development attempt")
    state.mkdir(parents=True)
    sources = {"baseline": c7.BASELINE, "candidate": c7.C7_SOURCE}
    for commit in dict.fromkeys([c7.CONTINUATION_COMMIT, c7.C4_ARCHIVE_COMMIT,
            c7.C5_RESULT_COMMIT, c7.C6_RESULT_COMMIT, *[x["commit"] for x in sources.values()]]):
        call("git", "fetch", "--depth", "1", "origin", commit)
    c7.continuation_registration()
    plans = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        "benchmarks/experiments/round5-c7-development-plan.json",
        "benchmarks/experiments/round5-c7-mcp-development-plan.json")}
    claim = "validation/v033-round5-c7-development-claim-" + c7.digest({"sources": sources, "plans": plans})
    c7.require(not call("git", "ls-remote", "--heads", "origin", "refs/heads/" + claim),
        "This source and registered development pair already has a remote execution claim; no rerun")
    call("git", "push", "--force-with-lease=refs/heads/" + claim + ":", "origin", "HEAD:refs/heads/" + claim)
    paths = {}
    for label, source in sources.items():
        location = state / ("source-" + label)
        call("git", "worktree", "add", "--no-checkout", "--detach", str(location), source["commit"])
        call("git", "-C", str(location), "sparse-checkout", "set", "src")
        call("git", "-C", str(location), "read-tree", "-mu", "HEAD")
        c7.require(c7.source_identity(location / "src") == source, "Frozen source differs")
        paths[label] = str(location / "src")
    spec = json.loads((ROOT / "benchmarks/locomo_split.json").read_bytes())
    with urllib.request.urlopen(spec["url"], timeout=60) as response:
        raw = response.read(spec["bytes"] + 1)
    c7.require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "Old data bytes differ")
    locomo = state / "locomo10.json"
    locomo.write_bytes(raw)
    import tiktoken
    for name in ("cl100k_base", "o200k_base"):
        tiktoken.get_encoding(name).encode("Initialize reference encoding outside timed workers.")
    from scripts.benchmark_default_recall import server_rss
    child = subprocess.Popen([sys.executable, "-c", 'import sys;print("ready",flush=True);sys.stdin.buffer.read(1)',
        "memory_book-procfs-preflight"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        c7.require(child.stdout.readline() == b"ready\n", "Harmless resource preflight child failed")
        rss = server_rss()
    finally:
        child.communicate(b"x", timeout=10)
    save(state / "resource-preflight.json", {"observation": rss, "product_calls": 0, "sdk_sessions": 0})
    c7.require(rss["available"] and rss["rss_bytes"] > 0 and rss["hwm_bytes"] > 0,
        "The unchanged resource selector must find the live child before any measurement")
    setup = {"sources": sources, "source_paths": paths, "plans": plans, "claim_branch": claim,
        "workflow_commit": call("git", "rev-parse", "HEAD"), "locomo": str(locomo),
        "locomo_sha256": spec["sha256"], "created_at": datetime.now(timezone.utc).isoformat()}
    save(state / "setup.json", setup)
    # Build identical source databases through the baseline in a fresh process.
    # No retrieval is performed; workers subsequently copy these closed files.
    code = '''from pathlib import Path
import hashlib,json,sys
sys.path.insert(0,sys.argv[1])
import memory_book
from scripts.benchmark_default_recall import dataset,indexed_content
from benchmarks.semantic_eval import source_snapshot
assert Path(memory_book.__file__).resolve().parent == Path(sys.argv[1]).resolve()/"memory_book"
target=Path(sys.argv[2]);target.mkdir()
records={}
for name in ("synthetic61","public1015"):
 data=dataset(name,Path(sys.argv[3]));path=target/(name+".db")
 with memory_book.MemoryBook(path,cache_size=0) as book:
  for session in data.sessions: book.ingest(session)
  records[name]={"dataset_sha256":data.fingerprint,"source_snapshot_sha256":source_snapshot(book.db),"indexed_content":indexed_content(book.db),"revision":book.revision,"cache_entries":book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}
  assert records[name]["cache_entries"]==0
 records[name]["database_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
(target.parent/"base-databases.json").write_text(json.dumps(records,indent=2)+"\\n")
'''
    subprocess.run([sys.executable, "-c", code, paths["baseline"], str(state / "databases"), str(locomo)], cwd=ROOT, check=True)
    print(json.dumps({"prepared": True, "sources": sources, "sdk_sessions": 0, "recalls": 0}))


def measure(phase, state):
    setup = json.loads((state / "setup.json").read_bytes())
    c7.require(setup["workflow_commit"] == call("git", "rev-parse", "HEAD"), "Wrapper must not move evaluator HEAD")
    c7.require(setup["sources"] == {"baseline": c7.BASELINE, "candidate": c7.C7_SOURCE}, "Source changed")
    paths = setup["source_paths"]
    if phase == "native":
        argv = [sys.executable, "-u", "scripts/round5_c7_development_pair.py",
            "--db-directory", str(state / "databases"), "--state", str(state / "native-state"),
            "--output", str(state / "native-manifest.json"), "--locomo-path", setup["locomo"]]
        for label in ("baseline", "candidate"):
            argv += ["--" + label + "-src", paths[label], "--" + label + "-sha", setup["sources"][label]["runtime_sha256"],
                "--" + label + "-commit", setup["sources"][label]["commit"]]
    else:
        argv = [sys.executable, "-u", "scripts/round5_c7_mcp_development_pair.py",
            "--baseline-src", paths["baseline"], "--candidate-src", paths["candidate"],
            "--locomo-path", setup["locomo"], "--state-dir", str(state / "mcp-state"),
            "--output", str(state / "mcp-manifest.json.gz")]
    subprocess.run(argv, cwd=ROOT, check=True)


def preserve(stage, state, public, branch):
    public.mkdir(parents=True, exist_ok=True)
    for name in ("setup.json", "resource-preflight.json", "base-databases.json", "native.log", "mcp.log"):
        source = state / name
        if source.is_file():
            shutil.copyfile(source, public / name)
    for name in ("native-manifest.json", "mcp-manifest.json.gz"):
        source = state / name
        if source.is_file():
            raw = source.read_bytes()
            (public / (name if name.endswith(".gz") else name + ".gz")).write_bytes(raw if name.endswith(".gz") else gzip.compress(raw, mtime=0))
    for folder, patterns in (("native-state", ("*.json",)), ("mcp-state", ("*.json", "workers/*.json", "workers/*.gz", "workers/*.jsonl"))):
        for pattern in patterns:
            for source in sorted((state / folder).glob(pattern)):
                destination = public / folder / source.relative_to(state / folder)
                destination.parent.mkdir(parents=True, exist_ok=True)
                raw = source.read_bytes()
                # Keep small MCP run/started metadata directly readable by the
                # frozen saved-data auditor; compress large rows and ledgers.
                if source.suffix == ".jsonl" or (source.suffix == ".json" and folder == "native-state"):
                    destination = destination.with_name(destination.name + ".gz")
                    raw = gzip.compress(raw, mtime=0)
                destination.write_bytes(raw)
    for source in sorted((ROOT / ".artifacts").glob("round5-c7-mcp-development-*.execution.json")):
        shutil.copyfile(source, public / source.name)
    save(public / ("checkpoint-" + stage + ".json"), {"stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat(), "workflow_commit": call("git", "rev-parse", "HEAD"),
        "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": "1", "phase_outcome": os.environ.get("PHASE_OUTCOME"),
        "files_sha256": {str(p.relative_to(public)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(public.rglob("*")) if p.is_file()},
        "scope": "Exact complete or interrupted development observations; no formal acceptance and no repeated measurement."})
    record = state / "publication.json"
    previous = json.loads(record.read_bytes())["commit"] if record.exists() else None
    remote = call("git", "ls-remote", "--heads", "origin", "refs/heads/" + branch).split()
    c7.require(remote == ([previous, "refs/heads/" + branch] if previous else []), "Unexpected result branch writer")
    parent = previous or call("git", "rev-parse", "HEAD")
    index = state / "publication.index"
    index.unlink(missing_ok=True)
    environment = {**os.environ, "GIT_INDEX_FILE": str(index), "GIT_AUTHOR_NAME": "github-actions[bot]",
        "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
        "GIT_COMMITTER_NAME": "github-actions[bot]", "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    call("git", "read-tree", parent, env=environment)
    call("git", "add", "--", str(public.relative_to(ROOT)), env=environment)
    tree = call("git", "write-tree", env=environment)
    commit = call("git", "commit-tree", tree, "-p", parent, "-m", "bench: preserve C7 development " + stage, env=environment)
    try:
        call("git", "push", "--force-with-lease=refs/heads/" + branch + ":" + (previous or ""),
            "origin", commit + ":refs/heads/" + branch)
    except BaseException as error:
        save(public / "publication-failure.json", {"commit": commit, "branch": branch, "error": str(error),
            "policy": "No automatic retry after rejected or ambiguous push; retain workflow artifact."})
        raise
    save(record, {"commit": commit, "tree": tree, "branch": branch})
    print(json.dumps({"checkpoint": stage, "commit": commit, "result_branch": branch}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "native", "mcp", "preserve"))
    parser.add_argument("--stage", choices=("prepared", "native", "mcp", "failed"))
    args = parser.parse_args()
    state, public, branch = identity()
    if args.phase == "prepare":
        prepare(state, public)
    elif args.phase == "preserve":
        c7.require(args.stage, "Checkpoint stage is required")
        state.mkdir(parents=True, exist_ok=True)
        preserve(args.stage, state, public, branch)
    else:
        measure(args.phase, state)


if __name__ == "__main__":
    main()
