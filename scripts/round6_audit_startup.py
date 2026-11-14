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
              "tests/test_round6_startup_confirmation.py", "tests/test_round6_startup_audit.py",
              ".github/workflows/round6-startup.yml")
BOUNDARIES = ("cli-help", "cli-version", "api-import", "api-new", "api-existing", "mcp-initialize")
ORDERS = (("baseline", "candidate"), ("candidate", "baseline"),
          ("candidate", "baseline"), ("baseline", "candidate"))
METRICS = ("mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms")
PROCESS_RESOURCES = ("process.wall_ms", "process.user_cpu_s", "process.system_cpu_s", "process.max_rss_bytes")
MCP_RESOURCES = tuple("details.server_sample." + name
                      for name in ("rss_bytes", "hwm_bytes", "user_cpu_s", "system_cpu_s"))


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
        for path in PROCESS_RESOURCES + (MCP_RESOURCES if boundary == "mcp-initialize" else ()):
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
