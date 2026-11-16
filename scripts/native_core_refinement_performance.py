"""Frozen native core refinement against released native v0.8.1.

Old synthetic61/public1015 inputs are performance and compatibility regressions,
not new retrieval-quality evidence. Only committed plans, evaluator files and
runtime sources may measure. Every worker runs once in a fresh process; failed
or interrupted workers are preserved, never silently repeated. No benchmark
downloads data or builds an extension. Build and input provenance are explicit.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import subprocess
import sys
import sysconfig
import tempfile
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.data import generate_dataset
from benchmarks.public_data import load_locomo
from benchmarks.run import original_turn_texts, percentile

PROTOCOL = "native-core-refinement-performance-4"
BASELINE = "56eccd8c3a6f1d5637664607936da2595ce50c62"
PRIOR_ATTEMPT = {
    "run_id": 43871304560,
    "evaluator_commit": "346e5ede35851fd6283bc8be8a34bf4243dc34dd",
    "candidate_commit": "0be1f09502aff1d4ddc0a9e644be7a62be6a944f",
    "evidence_commit": "4e1e6177e9af188a582b2f2e28aafe6290dfae36",
    "disposition": "Not accepted for release: unchanged reingestion regressed in all four rounds in both cohorts. All first-attempt results and costs remain retained."
}
ORDERS = [["baseline", "candidate"], ["candidate", "baseline"],
          ["candidate", "baseline"], ["baseline", "candidate"]]
COHORTS = {
    "synthetic61": {"queries": 168, "sha256": "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26"},
    "public1015": {"queries": 1015, "sha256": "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"},
}
CONFIGS = {
    "native-char2400": {"surface": "native", "budget_chars": 2400, "budget_tokens": None},
    "mcp-char2400": {"surface": "official-sdk-mcp-stdio", "budget_chars": 2400, "budget_tokens": None},
    "native-token1024": {"surface": "native", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
    "mcp-token1024": {"surface": "official-sdk-mcp-stdio", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
}
EVALUATOR_FILES = ("scripts/native_core_refinement_performance.py", "benchmarks/__init__.py",
                   "benchmarks/data.py", "benchmarks/public_data.py", "benchmarks/run.py",
                   "benchmarks/locomo_split.json", "tests/test_native_core_refinement_performance.py",
                   "scripts/native_core_refinement_host.py", "scripts/native_core_refinement_preserve.py",
                   ".github/workflows/native-core-refinement-performance.yml", "scripts/native_incremental_performance.py",
                   "scripts/native_core_performance.py")
BUILD_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in", "Cargo.toml", "Cargo.lock", "README.md", "LICENSE")
SOURCE_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")
HOST_COLUMNS = {"projects": {"created_at", "updated_at"},
                "chapters": {"updated_at"}, "sessions": {"updated_at"}}
ROW_STABLE = ("query_id", "payload_sha256", "native_payload_sha256", "context_sha256",
              "envelope_sha256", "context_chars", "context_tokens", "result_count", "invariants")
INVARIANT_KEYS = {"scope", "source_spans", "page_projection", "context_reconstruction", "metadata",
                  "character_budget", "result_limit", "token_budget", "token_metadata"}
NATIVE_HELPERS = ("terms_ascii", "ascii_tokens", "unicode_tokens", "fold_excerpt_source", "evidence_units",
                  "identifier_aliases", "literal_positions")
# The unreleased joined_turns dispatch was slower through the measured public wrapper.
# Keep the frozen Python _joined body and build_pages' current-global callback.
CANDIDATE_HELPERS = (*NATIVE_HELPERS, "strip_nonspacing_marks", "identifier_has_boundary", "excerpt_window",
    "rank_candidates", "select_novelty", "context_allocations", "refs_from_parsed",
    "source_units", "projected_units", "source_map_matches",
    "make_turns", "page_cuts", "build_pages", "segment_turns", "segmentation_ready")
BUILD_POLICY = {"definition": "source-commit-bound-per-label", "compiler_and_flags": "identical",
                "native_compilation": "one-native-extension-all-c-h-inputs"}
RESOURCE_COMPARISONS = ("fresh_ingestion_ms", "unchanged_reingestion_ms")
PROBE_HELPERS = {"baseline": NATIVE_HELPERS, "candidate": CANDIDATE_HELPERS}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(dump(value).encode())


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write(path, value, *, exclusive=False):
    path = Path(path)
    raw = (dump(value) + "\n").encode()
    if path.suffix == ".gz":
        raw = gzip.compress(raw, mtime=0)
    if exclusive:
        with path.open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    else:
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(raw)
        temporary.replace(path)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def committed_file(name):
    raw = (ROOT / name).read_bytes()
    require(raw == git("show", "HEAD:" + name), "Commit exact evaluator/plan bytes first: " + name)
    return sha(raw)


def validate_plan(plan):
    require(plan.get("schema_version") == 4 and plan.get("protocol") == PROTOCOL, "Unknown native-core-refinement plan protocol")
    require(plan.get("prior_attempt") == PRIOR_ATTEMPT, "Retain the complete rejected first-attempt identity")
    require(set(plan["sources"]) == {"baseline", "candidate"}, "Unexpected source label")
    require(plan["sources"]["baseline"] == {"commit": BASELINE, "backend": "native"},
            "Baseline must be the released native v0.8.1 commit")
    candidate = plan["sources"]["candidate"]
    require(set(candidate) == {"commit", "backend"} and candidate.get("backend") == "native"
            and len(candidate.get("commit", "")) == 40
            and all(c in "0123456789abcdef" for c in candidate["commit"])
            and candidate["commit"] != BASELINE, "Freeze a distinct candidate native source commit")
    require(plan["engine_order"] == ORDERS, "Use all four balanced AB/BA/BA/AB rounds")
    require(plan.get("repetitions_per_worker") == 3, "Use all three registered passes per worker/configuration")
    require(plan["cohorts"] == list(COHORTS), "Retain both registered regression cohorts")
    require(plan["configurations"] == list(CONFIGS), "Retain all primary and secondary performance cells")
    require(plan.get("primary") == ["native-char2400", "mcp-char2400"]
            and plan.get("secondary") == ["native-token1024", "mcp-token1024"], "Primary/secondary designation differs")
    require(plan.get("query_seed") == 110061 and plan.get("limit") == 5, "Query order/result limit differs")
    require(plan.get("excluded_native_response_fields") == ["latency_ms"], "Only native latency_ms may be excluded")
    require(plan.get("result_cache") == "disabled-native-cleared-before-each-mcp-call", "Cache policy differs")
    require(plan.get("build_policy") == BUILD_POLICY, "Native source/build policy differs")
    require(plan.get("resource_comparisons") == list(RESOURCE_COMPARISONS), "Retain both ingestion batch comparisons")
    probes = plan.get("native_helper_calls", {})
    effective = plan.get("native_helper_effective_calls", {})
    fallback = plan.get("native_helper_fallback_calls", {})
    require(set(probes) == set(effective) == set(fallback) == set(PROBE_HELPERS),
            "Freeze both native helper inventories and effective/fallback counts")
    for label, helpers in PROBE_HELPERS.items():
        require(set(probes[label]) == set(effective[label]) == set(fallback[label]) == set(helpers)
                and all(type(count) is int and count > 0 for count in probes[label].values())
                and all(type(count) is int and count > 0 for count in effective[label].values())
                and all(type(count) is int and count >= 0 for count in fallback[label].values())
                and all(probes[label][name] == effective[label][name] + fallback[label][name] for name in helpers),
                "Every native helper needs frozen positive effective calls and complete fallback accounting: " + label)
    calls = 2 * 4 * 3 * len(CONFIGS) * sum(COHORTS[name]["queries"] for name in COHORTS)
    require(plan.get("expected_timed_calls") == calls and plan.get("expected_paired_calls") == calls // 2,
            "Declared matrix counts differ from all registered attempts")
    return plan


def validate_build_manifest(build, sources):
    require(build.get("schema_version") == 4 and build.get("status") == "completed"
            and set(build.get("builds", {})) == {"baseline", "candidate"}, "Both native builds must be retained")
    require(build.get("workflow_run_id") and build.get("workflow_run_attempt") == 1
            and len(build.get("workflow_commit", "")) == 40, "Missing hosted first-attempt build identity")
    for label, source in sources.items():
        record = build["builds"][label]
        require(record.get("status") == "completed" and record.get("source_commit") == source["commit"]
                and record.get("backend") == source["backend"] == "native"
                and all(record.get(key) for key in ("command", "compiler", "flags", "build_log_sha256")),
                "Native build provenance differs: " + label)
        require(record.get("native_binaries") == source["native_binaries"], "Built binary differs: " + label)
    baseline, candidate = (build["builds"][label] for label in ("baseline", "candidate"))
    require(all(baseline[key] == candidate[key] for key in ("command", "compiler", "flags")),
            "Both native sources must use the same compiler, command and flags")
    for label, source in sources.items():
        record = build["builds"][label]
        expected_inputs = {name: value for name, value in source["source_files"].items()
                           if name in BUILD_FILES}
        expected_native = {name: value for name, value in source["source_files"].items()
                           if name.startswith("src/memory_book/") and Path(name).suffix in {".c", ".h"}}
        require(record.get("build_inputs") == expected_inputs, "Per-source build inputs differ: " + label)
        require(record.get("native_source_inputs") == expected_native and expected_native,
                "Complete native source/header inputs differ: " + label)
    return build


def evaluator_manifest(plan_path):
    name = str(plan_path.resolve().relative_to(ROOT))
    return {path: committed_file(path) for path in (*EVALUATOR_FILES, name)}


def source_manifest(source, specification):
    """Bind every runtime file, build configuration and built native binary.

    Source archives need no second Git checkout. All package bytes are checked
    against the declared commit in this repository's object database. Historical
    build files may be unmaterialized; their committed hashes remain explicit.
    The candidate build files must exist and match the frozen source commit.
    """
    source = source.resolve()
    commit = specification["commit"]
    names = git("ls-tree", "-r", "--name-only", commit, "src/memory_book", *BUILD_FILES).decode().splitlines()
    require(names and "src/memory_book/__init__.py" in names, "Missing frozen runtime source")
    files, unmaterialized = {}, []
    for name in names:
        expected = sha(git("show", commit + ":" + name))
        path = source.parent / name
        if path.is_file():
            require(sha(path.read_bytes()) == expected, "Runtime/build file differs from source commit: " + name)
        else:
            require(not name.startswith("src/") and specification["backend"] == "python", "Missing frozen runtime/build file: " + name)
            unmaterialized.append(name)
        files[name] = expected
    package = source / "memory_book"
    binaries = {}
    for path in sorted(package.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        name = str(path.relative_to(source.parent))
        if path.suffix in {".so", ".pyd", ".dll", ".dylib"}:
            binaries[name] = sha(path.read_bytes())
        elif path.suffix != ".pyc":
            require(name in files, "Untracked runtime file: " + name)
    require((len(binaries) == 1 and next(iter(binaries)).split("/")[-1].startswith("_native."))
            if specification["backend"] == "native" else not binaries, "Native binary inventory differs from requested backend")
    return {**specification, "source_files": files, "source_files_sha256": digest(files),
            "unmaterialized_build_files": unmaterialized, "native_binaries": binaries}


def verify_source(source, manifest):
    root = Path(source).resolve().parent
    for name, expected in {**manifest["source_files"], **manifest["native_binaries"]}.items():
        if name in manifest["unmaterialized_build_files"]:
            continue
        require(sha((root / name).read_bytes()) == expected, "Bound source or binary changed: " + name)
    expected = {name for name in manifest["source_files"] if name.startswith("src/memory_book/")}
    expected.update(manifest["native_binaries"])
    observed = {str(p.relative_to(root)) for p in (root / "src/memory_book").rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    require(observed == expected, "Runtime package file inventory changed")


def dataset(name, locomo):
    data = generate_dataset(seed=61, split="development", projects=8) if name == "synthetic61" else load_locomo(Path(locomo))
    require(len(data.queries) == COHORTS[name]["queries"] and data.fingerprint == COHORTS[name]["sha256"], "Frozen cohort differs")
    return data


def host_identity():
    packages = {}
    for name in ("mcp", "pydantic", "tiktoken", "setuptools"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    model = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                  if line.startswith("model name")), None)
    return {"python": sys.version, "executable": sys.executable, "sqlite": sqlite3.sqlite_version,
            "unicode": unicodedata.unidata_version, "cpu_model": model,
            "platform": platform.platform(), "machine": platform.machine(), "hostname": platform.node(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "cpu_count": os.cpu_count(), "affinity": sorted(os.sched_getaffinity(0)), "packages": packages,
            "python_build": {key: sysconfig.get_config_var(key) for key in ("CC", "CFLAGS", "LDSHARED", "SOABI")}}


def usage(pid="self"):
    status = Path(f"/proc/{pid}/status").read_text()
    values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in status.splitlines()
              if line.startswith(("VmRSS:", "VmHWM:"))}
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    ticks = os.sysconf("SC_CLK_TCK")
    return {"rss_bytes": values["VmRSS"], "hwm_bytes": values["VmHWM"],
            "user_cpu_s": int(fields[11]) / ticks, "system_cpu_s": int(fields[12]) / ticks}


def server_pid(db):
    children = set()
    for task in Path("/proc/self/task").iterdir():
        try:
            children.update((task / "children").read_text().split())
        except FileNotFoundError:
            continue
    found = []
    for pid in children:
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if b"memory_book" in args and os.fsencode(db) in args:
                found.append(pid)
        except FileNotFoundError:
            continue
    require(len(found) == 1, "Exactly one live official-SDK child must be observable")
    return found[0]


def storage(connection, path):
    return {"logical_db_bytes": connection.execute("PRAGMA page_count").fetchone()[0]
            * connection.execute("PRAGMA page_size").fetchone()[0],
            "file_bytes": {suffix or "db": Path(str(path) + suffix).stat().st_size
                           if Path(str(path) + suffix).exists() else 0 for suffix in ("", "-wal", "-shm")}}


def archive_state(connection, *, retain_host_times=False):
    """Hash complete originals, IDs, source offsets, derived FTS and schema."""
    tables = {}
    for table in SOURCE_TABLES:
        columns = [r[1] for r in connection.execute(f'PRAGMA table_info("{table}")')]
        excluded = set() if retain_host_times else HOST_COLUMNS.get(table, set())
        require(excluded <= set(columns), "Source schema differs")
        columns = [name for name in columns if name not in excluded]
        selection = ",".join('"' + name + '"' for name in columns)
        rows = [list(row) for row in connection.execute(f'SELECT {selection} FROM "{table}" ORDER BY id')]
        tables[table] = {"columns": columns, "excluded_host_columns": sorted(excluded), "rows": len(rows), "sha256": digest(rows)}
    for table in ("pages_fts", "pages_stem_fts"):
        rows = [list(row) for row in connection.execute(f"SELECT rowid,title,question,body,directory FROM {table} ORDER BY rowid")]
        tables[table] = {"rows": len(rows), "sha256": digest(rows)}
    tables["schema"] = digest([list(row) for row in connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")])
    tables["meta"] = digest([list(row) for row in connection.execute("SELECT * FROM meta ORDER BY key")])
    tables["user_version"] = connection.execute("PRAGMA user_version").fetchone()[0]
    tables["application_id"] = connection.execute("PRAGMA application_id").fetchone()[0]
    return tables


def validate_response(case, native, config, sources, pages, counter):
    context = native["context"]
    errors = {"scope": 0, "source_spans": 0, "page_projection": 0, "context_reconstruction": 0,
              "metadata": int(native.get("query") != case.query or native.get("cache_hit") is not False
                              or native.get("budget_chars") != config["budget_chars"]
                              or native.get("context_chars") != len(context)),
              "character_budget": int(len(context) > config["budget_chars"]),
              "result_limit": int(len(native["results"]) > 5 or len({r["id"] for r in native["results"]}) != len(native["results"])),
              "token_budget": 0, "token_metadata": 0}
    cursor = 0
    for index, result in enumerate(native["results"]):
        project = result["breadcrumb"][0]["id"]
        errors["scope"] += int(case.project is not None and project != case.project)
        original = pages.get(result["id"])
        spans = result.get("excerpt_spans", [])
        good = original is not None and len(spans) == 1
        if good:
            start, end = spans[0]
            good = type(start) is int and type(end) is int and 0 <= start < end <= len(original)
            if good:
                excerpt = original[start:end]
                rendered = ("…" if start else "") + excerpt + ("…" if end < len(original) else "")
                good = result["text"] in (excerpt, rendered)
        errors["page_projection"] += int(not good)
        for ref in result["source_refs"]:
            errors["scope"] += int(ref.get("project") != project)
            source = sources.get((ref.get("project"), ref["session_id"], ref["turn_index"]))
            start, end = ref.get("turn_start"), ref.get("turn_end")
            errors["source_spans"] += int(source is None or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(source) or source[start:end] not in result["text"])
        beginning = cursor + (2 if index else 0)
        if index and context[cursor:beginning] != "\n\n":
            errors["context_reconstruction"] += 1
        body = context.find("\n" + result["text"], beginning)
        if body < beginning or not result["text"]:
            errors["context_reconstruction"] += 1
        cursor = body + 1 + len(result["text"])
    errors["context_reconstruction"] += int(cursor != len(context))
    tokens = len(counter.encode(context, disallowed_special=())) if counter is not None else None
    if config["budget_tokens"] is not None:
        errors["token_budget"] = int(tokens > config["budget_tokens"])
        errors["token_metadata"] = int(any(native.get(key) != value for key, value in {
            "budget_tokens": 1024, "tokenizer": "cl100k_base", "tokenizer_version": "0.12.0", "context_tokens": tokens}.items()))
    return errors, tokens


def make_row(case, native, config, sources, pages, counter, elapsed, cpu_ms, payload, envelope=None, *, repetition):
    invariants, tokens = validate_response(case, native, config, sources, pages, counter)
    return {"query_id": case.id, "repetition": repetition, "category": case.category, "wall_ms": elapsed,
            "calling_process_cpu_ms": cpu_ms, "payload_sha256": sha(payload.encode()),
            "native_payload_sha256": digest(native), "context_sha256": sha(native["context"].encode()),
            "envelope_sha256": sha(envelope.encode()) if envelope is not None else None,
            "context_chars": len(native["context"]), "context_tokens": tokens,
            "result_count": len(native["results"]), "invariants": invariants}


def summary(values):
    require(values and all(type(v) in (float, int) and math.isfinite(v) and v > 0 for v in values), "Invalid timing samples")
    return {"samples": len(values), "mean_ms": statistics.fmean(values),
            "p50_ms": percentile(values, .5), "p95_ms": percentile(values, .95),
            "min_ms": min(values), "max_ms": max(values)}


class Ledger:
    def __init__(self, path):
        self.raw = path.open("xb")
        self.compressed = gzip.GzipFile(filename="", mode="wb", fileobj=self.raw, mtime=0)

    def event(self, event, config, query_id, repetition, row=None):
        self.compressed.write((dump({"event": event, "configuration": config, "query_id": query_id,
                                    "repetition": repetition, "attempt_id": f"{config}:p{repetition}:{query_id}",
                                    **({"row": row} if row is not None else {})}) + "\n").encode())
        self.compressed.flush()
        self.raw.flush()

    def close(self):
        self.compressed.close()
        self.raw.flush()
        os.fsync(self.raw.fileno())
        self.raw.close()


def common_probe_suite():
    """Identical non-corpus public-wrapper inputs for both frozen runtimes.

    The isolated memory book and source-unit cache are discarded. This may
    initialize Python modules, regexes and SQLite library state, but never a
    measured database, query-result cache or tokenizer vocabulary.
    """
    from dataclasses import asdict
    from memory_book import MemoryBook, text, segmentation, store, token_budget
    lexical = [text.terms("HTTPParser requestTimeout", query=True),
               text.terms("café déjà", query=True),
               text.terms("为什么内存隔离必须安全？", query=True),
               text._fold_excerpt_source("Straße cafe\u0301 Å🙂"),
               text._evidence_units("First sentence. Second clause！\n短句", 8),
               text.identifier_terms("HTTPParser parseHTTPResponse xml_http_request", query=True),
               text.identifier_terms("HTTPParser parseHTTPResponse xml_http_request", query=False),
               text.excerpt("prefix " * 20 + "café HTTPParser suffix " * 20,
                            "cafe parser", 32, prepared_terms=["cafe", "parser"])]
    messages = [
        {"role": "system", "content": "Preserve original messages."},
        {"role": "user", "content": "How does HTTPParser keep the cache?"},
        {"role": "assistant", "content": "The café cache preserves source coordinates. 中🙂\n" * 4},
        {"role": "tool", "content": "Cache validation passed."},
        {"role": "user", "content": "And what is the pressure?"},
        {"role": "assistant", "content": "The quartz pressure is 37 pascals.\n\nSecond complete fact."},
        {"role": "user", "content": "Independent source note"},
        {"role": "assistant", "content": "A source note remains exact."},
    ]
    turns = segmentation.make_turns(messages)
    joined = segmentation._joined(turns)
    structure = {"turns": [asdict(turn) for turn in turns], "joined": joined,
                 "cuts": segmentation._cuts(joined[0], 53),
                 "pages": [asdict(page) for page in segmentation._pages(turns, 113)],
                 "sections": {mode: [asdict(section) for section in
                     segmentation.segment(turns, mode, 180, 24, .22)]
                     for mode in ("adaptive", "turn", "session")}}
    original = "ASSISTANT: First complete café fact. 中🙂\n\n" + chr(96) * 3 + "python\nvalue = 37\n" + chr(96) * 3 + "\nLast intact sentence."
    source_turns = {("probe-session", 0): original}
    row = {"id": "probe-page", "session_pk": "probe-session", "content": original}
    refs = [{"turn_index": 0, "start": 0, "end": len(original),
             "turn_start": 0, "turn_end": len(original), "message_indices": [1, 2]}]
    cache = {}
    projection = token_budget._projected_units(row, source_turns, cache, refs)
    source_units = {"units": token_budget.source_units(original), "projected": projection,
        "certificate": token_budget._source_map_matches(row, source_turns, refs),
        "cache": [[list(key), value] for key, value in sorted(cache.items())]}
    pages = [{"id": "page-a", "project_id": "probe", "session_id": "source-a",
              "created_at": "2026-01-01T00:00:00Z", "content": original},
             {"id": "page-b", "project_id": "probe", "session_id": "source-b",
              "created_at": "2026-01-02T00:00:00Z", "content": "A short fact."}]
    allocations = store._context_allocations(pages, 230)
    clipped = store._refs_from_parsed(refs, [(4, len(original) - 4)])
    before_now = store._now
    try:
        store._now = lambda: "2026-01-03T00:00:00+00:00"
        with MemoryBook(":memory:", cache_size=0, max_page_chars=240, min_page_chars=0) as book:
            ingestions = [book.ingest({"project": "probe" if i < 7 else "foreign",
                "session_id": "probe-" + str(i), "task_id": "task-" + str(i % 3),
                "task_title": "Quartz pressure cache", "title": "Cache source " + str(i % 2),
                "created_at": f"2026-01-{i + 1:02d}T00:00:00+00:00",
                "messages": [{"role": "user", "content": "quartz pressure and HTTPParser cache"},
                             {"role": "assistant", "content": f"The quartz pressure is {37 + i} pascals. " +
                              "The café cached source is exact. 中🙂 " * 5}]})
                for i in range(8)]
            recall = book.recall("quartz pressure", project="probe", limit=3,
                                 budget_chars=430, use_cache=False)
            recall.pop("latency_ms")
    finally:
        store._now = before_now
    return {"lexical": lexical, "structure": structure, "source_units": source_units,
            "allocations": allocations, "clipped": clipped, "ingestions": ingestions, "recall": recall}


def dispatch_probe(text, native, expected_hits, expected_effective=None, expected_fallback=None):
    """Wrap one helper at a time, outside every ingestion/query timer.

    Cross-helper identity guards remain effective. Every instrumented suite must
    equal an uninstrumented execution of the same inputs. Capture mode with
    expected_hits=None is development-only; a frozen plan always supplies counts.
    """
    original_binding = getattr(text, "_NATIVE", None)
    require(original_binding is native, "Text wrappers do not target the bound native module")
    available = sorted(name for name in dir(native) if not name.startswith("_"))
    inventory = set(available)
    require(inventory in (set(NATIVE_HELPERS), set(CANDIDATE_HELPERS)),
            "Native helper inventory differs from either registered source")
    if expected_hits is not None:
        require(inventory == set(expected_hits), "Native helper inventory differs from the frozen probe")
    if expected_hits is not None:
        expected_effective = expected_hits if expected_effective is None else expected_effective
        expected_fallback = dict.fromkeys(expected_hits, 0) if expected_fallback is None else expected_fallback
        require(set(expected_effective) == set(expected_fallback) == inventory,
                "Native effective/fallback inventory differs from the frozen probe")
    originals = {name: getattr(native, name) for name in available}
    reference = digest(common_probe_suite())
    hits, effective, fallback, output_hashes = {}, {}, {}, {}
    for name in available:
        count = declined = 0
        function = originals[name]
        def invoke(*args, **kwargs):
            nonlocal count, declined
            count += 1
            result = function(*args, **kwargs)
            if result is NotImplemented:
                declined += 1
            return result
        setattr(native, name, invoke)
        try:
            output_hashes[name] = digest(common_probe_suite())
        finally:
            setattr(native, name, function)
        hits[name], fallback[name], effective[name] = count, declined, count - declined
        require(count > 0 and (expected_hits is None or count == expected_hits[name]),
                "Native helper dispatch counts differ from the frozen probe: " + name)
        require(effective[name] > 0, "Native helper returned only NotImplemented for ordinary probe inputs: " + name)
        if expected_hits is not None:
            require(effective[name] == expected_effective[name] and fallback[name] == expected_fallback[name],
                    "Native helper effective/fallback counts differ from the frozen probe: " + name)
        require(output_hashes[name] == reference, "Instrumentation changed public-wrapper outputs: " + name)
    require(getattr(text, "_NATIVE", None) is original_binding
            and all(getattr(native, name) is function for name, function in originals.items()),
            "Probe instrumentation was not restored")
    return {"native_helper_calls": hits, "native_helper_effective_calls": effective,
            "native_helper_fallback_calls": fallback, "outputs_sha256": reference,
            "per_helper_outputs_sha256": output_hashes, "uninstrumented_outputs_sha256": reference,
            "instrumentation_restored": True,
            "scope": "Identical isolated non-corpus wrapper suite; one native method wrapped at a time; all probes removed before measured database creation."}


def active_backend(source, expected_hits, expected_effective=None, expected_fallback=None):
    import memory_book
    from memory_book import text, _text_backend
    require(Path(memory_book.__file__).resolve().parent == Path(source).resolve() / "memory_book", "Wrong runtime imported")
    require(_text_backend.BACKEND_NAME == "native" and _text_backend.REQUESTED_BACKEND == "native"
            and _text_backend.NATIVE is not None, "A native source silently fell back to Python")
    from memory_book import store, segmentation, token_budget
    modules = {"text": text, "store": store, "segmentation": segmentation, "token_budget": token_budget}
    bindings = {name: getattr(module, "_NATIVE") is _text_backend.NATIVE
                for name, module in modules.items() if hasattr(module, "_NATIVE")}
    require(bindings.get("text") is True and all(bindings.values()), "Runtime wrappers target different native modules")
    if hasattr(_text_backend.NATIVE, "rank_candidates"):
        require(set(bindings) == set(modules), "Candidate native wrapper family is missing")
    native = Path(_text_backend.NATIVE.__file__).resolve()
    require(native.parent == Path(source).resolve() / "memory_book", "Loaded native binary outside bound runtime")
    return {"requested": "native", "actual": "native", "binary_sha256": sha(native.read_bytes()),
            "available_functions": sorted(name for name in dir(_text_backend.NATIVE) if not name.startswith("_")),
            "wrapper_bindings": bindings,
            "dispatch_probe": dispatch_probe(text, _text_backend.NATIVE, expected_hits, expected_effective, expected_fallback)}


async def mcp_calls(data, config_id, order, db, work, source, backend, sources, pages, counter, ledger):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import _json, recall_payload
    config = CONFIGS[config_id]
    environment = {**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONHASHSEED": "0", "MEMORY_BOOK_TEXT_BACKEND": backend,
                   "MEMORY_BOOK_DB": str(db), "MEMORY_BOOK_HOME": str(work / "home")}
    if environment.get("TIKTOKEN_CACHE_DIR"):
        environment["TIKTOKEN_CACHE_DIR"] = str(Path(environment["TIKTOKEN_CACHE_DIR"]).resolve())
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(db), "mcp"], env=environment, cwd=str(work))
    rows, resource = [], {}
    cases = {case.id: case for case in data.queries}
    with sqlite3.connect(db) as cache:
        started = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                resource["startup_to_initialize_ms"] = (time.perf_counter_ns() - started) / 1e6
                tools = await client.list_tools()
                resource["tool_schema_sha256"] = sha(tools.model_dump_json(exclude_none=True).encode())
                resource["instructions_sha256"] = sha((initialized.instructions or "").encode())
                pid = server_pid(db)
                resource["server_before_calls"] = usage(pid)
                for attempt in order:
                    identity, repetition = attempt["query_id"], attempt["repetition"]
                    case = cases[identity]
                    cache.execute("DELETE FROM recall_cache")
                    cache.commit()
                    require(cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0, "MCP result cache not empty")
                    arguments = {"query": case.query, "project": case.project, "limit": 5, "budget_chars": config["budget_chars"]}
                    if config["budget_tokens"] is not None:
                        arguments.update(budget_tokens=1024, tokenizer="cl100k_base")
                    ledger.event("started", config_id, identity, repetition)
                    cpu = time.process_time_ns()
                    started = time.perf_counter_ns()
                    response = await client.call_tool("recall_memory", arguments)
                    elapsed = (time.perf_counter_ns() - started) / 1e6
                    cpu_ms = (time.process_time_ns() - cpu) / 1e6
                    require(not response.isError and all(part.type == "text" for part in response.content), "MCP tool returned error/non-text")
                    payload = "\n".join(part.text for part in response.content)
                    cached = cache.execute("SELECT payload FROM recall_cache").fetchall()
                    require(len(cached) == 1, "MCP must preserve exactly one full native provenance record")
                    native = json.loads(cached[0][0])
                    require("latency_ms" not in native and payload == _json(recall_payload(native)), "MCP projection differs from full native provenance")
                    row = make_row(case, native, config, sources, pages, counter, elapsed, cpu_ms, payload,
                                   response.model_dump_json(exclude_none=True), repetition=repetition)
                    rows.append(row)
                    ledger.event("finished", config_id, identity, repetition, row)
                    require(not any(row["invariants"].values()), "MCP source/scope/budget invariant failed")
                resource["server_after_calls"] = usage(pid)
                resource["storage_live"] = storage(cache, db)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
    return rows, resource


def worker(directory, key):
    run = read(directory / "run.json")
    item = next(item for item in run["schedule"] if item["key"] == key)
    intent = read(directory / (key + ".started.json"))
    require(intent.get("worker") == item and intent.get("run_sha256") == digest(run), "Worker has no matching immutable execution intent")
    manifest = run["sources"][item["label"]]
    source = Path(run["source_paths"][item["label"]])
    verify_source(source, manifest)
    require(host_identity() == run["host"], "Worker host/environment changed")
    require({name: sha((ROOT / name).read_bytes()) for name in run["evaluator"]} == run["evaluator"], "Evaluator changed")
    sys.path.insert(0, str(source))
    os.environ["MEMORY_BOOK_TEXT_BACKEND"] = manifest["backend"]
    started = time.perf_counter_ns()
    from memory_book import MemoryBook
    import_ms = (time.perf_counter_ns() - started) / 1e6
    backend = active_backend(source, run["plan"]["native_helper_calls"][item["label"]],
        run["plan"]["native_helper_effective_calls"][item["label"]],
        run["plan"]["native_helper_fallback_calls"][item["label"]])
    data = dataset(item["cohort"], run["locomo_path"])
    report = {**item, "status": "running", "run_sha256": digest(run), "started_at": now(),
              "backend": backend, "source_manifest_sha256": digest(manifest), "runtime_import_ms": import_ms,
              "dataset": data.description(), "configurations": [], "resources": {}, "error": None}
    output = directory / (key + ".json.gz")
    ledger_path = directory / (key + ".attempts.jsonl.gz")
    ledger = Ledger(ledger_path)
    write(output, report, exclusive=True)
    try:
        with tempfile.TemporaryDirectory(prefix="native-language-", dir=directory) as temporary:
            work = Path(temporary)
            db = work / "memory.db"
            started = time.perf_counter_ns()
            with MemoryBook(db, cache_size=0) as book:
                report["resources"]["new_database_ms"] = (time.perf_counter_ns() - started) / 1e6
                ingested = report["ingestion_results"] = []
                report["ingestion_stage"] = "fresh-started"
                report["ingestion_order_sha256"] = digest([
                    {"project": session["project"], "session_id": session["session_id"]} for session in data.sessions])
                started = time.perf_counter_ns()
                for session in data.sessions:
                    ingested.append(book.ingest(session))
                report["resources"]["fresh_ingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["ingestion_sha256"] = digest(ingested)
                report["ingestion_stage"] = "fresh-completed"
                report["resources"]["after_ingestion"] = usage()
                report["resources"]["storage_after_ingestion"] = storage(book.db, db)
                replayed = report["unchanged_reingestion_results"] = []
                report["ingestion_stage"] = "unchanged-started"
                started = time.perf_counter_ns()
                for session in data.sessions:
                    replayed.append(book.ingest(session))
                report["resources"]["unchanged_reingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["unchanged_reingestion_sha256"] = digest(replayed)
                report["ingestion_stage"] = "completed"
                require(all(row["skipped"] for row in replayed), "Unchanged sessions were not all skipped")
                report["archive_before"] = archive_state(book.db)
                original_archive = archive_state(book.db, retain_host_times=True)
                sources = original_turn_texts(data)
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                counter = None
                for index, config_id in enumerate(run["plan"]["configurations"]):
                    config = CONFIGS[config_id]
                    if config["budget_tokens"] is not None and counter is None:
                        import tiktoken
                        require(tiktoken.__version__ == "0.12.0", "Token matrix requires frozen tiktoken 0.12.0")
                        counter = tiktoken.get_encoding("cl100k_base")
                        counter.encode("Initialize reference vocabulary outside timed calls.")
                    order = query_order([case.id for case in data.queries], item["round"], index)
                    cases = {case.id: case for case in data.queries}
                    active_counter = counter if config["budget_tokens"] is not None else None
                    if config["surface"] == "official-sdk-mcp-stdio":
                        rows, resource = asyncio.run(mcp_calls(data, config_id, order, db, work, source,
                            manifest["backend"], sources, pages, active_counter, ledger))
                    else:
                        rows = []
                        for attempt in order:
                            identity, repetition = attempt["query_id"], attempt["repetition"]
                            case = cases[identity]
                            require(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0, "Native result cache not empty")
                            options = {"project": case.project, "limit": 5, "budget_chars": config["budget_chars"], "use_cache": False}
                            if config["budget_tokens"] is not None:
                                options.update(budget_tokens=1024, tokenizer="cl100k_base")
                            ledger.event("started", config_id, identity, repetition)
                            cpu = time.process_time_ns()
                            started = time.perf_counter_ns()
                            native = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - started) / 1e6
                            cpu_ms = (time.process_time_ns() - cpu) / 1e6
                            native.pop("latency_ms")
                            row = make_row(case, native, config, sources, pages, active_counter, elapsed, cpu_ms, dump(native), repetition=repetition)
                            rows.append(row)
                            ledger.event("finished", config_id, identity, repetition, row)
                            require(not any(row["invariants"].values()), "Native source/scope/budget invariant failed")
                        require(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0, "Native unexpectedly wrote result cache")
                        resource = {"process_after_calls": usage()}
                    report["configurations"].append({"id": config_id, **config, "rows": rows,
                        "query_order_sha256": digest(order),
                        "latency": summary([row["wall_ms"] for row in rows]), "resources": resource})
                    write(output, report)
                    print(dump({"worker": key, "configuration": config_id, "completed_calls": len(rows)}), flush=True)
                report["archive_after"] = archive_state(book.db)
                require(original_archive == archive_state(book.db, retain_host_times=True), "Retrieval mutated original archive/index")
                report["resources"]["after_calls"] = usage()
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report["resources"]["storage_after_checkpoint"] = storage(book.db, db)
            started = time.perf_counter_ns()
            with MemoryBook(db, cache_size=0):
                report["resources"]["existing_database_open_ms"] = (time.perf_counter_ns() - started) / 1e6
        verify_source(source, manifest)
        report["source_unchanged"] = True
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        ledger.close()
        report["ledger_sha256"] = sha(ledger_path.read_bytes())
        report["finished_at"] = now()
        write(output, report)


def schedule(plan):
    return [{"key": f"r{round_}-{cohort}-{label}", "round": round_, "cohort": cohort, "label": label}
            for round_, labels in enumerate(plan["engine_order"]) for cohort in plan["cohorts"] for label in labels]


def query_order(identities, round_, configuration_index):
    order = []
    for repetition in range(3):
        values = list(identities)
        random.Random(110061 + 1009 * round_ + 97 * repetition + configuration_index).shuffle(values)
        order.extend({"query_id": identity, "repetition": repetition} for identity in values)
    return order


def stable(row):
    return {key: row[key] for key in ROW_STABLE}


def verify_ingestion_results(fresh, replayed, expected_order):
    """Validate this registered unique-session corpus against real ingest API semantics.

    Each fresh MemoryBook starts at global revision zero. Every first insertion
    advances that global value once; all later unchanged calls retain the final
    batch revision. Revision is not a per-session counter.
    """
    fields = {"project", "session_id", "chapter_id", "pages", "sections", "turns", "skipped", "revision"}
    counters = ("pages", "sections", "turns", "revision")
    stable_fields = ("project", "session_id", "chapter_id", "pages", "sections", "turns")
    require(type(expected_order) is list and expected_order
            and all(type(identity) is dict and set(identity) == {"project", "session_id"}
                    and all(type(identity[name]) is str and identity[name] for name in ("project", "session_id"))
                    for identity in expected_order),
            "Independent registered ingestion identity schema differs")
    identities = [(item["project"], item["session_id"]) for item in expected_order]
    require(len(set(identities)) == len(identities),
            "This fresh-ingestion contract requires the registered unique session identities")
    count = len(identities)
    require(type(fresh) is list and type(replayed) is list and len(fresh) == len(replayed) == count,
            "Independent complete ingestion batch lengths differ")
    for number, (identity, inserted, unchanged) in enumerate(zip(identities, fresh, replayed), 1):
        for row in (inserted, unchanged):
            require(type(row) is dict and set(row) == fields
                    and all(type(row[name]) is str and row[name] for name in ("project", "session_id", "chapter_id"))
                    and all(type(row[name]) is int and row[name] >= 0 for name in counters)
                    and type(row["skipped"]) is bool,
                    "Independent ingestion return schema/types differ")
            require((row["project"], row["session_id"]) == identity,
                    "Independent ingestion response does not match its ordered input")
        require(inserted["skipped"] is False and inserted["revision"] == number,
                "Independent fresh-ingestion skip/global revision semantics differ")
        require(unchanged["skipped"] is True and unchanged["revision"] == count,
                "Independent unchanged-ingestion skip/global revision semantics differ")
        require(all(inserted[name] == unchanged[name] for name in stable_fields),
                "Independent unchanged-ingestion structure differs from its fresh response")
    return {"sessions": count, **{name: sum(row[name] for row in fresh)
                                  for name in ("pages", "sections", "turns")}}


def verify_worker(report, run, directory):
    item = next(item for item in run["schedule"] if item["key"] == report["key"])
    require(all(report[key] == value for key, value in item.items()), "Worker identity differs")
    require(report["status"] == "completed" and report["source_unchanged"]
            and report["run_sha256"] == digest(run), "Worker incomplete/source unbound")
    require(report["source_manifest_sha256"] == digest(run["sources"][item["label"]]), "Worker source identity differs")
    backend = run["sources"][item["label"]]
    require(report["backend"]["actual"] == backend["backend"] and report["backend"]["requested"] == backend["backend"], "Worker backend differs")
    require(backend["backend"] == "native" and report["backend"]["binary_sha256"] in backend["native_binaries"].values(),
            "Worker native binary differs")
    probe = report["backend"]["dispatch_probe"]
    expected_hits = run["plan"]["native_helper_calls"][item["label"]]
    require(report["backend"]["available_functions"] == sorted(expected_hits), "Worker native helper inventory differs")
    require(probe["native_helper_calls"] == expected_hits and probe["instrumentation_restored"] is True, "Native dispatch identity probe differs")
    require(probe.get("native_helper_effective_calls") == run["plan"]["native_helper_effective_calls"][item["label"]]
            and probe.get("native_helper_fallback_calls") == run["plan"]["native_helper_fallback_calls"][item["label"]],
            "Native effective/fallback dispatch identity differs")
    require(probe.get("uninstrumented_outputs_sha256") == probe["outputs_sha256"]
            and probe.get("per_helper_outputs_sha256") == dict.fromkeys(expected_hits, probe["outputs_sha256"]),
            "Instrumented and ordinary public-wrapper outputs differ")
    required_bindings = {"text"} if item["label"] == "baseline" else {"text", "store", "segmentation", "token_budget"}
    require(report["backend"].get("wrapper_bindings") == dict.fromkeys(required_bindings, True),
            "Native wrapper family binding differs")
    expected_ingestion = run["ingestion_order"][item["cohort"]]
    require(report.get("ingestion_stage") == "completed"
            and report.get("ingestion_order_sha256") == digest(expected_ingestion), "Ingestion order/stage differs")
    for rows_field, digest_field in (("ingestion_results", "ingestion_sha256"),
                                     ("unchanged_reingestion_results", "unchanged_reingestion_sha256")):
        values = report.get(rows_field)
        require(type(values) is list and len(values) == len(expected_ingestion)
                and all(type(value) is dict for value in values)
                and digest(values) == report.get(digest_field), "Raw ingestion results differ: " + rows_field)
    ingestion_totals = verify_ingestion_results(report["ingestion_results"],
        report["unchanged_reingestion_results"], expected_ingestion)
    require(all(type(report["archive_before"].get(table)) is dict
                and type(report["archive_before"][table].get("rows")) is int
                and report["archive_before"][table]["rows"] == count
                for table, count in ingestion_totals.items()),
            "Ingestion returns differ from the complete archive table counts")
    for metric in RESOURCE_COMPARISONS:
        value = report["resources"].get(metric)
        require(type(value) in (int, float) and math.isfinite(value) and value > 0,
                "Invalid ingestion batch timing: " + metric)
    require(report["dataset"] == run["cohorts"][item["cohort"]], "Worker cohort differs")
    require(report["archive_before"] == report["archive_after"], "Worker archive changed")
    require([cell["id"] for cell in report["configurations"]] == run["plan"]["configurations"], "Worker matrix differs")
    expected_events = []
    for index, cell in enumerate(report["configurations"]):
        require({key: cell[key] for key in CONFIGS[cell["id"]]} == CONFIGS[cell["id"]], "Worker configuration changed")
        rows = cell["rows"]
        identities = run["query_ids"][item["cohort"]]
        require(len(identities) == COHORTS[item["cohort"]]["queries"] and len(set(identities)) == len(identities), "Worker query count or unique identities differ")
        expected = query_order(identities, item["round"], index)
        require([{key: row[key] for key in ("query_id", "repetition")} for row in rows] == expected, "Worker query identities/order differ")
        require(cell["query_order_sha256"] == digest(expected), "Worker query-order digest differs")
        require(all(set(row["invariants"]) == INVARIANT_KEYS and not any(row["invariants"].values()) for row in rows), "Worker invariant failure")
        require(all(type(row["calling_process_cpu_ms"]) in (int, float) and math.isfinite(row["calling_process_cpu_ms"])
                    and row["calling_process_cpu_ms"] >= 0 for row in rows), "Invalid calling-process CPU sample")
        require(cell["latency"] == summary([row["wall_ms"] for row in rows]), "Worker summary differs from raw rows")
        for row in rows:
            identity = {"configuration": cell["id"], "query_id": row["query_id"], "repetition": row["repetition"],
                        "attempt_id": f"{cell['id']}:p{row['repetition']}:{row['query_id']}"}
            expected_events.extend([{"event": "started", **identity}, {"event": "finished", **identity, "row": row}])
    ledger = directory / (item["key"] + ".attempts.jsonl.gz")
    raw = ledger.read_bytes()
    require(sha(raw) == report["ledger_sha256"], "Attempt ledger bytes differ")
    require([json.loads(line) for line in gzip.decompress(raw).splitlines()] == expected_events, "Started/finished attempt ledger differs")


def comparisons(reports, run):
    differences, cells = [], []
    workers = {(w["round"], w["cohort"], w["label"]): w for w in reports}
    for cohort in run["plan"]["cohorts"]:
        reference = workers[(0, cohort, "baseline")]
        for report in (w for w in reports if w["cohort"] == cohort):
            if report["backend"]["dispatch_probe"]["outputs_sha256"] != reference["backend"]["dispatch_probe"]["outputs_sha256"]:
                differences.append({"worker": report["key"], "field": "backend.dispatch_probe.outputs_sha256"})
            for field in ("archive_before", "archive_after", "ingestion_sha256", "unchanged_reingestion_sha256",
                          "ingestion_results", "unchanged_reingestion_results", "ingestion_order_sha256"):
                if report[field] != reference[field]:
                    differences.append({"worker": report["key"], "field": field})
        for config_id in run["plan"]["configurations"]:
            pooled = {label: [] for label in ("baseline", "candidate")}
            round_results = []
            canonical = None
            canonical_protocol = None
            for round_ in range(4):
                samples = {}
                for label in ("baseline", "candidate"):
                    work = workers[(round_, cohort, label)]
                    cell = next(cell for cell in work["configurations"] if cell["id"] == config_id)
                    if CONFIGS[config_id]["surface"] == "official-sdk-mcp-stdio":
                        protocol = {key: cell["resources"][key] for key in ("tool_schema_sha256", "instructions_sha256")}
                        if canonical_protocol is None:
                            canonical_protocol = protocol
                        if protocol != canonical_protocol:
                            differences.append({"worker": work["key"], "configuration": config_id, "protocol_metadata": "changed"})
                    values = {(row["repetition"], row["query_id"]): stable(row) for row in cell["rows"]}
                    if canonical is None:
                        canonical = values
                    if values != canonical:
                        differences.append({"worker": work["key"], "configuration": config_id,
                            "attempts": [list(identity) for identity in values if values[identity] != canonical.get(identity)]})
                    first_pass = {row["query_id"]: stable(row) for row in cell["rows"] if row["repetition"] == 0}
                    unstable = [{"query_id": row["query_id"], "repetition": row["repetition"]} for row in cell["rows"]
                                if stable(row) != first_pass[row["query_id"]]]
                    if unstable:
                        differences.append({"worker": work["key"], "configuration": config_id, "unstable_repetitions": unstable})
                    times = [row["wall_ms"] for row in cell["rows"]]
                    samples[label] = summary(times)
                    pooled[label].extend(times)
                round_results.append({"round": round_, **samples,
                    "p95_improvement_percent": 100 * (1 - samples["candidate"]["p95_ms"] / samples["baseline"]["p95_ms"])})
            values = {label: summary(times) for label, times in pooled.items()}
            cells.append({"cohort": cohort, "configuration": config_id, **values,
                "p50_improvement_percent": 100 * (1 - values["candidate"]["p50_ms"] / values["baseline"]["p50_ms"]),
                "p95_improvement_percent": 100 * (1 - values["candidate"]["p95_ms"] / values["baseline"]["p95_ms"]),
                "rounds": round_results})
    return {"complete_output_and_archive_equivalence": not differences, "differences": differences,
            "cells": cells, "scope": "Host-specific complete-output regression timings; no new retrieval-quality or cross-product claim. Negative improvements are regressions."}


def ingestion_comparisons(reports, run):
    """Retain four paired batch totals per cohort, including every regression."""
    workers = {(item["round"], item["cohort"], item["label"]): item for item in reports}
    comparisons = []
    for cohort in run["plan"]["cohorts"]:
        for metric in RESOURCE_COMPARISONS:
            rounds = []
            values = {label: [] for label in ("baseline", "candidate")}
            for round_ in range(4):
                pair = {label: workers[(round_, cohort, label)]["resources"][metric]
                        for label in values}
                for label, value in pair.items():
                    values[label].append(value)
                rounds.append({"round": round_, **pair,
                    "improvement_percent": 100 * (1 - pair["candidate"] / pair["baseline"])})
            totals = {label: sum(samples) for label, samples in values.items()}
            comparisons.append({"cohort": cohort, "metric": metric,
                "sessions_per_batch": len(run["ingestion_order"][cohort]), "paired_batches": 4,
                "baseline_ms": values["baseline"], "candidate_ms": values["candidate"],
                "baseline_total_ms": totals["baseline"], "candidate_total_ms": totals["candidate"],
                "baseline_median_ms": statistics.median(values["baseline"]),
                "candidate_median_ms": statistics.median(values["candidate"]),
                "total_improvement_percent": 100 * (1 - totals["candidate"] / totals["baseline"]),
                "rounds": rounds})
    return comparisons


def audit(directory):
    run = read(directory / "run.json")
    validate_plan(run["plan"])
    require(run["protocol"] == PROTOCOL, "Run protocol differs")
    require(all({key: run["sources"][label][key] for key in ("commit", "backend")} == spec
                for label, spec in run["plan"]["sources"].items()), "Run source identities differ from the frozen plan")
    validate_build_manifest(run["build_manifest"], run["sources"])
    require(run["build_manifest"]["workflow_commit"] == run["evaluator_commit"], "Build/evaluator commits differ")
    require(run["build_manifest"].get("host_preparation_sha256") == run["evaluator"]["scripts/native_core_refinement_host.py"],
            "Host preparation source differs from frozen evaluator")
    require(run["schedule"] == schedule(run["plan"]), "Run schedule differs")
    reports = []
    for item in run["schedule"]:
        report = read(directory / (item["key"] + ".json.gz"))
        verify_worker(report, run, directory)
        reports.append(report)
    compared = comparisons(reports, run)
    require(sum(len(cell["rows"]) for w in reports for cell in w["configurations"]) == run["plan"]["expected_timed_calls"],
            "Completed raw call count differs from the frozen plan")
    return {"protocol": PROTOCOL, "run_sha256": digest(run), "status": "completed",
            "attempted_calls": sum(len(cell["rows"]) for w in reports for cell in w["configurations"]),
            "paired_calls": sum(len(cell["rows"]) for w in reports if w["label"] == "candidate" for cell in w["configurations"]),
            "comparison": compared, "ingestion_comparisons": ingestion_comparisons(reports, run),
            "worker_resources": [{"key": w["key"], "runtime_import_ms": w["runtime_import_ms"],
                                  "resources": w["resources"], "configuration_resources": {
                                      c["id"]: c["resources"] for c in w["configurations"]}} for w in reports]}


def controller(args):
    require(sys.platform == "linux", "This registered resource protocol requires Linux procfs")
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/validation/native-core-refinement-formal-1"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "Formal timing requires the dedicated hosted first attempt")
    plan_path = args.plan.resolve()
    plan = validate_plan(read(plan_path))
    evaluator = evaluator_manifest(plan_path)
    sources = {label: source_manifest(getattr(args, label + "_src"), spec)
               for label, spec in plan["sources"].items()}
    build = read(args.build_manifest)
    validate_build_manifest(build, sources)
    require(build["workflow_commit"] == git("rev-parse", "HEAD").decode().strip(), "Build/evaluator commits differ")
    require(build["workflow_run_id"] == os.environ.get("GITHUB_RUN_ID"), "Build/timing run identities differ")
    require(build.get("host_preparation_sha256") == evaluator["scripts/native_core_refinement_host.py"],
            "Host preparation source differs from frozen evaluator")
    if "public1015" in plan["cohorts"]:
        require(args.locomo_path is not None, "Pinned public input required by this plan")
    host = host_identity()
    require(host["packages"]["mcp"] == "1.30.0" and host["packages"]["pydantic"] is not None, "Use frozen MCP SDK 1.30.0")
    if "native-token1024" in plan["configurations"]:
        require(host["packages"]["tiktoken"] == "0.12.0", "Use frozen tiktoken 0.12.0")
    data = {name: dataset(name, args.locomo_path) for name in plan["cohorts"]}
    run = {"protocol": PROTOCOL, "plan": plan, "plan_sha256": sha(plan_path.read_bytes()),
           "evaluator": evaluator, "evaluator_commit": git("rev-parse", "HEAD").decode().strip(),
           "sources": sources, "source_paths": {label: str(getattr(args, label + "_src").resolve()) for label in sources},
           "host": host, "build_manifest": build, "build_manifest_sha256": sha(args.build_manifest.read_bytes()),
           "locomo_path": str(args.locomo_path.resolve()) if args.locomo_path else None,
           "query_ids": {name: [case.id for case in value.queries] for name, value in data.items()},
           "ingestion_order": {name: [{"project": session["project"], "session_id": session["session_id"]}
               for session in value.sessions] for name, value in data.items()},
           "cohorts": {name: value.description() for name, value in data.items()}, "schedule": schedule(plan),
           "query_order_sha256": {f"r{round_}-{name}-{config_id}": digest(query_order([case.id for case in value.queries], round_, index))
               for name, value in data.items() for round_ in range(4) for index, config_id in enumerate(plan["configurations"])},
           "timing_boundaries": {"native": "MemoryBook.recall only, including exact optional-token budget work; validation/hash/ledger excluded",
               "mcp": "Official SDK call_tool round trip including server recall, normal cache write, serialization and transport; result-cache clear/validation excluded",
               "cache": "No query-result hits. SQLite/OS caches are not cleared; token-count memo warms naturally. No timed-call warmup or discarded sample.",
               "resource_cpu": "Native calling-process CPU per call; MCP calling-process CPU is CLIENT only. Server live snapshots separately include startup/calls/background process lifetime.",
               "api_import": "Import MemoryBook in a fresh worker after the common evaluator/bootstrap imports; this is not full CLI/process startup.",
               "probe": "An identical isolated non-corpus wrapper suite precedes measured database creation and may warm process code/import/regex/SQLite-library state. No measured database or tokenizer vocabulary is warmed.",
               "ingestion": "Complete fresh and unchanged session batches, with ordinary list append overhead inside the batch timer. Raw ordered responses and hashes are retained outside timing; four paired batches per cohort.",
               "tokens": "Reference cl100k_base vocabulary initialized in worker before token calls; each fresh MCP token server retains its natural first-call initialization cost."}}
    directory = args.output.resolve()
    if args.resume:
        require(read(directory / "run.json") == run, "Resume binding/source/host differs; preserve original run")
    else:
        directory.mkdir(parents=True, exist_ok=False)
        write(directory / "run.json", run, exclusive=True)
    for item in run["schedule"]:
        output = directory / (item["key"] + ".json.gz")
        intent = directory / (item["key"] + ".started.json")
        if output.exists():
            verify_worker(read(output), run, directory)
            continue
        require(not intent.exists(), "Incomplete worker already attempted; preserve it and do not silently repeat")
        write(intent, {"worker": item, "run_sha256": digest(run), "started_at": now()}, exclusive=True)
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
        with (directory / (item["key"] + ".log")).open("xb") as log:
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", item["key"],
                "--output", str(directory)], env=environment, stdout=log, stderr=subprocess.STDOUT)
        require(completed.returncode == 0, "Worker failed; immutable partial report/log retained: " + item["key"])
        verify_worker(read(output), run, directory)
        print(dump({"completed_worker": item["key"], "total_workers": len(run["schedule"])}), flush=True)
    result = audit(directory)
    write(directory / "summary.json", result)
    require(result["comparison"]["complete_output_and_archive_equivalence"], "Output/archive difference: inspect preserved evidence")
    print(dump({"output": str(directory), "paired_calls": result["paired_calls"], "equivalent": True}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--build-manifest", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--probe-label", choices=("baseline", "candidate"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    if args.probe_label:
        if args.plan is None or args.source is None:
            parser.error("--probe-label requires --plan and --source")
        specification = validate_plan(read(args.plan))
        sys.path.insert(0, str(args.source.resolve()))
        os.environ["MEMORY_BOOK_TEXT_BACKEND"] = "native"
        print(dump(active_backend(args.source, specification["native_helper_calls"][args.probe_label],
            specification["native_helper_effective_calls"][args.probe_label],
            specification["native_helper_fallback_calls"][args.probe_label])))
    elif args.audit:
        result = audit(args.audit.resolve())
        print(dump(result))
        if not result["comparison"]["complete_output_and_archive_equivalence"]:
            raise SystemExit(2)
    elif args.worker:
        worker(args.output.resolve(), args.worker)
    else:
        for name in ("plan", "baseline_src", "candidate_src", "build_manifest", "output"):
            if getattr(args, name) is None:
                parser.error("--" + name.replace("_", "-") + " is required")
        controller(args)


if __name__ == "__main__":
    main()
