"""Prospective T1 fresh selection and data binding; never selects on import.

Binding precedes ID/type decoding. A committed selection precedes selected-row
decoding. This module never calls recall or any model, and never rebinds old
round-four loaders/controllers. Artificial tests use invented IDs only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_title_reference_eval_v2 as scoring

SCOPE = "benchmarks/experiments/round5-title-reference-fresh-v2-scope.json"
SCOPE_SHA256 = "cc6df4ae6d6c35a7b2a5aeff1656433c2c629fdeb60954143abb6f8305e565de"
VERSION = "round5-title-reference-fresh512-native-2"
PREFIX = "AI-Memory-Book/v033/title-reference-t1/2026-11-13/"
COUNTS = {"bridge": 384, "comparison": 128}
SEED = 61512
SOURCE_COLUMNS = ("id", "question", "answer", "type", "level", "context", "supporting_facts")
NEW_FILES = (SCOPE, "scripts/round5_title_reference_fresh_data_v2.py",
             "scripts/round5_title_reference_fresh_v2.py", "tests/test_round5_title_reference_fresh_v2.py",
             "scripts/round5_source_content_snapshot.py", "tests/test_round5_source_content_snapshot.py",
             "tests/test_round5_fresh_snapshot_v2_integration.py",
             "benchmarks/experiments/round5-fresh-snapshot-v2-plan.json")
INTERFACE_FILES = ("benchmarks/experiments/round5-final-interface-v2-scope.json",
    "scripts/round5_interface_certificate.py", "scripts/round5_performance_v2.py",
    "tests/test_round5_performance_v2.py", ".github/workflows/round5-performance-v2.yml",
    "benchmarks/experiments/round5-final-interface-certificate.json")
read, save, raw, sha, digest, require, relative, now = (
    scoring.read, scoring.save, scoring.raw, scoring.sha, scoring.digest,
    scoring.require, scoring.relative, scoring.now)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30, stderr=subprocess.DEVNULL)


def committed(path):
    require(Path(path).read_bytes() == git("show", "HEAD:" + relative(path)), "Commit before use: " + relative(path))


def registered():
    require(sha(ROOT / SCOPE) == SCOPE_SHA256, "Fresh scope changed")
    scope = read(ROOT / SCOPE)
    repair = scope["snapshot_repair"]
    for path, expected in repair["preserved_original_files_sha256"].items():
        require(sha(ROOT / path) == expected, "Original fresh v1 evidence changed: " + path)
        committed(ROOT / path)
    require(sha(ROOT / repair["component_scope"]["path"]) == repair["component_scope"]["sha256"],
            "Versioned component scope changed")
    original = scope["original_plan"]
    require(sha(ROOT / original["path"]) == original["sha256"]
            and (ROOT / original["path"]).read_bytes() == git("show", original["commit"] + ":" + original["path"]),
            "Original T1 registration changed")
    require(sha(ROOT / scope["reused_evaluator"]["script"]) == scope["reused_evaluator"]["sha256"],
            "Frozen v2 scoring helper changed")
    for item in scope["selection"]["historical_exclusions"] + scope["comparators"]["locks"]:
        require(sha(ROOT / item["path"]) == item["sha256"], "Historical manifest or comparator lock changed")
    require(scope["final_interface"]["files"] == list(INTERFACE_FILES)
            and scope["final_interface"]["certificate"] == INTERFACE_FILES[-1], "Final interface certificate boundary changed")
    return scope


def historical_exclusions(scope):
    all_ids = set()
    for item in scope["selection"]["historical_exclusions"]:
        ids = read(ROOT / item["path"])["selected_ids"]
        require(len(ids) == len(set(ids)) == item["count"] and not all_ids.intersection(ids), "Historical ID manifests overlap/change")
        all_ids.update(ids)
    require(len(all_ids) == scope["selection"]["historical_union"] == 896, "Historical exclusion union changed")
    return all_ids


def choose_ids(metadata, excluded):
    """Pure, label-free stratified selection; callers must freeze first."""
    groups, seen = {kind: [] for kind in COUNTS}, set()
    for item in metadata:
        require(set(item) == {"id", "type"}, "Selection may decode only id and type")
        identity, kind = item["id"], item["type"]
        require(type(identity) is str and identity and identity not in seen and kind in COUNTS, "Invalid/duplicate metadata ID or type")
        seen.add(identity)
        if identity not in excluded:
            groups[kind].append(identity)
    selected = []
    for kind, count in COUNTS.items():
        require(len(groups[kind]) >= count, "Insufficient unseen " + kind + " population")
        ordered = sorted(groups[kind], key=lambda identity: (hashlib.sha256((PREFIX + identity).encode()).hexdigest(), identity))
        selected.extend({"id": identity, "type": kind} for identity in ordered[:count])
    return selected


def read_metadata(path, reader=None):
    if reader is None:
        import pyarrow.parquet as pq
        reader = pq.read_table
    return reader(path, columns=["id", "type"]).to_pylist()


def host():
    return {**scoring.host(), "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count(),
            "processor": platform.processor(), "python_executable": sys.executable}


def query_order(ids, configuration):
    ordered = list(ids)
    random.Random(SEED + configuration["index"]).shuffle(ordered)
    return ordered


def comparator_registration(path, scope, candidate, selection):
    committed(path)
    value = read(path)
    require(value["protocol"] == "round5-t1-fresh512-comparators-2"
            and value["status"] == "frozen-before-selection"
            and value["upstream_pins"] == scope["comparators"]["pins"]
            and value["candidate_source"] == candidate and value["selection_manifest"] == selection
            and value["top_k"] == 5 and value["tokenizers"] == ["cl100k_base", "o200k_base"]
            and value["token_budgets"] == [512, 1024, 2048], "Comparator registration is incomplete or uses other sources/axes")
    require(value["evaluator_files"] and value["dependencies"] and value["native_boundaries"]
            and value["schedule"] and value["asset_pins"], "Freeze comparator evaluators, assets, parameters and boundaries before selection")
    for name, expected in value["evaluator_files"].items():
        require(relative(ROOT / name) == name and sha(ROOT / name) == expected, "Comparator evaluator file changed")
        committed(ROOT / name)
    return value


def registry(scope, comparator_path, comparison):
    names = set(scoring.registry()) | set(NEW_FILES) | set(INTERFACE_FILES) | {relative(comparator_path)}
    names.update(item["path"] for item in scope["selection"]["historical_exclusions"] + scope["comparators"]["locks"])
    names.update(comparison["evaluator_files"])
    names.update(scope["snapshot_repair"]["preserved_original_files_sha256"])
    return {name: sha(ROOT / name) for name in sorted(names)}


def interface_certificate(sources):
    from scripts import round5_interface_certificate
    round5_interface_certificate.load_certificate(sources)
    return {"path": INTERFACE_FILES[-1], "sha256": sha(ROOT / INTERFACE_FILES[-1])}


def bind(args):
    scope = registered()
    for path in (args.bind, args.selection, args.data_binding, args.state, args.output):
        require(path is not None and not path.exists(), "Use fresh binding, manifest, data, state and output paths")
        relative(path)
    require(re.fullmatch(r"refs/heads/[A-Za-z0-9_./-]+", args.publication_ref or ""), "Bind the exact remote publication ref")
    sources = {name: scoring.source(path) for name, path in (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == scope["baseline"], "Baseline is not published v0.3.2")
    interface = interface_certificate(sources)
    comparison = comparator_registration(args.comparators, scope, sources["candidate"], relative(args.selection))
    files = registry(scope, args.comparators, comparison)
    for name in files:
        committed(ROOT / name)
    additional = read(args.additional_exclusions) if args.additional_exclusions else []
    require(isinstance(additional, list) and all(type(x) is str and x for x in additional)
            and len(additional) == len(set(additional)), "Additional inspected IDs must be an explicit unique list")
    if args.additional_exclusions:
        committed(args.additional_exclusions)
    known = historical_exclusions(scope) | set(additional)
    upstream = read(ROOT / "benchmarks/hotpot_manifest.json")
    require(sha(args.parquet) == upstream["upstream_sha256"] and args.parquet.stat().st_size == upstream["upstream_bytes"], "Pinned Parquet bytes changed")
    environment = host()
    require(environment["packages"] == {"tiktoken": "0.12.0", "pyarrow": "26.0.1"}, "Use registered reference/data dependencies")
    value = {"version": VERSION, "status": "frozen-before-fresh-metadata-selection", "created_at": now(),
        "scope": {"path": SCOPE, "sha256": SCOPE_SHA256}, "sources": sources,
        "evaluator_commit": git("rev-parse", "HEAD").decode().strip(), "evaluator_files": files,
        "final_interface": interface,
        "comparators": {"path": relative(args.comparators), "sha256": sha(args.comparators)},
        "additional_exclusions": sorted(additional), "excluded_ids": sorted(known),
        "parquet": {"sha256": sha(args.parquet), "bytes": args.parquet.stat().st_size},
        "selection": relative(args.selection), "data_binding": relative(args.data_binding),
        "state": relative(args.state), "output": relative(args.output), "host": environment,
        "publication_ref": args.publication_ref, "configurations": scope["native"]["configurations"],
        "workers": scope["native"]["workers"], "expected_calls": 15360,
        "limits": "Final source and all parameters frozen before metadata selection; no fresh metadata decoded while binding."}
    save(args.bind, value, exclusive=True)
    print(json.dumps({"binding": relative(args.bind), "next": "Publish this exact binding before --select."}), flush=True)


def load_binding(path):
    committed(path)
    bound, scope = read(path), registered()
    require(bound["version"] == VERSION and bound["status"] == "frozen-before-fresh-metadata-selection"
            and bound["scope"] == {"path": SCOPE, "sha256": SCOPE_SHA256}
            and bound["sources"]["baseline"] == scope["baseline"] and bound["expected_calls"] == 15360
            and bound["configurations"] == scope["native"]["configurations"] and bound["workers"] == scope["native"]["workers"]
            and bound["excluded_ids"] == sorted(historical_exclusions(scope) | set(bound["additional_exclusions"])), "Fresh binding changed")
    comparison = comparator_registration(ROOT / bound["comparators"]["path"], scope, bound["sources"]["candidate"], bound["selection"])
    require(bound["final_interface"] == interface_certificate(bound["sources"]), "Final interface certificate changed")
    require(sha(ROOT / bound["comparators"]["path"]) == bound["comparators"]["sha256"]
            and registry(scope, ROOT / bound["comparators"]["path"], comparison) == bound["evaluator_files"], "Bound evaluator/comparator bytes changed")
    for name, expected in bound["evaluator_files"].items():
        require(hashlib.sha256(git("show", bound["evaluator_commit"] + ":" + name)).hexdigest() == expected,
                "Evaluator was not frozen before selection: " + name)
    return bound


def published(bound, commit, paths):
    """Verify immutable file bytes and the exact remote ref before advancing."""
    require(re.fullmatch("[0-9a-f]{40}", commit or ""), "A full published checkpoint commit is required")
    remote = git("ls-remote", "--refs", "origin", bound["publication_ref"]).decode().split()
    require(remote == [commit, bound["publication_ref"]], "Remote checkpoint ref differs; inspect before continuing")
    for path in paths:
        require(Path(path).read_bytes() == git("show", commit + ":" + relative(path)), "Checkpoint did not publish exact artifact: " + relative(path))


def select(args):
    bound = load_binding(args.binding)
    target = ROOT / bound["selection"]
    require(not target.exists(), "Never replace a selected manifest")
    published(bound, args.published_commit, [args.binding])
    require(host() == bound["host"] and sha(args.parquet) == bound["parquet"]["sha256"], "Host or source data changed before selection")
    metadata = read_metadata(args.parquet)
    selected = choose_ids(metadata, set(bound["excluded_ids"]))
    value = {"version": VERSION, "status": "selected-before-content-decoding", "created_at": now(),
        "binding_sha256": sha(args.binding), "binding_publication_commit": args.published_commit,
        "selection_prefix": PREFIX, "mixture": COUNTS, "selected": selected,
        "selected_ids": [x["id"] for x in selected], "metadata_rows": len(metadata),
        "metadata_sha256": digest(sorted(metadata, key=lambda x: x["id"])), "parquet": bound["parquet"]}
    save(target, value, exclusive=True)
    print(json.dumps({"manifest": relative(target), "selected_ids": 512, "content_rows_decoded": 0,
                      "next": "Publish the manifest before --prepare-data."}), flush=True)


def load_selection(bound, binding_path):
    path = ROOT / bound["selection"]
    committed(path)
    value = read(path)
    ids = value["selected_ids"]
    require(value["version"] == VERSION and value["status"] == "selected-before-content-decoding"
            and value["binding_sha256"] == sha(binding_path) and value["parquet"] == bound["parquet"]
            and value["selection_prefix"] == PREFIX and value["mixture"] == COUNTS
            and len(ids) == len(set(ids)) == 512 and not set(ids).intersection(bound["excluded_ids"])
            and [x["id"] for x in value["selected"]] == ids
            and choose_ids(value["selected"], set()) == value["selected"], "Selected cohort/mixture/order changed")
    return value


def load_dataset(path, bound, selection, reader=None):
    require(sha(path) == bound["parquet"]["sha256"], "Parquet bytes changed")
    if reader is None:
        import pyarrow.parquet as pq
        reader = pq.read_table
    ids = selection["selected_ids"]
    records = reader(path, columns=list(SOURCE_COLUMNS), filters=[("id", "in", ids)]).to_pylist()
    require(len(records) == len(ids) and {r["id"] for r in records} == set(ids), "Selected rows incomplete or duplicated")
    require({r["id"]: r["type"] for r in records} == {x["id"]: x["type"] for x in selection["selected"]}, "Selected type changed")
    from benchmarks.prepare_native_data import normalize_hotpot
    from benchmarks.hotpot_data import convert_hotpot
    data = convert_hotpot(json.loads(normalize_hotpot(records)), ids)
    data.seed, data.split, data.variant = SEED, "heldout", "hotpot_round5_t1_fresh512_v1"
    data.provenance["selection"] = PREFIX + " stratified SHA256,384bridge/128comparison"
    require(all(q.answerable is True and q.required for q in data.queries), "Selected annotation contract differs")
    return data


def prepare_data(args):
    bound = load_binding(args.binding)
    selection = load_selection(bound, args.binding)
    path = ROOT / bound["data_binding"]
    require(not path.exists(), "Never replace a data binding")
    published(bound, args.published_commit, [args.binding, ROOT / bound["selection"]])
    require(host() == bound["host"], "Selected data binding requires the original host and frozen dependencies")
    data = load_dataset(args.parquet, bound, selection)
    value = {"version": VERSION, "status": "selected-data-frozen-before-retrieval", "created_at": now(),
        "binding_sha256": sha(args.binding), "selection_sha256": sha(ROOT / bound["selection"]),
        "selection_publication_commit": args.published_commit, "dataset_sha256": data.fingerprint,
        "dataset_description": data.description(), "queries": {q.id: {"project": q.project,
            "required_evidence": len(q.required), "category": q.category,
            "input_query": scoring.query_projection(q.query), "expected_query": scoring.query_projection(q.query.strip())}
            for q in data.queries}, "retrieval_calls_executed": 0}
    save(path, value, exclusive=True)
    print(json.dumps({"data_binding": relative(path), "retrieval_calls_executed": 0,
                      "next": "Publish before the first native worker intent."}), flush=True)


def frozen_data(bound, binding_path, selection):
    path = ROOT / bound["data_binding"]
    committed(path)
    value = read(path)
    require(value["version"] == VERSION and value["status"] == "selected-data-frozen-before-retrieval"
            and value["binding_sha256"] == sha(binding_path) and value["selection_sha256"] == sha(ROOT / bound["selection"])
            and set(value["queries"]) == set(selection["selected_ids"])
            and all(type(x["required_evidence"]) is int and x["required_evidence"] > 0 for x in value["queries"].values())
            and value["retrieval_calls_executed"] == 0, "Data binding changed")
    return value
