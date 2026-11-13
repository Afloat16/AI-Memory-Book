"""One prospectively registered hosted recovery of I's old-data diagnostic.

No profile, fresh quality data, formal acceptance, or automatic replay is run.
Every timing stage is preceded and followed by a verified remote Git checkpoint.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tarfile
import tempfile
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = "round5-recovery-i-hosted-1"
BRANCH = "validation/v033-recovery-i-hosted-1"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SCOPE = ROOT / "benchmarks/experiments/round5-recovery-i-hosted-scope.json"
OLD = ROOT / "benchmarks/experiments/round5-development-attempt-i.json"
OLD_SHA = "02067bdd4c38bd1fcd2a3feef5974aa7bf9eac213e6009ddd64ead37356b7ad5"
CORRECTNESS_COMMIT = "21b6f4196e42167f8532feafc30457f5684d25cf"
COHORTS = ("synthetic61", "public1015")
CONFIGS = ("native-char4000", "native-token512", "native-token1024", "native-token2048")
TABLES = ("sessions", "chapters", "turns", "sections", "pages", "pages_fts", "pages_stem_fts")


class PublicationError(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def parse_remote(raw):
    fields = raw.split()
    if not fields:
        return None
    if len(fields) != 2 or fields[1] != "refs/heads/" + BRANCH or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise PublicationError("Unexpected remote result-ref response")
    return fields[0]


def remote_head():
    return parse_remote(git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH))


def publish(message):
    """One non-force push; reject divergent refs and never retry ambiguous writes."""
    journal = STATE / "publication.json"
    if (PUBLIC / "publication-failure.json").exists():
        raise PublicationError("Publication already failed; artifact-only preservation")
    expected = read(journal)["expected_remote"]
    parent = git("rev-parse", "HEAD")
    try:
        if remote_head() != expected:
            raise PublicationError("Another writer owns or advanced the result ref")
        if expected is not None and parent != expected:
            raise PublicationError("Local result ancestry changed")
        if git("diff", "--cached", "--name-only"):
            raise PublicationError("Unrelated staged changes")
        subprocess.run(["git", "add", "--sparse", "--", str(PUBLIC.relative_to(ROOT))], cwd=ROOT, check=True)
        staged = git("diff", "--cached", "--name-only").splitlines()
        prefix = str(PUBLIC.relative_to(ROOT)) + "/"
        if not staged or any(not path.startswith(prefix) for path in staged):
            raise PublicationError("Checkpoint contains missing or unrelated files")
        subprocess.run(["git", "commit", "-m", message + " [skip ci]"], cwd=ROOT, check=True)
        head = git("rev-parse", "HEAD")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH],
                                cwd=ROOT, capture_output=True, text=True)
        observed = remote_head()
        if pushed.returncode or observed != head:
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected, "local_commit": head,
                "observed_remote": observed, "push_returncode": pushed.returncode,
                "stdout": pushed.stdout, "stderr": pushed.stderr,
                "policy": "No automatic write or measurement retry; retain artifacts."})
            raise PublicationError("Push failed or did not verify at the expected commit")
        save(journal, {"expected_remote": head})
        print(json.dumps({"checkpoint": head, "branch": BRANCH, "message": message}), flush=True)
    except BaseException as error:
        if not (PUBLIC / "publication-failure.json").exists():
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected,
                "error": type(error).__name__ + ": " + str(error),
                "policy": "No automatic retry; inspect remote ref and artifact evidence."})
        raise


def verify_files(files, directory=ROOT):
    for path, expected in files.items():
        if sha(directory / path) != expected:
            raise ValueError("Frozen file changed: " + path)


def source_files(directory):
    return {str(path.relative_to(directory)): sha(path)
            for path in sorted((directory / "src").rglob("*")) if path.is_file()}


def export_source(label, identity):
    directory = STATE / "sources" / label
    directory.mkdir(parents=True, exist_ok=False)
    export_commit = CORRECTNESS_COMMIT if label == "candidate" else identity["commit"]
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", export_commit], cwd=ROOT, check=True)
    archive = STATE / (label + ".tar")
    subprocess.run(["git", "archive", "--format=tar", "--output=" + str(archive),
                    export_commit, "src", "tests"], cwd=ROOT, check=True)
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] not in ("src", "tests") or ".." in parts:
                raise ValueError("Unexpected source archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Nonregular source archive member")
        stream.extractall(directory)
    archive.unlink()
    if source_files(directory) != identity["files_sha256"]:
        raise ValueError("Exported source file inventory does not match frozen runtime")
    return directory


def environment():
    import tiktoken
    return {
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "machine": platform.machine(),
        "python_executable_sha256": sha(Path(sys.executable).resolve()),
        "packages": {name: importlib.metadata.version(name)
                     for name in ("mcp", "pydantic", "tiktoken", "regex")},
        "tokenizer_cache": {path.name: sha(path) for path in sorted(
            Path(os.environ["TIKTOKEN_CACHE_DIR"]).glob("*")) if path.is_file()},
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "scope": "This new hosted VM only; no cross-host timing pooling."}


def schedule():
    return [(cohort, round_number, label)
            for cohort in COHORTS
            for round_number, order in enumerate((("baseline", "candidate"), ("candidate", "baseline")))
            for label in order]


def ident(cohort, round_number, label):
    return f"{cohort}-r{round_number}-{label}"


def expected_ids(old, cohort, round_number, configuration):
    ids = list(old["cohorts"][cohort]["paired_selected_query_ids"])
    random.Random(91261 + round_number * 1009 + CONFIGS.index(configuration)).shuffle(ids)
    return ids


def validate_worker(value, old, cohort, round_number, label):
    source = old["baseline"] if label == "baseline" else old["candidate_source"]
    if (value.get("status"), value.get("cohort"), value.get("round"), value.get("label"),
        value.get("runtime_source_sha256"), value.get("dataset_sha256")) != (
            "completed", cohort, round_number, label, source["runtime_sha256"],
            old["cohorts"][cohort]["dataset_sha256"]):
        raise ValueError("Worker status, source, dataset, or axes mismatch")
    if [cell["configuration"] for cell in value["cells"]] != list(CONFIGS):
        raise ValueError("Worker configuration inventory/order mismatch")
    for cell in value["cells"]:
        if [row["query_id"] for row in cell["rows"]] != expected_ids(
                old, cohort, round_number, cell["configuration"]):
            raise ValueError("Missing, duplicated, or reordered query rows")
        for row in cell["rows"]:
            if not re.fullmatch(r"[0-9a-f]{64}", row["payload_sha256"]):
                raise ValueError("Invalid complete-payload digest")
            wall = row["wall_ms"]
            if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(wall) or wall < 0:
                raise ValueError("Invalid timing observation")


def quantile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def numeric(values):
    return {"samples": len(values), "p50": quantile(values, .5),
            "p95": quantile(values, .95), "mean": statistics.fmean(values)}


def audit(old):
    workers = {}
    records = []
    for cohort, round_number, label in schedule():
        identity = ident(cohort, round_number, label)
        path = PUBLIC / (identity + ".json")
        value = read(path)
        validate_worker(value, old, cohort, round_number, label)
        workers[cohort, round_number, label] = value
        records.append({"id": identity, "path": str(path.relative_to(ROOT)), "sha256": sha(path), "calls": 512})
    cells, mismatches = [], []
    for cohort in COHORTS:
        for index, config in enumerate(CONFIGS):
            rounds = []
            pooled = {"baseline": [], "candidate": []}
            for round_number in (0, 1):
                a = workers[cohort, round_number, "baseline"]["cells"][index]["rows"]
                b = workers[cohort, round_number, "candidate"]["cells"][index]["rows"]
                for left, right in zip(a, b):
                    if left["payload_sha256"] != right["payload_sha256"]:
                        mismatches.append({"cohort": cohort, "round": round_number,
                            "configuration": config, "query_id": left["query_id"],
                            "baseline": left["payload_sha256"], "candidate": right["payload_sha256"]})
                values = {"baseline": [row["wall_ms"] for row in a], "candidate": [row["wall_ms"] for row in b]}
                for label in pooled:
                    pooled[label].extend(values[label])
                summaries = {label: numeric(data) for label, data in values.items()}
                rounds.append({"round": round_number, **summaries,
                    **{metric + "_change_percent": (summaries["candidate"][metric] /
                        summaries["baseline"][metric] - 1) * 100 for metric in ("p50", "p95")}})
            summaries = {label: numeric(data) for label, data in pooled.items()}
            cells.append({"cohort": cohort, "configuration": config, **summaries, "rounds": rounds,
                **{metric + "_change_percent": (summaries["candidate"][metric] /
                    summaries["baseline"][metric] - 1) * 100 for metric in ("p50", "p95")}})
    improvement = (1 - math.exp(statistics.fmean(
        math.log(cell["candidate"]["p95"] / cell["baseline"]["p95"]) for cell in cells))) * 100
    return {"schema_version": 1, "attempt": ATTEMPT, "status": "completed",
        "workers": records, "calls": 4096, "complete_payload_pairs": 2048,
        "all_payloads_equal": not mismatches, "mismatches": mismatches, "cells": cells,
        "pooled_p95_geomean_improvement_percent": improvement,
        "adverse_cells_over_five_percent": [{"cohort": c["cohort"], "configuration": c["configuration"],
            "p50_change_percent": c["p50_change_percent"], "p95_change_percent": c["p95_change_percent"]}
            for c in cells if c["p50_change_percent"] > 5 or c["p95_change_percent"] > 5],
        "formal_acceptance": False, "fresh_rows_decoded": 0, "audit_retrieval_calls": 0,
        "scope": "All new hosted observations retained. Old I/F timings are not pooled. Development only; original formal and release gates unchanged."}


def correctness(candidate):
    modules = ["tests.test_round5_statement_cache", "tests.test_round5_native_rows",
        "tests.test_round5_materialization", "tests.test_round4_sealed_counts",
        "tests.test_round4_highlight", "tests.test_round4_token_work", "tests.test_token_budget",
        "tests.test_project_rowid_bounds", "tests.test_lexical_cache"]
    receipt = PUBLIC / "correctness.json"
    program = ("import json,sys,unittest; from pathlib import Path; "
        "suite=unittest.defaultTestLoader.loadTestsFromNames(json.loads(sys.argv[1])); "
        "r=unittest.TextTestRunner(verbosity=2).run(suite); "
        "Path(sys.argv[2]).write_text(json.dumps(dict(tests=r.testsRun,errors=len(r.errors),"
        "failures=len(r.failures),skipped=len(r.skipped),passed=r.wasSuccessful()),indent=2)+'\\n'); "
        "sys.exit(0 if r.wasSuccessful() and not r.skipped else 1)")
    env = dict(os.environ, PYTHONPATH=str(candidate / "src") + os.pathsep + str(ROOT))
    with (PUBLIC / "correctness.log").open("xb") as log:
        completed = subprocess.run([sys.executable, "-c", program, json.dumps(modules), str(receipt)],
            cwd=candidate, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    publish("bench: preserve hosted I correctness fixtures")
    if completed.returncode:
        raise RuntimeError("Candidate correctness fixtures did not all pass")


def prepare(old):
    sources = {label: export_source(label, old[key])
               for label, key in (("baseline", "baseline"), ("candidate", "candidate_source"))}
    correctness(sources["candidate"])
    raw_spec = read(ROOT / "benchmarks/locomo_split.json")
    with urllib.request.urlopen(raw_spec["url"], timeout=60) as response:
        raw = response.read(raw_spec["bytes"] + 1)
    if len(raw) != raw_spec["bytes"] or hashlib.sha256(raw).hexdigest() != raw_spec["sha256"]:
        raise ValueError("Pinned LoCoMo input mismatch")
    locomo = STATE / "locomo10.json"
    locomo.write_bytes(raw)
    sys.path[:0] = [str(sources["baseline"] / "src"), str(ROOT)]
    import memory_book
    from benchmarks.run import engine_source_hash
    from scripts.benchmark_default_recall import dataset
    from memory_book.token_budget import TokenCounter
    if Path(memory_book.__file__).resolve().parent != sources["baseline"] / "src/memory_book":
        raise ValueError("Baseline snapshot builder imported another runtime")
    if engine_source_hash(Path(memory_book.__file__).resolve().parent) != old["baseline"]["runtime_sha256"]:
        raise ValueError("Baseline runtime digest mismatch")
    TokenCounter("cl100k_base").count("Initialize outside timed calls.")
    databases = STATE / "databases"
    databases.mkdir(exist_ok=False)
    cohorts = {}
    for cohort in COHORTS:
        data = dataset(cohort, locomo)
        previous = old["cohorts"][cohort]
        selected = sorted(data.queries, key=lambda c: (
            hashlib.sha256(("round4-native-development-v1/" + c.id).encode()).digest(), c.id))[:128]
        if [case.id for case in selected] != previous["paired_selected_query_ids"]:
            raise ValueError("Registered old query selection changed")
        if len(data.sessions) != previous["sessions"] or data.fingerprint != previous["dataset_sha256"]:
            raise ValueError("Registered old dataset changed")
        target = databases / (cohort + ".db")
        logical = {}
        with memory_book.MemoryBook(target, cache_size=0) as book:
            for session in data.sessions:
                book.ingest(session)
            for table in TABLES:
                rows = [list(row) for row in book.db.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]
                logical[table] = {"rows": len(rows), "sha256": digest(rows)}
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            del rows  # Preparation memory is not a formal worker/resource measurement.
        if any(Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("Source snapshot has a live sidecar")
        cohorts[cohort] = {"dataset_sha256": data.fingerprint, "sessions": len(data.sessions),
            "queries": len(data.queries), "database_sha256": sha(target),
            "database_bytes": target.stat().st_size, "indexed_content": logical,
            "query_ids_sha256": digest([c.id for c in selected])}
    binding = {"schema_version": 1, "attempt": ATTEMPT, "created_at": stamp(),
        "scope_sha256": sha(SCOPE), "script_sha256": sha(Path(__file__)),
        "workflow_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "old_binding_sha256": sha(OLD), "sources": {label: old[key]
            for label, key in (("baseline", "baseline"), ("candidate", "candidate_source"))},
        "source_export_commits": {"baseline": old["baseline"]["commit"], "candidate": CORRECTNESS_COMMIT},
        "candidate_correctness_tests_sha256": {str(p.relative_to(sources["candidate"])): sha(p)
            for p in sorted((sources["candidate"] / "tests").rglob("*.py"))},
        "environment": environment(), "cohorts": cohorts,
        "helpers_sha256": old["helpers_sha256"],
        "helper_dependency_sha256": old["helper_dependency_sha256"],
        "worker_order": [ident(*item) for item in schedule()],
        "calls": 4096, "complete_payload_pairs": 2048,
        "snapshot_policy": "New baseline-built immutable bytes shared by both labels; never relabelled as the missing F snapshots.",
        "profile_repeated": False, "fresh_rows_decoded": 0, "formal_acceptance": False}
    save(PUBLIC / "binding.json", binding)
    publish("bench: bind hosted I sources environment and new snapshots before timing")
    return sources, locomo, databases, binding


def guards(old, binding, sources, locomo, databases):
    if sha(OLD) != OLD_SHA or sha(SCOPE) != binding["scope_sha256"] or sha(Path(__file__)) != binding["script_sha256"]:
        raise ValueError("Recovery scope, original binding, or orchestrator changed")
    verify_files(old["helpers_sha256"])
    verify_files(old["helper_dependency_sha256"])
    for label in ("baseline", "candidate"):
        if source_files(sources[label]) != binding["sources"][label]["files_sha256"]:
            raise ValueError("Runtime source changed")
    if environment() != binding["environment"]:
        raise ValueError("Bound environment changed")
    if sha(locomo) != read(ROOT / "benchmarks/locomo_split.json")["sha256"]:
        raise ValueError("Raw input changed")
    for cohort in COHORTS:
        path = databases / (cohort + ".db")
        if sha(path) != binding["cohorts"][cohort]["database_sha256"]:
            raise ValueError("Immutable source snapshot changed")
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("Immutable source snapshot has a sidecar")


def run():
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1" or os.environ.get("GITHUB_REF") != "refs/heads/ci/v033-recovery-i-hosted-1":
        raise RuntimeError("Only the prospectively registered first hosted attempt may run")
    if remote_head() is not None:
        raise RuntimeError("The fixed attempt is already claimed; do not replay")
    if PUBLIC.exists() or STATE.exists():
        raise RuntimeError("Recovery output/state already exists; do not reuse")
    STATE.mkdir(parents=True)
    PUBLIC.mkdir(parents=True)
    save(STATE / "publication.json", {"expected_remote": None})
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    old = read(OLD)
    if sha(OLD) != OLD_SHA:
        raise ValueError("Original I binding bytes changed")
    verify_files(old["helpers_sha256"])
    verify_files(old["helper_dependency_sha256"])
    save(PUBLIC / "attempt.intent.json", {"attempt": ATTEMPT, "status": "started",
        "created_at": stamp(), "workflow_commit": os.environ["GITHUB_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": 1, "scope_sha256": sha(SCOPE),
        "old_I": "Preserved separately; synthetic61-r0-candidate had started and has no saved completion. Its timing is never reconstructed or pooled.",
        "scope": "New independent old-data diagnostic only; original numerical/formal/release gates unchanged."})
    publish("bench: claim the single hosted I recovery attempt")
    stage = "prepare"
    try:
        sources, locomo, databases, binding = prepare(old)
        for cohort, round_number, label in schedule():
            stage = ident(cohort, round_number, label)
            guards(old, binding, sources, locomo, databases)
            output = PUBLIC / (stage + ".json")
            state = STATE / "workers" / stage
            if output.exists() or state.exists() or (PUBLIC / (stage + ".intent.json")).exists():
                raise ValueError("Worker was already started")
            identity = binding["sources"][label]
            command = [sys.executable, str(ROOT / "scripts/round4_development_pair.py"), "--worker",
                "--source", str(sources[label] / "src"), "--source-sha", identity["runtime_sha256"],
                "--label", label, "--cohort", cohort, "--round", str(round_number),
                "--db-directory", str(databases), "--locomo-path", str(locomo),
                "--state", str(state), "--output", str(output)]
            save(PUBLIC / (stage + ".intent.json"), {"status": "started", "created_at": stamp(),
                "worker": stage, "binding_sha256": sha(PUBLIC / "binding.json"), "argv": command,
                "expected_calls": 512, "frozen_runtime_origin": identity["commit"],
                "source_export_commit": binding["source_export_commits"][label],
                "snapshot_sha256": binding["cohorts"][cohort]["database_sha256"]})
            publish("bench: claim hosted I worker " + stage)
            returncode, failure = None, None
            try:
                with (PUBLIC / (stage + ".log")).open("xb") as log:
                    returncode = subprocess.run(command, cwd=ROOT, stdout=log,
                        stderr=subprocess.STDOUT, timeout=240).returncode
            except BaseException as error:
                failure = type(error).__name__ + ": " + str(error)
            save(PUBLIC / (stage + ".exit.json"), {"returncode": returncode,
                "error": failure, "finished_at": stamp(),
                "output_sha256": sha(output) if output.exists() else None,
                "policy": "All partial and negative observations are retained; no automatic replay."})
            publish("bench: preserve hosted I worker " + stage)
            if failure or returncode != 0:
                raise RuntimeError("Worker did not complete: " + stage)
            validate_worker(read(output), old, cohort, round_number, label)
        guards(old, binding, sources, locomo, databases)
        stage = "saved-result-audit"
        result = audit(old)
        save(PUBLIC / "paired-audit.json", result)
        save(PUBLIC / "completion.json", {"status": "completed", "created_at": stamp(),
            "attempt": ATTEMPT, "calls": result["calls"], "complete_payload_pairs": 2048,
            "all_payloads_equal": result["all_payloads_equal"], "formal_acceptance": False,
            "source_snapshots_unchanged": True, "fresh_rows_decoded": 0})
        publish("bench: preserve all hosted I observations and saved-result audit")
        if not result["all_payloads_equal"]:
            raise RuntimeError("Complete payload equality failed; no formal acceptance")
    except BaseException as error:
        save(PUBLIC / "failure.json", {"status": "failed_or_incomplete", "stage": stage,
            "created_at": stamp(), "error": type(error).__name__ + ": " + str(error),
            "replay_permitted": False, "formal_acceptance": False})
        if not (PUBLIC / "publication-failure.json").exists():
            publish("bench: preserve interrupted hosted I recovery evidence")
        raise


def preserve():
    """Workflow always step: save logs/partial evidence without invoking retrieval."""
    if not PUBLIC.exists() or not (STATE / "publication.json").exists():
        print("No new attempt was claimed; nothing to append.")
        return
    runner_log = ROOT / ".artifacts" / (ATTEMPT + "-runner.log")
    if runner_log.exists():
        shutil.copyfile(runner_log, PUBLIC / "runner.log")
    save(PUBLIC / "workflow-outcome.json", {"created_at": stamp(),
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "outcome": os.environ.get("RECOVERY_OUTCOME"), "retrieval_calls": 0,
        "scope": "Preservation only. Existing receipts are not overwritten or replayed."})
    if (PUBLIC / "publication-failure.json").exists():
        print("Publication had failed; preserve through artifact upload without retry.")
        return
    publish("bench: preserve hosted recovery workflow log and outcome")


class ProtocolTests(unittest.TestCase):
    def test_remote_ref_parser_rejects_wrong_ref_or_multiple_rows(self):
        self.assertIsNone(parse_remote(""))
        value = "a" * 40
        self.assertEqual(parse_remote(value + "\trefs/heads/" + BRANCH), value)
        for raw in (value + "\trefs/heads/unrelated", value + " refs/heads/" + BRANCH + "\n" + value,
                    "not-a-sha refs/heads/" + BRANCH):
            with self.assertRaises(PublicationError):
                parse_remote(raw)

    def test_schedule_is_complete_and_balanced_without_replay(self):
        values = schedule()
        self.assertEqual(len(values), 8)
        self.assertEqual(len(set(values)), 8)
        self.assertEqual([label for _, _, label in values], ["baseline", "candidate", "candidate", "baseline"] * 2)

    def test_quantiles_interpolate_without_discarding_slow_rows(self):
        self.assertEqual(quantile([1, 2, 3, 4, 100], .5), 3)
        self.assertAlmostEqual(quantile([1, 2, 3, 4, 100], .95), 80.8)

    def test_worker_rejects_missing_reordered_and_nonfinite_observations(self):
        old = {"baseline": {"runtime_sha256": "a" * 64},
            "candidate_source": {"runtime_sha256": "b" * 64},
            "cohorts": {"synthetic61": {"dataset_sha256": "c" * 64,
                "paired_selected_query_ids": ["invented-" + str(i) for i in range(128)]}}}
        value = {"status": "completed", "cohort": "synthetic61", "round": 0, "label": "baseline",
            "runtime_source_sha256": "a" * 64, "dataset_sha256": "c" * 64,
            "cells": [{"configuration": config, "rows": [{"query_id": q, "wall_ms": 1.0,
                "payload_sha256": "d" * 64} for q in expected_ids(old, "synthetic61", 0, config)]}
                for config in CONFIGS]}
        validate_worker(value, old, "synthetic61", 0, "baseline")
        for mutation in ("missing", "order", "nan", "hash"):
            damaged = json.loads(json.dumps(value))
            rows = damaged["cells"][0]["rows"]
            if mutation == "missing":
                rows.pop()
            elif mutation == "order":
                rows.reverse()
            elif mutation == "nan":
                rows[0]["wall_ms"] = float("nan")
            else:
                rows[0]["payload_sha256"] = "invalid"
            with self.assertRaises(ValueError):
                validate_worker(damaged, old, "synthetic61", 0, "baseline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "preserve", "self-test"))
    mode = parser.parse_args().mode
    if mode == "self-test":
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    elif mode == "preserve":
        preserve()
    else:
        run()
