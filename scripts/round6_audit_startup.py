"""Independent stdlib audit of saved startup observations; never benchmarks.

All numeric results are derived here from the original 480 observations and
960 intent/completion events. The product and measurement runner are never
imported, and no measured command, server or timer is run by this auditor.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "v034-startup-confirmation-v1"
PLAN_PATH = "benchmarks/experiments/round6-startup-plan.json"
PLAN_COMMIT = "17bbd1feb767b92ccdba6c20565923a516ff6afc"
EVALUATORS = ("scripts/round6_startup.py", "scripts/round6_audit_startup.py",
              "tests/test_round6_startup_benchmark.py", "tests/test_round6_startup_audit.py",
              ".github/workflows/round6-startup.yml")
BOUNDARIES = ("cli-help", "cli-version", "api-import", "api-new", "api-existing", "mcp-initialize")
ORDERS = (("baseline", "candidate"), ("candidate", "baseline"),
          ("candidate", "baseline"), ("baseline", "candidate"))
METRICS = ("mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms")
PROCESS_RESOURCES = ("process.wall_ms", "process.user_cpu_s", "process.system_cpu_s", "process.max_rss_bytes")
API_RESOURCES = ("details.stats.database_bytes",)
MCP_RESOURCES = tuple("details.server_sample." + name
                      for name in ("rss_bytes", "hwm_bytes", "user_cpu_s", "system_cpu_s"))
EMPTY_TABLES = {"meta", "projects", "chapters", "sessions", "turns", "sections", "pages", "recall_cache",
                "pages_fts", "pages_stem_fts", *(table + suffix for table in ("pages_fts", "pages_stem_fts")
                for suffix in ("_data", "_idx", "_content", "_docsize", "_config"))}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def valid_hash(value, length=64):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None


def number(value, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def exact_number(actual, expected, label):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9), label + " differs")


def compare(actual, expected, label="value"):
    if isinstance(expected, dict):
        require(type(actual) is dict and set(actual) == set(expected), label + ": fields differ")
        for key in expected:
            compare(actual[key], expected[key], label + "." + key)
    elif isinstance(expected, list):
        require(type(actual) is list and len(actual) == len(expected), label + ": length differs")
        for index, (left, right) in enumerate(zip(actual, expected)):
            compare(left, right, label + f"[{index}]")
    elif isinstance(expected, float):
        exact_number(actual, expected, label)
    else:
        require(type(actual) is type(expected) and actual == expected, label + ": value differs")


def nested(value, path):
    for key in path.split("."):
        value = value[key]
    return value


def schedule():
    rows = []
    for round_id, order in enumerate(ORDERS):
        for boundary in BOUNDARIES:
            for engine in order:
                for repetition in range(10):
                    rows.append({"sequence": len(rows), "round": round_id, "boundary": boundary,
                                 "engine": engine, "repetition": repetition})
    return rows


def quantile(values, proportion):
    ordered = sorted(values)
    require(bool(ordered), "Empty population")
    position = (len(ordered) - 1) * proportion
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def mean(values):
    require(bool(values), "Empty mean population")
    return math.fsum(values) / len(values)


def statistics(values):
    require(all(number(value) for value in values), "Invalid numeric population")
    return {"samples": len(values), "mean_ms": mean(values), "median_ms": quantile(values, .5),
            "p95_ms": quantile(values, .95), "min_ms": min(values), "max_ms": max(values)}


def percent(baseline, candidate):
    return (100 * (candidate / baseline - 1) if baseline else 0.0 if not candidate else None)


def pair(baseline, candidate):
    left, right = statistics(baseline), statistics(candidate)
    return {"baseline": left, "candidate": right,
            "change_percent": {key: percent(left[key], right[key]) for key in METRICS},
            "absolute_change_ms": {key: right[key] - left[key] for key in METRICS}}


def resource_pair(baseline, candidate):
    left, right = mean(baseline), mean(candidate)
    return {"baseline_mean": left, "candidate_mean": right,
            "change_percent": percent(left, right), "absolute_change": right - left}


def recompute_comparisons(observations):
    result = []
    for boundary in BOUNDARIES:
        by_engine = {engine: [row for row in observations if row["boundary"] == boundary
                             and row["engine"] == engine] for engine in ("baseline", "candidate")}
        require(all(len(rows) == 40 for rows in by_engine.values()), "Incomplete pooled population")
        rounds = []
        for round_id in range(4):
            rounds.append({"round": round_id, **pair(
                [row["primary_ms"] for row in by_engine["baseline"] if row["round"] == round_id],
                [row["primary_ms"] for row in by_engine["candidate"] if row["round"] == round_id])})
        resources = {}
        paths = PROCESS_RESOURCES + (MCP_RESOURCES if boundary == "mcp-initialize" else
                                    API_RESOURCES if boundary in ("api-new", "api-existing") else ())
        for path in paths:
            pooled = resource_pair(*[[nested(row, path) for row in by_engine[engine]]
                                     for engine in ("baseline", "candidate")])
            pooled["rounds"] = [{"round": round_id, **resource_pair(*[
                [nested(row, path) for row in by_engine[engine] if row["round"] == round_id]
                for engine in ("baseline", "candidate")])} for round_id in range(4)]
            resources[path] = pooled
        result.append({"boundary": boundary, "pooled": pair(*[
            [row["primary_ms"] for row in by_engine[engine]] for engine in ("baseline", "candidate")]),
            "rounds": rounds, "resources": resources})
    return result


def recompute_acceptance(comparisons, plan, validation_passed=True):
    by_boundary = {row["boundary"]: row for row in comparisons}
    primary = []
    for target in plan["acceptance"]["primary_targets"]:
        row = by_boundary[target["boundary"]]["pooled"]
        improvements = {key: -row["change_percent"][key]
                        if row["change_percent"][key] is not None else None
                        for key in ("median_ms", "p95_ms")}
        absolute = -row["absolute_change_ms"]["median_ms"]
        passed = (row["baseline"]["median_ms"] > 0 and row["baseline"]["p95_ms"] > 0
            and row["candidate"]["median_ms"] <= row["baseline"]["median_ms"] *
                (1 - target["median_minimum_improvement_percent"] / 100)
            and row["candidate"]["p95_ms"] <= row["baseline"]["p95_ms"] *
                (1 - target["p95_minimum_improvement_percent"] / 100)
            and absolute >= target["median_minimum_absolute_reduction_ms"])
        primary.append({"boundary": target["boundary"],
            "median_improvement_percent": improvements["median_ms"],
            "p95_improvement_percent": improvements["p95_ms"],
            "median_absolute_reduction_ms": absolute, "passed": passed})
    secondary = []
    for boundary in plan["acceptance"]["secondary_regression_guards"]["boundaries"]:
        row = by_boundary[boundary]["pooled"]
        for metric in ("median_ms", "p95_ms"):
            secondary.append({"boundary": boundary, "metric": metric,
                "change_percent": row["change_percent"][metric],
                "absolute_change_ms": row["absolute_change_ms"][metric],
                "passed": not (row["candidate"][metric] > 1.1 * row["baseline"][metric]
                               and row["absolute_change_ms"][metric] > 1)})
    reviews = []
    for row in comparisons:
        for metric, value in row["resources"].items():
            if value["candidate_mean"] > 1.1 * value["baseline_mean"]:
                reviews.append({"boundary": row["boundary"], "metric": metric,
                                **{key: val for key, val in value.items() if key != "rounds"}})
    numeric = all(row["passed"] for row in primary + secondary)
    return {"numeric_gate_passed": numeric, "primary_targets": primary, "secondary_guards": secondary,
            "resource_review": reviews, "original_recall_gates_unpassed": True,
            "accepted": validation_passed and numeric and not reviews}


def recompute_adverse(comparisons):
    result = {"pooled": [], "rounds": [], "resources": [], "resource_rounds": []}
    for row in comparisons:
        for kind, groups in (("pooled", [row["pooled"]]), ("rounds", row["rounds"])):
            for group in groups:
                for metric in METRICS:
                    if group["candidate"][metric] > group["baseline"][metric]:
                        result[kind].append({"boundary": row["boundary"],
                            **({"round": group["round"]} if kind == "rounds" else {}),
                            "metric": metric, "change_percent": group["change_percent"][metric],
                            "absolute_change_ms": group["absolute_change_ms"][metric]})
        for metric, value in row["resources"].items():
            for kind, groups in (("resources", [value]), ("resource_rounds", value["rounds"])):
                for group in groups:
                    if group["candidate_mean"] > group["baseline_mean"]:
                        result[kind].append({"boundary": row["boundary"],
                            **({"round": group["round"]} if kind == "resource_rounds" else {}),
                            "metric": metric, **{key: val for key, val in group.items()
                                                  if key not in ("round", "rounds")}})
    return result


def json_value(raw):
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value, "Duplicate JSON key")
            value[key] = item
        return value
    def nonfinite(value):
        raise ValueError("Non-finite JSON constant: " + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def read_raw(path):
    raw = Path(path).read_bytes()
    return gzip.decompress(raw) if str(path).endswith(".gz") else raw


def absolute(value):
    return (type(value) is str and PurePosixPath(value).is_absolute()
            and ".." not in PurePosixPath(value).parts and "\x00" not in value)


def verify_empty(snapshot):
    require(type(snapshot) is dict and snapshot["schema_version"] == 3
            and snapshot["application_id"] == 0x4D424F4B and snapshot["quick_check"] == ["ok"],
            "Archive application/schema/integrity differs")
    schema, tables = snapshot["schema"], snapshot["tables"]
    require(type(schema) is list and bool(schema) and type(tables) is dict, "Missing complete archive state")
    require(all(type(row) is list and len(row) == 4 and all(type(v) is str for v in row[:3])
                and (row[3] is None or type(row[3]) is str) for row in schema), "Invalid schema rows")
    require(schema == sorted(schema, key=lambda row: (row[0], row[1]))
            and len({row[1] for row in schema}) == len(schema), "Duplicate or reordered schema objects")
    require(set(tables) == EMPTY_TABLES == {row[1] for row in schema if row[0] == "table"}, "Omitted table snapshot")
    for name, table in tables.items():
        require(set(table) == {"columns", "rows"} and type(table["columns"]) is list
                and table["columns"] and len(set(table["columns"])) == len(table["columns"])
                and all(type(key) is str for key in table["columns"]), "Invalid table columns: " + name)
        require(type(table["rows"]) is list and table["rows"] == sorted(table["rows"], key=canonical)
                and all(type(row) is list and len(row) == len(table["columns"]) for row in table["rows"]),
                "Invalid complete table rows: " + name)
    for name in ("projects", "chapters", "sessions", "turns", "sections", "pages", "recall_cache",
                 "pages_fts", "pages_stem_fts"):
        require(name in tables and tables[name]["rows"] == [], "Archive is not empty: " + name)
    require(tables["meta"]["columns"] == ["key", "value"]
            and tables["meta"]["rows"] == [["revision", "0"], ["stem_revision", "0"]], "Initial revisions differ")


def verify_stats(value):
    zeroes = ("projects", "chapters", "sessions", "turns", "sections", "pages", "chars",
              "page_chars", "cache_entries", "revision")
    require(type(value) is dict and set(value) == {*zeroes, "schema_version", "database_bytes"}, "Incomplete archive statistics")
    require(all(type(value[key]) is int and value[key] == 0 for key in zeroes)
            and type(value["schema_version"]) is int and value["schema_version"] == 3
            and type(value["database_bytes"]) is int and value["database_bytes"] > 0, "Nonempty or invalid archive statistics")


def verify_environment(environment, source, cwd, database):
    require(absolute(source) and absolute(cwd) and absolute(database), "Nonabsolute sample path")
    require(environment == {"PYTHONPATH": source, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
            "MEMORY_BOOK_HOME": str(PurePosixPath(cwd) / "isolated-home"), "MEMORY_BOOK_DB": database},
            "Source or isolation environment differs")


def helper_command(executable, helper, mode, source, database, version):
    return [executable, helper, "--child", mode, "--source", source,
            "--database", database, "--version", version]


def verify_import(details, source, version):
    require(details["module_path"] == str(PurePosixPath(source) / "memory_book/__init__.py")
            and details["store_path"] == str(PurePosixPath(source) / "memory_book/store.py")
            and details["class_module"] == "memory_book.store" and details["version"] == version,
            "Actual imported API source/version differs")


def verify_fixture(fixture, run):
    require(fixture["returncode"] == 0 and fixture["stderr"] == ""
            and valid_hash(fixture["database_sha256"]), "Baseline fixture failed or lacks identity")
    details = fixture["details"]
    require(json_value(fixture["stdout"]) == details and details["timer"] is None
            and details["database_before"] is None, "Fixture used a measured timer or existing archive")
    source = run["source_paths"]["baseline"]
    version = run["binding"]["sources"]["baseline"]["version"]
    verify_import(details, source, version)
    verify_empty(details["database_after"])
    verify_stats(details["stats"])
    database = fixture["database"]
    verify_environment(fixture["environment"], source, str(PurePosixPath(database).parent), database)
    command = fixture["command"]
    require(type(command) is list and len(command) == 10 and absolute(command[1])
            and command[1].endswith("/scripts/round6_startup.py"), "Wrong baseline fixture helper")
    require(command == helper_command(run["host"]["executable"], command[1], "fixture", source, database, version),
            "Baseline fixture command differs")
    return command[1]


def verify_timer(timer, process, primary):
    require(type(timer) is dict and set(timer) == {"start_ns", "end_ns", "elapsed_ms"}, "Wrong child timer fields")
    require(type(timer["start_ns"]) is int and type(timer["end_ns"]) is int
            and process["wall_start_ns"] <= timer["start_ns"] <= timer["end_ns"] <= process["wall_end_ns"],
            "Child timer is outside actual process lifetime")
    exact_number(timer["elapsed_ms"], (timer["end_ns"] - timer["start_ns"]) / 1e6, "Child elapsed milliseconds")
    exact_number(primary, timer["elapsed_ms"], "Primary timer boundary")


def verify_mcp(details, process, version, template):
    require(details["database_before"] == details["database_after"] == template, "MCP changed its input archive")
    initialization, tools = details["initialize_result"], details["tools_result"]
    require(type(initialization) is dict and type(initialization.get("protocolVersion")) is str
            and type(initialization.get("capabilities")) is dict
            and initialization.get("serverInfo", {}).get("name") == "AI-Memory-Book"
            and type(initialization["serverInfo"].get("version")) is str, "Invalid full MCP initialization")
    instructions = initialization.get("instructions")
    require(type(instructions) is str and bool(instructions), "Missing MCP instructions")
    normalized = json_value(canonical(initialization))
    if normalized["serverInfo"]["version"] == version:
        normalized["serverInfo"]["version"] = "<declared-product-version>"
    require(details["normalization"] == "Only initialize_result.serverInfo.version exactly equal to the declared source version becomes <declared-product-version>; no other changes.",
            "Undeclared MCP identity normalization")
    require(details["initialize_identity_sha256"] == digest(normalized)
            and details["tools_sha256"] == digest(tools)
            and details["instructions_sha256"] == sha(instructions.encode()), "MCP raw metadata hashes differ")
    expected_tools = {"recall_memory", "browse_projects", "browse_book", "browse_chapter", "browse_section", "read_page"}
    require(type(tools) is dict and type(tools.get("tools")) is list
            and len(tools["tools"]) == len(expected_tools)
            and {tool["name"] for tool in tools["tools"]} == expected_tools, "Incomplete/read-write MCP tool population")
    require(all(type(tool.get("inputSchema")) is dict and tool["inputSchema"].get("type") == "object"
                for tool in tools["tools"]), "Missing MCP tool schemas")
    expected_command = [process["command"][0], "-m", "memory_book", "--db",
                        process["environment"]["MEMORY_BOOK_DB"], "mcp"]
    sample = details["server_sample"]
    require(details["server_command"] == sample["cmdline"] == expected_command
            and details["server_environment"] == process["environment"], "Actual MCP server command/environment differs")
    require(type(sample["pid"]) is int and sample["pid"] > 0 and sample["pid"] != process["pid"]
            and type(sample["sampled_at_ns"]) is int
            and details["timer"]["end_ns"] <= sample["sampled_at_ns"] <= process["wall_end_ns"], "Wrong MCP sample PID/boundary")
    require(sample["scope"] == "Live server procfs snapshot immediately after initialize; RSS/HWM and CPU observed at this point, not whole-lifetime maxima/totals.",
            "MCP sampled resource scope changed")
    require(type(sample["rss_bytes"]) is int and type(sample["hwm_bytes"]) is int
            and 0 < sample["rss_bytes"] <= sample["hwm_bytes"]
            and sample["rss_bytes"] % 1024 == sample["hwm_bytes"] % 1024 == 0
            and number(sample["user_cpu_s"]) and number(sample["system_cpu_s"]), "Invalid MCP resources")


def verify_observation(row, identity, run, template, helper):
    require(type(row) is dict and {key: row[key] for key in identity} == identity
            and row["status"] == "completed", "Missing/reordered/failed original sample")
    require(number(row["primary_ms"]), "Invalid primary sample")
    process, boundary = row["process"], row["boundary"]
    require(type(process["returncode"]) is int and process["returncode"] == 0
            and process["timed_out"] is False and process["stderr"] == ""
            and type(process["stdout"]) is str, "Process failed, timed out or emitted stderr")
    require(type(process["pid"]) is int and process["pid"] > 0
            and type(process["wall_start_ns"]) is int and type(process["wall_end_ns"]) is int
            and 0 <= process["wall_start_ns"] < process["wall_end_ns"], "Invalid parent clock/PID")
    exact_number(process["wall_ms"], (process["wall_end_ns"] - process["wall_start_ns"]) / 1e6, "Process wall milliseconds")
    require(number(process["user_cpu_s"]) and number(process["system_cpu_s"])
            and type(process["max_rss_bytes"]) is int and process["max_rss_bytes"] > 0
            and process["max_rss_bytes"] % 1024 == 0, "Invalid per-child wait4 resources")
    require(process["rusage_scope"] == "Kernel wait4 usage for the actual child PID, with Linux ru_maxrss KiB converted to bytes; it may include descendants reaped by that child. MCP helper results are not isolated client-only usage; live server resources are separately sampled.",
            "Actual child rusage scope differs")
    source, version = run["source_paths"][row["engine"]], run["binding"]["sources"][row["engine"]]["version"]
    cwd = process["cwd"]
    database = str(PurePosixPath(cwd).parent / "book.db")
    verify_environment(process["environment"], source, cwd, database)
    require(process["cwd_before"] == process["cwd_after"] == [], "Unexpected sample working-directory files")
    executable = run["host"]["executable"]
    if boundary.startswith("cli-"):
        require(process["command"] == [executable, "-m", "memory_book", "--" + boundary[4:]]
                and row["details"] is None and row["database_exists_after"] is False, "CLI was wrapped or created an archive")
        exact_number(row["primary_ms"], process["wall_ms"], "CLI end-to-end boundary")
        if boundary == "cli-version":
            require(process["stdout"] == version + "\n", "Actual CLI version differs")
        else:
            require(process["stdout"].startswith("usage: memory-book") and "--help" in process["stdout"], "Missing actual CLI help")
        return
    require(process["command"] == helper_command(executable, helper, boundary, source, database, version), "Wrong timed helper command")
    details = row["details"]
    require(type(details) is dict and json_value(process["stdout"]) == details, "Helper stdout differs from saved details")
    verify_timer(details["timer"], process, row["primary_ms"])
    if boundary == "mcp-initialize":
        require(row["database_exists_after"] is True, "MCP archive disappeared")
        verify_mcp(details, process, version, template)
    else:
        verify_import(details, source, version)
        if boundary == "api-import":
            require(details["database_before"] is details["database_after"] is details["stats"] is None
                    and row["database_exists_after"] is False, "API import created/opened an archive")
        else:
            require(row["database_exists_after"] is True and details["database_after"] == template
                    and details["database_before"] == (None if boundary == "api-new" else template), "Constructor changed empty source/schema state")
            verify_stats(details["stats"])


def verify_ledger(events, observations):
    require(type(events) is list and len(events) == 960, "Expected all 960 original attempt events")
    for identity, row in zip(schedule(), observations):
        started, finished = events[2 * identity["sequence"]:2 * identity["sequence"] + 2]
        require(set(started) == {"event", "at", *identity}
                and set(finished) == {"event", "at", "observation_sha256", *identity}, "Unexpected attempt event fields")
        require(started["event"] == "started" and finished["event"] == "finished"
                and all(started[key] == finished[key] == value for key, value in identity.items()),
                "Reordered, duplicate or unfinished original attempt")
        require(type(started["at"]) is str and bool(started["at"])
                and type(finished["at"]) is str and bool(finished["at"])
                and finished["observation_sha256"] == digest(row), "Saved observation differs from original finish event")


def audit_observations(report, events, binding, plan):
    require(report["schema_version"] == 1 and report["protocol"] == PROTOCOL
            and report["status"] == "measurements_completed" and "error" not in report,
            "Measurement is not an intact completed startup study")
    run, observations = report["run"], report["observations"]
    require(run["binding"] == binding and run["schedule"] == schedule()
            and type(observations) is list and len(observations) == 480, "Binding/schedule/sample matrix differs")
    require(binding["sources"] == plan["sources"] and binding["measurement"] == plan["matrix"], "Frozen source/matrix differs")
    require(set(run["source_paths"]) == {"baseline", "candidate"}
            and all(absolute(path) for path in run["source_paths"].values())
            and len(set(run["source_paths"].values())) == 2, "Source paths are not isolated")
    host = run["host"]
    require(absolute(host["executable"]) and type(host["python"]) is str
            and host["python"].startswith("3.12.")
            and host["os_release"]["ID"].strip('"') == "ubuntu"
            and host["os_release"]["VERSION_ID"].strip('"') == "24.04"
            and host["packages"] == {"mcp": "1.30.0", "pydantic": "2.14.3"}
            and valid_hash(host["boot_sha256"]) and type(host["cpu_count"]) is int and host["cpu_count"] > 0,
            "Registered host/runtime environment differs")
    integrity = report["integrity_after"]
    require(integrity == {"passed": True,
            "sources": {name: value["runtime_sha256"] for name, value in binding["sources"].items()},
            "evaluator_files": binding["evaluator_files"], "plan_sha256": binding["plan"]["sha256"],
            "binding_sha256": run["binding_file"]["sha256"]}, "Final source/evaluator integrity differs")
    helper = verify_fixture(report["fixture"], run)
    template = report["fixture"]["details"]["database_after"]
    prior_end = -1
    directories = set()
    for identity, row in zip(schedule(), observations):
        verify_observation(row, identity, run, template, helper)
        process = row["process"]
        require(process["wall_start_ns"] >= prior_end, "Samples overlapped or parent clocks were reordered")
        require(process["cwd"] not in directories, "A sample reused its working directory")
        directories.add(process["cwd"])
        prior_end = process["wall_end_ns"]
    help_values = {row["process"]["stdout"] for row in observations if row["boundary"] == "cli-help"}
    require(len(help_values) == 1, "Actual CLI help bytes differ")
    for key in ("initialize_identity_sha256", "tools_sha256", "instructions_sha256"):
        require(len({row["details"][key] for row in observations if row["boundary"] == "mcp-initialize"}) == 1,
                "Full MCP identity differs: " + key)
    verify_ledger(events, observations)
    validation = {"passed": True, "expected_samples": 480, "completed_samples": 480, "errors": []}
    compare(report["validation"], validation, "validation")
    compared = recompute_comparisons(observations)
    accepted = recompute_acceptance(compared, plan)
    adverse = recompute_adverse(compared)
    compare(report["comparisons"], compared, "comparisons")
    compare(report["acceptance"], accepted, "acceptance")
    compare(report["adverse_observations"], adverse, "adverse_observations")
    return {"schema_version": 1, "protocol": PROTOCOL, "passed": True, "no_new_measurements": True,
            "samples_checked": 480, "ledger_events_checked": 960,
            "source_identities": binding["sources"], "empty_archive_snapshot_sha256": digest(template),
            "help_sha256": sha(next(iter(help_values)).encode()),
            "startup_numeric_gate_passed": accepted["numeric_gate_passed"],
            "original_automatic_accepted": report["acceptance"]["accepted"],
            "original_recall_gates_unpassed": True,
            "comparisons": compared, "acceptance": accepted, "adverse_observations": adverse}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def committed_runtime_hash(commit):
    require(valid_hash(commit, 40), "Invalid source commit identity")
    prefix = "src/memory_book/"
    files = sorted(name for name in git("ls-tree", "-r", "--name-only", commit, prefix).decode().splitlines()
                   if name.endswith(".py"))
    require(bool(files), "Missing committed runtime files")
    hashed = hashlib.sha256()
    for name in files:
        hashed.update(name[len(prefix):].encode() + b"\0")
        hashed.update(git("show", commit + ":" + name) + b"\0")
    return hashed.hexdigest()


def verify_git_identity(report, binding_raw):
    binding = json_value(binding_raw)
    plan_raw = git("show", PLAN_COMMIT + ":" + PLAN_PATH)
    plan = json_value(plan_raw)
    require((ROOT / PLAN_PATH).read_bytes() == plan_raw and plan["protocol"] == PROTOCOL, "Registered plan Git bytes differ")
    require(binding["schema_version"] == 1 and binding["protocol"] == PROTOCOL
            and binding["status"] == "frozen-before-measurement"
            and binding["plan"] == {"path": PLAN_PATH, "commit": PLAN_COMMIT, "sha256": sha(plan_raw)}
            and binding["sources"] == plan["sources"] and binding["measurement"] == plan["matrix"], "Frozen binding differs")
    require(plan["matrix"]["rounds"] == 4 and plan["matrix"]["total_samples"] == 480
            and plan["matrix"]["samples_per_engine_boundary"] == 40
            and plan["matrix"]["samples_per_engine_boundary_round"] == 10
            and plan["matrix"]["boundaries"] == list(BOUNDARIES)
            and plan["matrix"]["engine_order"] == [list(order) for order in ORDERS], "Registered matrix differs")
    require(valid_hash(binding["evaluator_commit"], 40)
            and set(binding["evaluator_files"]) == set(EVALUATORS), "Evaluator closure differs")
    publication, original = report["run"]["publication"], report["run"]["binding_file"]
    key = digest({"protocol": PROTOCOL, "sources": {name: value["runtime_sha256"]
                                                  for name, value in binding["sources"].items()}})
    require(type(publication["run_id"]) is str and publication["run_id"].isdigit()
            and publication["attempt"] == "1" and valid_hash(publication["workflow_commit"], 40)
            and publication["key"] == key
            and publication["branch"] == "validation/v034-round6-startup-" + publication["run_id"] + "-1"
            and publication["claim_branch"] == "validation/v034-round6-startup-claim-" + key,
            "Original first-attempt execution identity differs")
    path = PurePosixPath(original["path"])
    require(path.parent.as_posix() == "benchmarks/experiments" and path.name.startswith("round6-startup-")
            and path.name.endswith("binding.json") and original["sha256"] == sha(binding_raw)
            and git("show", publication["workflow_commit"] + ":" + path.as_posix()) == binding_raw,
            "Trigger did not contain the exact original binding")
    for name, expected in binding["evaluator_files"].items():
        require(valid_hash(expected) and sha((ROOT / name).read_bytes()) == expected
                and sha(git("show", binding["evaluator_commit"] + ":" + name)) == expected
                and sha(git("show", publication["workflow_commit"] + ":" + name)) == expected,
                "Bound evaluator Git/current bytes differ: " + name)
    for source in binding["sources"].values():
        require(committed_runtime_hash(source["commit"]) == source["runtime_sha256"], "Bound source Git bytes differ")
    return binding, plan


def audit_files(report_path, ledger_path, binding_path):
    report_raw, ledger_raw, binding_raw = read_raw(report_path), read_raw(ledger_path), Path(binding_path).read_bytes()
    report = json_value(report_raw)
    require(report["ledger_sha256"] == sha(ledger_raw), "Declared original ledger digest differs")
    events = [json_value(line) for line in ledger_raw.splitlines()]
    binding, plan = verify_git_identity(report, binding_raw)
    result = audit_observations(report, events, binding, plan)
    directory = Path(report_path).parent
    require(json_value((directory / "run.json").read_bytes()) == report["run"]
            and json_value((directory / "fixture.json").read_bytes()) == report["fixture"], "Original run/fixture record differs")
    execution = json_value((directory / "execution.json").read_bytes())
    require(execution["protocol"] == PROTOCOL and execution["key"] == report["run"]["publication"]["key"]
            and execution["run_sha256"] == digest(report["run"]), "Original execution claim differs")
    result["saved_files"] = {name: {"sha256": sha(Path(path).read_bytes()), "bytes": Path(path).stat().st_size}
                             for name, path in (("report", report_path), ("ledger", ledger_path), ("binding", binding_path))}
    result["git_identity_verified"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("report", "ledger", "binding", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_files(args.report, args.ledger, args.binding)
    except Exception as error:
        result = {"schema_version": 1, "protocol": PROTOCOL, "passed": False, "no_new_measurements": True,
                  "error": {"type": type(error).__name__, "message": str(error)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({key: value for key, value in result.items()
                      if key in ("passed", "samples_checked", "ledger_events_checked", "startup_numeric_gate_passed",
                                 "original_automatic_accepted", "no_new_measurements", "error")}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
