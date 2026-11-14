"""Archive and independently inspect saved C7 development rows; never run recall."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
from c6_development_memo_verifier import audit_native_memo

SOURCES = {
    "baseline": {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82", "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"},
    "candidate": {"commit": "d0c84cbfc9bad440ad447d41e211d070ef5b2cae", "runtime_sha256": "55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45"}}
CONFIGS = ("native-char4000", "native-token512", "native-token1024", "native-token2048")
COHORTS = {"synthetic61": (168, "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26"),
    "public1015": (1015, "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857")}
HELPER_SHA = "b19f6a473868ab6c8b3c2c49d572740401ffd6812efac71e0b4aa9ef290769ad"
PLAN_SHA = "b6b61348a178cabbc4f787eb8ccd18ebdbeeb11cd18f6f82149b098c1057593c"
REGISTRATION_SHA = "7dc67e10049bf28ffc57060432442a0bdc371da2cc95506bf373e8381d50afeb"
REGISTRATION_COMMIT = "718ce3bbe42e23774e616219bd8ae60d143fb76f"
QUERY_ORDER_RUN_SHA = "5c042cbb299db837a9c9c5b1b3f3e2205042287915e77b696bc5376b3075d93c"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_json(path):
    raw = path.read_bytes()
    return gzip.decompress(raw) if path.suffix == ".gz" else raw


def quantile(values, proportion):
    values = sorted(values)
    position = (len(values) - 1) * proportion
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def statistics(values):
    return {"count": len(values), "mean_ms": math.fsum(values) / len(values),
            "p50_ms": quantile(values, .5), "p95_ms": quantile(values, .95)}


def inspect(report, workers, root, manifest_raw):
    require(type(HELPER_SHA) is str and re.fullmatch(r"[0-9a-f]{64}", HELPER_SHA) is not None
            and all(isinstance(value, str) for value in SOURCES["candidate"].values()),
            "C7 development audit is blocked until source and measurement helper are frozen")
    require(report["status"] == "completed" and report["sources"] == SOURCES, "Incomplete or different source-bound development run")
    require(report["script_sha256"] == HELPER_SHA and report["development_plan_sha256"] == PLAN_SHA,
            "Changed development helper or registered plan")
    require(sha((root / "scripts/round5_c7_development_pair.py").read_bytes()) == HELPER_SHA
            and sha((root / "benchmarks/experiments/round5-c7-development-plan.json").read_bytes()) == PLAN_SHA,
            "Repository helper/plan bytes differ")
    registration = report["continuation_registration"]
    require(registration["commit"] == REGISTRATION_COMMIT and registration["sha256"] == REGISTRATION_SHA
            and sha((root / registration["path"]).read_bytes()) == REGISTRATION_SHA,
            "C7 preregistration differs")
    expected = [(cohort, repetition, label) for cohort in COHORTS
                for repetition, labels in enumerate((("baseline", "candidate"), ("candidate", "baseline")))
                for label in labels]
    require([(w["cohort"], w["round"], w["label"]) for w in report["workers"]] == expected,
            "Missing, duplicate or reordered source workers")
    require(report["workers"] == workers, "Raw worker files differ from the aggregate")
    reference_raw = (root / "benchmarks/reports/round5-performance-43547085915-1/run.json").read_bytes()
    require(sha(reference_raw) == QUERY_ORDER_RUN_SHA, "Frozen original query-ID reference differs")
    reference = json.loads(reference_raw)
    paired, archive_projections, values, by_round, cold_first, memo = {}, {}, {}, {}, [], []
    counts = {"baseline": 0, "candidate": 0}
    invariant_failures, mismatches = [], []
    for worker in workers:
        cohort, repetition, label = worker["cohort"], worker["round"], worker["label"]
        key = f"{cohort}-{repetition}-{label}"
        require(worker["status"] == "completed" and worker["runtime_source_commit"] == SOURCES[label]["commit"]
                and worker["runtime_source_sha256"] == SOURCES[label]["runtime_sha256"], "Worker source/status differs: " + key)
        require(worker["dataset_sha256"] == COHORTS[cohort][1], "Dataset differs: " + key)
        require(worker["archive_before"] == worker["archive_after"]
                and worker["archive_before"]["cache_entries"] == 0, "Archive or result cache changed: " + key)
        projection = worker["archive_before"]
        require(cohort not in archive_projections or archive_projections[cohort] == projection,
                "Cross-source archive projections differ: " + key)
        archive_projections.setdefault(cohort, projection)
        require([cell["configuration"] for cell in worker["cells"]] == list(CONFIGS), "Configuration order differs: " + key)
        memo.append(audit_native_memo({**worker, "key": key, "configurations": [
            {"id": cell["configuration"], "surface": "native", "rows": cell["rows"]} for cell in worker["cells"]]}))
        actual_calls = actual_tokens = 0
        for config_index, cell in enumerate(worker["cells"]):
            config = cell["configuration"]
            original_ids = reference["cohorts"][cohort]["query_ids_original_order"]
            ordered = sorted(original_ids, key=lambda identity: (hashlib.sha256(
                ("round4-native-development-v1/" + identity).encode()).digest(), identity))
            random.Random(91261 + repetition * 1009 + config_index).shuffle(ordered)
            require([row["query_id"] for row in cell["rows"]] == ordered
                    and len(ordered) == COHORTS[cohort][0], "Full fixed query order differs: " + key + ":" + config)
            times = []
            for row in cell["rows"]:
                elapsed = row["wall_ms"]
                require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0,
                        "Invalid saved timing sample: " + key + ":" + config + ":" + row["query_id"])
                require(re.fullmatch(r"[0-9a-f]{64}", row["payload_sha256"]) is not None, "Malformed full payload digest")
                expected_checks = {"context_size", "character_cap", "cache_hit_false", "revision"}
                if config != "native-char4000":
                    expected_checks |= {"exact_token_count", "token_cap"}
                    actual_tokens += 1
                if set(row["invariants"]) != expected_checks or any(value is not True for value in row["invariants"].values()):
                    invariant_failures.append({"worker": key, "configuration": config, "query_id": row["query_id"], "invariants": row["invariants"]})
                pair = (cohort, repetition, config, row["query_id"])
                require(label not in paired.setdefault(pair, {}), "Duplicated saved version pair")
                paired[pair][label] = row["payload_sha256"]
                counts[label] += 1
                actual_calls += 1
                times.append(elapsed)
            values.setdefault((cohort, config, label), []).extend(times)
            by_round[(cohort, config, repetition, label)] = times
            cold_first.append({"worker": key, "configuration": config, "query_id": cell["rows"][0]["query_id"],
                               "wall_ms": times[0], "retained_in_pooled_and_round_statistics": True})
        require(worker["invariant_checks"] == {"calls": actual_calls, "exact_token_calls": actual_tokens, "violations": 0},
                "Saved invariant count differs: " + key)
    require(counts == {"baseline": 9464, "candidate": 9464} and len(paired) == 9464,
            "Incomplete 18,928-call/9,464-pair comparison")
    for identity, pair in paired.items():
        if set(pair) != {"baseline", "candidate"} or pair["baseline"] != pair["candidate"]:
            mismatches.append({"identity": list(identity), "payloads": pair})
    pooled, rounds, adverse, round_adverse = [], [], [], []
    for cohort in COHORTS:
        for config in CONFIGS:
            def comparison(value_map, repetition=None):
                result = {"cohort": cohort, "configuration": config}
                if repetition is not None:
                    result["round"] = repetition
                for label in SOURCES:
                    result[label] = statistics(value_map[label])
                result["change_percent"] = {field: 100 * (result["candidate"][field] / result["baseline"][field] - 1)
                                            for field in ("mean_ms", "p50_ms", "p95_ms")}
                return result
            result = comparison({label: values[(cohort, config, label)] for label in SOURCES})
            pooled.append(result)
            for metric, change in result["change_percent"].items():
                if change > 0:
                    adverse.append({"cohort": cohort, "configuration": config, "metric": metric, "change_percent": change})
            for repetition in range(2):
                result = comparison({label: by_round[(cohort, config, repetition, label)] for label in SOURCES}, repetition)
                rounds.append(result)
                for metric, change in result["change_percent"].items():
                    if change > 0:
                        round_adverse.append({"cohort": cohort, "configuration": config, "round": repetition,
                                              "metric": metric, "change_percent": change})
    require(report["complete_payload_pairs"] == len(paired) and report["complete_payload_mismatches"] == len(mismatches),
            "Aggregate complete-payload verification differs")
    return {"status": "completed", "audit_passed": not mismatches and not invariant_failures,
        "role": "Single fixed full-old-data native C7 development comparison; no formal acceptance, MCP timing or new competitor result.",
        "sources": SOURCES, "manifest_sha256": sha(manifest_raw), "helper_sha256": HELPER_SHA,
        "development_plan_sha256": PLAN_SHA, "registration_sha256": REGISTRATION_SHA,
        "original_query_reference_sha256": QUERY_ORDER_RUN_SHA,
        "calls": counts, "total_calls": sum(counts.values()), "complete_payload_pairs": len(paired),
        "unique_query_configuration_pairs": len(paired) // 2, "payload_mismatches": mismatches,
        "invariant_failures": invariant_failures, "all_invariants_passed": not invariant_failures,
        "source_index_revision_unchanged": True, "cross_source_archive_projections_identical": True,
        "pooled": pooled, "per_round": rounds,
        "geometric_mean_p95_improvement_percent": 100 * (1 - math.exp(math.fsum(
            math.log(cell["candidate"]["p95_ms"] / cell["baseline"]["p95_ms"]) for cell in pooled) / len(pooled))),
        "all_pooled_adverse_metrics": adverse, "all_per_round_adverse_metrics": round_adverse,
        "native_memo_observations": memo, "first_query_timings": cold_first,
        "cold_start_verified_for_candidate_books": 4, "memo_limits": {"entries": 2048, "retained_text_object_bytes": 2097152},
        "sample_retention": "Every call, version pair, round and adverse metric retained. First queries remain in every applicable statistic; no measurement repeated.",
        "retrievals_or_timing_runs_executed_during_audit": 0, "formal_acceptance_evaluated": False,
        "limitations": ["Old regression questions on one host, two AB/BA development rounds; no fresh-domain, statistical-significance or competitor claim.",
            "Query-result cache is disabled. The candidate's exact token-count memo is enabled and naturally retained across native configurations on each book.",
            "First-query snapshots describe the native memo prefix, not cold OS caches or a separate latency experiment.",
            "The 2 MiB cap counts retained text objects only. This development helper does not measure total memo overhead, process RSS or actual MCP latency; the fixed formal resource and MCP gates remain required."],
        "started_at": report["created_at"], "finished_at": report["finished_at"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    args = parser.parse_args()
    require(type(SOURCES["candidate"]["commit"]) is str and
            re.fullmatch(r"[0-9a-f]{40}", SOURCES["candidate"]["commit"]) is not None and
            type(SOURCES["candidate"]["runtime_sha256"]) is str and
            re.fullmatch(r"[0-9a-f]{64}", SOURCES["candidate"]["runtime_sha256"]) is not None,
            "C7 development audit is blocked until its exact source is frozen")
    root, output = args.root.resolve(), args.archive_dir.resolve()
    manifest_raw = raw_json(args.manifest)
    report = json.loads(manifest_raw)
    output.mkdir(parents=True, exist_ok=False)
    checksums, workers = {}, []
    def retain(name, raw):
        compressed = gzip.compress(raw, mtime=0)
        with (output / name).open("xb") as stream:
            stream.write(compressed)
        require(gzip.decompress((output / name).read_bytes()) == raw, "Compressed archive did not preserve original bytes")
        checksums[name] = {"sha256": sha(compressed), "uncompressed_sha256": sha(raw),
                           "bytes": len(compressed), "uncompressed_bytes": len(raw)}
    retain("manifest.json.gz", manifest_raw)
    for worker in report["workers"]:
        name = f"{worker['cohort']}-{worker['round']}-{worker['label']}.json"
        path = args.state_dir / name
        if not path.exists():
            path = args.state_dir / (name + ".gz")
        raw = raw_json(path)
        retain(name + ".gz", raw)
        workers.append(json.loads(raw))
    shutil.copyfile(__file__, output / "audit_saved.py")
    shutil.copyfile(Path(__file__).with_name("c6_development_memo_verifier.py"), output / "c6_development_memo_verifier.py")
    try:
        summary = inspect(report, workers, root, manifest_raw)
    except Exception as error:
        summary = {"status": "audit_failed", "audit_passed": False, "error": type(error).__name__ + ": " + str(error),
                   "sources": SOURCES, "manifest_sha256": sha(manifest_raw), "retrievals_or_timing_runs_executed_during_audit": 0}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    receipt = {"original_manifest": str(args.manifest), "original_worker_state": str(args.state_dir),
        "compressed_originals": checksums, "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
            for p in sorted(output.iterdir()) if p.is_file()},
        "scope": "Archived exact original JSON bytes in deterministic gzip; no measurement repeated."}
    (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key in
        ("status", "audit_passed", "error", "total_calls", "complete_payload_pairs", "geometric_mean_p95_improvement_percent", "pooled", "per_round", "all_pooled_adverse_metrics", "all_per_round_adverse_metrics")}, indent=2))
    return 0 if summary.get("audit_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
