"""Certify the one approved MCP schema addition without loading any questions.

Generation performs official SDK initialize/list_tools only, after the final
source and this evaluator registration are committed. Pure verification also
serves the formal and fresh bindings. It never calls ingestion or recall.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import timedelta
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_performance as original

VERSION = "round5-final-interface-certificate-1"
SCOPE = ROOT / "benchmarks/experiments/round5-final-interface-v2-scope.json"
SCOPE_SHA256 = "28e8f491c4ff2fbe6f815b0864cf36f497acf49414df395711e67ade57bde292"
CERTIFICATE = ROOT / "benchmarks/experiments/round5-final-interface-certificate.json"
PROPERTY = {"default": False, "title": "Follow Titles", "type": "boolean"}
DESCRIPTION_SUFFIX = (
    "follow_titles opts into one complete source-title hop from the first\n"
    "        lexical page within an explicit project. It is disabled by default and\n"
    "        cannot be combined with semantic or coverage. Compact and detailed\n"
    "        replies both retain title_reference provenance when it is enabled.\n"
    "        "
)
NEW_FILES = (
    "benchmarks/experiments/round5-final-interface-v2-scope.json",
    "scripts/round5_interface_certificate.py", "scripts/round5_performance_v2.py",
    "tests/test_round5_performance_v2.py", ".github/workflows/round5-performance-v2.yml",
)
REGISTRATION_FILES = (*original.EVALUATORS, *NEW_FILES)
OBSERVATION_FIELDS = ("tool_schema_json", "tool_schema_sha256", "instructions",
    "instructions_sha256", "initialization_tokens", "database_created")
require = original.require
sha = original.sha


def canonical(value):
    """JSON-value equality must distinguish false, zero and numeric strings."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate schema JSON field: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Non-finite schema JSON value: " + value)

    require(type(raw) is str, "Schema must preserve the actual serialized string")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def schema_projection(baseline_json, candidate_json):
    old, new = strict_json(baseline_json), strict_json(candidate_json)
    for value in (old, new):
        require(type(value) is dict and type(value.get("tools")) is list,
                "Missing complete ListToolsResult schema")
        require(all(type(tool) is dict and type(tool.get("name")) is str
                    for tool in value["tools"]), "Invalid tool schema")
        names = [tool["name"] for tool in value["tools"]]
        require(len(names) == len(set(names)) and names.count("recall_memory") == 1,
                "Missing or duplicate recall tool")
    require([t["name"] for t in old["tools"]] == [t["name"] for t in new["tools"]],
            "Ordered tool names differ")
    before = next(tool for tool in old["tools"] if tool["name"] == "recall_memory")
    projected = copy.deepcopy(new)
    after = next(tool for tool in projected["tools"] if tool["name"] == "recall_memory")
    require(type(before.get("inputSchema")) is dict and type(after.get("inputSchema")) is dict
            and type(before["inputSchema"].get("properties")) is dict
            and type(after["inputSchema"].get("properties")) is dict,
            "Missing recall input properties")
    require("follow_titles" not in before["inputSchema"]["properties"]
            and "follow_titles" in after["inputSchema"]["properties"],
            "The approved property must be the unique new recall input")
    require(canonical(after["inputSchema"]["properties"].pop("follow_titles")) == canonical(PROPERTY),
            "follow_titles must have the exact boolean/default-False schema")
    require("follow_titles" not in after["inputSchema"].get("required", []),
            "follow_titles must remain optional")
    require(type(before.get("description")) is str
            and after.get("description") == before["description"] + DESCRIPTION_SUFFIX,
            "Recall description is not the exact approved append-only addition")
    after["description"] = before["description"]
    require(canonical(projected) == canonical(old),
            "Legacy full tools schema changed after the sole approved projection")
    return {"verified": True, "tool": "recall_memory", "property": "follow_titles",
        "property_schema": PROPERTY, "description_suffix": DESCRIPTION_SUFFIX,
        "legacy_projected_schema_sha256": sha(canonical(projected).encode()),
        "ordered_tools": [t["name"] for t in old["tools"]]}


def token_counts(schema, instructions, counters):
    require(set(counters) == set(original.ENCODINGS), "Reference tokenizer axis differs")
    return {name: {"tool_schema": counter.count(schema), "instructions": counter.count(instructions)}
            for name, counter in counters.items()}


def observation(schema, instructions, counters):
    require(type(instructions) is str, "Instructions must preserve actual bytes")
    strict_json(schema)
    return {"tool_schema_json": schema, "tool_schema_sha256": sha(schema.encode()),
        "instructions": instructions, "instructions_sha256": sha(instructions.encode()),
        "initialization_tokens": token_counts(schema, instructions, counters), "database_created": False}


def verify_observation(value, counters=None):
    require(type(value) is dict and set(value) == set(OBSERVATION_FIELDS),
            "Interface observation fields differ")
    strict_json(value["tool_schema_json"])
    require(type(value["instructions"]) is str and value["database_created"] is False,
            "Schema-only initialization created a database or lost instructions")
    require(value["tool_schema_sha256"] == sha(value["tool_schema_json"].encode())
            and value["instructions_sha256"] == sha(value["instructions"].encode()),
            "Actual schema/instruction bytes differ from their hashes")
    costs = value["initialization_tokens"]
    require(type(costs) is dict and set(costs) == set(original.ENCODINGS),
            "Initialization tokenizer axis differs")
    for row in costs.values():
        require(type(row) is dict and set(row) == {"tool_schema", "instructions"}
                and all(type(n) is int and n >= 0 for n in row.values()),
                "Invalid initialization token counts")
    if counters is not None:
        require(costs == token_counts(value["tool_schema_json"], value["instructions"], counters),
                "Initialization counts differ from actual complete schema/instructions")


def initialization_delta(observations):
    return {name: {field: observations["candidate"]["initialization_tokens"][name][field]
                         - observations["baseline"]["initialization_tokens"][name][field]
                  for field in ("tool_schema", "instructions")}
            for name in original.ENCODINGS}


def verify_certificate(value, expected_sources, counters=None):
    require(value.get("schema_version") == 1 and value.get("evaluator") == VERSION
            and value.get("status") == "verified-before-formal-measurement-and-fresh-selection",
            "Wrong final-interface certificate registration")
    require(value.get("sources") == expected_sources and set(expected_sources) == {"baseline", "candidate"}
            and expected_sources["baseline"] == {"commit": original.BASELINE, "runtime_sha256": original.BASELINE_HASH},
            "Certificate is not bound to the exact baseline/final candidate")
    require(all(set(source) == {"commit", "runtime_sha256"}
                and re.fullmatch(r"[0-9a-f]{40}", source["commit"])
                and re.fullmatch(r"[0-9a-f]{64}", source["runtime_sha256"])
                for source in expected_sources.values()), "Invalid certified source identity")
    require(value.get("packages") == original.PACKAGES and value.get("scope_sha256") == SCOPE_SHA256,
            "Certificate package/scope registration differs")
    require(value.get("server_packages") == {label: original.PACKAGES for label in ("baseline", "candidate")},
            "Actual stdio server package versions differ from the registration")
    require(type(value.get("retrieval_calls_executed")) is int and value["retrieval_calls_executed"] == 0,
            "Interface generation must never retrieve")
    observed = value["observations"]
    require(set(observed) == {"baseline", "candidate"}, "Certificate source observations are incomplete")
    for item in observed.values():
        verify_observation(item, counters)
    require(observed["baseline"]["instructions"] == observed["candidate"]["instructions"],
            "MCP instructions changed")
    projected = schema_projection(observed["baseline"]["tool_schema_json"], observed["candidate"]["tool_schema_json"])
    require(canonical(value.get("projection")) == canonical(projected), "Stored schema projection differs")
    require(canonical(value.get("initialization_token_delta")) == canonical(initialization_delta(observed)),
            "Stored actual initialization token delta differs")
    return value


def registration_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in REGISTRATION_FILES}


def load_scope():
    raw = SCOPE.read_bytes()
    require(sha(raw) == SCOPE_SHA256, "Prospective interface scope changed")
    value = json.loads(raw)
    for name, expected in value["preserved_original_files_sha256"].items():
        require(sha((ROOT / name).read_bytes()) == expected, "Original evaluator was changed: " + name)
    require(value["interface_contract"]["exact_description_suffix"] == DESCRIPTION_SUFFIX
            and canonical(value["interface_contract"]["exact_new_property_schema"]) == canonical(PROPERTY),
            "Scope and exact interface contract differ")
    return value


def reference_counters():
    require(importlib.metadata.version("tiktoken") == original.PACKAGES["tiktoken"],
            "Use the registered reference tokenizer version")
    return {name: original.TokenCounter(name) for name in original.ENCODINGS}


def verify_registration(value):
    load_scope()
    require(value.get("generator_files") == registration_hashes(),
            "Certificate evaluator registration changed")
    commit = value.get("generator_commit", "")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Missing original generator commit")
    for name, expected in value["generator_files"].items():
        require(sha(original.git("show", commit + ":" + name)) == expected,
                "Certificate generator commit bytes differ: " + name)


def load_certificate(expected_sources):
    raw = CERTIFICATE.read_bytes()
    relative = CERTIFICATE.relative_to(ROOT).as_posix()
    require(raw == original.git("show", "HEAD:" + relative), "Commit the exact interface certificate before binding")
    value = json.loads(raw)
    require(raw == original.json_bytes(value), "Certificate must retain its exact canonical generated bytes")
    verify_registration(value)
    return verify_certificate(value, expected_sources, reference_counters())


def verify_session(session, expected, counters=None):
    """Keep observed costs; never replace candidate observations with baseline."""
    fields = {"mcp_tool_schema_json": "tool_schema_json", "mcp_tool_schema_sha256": "tool_schema_sha256",
        "mcp_instructions": "instructions", "mcp_instructions_sha256": "instructions_sha256",
        "mcp_initialization_tokens": "initialization_tokens"}
    actual = {target: session[source] for source, target in fields.items()}
    actual["database_created"] = False  # Formal sessions use the already ingested database.
    verify_observation(actual, counters)
    require(canonical(actual) == canonical(expected), "Actual MCP interface differs from its exact source certificate")


def server_packages(environment, work):
    """Read only dependency versions under the exact forthcoming server env."""
    command = [sys.executable, "-c", "import importlib.metadata,json; "
        "print(json.dumps({name:importlib.metadata.version(name) "
        "for name in ('mcp','pydantic','tiktoken')}))"]
    packages = json.loads(subprocess.check_output(command, env=environment, cwd=work, timeout=30))
    require(packages == original.PACKAGES,
            "Actual stdio server must use the exact registered packages; observed=" + canonical(packages))
    return packages


async def collect(src, counters):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    with tempfile.TemporaryDirectory(prefix="round5-interface-only-") as temporary:
        work = Path(temporary)
        database = work / "must-not-be-created.db"
        environment = {**os.environ, "PYTHONPATH": str(src.resolve()), "PYTHONDONTWRITEBYTECODE": "1",
            "MEMORY_BOOK_HOME": str(work / "isolated-home"), "MEMORY_BOOK_DB": str(database)}
        if environment.get("TIKTOKEN_CACHE_DIR"):
            environment["TIKTOKEN_CACHE_DIR"] = str(Path(environment["TIKTOKEN_CACHE_DIR"]).resolve())
        # A parent PYTHONPATH can provide different dependencies than the child,
        # whose import path is intentionally restricted to the bound runtime.
        # Probe this exact executable/env/cwd before starting the schema server.
        packages = server_packages(environment, work)
        parameters = StdioServerParameters(command=sys.executable,
            args=["-m", "memory_book", "--db", str(database), "mcp"], env=environment, cwd=str(work))
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                tools = await client.list_tools()
                result = observation(tools.model_dump_json(exclude_none=True), initialized.instructions or "", counters)
        require(not database.exists() and not list(work.glob(database.name + "*")),
                "Schema-only generation unexpectedly created a database")
        return {"observation": result, "packages": packages}


def generate(args):
    require(args.output.resolve() == CERTIFICATE.resolve(), "Use the single registered certificate destination")
    require(not args.output.exists(), "An existing certificate must never be overwritten")
    # Keep the failure and every completed observation if any preflight or SDK step fails.
    attempt = ROOT / ".artifacts/round5-interface-certificate" / uuid.uuid4().hex
    original.exclusive(attempt / "started.json", {"at": original.now(), "output": str(args.output),
        "baseline_src": str(args.baseline_src), "candidate_src": str(args.candidate_src)})
    record = {"schema_version": 1, "evaluator": VERSION, "status": "started", "observations": {}, "server_packages": {},
              "retrieval_calls_executed": 0}
    try:
        load_scope()
        packages = {name: importlib.metadata.version(name) for name in original.PACKAGES}
        require(packages == original.PACKAGES, "Certificate requires the exact registered SDK/Pydantic/tokenizer packages")
        sources = {label: original.source_identity(path) for label, path in
                   (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
        require(sources["baseline"] == {"commit": original.BASELINE, "runtime_sha256": original.BASELINE_HASH},
                "Certificate baseline differs from published v0.3.2")
        commit = original.git("rev-parse", "HEAD").decode().strip()
        hashes = registration_hashes()
        for name, expected in hashes.items():
            require(sha(original.git("show", commit + ":" + name)) == expected,
                    "Commit the prospective scope/evaluator/tests/workflow before generation: " + name)
        record.update(created_at=original.now(), generator_commit=commit, generator_files=hashes,
                      packages=packages, sources=sources, scope_sha256=SCOPE_SHA256)
        counters = reference_counters()
        for label, path in (("baseline", args.baseline_src), ("candidate", args.candidate_src)):
            require(original.source_identity(path) == sources[label], "Source changed before initialization")
            collected = asyncio.run(collect(path, counters))
            record["observations"][label] = collected["observation"]
            record["server_packages"][label] = collected["packages"]
            require(original.source_identity(path) == sources[label], "Source changed during initialization")
            original.exclusive(attempt / (label + ".json"), collected)
        record["projection"] = schema_projection(record["observations"]["baseline"]["tool_schema_json"],
                                                   record["observations"]["candidate"]["tool_schema_json"])
        record["initialization_token_delta"] = initialization_delta(record["observations"])
        record["status"] = "verified-before-formal-measurement-and-fresh-selection"
        verify_certificate(record, sources, counters)
        verify_registration(record)
        require(original.git("rev-parse", "HEAD").decode().strip() == commit,
                "Registration HEAD changed during schema-only generation")
        original.exclusive(args.output, record)
        original.exclusive(attempt / "completed.json", {"status": "verified", "at": original.now(),
            "certificate_sha256": sha(args.output.read_bytes()), "retrieval_calls_executed": 0})
        print(json.dumps({"certificate": str(args.output), "sha256": sha(args.output.read_bytes()),
            "initialization_token_delta": record["initialization_token_delta"], "retrieval_calls_executed": 0,
            "next": "Commit the certificate before formal binding and fresh metadata selection."}))
    except BaseException as error:
        record.update(status="failed_or_interrupted", error={"type": type(error).__name__, "message": str(error)})
        original.exclusive(attempt / "failed.json", record)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=CERTIFICATE)
    generate(parser.parse_args(argv))


if __name__ == "__main__":
    main()
