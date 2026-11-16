"""Frozen incremental native-vs-native performance comparison after v0.8.0.

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

PROTOCOL = "native-language-performance-2"
BASELINE = "6a8a9c6d603a812c75def258b11eb563ed590c9b"
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
EVALUATOR_FILES = ("scripts/native_incremental_performance.py", "benchmarks/__init__.py",
                   "benchmarks/data.py", "benchmarks/public_data.py", "benchmarks/run.py",
                   "benchmarks/locomo_split.json", "tests/test_native_incremental_performance.py",
                   "scripts/native_incremental_host.py", "scripts/native_incremental_preserve.py",
                   ".github/workflows/native-incremental-performance.yml")
BUILD_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in", "Cargo.toml", "Cargo.lock")
SOURCE_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")
HOST_COLUMNS = {"projects": {"created_at", "updated_at"},
                "chapters": {"updated_at"}, "sessions": {"updated_at"}}
ROW_STABLE = ("query_id", "payload_sha256", "native_payload_sha256", "context_sha256",
              "envelope_sha256", "context_chars", "context_tokens", "result_count", "invariants")
INVARIANT_KEYS = {"scope", "source_spans", "page_projection", "context_reconstruction", "metadata",
                  "character_budget", "result_limit", "token_budget", "token_metadata"}
NATIVE_HELPERS = ("terms_ascii", "ascii_tokens", "unicode_tokens", "fold_excerpt_source", "evidence_units")
CANDIDATE_HELPERS = (*NATIVE_HELPERS, "identifier_aliases", "literal_positions")
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
    require(plan.get("schema_version") == 2 and plan.get("protocol") == PROTOCOL, "Unknown incremental plan protocol")
    require(set(plan["sources"]) == {"baseline", "candidate"}, "Unexpected source label")
    require(plan["sources"]["baseline"] == {"commit": BASELINE, "backend": "native"},
            "Baseline must be the released native v0.8.0 commit")
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
    probes = plan.get("native_helper_calls", {})
    require(set(probes) == set(PROBE_HELPERS), "Freeze both native helper inventories")
    for label, helpers in PROBE_HELPERS.items():
        require(set(probes[label]) == set(helpers)
                and all(type(count) is int and count > 0 for count in probes[label].values()),
                "Every native helper needs a positive pre-timing dispatch count: " + label)
    calls = 2 * 4 * 3 * len(CONFIGS) * sum(COHORTS[name]["queries"] for name in COHORTS)
    require(plan.get("expected_timed_calls") == calls and plan.get("expected_paired_calls") == calls // 2,
            "Declared matrix counts differ from all registered attempts")
    return plan


def validate_build_manifest(build, sources):
    require(build.get("schema_version") == 2 and build.get("status") == "completed"
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
    require(sources["baseline"]["source_files"].get("setup.py")
            == sources["candidate"]["source_files"].get("setup.py"), "Native build definition changed between sources")
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


def dispatch_probe(text, native, expected_hits):
    """Prove every bound helper dispatches, before ingestion and query timing.

    Both native sources run identical public-wrapper calls. Their helper sets
    differ because the candidate replaces two more Python loops. Exact counts
    and output hashes are frozen; instrumentation is always removed.
    """
    hits = dict.fromkeys(expected_hits, 0)
    original = getattr(text, "_NATIVE", None)
    require(original is native, "Text wrappers do not target the bound native module")
    available = sorted(name for name in dir(native) if not name.startswith("_"))
    require(available == sorted(expected_hits), "Native helper inventory differs from the frozen probe")
    class Probe:
        def __getattr__(self, name):
            function = getattr(native, name)
            def invoke(*args, **kwargs):
                hits[name] += 1
                return function(*args, **kwargs)
            return invoke
    text._NATIVE = Probe()
    try:
        outputs = [text.terms("HTTPParser requestTimeout", query=True),
                   text.terms("café déjà", query=True),
                   text.terms("为什么内存隔离必须安全？", query=True),
                   text._fold_excerpt_source("Straße cafe\u0301 Å🙂"),
                   text._evidence_units("First sentence. Second clause！\n短句", 8),
                   text.identifier_terms("HTTPParser parseHTTPResponse xml_http_request", query=True),
                   text.identifier_terms("HTTPParser parseHTTPResponse xml_http_request", query=False),
                   text.excerpt("prefix " * 20 + "café HTTPParser suffix " * 20,
                                "cafe parser", 32, prepared_terms=["cafe", "parser"])]
    finally:
        text._NATIVE = original
    require(hits == expected_hits, "Native helper dispatch counts differ from the frozen probe")
    require(text._NATIVE is native, "Probe instrumentation was not restored")
    return {"native_helper_calls": hits, "outputs_sha256": digest(outputs), "instrumentation_restored": True,
            "scope": "Same eight fixed non-corpus public calls in both native runtimes, before ingestion/query timers; identity evidence only."}


def active_backend(source, expected_hits):
    import memory_book
    from memory_book import text, _text_backend
    require(Path(memory_book.__file__).resolve().parent == Path(source).resolve() / "memory_book", "Wrong runtime imported")
    require(_text_backend.BACKEND_NAME == "native" and _text_backend.REQUESTED_BACKEND == "native"
            and _text_backend.NATIVE is not None, "A native source silently fell back to Python")
    native = Path(_text_backend.NATIVE.__file__).resolve()
    require(native.parent == Path(source).resolve() / "memory_book", "Loaded native binary outside bound runtime")
    return {"requested": "native", "actual": "native", "binary_sha256": sha(native.read_bytes()),
            "available_functions": sorted(name for name in dir(_text_backend.NATIVE) if not name.startswith("_")),
            "dispatch_probe": dispatch_probe(text, _text_backend.NATIVE, expected_hits)}


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
    backend = active_backend(source, run["plan"]["native_helper_calls"][item["label"]])
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
                started = time.perf_counter_ns()
                ingested = [book.ingest(session) for session in data.sessions]
                report["resources"]["fresh_ingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["ingestion_sha256"] = digest(ingested)
                report["resources"]["after_ingestion"] = usage()
                report["resources"]["storage_after_ingestion"] = storage(book.db, db)
                started = time.perf_counter_ns()
                replayed = [book.ingest(session) for session in data.sessions]
                report["resources"]["unchanged_reingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
                report["unchanged_reingestion_sha256"] = digest(replayed)
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
            for field in ("archive_before", "archive_after", "ingestion_sha256", "unchanged_reingestion_sha256"):
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


def audit(directory):
    run = read(directory / "run.json")
    validate_plan(run["plan"])
    require(run["protocol"] == PROTOCOL, "Run protocol differs")
    require(all({key: run["sources"][label][key] for key in ("commit", "backend")} == spec
                for label, spec in run["plan"]["sources"].items()), "Run source identities differ from the frozen plan")
    validate_build_manifest(run["build_manifest"], run["sources"])
    require(run["build_manifest"]["workflow_commit"] == run["evaluator_commit"], "Build/evaluator commits differ")
    require(run["build_manifest"].get("host_preparation_sha256") == run["evaluator"]["scripts/native_incremental_host.py"],
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
            "comparison": compared,
            "worker_resources": [{"key": w["key"], "runtime_import_ms": w["runtime_import_ms"],
                                  "resources": w["resources"], "configuration_resources": {
                                      c["id"]: c["resources"] for c in w["configurations"]}} for w in reports]}


def controller(args):
    require(sys.platform == "linux", "This registered resource protocol requires Linux procfs")
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/validation/native-incremental-formal-1"
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
    require(build.get("host_preparation_sha256") == evaluator["scripts/native_incremental_host.py"],
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
           "cohorts": {name: value.description() for name, value in data.items()}, "schedule": schedule(plan),
           "query_order_sha256": {f"r{round_}-{name}-{config_id}": digest(query_order([case.id for case in value.queries], round_, index))
               for name, value in data.items() for round_ in range(4) for index, config_id in enumerate(plan["configurations"])},
           "timing_boundaries": {"native": "MemoryBook.recall only, including exact optional-token budget work; validation/hash/ledger excluded",
               "mcp": "Official SDK call_tool round trip including server recall, normal cache write, serialization and transport; result-cache clear/validation excluded",
               "cache": "No query-result hits. SQLite/OS caches are not cleared; token-count memo warms naturally. No timed-call warmup or discarded sample.",
               "resource_cpu": "Native calling-process CPU per call; MCP calling-process CPU is CLIENT only. Server live snapshots separately include startup/calls/background process lifetime.",
               "api_import": "Import MemoryBook in a fresh worker after the common evaluator/bootstrap imports; this is not full CLI/process startup.",
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
        print(dump(active_backend(args.source, specification["native_helper_calls"][args.probe_label])))
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
