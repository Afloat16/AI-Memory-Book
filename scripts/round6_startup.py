"""One prospective, independently audited 480-sample startup confirmation.

Only --host may measure, after exact Git/source/binding checks and a remote
exclusive claim. --bind writes a new binding after the evaluator is committed.
The fresh API helper imports only stdlib until its declared import boundary;
CLI samples invoke the real module directly. This never accepts recall gates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "v034-startup-confirmation-v1"
PLAN_COMMIT = "17bbd1feb767b92ccdba6c20565923a516ff6afc"
PLAN_PATH = "benchmarks/experiments/round6-startup-plan.json"
FILES = ("scripts/round6_startup.py", "scripts/round6_audit_startup.py",
         "tests/test_round6_startup_benchmark.py", "tests/test_round6_startup_audit.py",
         ".github/workflows/round6-startup.yml")
BOUNDARIES = ("cli-help", "cli-version", "api-import", "api-new", "api-existing", "mcp-initialize")
ORDERS = (("baseline", "candidate"), ("candidate", "baseline"),
          ("candidate", "baseline"), ("baseline", "candidate"))
METRICS = ("mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms")
PROCESS_RESOURCES = ("process.wall_ms", "process.user_cpu_s", "process.system_cpu_s", "process.max_rss_bytes")
API_RESOURCES = ("details.stats.database_bytes",)
MCP_RESOURCES = tuple("details.server_sample." + key for key in
                      ("rss_bytes", "hwm_bytes", "user_cpu_s", "system_cpu_s"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def write(path, value, *, exclusive=False):
    path = Path(path)
    raw = canonical(value) + b"\n"
    if str(path).endswith(".gz"):
        raw = gzip.compress(raw, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path if exclusive else path.with_name(path.name + ".tmp")
    with temporary.open("xb" if exclusive else "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if not exclusive:
        temporary.replace(path)


def git(*args, environment=None):
    completed = subprocess.run(["git", *args], cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    require(completed.returncode == 0, "Git operation failed; credential-bearing diagnostics omitted")
    return completed.stdout


def runtime_hash(source):
    root = Path(source) / "memory_book"
    paths = sorted(root.rglob("*.py"))
    require(bool(paths) and not any(path.is_symlink() for path in paths), "Missing/symbolic source package")
    hashed = hashlib.sha256()
    for path in paths:
        hashed.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return hashed.hexdigest()


def committed_runtime_hash(commit):
    prefix = "src/memory_book/"
    names = sorted(name for name in git("ls-tree", "-r", "--name-only", commit, prefix).decode().splitlines()
                   if name.endswith(".py"))
    require(bool(names), "Missing committed source")
    hashed = hashlib.sha256()
    for name in names:
        hashed.update(name[len(prefix):].encode() + b"\0" + git("show", commit + ":" + name) + b"\0")
    return hashed.hexdigest()


def evaluator_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in FILES}


def load_plan():
    raw = (ROOT / PLAN_PATH).read_bytes()
    require(raw == git("show", PLAN_COMMIT + ":" + PLAN_PATH), "Registered startup plan changed")
    plan = json.loads(raw)
    require(plan["protocol"] == PROTOCOL and plan["matrix"]["boundaries"] == list(BOUNDARIES)
            and plan["matrix"]["engine_order"] == [list(order) for order in ORDERS]
            and plan["matrix"]["total_samples"] == 480
            and plan["matrix"]["samples_per_engine_boundary_round"] == 10, "Registered matrix differs")
    return plan


def bind(path):
    plan = load_plan()
    commit = git("rev-parse", "HEAD").decode().strip()
    files = evaluator_hashes()
    for name, value in files.items():
        require(sha(git("show", commit + ":" + name)) == value, "Commit evaluator before binding: " + name)
    for source in plan["sources"].values():
        require(committed_runtime_hash(source["commit"]) == source["runtime_sha256"], "Frozen source Git bytes differ")
    value = {"schema_version": 1, "protocol": PROTOCOL, "status": "frozen-before-measurement", "created_at": now(),
             "plan": {"path": PLAN_PATH, "commit": PLAN_COMMIT, "sha256": sha((ROOT / PLAN_PATH).read_bytes())},
             "sources": plan["sources"], "measurement": plan["matrix"],
             "evaluator_commit": commit, "evaluator_files": files}
    path = Path(path).resolve()
    require(path.parent == ROOT / "benchmarks/experiments" and path.name.startswith("round6-startup-")
            and path.name.endswith("binding.json"), "Use a new startup binding path")
    write(path, value, exclusive=True)
    return {"binding": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes()), "evaluator_commit": commit}


def load_binding(path):
    plan, binding = load_plan(), read(path)
    require(binding["schema_version"] == 1 and binding["protocol"] == PROTOCOL
            and binding["status"] == "frozen-before-measurement"
            and binding["sources"] == plan["sources"] and binding["measurement"] == plan["matrix"]
            and binding["plan"] == {"path": PLAN_PATH, "commit": PLAN_COMMIT, "sha256": sha((ROOT / PLAN_PATH).read_bytes())}
            and binding["evaluator_files"] == evaluator_hashes(), "Frozen binding differs")
    name = Path(path).resolve().relative_to(ROOT).as_posix()
    require(Path(path).read_bytes() == git("show", "HEAD:" + name), "Commit exact binding before execution")
    for name, expected in binding["evaluator_files"].items():
        require(sha(git("show", binding["evaluator_commit"] + ":" + name)) == expected, "Evaluator commit differs")
    for source in binding["sources"].values():
        require(committed_runtime_hash(source["commit"]) == source["runtime_sha256"], "Committed source differs")
    return binding


def schedule():
    rows = []
    for round_number, order in enumerate(ORDERS):
        for boundary in BOUNDARIES:
            for engine in order:
                for repetition in range(10):
                    rows.append({"sequence": len(rows), "round": round_number, "boundary": boundary,
                                 "engine": engine, "repetition": repetition})
    return rows


def publication_identity(binding):
    run_id, attempt, commit = (os.environ.get(name, "") for name in
                               ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA"))
    require(os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/ci/v034-round6-startup"
            and run_id.isdigit() and attempt == "1" and re.fullmatch(r"[0-9a-f]{40}", commit)
            and git("rev-parse", "HEAD").decode().strip() == commit, "Only the exact first-attempt registered push may measure")
    require(git("remote", "get-url", "origin").decode().strip() in
            ("https://github.com/Afloat16/AI-Memory-Book", "https://github.com/Afloat16/AI-Memory-Book.git",
             "git@github.com:Afloat16/AI-Memory-Book.git"), "Unexpected checkpoint origin")
    key = digest({"protocol": PROTOCOL, "sources": {label: source["runtime_sha256"]
                                                   for label, source in binding["sources"].items()}})
    return {"run_id": run_id, "attempt": attempt, "workflow_commit": commit,
            "branch": "validation/v034-round6-startup-" + run_id + "-1",
            "claim_branch": "validation/v034-round6-startup-claim-" + key, "key": key}


class PublicationFailure(RuntimeError):
    pass


def publish(public, state, publication, phase, *, claim=False):
    failure = public / "publication-failure.json"
    require(not failure.exists(), "No retry after ambiguous publication")
    try:
        parent_path = state / "publication-parent.json"
        parent = read(parent_path)["commit"] if parent_path.exists() else publication["workflow_commit"]
        branch, claim_ref = ("refs/heads/" + publication[key] for key in ("branch", "claim_branch"))
        remote = git("ls-remote", "--heads", "origin", branch).decode().split()
        require((remote == [parent, branch]) if parent_path.exists() else not remote, "Result branch already exists or advanced")
        if claim:
            require(not git("ls-remote", "--heads", "origin", claim_ref).strip(), "Source-pair/protocol already claimed; no remeasurement")
        with tempfile.TemporaryDirectory(prefix="startup-index-") as temporary:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
            git("read-tree", parent, environment=env)
            git("add", "--sparse", "--", public.relative_to(ROOT).as_posix(), environment=env)
            tree = git("write-tree", environment=env).decode().strip()
            message = Path(temporary) / "message"
            message.write_text("bench: preserve startup " + phase + "\n")
            commit = git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                         "commit-tree", tree, "-p", parent, "-F", str(message), environment=env).decode().strip()
        if claim:
            git("push", "--force-with-lease=" + claim_ref + ":", "origin", commit + ":" + claim_ref)
        git("push", "origin", commit + ":" + branch)
        write(parent_path, {"commit": commit, "phase": phase, "at": now()})
    except BaseException as error:
        if not failure.exists():
            write(failure, {"status": "publication-failed-no-automatic-retry", "phase": phase,
                            "error_type": type(error).__name__, "at": now()}, exclusive=True)
        raise PublicationFailure("Checkpoint publication failed; no further timing or blind retry") from error


def prepare_sources(binding, state):
    paths = {}
    for label, source in binding["sources"].items():
        worktree = state / ("source-" + label)
        git("worktree", "add", "--no-checkout", "--detach", str(worktree), source["commit"])
        git("-C", str(worktree), "sparse-checkout", "set", "--cone", "src")
        git("-C", str(worktree), "read-tree", "-mu", "HEAD")
        paths[label] = str(worktree / "src")
    verify_sources(binding, paths)
    return paths


def verify_sources(binding, paths):
    observed = {}
    for label, source in binding["sources"].items():
        path = Path(paths[label])
        require(git("-C", str(path), "rev-parse", "HEAD").decode().strip() == source["commit"], "Source worktree commit differs")
        require(not git("-C", str(path.parent), "status", "--porcelain", "--untracked-files=all", "--", "src").strip(), "Source worktree changed")
        observed[label] = runtime_hash(path)
        require(observed[label] == source["runtime_sha256"], "Source runtime bytes differ")
    return observed


def database_snapshot(path):
    import sqlite3
    path = Path(path)
    if not path.exists():
        return None
    def value(item):
        return {"blob_hex": item.hex()} if isinstance(item, bytes) else item
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        schema = [list(row) for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
        tables = {}
        for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [row[1] for row in connection.execute("PRAGMA table_info(" + quoted + ")")]
            rows = [[value(item) for item in row] for row in connection.execute("SELECT * FROM " + quoted)]
            tables[name] = {"columns": columns, "rows": sorted(rows, key=canonical)}
        return {"schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
                "application_id": connection.execute("PRAGMA application_id").fetchone()[0],
                "quick_check": [row[0] for row in connection.execute("PRAGMA quick_check")],
                "schema": schema, "tables": tables}
    finally:
        connection.close()


def empty_archive(snapshot):
    return (isinstance(snapshot, dict) and snapshot.get("schema_version") == 3
            and snapshot.get("application_id") == 0x4D424F4B and snapshot.get("quick_check") == ["ok"]
            and snapshot["tables"].get("meta", {}).get("rows") == [["revision", "0"], ["stem_revision", "0"]]
            and all(snapshot["tables"].get(name, {}).get("rows") == [] for name in
                    ("projects", "chapters", "sessions", "turns", "sections", "pages", "recall_cache", "pages_fts", "pages_stem_fts")))


def normalized_initialize(value, version):
    result = json.loads(json.dumps(value))
    if result.get("serverInfo", {}).get("version") == version:
        result["serverInfo"]["version"] = "<declared-product-version>"
    return result


def server_sample(command):
    children = set()
    for task in Path("/proc/self/task").iterdir():
        try:
            children.update((task / "children").read_text().split())
        except FileNotFoundError:
            continue
    matches = []
    for pid in children:
        try:
            cmdline = [part.decode() for part in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if part]
            if cmdline == command:
                matches.append((pid, cmdline))
        except FileNotFoundError:
            continue
    require(len(matches) == 1, "Exactly one actual official-SDK server child must be visible")
    pid, cmdline = matches[0]
    status = Path(f"/proc/{pid}/status").read_text()
    values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in status.splitlines()
              if line.startswith(("VmRSS:", "VmHWM:"))}
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    ticks = os.sysconf("SC_CLK_TCK")
    return {"pid": int(pid), "cmdline": cmdline, "sampled_at_ns": time.perf_counter_ns(),
            "rss_bytes": values["VmRSS"], "hwm_bytes": values["VmHWM"],
            "user_cpu_s": int(fields[11]) / ticks, "system_cpu_s": int(fields[12]) / ticks,
            "scope": "Live server procfs snapshot immediately after initialize; RSS/HWM and CPU observed at this point, not whole-lifetime maxima/totals."}


async def mcp_child(db, version):
    # SDK imports and parameters are outside the registered initialize timer.
    from datetime import timedelta
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    command = [sys.executable, "-m", "memory_book", "--db", str(db), "mcp"]
    environment = {name: os.environ[name] for name in
                   ("PYTHONPATH", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "MEMORY_BOOK_HOME", "MEMORY_BOOK_DB")}
    parameters = StdioServerParameters(command=command[0], args=command[1:], env={**os.environ, **environment})
    before = database_snapshot(db)
    started = time.perf_counter_ns()
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as session:
            initialized = await session.initialize()
            finished = time.perf_counter_ns()
            sampled = server_sample(command)
            tools = await session.list_tools()
            initialization = initialized.model_dump(mode="json", by_alias=True, exclude_none=True)
            tool_result = tools.model_dump(mode="json", by_alias=True, exclude_none=True)
    after = database_snapshot(db)
    return {"timer": {"start_ns": started, "end_ns": finished, "elapsed_ms": (finished - started) / 1e6},
            "initialize_result": initialization, "tools_result": tool_result,
            "initialize_identity_sha256": digest(normalized_initialize(initialization, version)),
            "tools_sha256": digest(tool_result), "instructions_sha256": sha(initialization.get("instructions", "").encode()),
            "normalization": "Only initialize_result.serverInfo.version exactly equal to the declared source version becomes <declared-product-version>; no other changes.",
            "server_sample": sampled, "server_command": command, "server_environment": environment,
            "database_before": before, "database_after": after}


def child(mode, source, db, version):
    require(os.environ.get("PYTHONPATH") == str(source.resolve()), "Helper source environment differs")
    if mode == "mcp-initialize":
        import asyncio
        async def invoke():
            return await asyncio.wait_for(mcp_child(db, version), timeout=60)
        return asyncio.run(invoke())
    began = time.perf_counter_ns() if mode == "api-import" else None
    import memory_book
    from memory_book import MemoryBook
    import_finished = time.perf_counter_ns() if mode == "api-import" else None
    result = {"module_path": str(Path(memory_book.__file__).resolve()),
              "store_path": str(Path(sys.modules[MemoryBook.__module__].__file__).resolve()),
              "class_module": MemoryBook.__module__, "version": memory_book.__version__,
              "database_before": None, "database_after": None, "stats": None, "timer": None}
    require(Path(result["module_path"]).parent == source.resolve() / "memory_book"
            and result["store_path"] == str(source.resolve() / "memory_book/store.py")
            and result["class_module"] == "memory_book.store" and result["version"] == version, "Actual imported source differs")
    if mode == "api-import":
        result["timer"] = {"start_ns": began, "end_ns": import_finished, "elapsed_ms": (import_finished - began) / 1e6}
        return result
    before = database_snapshot(db)
    require((before is None) if mode in ("api-new", "fixture") else empty_archive(before), "Wrong constructor input")
    began = time.perf_counter_ns() if mode != "fixture" else None
    book = MemoryBook(db)
    finished = time.perf_counter_ns() if mode != "fixture" else None
    try:
        stats = book.stats()
    finally:
        book.close()
    result.update(database_before=before, database_after=database_snapshot(db), stats=stats)
    if mode != "fixture":
        result["timer"] = {"start_ns": began, "end_ns": finished, "elapsed_ms": (finished - began) / 1e6}
    return result


def process_environment(source, cwd, db):
    return {"PYTHONPATH": str(Path(source).resolve()), "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
            "MEMORY_BOOK_HOME": str(cwd / "isolated-home"), "MEMORY_BOOK_DB": str(db)}


def inventory(cwd):
    return sorted(path.relative_to(cwd).as_posix() + ("/" if path.is_dir() else "") for path in cwd.rglob("*"))


def measured_process(command, cwd, environment, output, *, timeout=90):
    """One wait4(pid) record; Popen.communicate/wait must not reap this child."""
    require(sys.platform == "linux" and hasattr(os, "wait4"), "Linux per-child wait4 required")
    before = inventory(cwd)
    timed_out = False
    process = None
    def alarm(_signum, _frame):
        raise TimeoutError("Sample process deadline exceeded")
    prior_handler = signal.signal(signal.SIGALRM, alarm)
    try:
        with (output / "stdout.txt").open("wb") as stdout, (output / "stderr.txt").open("wb") as stderr:
            signal.setitimer(signal.ITIMER_REAL, timeout)
            began = time.perf_counter_ns()
            process = subprocess.Popen(command, cwd=cwd, env={**os.environ, **environment}, stdout=stdout, stderr=stderr)
            try:
                pid, status, usage = os.wait4(process.pid, 0)
            except TimeoutError:
                timed_out = True
                process.kill()
                pid, status, usage = os.wait4(process.pid, 0)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            finished = time.perf_counter_ns()
            require(pid == process.pid, "wait4 returned another process")
            process.returncode = os.waitstatus_to_exitcode(status)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)
        if process is not None and process.returncode is None:
            process.kill()
            _, status, _ = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(status)
    return {"command": command, "cwd": str(cwd), "environment": environment, "returncode": process.returncode,
            "wall_start_ns": began, "wall_end_ns": finished, "wall_ms": (finished - began) / 1e6,
            "user_cpu_s": usage.ru_utime, "system_cpu_s": usage.ru_stime, "max_rss_bytes": usage.ru_maxrss * 1024,
            "rusage_scope": "Kernel wait4 usage for the actual child PID, with Linux ru_maxrss KiB converted to bytes; it may include descendants reaped by that child. MCP helper results are not isolated client-only usage; live server resources are separately sampled.",
            "pid": pid, "timed_out": timed_out,
            "stdout": (output / "stdout.txt").read_text(), "stderr": (output / "stderr.txt").read_text(),
            "cwd_before": before, "cwd_after": inventory(cwd)}


def helper_command(mode, source, db, version):
    return [sys.executable, str(ROOT / "scripts/round6_startup.py"), "--child", mode,
            "--source", str(source), "--database", str(db), "--version", version]


def prepare_fixture(state, sources, binding):
    directory = state / "fixture"
    directory.mkdir()
    db = directory / "book.db"
    environment = process_environment(sources["baseline"], directory, db)
    command = helper_command("fixture", sources["baseline"], db, binding["sources"]["baseline"]["version"])
    completed = subprocess.run(command, cwd=directory, env={**os.environ, **environment},
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    record = {"purpose": "One baseline-created closed empty archive; setup only, outside all 480 sample timers.",
              "command": command, "environment": environment, "returncode": completed.returncode,
              "stdout": completed.stdout.decode(), "stderr": completed.stderr.decode(), "database": str(db)}
    write(state / "fixture-attempt.json", record, exclusive=True)
    require(completed.returncode == 0 and not completed.stderr, "Baseline fixture setup failed")
    record["details"] = json.loads(completed.stdout)
    require(record["details"]["timer"] is None and empty_archive(record["details"]["database_after"]), "Invalid baseline fixture")
    record["database_sha256"] = sha(db.read_bytes())
    return record


def observe(item, state, run, fixture):
    directory = state / "samples" / f'{item["sequence"]:03d}'
    cwd = directory / "cwd"
    cwd.mkdir(parents=True)
    db = directory / "book.db"
    source = run["source_paths"][item["engine"]]
    version = run["binding"]["sources"][item["engine"]]["version"]
    if item["boundary"] in ("api-existing", "mcp-initialize"):
        shutil.copyfile(fixture["database"], db)
        require(sha(db.read_bytes()) == fixture["database_sha256"], "Existing archive copy differs")
    environment = process_environment(source, cwd, db)
    if item["boundary"].startswith("cli-"):
        command = [sys.executable, "-m", "memory_book", "--" + item["boundary"].split("-", 1)[1]]
    else:
        command = helper_command(item["boundary"], source, db, version)
    process = measured_process(command, cwd, environment, directory)
    details = None
    if not item["boundary"].startswith("cli-") and process["returncode"] == 0:
        try:
            details = json.loads(process["stdout"])
        except ValueError:
            pass
    primary = process["wall_ms"] if item["boundary"].startswith("cli-") else (details or {}).get("timer", {}).get("elapsed_ms")
    return {**item, "status": "completed", "primary_ms": primary, "process": process, "details": details,
            "database_exists_after": db.exists()}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_observation(row, run, fixture):
    process, boundary = row["process"], row["boundary"]
    source = run["source_paths"][row["engine"]]
    version = run["binding"]["sources"][row["engine"]]["version"]
    require(row["status"] == "completed" and process["returncode"] == 0 and not process["timed_out"], "Sample child failed")
    require(all(finite(process[key]) for key in ("wall_ms", "user_cpu_s", "system_cpu_s", "max_rss_bytes"))
            and process["max_rss_bytes"] > 0 and finite(row["primary_ms"]), "Invalid or missing time/resource sample")
    require(process["wall_end_ns"] >= process["wall_start_ns"]
            and process["wall_ms"] == (process["wall_end_ns"] - process["wall_start_ns"]) / 1e6, "Parent timer differs")
    require(process["environment"]["PYTHONPATH"] == source
            and process["environment"]["PYTHONHASHSEED"] == "0"
            and process["environment"]["PYTHONDONTWRITEBYTECODE"] == "1", "Child environment differs")
    if boundary.startswith("cli-"):
        require(process["command"] == [run["host"]["executable"], "-m", "memory_book", "--" + boundary.split("-", 1)[1]], "CLI was wrapped or changed")
        require(not process["stderr"] and process["cwd_before"] == process["cwd_after"] == []
                and not row["database_exists_after"] and row["primary_ms"] == process["wall_ms"], "CLI side effect/error or wrong timer")
        require(process["stdout"] == version + "\n" if boundary == "cli-version" else bool(process["stdout"]), "Unexpected CLI output")
        return
    details = row["details"]
    require(details == json.loads(process["stdout"]), "Helper output was changed")
    timer = details["timer"]
    require(process["wall_start_ns"] <= timer["start_ns"] <= timer["end_ns"] <= process["wall_end_ns"]
            and timer["elapsed_ms"] == (timer["end_ns"] - timer["start_ns"]) / 1e6
            and row["primary_ms"] == timer["elapsed_ms"], "Child timer bounds differ")
    db = Path(process["environment"]["MEMORY_BOOK_DB"])
    require(process["command"] == helper_command(boundary, source, db, version), "Helper command differs")
    if boundary.startswith("api-"):
        require(not process["stderr"] and details["module_path"] == str(Path(source) / "memory_book/__init__.py")
                and details["store_path"] == str(Path(source) / "memory_book/store.py")
                and details["class_module"] == "memory_book.store" and details["version"] == version, "API source/import/output differs")
        if boundary == "api-import":
            require(details["database_before"] is None and details["database_after"] is None
                    and not row["database_exists_after"], "Import created an archive")
        else:
            require(details["database_after"] == fixture["details"]["database_after"]
                    and empty_archive(details["database_after"]), "Constructed empty schema differs")
            require(details["database_before"] is None if boundary == "api-new" else
                    details["database_before"] == details["database_after"], "Wrong/modified existing archive")
            require(details["stats"]["schema_version"] == 3 and all(details["stats"][key] == 0 for key in
                    ("projects", "chapters", "sessions", "turns", "sections", "pages", "chars", "page_chars", "cache_entries", "revision")), "Archive not empty")
            require(type(details["stats"]["database_bytes"]) is int and details["stats"]["database_bytes"] > 0,
                    "Logical archive size is missing/invalid")
    else:
        require(details["database_before"] == details["database_after"] == fixture["details"]["database_after"], "MCP changed existing archive")
        require(details["tools_sha256"] == digest(details["tools_result"])
                and details["initialize_identity_sha256"] == digest(normalized_initialize(details["initialize_result"], version))
                and details["instructions_sha256"] == sha(details["initialize_result"].get("instructions", "").encode()), "MCP metadata identity differs")
        expected = [run["host"]["executable"], "-m", "memory_book", "--db", str(db), "mcp"]
        require(details["server_command"] == expected == details["server_sample"]["cmdline"]
                and details["server_environment"] == process["environment"], "MCP server provenance differs")
        sampled = details["server_sample"]
        require(all(finite(sampled[name]) for name in ("rss_bytes", "hwm_bytes", "user_cpu_s", "system_cpu_s"))
                and sampled["hwm_bytes"] >= sampled["rss_bytes"] > 0
                and timer["end_ns"] <= sampled["sampled_at_ns"] <= process["wall_end_ns"], "MCP resources missing/outside observed interval")


def validation(report):
    rows, errors = report["observations"], []
    expected = report["run"]["schedule"]
    if len(rows) != len(expected) or len(expected) != 480:
        errors.append("Incomplete original 480-sample matrix")
    for index, row in enumerate(rows):
        try:
            require(index < len(expected) and {key: row[key] for key in expected[index]} == expected[index], "Sample order/identity differs")
            validate_observation(row, report["run"], report["fixture"])
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append({"sequence": index, "type": type(error).__name__, "message": str(error)})
    help_outputs = {row["process"]["stdout"] for row in rows if row["boundary"] == "cli-help"}
    if len(help_outputs) != 1:
        errors.append("CLI help bytes differ")
    for field in ("initialize_identity_sha256", "tools_sha256", "instructions_sha256"):
        values = {row.get("details", {}).get(field) for row in rows
                  if row["boundary"] == "mcp-initialize" and isinstance(row.get("details"), dict)}
        if len(values) != 1 or None in values:
            errors.append("MCP identity differs: " + field)
    if not report.get("integrity_after", {}).get("passed", False):
        errors.append("Final evaluator/source integrity is not verified")
    return {"passed": not errors, "expected_samples": 480, "completed_samples": len(rows), "errors": errors}


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def stats(values):
    require(bool(values) and all(finite(value) for value in values), "Invalid statistics input")
    return {"samples": len(values), "mean_ms": statistics.mean(values), "median_ms": statistics.median(values),
            "p95_ms": percentile(values, .95), "min_ms": min(values), "max_ms": max(values)}


def percent(baseline, candidate):
    return 100 * (candidate - baseline) / baseline if baseline else (0.0 if candidate == 0 else None)


def compare(left, right):
    baseline, candidate = stats(left), stats(right)
    return {"baseline": baseline, "candidate": candidate,
            "change_percent": {key: percent(baseline[key], candidate[key]) for key in METRICS},
            "absolute_change_ms": {key: candidate[key] - baseline[key] for key in METRICS}}


def nested(row, path):
    for key in path.split("."):
        row = row[key]
    return row


def resource_pair(rows, path):
    left, right = (statistics.mean(nested(row, path) for row in rows if row["engine"] == label)
                   for label in ("baseline", "candidate"))
    return {"baseline_mean": left, "candidate_mean": right, "change_percent": percent(left, right), "absolute_change": right - left}


def comparisons(rows):
    result = []
    for boundary in BOUNDARIES:
        selected = [row for row in rows if row["boundary"] == boundary]
        if len(selected) != 80 or any(not finite(row.get("primary_ms")) for row in selected):
            continue
        pooled = compare(*([row["primary_ms"] for row in selected if row["engine"] == label]
                           for label in ("baseline", "candidate")))
        rounds = [{"round": number, **compare(*([row["primary_ms"] for row in selected
                   if row["round"] == number and row["engine"] == label] for label in ("baseline", "candidate")))} for number in range(4)]
        resources = {}
        paths = PROCESS_RESOURCES + (MCP_RESOURCES if boundary == "mcp-initialize" else ())
        paths += API_RESOURCES if boundary in ("api-new", "api-existing") else ()
        for path in paths:
            resources[path] = {**resource_pair(selected, path), "rounds": [
                {"round": number, **resource_pair([row for row in selected if row["round"] == number], path)} for number in range(4)]}
        result.append({"boundary": boundary, "pooled": pooled, "rounds": rounds, "resources": resources})
    return result


def evaluate(compared, valid, plan):
    primary, secondary, review = [], [], []
    by_boundary = {row["boundary"]: row for row in compared}
    for target in plan["acceptance"]["primary_targets"]:
        if target["boundary"] not in by_boundary:
            continue
        pooled = by_boundary[target["boundary"]]["pooled"]
        median = pooled["change_percent"]["median_ms"]
        p95 = pooled["change_percent"]["p95_ms"]
        absolute = -pooled["absolute_change_ms"]["median_ms"]
        passed = median is not None and p95 is not None and pooled["baseline"]["median_ms"] > 0 and pooled["baseline"]["p95_ms"] > 0
        passed = (passed and pooled["candidate"]["median_ms"] <= pooled["baseline"]["median_ms"] * (1 - target["median_minimum_improvement_percent"] / 100)
                  and pooled["candidate"]["p95_ms"] <= pooled["baseline"]["p95_ms"] * (1 - target["p95_minimum_improvement_percent"] / 100)
                  and absolute >= target["median_minimum_absolute_reduction_ms"])
        primary.append({"boundary": target["boundary"], "median_improvement_percent": -median if median is not None else None,
                        "p95_improvement_percent": -p95 if p95 is not None else None, "median_absolute_reduction_ms": absolute, "passed": bool(passed)})
    for boundary in plan["acceptance"]["secondary_regression_guards"]["boundaries"]:
        if boundary not in by_boundary:
            continue
        pooled = by_boundary[boundary]["pooled"]
        for metric in ("median_ms", "p95_ms"):
            absolute = pooled["absolute_change_ms"][metric]
            passed = not (pooled["candidate"][metric] > 1.1 * pooled["baseline"][metric] and absolute > 1)
            secondary.append({"boundary": boundary, "metric": metric, "change_percent": pooled["change_percent"][metric], "absolute_change_ms": absolute, "passed": passed})
    for item in compared:
        for metric, values in item["resources"].items():
            if values["candidate_mean"] > 1.1 * values["baseline_mean"]:
                review.append({"boundary": item["boundary"], "metric": metric,
                               **{key: value for key, value in values.items() if key != "rounds"}})
    numeric = valid and len(primary) == 3 and len(secondary) == 6 and all(row["passed"] for row in primary + secondary)
    return {"numeric_gate_passed": bool(numeric), "primary_targets": primary, "secondary_guards": secondary,
            "resource_review": review, "original_recall_gates_unpassed": True, "accepted": bool(numeric and not review)}


def adverse(compared):
    result = {"pooled": [], "rounds": [], "resources": [], "resource_rounds": []}
    for item in compared:
        for name, records in (("pooled", [item["pooled"]]), ("rounds", item["rounds"])):
            for record in records:
                for metric in METRICS:
                    if record["absolute_change_ms"][metric] > 0:
                        result[name].append({"boundary": item["boundary"], **({"round": record["round"]} if "round" in record else {}),
                            "metric": metric, "change_percent": record["change_percent"][metric], "absolute_change_ms": record["absolute_change_ms"][metric]})
        for metric, values in item["resources"].items():
            for name, records in (("resources", [values]), ("resource_rounds", values["rounds"])):
                for record in records:
                    if record["absolute_change"] > 0:
                        result[name].append({"boundary": item["boundary"], "metric": metric,
                            **{key: value for key, value in record.items() if key != "rounds"}})
    return result


def ledger_event(handle, value):
    handle.write(canonical(value) + b"\n")
    handle.flush()
    os.fsync(handle.fileno())


def checkpoint(report, public, ledger_path, plan):
    report["validation"] = validation(report)
    try:
        report["comparisons"] = comparisons(report["observations"])
        report["acceptance"] = evaluate(report["comparisons"], report["validation"]["passed"], plan)
        report["adverse_observations"] = adverse(report["comparisons"])
    except (ValueError, KeyError, TypeError, statistics.StatisticsError) as error:
        report["statistics_error"] = {"type": type(error).__name__, "message": str(error)}
        report["acceptance"] = {"accepted": False, "numeric_gate_passed": False, "original_recall_gates_unpassed": True}
    if ledger_path.exists():
        raw = ledger_path.read_bytes()
        report["ledger_sha256"] = sha(raw)
        compressed = public / "attempts.jsonl.gz"
        temporary = compressed.with_name(compressed.name + ".tmp")
        temporary.write_bytes(gzip.compress(raw, mtime=0))
        temporary.replace(compressed)
    write(public / "report.json.gz", report)


def host(binding_path):
    raw_binding = read(binding_path)
    # Fetch only exact provenance objects; never fetch the historical report tree.
    for commit in sorted({PLAN_COMMIT, raw_binding["evaluator_commit"], *(v["commit"] for v in raw_binding["sources"].values())}):
        require(re.fullmatch(r"[0-9a-f]{40}", commit), "Invalid frozen Git identity")
        git("fetch", "--no-tags", "--depth", "1", "--filter=blob:none", "origin", commit)
    binding, plan = load_binding(binding_path), load_plan()
    publication = publication_identity(binding)
    suffix = "round6-startup-" + publication["run_id"] + "-1"
    public, state = ROOT / "benchmarks/reports" / suffix, ROOT / ".artifacts" / suffix
    require(not public.exists() and not state.exists(), "Preserve existing startup attempt; no retry")
    public.mkdir(parents=True)
    state.mkdir(parents=True)
    report = {"schema_version": 1, "protocol": PROTOCOL, "status": "preparing", "started_at": now(), "observations": [],
              "scope": "Independent prospective startup confirmation only; original recall 10/15/10 remains unaccepted and formal unrun."}
    ledger_path = state / "attempts.jsonl"
    code, audit_code, error = 1, None, None
    try:
        require(sys.platform == "linux" and sys.version_info[:2] == (3, 12) and hasattr(os, "wait4"), "Registered Linux/Python environment differs")
        os_release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
        require(os_release.get("ID", "").strip('"') == "ubuntu" and os_release.get("VERSION_ID", "").strip('"') == "24.04", "Registered Ubuntu version differs")
        packages = {name: importlib.metadata.version(name) for name in ("mcp", "pydantic")}
        require(packages == {"mcp": "1.30.0", "pydantic": "2.14.3"}
                and os.environ.get("PYTHONHASHSEED") == "0" and os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "Package/environment pins differ")
        paths = prepare_sources(binding, state)
        host_info = {"platform": platform.platform(), "python": sys.version, "executable": sys.executable,
                     "packages": packages, "os_release": os_release, "cpu_count": os.cpu_count(),
                     "boot_sha256": sha(Path("/proc/sys/kernel/random/boot_id").read_bytes()),
                     "cpu_model": next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), None)}
        run = {"binding": binding, "binding_file": {"path": binding_path.relative_to(ROOT).as_posix(), "sha256": sha(binding_path.read_bytes())},
               "publication": publication, "source_paths": paths, "host": host_info, "schedule": schedule()}
        report["run"] = run
        write(public / "run.json", run, exclusive=True)
        (public / "binding.json").write_bytes(binding_path.read_bytes())
        write(public / "execution.json", {"protocol": PROTOCOL, "key": publication["key"], "run_sha256": digest(run), "created_at": now()}, exclusive=True)
        publish(public, state, publication, "execution claimed", claim=True)
        fixture = prepare_fixture(state, paths, binding)
        report["fixture"] = fixture
        write(public / "fixture.json", fixture, exclusive=True)
        report["status"] = "running"
        with ledger_path.open("xb") as ledger:
            for offset in range(0, 480, 20):
                batch = run["schedule"][offset:offset + 20]
                label = f'round {batch[0]["round"]} {batch[0]["boundary"]}'
                report["checkpoint"] = {"phase": "before", "round": batch[0]["round"], "boundary": batch[0]["boundary"], "at": now()}
                checkpoint(report, public, ledger_path, plan)
                publish(public, state, publication, "before " + label)
                for item in batch:
                    ledger_event(ledger, {"event": "started", **item, "at": now()})
                    row = observe(item, state, run, fixture)
                    report["observations"].append(row)
                    ledger_event(ledger, {"event": "finished", **item, "observation_sha256": digest(row), "at": now()})
                    validate_observation(row, run, fixture)
                report["checkpoint"]["phase"] = "after"
                checkpoint(report, public, ledger_path, plan)
                publish(public, state, publication, "after " + label)
                print(json.dumps({"completed_samples": len(report["observations"]), "boundary": label}), flush=True)
        source_after = verify_sources(binding, paths)
        require(load_binding(binding_path) == binding, "Binding changed during measurement")
        report["integrity_after"] = {"passed": True, "sources": source_after, "evaluator_files": evaluator_hashes(),
                                     "plan_sha256": sha((ROOT / PLAN_PATH).read_bytes()), "binding_sha256": sha(binding_path.read_bytes())}
        report["status"] = "measurements_completed"
        checkpoint(report, public, ledger_path, plan)
        code = 0 if report["validation"]["passed"] else 1
    except BaseException as exception:
        error = {"type": type(exception).__name__, "message": str(exception)}
        report.update(status="error", error=error)
    finally:
        report["finished_at"] = now()
        # If an interrupted/failed observer could not serialize its process
        # record, preserve its original captured bytes alongside the ledger.
        completed_sequences = {row["sequence"] for row in report["observations"]}
        for path in sorted((state / "samples").glob("*/*.txt")):
            if int(path.parent.name) not in completed_sequences:
                target = public / "unfinished-samples" / path.parent.name / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        if "run" in report:
            checkpoint(report, public, ledger_path, plan)
        else:
            write(public / "report.json.gz", report)
        if (state / "fixture-attempt.json").exists() and not (public / "fixture.json").exists():
            shutil.copyfile(state / "fixture-attempt.json", public / "fixture-failure.json")
        if (public / "attempts.jsonl.gz").exists():
            audit_code = subprocess.run([sys.executable, str(ROOT / "scripts/round6_audit_startup.py"),
                "--report", str(public / "report.json.gz"), "--ledger", str(public / "attempts.jsonl.gz"),
                "--binding", str(public / "binding.json"), "--output", str(public / "independent-audit.json")], cwd=ROOT).returncode
        write(public / "completion.json", {"schema_version": 1, "protocol": PROTOCOL, "created_at": now(),
            "measurement_returncode": code, "audit_returncode": audit_code, "error": error,
            "validation": report.get("validation"), "acceptance": report.get("acceptance"),
            "files_sha256": {path.relative_to(public).as_posix(): sha(path.read_bytes()) for path in sorted(public.rglob("*")) if path.is_file()}}, exclusive=True)
        if (state / "publication-parent.json").exists() and not (public / "publication-failure.json").exists():
            try:
                publish(public, state, publication, "completion and independent audit")
            except PublicationFailure as exception:
                error = {"type": type(exception).__name__, "message": str(exception)}
        print(json.dumps({"report": str(public / "report.json.gz"), "measurement_returncode": code,
                          "audit_returncode": audit_code, "error": error, "acceptance": report.get("acceptance")}), flush=True)
    return 0 if code == 0 and audit_code == 0 and error is None and report.get("acceptance", {}).get("accepted") else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=Path)
    parser.add_argument("--binding", type=Path, default=ROOT / "benchmarks/experiments/round6-startup-binding.json")
    parser.add_argument("--host", action="store_true")
    parser.add_argument("--child", choices=("fixture", "api-import", "api-new", "api-existing", "mcp-initialize"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    require(sum((bool(args.bind), args.host, bool(args.child))) == 1, "Choose one explicit mode")
    if args.bind:
        print(json.dumps(bind(args.bind)))
        return 0
    if args.child:
        require(args.source and args.database and args.version, "Explicit child provenance required")
        print(canonical(child(args.child, args.source, args.database, args.version)).decode(), flush=True)
        return 0
    return host(args.binding.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
