"""Derive the second frozen recall assessment after every timed stage finishes.

Run from the repository root, after the 11 retained stages and 5 continuation
stages complete:
    PYTHONPATH=. python scripts/assess_score_quality.py

For a fresh, complete run of the corrected v2 manifest, pass --full-checkpoint.
This checks every published output and its execution lineage before deriving
paired coverage, native component comparisons, and real MCP costs. It runs no
benchmark and does not alter first-round artifacts or the failed original run.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

from benchmarks.token_compare import summarize_rows, validation_status


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "recall-score-final-"
CANDIDATE = "score-aware-recall"
BASELINE = "first-round-recall"
SOURCES = {
    "main-v0.2.1": {
        "runtime_commit": "a05f88a79ce20be3fd5912c62fc020f8b11ba4a9",
        "source_sha256": "910eeabc9780a086d4176adf5a905142924a4694ba601f27cf31408570efa88a",
    },
    "preserved-v0.3": {
        "runtime_commit": "3ee40946c5407e65fd375a8d47472066a82ae472",
        "source_sha256": "ab31378c3ed7eb486aea9a6f237139000ed6b30b8cc5dcf719b53f1b864caa1f",
    },
    BASELINE: {
        "runtime_commit": "6f5299004642618e606d001b4c574e1bae572a7e",
        "source_sha256": "191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85",
    },
    CANDIDATE: {
        "runtime_commit": "0ab49d4f2be6aabe5e51c3314bb9369041af5369",
        "source_sha256": "c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46",
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    path = ROOT / path
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_checkpoint(manifest_path, checkpoint_path, expected_stages):
    manifest = read(manifest_path)
    checkpoint_bytes = checkpoint_path.read_bytes()
    state = json.loads(checkpoint_bytes)
    require(manifest.get("version") == state.get("version") == 1, "Unsupported manifest/checkpoint")
    require(state["identity"]["manifest_sha256"] == digest(manifest), "Checkpoint manifest identity differs")
    identity_hash = digest(state["identity"])
    registered = {stage["id"]: stage for stage in manifest["stages"]}
    require(len(registered) == len(manifest["stages"]), "Manifest has duplicate stage IDs")
    verified = {}
    for stage in expected_stages:
        require(registered.get(stage["id"]) == stage,
                f"Stage differs from corrected full manifest: {stage['id']}")
        record = state["stages"].get(stage["id"], {})
        require(record.get("status") == "completed", f"Stage is not completed: {stage['id']}")
        require(record.get("identity_sha256") == identity_hash, f"Stage identity differs: {stage['id']}")
        argv = [state["identity"]["python"] if arg == "{python}" else arg for arg in stage["argv"]]
        require(record.get("argv") == argv, f"Stage command differs: {stage['id']}")
        require(set(record["outputs"]) == set(stage["outputs"]), f"Output set differs: {stage['id']}")
        for filename in stage["outputs"]:
            observed = file_hash(ROOT / filename)
            require(observed == record["outputs"][filename], f"Completed output changed: {filename}")
            verified[filename] = observed
    # The helpers used below must still have the exact scoring semantics frozen
    # in the checkpoint; report scripts themselves are deliberately not inputs.
    for relative in ("benchmarks/token_compare.py", "benchmarks/run.py"):
        recorded_path = str(Path(state["identity"]["cwd"]) / relative)
        require(file_hash(ROOT / relative) == state["identity"]["inputs"][recorded_path],
                f"Assessment helper differs from frozen harness: {relative}")
    return manifest, state, checkpoint_bytes, verified


def verify_execution(args):
    corrected = read(args.manifest)
    require(len(corrected["stages"]) == 16, "The corrected full manifest must contain 16 stages")
    if args.full_checkpoint is not None:
        _, state, content, verified = verify_checkpoint(args.manifest, args.full_checkpoint, corrected["stages"])
        return corrected, [{"role": "complete corrected run", "state": state, "bytes": content,
                            "stage_ids": [stage["id"] for stage in corrected["stages"]]}], verified, None

    original, first, first_bytes, first_outputs = verify_checkpoint(
        args.original_manifest, args.checkpoint, corrected["stages"][:11])
    tail, second, second_bytes, second_outputs = verify_checkpoint(
        args.continuation_manifest, args.continuation_checkpoint, corrected["stages"][11:])
    require(len(original["stages"]) == 16 and len(tail["stages"]) == 5,
            "Expected the original 16-stage plan and five-stage continuation")
    require(tail["inputs"] == original["inputs"] == corrected["inputs"],
            "Recovery must preserve the exact frozen input specifications")
    for key in ("version", "cwd", "runtime_commands"):
        require(original.get(key) == tail.get(key) == corrected.get(key),
                f"Recovery changed a manifest runtime setting: {key}")
    manifest_paths = {str(path.resolve()) for path in (args.manifest, args.original_manifest, args.continuation_manifest)}

    def without_manifest(identity):
        return {key: ({path: value for path, value in values.items() if path not in manifest_paths}
                      if key == "inputs" else values)
                for key, values in identity.items() if key != "manifest_sha256"}

    require(without_manifest(first["identity"]) == without_manifest(second["identity"]),
            "Runtime, source, dataset, or evaluator identity changed across recovery")
    # Only the two migration baselines changed. Keep the rejected schema-3 plan
    # and its failure intact instead of turning it into an apparent success.
    for before, after in zip(original["stages"], corrected["stages"]):
        expected = dict(before)
        if before["id"] in ("upgrade-synthetic", "upgrade-public"):
            expected["argv"] = list(before["argv"])
            for flag, old, new in (("--baseline-src", "../baseline-recall/src", "../baseline-v0.3/src"),
                                   ("--baseline-label", BASELINE, "preserved-v0.3")):
                position = expected["argv"].index(flag) + 1
                require(expected["argv"][position] == old, "Unexpected original migration baseline")
                expected["argv"][position] = new
        require(expected == after, f"Unregistered stage change in corrected manifest: {after['id']}")
    recovery = read(args.recovery)
    require(recovery["runtime_commit"] == SOURCES[CANDIDATE]["runtime_commit"]
            and recovery["source_sha256"] == SOURCES[CANDIDATE]["source_sha256"],
            "Recovery identifies a different candidate")
    require(hashlib.sha256(first_bytes).hexdigest() == recovery["original_checkpoint_sha256"],
            "The preserved failed checkpoint changed")
    require(first["stages"].get("upgrade-synthetic") == recovery["failed_stage_record"]
            and recovery["failed_stage_record"]["status"] == "failed", "Original failure record changed")
    first_ids = [stage["id"] for stage in corrected["stages"][:11]]
    second_ids = [stage["id"] for stage in corrected["stages"][11:]]
    require(first_ids == recovery["retained_completed_stages"] and second_ids == recovery["continuation_stages"],
            "Recovery stage lineage differs")
    require(not first_outputs.keys() & second_outputs.keys(), "Recovery checkpoints overlap output paths")
    chains = [{"role": "original run: eleven completed stages and preserved migration failure",
               "state": first, "bytes": first_bytes, "stage_ids": first_ids},
              {"role": "corrected five-stage cost continuation", "state": second,
               "bytes": second_bytes, "stage_ids": second_ids}]
    return corrected, chains, {**first_outputs, **second_outputs}, recovery


def source_record(engine, label):
    expected = SOURCES[label]
    before = engine.get("source_sha256_before", engine.get("source_sha256"))
    require(before == engine.get("source_sha256_after") == expected["source_sha256"],
            f"Unexpected or changed source for {label}")
    provenance = engine["source_provenance"]
    require(not provenance["source_dirty"] and provenance["commit_identifies_source"],
            f"Source provenance does not identify clean runtime bytes for {label}")
    return {"label": label, **expected, "source_sha256_before": before,
            "source_sha256_after": engine["source_sha256_after"], "source_provenance": provenance}


def indexed(rows, description):
    result = {row["id"]: row for row in rows}
    require(len(result) == len(rows), f"Duplicate query IDs in {description}")
    return result


def changes(old, new, ids):
    require(old.keys() == new.keys(), "Paired query ID populations differ")
    require(set(ids) <= old.keys(), "Requested cohort contains missing query IDs")
    ids = sorted(ids)
    fields = ("category", "project", "answerable", "required_evidence")
    annotation_gains = annotation_losses = 0
    for identity in ids:
        a, b = old[identity], new[identity]
        require(all(a[key] == b[key] for key in fields), f"Paired annotation differs: {identity}")
        require(len(a["evidence_ranks"]) == len(b["evidence_ranks"]) == a["required_evidence"],
                f"Evidence-rank count differs: {identity}")
        annotation_gains += sum(x is None and y is not None for x, y in zip(a["evidence_ranks"], b["evidence_ranks"]))
        annotation_losses += sum(x is not None and y is None for x, y in zip(a["evidence_ranks"], b["evidence_ranks"]))
    gained = [identity for identity in ids if new[identity]["complete"] and not old[identity]["complete"]]
    lost = [identity for identity in ids if old[identity]["complete"] and not new[identity]["complete"]]
    return {
        # Retain the first assessment's count-change convention for these keys.
        "evidence_gained": sum(max(0, new[i]["matched_evidence"] - old[i]["matched_evidence"]) for i in ids),
        "evidence_lost": sum(max(0, old[i]["matched_evidence"] - new[i]["matched_evidence"]) for i in ids),
        "complete_queries_gained": len(gained), "complete_queries_lost": len(lost),
        "complete_query_gain_ids": gained, "complete_query_loss_ids": lost,
        "quality_changed_query_ids": [i for i in ids if (old[i]["matched_evidence"], old[i]["complete"]) !=
                                      (new[i]["matched_evidence"], new[i]["complete"])],
        "annotation_evidence_gained": annotation_gains,
        "annotation_evidence_lost": annotation_losses,
    }


def paired(name, *, baseline=BASELINE, role, cohorts=None, report=None):
    report = report if report is not None else read(f"benchmarks/results/{name}.json.gz")
    require(report["validation"]["passed"], f"Paired report failed: {name}")
    require(len(report["engines"]) == 2, f"Expected two paired engines: {name}")
    old, new = report["engines"]
    require((old["label"], new["label"]) == (baseline, CANDIDATE), f"Unexpected pair labels: {name}")
    require(validation_status([old, new])["passed"], f"Recorded source/budget invariant failed: {name}")
    require(old["dataset"]["sha256"] == new["dataset"]["sha256"] == report["dataset"]["sha256"],
            f"Paired dataset fingerprints differ: {name}")
    result = {"artifact": f"{name}.json.gz", "dataset": report["dataset"], "population_role": role,
              "sources": [source_record(old, baseline), source_record(new, CANDIDATE)], "budgets": []}
    configurations = [{c["budget_chars"]: c for c in engine["configurations"]} for engine in (old, new)]
    require(set(configurations[0]) == set(configurations[1]) == {2000, 8000}, f"Unexpected character caps: {name}")
    for cap in sorted(configurations[0]):
        a, b = (config[cap] for config in configurations)
        aa, bb = (indexed(config["query_results"], name) for config in (a, b))
        require(len(aa) == report["dataset"]["queries"], f"Missing query records: {name}")
        for label, ids in (cohorts or {"all": set(aa)}).items():
            delta = changes(aa, bb, ids)
            result["budgets"].append({"cohort": label, "budget_chars": cap,
                "old": summarize_rows([aa[i] for i in sorted(ids)]),
                "new": summarize_rows([bb[i] for i in sorted(ids)]), **delta,
                "latency_scope": "whole measured population, not a separately timed cohort",
                "old_latency": a["latency"], "new_latency": b["latency"]})
    result["categories"] = {str(c["budget_chars"]): c["by_category"] for c in new["configurations"]}
    result["baseline_categories"] = {str(c["budget_chars"]): c["by_category"] for c in old["configurations"]}
    return result


def native_comparisons(report, public_hash):
    require(report["validation"]["passed"], "Native component report failed validation")
    require(validation_status(report["engines"])["passed"], "Native source/budget invariant failed")
    by_selector = {engine["engine_selector"]: engine for engine in report["engines"]}
    require(len(by_selector) == len(report["engines"]) == 4, "Expected four unique native components")
    require(set(by_selector) == {"baseline", "candidate", "billion-context", "ai-memory-hybrid"},
            "Unexpected native component selection")
    for selector, label in (("baseline", BASELINE), ("candidate", CANDIDATE)):
        require(by_selector[selector]["label"] == label, f"Incorrect native label: {selector}")
        source_record(by_selector[selector]["metadata"], label)
    configurations = {}
    for selector, engine in by_selector.items():
        require(engine["dataset"]["sha256"] == public_hash, "Native and paired datasets differ")
        configurations[selector] = {(c["tokenizer"], c["budget_tokens"]): c for c in engine["packed_configurations"]}
        require(set(configurations[selector]) == {(name, cap) for name in ("cl100k_base", "o200k_base")
                                                 for cap in (512, 1024, 2048)}, "Missing native token settings")
    comparisons = []
    baseline_comparisons = []
    for selector in ("baseline", "billion-context", "ai-memory-hybrid"):
        for (tokenizer, cap), candidate in configurations["candidate"].items():
            other = configurations[selector][tokenizer, cap]
            a, b = candidate["metrics"], other["metrics"]
            before, after = (indexed(config["query_results"], f"native {selector}") for config in (other, candidate))
            item = {"competitor": by_selector[selector]["label"], "tokenizer": tokenizer, "token_budget": cap,
                "evidence_recall_at_least_equal": a["evidence_recall"] >= b["evidence_recall"],
                "complete_evidence_at_least_equal": a["complete_evidence_rate"] >= b["complete_evidence_rate"],
                "mean_common_context_tokens_lower": a["mean_context_tokens"][tokenizer] < b["mean_context_tokens"][tokenizer],
                "candidate_evidence_recall": a["evidence_recall"], "competitor_evidence_recall": b["evidence_recall"],
                "candidate_complete_evidence_rate": a["complete_evidence_rate"],
                "competitor_complete_evidence_rate": b["complete_evidence_rate"],
                "candidate_mean_context_tokens": a["mean_context_tokens"][tokenizer],
                "competitor_mean_context_tokens": b["mean_context_tokens"][tokenizer],
                **changes(before, after, set(before)),
                "latency_superiority": "not established by common-context quality; see separately named timing boundaries",
                "generated_answer_superiority": "not measured"}
            (baseline_comparisons if selector == "baseline" else comparisons).append(item)
    engines = []
    for engine in report["engines"]:
        trimmed = {key: value for key, value in engine.items() if key not in ("native_query_costs", "packed_configurations")}
        trimmed["packed_configurations"] = [{key: value for key, value in config.items() if key != "query_results"}
                                            for config in engine["packed_configurations"]]
        engines.append(trimmed)
    return engines, comparisons, baseline_comparisons


def plot_sources():
    def version(key, name, artifact, side, tick_label):
        return {"key": key, "name": name, "artifact": PREFIX + artifact + ".json.gz",
                "side": side, "tick_label": tick_label}
    return {
        "primary_pair": PREFIX + "public-expanded.json.gz", "cohort": "all_1015",
        "versions": [version("main", "Main v0.2.1", "main-expanded", "old", "Main\nv0.2.1"),
                     version("preserved", "Preserved v0.3", "preserved-expanded", "old", "Preserved\nv0.3"),
                     version("first-round", "First round 6f", "public-expanded", "old", "First round\n6f52990"),
                     version("candidate", "Score-aware", "public-expanded", "new", "Score-aware")],
        "component_names": {"candidate": "AI-Memory-Book score-aware", "billion-context": "billion-context kernel",
                            "ai-memory-hybrid": "ai-memory local hybrid"},
        "output_prefix": "docs/assets/recall-score-quality-costs",
    }


def assess(manifest, verified):
    regression = read(f"benchmarks/results/{PREFIX}public-regression.json.gz")
    expanded = read(f"benchmarks/results/{PREFIX}public-expanded.json.gz")
    previous = set(indexed(regression["engines"][0]["configurations"][0]["query_results"], "public regression"))
    all_ids = set(indexed(expanded["engines"][0]["configurations"][0]["query_results"], "public expanded"))
    require(len(previous) == 256 and len(all_ids) == 1015 and previous <= all_ids,
            "Public cohort identity/counts differ from the registered plan")
    cohorts = {"previous_256": previous, "additional_759": all_ids - previous, "all_1015": all_ids}
    pairs = []
    for seed in (61, 211, 509, 883, 1297):
        role = ("development" if seed == 61 else "previously observed regression" if seed in (211, 509)
                else "reserved before second-round results; shared synthetic templates")
        pairs.append(paired(f"{PREFIX}synthetic-{seed}", role=role))
    pairs.append(paired(PREFIX + "public-development", role="development"))
    pairs.append(paired(PREFIX + "public-regression", role="previously observed public regression", report=regression))
    pairs.append(paired(PREFIX + "public-expanded", role="previously observed public regression; shared conversations",
                        cohorts=cohorts, report=expanded))
    for suffix, label in (("preserved-expanded", "preserved-v0.3"), ("main-expanded", "main-v0.2.1")):
        pairs.append(paired(PREFIX + suffix, baseline=label, role="separate historical baseline; observed public regression",
                            cohorts=cohorts))
    primary = next(pair for pair in pairs if pair["artifact"] == PREFIX + "public-expanded.json.gz")
    for pair in pairs:
        if not pair["artifact"].endswith("-expanded.json.gz"):
            continue
        require(pair["dataset"]["sha256"] == primary["dataset"]["sha256"], "Expanded paired populations differ")
        for first, second in zip(primary["budgets"], pair["budgets"]):
            require((first["cohort"], first["budget_chars"]) == (second["cohort"], second["budget_chars"])
                    and first["new"] == second["new"], "Candidate quality/context differs between baseline comparisons")

    native = read(f"benchmarks/results/{PREFIX}components-public.json.gz")
    engines, comparisons, native_baseline = native_comparisons(native, primary["dataset"]["sha256"])
    preflight = read(f"benchmarks/results/{PREFIX}preflight.json")
    require(preflight["validation"]["passed"] and preflight["unattainable_labels"] == 0,
            "Source-evidence preflight did not pass")
    require(len(preflight["records"]) == 16, "Every one of eight corpora must pass for both sources")
    for record in preflight["records"]:
        require(record["label"] in (BASELINE, CANDIDATE), "Unexpected preflight label")
        source_record(record, record["label"])

    upgrades, upgrade_details = {}, {}
    for name in ("synthetic", "public"):
        report = read(f"benchmarks/reports/{PREFIX}upgrade-{name}.json")
        summary = report["summary"]
        source_record(report["baseline"]["engine"], "preserved-v0.3")
        for trial in report["trials"]:
            source_record(trial["engine"], CANDIDATE)
        require(summary["schema_before"] == 2 and summary["schema_after"] == [3, 3, 3],
                "The corrected upgrade comparison requires preserved schema 2 to candidate schema 3")
        for key in ("source_tables_preserved", "page_ids_content_source_refs_preserved", "cache_invalidated", "reopen_unchanged"):
            require(summary[key] is True, f"Upgrade invariant failed: {name} {key}")
        upgrades[name] = summary
        upgrade_details[name] = {"artifact": f"{PREFIX}upgrade-{name}.json", "dataset": report["dataset"],
            "operation": "preserved v0.3 schema 2 to score-aware schema 3 migration and cache invalidation",
            "baseline_source": source_record(report["baseline"]["engine"], "preserved-v0.3"),
            "candidate_source": source_record(report["trials"][0]["engine"], CANDIDATE)}

    mcp = {name: read(f"benchmarks/reports/{PREFIX}mcp-{name}.summary.json") for name in ("synthetic", "public")}
    mcp_sources = defaultdict(set)
    for name, report in mcp.items():
        require(len(report["engines"]) == 4 and {e["label"] for e in report["engines"]} == set(SOURCES),
                f"Expected all four MCP versions: {name}")
        require(report["fixture"]["queries"] == (1015 if name == "public" else 42), "MCP query count differs")
        if name == "public":
            require(report["fixture"]["sha256"] == primary["dataset"]["sha256"], "MCP public population differs")
        for engine in report["engines"]:
            detail = engine["same_evidence_detail_comparison"]
            require(detail["all_contexts_identical"] is True, "Compact and detailed contexts differ")
            require(detail["queries"] == (0 if engine["label"] == "main-v0.2.1" else report["fixture"]["queries"]),
                    "Missing compact/detailed checks")
            counts = engine["query_pair_counts"]
            require(counts["query_rows"] == report["fixture"]["queries"], "MCP query IDs were dropped")
            require(counts["distinct_query_project_pairs"] + counts["duplicate_query_project_rows"] == counts["query_rows"],
                    "MCP duplicate-pair accounting differs")
            require(counts["duplicate_pair_cache_clears"] == 3 * counts["duplicate_query_project_rows"],
                    "MCP repeated pairs were not reset on every repetition")
            mcp_sources[engine["label"]].add(engine["engine_sha256"])
    require(all(len(values) == 1 for values in mcp_sources.values()), "MCP source fingerprint changed across workloads")

    selection = read("benchmarks/experiments/score-aware-fusion-selection.json")
    require(selection["acceptance_gate_passed"] is True and
            selection["adopted_runtime_source_sha256"] == SOURCES[CANDIDATE]["source_sha256"],
            "Selection record does not identify the measured candidate")
    return {
        "schema_version": 1,
        "status": "second frozen evaluation completed; universal lower-cost equal-or-better answer quality not established",
        "candidate_runtime_commit": SOURCES[CANDIDATE]["runtime_commit"],
        "candidate_source_sha256": SOURCES[CANDIDATE]["source_sha256"],
        "primary_baseline_runtime_commit": SOURCES[BASELINE]["runtime_commit"],
        "primary_baseline_source_sha256": SOURCES[BASELINE]["source_sha256"],
        "runtime_sources": {label: {**values, "mcp_source_sha256": next(iter(mcp_sources[label]))}
                            for label, values in SOURCES.items()},
        "completed_stages": len(manifest["stages"]), "completed_output_hashes_verified": True,
        "verified_outputs": verified,
        "public_cohort_sizes": {key: len(value) for key, value in cohorts.items()},
        "population_roles": {"development_synthetic_seeds": [61], "observed_synthetic_regression_seeds": [211, 509],
            "new_reserved_synthetic_seeds": [883, 1297], "public_verification": "all previously measured in the first round"},
        "paired_results": pairs, "native_components": engines, "common_context_comparisons": comparisons,
        "native_baseline_comparisons": native_baseline, "mcp": mcp, "upgrades": upgrades, "upgrade_details": upgrade_details,
        "preflight": {"source_corpus_checks": len(preflight["records"]), "unattainable_labels": 0,
                      "validation": preflight["validation"]},
        "development_selection_record": "../experiments/score-aware-fusion-selection.json",
        "development_selection": {key: selection[key] for key in ("acceptance_gate_passed", "formula", "controlled_fixture_result", "adoption_tests")},
        "plot_sources": plot_sources(),
        "validation": {"passed": True, "scope": "artifact/source/population/budget integrity, not achievement of the product goal"},
        "notes": [
            "Primary baseline is frozen first-round 6f52990. Preserved v0.3 and older main are separately named comparisons.",
            "The single formula was selected on development data. First-round public and synthetic 211/509 results were already known; 883/1297 were reserved before the second formal run.",
            "Additional public questions share conversations with the previous 256, and all public verification questions were evaluated in the first round.",
            "evidence_gained/lost retain first-round per-query matched-count deltas; annotation_evidence_gained/lost additionally reveal equal-count exchanges of individual annotations.",
            "MCP source hashes use paths relative to the repository; core source hashes use paths relative to the package. Their different hash values do not imply different bytes.",
            "The original schema-3-to-3 migration stage correctly failed its schema-increase guard. Corrected migration costs use preserved v0.3 schema 2 as baseline; no evaluator or runtime assertion was weakened.",
            "Common-page context and native tool response tokens are distinct surfaces. Native ai-memory reads follow search plus every mapped top-k page, not a minimum-read agent policy.",
            "Component timing boundaries differ and do not establish universal end-to-end speed superiority.",
            "Quality is exact source-evidence delivery, not generated-answer accuracy; claude-mem is unmeasured and no paid model calls or API keys were used.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmarks/recall_score_quality_manifest_v2.json")
    parser.add_argument("--original-manifest", type=Path, default=ROOT / "benchmarks/recall_score_quality_manifest.json")
    parser.add_argument("--continuation-manifest", type=Path, default=ROOT / "benchmarks/recall_score_cost_manifest.json")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / ".artifacts/score-quality-checkpoint.json")
    parser.add_argument("--continuation-checkpoint", type=Path, default=ROOT / ".artifacts/score-cost-checkpoint.json")
    parser.add_argument("--full-checkpoint", type=Path, help="A fresh completed run of the corrected full v2 manifest; bypass recovery mode")
    parser.add_argument("--recovery", type=Path, default=ROOT / "benchmarks/reports/recall-score-recovery.json")
    parser.add_argument("--output", type=Path, default=ROOT / f"benchmarks/results/{PREFIX}assessment.json")
    parser.add_argument("--durable-checkpoint", type=Path, default=ROOT / f"benchmarks/reports/{PREFIX}run-checkpoint.json")
    args = parser.parse_args()
    try:
        manifest, chains, verified, recovery = verify_execution(args)
        result = assess(manifest, verified)
        snapshots = []
        for index, chain in enumerate(chains):
            path = (args.durable_checkpoint if len(chains) == 1 else args.durable_checkpoint.with_name(
                PREFIX + ("original-run-checkpoint.json" if index == 0 else "cost-run-checkpoint.json")))
            atomic_write(path, chain["bytes"])
            snapshots.append({"role": chain["role"], "path": os.path.relpath(path, args.output.parent),
                "sha256": hashlib.sha256(chain["bytes"]).hexdigest(),
                "identity_sha256": digest(chain["state"]["identity"]),
                "completed_stages_used": chain["stage_ids"]})
        execution = {"mode": "single corrected run" if len(chains) == 1 else "eleven retained stages plus five-stage continuation",
            "completed_stage_count": len(manifest["stages"]), "checkpoints": snapshots,
            "corrected_manifest": os.path.relpath(args.manifest, args.output.parent),
            "corrected_manifest_file_sha256": file_hash(args.manifest),
            "runtime_and_source_identity_unchanged": True}
        if recovery is not None:
            execution["original_failed_stage"] = recovery["failed_stage_record"]
            execution["recovery_record"] = os.path.relpath(args.recovery, args.output.parent)
            checkpoint_bytes = (json.dumps({"schema_version": 1,
                "artifact_kind": "verified execution index; not a runner checkpoint", **execution,
                "verified_outputs": verified}, ensure_ascii=False, indent=2) + "\n").encode()
            atomic_write(args.durable_checkpoint, checkpoint_bytes)
            recovery = {**recovery, "status": "completed; eleven retained stages and five corrected continuation stages verified",
                        "completed_stage_count": len(manifest["stages"]), "completed_output_hashes_verified": True,
                        "runtime_and_source_identity_unchanged": True, "completed_checkpoints": snapshots,
                        "execution_index": os.path.relpath(args.durable_checkpoint, ROOT),
                        "execution_index_sha256": hashlib.sha256(checkpoint_bytes).hexdigest()}
        else:
            checkpoint_bytes = chains[0]["bytes"]
        result["execution"] = execution
        result["execution_checkpoint"] = os.path.relpath(args.durable_checkpoint, args.output.parent)
        result["execution_checkpoint_kind"] = ("exact complete runner checkpoint" if len(chains) == 1 else
                                                "verified index of two exact checkpoint snapshots; original run failed")
        result["execution_checkpoint_sha256"] = hashlib.sha256(checkpoint_bytes).hexdigest()
        atomic_write(args.output, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
        if recovery is not None:
            atomic_write(args.recovery, (json.dumps(recovery, ensure_ascii=False, indent=2) + "\n").encode())
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(f"Cannot assess incomplete or incompatible score-aware artifacts: {error}")
    comparisons = result["common_context_comparisons"]
    print(json.dumps({"assessment": str(args.output), "execution_checkpoint": str(args.durable_checkpoint),
        "completed_stages": result["completed_stages"], "execution_mode": result["execution"]["mode"],
        "verified_outputs": len(verified),
        "native_comparisons": len(comparisons),
        "native_quality_at_least_equal": sum(c["evidence_recall_at_least_equal"] and c["complete_evidence_at_least_equal"] for c in comparisons),
        "native_common_context_tokens_lower": sum(c["mean_common_context_tokens_lower"] for c in comparisons),
        "status": result["status"]}, indent=2))


if __name__ == "__main__":
    main()
