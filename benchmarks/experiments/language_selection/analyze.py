#!/usr/bin/env python3
"""Independent, fail-closed audit and paired-round analysis for the language lab.

Restored from the agreed protocol after the transient execution environment was
lost. This source requires its own CI self-test; earlier local predecessor tests
do not certify these reconstructed bytes. No production code is modified.
"""
from __future__ import annotations

import argparse
import copy
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys
import tempfile

BASELINE = "234891619d7bed88ddf3fae37e7f3e1b14a808b6"
MAIN_VARIANTS = ("current", "rust_same", "c_table", "rust_table",
                 "rust_window", "c_window", "node_window", "node_small")
COHORTS = ("synthetic61", "public1015", "unicode_stress")
CONFIGS = ("direct-char2400", "mcp-char2400", "direct-token1024", "mcp-token1024")
INVARIANTS = {"scope", "source_spans", "page_projection", "context_reconstruction",
              "metadata", "character_budget", "result_limit", "token_budget", "token_metadata"}
OUTPUT_FIELDS = ("query_id", "category", "payload_sha256", "native_payload_sha256",
                 "context_sha256", "envelope_sha256", "context_chars", "context_tokens",
                 "result_count", "invariants")
ROW_FIELDS = set(OUTPUT_FIELDS) | {"repetition", "wall_ms", "calling_process_cpu_ms"}
INGESTION = ("fresh_ingestion_ms", "unchanged_ingestion_ms", "changed_ingestion_ms")
SOURCE_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")
ARCHIVE_FIELDS = set(SOURCE_TABLES) | {"pages_fts", "pages_stem_fts", "schema", "meta",
                                       "user_version", "application_id"}
CLASSES = {
    "rust_same": "Rust at the same native interface; retains the other native helpers",
    "c_table": "C shared-table strategy control; not a language-only change",
    "rust_table": "Rust shared-table strategy; compare directly with c_table",
    "rust_window": "Rust owns a complete excerpt-selection stage",
    "c_window": "C owns the identical excerpt-selection stage",
    "node_window": "Persistent Node owned-stage bridge; not a complete Node application",
    "node_small": "Persistent Node small-helper bridge; not a complete Node application",
    "python_reference": "Correctness reference only; excluded from performance ranking",
}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
KEY_RE = re.compile(r"[A-Za-z0-9_.-]+\Z")


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def reject_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def load_json(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return loads(handle.read())


def quantile(values, probability):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot summarize zero samples")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower])


def latency(values):
    return {"samples": len(values), "mean_ms": statistics.fmean(values),
            "p50_ms": quantile(values, .5), "p95_ms": quantile(values, .95),
            "min_ms": min(values), "max_ms": max(values)}


def finite(value, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def sha(value):
    return isinstance(value, str) and HASH_RE.fullmatch(value) is not None


def close(left, right):
    return finite(left) and finite(right) and math.isclose(left, right, rel_tol=1e-11, abs_tol=1e-12)


def scenario(cohort, configuration, metric):
    return (cohort, None if configuration in (None, "ingestion") else configuration, metric)


def declared(items):
    return {scenario(x["cohort"], x.get("configuration"), x["metric"]) for x in items}


def ordered_queries(query_ids, round_index, repeats, configuration_index):
    for repetition in range(repeats):
        ordered = list(query_ids)
        random.Random(171117 + round_index * 1009 + repetition * 97 + configuration_index).shuffle(ordered)
        for query_id in ordered:
            yield query_id, repetition


@lru_cache(maxsize=4096)
def bootstrap(values, resamples, seed):
    """Whole rounds are the sampling units. No query-level bootstrap."""
    if not values:
        return (None, None)
    if min(values) == max(values):
        return (values[0], values[0])
    generator = random.Random(seed)
    n = len(values)
    means = [statistics.fmean(values[generator.randrange(n)] for _ in range(n))
             for _ in range(resamples)]
    return (quantile(means, .025), quantile(means, .975))


class Audit:
    def __init__(self):
        self.errors = []

    def require(self, condition, code, detail=None):
        if not condition:
            self.errors.append({"code": code, "detail": detail})
        return bool(condition)

    def read(self, path, code):
        try:
            return load_json(path)
        except (OSError, ValueError, TypeError, EOFError) as error:
            self.require(False, code, {"path": str(path), "error": str(error)})
            return None


def bound_artifact(root, relative, expected_hash, audit, code):
    if not audit.require(isinstance(relative, str), code + ".path", relative):
        return None
    path = (root / relative).resolve()
    if not audit.require(path.is_relative_to(root.resolve()), code + ".path_escape", relative):
        return None
    try:
        actual = file_hash(path)
    except OSError as error:
        audit.require(False, code + ".missing", {"path": relative, "error": str(error)})
        return None
    audit.require(sha(expected_hash) and actual == expected_hash, code + ".sha256",
                  {"path": relative, "expected": expected_hash, "actual": actual})
    return path


def check_usage(value, audit, where):
    if not audit.require(isinstance(value, dict), "resources.missing_usage", where):
        return
    for name in ("rss_bytes", "hwm_bytes", "user_cpu_s", "system_cpu_s"):
        audit.require(finite(value.get(name)), "resources.invalid", [where, name, value.get(name)])
    if finite(value.get("rss_bytes")) and finite(value.get("hwm_bytes")):
        audit.require(value["hwm_bytes"] >= value["rss_bytes"], "resources.hwm_below_rss", where)


def check_identity(identity, variant, manifest, audit, where):
    if not audit.require(isinstance(identity, dict), "identity.missing", where):
        return
    spec = manifest.get("variants", {}).get(variant, {})
    python = variant == "python_reference"
    for field, expected in (("variant", variant), ("source", spec.get("source")),
                            ("requested", "python" if python else "native"),
                            ("actual", "python" if python else "native")):
        audit.require(identity.get(field) == expected, "identity." + field,
                      [where, identity.get(field), expected])
    expected_methods = spec.get("expected_runtime_registered_methods", [])
    actual_methods = identity.get("runtime_registered_methods")
    audit.require(isinstance(actual_methods, list) and len(set(actual_methods)) == len(actual_methods)
                  and sorted(actual_methods) == sorted(expected_methods),
                  "identity.registered_methods", [where, actual_methods, expected_methods])
    if not python:
        audit.require(identity.get("excerpt_window_ready") is True, "identity.excerpt_guard", where)
        expected = spec.get("native_binary_sha256")
        audit.require(sha(expected) and identity.get("native_binary_sha256") == expected,
                      "identity.native_binary", where)
    if variant in ("c_table", "rust_table"):
        expected = spec.get("plugin_binary_sha256")
        audit.require(sha(expected) and identity.get("plugin_binary_sha256") == expected,
                      "identity.plugin_binary", where)
        plugin = identity.get("plugin", {})
        audit.require(isinstance(plugin, dict) and plugin.get("candidate") ==
                      ("c-table-fold" if variant == "c_table" else "rust-table-fold"),
                      "identity.table_candidate", where)
        audit.require(plugin.get("table_enabled") is True, "identity.table_disabled", where)
        audit.require(sha(plugin.get("table_sha256")), "identity.table_hash", where)
        audit.require(bool(plugin.get("runtime_ucd_version")) and
                      plugin.get("runtime_ucd_version") == plugin.get("table_ucd_version"),
                      "identity.unicode_version", where)
    if variant in ("rust_window", "c_window"):
        prefix = "rust" if variant == "rust_window" else "c"
        expected = spec.get(prefix + "_owned_sha256")
        audit.require(sha(expected) and identity.get(prefix + "_owned_binary_sha256") == expected,
                      "identity.owned_binary", where)
    if variant.startswith("node_"):
        audit.require(identity.get("node_math_verified") is True, "identity.node_math", where)
        audit.require(integer(identity.get("node_pid"), 1), "identity.node_pid", where)
        expected = manifest.get("host", {}).get("node_executable_sha256")
        audit.require(sha(expected) and identity.get("node_executable_sha256") == expected,
                      "identity.node_binary", where)


def check_archive(value, audit, where):
    if not audit.require(isinstance(value, dict) and set(value) == ARCHIVE_FIELDS,
                         "archive.fields", where):
        return
    for table in SOURCE_TABLES:
        row = value[table]
        if not audit.require(isinstance(row, dict), "archive.table", [where, table]):
            continue
        audit.require(set(row) == {"columns", "excluded_host_columns", "rows", "sha256"},
                      "archive.table_fields", [where, table])
        audit.require(isinstance(row.get("columns"), list) and all(isinstance(x, str) for x in row["columns"]),
                      "archive.columns", [where, table])
        excluded = ["created_at", "updated_at"] if table == "projects" else (
            ["updated_at"] if table in ("chapters", "sessions") else [])
        audit.require(row.get("excluded_host_columns") == excluded,
                      "archive.exclusions", [where, table, row.get("excluded_host_columns")])
        audit.require(integer(row.get("rows")) and sha(row.get("sha256")),
                      "archive.table_count_hash", [where, table])
    for table in ("pages_fts", "pages_stem_fts"):
        row = value[table]
        audit.require(isinstance(row, dict) and set(row) == {"rows", "sha256"}
                      and integer(row.get("rows")) and sha(row.get("sha256")),
                      "archive.fts", [where, table])
        if isinstance(row, dict):
            audit.require(row.get("rows") == value["pages"].get("rows"),
                          "archive.fts_row_count", [where, table])
    for key in ("schema", "meta"):
        audit.require(sha(value[key]), "archive.hash", [where, key])
    for key in ("user_version", "application_id"):
        audit.require(integer(value[key]), "archive.integer", [where, key])


def check_row(row, config, audit, where):
    if not audit.require(isinstance(row, dict) and set(row) == ROW_FIELDS, "row.fields", where):
        return False
    audit.require(isinstance(row["query_id"], str) and isinstance(row["category"], str),
                  "row.labels", where)
    audit.require(integer(row["repetition"]), "row.repetition", where)
    audit.require(finite(row["wall_ms"], positive=True), "row.wall_ms", where)
    audit.require(finite(row["calling_process_cpu_ms"]), "row.cpu_ms", where)
    for key in ("payload_sha256", "native_payload_sha256", "context_sha256"):
        audit.require(sha(row[key]), "row.hash", [where, key])
    audit.require((sha(row["envelope_sha256"]) if config.startswith("mcp-")
                   else row["envelope_sha256"] is None), "row.envelope", where)
    tokens = config.endswith("token1024")
    audit.require(integer(row["context_chars"]) and row["context_chars"] <= (8000 if tokens else 2400),
                  "row.character_budget", where)
    audit.require((integer(row["context_tokens"]) and row["context_tokens"] <= 1024)
                  if tokens else row["context_tokens"] is None, "row.token_budget", where)
    audit.require(integer(row["result_count"]) and row["result_count"] <= 5, "row.result_limit", where)
    audit.require(isinstance(row["invariants"], dict) and set(row["invariants"]) == INVARIANTS
                  and all(type(x) is int and x == 0 for x in row["invariants"].values()),
                  "row.invariants", where)
    return True


def output_signature(row):
    return digest({key: row[key] for key in OUTPUT_FIELDS})


def check_configuration_resources(resources, variant, config, manifest, audit, where):
    if not audit.require(isinstance(resources, dict), "resources.configuration_missing", where):
        return
    if config.startswith("direct-"):
        check_usage(resources.get("parent"), audit, where + ".parent")
        if variant.startswith("node_"):
            check_usage(resources.get("node"), audit, where + ".node")
        return
    audit.require(finite(resources.get("startup_to_initialize_ms"), positive=True),
                  "resources.startup", where)
    for key in ("tool_schema_sha256", "instructions_sha256"):
        audit.require(sha(resources.get(key)), "resources.schema_hash", [where, key])
    for key in ("server_before", "server_after"):
        check_usage(resources.get(key), audit, where + "." + key)
    for key in ("activation_receipt", "server_receipt"):
        # The SDK may terminate the server before its finally block writes the
        # shutdown receipt. Start identity plus live before/after sampling are
        # mandatory; a retained shutdown identity is checked when available.
        if key == "server_receipt" and key not in resources:
            continue
        receipt = resources.get(key)
        if audit.require(isinstance(receipt, dict), "resources.receipt_missing", [where, key]):
            check_identity(receipt.get("identity"), variant, manifest, audit, where + "." + key)
            check_usage(receipt.get("parent"), audit, where + "." + key + ".parent")
            if variant.startswith("node_"):
                check_usage(receipt.get("node"), audit, where + "." + key + ".node")
    if variant.startswith("node_"):
        for key in ("node_before", "node_after"):
            check_usage(resources.get(key), audit, where + "." + key)


def check_ledger(path, configurations, config_order, audit, where):
    expected = ((config, row) for config in config_order
                for row in configurations.get(config, {}).get("rows", []))
    events = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for config, row in expected:
                for event in ("started", "completed"):
                    line = handle.readline()
                    if not line:
                        audit.require(False, "ledger.truncated", [where, events, event])
                        return events
                    entry = loads(line)
                    events += 1
                    wanted = {"event": event, "configuration": config,
                              "query_id": row.get("query_id"), "repetition": row.get("repetition"),
                              "row": None if event == "started" else row}
                    audit.require(canonical(entry) == canonical(wanted), "ledger.event_mismatch",
                                  [where, events, config, row.get("query_id"), event])
            trailing = handle.readline()
            audit.require(not trailing, "ledger.extra_events", where)
            # Read to EOF so gzip CRC/trailer failures cannot be ignored.
            if trailing:
                for _ in handle:
                    events += 1
                events += 1
    except (OSError, EOFError, ValueError, TypeError) as error:
        audit.require(False, "ledger.unreadable", [where, str(error)])
    return events


def load_worker(root, item, run, audit):
    key = item["key"]
    metadata = run.get("artifacts", {}).get(key, {})
    report_path = bound_artifact(root, key + ".json.gz", metadata.get("report_sha256"),
                                 audit, "report")
    ledger_path = bound_artifact(root, key + ".json.gz.events.jsonl.gz",
                                 metadata.get("ledger_sha256"), audit, "ledger")
    intent = audit.read(root / (key + ".intent.json"), "intent.unreadable")
    audit.require(intent == {"item": item, "plan_sha256": digest(run["plan"])},
                  "intent.plan_or_schedule_changed", key)
    if report_path is None:
        return None
    raw = audit.read(report_path, "report.unreadable")
    if not audit.require(isinstance(raw, dict), "report.object", key):
        return None
    variant, cohort = item["variant"], item["cohort"]
    for field in ("variant", "cohort", "round"):
        audit.require(raw.get(field) == item[field], "report.schedule_identity", [key, field])
    completed = raw.get("status") == "completed"
    audit.require(completed and raw.get("error") is None, "report.worker_failed",
                  [key, raw.get("status"), raw.get("error")])
    audit.require(raw.get("manifest_sha256") == digest(run["manifest"]),
                  "report.manifest_changed", key)
    expected_dataset = run["plan"]["cohorts"][cohort]["dataset"]
    audit.require(raw.get("dataset") == expected_dataset, "report.dataset_changed", key)
    check_identity(raw.get("identity"), variant, run["manifest"], audit, key)
    audit.require(raw.get("frozen_inputs_unchanged") is True, "report.inputs_changed", key)
    configurations = raw.get("configurations", {})
    if not isinstance(configurations, dict):
        audit.require(False, "report.configurations_type", key)
        configurations = {}
    audit.require(set(configurations) == set(item["configs"]), "report.configurations", key)
    ledger_events = check_ledger(ledger_path, configurations, item["configs"], audit, key) if ledger_path else 0
    output = {"item": item, "status": raw.get("status"), "error": raw.get("error"),
              "identity": raw.get("identity"), "resources": raw.get("resources", {}),
              "configurations": {}, "completed": completed, "ledger_events": ledger_events,
              "row_count": 0}
    query_ids = run["plan"]["cohorts"][cohort]["query_ids"]
    for index, config in enumerate(item["configs"]):
        cell = configurations.get(config, {})
        rows = cell.get("rows", [])
        if not audit.require(isinstance(rows, list), "report.rows_type", [key, config]):
            continue
        expected_order = list(ordered_queries(query_ids, item["round"], item["repeats"], index))
        actual_order = [(row.get("query_id"), row.get("repetition")) for row in rows if isinstance(row, dict)]
        audit.require(actual_order == expected_order, "report.query_order_or_count", [key, config])
        signatures, values, cpu = {}, [], []
        for row_index, row in enumerate(rows):
            if not check_row(row, config, audit, [key, config, row_index]):
                continue
            signature = output_signature(row)
            qid = row["query_id"]
            if qid in signatures:
                audit.require(signatures[qid] == signature, "report.repeat_output_changed",
                              [key, config, qid])
            signatures[qid] = signature
            if finite(row["wall_ms"], positive=True):
                values.append(row["wall_ms"])
            if finite(row["calling_process_cpu_ms"]):
                cpu.append(row["calling_process_cpu_ms"])
        output["row_count"] += len(rows)
        summary = latency(values) if values else None
        declared_latency = cell.get("latency", {})
        if summary:
            audit.require(isinstance(declared_latency, dict) and set(declared_latency) == set(summary),
                          "report.latency_fields", [key, config])
            for name, value in summary.items():
                audit.require(close(declared_latency.get(name), value),
                              "report.latency_recompute", [key, config, name])
        resources = cell.get("resources", {})
        check_configuration_resources(resources, variant, config, run["manifest"], audit, key + "." + config)
        output["configurations"][config] = {
            "signatures": signatures, "values": values, "cpu_values": cpu,
            "summary": summary, "resources": resources}
    for field in ("ingestion_sha256", "unchanged_sha256", "changed_ingestion_sha256"):
        audit.require(sha(raw.get(field)), "report.ingestion_hash", [key, field])
        output[field] = raw.get(field)
    for field in ("archive_before", "archive_after", "archive_changed"):
        check_archive(raw.get(field), audit, key + "." + field)
        output[field] = raw.get(field)
    audit.require(raw.get("archive_before") == raw.get("archive_after"),
                  "report.query_mutated_archive", key)
    audit.require(raw.get("archive_changed") != raw.get("archive_before"),
                  "report.changed_ingestion_not_changed", key)
    resources = output["resources"]
    if not isinstance(resources, dict):
        audit.require(False, "resources.worker_type", key)
        output["resources"] = resources = {}
    for field in ("experimental_activation_ms", "new_database_ms") + INGESTION:
        audit.require(finite(resources.get(field)), "resources.worker_duration", [key, field])
    check_usage(resources.get("parent_after"), audit, key + ".parent_after")
    if variant.startswith("node_"):
        check_usage(resources.get("node_after"), audit, key + ".node_after")
    return output


def check_plan(run, audit):
    plan, manifest = run.get("plan", {}), run.get("manifest", {})
    formal = run.get("formal") is True
    audit.require(run.get("schema_version") == 1, "run.schema")
    audit.require(type(run.get("formal")) is bool, "run.formal_boolean")
    audit.require(run.get("status") == "completed", "run.not_completed", run.get("status"))
    audit.require(manifest.get("schema_version") == 1, "manifest.schema")
    audit.require(manifest.get("baseline_commit") == BASELINE, "manifest.baseline")
    audit.require(run.get("manifest_sha256") == digest(manifest), "manifest.digest")
    audit.require(tuple(plan.get("variants", [])) == MAIN_VARIANTS, "plan.variants")
    audit.require(set(plan.get("cohorts", {})) == set(COHORTS), "plan.cohorts")
    audit.require(tuple(plan.get("configs", [])) == CONFIGS, "plan.configs")
    for name in ("rounds", "repeats"):
        audit.require(integer(plan.get(name), 1), "plan.positive_integer", name)
    if formal:
        audit.require(plan.get("rounds") == 6 and plan.get("repeats") == 2,
                      "plan.formal_rounds_repeats")
        audit.require(manifest.get("status") == "formal", "manifest.formal_status")
    for name, expected in (("benefit_percent", 5.0), ("regression_percent", 3.0),
                           ("minimum_improving_rounds", 5), ("bootstrap_resamples", 10000)):
        audit.require(type(plan.get(name)) in (int, float) and plan.get(name) == expected,
                      "plan.frozen_threshold", name)
    for cohort, spec in plan.get("cohorts", {}).items():
        ids = spec.get("query_ids", [])
        audit.require(isinstance(ids, list) and bool(ids) and
                      all(isinstance(x, str) for x in ids) and len(set(ids)) == len(ids)
                      and spec.get("query_count") == len(ids), "plan.query_ids", cohort)
        audit.require(isinstance(spec.get("dataset"), dict), "plan.dataset", cohort)
    expected_primary = {(cohort, config, metric) for cohort in COHORTS
                        for config in CONFIGS[:2] for metric in ("p50_ms", "p95_ms")}
    expected_primary |= {(cohort, None, "fresh_ingestion_ms") for cohort in COHORTS}
    expected_keys = {(cohort, config, metric) for cohort in COHORTS for config in CONFIGS
                     for metric in ("p50_ms", "p95_ms")}
    expected_keys |= {(cohort, None, metric) for cohort in COHORTS for metric in INGESTION}
    try:
        audit.require(declared(plan.get("primary_targets", []) + plan.get("stress_targets", [])) == expected_primary,
                      "plan.primary_targets")
        audit.require(declared(plan.get("key_scenarios", [])) == expected_keys,
                      "plan.key_scenarios")
    except (KeyError, TypeError, ValueError) as error:
        audit.require(False, "plan.scenario_schema", str(error))
    aa = plan.get("aa", {})
    audit.require(integer(aa.get("rounds")), "plan.aa_rounds")
    placement = aa.get("placement", {})
    before_rounds = placement.get("before_main_rounds") if isinstance(placement, dict) else None
    audit.require(before_rounds == ([0, 2, 4] if formal else []),
                  "plan.aa_placement", before_rounds)
    audit.require(isinstance(before_rounds, list) and len(before_rounds) == aa.get("rounds"),
                  "plan.aa_placement_count")
    if formal:
        audit.require(aa.get("rounds") == 3, "plan.formal_aa_rounds")
    if aa.get("rounds", 0):
        audit.require(aa.get("cohort") == "public1015" and aa.get("configs") == list(CONFIGS[:2])
                      and aa.get("variants") == ["current", "aa_current"]
                      and aa.get("repeats", 1) == 1, "plan.aa_definition")
    expected_variants = set(MAIN_VARIANTS) | {"python_reference"}
    if aa.get("rounds", 0):
        expected_variants.add("aa_current")
    audit.require(expected_variants <= set(manifest.get("variants", {})),
                  "manifest.variant_specs_missing")
    current = manifest.get("variants", {}).get("current", {})
    aa_current = manifest.get("variants", {}).get("aa_current", {})
    if aa.get("rounds", 0):
        for key in ("native_binary_sha256", "source"):
            audit.require(current.get(key) == aa_current.get(key), "aa.not_identical_" + key)
    frozen = manifest.get("file_sha256", {})
    audit.require(isinstance(frozen, dict) and bool(frozen) and
                  all(isinstance(k, str) and sha(v) for k, v in frozen.items()), "manifest.file_hashes")
    audit.require(run.get("file_sha256_after") == frozen, "manifest.inputs_changed_after")
    for variant, spec in manifest.get("variants", {}).items():
        for name in ("native_binary_sha256", "plugin_binary_sha256", "rust_owned_sha256", "c_owned_sha256"):
            if name in spec:
                audit.require(sha(spec[name]) and spec[name] in frozen.values(),
                              "manifest.binary_not_frozen", [variant, name])
    node_hash = manifest.get("host", {}).get("node_executable_sha256")
    audit.require(sha(node_hash) and node_hash in frozen.values(), "manifest.node_not_frozen")
    source_hash = file_hash(Path(__file__))
    audit.require(any(Path(name).name == Path(__file__).name and value == source_hash
                      for name, value in frozen.items()), "manifest.analyzer_not_frozen")
    methods = manifest.get("native_methods")
    audit.require(isinstance(methods, list) and len(methods) == 22 and len(set(methods)) == 22,
                  "manifest.native_methods")


def check_schedule(run, audit):
    plan = run["plan"]
    schedule = run.get("schedule", [])
    audit.require(isinstance(schedule, list), "schedule.type")
    if not isinstance(schedule, list):
        return []
    expected = {("main", variant, cohort, r)
                for variant in plan["variants"] for cohort in plan["cohorts"]
                for r in range(plan["rounds"])}
    aa = plan.get("aa", {})
    expected |= {("aa", variant, aa["cohort"], r)
                 for variant in aa.get("variants", []) for r in range(aa.get("rounds", 0))}
    observed, keys, usable = set(), set(), []
    for item in schedule:
        if not audit.require(isinstance(item, dict), "schedule.item_type"):
            continue
        key = item.get("key")
        if not audit.require(isinstance(key, str) and KEY_RE.fullmatch(key) is not None
                             and key not in keys, "schedule.key", key):
            continue
        keys.add(key)
        phase = item.get("phase", "main")
        identifier = (phase, item.get("variant"), item.get("cohort"), item.get("round"))
        if phase == "reference":
            audit.require(item.get("variant") == "python_reference", "schedule.reference_variant", key)
        else:
            audit.require(identifier in expected and identifier not in observed,
                          "schedule.unexpected_or_duplicate_worker", key)
        observed.add(identifier)
        definition = aa if phase == "aa" else plan
        audit.require(item.get("configs") == definition.get("configs")
                      and item.get("repeats") == definition.get("repeats", 1),
                      "schedule.worker_plan", key)
        audit.require(item.get("cohort") in plan["cohorts"] and
                      item.get("variant") in run["manifest"]["variants"]
                      and integer(item.get("round")), "schedule.worker_identity", key)
        usable.append(dict(item, phase=phase))
    audit.require(expected <= observed, "schedule.missing_workers", sorted(expected - observed))
    audit.require(len([x for x in observed if x[0] != "reference"]) == len(expected),
                  "schedule.matrix_size")
    # The declaration binds where the controls occur, not merely their set.
    # Two A/A workers precede all main workers of rounds 0, 2 and 4.
    placement = aa.get("placement", {}).get("before_main_rounds", [])
    expected_phase_order = []
    for main_round in range(plan["rounds"]):
        if main_round in placement:
            aa_round = placement.index(main_round)
            expected_phase_order.extend([("aa", aa_round)] * len(aa.get("variants", [])))
        expected_phase_order.extend([("main", main_round)] *
                                    (len(plan["variants"]) * len(plan["cohorts"])))
    actual_phase_order = [(x["phase"], x["round"]) for x in usable if x["phase"] != "reference"]
    audit.require(actual_phase_order == expected_phase_order,
                  "schedule.aa_placement_or_round_order")
    for aa_round in range(aa.get("rounds", 0)):
        actual = [x["variant"] for x in usable if x["phase"] == "aa" and x["round"] == aa_round]
        wanted = ["current", "aa_current"] if aa_round % 2 == 0 else ["aa_current", "current"]
        audit.require(actual == wanted, "schedule.aa_pair_order", aa_round)
    if run.get("formal"):
        for cohort in plan["cohorts"]:
            for variant in plan["variants"]:
                if variant == "current":
                    continue
                earlier = 0
                for r in range(plan["rounds"]):
                    order = [x["variant"] for x in usable if x["phase"] == "main"
                             and x["cohort"] == cohort and x["round"] == r]
                    if "current" in order and variant in order:
                        earlier += order.index(variant) < order.index("current")
                audit.require(earlier == 3, "schedule.order_not_balanced", [cohort, variant, earlier])
    return usable


def audit_outputs(workers, audit):
    indexed = {(w["item"]["phase"], w["item"]["variant"], w["item"]["cohort"], w["item"]["round"]): w
               for w in workers}
    paired_calls, mismatches = 0, 0
    archive_fields = ("ingestion_sha256", "unchanged_sha256", "changed_ingestion_sha256",
                      "archive_before", "archive_after", "archive_changed")
    for worker in workers:
        item = worker["item"]
        if item["variant"] == "current":
            continue
        baseline = indexed.get((item["phase"], "current", item["cohort"], item["round"]))
        if baseline is None and item["phase"] == "reference":
            baseline = indexed.get(("main", "current", item["cohort"], item["round"]))
        if not audit.require(baseline is not None, "comparison.baseline_missing", item["key"]):
            continue
        for field in archive_fields:
            equal = worker.get(field) == baseline.get(field)
            audit.require(equal, "comparison.archive_or_ingestion_mismatch", [item["key"], field])
            mismatches += not equal
        for config, cell in worker["configurations"].items():
            reference = baseline["configurations"].get(config)
            if not audit.require(reference is not None, "comparison.baseline_cell_missing", [item["key"], config]):
                continue
            equal = cell["signatures"] == reference["signatures"]
            audit.require(equal, "comparison.full_output_mismatch", [item["key"], config])
            mismatches += not equal
            paired_calls += len(cell["values"])
            if config.startswith("mcp-"):
                for field in ("tool_schema_sha256", "instructions_sha256"):
                    audit.require(cell["resources"].get(field) == reference["resources"].get(field),
                                  "comparison.mcp_schema_mismatch", [item["key"], config, field])
    # The same fixed dataset must be deterministic across repetitions, rounds,
    # process boundaries and the separate A/A phase.
    archive_references, output_references = {}, {}
    for worker in workers:
        item = worker["item"]
        if item["variant"] != "current":
            continue
        prior = archive_references.setdefault(item["cohort"], worker)
        for field in archive_fields:
            audit.require(worker.get(field) == prior.get(field), "comparison.baseline_round_archive",
                          [item["key"], field])
        for config, cell in worker["configurations"].items():
            # A/A precedes main and covers only character configurations.
            # Every configuration needs its own first-seen baseline.
            previous = output_references.setdefault((item["cohort"], config), cell)
            audit.require(cell["signatures"] == previous["signatures"],
                          "comparison.baseline_round_output", [item["key"], config])
            if config.startswith("mcp-"):
                for field in ("tool_schema_sha256", "instructions_sha256"):
                    audit.require(cell["resources"].get(field) == previous["resources"].get(field),
                                  "comparison.baseline_round_schema", [item["key"], config, field])
    return indexed, paired_calls, mismatches


def audit_probes(root, run, audit):
    expected = {(v, c) for v in MAIN_VARIANTS + ("python_reference",) for c in COHORTS}
    entries = run.get("probes", [])
    records, indexed = [], {}
    for entry in entries:
        if not audit.require(isinstance(entry, dict), "probe.entry_type"):
            continue
        variant, cohort = entry.get("variant"), entry.get("cohort")
        pair = (variant, cohort)
        audit.require(pair in expected and pair not in indexed, "probe.unexpected_or_duplicate", pair)
        path = bound_artifact(root, entry.get("path"), entry.get("sha256"), audit, "probe")
        if path is None:
            continue
        value = audit.read(path, "probe.unreadable")
        if not audit.require(isinstance(value, dict), "probe.object", pair):
            continue
        indexed[pair] = value
        check_identity(value.get("identity"), variant, run["manifest"], audit, "probe." + str(pair))
        audit.require(value.get("dataset") == run["plan"]["cohorts"].get(cohort, {}).get("dataset"),
                      "probe.dataset", pair)
        audit.require(value.get("instrumentation_removed") is True, "probe.instrumentation_retained", pair)
        audit.require(value.get("frozen_inputs_unchanged") is True, "probe.inputs_changed", pair)
        if variant == "rust_same":
            linked = value.get("linked_methods", [])
            replaced = {"terms_ascii", "ascii_tokens", "unicode_tokens", "literal_positions",
                        "fold_excerpt_source", "evidence_units"}
            audit.require(isinstance(linked, list) and len(linked) == 22
                          and {x.get("name") for x in linked} == set(run["manifest"]["native_methods"])
                          and all(type(x.get("replaced")) is int and x["replaced"] in (0, 1) for x in linked)
                          and {x.get("name") for x in linked if x.get("replaced") == 1} == replaced
                          and all(type(x.get("flags")) is int and x["flags"] == 1
                                  and integer(x.get("original_address"), 1)
                                  and integer(x.get("effective_address"), 1)
                                  and ((x["original_address"] != x["effective_address"]) == (x["replaced"] == 1))
                                  for x in linked),
                          "probe.rust_linkage", pair)
        for field in ("ingestion_sha256", "responses_sha256"):
            audit.require(sha(value.get(field)), "probe.output_hash", [pair, field])
        check_archive(value.get("archive"), audit, "probe." + str(pair))
        record = {"variant": variant, "cohort": cohort, "identity": value.get("identity")}
        for field in ("native_calls", "bridge_calls", "actual_node_operations", "bridge_native_fallback"):
            counts = value.get(field, {})
            audit.require(isinstance(counts, dict) and all(isinstance(k, str) and integer(v)
                                                          for k, v in counts.items()),
                          "probe.dispatch_counts", [pair, field])
            record[field] = counts
        owned = value.get("owned_window_dispatch", {})
        if variant in ("rust_window", "c_window"):
            audit.require(isinstance(owned, dict) and set(owned) >= {"calls", "completed", "fallback"}
                          and all(integer(owned.get(k)) for k in ("calls", "completed", "fallback"))
                          and owned.get("calls") == owned.get("completed", 0) + owned.get("fallback", 0)
                          and owned.get("completed", 0) > 0, "probe.owned_not_executed", pair)
        record["owned_window_dispatch"] = owned
        records.append(record)
    audit.require(expected == set(indexed), "probe.missing_matrix", sorted(expected - set(indexed)))
    for pair, value in indexed.items():
        variant, cohort = pair
        reference = indexed.get(("current", cohort))
        if reference is None:
            continue
        for field in ("ingestion_sha256", "responses_sha256", "archive"):
            audit.require(value.get(field) == reference.get(field), "probe.full_output_mismatch", [pair, field])
        if variant == "rust_same":
            for method in ("terms_ascii", "ascii_tokens", "unicode_tokens", "literal_positions",
                           "fold_excerpt_source", "evidence_units"):
                if reference.get("native_calls", {}).get(method, 0) > 0:
                    audit.require(value.get("native_calls", {}).get(method, 0) > 0,
                                  "probe.rust_not_executed", [pair, method])
        if variant in ("c_table", "rust_table"):
            if reference.get("native_calls", {}).get("fold_excerpt_source", 0) > 0:
                audit.require(value.get("native_calls", {}).get("fold_excerpt_source", 0) > 0,
                              "probe.table_not_executed", pair)
        if variant.startswith("node_"):
            targeted = ["excerpt_window"] if variant == "node_window" else (
                ["terms_ascii", "ascii_tokens", "context_allocations"])
            for method in targeted:
                expected_calls = reference.get("native_calls", {}).get(method, 0)
                if expected_calls > 0:
                    audit.require(value.get("actual_node_operations", {}).get(method, 0) > 0,
                                  "probe.node_not_executed", [pair, method])
            audit.require("bridge_native_fallback" in value and "actual_node_operations" in value,
                          "probe.node_actual_dispatch_missing", pair)
        if variant in ("c_table", "rust_table"):
            other = indexed.get(("rust_table" if variant == "c_table" else "c_table", cohort))
            if other:
                left = value.get("identity", {}).get("plugin", {})
                right = other.get("identity", {}).get("plugin", {})
                for field in ("table_sha256", "table_ucd_version", "table_bytes"):
                    audit.require(left.get(field) == right.get(field), "probe.table_control_not_same", [pair, field])
    return records


def compare(indexed, plan, variant, baseline="current", phase="main", cohort=None,
            configuration=None, metric="p50_ms"):
    expected_rounds = plan["rounds"] if phase == "main" else plan.get("aa", {}).get("rounds", 0)
    pairs, ratios = [], []
    base_pool, candidate_pool = [], []
    for round_index in range(expected_rounds):
        left = indexed.get((phase, baseline, cohort, round_index))
        right = indexed.get((phase, variant, cohort, round_index))
        if not left or not right or not left["completed"] or not right["completed"]:
            continue
        if configuration is None:
            a, b = left["resources"].get(metric), right["resources"].get(metric)
        else:
            left_cell, right_cell = left["configurations"].get(configuration), right["configurations"].get(configuration)
            if not left_cell or not right_cell or not left_cell["summary"] or not right_cell["summary"]:
                continue
            a, b = left_cell["summary"].get(metric), right_cell["summary"].get(metric)
            base_pool.extend(left_cell["values"])
            candidate_pool.extend(right_cell["values"])
        if not finite(a, positive=True) or not finite(b, positive=True):
            continue
        improvement = 100.0 * (1.0 - b / a)
        ratios.append(improvement)
        pairs.append({"round": round_index, "baseline_ms": a, "candidate_ms": b,
                      "improvement_percent": improvement})
    seed = int(digest([phase, baseline, variant, cohort, configuration, metric])[:16], 16)
    lower, upper = bootstrap(tuple(ratios), int(plan.get("bootstrap_resamples", 10000)), seed)
    mean = statistics.fmean(ratios) if ratios else None
    improving = sum(value > 0 for value in ratios)
    regressing = sum(value < 0 for value in ratios)
    complete = len(pairs) == expected_rounds and expected_rounds > 0
    numeric_benefit = (phase == "main" and complete and expected_rounds == 6 and mean is not None
                       and mean >= plan["benefit_percent"] and lower > 0
                       and improving >= plan["minimum_improving_rounds"])
    regression = (phase == "main" and complete and expected_rounds == 6 and mean is not None
                  and mean < -plan["regression_percent"] and upper < 0
                  and regressing >= plan["minimum_improving_rounds"])
    record = {
        "phase": phase, "variant": variant, "baseline": baseline, "cohort": cohort,
        "configuration": configuration or "ingestion", "metric": metric,
        "classification": CLASSES.get(variant, "A/A identical binary control"),
        "paired_rounds": pairs, "expected_rounds": expected_rounds, "complete_rounds": complete,
        "mean_paired_improvement_percent": mean, "ci95_percent": [lower, upper],
        "improving_rounds": improving, "regressing_rounds": regressing,
        "rounds_worse_than_regression_threshold": sum(x < -plan["regression_percent"] for x in ratios),
        "numeric_benefit": bool(numeric_benefit), "repeatable_regression": bool(regression),
        "pooled_baseline": latency(base_pool) if base_pool else None,
        "pooled_candidate": latency(candidate_pool) if candidate_pool else None,
        "pooled_descriptive_improvement_percent": None,
    }
    if base_pool and candidate_pool:
        a, b = record["pooled_baseline"][metric], record["pooled_candidate"][metric]
        record["pooled_descriptive_improvement_percent"] = 100.0 * (1.0 - b / a)
    return record


def all_comparisons(indexed, plan, variant, baseline="current", phase="main"):
    if phase == "aa":
        cohorts = [plan["aa"]["cohort"]]
        configs = plan["aa"]["configs"]
    else:
        cohorts, configs = plan["cohorts"], plan["configs"]
    result = []
    for cohort in cohorts:
        for config in configs:
            for metric in ("p50_ms", "p95_ms"):
                result.append(compare(indexed, plan, variant, baseline, phase, cohort, config, metric))
        for metric in INGESTION:
            result.append(compare(indexed, plan, variant, baseline, phase, cohort, None, metric))
    return result


def aa_noise(records, expected_rounds):
    details = []
    for record in records:
        mean = record["mean_paired_improvement_percent"]
        low, high = record["ci95_percent"]
        directional = max(record["improving_rounds"], record["regressing_rounds"]) == expected_rounds
        flag = (expected_rounds == 3 and record["complete_rounds"] and mean is not None
                and abs(mean) >= 5.0 and (low > 0 or high < 0) and directional)
        details.append({"cohort": record["cohort"], "configuration": record["configuration"],
                        "metric": record["metric"], "flagged": bool(flag),
                        "mean_paired_improvement_percent": mean, "ci95_percent": [low, high]})
    query_noise = any(row["flagged"] and row["configuration"] != "ingestion" for row in details)
    ingestion_noise = sorted({row["metric"] for row in details
                              if row["flagged"] and row["configuration"] == "ingestion"})
    return {"query_timing_noise_unresolved": query_noise,
            "ingestion_metrics_with_unresolved_noise": ingestion_noise,
            "scenarios": details,
            "rule": "Three complete same-binary paired rounds, absolute mean apparent change >=5%, "
                    "95% paired-round CI excludes zero, all three rounds agree. Query noise blocks "
                    "all positive adoption; ingestion noise blocks benefit claims for that metric."}


def flatten_numeric(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = prefix + "." + key if prefix else key
            result.update(flatten_numeric(child, name))
    elif finite(value):
        result[prefix] = value
    return result


def resource_comparisons(workers, indexed):
    records = []
    for worker in workers:
        item = worker["item"]
        if item["phase"] != "main" or item["variant"] == "current":
            continue
        baseline = indexed.get(("main", "current", item["cohort"], item["round"]))
        if baseline is None:
            continue
        left = {"worker": baseline["resources"], "configuration":
                {k: v["resources"] for k, v in baseline["configurations"].items()}}
        right = {"worker": worker["resources"], "configuration":
                 {k: v["resources"] for k, v in worker["configurations"].items()}}
        a, b = flatten_numeric(left), flatten_numeric(right)
        for path in sorted(set(a) | set(b)):
            av, bv = a.get(path), b.get(path)
            records.append({"variant": item["variant"], "cohort": item["cohort"],
                            "round": item["round"], "path": path, "baseline": av, "candidate": bv,
                            "candidate_minus_baseline": bv - av if av is not None and bv is not None else None})
    return records


def adoption_decisions(comparisons, plan, audit, formal, noise):
    primary = declared(plan["primary_targets"] + plan.get("stress_targets", []))
    keys = declared(plan["key_scenarios"])
    results = []
    blocked = bool(audit.errors) or not formal or noise["query_timing_noise_unresolved"]
    for variant in plan["variants"]:
        if variant == "current":
            continue
        records = [x for x in comparisons if x["variant"] == variant]
        ordinary, stress, regressions, gates = [], [], [], []
        for row in records:
            key = scenario(row["cohort"], row["configuration"], row["metric"])
            ingestion_noise = (row["configuration"] == "ingestion" and
                               row["metric"] in noise["ingestion_metrics_with_unresolved_noise"])
            passed = key in primary and row["numeric_benefit"] and not ingestion_noise
            label = {"cohort": row["cohort"], "configuration": row["configuration"], "metric": row["metric"]}
            if passed:
                (stress if row["cohort"] == "unicode_stress" else ordinary).append(label)
            if key in keys and row["repeatable_regression"]:
                regressions.append(label)
            gates.append(dict(label, predeclared_primary=key in primary,
                              predeclared_key=key in keys, numeric_benefit=row["numeric_benefit"],
                              aa_ingestion_noise_blocks_benefit=ingestion_noise,
                              audited_benefit=bool(passed and not blocked),
                              repeatable_key_regression=key in keys and row["repeatable_regression"]))
        ordinary_gate = bool(ordinary) and not regressions and not blocked
        stress_gate = bool(stress) and not regressions and not blocked
        results.append({
            "variant": variant, "classification": CLASSES[variant],
            "ordinary_production_gate": ordinary_gate,
            "stress_only_gate": stress_gate and not ordinary_gate,
            "stress_evidence_gate": stress_gate,
            "ordinary_numeric_targets_passed": ordinary,
            "stress_numeric_targets_passed": stress,
            "blocking_key_regressions": regressions,
            "audit_blocks_adoption": bool(audit.errors),
            "nonformal_blocks_adoption": not formal,
            "aa_query_noise_blocks_adoption": noise["query_timing_noise_unresolved"],
            "scenario_gates": gates,
            "decision_scope": ("Pass means evidence for this measured candidate and workload; "
                               "not proof of the globally fastest language, whole-application migration, "
                               "or production authorization. Stress-only evidence cannot justify ordinary adoption.")
        })
    return results


def analyze(run_path, verify_local_files=False):
    run_path = Path(run_path).resolve()
    root, audit = run_path.parent, Audit()
    run = audit.read(run_path, "run.unreadable")
    if not isinstance(run, dict):
        return {"status": "partial-or-invalid-unadoptable",
                "audit": {"passed": False, "errors": audit.errors or [{"code": "run.not_object"}]},
                "adoption": []}
    workers, indexed, probes = [], {}, []
    comparisons, controls, aa_records = [], [], []
    paired_calls = mismatches = checked_files = 0

    def attempt(code, function, fallback=None):
        try:
            return function()
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, OSError, OverflowError) as error:
            audit.require(False, code, {"type": type(error).__name__, "message": str(error)})
            return fallback

    attempt("run.plan_validation_exception", lambda: check_plan(run, audit))
    schedule = attempt("run.schedule_validation_exception", lambda: check_schedule(run, audit), [])
    manifest = run.get("manifest") if isinstance(run.get("manifest"), dict) else {}
    plan = run.get("plan") if isinstance(run.get("plan"), dict) else {}
    frozen = manifest.get("file_sha256") if isinstance(manifest.get("file_sha256"), dict) else {}
    if verify_local_files:
        for path, expected in frozen.items():
            try:
                actual = file_hash(path)
                checked_files += 1
                audit.require(actual == expected, "manifest.actual_file_changed", path)
            except OSError as error:
                audit.require(False, "manifest.actual_file_missing", [path, str(error)])
    for item in schedule:
        worker = attempt("report.validation_exception." + item["key"],
                         lambda item=item: load_worker(root, item, run, audit))
        if worker is not None:
            workers.append(worker)
    result = attempt("comparison.validation_exception", lambda: audit_outputs(workers, audit))
    if result:
        indexed, paired_calls, mismatches = result
    probes = attempt("probe.validation_exception", lambda: audit_probes(root, run, audit), [])
    variants = plan.get("variants") if isinstance(plan.get("variants"), list) else []
    for variant in variants:
        if variant != "current":
            comparisons.extend(attempt("statistics.exception." + variant,
                                       lambda variant=variant: all_comparisons(indexed, plan, variant), []))
    for variant, baseline in (("rust_table", "c_table"), ("rust_window", "c_window")):
        controls.extend(attempt("statistics.control_exception." + variant,
                                lambda variant=variant, baseline=baseline:
                                all_comparisons(indexed, plan, variant, baseline), []))
    aa = plan.get("aa") if isinstance(plan.get("aa"), dict) else {}
    aa_rounds = aa.get("rounds", 0) if integer(aa.get("rounds", 0)) else 0
    if aa_rounds:
        aa_records = attempt("statistics.aa_exception",
                             lambda: all_comparisons(indexed, plan, "aa_current", phase="aa"), [])
    noise = aa_noise(aa_records, aa_rounds)
    decisions = attempt("adoption.validation_exception",
                        lambda: adoption_decisions(comparisons, plan, audit, run.get("formal") is True, noise), [])
    valid = not audit.errors
    status = ("completed" if run.get("formal") else "preflight-completed-not-adoptable") if valid else (
        "partial-or-invalid-unadoptable")
    # Do not expose rows as if independent observations supported uncertainty.
    resources = []
    for worker in workers:
        configurations = {}
        for name, cell in worker["configurations"].items():
            configurations[name] = {"resources": cell["resources"], "latency": cell["summary"],
                                    "calling_process_cpu": latency(cell["cpu_values"]) if cell["cpu_values"] else None}
        resources.append({"key": worker["item"]["key"], "status": worker["status"], "error": worker["error"],
                          "identity": worker["identity"], "resources": worker["resources"],
                          "configurations": configurations})
    return {
        "schema_version": 1, "status": status, "formal": run.get("formal"),
        "run_file_sha256": file_hash(run_path), "run_canonical_sha256": digest(run),
        "analysis_source_sha256": file_hash(Path(__file__)),
        "baseline_commit": manifest.get("baseline_commit"),
        "experiment_commit": manifest.get("experiment_commit"), "host": manifest.get("host"),
        "audit": {
            "passed": valid, "errors": audit.errors, "expected_workers": len(schedule),
            "completed_workers_loaded": sum(w["completed"] for w in workers),
            "worker_reports_loaded": len(workers),
            "attempted_calls_in_completed_reports": sum(w["row_count"] for w in workers if w["completed"]),
            "ledger_events_in_completed_reports": sum(w["ledger_events"] for w in workers if w["completed"]),
            "manifest_before_after_equal": run.get("file_sha256_after") == manifest.get("file_sha256"),
            "local_byte_verification_requested": verify_local_files,
            "local_frozen_files_checked": checked_files,
            "full_output_comparison_fields": list(OUTPUT_FIELDS),
            "paired_candidate_calls": paired_calls, "comparison_mismatches": mismatches,
        },
        "method": {
            "sampling_unit": "Whole paired rounds; queries within a round are not independent bootstrap units",
            "estimand": "Mean of per-round 100*(1-candidate_metric/baseline_metric)",
            "bootstrap_resamples": plan.get("bootstrap_resamples"), "interval": "Percentile 95%",
            "pooled_statistics": "Pooled p50/p95 describe all calls, not the bootstrap estimand",
            "benefit_rule": "Six complete rounds, mean improvement >=5%, 95% CI excludes zero, >=5/6 rounds improve",
            "regression_rule": "Mean change worse than -3%, 95% CI below zero, >=5/6 rounds regress",
            "aa_noise_rule": noise["rule"],
            "multiplicity": "Intervals are per scenario, not adjusted for searching many targets",
            "formal_required_for_adoption": True,
        },
        "comparisons": comparisons, "control_comparisons": controls,
        "aa_comparisons": aa_records, "aa_noise_flags": noise,
        "resource_comparisons": resource_comparisons(workers, indexed),
        "worker_resources": resources, "dispatch_probes": probes,
        "adoption": decisions,
        "limitations": [
            "An audited candidate improvement is not proof that a language is globally optimal.",
            "The table controls change the execution and data strategy; compare Rust directly with the same C strategy.",
            "Node kernel and Node bridge costs are different boundaries; these bridge results do not measure a complete Node rewrite.",
            "RSS values are sampled process measurements. Parent and Node high-water marks must not be summed and described as a simultaneous peak.",
            "Timing diagnostic fields alone are excluded from output equivalence. Payload, envelope, coordinates, indexes and archive hashes remain required.",
            "Downloaded evidence without --verify-local-files can check signed-in-record before/after bindings, not re-read the original host's source and binary bytes.",
            "Any failure, missing artifact, invariant or audit error prevents a positive adoption gate; completed partial evidence remains visible.",
            "A/A ingestion noise blocks only the corresponding ingestion benefit, while A/A query noise blocks all adoption. Key repeatable regressions remain visible and blocking.",
            "This analyzer was reconstructed after environment loss and must pass its own current-byte CI self-test.",
        ],
    }


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (canonical(value) + "\n").encode("utf-8")
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def fixture_usage(scale=1):
    return {"rss_bytes": 1000000 * scale, "hwm_bytes": 1200000 * scale,
            "user_cpu_s": .2, "system_cpu_s": .1}


def fixture_archive(cohort, changed=False):
    result = {}
    for name in SOURCE_TABLES:
        excluded = ["created_at", "updated_at"] if name == "projects" else (
            ["updated_at"] if name in ("chapters", "sessions") else [])
        result[name] = {"columns": ["id", "value"], "excluded_host_columns": excluded,
                        "rows": 2, "sha256": digest([cohort, name, changed])}
    for name in ("pages_fts", "pages_stem_fts"):
        result[name] = {"rows": 2, "sha256": digest([cohort, name, changed])}
    result.update(schema=digest("schema"), meta=digest([cohort, changed]),
                  user_version=1, application_id=1)
    return result


def fixture_identity(variant, manifest):
    spec = manifest["variants"][variant]
    python = variant == "python_reference"
    result = {"variant": variant, "source": spec["source"],
              "requested": "python" if python else "native", "actual": "python" if python else "native",
              "runtime_registered_methods": sorted(spec["expected_runtime_registered_methods"]),
              "excerpt_window_ready": not python}
    if not python:
        result["native_binary_sha256"] = spec["native_binary_sha256"]
    if variant in ("c_table", "rust_table"):
        result["plugin_binary_sha256"] = spec["plugin_binary_sha256"]
        result["plugin"] = {"candidate": "c-table-fold" if variant == "c_table" else "rust-table-fold",
                            "table_enabled": True, "table_sha256": digest("shared-table"),
                            "runtime_ucd_version": "15.0.0", "table_ucd_version": "15.0.0",
                            "table_bytes": 100}
    if variant in ("rust_window", "c_window"):
        prefix = "rust" if variant == "rust_window" else "c"
        result[prefix + "_owned_binary_sha256"] = spec[prefix + "_owned_sha256"]
    if variant.startswith("node_"):
        result.update(node_math_verified=True, node_pid=171117,
                      node_executable_sha256=manifest["host"]["node_executable_sha256"])
    return result


def fixture_config_resources(variant, config, manifest):
    node = fixture_usage(2) if variant.startswith("node_") else None
    if config.startswith("direct-"):
        return {"parent": fixture_usage(), "node": node}
    receipt = {"identity": fixture_identity(variant, manifest), "parent": fixture_usage(), "node": node}
    result = {"startup_to_initialize_ms": 50.0, "tool_schema_sha256": digest("schema"),
              "instructions_sha256": digest("instructions"),
              "activation_receipt": dict(receipt, pid=1, parent_pid=2),
              "server_receipt": receipt, "server_before": fixture_usage(), "server_after": fixture_usage()}
    if node:
        result.update(node_before=node, node_after=node)
    return result


def fixture_schedule(plan):
    result = []
    placement = plan["aa"]["placement"]["before_main_rounds"]
    for r in range(plan["rounds"]):
        if r in placement:
            aa_round = placement.index(r)
            aa_order = ("current", "aa_current") if aa_round % 2 == 0 else ("aa_current", "current")
            for variant in aa_order:
                result.append({"key": f"aa-r{aa_round}-public1015-{variant}", "phase": "aa", "variant": variant,
                               "cohort": "public1015", "round": aa_round, "repeats": 1, "configs": list(CONFIGS[:2])})
        shift = (r // 2) * 2
        order = list(MAIN_VARIANTS[shift:] + MAIN_VARIANTS[:shift])
        if r % 2:
            order.reverse()
        for cohort in COHORTS:
            for variant in order:
                result.append({"key": f"main-r{r}-{cohort}-{variant}", "phase": "main", "variant": variant,
                               "cohort": cohort, "round": r, "repeats": plan["repeats"], "configs": list(CONFIGS)})
    return result


def fixture_write_worker(root, run, item, report):
    key = item["key"]
    report_path = root / (key + ".json.gz")
    ledger_path = root / (key + ".json.gz.events.jsonl.gz")
    save_json(report_path, report)
    lines = []
    for config in item["configs"]:
        for row in report["configurations"].get(config, {}).get("rows", []):
            for event in ("started", "completed"):
                lines.append(canonical({"event": event, "configuration": config, "query_id": row["query_id"],
                                        "repetition": row["repetition"],
                                        "row": row if event == "completed" else None}))
    ledger_path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0))
    save_json(root / (key + ".intent.json"), {"item": item, "plan_sha256": digest(run["plan"])})
    run["artifacts"][key] = {"report_sha256": file_hash(report_path), "ledger_sha256": file_hash(ledger_path)}


def create_fixture(root):
    """A complete eight-arm, three-cohort, six-round matrix plus three A/A rounds."""
    root = Path(root)
    manifest = {"schema_version": 1, "status": "formal", "baseline_commit": BASELINE,
                "experiment_commit": "a" * 40, "host": {}, "file_sha256": {}, "variants": {}}
    native_methods = ["terms_ascii", "ascii_tokens", "unicode_tokens", "literal_positions",
                      "fold_excerpt_source", "evidence_units", "excerpt_window", "context_allocations"]
    native_methods += ["other_" + str(i) for i in range(14)]
    manifest["native_methods"] = native_methods
    frozen = {}
    for name in ("base.so", "rust-same.so", "c-table.so", "rust-table.so", "rust-owned.so", "c-owned.so", "node"):
        path = root / "inputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        frozen[str(path)] = file_hash(path)
    frozen[str(Path(__file__).resolve())] = file_hash(Path(__file__))
    manifest["file_sha256"] = frozen
    manifest["host"]["node_executable_sha256"] = frozen[str(root / "inputs/node")]
    for variant in MAIN_VARIANTS + ("aa_current", "python_reference"):
        spec = {"source": str(root / ("rust-source" if variant == "rust_same" else "current-source")),
                "expected_runtime_registered_methods": []}
        if variant != "python_reference":
            spec["native_binary_sha256"] = frozen[str(root / "inputs" /
                                                      ("rust-same.so" if variant == "rust_same" else "base.so"))]
        if variant in ("c_table", "rust_table"):
            filename = "c-table.so" if variant == "c_table" else "rust-table.so"
            spec.update(plugin_binary_sha256=frozen[str(root / "inputs" / filename)],
                        expected_runtime_registered_methods=["fold_excerpt_source"])
        if variant in ("rust_window", "c_window"):
            prefix = "rust" if variant == "rust_window" else "c"
            spec[prefix + "_owned_sha256"] = frozen[str(root / "inputs" / (prefix + "-owned.so"))]
            spec["expected_runtime_registered_methods"] = ["excerpt_window"]
        if variant == "node_window":
            spec["expected_runtime_registered_methods"] = ["excerpt_window"]
        if variant == "node_small":
            spec["expected_runtime_registered_methods"] = ["terms_ascii", "ascii_tokens", "context_allocations"]
        manifest["variants"][variant] = spec
    plan = {"rounds": 6, "repeats": 2, "variants": list(MAIN_VARIANTS), "cohorts": {},
            "configs": list(CONFIGS), "primary_targets": [], "stress_targets": [], "key_scenarios": [],
            "benefit_percent": 5.0, "regression_percent": 3.0, "minimum_improving_rounds": 5,
            "bootstrap_resamples": 10000,
            "aa": {"rounds": 3, "repeats": 1, "cohort": "public1015", "placement": {"before_main_rounds": [0, 2, 4]},
                   "configs": list(CONFIGS[:2]), "variants": ["current", "aa_current"]}}
    for cohort in COHORTS:
        ids = [cohort + "-q0", cohort + "-q1"]
        plan["cohorts"][cohort] = {"query_ids": ids, "query_count": len(ids), "dataset": {"fixture": cohort}}
        for config in CONFIGS:
            for metric in ("p50_ms", "p95_ms"):
                target = {"cohort": cohort, "configuration": config, "metric": metric}
                plan["key_scenarios"].append(target)
                if config in CONFIGS[:2]:
                    plan["stress_targets" if cohort == "unicode_stress" else "primary_targets"].append(target)
        for metric in INGESTION:
            target = {"cohort": cohort, "configuration": "ingestion", "metric": metric}
            plan["key_scenarios"].append(target)
            if metric == "fresh_ingestion_ms":
                plan["stress_targets" if cohort == "unicode_stress" else "primary_targets"].append(target)
    run = {"schema_version": 1, "status": "completed", "formal": True, "manifest": manifest,
           "manifest_sha256": digest(manifest), "plan": plan, "schedule": fixture_schedule(plan),
           "artifacts": {}, "probes": [], "file_sha256_after": dict(frozen)}
    factors = {"current": 1.0, "aa_current": 1.0, "rust_same": .99, "c_table": .94,
               "rust_table": .90, "rust_window": .92, "c_window": .93,
               "node_window": 1.12, "node_small": 1.30}
    for item in run["schedule"]:
        variant, cohort, r = item["variant"], item["cohort"], item["round"]
        factor = factors[variant]
        report = {"status": "completed", "variant": variant, "cohort": cohort, "round": r,
                  "dataset": plan["cohorts"][cohort]["dataset"], "identity": fixture_identity(variant, manifest),
                  "manifest_sha256": digest(manifest), "error": None, "frozen_inputs_unchanged": True,
                  "configurations": {}, "resources": {
                      "experimental_activation_ms": 1.0, "new_database_ms": 1.0,
                      "fresh_ingestion_ms": 100.0 * factor, "unchanged_ingestion_ms": 2.0 * factor,
                      "changed_ingestion_ms": 20.0 * factor, "parent_after": fixture_usage(),
                      "node_after": fixture_usage(2) if variant.startswith("node_") else None},
                  "ingestion_sha256": digest([cohort, "ingestion"]), "unchanged_sha256": digest([cohort, "unchanged"]),
                  "changed_ingestion_sha256": digest([cohort, "changed"]),
                  "archive_before": fixture_archive(cohort), "archive_after": fixture_archive(cohort),
                  "archive_changed": fixture_archive(cohort, True)}
        for index, config in enumerate(item["configs"]):
            rows = []
            for qid, repetition in ordered_queries(plan["cohorts"][cohort]["query_ids"], r, item["repeats"], index):
                token = config.endswith("token1024")
                base = 1.0 + .1 * int(qid[-1]) + r * .01
                row = {"query_id": qid, "category": cohort, "repetition": repetition,
                       "wall_ms": base * factor, "calling_process_cpu_ms": .1,
                       "payload_sha256": digest([cohort, config, qid, "payload"]),
                       "native_payload_sha256": digest([cohort, config, qid, "native"]),
                       "context_sha256": digest([cohort, config, qid, "context"]),
                       "envelope_sha256": digest([cohort, config, qid, "envelope"]) if config.startswith("mcp-") else None,
                       "context_chars": 100, "context_tokens": 25 if token else None, "result_count": 2,
                       "invariants": {name: 0 for name in INVARIANTS}}
                rows.append(row)
            report["configurations"][config] = {"rows": rows, "latency": latency([x["wall_ms"] for x in rows]),
                                                "resources": fixture_config_resources(variant, config, manifest)}
        fixture_write_worker(root, run, item, report)
    replaced = {"terms_ascii", "ascii_tokens", "unicode_tokens", "literal_positions", "fold_excerpt_source", "evidence_units"}
    for variant in MAIN_VARIANTS + ("python_reference",):
        for cohort in COHORTS:
            probe = {"identity": fixture_identity(variant, manifest),
                     "dataset": plan["cohorts"][cohort]["dataset"],
                     "native_calls": {name: 1 for name in native_methods} if variant != "python_reference" else {},
                     "bridge_calls": {}, "actual_node_operations": {}, "bridge_native_fallback": {},
                     "owned_window_dispatch": {"calls": 0, "completed": 0, "fallback": 0},
                     "ingestion_sha256": digest([cohort, "ingestion"]), "responses_sha256": digest([cohort, "responses"]),
                     "archive": fixture_archive(cohort), "instrumentation_removed": True,
                     "frozen_inputs_unchanged": True}
            if variant.startswith("node_"):
                names = ["excerpt_window"] if variant == "node_window" else (
                    ["terms_ascii", "ascii_tokens", "context_allocations"])
                probe["actual_node_operations"] = {name: 1 for name in names}
            if variant in ("rust_window", "c_window"):
                probe["owned_window_dispatch"] = {"calls": 2, "completed": 1, "fallback": 1}
            if variant == "rust_same":
                probe["linked_methods"] = [{"name": name, "replaced": int(name in replaced), "flags": 1,
                                           "original_address": 10000 + index,
                                           "effective_address": (20000 if name in replaced else 10000) + index}
                                          for index, name in enumerate(native_methods)]
            relative = "probes/" + variant + "-" + cohort + ".json"
            save_json(root / relative, probe)
            run["probes"].append({"variant": variant, "cohort": cohort, "path": relative,
                                  "sha256": file_hash(root / relative)})
    save_json(root / "run.json", run)
    return run


def self_test():
    checks = []
    assert quantile([1, 2, 3, 4], .5) == 2.5
    assert math.isclose(quantile([1, 2, 3, 4], .95), 3.85)
    assert not finite(True) and not finite(float("nan")) and not finite(float("inf"))
    assert finite(0) and not finite(0, positive=True)
    assert list(ordered_queries(["a", "b", "c"], 2, 2, 1)) == list(ordered_queries(["a", "b", "c"], 2, 2, 1))
    low, high = bootstrap((1.0, 3.0, 4.0, 5.0, 9.0, 10.0), 10000, 171117)
    assert low < statistics.fmean([1, 3, 4, 5, 9, 10]) < high
    checks.append("quantiles, deterministic query order, finite-number guards, whole-round bootstrap")

    with tempfile.TemporaryDirectory(prefix="language-analyzer-selftest-") as temporary:
        root = Path(temporary).resolve()
        run = create_fixture(root)
        path = root / "run.json"
        result = analyze(path, verify_local_files=True)
        assert result["audit"]["passed"], result["audit"]["errors"]
        assert result["audit"]["expected_workers"] == 150
        assert result["audit"]["completed_workers_loaded"] == 150
        assert result["audit"]["attempted_calls_in_completed_reports"] == 2328
        assert result["audit"]["ledger_events_in_completed_reports"] == 4656
        decisions = {x["variant"]: x for x in result["adoption"]}
        assert decisions["rust_table"]["ordinary_production_gate"]
        assert not decisions["node_window"]["ordinary_production_gate"]
        assert decisions["node_window"]["blocking_key_regressions"]
        assert len(result["control_comparisons"]) == 66
        assert len(result["dispatch_probes"]) == 27
        checks.append("complete eight-arm 150-worker fixture, actual dispatch, identity, archive, controls and resource retention")

        def rejected(expected):
            value = analyze(path)
            assert not value["audit"]["passed"]
            assert any(error["code"].startswith(expected) for error in value["audit"]["errors"]), value["audit"]["errors"]
            assert not any(x["ordinary_production_gate"] or x["stress_only_gate"] for x in value["adoption"])
            return value

        item = next(x for x in run["schedule"] if x["variant"] == "rust_table" and
                    x["cohort"] == "public1015" and x["round"] == 2)
        report_path = root / (item["key"] + ".json.gz")
        ledger_path = root / (item["key"] + ".json.gz.events.jsonl.gz")
        original_report, original_ledger = report_path.read_bytes(), ledger_path.read_bytes()
        original_metadata = copy.deepcopy(run["artifacts"][item["key"]])

        # Alter the ledger, then update its outer artifact hash: the semantic
        # start/complete check must still reject it.
        lines = gzip.decompress(original_ledger).decode().splitlines()
        entry = loads(lines[1])
        entry["row"]["payload_sha256"] = digest("tampered ledger")
        lines[1] = canonical(entry)
        ledger_path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0))
        run["artifacts"][item["key"]]["ledger_sha256"] = file_hash(ledger_path)
        save_json(path, run)
        rejected("ledger.event_mismatch")
        ledger_path.write_bytes(original_ledger)
        run["artifacts"][item["key"]] = copy.deepcopy(original_metadata)
        checks.append("ledger semantic tamper rejected after rehashing the outer artifact")

        # Alter payload signatures in both report and ledger. Hash equality of
        # containers is insufficient; candidate/current outputs must agree.
        modified = loads(gzip.decompress(original_report))
        for row in modified["configurations"]["mcp-char2400"]["rows"]:
            row["native_payload_sha256"] = digest(["changed native payload", row["query_id"]])
        fixture_write_worker(root, run, item, modified)
        save_json(path, run)
        rejected("comparison.full_output_mismatch")
        report_path.write_bytes(original_report)
        ledger_path.write_bytes(original_ledger)
        run["artifacts"][item["key"]] = copy.deepcopy(original_metadata)
        checks.append("complete payload mismatch rejected even with a consistent ledger")

        modified = loads(gzip.decompress(original_report))
        rows = modified["configurations"]["direct-char2400"]["rows"]
        rows[0], rows[1] = rows[1], rows[0]
        fixture_write_worker(root, run, item, modified)
        save_json(path, run)
        rejected("report.query_order_or_count")
        report_path.write_bytes(original_report)
        ledger_path.write_bytes(original_ledger)
        run["artifacts"][item["key"]] = copy.deepcopy(original_metadata)
        checks.append("query/repetition order is independently reconstructed")

        report_path.unlink()
        save_json(path, run)
        missing = rejected("report.missing")
        assert missing["audit"]["completed_workers_loaded"] == 149
        report_path.write_bytes(original_report)
        checks.append("missing worker rejects adoption but preserves the other 149 workers")

        modified = loads(gzip.decompress(original_report))
        modified["status"] = "failed"
        modified["error"] = {"type": "FixtureFailure", "message": "intentional"}
        fixture_write_worker(root, run, item, modified)
        save_json(path, run)
        rejected("report.worker_failed")
        report_path.write_bytes(original_report)
        ledger_path.write_bytes(original_ledger)
        run["artifacts"][item["key"]] = copy.deepcopy(original_metadata)
        checks.append("failed worker is retained and prevents a positive gate")

        modified = loads(gzip.decompress(original_report))
        modified["configurations"]["direct-char2400"]["rows"][0]["wall_ms"] = True
        fixture_write_worker(root, run, item, modified)
        save_json(path, run)
        rejected("row.wall_ms")
        report_path.write_bytes(original_report)
        ledger_path.write_bytes(original_ledger)
        run["artifacts"][item["key"]] = copy.deepcopy(original_metadata)
        checks.append("boolean timing is rejected rather than interpreted as one millisecond")

        # Change token outputs for every arm in one round. Candidate/current
        # pairing still agrees; independent cross-round baseline comparison
        # must detect drift even though the first public baseline was A/A char.
        drift_backups = []
        for drift_item in [x for x in run["schedule"] if x["phase"] == "main"
                           and x["cohort"] == "public1015" and x["round"] == 3]:
            drift_path = root / (drift_item["key"] + ".json.gz")
            before = load_json(drift_path)
            drift_backups.append((drift_item, copy.deepcopy(before)))
            for row in before["configurations"]["direct-token1024"]["rows"]:
                row["payload_sha256"] = digest(["cross-round token drift", row["query_id"]])
            fixture_write_worker(root, run, drift_item, before)
        save_json(path, run)
        rejected("comparison.baseline_round_output")
        for drift_item, before in drift_backups:
            fixture_write_worker(root, run, drift_item, before)
        checks.append("token baseline drift is checked across rounds even when A/A char was first")

        modified = loads(gzip.decompress(original_report))
        modified["configurations"]["direct-char2400"] = None
        save_json(report_path, modified)
        run["artifacts"][item["key"]]["report_sha256"] = file_hash(report_path)
        save_json(path, run)
        malformed = rejected("report.validation_exception")
        assert malformed["status"] == "partial-or-invalid-unadoptable"
        report_path.write_bytes(original_report)
        ledger_path.write_bytes(original_ledger)
        run["artifacts"][item["key"]] = copy.deepcopy(original_metadata)
        checks.append("malformed nested cell returns an unadoptable partial report rather than crashing")

        probe_entry = next(x for x in run["probes"] if x["variant"] == "c_table"
                           and x["cohort"] == "synthetic61")
        probe_path = root / probe_entry["path"]
        probe_bytes, probe_sha = probe_path.read_bytes(), probe_entry["sha256"]
        modified_probe = loads(probe_bytes)
        modified_probe["native_calls"]["fold_excerpt_source"] = 0
        save_json(probe_path, modified_probe)
        probe_entry["sha256"] = file_hash(probe_path)
        save_json(path, run)
        rejected("probe.table_not_executed")
        probe_path.write_bytes(probe_bytes)
        probe_entry["sha256"] = probe_sha
        checks.append("a loaded table candidate with zero actual fold calls cannot pass")

        probe_entry = next(x for x in run["probes"] if x["variant"] == "rust_same"
                           and x["cohort"] == "public1015")
        probe_path = root / probe_entry["path"]
        probe_bytes, probe_sha = probe_path.read_bytes(), probe_entry["sha256"]
        modified_probe = loads(probe_bytes)
        modified_probe["native_calls"]["terms_ascii"] = 0
        save_json(probe_path, modified_probe)
        probe_entry["sha256"] = file_hash(probe_path)
        save_json(path, run)
        rejected("probe.rust_not_executed")
        probe_path.write_bytes(probe_bytes)
        probe_entry["sha256"] = probe_sha
        checks.append("Rust link replacement alone is insufficient without real helper execution")

        # Whole-round A/A controls: ingestion-only drift cannot silently remove
        # unrelated query evidence, but it invalidates that ingestion benefit.
        aa_backups = []
        for aa_item in [x for x in run["schedule"] if x["phase"] == "aa" and x["variant"] == "aa_current"]:
            aa_path = root / (aa_item["key"] + ".json.gz")
            aa_report = load_json(aa_path)
            aa_backups.append((aa_item, copy.deepcopy(aa_report)))
            aa_report["resources"]["fresh_ingestion_ms"] *= .8
            fixture_write_worker(root, run, aa_item, aa_report)
        save_json(path, run)
        value = analyze(path)
        assert value["audit"]["passed"], value["audit"]["errors"]
        assert value["aa_noise_flags"]["ingestion_metrics_with_unresolved_noise"] == ["fresh_ingestion_ms"]
        assert not value["aa_noise_flags"]["query_timing_noise_unresolved"]
        chosen = next(x for x in value["adoption"] if x["variant"] == "rust_table")
        assert chosen["ordinary_production_gate"]
        assert all(not x["audited_benefit"] for x in chosen["scenario_gates"]
                   if x["metric"] == "fresh_ingestion_ms")
        checks.append("A/A ingestion noise blocks only corresponding ingestion benefits")

        for aa_item, aa_report in aa_backups:
            for cell in aa_report["configurations"].values():
                for row in cell["rows"]:
                    row["wall_ms"] *= 1.2
                cell["latency"] = latency([row["wall_ms"] for row in cell["rows"]])
            fixture_write_worker(root, run, aa_item, aa_report)
        save_json(path, run)
        value = analyze(path)
        assert value["audit"]["passed"], value["audit"]["errors"]
        assert value["aa_noise_flags"]["query_timing_noise_unresolved"]
        assert not any(x["ordinary_production_gate"] or x["stress_only_gate"] for x in value["adoption"])
        checks.append("A/A query drift prevents positive adoption for every candidate")
        for aa_item, _ in aa_backups:
            # Restore using the original same-binary current worker with the
            # correct aa_current identity; resource and timing values are equal.
            current_item = next(x for x in run["schedule"] if x["phase"] == "aa" and
                                x["variant"] == "current" and x["round"] == aa_item["round"])
            restored = load_json(root / (current_item["key"] + ".json.gz"))
            restored["variant"] = "aa_current"
            restored["identity"] = fixture_identity("aa_current", run["manifest"])
            for config, cell in restored["configurations"].items():
                cell["resources"] = fixture_config_resources("aa_current", config, run["manifest"])
            fixture_write_worker(root, run, aa_item, restored)
        save_json(path, run)

        # A good stress scenario, on its own, must not become an ordinary gate.
        stress_records = copy.deepcopy(result["comparisons"])
        for row in stress_records:
            row["numeric_benefit"] = row["variant"] == "rust_same" and row["cohort"] == "unicode_stress"
            row["repeatable_regression"] = False
        no_noise = {"query_timing_noise_unresolved": False, "ingestion_metrics_with_unresolved_noise": []}
        gates = adoption_decisions(stress_records, run["plan"], Audit(), True, no_noise)
        gate = next(x for x in gates if x["variant"] == "rust_same")
        assert gate["stress_only_gate"] and not gate["ordinary_production_gate"]
        gates = adoption_decisions(result["comparisons"], run["plan"], Audit(), False, no_noise)
        assert not any(x["ordinary_production_gate"] or x["stress_only_gate"] for x in gates)
        checks.append("stress-only gains and nonformal runs cannot enable ordinary adoption")

        # Exercise actual formal=false one-round/one-repeat preprocessing too.
        preflight = copy.deepcopy(run)
        preflight["formal"] = False
        preflight["manifest"]["status"] = "preflight"
        preflight["manifest_sha256"] = digest(preflight["manifest"])
        preflight["plan"]["rounds"] = preflight["plan"]["repeats"] = 1
        preflight["plan"]["aa"]["rounds"] = 0
        preflight["plan"]["aa"]["placement"] = {"before_main_rounds": []}
        old_items = {(x["variant"], x["cohort"], x["round"]): x for x in run["schedule"] if x["phase"] == "main"}
        preflight["schedule"] = fixture_schedule(preflight["plan"])
        preflight["artifacts"] = {}
        for short in preflight["schedule"]:
            old = old_items[short["variant"], short["cohort"], short["round"]]
            report = load_json(root / (old["key"] + ".json.gz"))
            report["manifest_sha256"] = preflight["manifest_sha256"]
            for config, cell in report["configurations"].items():
                cell["rows"] = [row for row in cell["rows"] if row["repetition"] == 0]
                cell["latency"] = latency([row["wall_ms"] for row in cell["rows"]])
            fixture_write_worker(root, preflight, short, report)
        save_json(path, preflight)
        value = analyze(path)
        assert value["audit"]["passed"], value["audit"]["errors"]
        assert value["status"] == "preflight-completed-not-adoptable"
        assert value["audit"]["completed_workers_loaded"] == 24
        assert not any(x["ordinary_production_gate"] or x["stress_only_gate"] for x in value["adoption"])
        checks.append("full nonformal 24-worker preflight fixture audits successfully without adoption")
    return {"status": "passed", "kind": "analyzer-self-test-not-performance", "checks": checks,
            "analysis_source_sha256": file_hash(Path(__file__)),
            "fixture_workers": 150, "fixture_calls": 2328}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-local-files", action="store_true")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Return success for an explicitly unadoptable partial report, to preserve evidence")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        if args.output:
            save_json(args.output, result)
        print(canonical(result))
        return
    if args.run is None or args.output is None:
        parser.error("--run and --output are required unless --self-test is used")
    result = analyze(args.run, verify_local_files=args.verify_local_files)
    save_json(args.output, result)
    print(canonical({"status": result["status"], "output": str(args.output),
                     "audit_passed": result["audit"]["passed"],
                     "audit_errors": len(result["audit"].get("errors", [])),
                     "adoption": [{key: row[key] for key in ("variant", "ordinary_production_gate", "stress_only_gate")}
                                  for row in result["adoption"]]}))
    if not result["audit"]["passed"] and not args.allow_partial:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
