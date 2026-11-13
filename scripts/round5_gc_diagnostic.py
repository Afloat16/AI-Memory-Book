"""Registered E lifetime/GC diagnosis; no timings, collector control or inference.

Bind first, commit/push the binding, then run the nine one-call probes followed
by the three 4,732-call workers in the printed order. Each invocation is a fresh
process. Commit/push each completed report before the next invocation. A failed
or interrupted attempt is never resumed or replaced. Audit only reads files.
"""
from __future__ import annotations

import argparse
import ast
import gc
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import signal
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "round5-gc-diagnostic-1"
SCOPE = "benchmarks/experiments/round5-ranked-lifetime-addendum.json"
SCOPE_COMMIT = "10b04c8fdcfd0ecc95492e17b2a764c62a0651f1"
SCOPE_SHA = "3bead725a2761d184ba62d76e07d7d9a06573a21f139764f6b34da21c09f142e"
SOURCES = {
    "v032": ("692fb959ddf8934c5f516ba3d74ceb4385a2fa82", "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"),
    "candidate-d": ("c67757305d6334b74d98c34ffbfab9b8ebdd6e27", "bdfb117368c937ad4da9076c71a2f454eba49ae85ed0057872eac199c3022c16"),
    "candidate-e": ("0f8d34c452bbab8918bcf7f11ec6c12214d70050", "5caa9a72d73eef7121e81f4823f583dc35fc246a1b61b792829bdd275787127b"),
}
REGISTRATIONS = {
    "benchmarks/experiments/round5-plan.json": "7068594181c7e98c576f68a81daf85cd0d06c729",
    "benchmarks/experiments/round5-materialization-addendum.json": "9042570d8cff01be7c95cd01f8698e166fc7d313",
    "benchmarks/experiments/round5-canonical-row-addendum.json": "c724452e8f7333af73ed8a0424f572b7d7280a07",
    "benchmarks/experiments/round5-derived-map-addendum.json": "0e933580a2a7d28f24b0ac7a8a2f5db4acfb762d",
    SCOPE: SCOPE_COMMIT,
}
PROFILE = "scripts/round4_development_profile.py"
REFERENCE = "benchmarks/reports/round4-development/candidate-c2-manifest.json"
REFERENCE_SHA = "4e1b098f32a89c7c8363c8ee67e02af54bb438965a72e773ec0ef199fb2cca00"
LOCOMO_SHA = "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
FILES = ("scripts/round5_gc_diagnostic.py", "tests/test_round5_gc_diagnostic.py",
         PROFILE, "scripts/benchmark_default_recall.py", "tests/test_round5_materialization.py",
         "benchmarks/run.py", "benchmarks/data.py", "benchmarks/public_data.py",
         "benchmarks/token_compare.py", "benchmarks/query_guard.py", "benchmarks/locomo_split.json",
         "benchmarks/experiments/round2-default-recall-performance-plan.json")
COHORTS = ("synthetic61", "public1015")
CONFIGS = (("native-char4000", {"budget_chars": 4000}),
           ("native-token512", {"budget_chars": 8000, "budget_tokens": 512}),
           ("native-token1024", {"budget_chars": 8000, "budget_tokens": 1024}),
           ("native-token2048", {"budget_chars": 8000, "budget_tokens": 2048}))
CASES = ("fused", "identical-route", "single-route")
PHASES = ("evaluator", "recall_other", "source_prepare", "token_assembly")
COUNTER_FIELDS = ("starts", "stops", "collected", "uncollectable")
SETTINGS = {"cache_size": 0, "use_cache": False, "limit": 5, "semantic": False,
            "coverage": False, "tokenizer": "cl100k_base", "query_shuffle_seed": 41061}


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    return sha(raw(value).rstrip(b"\n"))


def is_digest(value):
    return type(value) is str and len(value) == 64 and all(letter in "0123456789abcdef" for letter in value)


def local(path):
    value = (ROOT / path).resolve()
    value.relative_to(ROOT)
    return value


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def file_sha(path):
    return sha(Path(path).read_bytes())


def read(path):
    value = Path(path).read_bytes()
    return json.loads(gzip.decompress(value) if str(path).endswith(".gz") else value)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30,
                                   stderr=subprocess.DEVNULL)


def committed(path, ref="HEAD"):
    require(Path(path).read_bytes() == git("show", ref + ":" + relative(path)),
            "Commit and push the exact artifact before continuing: " + relative(path))


def publish_new(path, value, *, compressed=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = raw(value)
    if compressed is None:
        compressed = str(path).endswith(".gz")
    if compressed:
        data = gzip.compress(data, mtime=0)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def save_owned(path, report):
    """Only update this process's exclusively claimed report; retain partials."""
    current = read(path)
    require(current["attempt_id"] == report["attempt_id"], "Report ownership changed")
    report["save_sequence"] += 1
    partial = path.with_name(path.name + f".partial-{report['save_sequence']:04d}")
    publish_new(partial, report, compressed=str(path).endswith(".gz"))
    partial.replace(path)


def registered():
    for name, commit in REGISTRATIONS.items():
        require(local(name).read_bytes() == git("show", commit + ":" + name),
                "Registered bytes changed: " + name)
    require(file_sha(local(SCOPE)) == SCOPE_SHA, "Wrong E registration")
    scope = read(local(SCOPE))
    require(scope["prior_candidate_commit"] == SOURCES["candidate-d"][0] and
            scope["prior_candidate_runtime_sha256"] == SOURCES["candidate-d"][1], "Wrong D parent")
    require(file_sha(local(PROFILE)) == "593b9f0667b1fc1cb3e38f5cc8411620759bc5abae68c56816221b950f99a416",
            "Frozen profile helper changed")
    require(file_sha(local("scripts/benchmark_default_recall.py")) ==
            "ce74bd117ef54da865963f6a185f40707dbf8a0eaf0019957288b71edf8c305a", "Dataset helper changed")


def source_files(path):
    package = local(path) / "memory_book"
    return {p.relative_to(package).as_posix(): p.read_bytes() for p in sorted(package.rglob("*.py"))}


def runtime_hash(files):
    result = hashlib.sha256()
    for name, value in sorted(files.items()):
        result.update(name.encode() + b"\0" + value + b"\0")
    return result.hexdigest()


def verify_source(label, path):
    commit, expected = SOURCES[label]
    files = source_files(path)
    names = git("ls-tree", "-r", "--name-only", commit, "--", "src/memory_book").decode().splitlines()
    names = [name for name in names if name.endswith(".py")]
    require(set(files) == {name.removeprefix("src/memory_book/") for name in names}, "Source file set changed")
    for name in names:
        require(files[name.removeprefix("src/memory_book/")] == git("show", commit + ":" + name),
                "Source differs from named commit: " + label)
    require(runtime_hash(files) == expected, "Runtime source changed: " + label)
    return {"path": relative(local(path)), "commit": commit, "runtime_sha256": expected}


def verify_one_clear(d_files, e_files):
    require(set(d_files) == set(e_files), "E changed package membership")
    for name in d_files:
        if name != "store.py":
            require(d_files[name] == e_files[name], "E changed another runtime file")
    original, candidate = ast.parse(d_files["store.py"]), ast.parse(e_files["store.py"])
    removed = 0
    for node in ast.walk(candidate):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "late_materialize":
            if len(node.body) < 2:
                continue
            last = node.body[-1]
            expected = ast.parse("ranked_rows.clear()").body[0]
            if ast.dump(last) == ast.dump(expected):
                require(isinstance(node.body[-2], ast.For), "Clear is not after the entire prefix loop")
                node.body.pop()
                removed += 1
    require(removed == 1 and ast.dump(original) == ast.dump(candidate), "E is not exactly one allowed clear")


def reference_cells():
    require(file_sha(local(REFERENCE)) == REFERENCE_SHA, "Original profile manifest changed")
    manifest = read(local(REFERENCE))
    require(manifest["runtime_source_sha256"] == SOURCES["v032"][1] and
            manifest["completed_calls"] == 4732, "Wrong original profile")
    cells, files = [], {REFERENCE: REFERENCE_SHA}
    expected = [(cohort, config) for cohort in COHORTS for config, _ in CONFIGS]
    for item, pair in zip(manifest["cells"], expected):
        path = local(REFERENCE).parent / item["path"]
        payload = gzip.decompress(path.read_bytes())
        require(file_sha(path) == item["sha256"] and sha(payload) == item["uncompressed_sha256"],
                "Original profile cell changed")
        cell = json.loads(payload)
        require((cell["cohort"], cell["configuration"]) == pair and cell["status"] == "completed",
                "Original cell order changed")
        ids = [row["query_id"] for row in cell["rows"]]
        hashes = [row["non_timing_payload_sha256"] for row in cell["rows"]]
        require(len(ids) == len(set(ids)) == (168 if pair[0] == "synthetic61" else 1015), "Wrong query IDs")
        cells.append({"cohort": pair[0], "configuration": pair[1], "dataset_sha256": cell["dataset_sha256"],
                      "reference": relative(path), "reference_sha256": item["sha256"],
                      "query_ids": ids, "expected_payload_sha256": hashes})
        files[relative(path)] = item["sha256"]
    require(len(manifest["cells"]) == len(cells) == 8, "Wrong old profile cell count")
    return cells, files


def cell_bindings(cells):
    return [{key: cell[key] for key in ("cohort", "configuration", "dataset_sha256", "reference", "reference_sha256")} |
            {"query_count": len(cell["query_ids"]), "query_ids_sha256": digest(cell["query_ids"]),
             "payloads_sha256": digest(cell["expected_payload_sha256"])} for cell in cells]


def environment():
    return {"implementation": sys.implementation.name, "version": sys.version,
            "executable": str(Path(sys.executable).resolve()), "platform": platform.platform(),
            "sqlite_version": sqlite3.sqlite_version,
            "tiktoken_version": importlib.metadata.version("tiktoken")}


def gc_state():
    return {"enabled": gc.isenabled(), "threshold": list(gc.get_threshold()), "debug": gc.get_debug()}


def boundary():
    return {"stats": gc.get_stats(), "count": list(gc.get_count())}


def schedule(bound):
    result = []
    for label in SOURCES:
        for case in CASES:
            result.append({"kind": "probe", "label": label, "case": case, "expected_calls": 1})
    result.extend({"kind": "worker", "label": label, "case": None, "expected_calls": 4732} for label in SOURCES)
    for index, job in enumerate(result):
        name = f"{index + 1:02d}-{job['kind']}-{job['label']}" + ("-" + job["case"] if job["case"] else "")
        job.update(index=index, report=bound["results_root"] + "/" + name + ".json.gz",
                   state=bound["state_root"] + "/" + name)
    return result


def bind(args):
    registered()
    relative(args.output)
    cells, files = reference_cells()
    files.update({name: file_sha(local(name)) for name in (*FILES, *REGISTRATIONS)})
    commit = git("rev-parse", "HEAD").decode().strip()
    remote = git("rev-parse", "--symbolic-full-name", "@{upstream}").decode().strip()
    require(remote.startswith("refs/remotes/"), "An explicit remote tracking branch is required")
    for name in files:
        committed(local(name))
        committed(local(name), remote)
    sources = {label: verify_source(label, path) for label, path in zip(SOURCES,
               (args.baseline_src, args.candidate_d_src, args.candidate_e_src))}
    verify_one_clear(source_files(sources["candidate-d"]["path"]), source_files(sources["candidate-e"]["path"]))
    require(file_sha(args.locomo_path) == LOCOMO_SHA, "Wrong old LoCoMo file")
    state, results = relative(args.state), relative(args.results)
    require(state != results and not local(state).exists() and not local(results).exists(), "Use fresh state and results")
    require(not local(state).is_relative_to(local(results)) and not local(results).is_relative_to(local(state)),
            "State and results roots must not overlap")
    require(gc_state()["enabled"] and gc_state()["debug"] == 0 and not gc.callbacks, "Use default enabled GC without callbacks")
    value = {"version": VERSION, "scope_commit": SCOPE_COMMIT, "scope_sha256": SCOPE_SHA,
             "evaluator_commit": commit, "remote_ref": remote, "files": files, "sources": sources,
             "python": environment(), "gc_state": gc_state(), "settings": SETTINGS,
             "locomo": {"path": relative(args.locomo_path), "sha256": LOCOMO_SHA},
             "state_root": state, "results_root": results, "cells": cell_bindings(cells),
             "total_probe_calls": 9, "total_frequency_calls": 14196}
    value["jobs"] = schedule(value)
    publish_new(args.output, value)
    print(json.dumps({"binding": relative(args.output), "jobs": value["jobs"]}), flush=True)


def load_binding(path):
    registered()
    bound = read(path)
    require(bound["version"] == VERSION and bound["scope_commit"] == SCOPE_COMMIT and
            bound["scope_sha256"] == SCOPE_SHA and bound["settings"] == SETTINGS, "Wrong diagnostic binding")
    committed(path)
    committed(path, bound["remote_ref"])
    cells, files = reference_cells()
    files.update({name: file_sha(local(name)) for name in (*FILES, *REGISTRATIONS)})
    require(bound["files"] == files and bound["cells"] == cell_bindings(cells) and bound["jobs"] == schedule(bound),
            "Binding contents changed")
    require(bound["total_probe_calls"] == 9 and bound["total_frequency_calls"] == 14196, "Wrong call allowance")
    for name, expected in files.items():
        require(sha(git("show", bound["evaluator_commit"] + ":" + name)) == expected, "Evaluator commit changed")
        committed(local(name))
    for label in SOURCES:
        require(bound["sources"][label] == verify_source(label, bound["sources"][label]["path"]), "Source pin changed")
    verify_one_clear(source_files(bound["sources"]["candidate-d"]["path"]),
                     source_files(bound["sources"]["candidate-e"]["path"]))
    require(bound["locomo"]["sha256"] == LOCOMO_SHA == file_sha(local(bound["locomo"]["path"])), "Input changed")
    # Same immutable reference arrays in every fresh measurement interpreter;
    # no previous diagnostic reports are loaded by its private entry point.
    bound["_expected_cells"] = cells
    return bound


class Counters:
    """All tracked storage is allocated before callback installation."""

    def __init__(self):
        self.values = [[[[0, 0, 0, 0] for _ in range(3)] for _ in PHASES] for _ in range(9)]
        self.calls = [[0, 0] for _ in range(9)]
        self.cell, self.phase = 8, 0

    def callback(self, event, info):
        bucket = self.values[self.cell][self.phase][info["generation"]]
        if event == "start":
            bucket[0] += 1
        elif event == "stop":
            bucket[1] += 1
            bucket[2] += info["collected"]
            bucket[3] += info["uncollectable"]


def forwarding_wrappers(module, counters):
    prepare, assemble = module.prepare_source_units, module.assemble_with_count

    def prepare_source_units(pages, turns, refs_by_page):
        previous = counters.phase
        counters.phase = 2
        counters.calls[counters.cell][0] += 1
        try:
            return prepare(pages, turns, refs_by_page)
        finally:
            counters.phase = previous

    def assemble_with_count(legacy, pages, query_terms, *, budget_chars, budget_tokens,
                            counter, source_units_for=None):
        previous = counters.phase
        counters.phase = 3
        counters.calls[counters.cell][1] += 1
        try:
            return assemble(legacy, pages, query_terms, budget_chars=budget_chars,
                            budget_tokens=budget_tokens, counter=counter, source_units_for=source_units_for)
        finally:
            counters.phase = previous

    return prepare_source_units, assemble_with_count


def imported(bound, label):
    require("memory_book" not in sys.modules, "Each task requires a fresh process")
    source = local(bound["sources"][label]["path"])
    sys.path[:0] = [str(source), str(ROOT)]
    import memory_book
    from memory_book import token_budget
    require(Path(memory_book.__file__).resolve().parent == source / "memory_book", "Another runtime was imported")
    return memory_book.MemoryBook, token_budget


def owner_snapshot(values):
    """Probe-only: return scalars, never retain a frame, Row or field value."""
    routes = values["routes"]
    route_owners = {id(row) for route in routes for row in route}
    rows, metadata = values["rows"], values.get("metadata_by_id", {})
    item_owners = route_owners | {id(row) for row in metadata.values()}
    ranked = values.get("ranked_rows", [])
    return {"ranked_present": "ranked_rows" in values, "ranked_count": len(ranked),
            "ranked_tracked_count": sum(gc.is_tracked(entry) for entry in ranked),
            "route_count": len(routes), "route_row_count": sum(len(route) for route in routes),
            "native_union_rows": sum(type(row) is sqlite3.Row for row in rows.values()),
            "metadata_owner_rows": len(metadata),
            "candidate_count": values["candidate_count"] if "candidate_count" in values else len(values["candidates"]),
            "use_stem": values["use_stem"], "fuse_routes": values["fuse_routes"],
            "late_materialize": values.get("late_materialize", False),
            "tuple_route_owners_complete": all(id(entry[2]) in route_owners for entry in ranked),
            "tuple_item_owners_complete": all(id(entry[3]) in item_owners for entry in ranked),
            "native_union_owned_by_routes": all(id(row) in route_owners for row in rows.values()
                                                if type(row) is sqlite3.Row)}


def probe_run(bound, job, report):
    Book, module = imported(bound, job["label"])
    from tests.test_round5_materialization import fixture_sources
    module.TokenCounter("cl100k_base").count("Prepare the reference tokenizer before profiling.")
    original = module.assemble_with_count
    snapshots = []

    def assemble_with_count(legacy, pages, query_terms, *, budget_chars, budget_tokens,
                            counter, source_units_for=None):
        frame = sys._getframe(1)
        try:
            snapshots.append(owner_snapshot(frame.f_locals))
        finally:
            del frame
        return original(legacy, pages, query_terms, budget_chars=budget_chars,
                        budget_tokens=budget_tokens, counter=counter, source_units_for=source_units_for)

    sources = fixture_sources()
    report["fixture_sha256"] = digest(sources)
    report["snapshots"] = snapshots
    module.assemble_with_count = assemble_with_count
    try:
        with Book(local(job["state"]) / "fixture.db", segmentation="turn", max_page_chars=3000,
                  min_page_chars=0, cache_size=0) as book:
            for source in sources:
                book.ingest(source)
            report["attempted_calls"] = 1
            result = book.recall("qzx17" if job["case"] == "identical-route" else "orbiting relay",
                project="lab", strategy="flat" if job["case"] == "single-route" else "book",
                budget_chars=8000, budget_tokens=1024, use_cache=False)
            result.pop("latency_ms")
            report["payload_sha256"] = digest(result)
            report["completed_calls"] = 1
            report["transaction_closed"] = not book.db.in_transaction
            report["cache_entries"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
    finally:
        module.assemble_with_count = original
        report["wrappers_restored"] = module.assemble_with_count is original
    require(len(snapshots) == 1, "Probe must inspect assembly entry exactly once")


def frequency_run(bound, job, report, checkpoint):
    Book, module = imported(bound, job["label"])
    from scripts.benchmark_default_recall import dataset
    counters = Counters()
    cells = [{"cohort": spec["cohort"], "configuration": spec["configuration"],
              "dataset_sha256": spec["dataset_sha256"], "query_ids": spec["query_ids"],
              "payload_sha256": [None] * len(spec["query_ids"]), "attempted": 0, "completed": 0,
              "status": "pending", "counters": counters.values[index], "wrapper_calls": counters.calls[index],
              "before": None, "after": None, "transaction_closed": None, "cache_entries": None}
             for index, spec in enumerate(bound["_expected_cells"])]
    report.update(cells=cells, outside_cell_counters=counters.values[8],
                  outside_cell_wrapper_calls=counters.calls[8], phase_names=PHASES, counter_fields=COUNTER_FIELDS)
    prepare, assemble = module.prepare_source_units, module.assemble_with_count
    wrapped_prepare, wrapped_assemble = forwarding_wrappers(module, counters)
    callback = counters.callback
    report["before"] = boundary()
    gc.callbacks.append(callback)
    module.prepare_source_units, module.assemble_with_count = wrapped_prepare, wrapped_assemble
    try:
        module.TokenCounter("cl100k_base").count("Prepare the reference tokenizer before profiling.")
        for cohort_index, cohort in enumerate(COHORTS):
            data = dataset(cohort, local(bound["locomo"]["path"]))
            queries = list(data.queries)
            random.Random(41061).shuffle(queries)
            require([case.id for case in queries] == cells[cohort_index * 4]["query_ids"] and
                    data.fingerprint == cells[cohort_index * 4]["dataset_sha256"], "Frozen cohort changed")
            with Book(local(job["state"]) / (cohort + ".db"), cache_size=0) as book:
                for source in data.sessions:
                    book.ingest(source)
                for config_index, (_, options) in enumerate(CONFIGS):
                    index = cohort_index * 4 + config_index
                    cell = cells[index]
                    cell.update(status="running", before=boundary())
                    counters.cell = index
                    try:
                        for position, case in enumerate(queries):
                            cell["attempted"] += 1
                            report["attempted_calls"] += 1
                            counters.phase = 1
                            try:
                                result = book.recall(case.query, project=case.project, use_cache=False, **options)
                            finally:
                                counters.phase = 0
                            result.pop("latency_ms")
                            cell["payload_sha256"][position] = digest(result)
                            cell["completed"] += 1
                            report["completed_calls"] += 1
                            require(cell["payload_sha256"][position] == bound["_expected_cells"][index]["expected_payload_sha256"][position],
                                    "Complete non-timing payload differs from the original baseline")
                        cell["transaction_closed"] = not book.db.in_transaction
                        cell["cache_entries"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                        cell["status"] = "completed"
                    finally:
                        counters.cell, counters.phase = 8, 0
                        cell["after"] = boundary()
                        checkpoint()
    finally:
        counters.cell, counters.phase = 8, 0
        module.prepare_source_units, module.assemble_with_count = prepare, assemble
        gc.callbacks.remove(callback)
        report["after"] = boundary()
        report["wrappers_restored"] = module.prepare_source_units is prepare and module.assemble_with_count is assemble


def validate_counters(values):
    require(type(values) is list and len(values) == 4, "Wrong phase counters")
    for phase in values:
        require(type(phase) is list and len(phase) == 3, "Wrong generation counters")
        for bucket in phase:
            require(type(bucket) is list and len(bucket) == 4 and
                    all(type(value) is int and value >= 0 for value in bucket), "Malformed GC counter")
            require(bucket[0] == bucket[1], "Incomplete GC callback start/stop pair")


def validate_boundary(value):
    require(set(value) == {"stats", "count"} and len(value["stats"]) == len(value["count"]) == 3,
            "Malformed boundary snapshot")
    require(all(type(number) is int and number >= 0 for number in value["count"]), "Invalid get_count values")
    for stats in value["stats"]:
        require(set(stats) == {"collections", "collected", "uncollectable"} and
                all(type(number) is int and number >= 0 for number in stats.values()), "Invalid get_stats values")


def validate_window(before, after, counter_groups):
    validate_boundary(before)
    validate_boundary(after)
    for generation in range(3):
        start, end = before["stats"][generation], after["stats"][generation]
        require(all(end[key] >= start[key] for key in start), "GC statistics moved backwards")
        observed = sum(phase[generation][1] for group in counter_groups for phase in group)
        require(observed <= end["collections"] - start["collections"], "Callbacks exceed boundary collection delta")
    # No equality: snapshot construction/serialization can collect in evaluator
    # phase outside a cell's callback window. get_count is never a frequency.


def validate_report(bound, job, report, binding_sha):
    require(report["version"] == VERSION and report["job"] == job and report["binding_sha256"] == binding_sha,
            "Wrong report identity")
    require(report["source"] == bound["sources"][job["label"]] and report["python"] == bound["python"], "Wrong runtime identity")
    require(report["gc_state_before"] == report["gc_state_after"] == bound["gc_state"] and
            report["callbacks_restored"] is True and report["wrappers_restored"] is True, "Instrumentation/state was not restored")
    require(report["inputs_verified_after"] is True, "Missing input postcheck")
    require(report["process_boundary"] == "exec-fresh-interpreter-no-prefix-reports", "Missing fresh interpreter boundary")
    require(report["status"] == "completed" and type(report["attempted_calls"]) is int and
            type(report["completed_calls"]) is int and report["attempted_calls"] == report["completed_calls"] == job["expected_calls"],
            "Incomplete or failed report")
    if job["kind"] == "probe":
        require(len(report["snapshots"]) == 1 and report["transaction_closed"] is True and
                type(report["cache_entries"]) is int and report["cache_entries"] == 0,
                "Invalid probe lifecycle")
        value = report["snapshots"][0]
        require(value["use_stem"] is (job["case"] != "single-route") and
                value["fuse_routes"] is (job["case"] == "fused"), "Probe did not exercise its registered route")
        require(all(value[key] is True for key in ("tuple_route_owners_complete", "tuple_item_owners_complete",
                                                   "native_union_owned_by_routes")), "A Row lost its other owner")
        expected = value["candidate_count"] if job["label"] == "candidate-d" else 0
        require(all(type(value[key]) is int and value[key] >= 0 for key in
                    ("candidate_count", "ranked_count", "ranked_tracked_count", "route_count", "route_row_count",
                     "native_union_rows", "metadata_owner_rows")) and value["candidate_count"] > 0 and value["ranked_count"] == expected and
                0 <= value["ranked_tracked_count"] <= value["ranked_count"], "Unexpected ranking tuple lifetime")
        require(value["ranked_present"] is (job["label"] != "v032") and
                value["late_materialize"] is (job["label"] != "v032"), "Wrong late materialization path")
        require(is_digest(report["payload_sha256"]) and is_digest(report["fixture_sha256"]), "Invalid probe digest")
    else:
        require(report["phase_names"] == list(PHASES) and report["counter_fields"] == list(COUNTER_FIELDS), "Wrong counter axes")
        require(len(report["cells"]) == 8, "Incomplete frequency cells")
        for cell, expected in zip(report["cells"], bound["_expected_cells"]):
            for key in ("cohort", "configuration", "dataset_sha256", "query_ids"):
                require(cell[key] == expected[key], "Frequency cell changed")
            require(cell["payload_sha256"] == expected["expected_payload_sha256"], "Frequency payload mismatch")
            count = len(expected["query_ids"])
            require(cell["status"] == "completed" and type(cell["attempted"]) is int and type(cell["completed"]) is int and
                    cell["attempted"] == cell["completed"] == count and cell["transaction_closed"] is True and
                    type(cell["cache_entries"]) is int and cell["cache_entries"] == 0, "Incomplete cell lifecycle")
            require(len(cell["wrapper_calls"]) == 2 and all(type(n) is int and 0 <= n <= count for n in cell["wrapper_calls"]),
                    "Bad wrapper call counts")
            require(cell["wrapper_calls"][1] == (0 if cell["configuration"] == "native-char4000" else count),
                    "Assembly wrapper did not forward once per token call")
            validate_counters(cell["counters"])
            validate_window(cell["before"], cell["after"], [cell["counters"]])
        validate_counters(report["outside_cell_counters"])
        require(report["outside_cell_wrapper_calls"] == [0, 0], "Unexpected wrapper call outside query cells")
        validate_window(report["before"], report["after"],
                        [cell["counters"] for cell in report["cells"]] + [report["outside_cell_counters"]])


def compare_probes(reports):
    for case in CASES:
        group = [report for report in reports if report["job"]["kind"] == "probe" and report["job"]["case"] == case]
        if not group:
            continue
        require(len({report["payload_sha256"] for report in group}) == 1 and
                len({report["fixture_sha256"] for report in group}) == 1, "Probe payload/fixture mismatch")
        late = [report["snapshots"][0] for report in group if report["job"]["label"] != "v032"]
        for key in ("route_count", "route_row_count", "native_union_rows", "metadata_owner_rows", "candidate_count"):
            require(len({row[key] for row in late}) <= 1, "D/E owner inventory changed")


def audit_prefix(bound, binding_sha, count):
    reports = []
    for job in bound["jobs"][:count]:
        path = local(job["report"])
        # The nine fresh probes may be checkpointed as one batch. All probes
        # and previous corpus workers must be durable before a corpus worker.
        if count >= 9:
            committed(path)
            committed(path, bound["remote_ref"])
        require(not list(path.parent.glob(path.name + ".partial-*")), "Preserve an incomplete checkpoint")
        value = read(path)
        validate_report(bound, job, value, binding_sha)
        reports.append(value)
    compare_probes(reports)
    return reports


def refuse_replay(bound, start):
    for job in bound["jobs"][start:]:
        path = local(job["report"])
        require(not path.exists() and not local(job["state"]).exists() and
                not list(path.parent.glob(path.name + ".partial-*")), "Never replay an existing attempt")


def execute(args):
    """Controller only. Exec discards ALL prefix/provenance allocation history."""
    bound = load_binding(args.binding)
    index = next(job["index"] for job in bound["jobs"] if job["kind"] == args.command and
                 job["label"] == args.label and job["case"] == getattr(args, "case", None))
    binding_sha = file_sha(args.binding)
    audit_prefix(bound, binding_sha, index)
    refuse_replay(bound, index)
    require(environment() == bound["python"] and gc_state() == bound["gc_state"] and not gc.callbacks,
            "Use the bound interpreter/default GC state in a fresh process")
    job = bound["jobs"][index]
    local(job["state"]).mkdir(parents=True, exist_ok=False)
    path = local(job["report"])
    report = {"version": VERSION, "binding_sha256": binding_sha, "job": job,
              "source": bound["sources"][job["label"]], "python": environment(),
              "gc_state_before": gc_state(), "status": "running", "attempted_calls": 0,
              "completed_calls": 0, "save_sequence": 0, "attempt_id": f"{binding_sha}:{index}:{os.getpid()}"}
    publish_new(path, report)
    try:
        os.execv(sys.executable, [sys.executable, "-B", str(ROOT / "scripts/round5_gc_diagnostic.py"),
                                 "_run", "--binding", str(args.binding.resolve()), "--index", str(index)])
    except BaseException as error:
        report.update(status="failed", error_type=type(error).__name__, error_sha256=sha(str(error).encode()))
        save_owned(path, report)
        raise


def internal_run(args):
    """Fresh interpreter; same bound references, never any prefix report audit."""
    bound = load_binding(args.binding)
    require(type(args.index) is int and 0 <= args.index < 12, "Invalid private job index")
    job = bound["jobs"][args.index]
    binding_sha = file_sha(args.binding)
    path = local(job["report"])
    report = read(path)
    require(report["attempt_id"] == f"{binding_sha}:{args.index}:{os.getpid()}" and
            report["job"] == job and report["status"] == "running" and report["save_sequence"] == 0 and
            report["attempted_calls"] == report["completed_calls"] == 0, "Private entry requires the same live controller claim")
    # A second private invocation is forbidden even with the same PID/claim.
    publish_new(local(job["state"]) / "started.json", {"attempt_id": report["attempt_id"], "binding_sha256": binding_sha})
    report["process_boundary"] = "exec-fresh-interpreter-no-prefix-reports"
    old_handler = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise InterruptedError("Diagnostic process terminated")

    signal.signal(signal.SIGTERM, terminate)
    try:
        require(environment() == bound["python"] and gc_state() == bound["gc_state"] and not gc.callbacks,
                "Fresh interpreter/GC state differs from binding")
        report["gc_state_before"] = gc_state()
        if job["kind"] == "probe":
            probe_run(bound, job, report)
        else:
            frequency_run(bound, job, report, lambda: save_owned(path, report))
        require(verify_source(job["label"], report["source"]["path"]) == report["source"], "Runtime changed during worker")
        require(file_sha(local(bound["locomo"]["path"])) == LOCOMO_SHA, "Corpus changed during worker")
        require(file_sha(args.binding) == binding_sha and all(file_sha(local(name)) == expected
                for name, expected in bound["files"].items()), "Binding/evaluator inputs changed during worker")
        report.update(status="completed", gc_state_after=gc_state(), callbacks_restored=not gc.callbacks,
                      inputs_verified_after=True)
        # JSON normalization makes in-memory tuples and saved arrays identical.
        validate_report(bound, job, json.loads(raw(report)), binding_sha)
    except BaseException as error:
        report.update(status="failed", error_type=type(error).__name__, error_sha256=sha(str(error).encode()))
        raise
    finally:
        report.update(gc_state_after=gc_state(), callbacks_restored=not gc.callbacks)
        signal.signal(signal.SIGTERM, old_handler)
        save_owned(path, report)
    print(json.dumps({"report": job["report"], "completed_calls": report["completed_calls"],
                      "sha256": file_sha(path), "next": "Commit and push this report before the next task."}), flush=True)


def decision(d, e):
    def total(report, *, cohort=None, configuration=None, phases=(2, 3), generations=(0, 1)):
        return sum(cell["counters"][phase][generation][1] for cell in report["cells"]
                   if (cohort is None or cell["cohort"] == cohort) and
                      (configuration is None or cell["configuration"] == configuration) and
                      (phases != (2, 3) or cell["configuration"] != "native-char4000")
                   for phase in phases for generation in generations)
    comparisons = {}
    for cohort in COHORTS:
        comparisons[cohort + "_token_gen01"] = [total(d, cohort=cohort), total(e, cohort=cohort)]
    comparisons["synthetic_token1024_gen01"] = [total(report, cohort="synthetic61", configuration="native-token1024")
                                               for report in (d, e)]
    comparisons["all_recall_collections"] = [total(report, phases=(1, 2, 3), generations=(0, 1, 2)) for report in (d, e)]
    comparisons["all_recall_gen2"] = [total(report, phases=(1, 2, 3), generations=(2,)) for report in (d, e)]
    flags = {key: pair[1] < pair[0] if key.endswith("gen01") else pair[1] <= pair[0]
             for key, pair in comparisons.items()}
    return {"comparator": "E relative to D", "values_d_then_e": comparisons, "conditions": flags,
            "supported": all(flags.values()), "meaning": "Frequency evidence only; no speed or cause-of-old-regression claim."}


def audit(args):
    bound = load_binding(args.binding)
    relative(args.output)
    reports = audit_prefix(bound, file_sha(args.binding), 12)
    frequencies = {report["job"]["label"]: report for report in reports if report["job"]["kind"] == "worker"}
    require(sum(report["completed_calls"] for report in reports) == 14205, "Wrong complete call count")
    value = {"version": VERSION, "status": "completed", "binding_sha256": file_sha(args.binding),
             "probe_calls": 9, "frequency_calls": 14196, "payload_pairs_against_v032": 9464,
             "artifacts": {job["report"]: file_sha(local(job["report"])) for job in bound["jobs"]},
             "decision": decision(frequencies["candidate-d"], frequencies["candidate-e"])}
    publish_new(args.output, value)
    print(json.dumps(value["decision"]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("bind")
    for option in ("baseline-src", "candidate-d-src", "candidate-e-src", "locomo-path", "state", "results", "output"):
        command.add_argument("--" + option, type=Path, required=True)
    for name in ("probe", "worker", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--binding", type=Path, required=True)
        if name == "audit":
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--label", choices=SOURCES, required=True)
            if name == "probe":
                command.add_argument("--case", choices=CASES, required=True)
    command = commands.add_parser("_run", help=argparse.SUPPRESS)
    command.add_argument("--binding", type=Path, required=True)
    command.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    try:
        {"bind": bind, "probe": execute, "worker": execute, "audit": audit, "_run": internal_run}[args.command](args)
    except BaseException as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "error_sha256": sha(str(error).encode()), "policy": "Preserve this attempt; no retry."}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
