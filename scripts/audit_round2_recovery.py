"""Compare preserved first-run evidence with the fixed-candidate recovery.

Reads immutable Git objects only. It never invokes a retrieval engine, changes a
score, combines latency samples, or selects a run based on its outcome.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INITIAL_COMMIT = "150d37799098aa1fb1ddcebe5b42b18954adc035"
INITIAL_RUN = "43201620535-1"
RECOVERY_RUN = "43207732852-1"
RECOVERY_SOURCE = "cb64db805f8f822fee00cc453c523cfa06c2ce8f"
RECOVERY_BINDING = "39f18e8294a21d750d11ddc59e1bb309d409a067fd1b0974b78285f9834bbb82"
SHARED = ("export", "baseline-native", "candidate-native", "baseline-component", "candidate-component")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def raw_sha(value):
    return hashlib.sha256(value).hexdigest()


def blob(commit, path):
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "An immutable full Git commit is required")
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT)


def checkpoint(commit, run):
    path = "benchmarks/reports/round2-" + run + "-checkpoint.json"
    raw = blob(commit, path)
    value = json.loads(raw)
    require(value["run_id"] == run and value["host"]["id"] == run, "Checkpoint run/host differs")
    return value, {"commit": commit, "checkpoint_path": path, "checkpoint_sha256": raw_sha(raw)}


def report(commit, run, stage, cp):
    record = cp["stages"][stage]
    require(record["status"] == "completed" and record["exit_code"] == 0, "Shared stage incomplete: " + stage)
    prefix = "benchmarks/results/round2-" + run + "/" + stage
    files = {prefix + ext: blob(commit, prefix + ext) for ext in (".json.gz", ".summary.json")}
    hashes = {name: raw_sha(raw) for name, raw in files.items()}
    require(hashes == record["outputs"], "Published output hashes differ: " + stage)
    raw = gzip.decompress(files[prefix + ".json.gz"])
    full, summary = json.loads(raw), json.loads(files[prefix + ".summary.json"])
    projected = copy.deepcopy(full)
    projected.pop("timing_rows", None)
    projected.pop("attempt_states", None)
    for config in projected["configurations"]:
        config.pop("query_results", None)
    projected["full_report_sha256"] = raw_sha(raw)
    require(projected == summary, "Raw/summary projection differs: " + stage)
    require(full["stage"] == stage and full["host_id"] == run and full["validation"] == {"passed": True, "failures": []},
            "Shared report identity or validation differs")
    require(full["binding_sha256"] == cp["binding_sha256"] and full["plan_sha256"] == cp["plan_sha256"]
            and full["cohort_manifest_sha256"] == cp["cohort_manifest_sha256"], "Report protocol differs from checkpoint")
    return full, hashes


def key(row):
    return json.dumps(row.get("configuration", "search"), sort_keys=True), row.get("repetition", 0), row["id"]


def compare_rows(before, after):
    old, new = {key(row): row for row in before}, {key(row): row for row in after}
    require(len(old) == len(before) and len(new) == len(after) and old.keys() == new.keys(), "Distinct query/sample axes differ")
    differences = []
    for identity in sorted(old):
        left, right = old[identity], new[identity]
        if left != right:
            differences.append({"configuration": json.loads(identity[0]), "repetition": identity[1], "id": identity[2],
                "changed_fields": sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k)),
                "before_sha256": digest(left), "after_sha256": digest(right)})
    return {"comparisons": len(old), "differences": differences,
            "before_sha256": digest([old[k] for k in sorted(old)]), "after_sha256": digest([new[k] for k in sorted(new)])}


def audit(final_commit):
    old_cp, old_input = checkpoint(INITIAL_COMMIT, INITIAL_RUN)
    new_cp, new_input = checkpoint(final_commit, RECOVERY_RUN)
    require(old_cp["status"] == "failed" and new_cp["status"] == "complete-verified-snapshot"
            and new_cp["assessment_exit_code"] == 0, "Initial/recovery status differs")
    require(new_cp["source_commit"] == RECOVERY_SOURCE and new_cp["binding_sha256"] == RECOVERY_BINDING,
            "Unregistered recovery source or binding")
    final_prefix = "benchmarks/results/round2-" + RECOVERY_RUN + "/"
    assessed = {final_prefix + name: blob(final_commit, final_prefix + name) for name in ("assessment.json", "report.md")}
    require({name: raw_sha(raw) for name, raw in assessed.items()} == new_cp["assessment_outputs"],
            "Published strict assessment hashes differ")
    assessment = json.loads(assessed[final_prefix + "assessment.json"])
    require(assessment["status"] == "complete-verified-snapshot" and assessment["run_id"] == RECOVERY_RUN
            and assessment["source_commit"] == RECOVERY_SOURCE, "Strict assessment identity/status differs")
    require(all(old_cp[k] == new_cp[k] for k in ("plan_sha256", "cohort_manifest_sha256")), "Frozen selection or plan changed")
    require(len(new_cp["stages"]) == 10 and all(r["status"] == "completed" for r in new_cp["stages"].values()),
            "Recovery is not the complete registered matrix")
    results = {}
    for stage in SHARED:
        old, old_files = report(INITIAL_COMMIT, INITIAL_RUN, stage, old_cp)
        new, new_files = report(final_commit, RECOVERY_RUN, stage, new_cp)
        corpus_fields = ("dataset", "documents_sha256", "diagnostics_sha256", "originals_sha256", "stats", "source_sha256", "evidence_attainability")
        corpus_before = {k: old["frozen_corpus"][k] for k in corpus_fields}
        corpus_after = {k: new["frozen_corpus"][k] for k in corpus_fields}
        item = {"initial_files_sha256": old_files, "recovery_files_sha256": new_files,
            "frozen_corpus_identical": corpus_before == corpus_after,
            "frozen_corpus_before_sha256": digest(corpus_before), "frozen_corpus_after_sha256": digest(corpus_after),
            "frozen_corpus_differences": {k: {"before_sha256": digest(corpus_before[k]), "after_sha256": digest(corpus_after[k])}
                                          for k in corpus_fields if corpus_before[k] != corpus_after[k]},
            "originals_snapshot_before_sha256": corpus_before["originals_sha256"],
            "originals_snapshot_after_sha256": corpus_after["originals_sha256"],
            "configurations": []}
        require(len(old["configurations"]) == len(new["configurations"]), "Configuration count differs")
        for left, right in zip(old["configurations"], new["configurations"], strict=True):
            axes = {k: left[k] for k in ("budget_chars", "tokenizer", "budget_tokens") if k in left}
            require(axes == {k: right[k] for k in axes}, "Configuration axes or order differ")
            rows = compare_rows(left["query_results"], right["query_results"])
            item["configurations"].append({**axes, "query_rows": rows,
                "metrics_identical": left["metrics"] == right["metrics"],
                "groups_identical": left["by_group"] == right["by_group"],
                "before_metrics": left["metrics"], "after_metrics": right["metrics"]})
        if stage.endswith("native"):
            # Native score rows contain no timing: compare every field in every
            # query/configuration and all repeated evidence/hash projections.
            remove = {"elapsed_ms"}
        else:
            # Whole native envelopes may contain timing metadata. Only native
            # identities/top-five positions and mapping counts are compared.
            keep = {"id", "repetition", "status", "hit_ids", "native_hit_ids", "native_result_id_sha256", "unmapped_native_hits"}
            remove = set(old["timing_rows"][0]) - keep if old["timing_rows"] else set()
        project = lambda rows: [{k: v for k, v in row.items() if k not in remove} for row in rows]
        item["repeated_non_timing_samples"] = compare_rows(project(old["timing_rows"]), project(new["timing_rows"]))
        results[stage] = item
    differences = sum(len(c["query_rows"]["differences"]) for r in results.values() for c in r["configurations"])
    sample_differences = sum(len(r["repeated_non_timing_samples"]["differences"]) for r in results.values())
    aggregate_differences = sum(not r["frozen_corpus_identical"] for r in results.values()) + sum(
        not c["metrics_identical"] or not c["groups_identical"] for r in results.values() for c in r["configurations"])
    return {"schema_version": 1, "status": "identical" if not (differences or sample_differences or aggregate_differences) else "completed_with_differences",
        "initial": old_input, "recovery": new_input, "shared_stages": list(SHARED), "stages": results,
        "query_configuration_comparisons": sum(c["query_rows"]["comparisons"] for r in results.values() for c in r["configurations"]),
        "repeated_sample_comparisons": sum(r["repeated_non_timing_samples"]["comparisons"] for r in results.values()),
        "query_row_differences": differences, "sample_differences": sample_differences, "aggregate_differences": aggregate_differences,
        "timings_combined": False, "run_selected_by_score_or_latency": False,
        "interpretation": "Equality only covers five shared completed stages. The initial run did not complete the external or semantic stages. Timings, resource samples, model/preparation state and whole native payload hashes are deliberately excluded; final performance uses only the complete recovery host. Differences, if any, remain unresolved evidence rather than a basis for selecting a run.",
        "database_snapshot_boundary": "source_snapshot in benchmarks/semantic_eval.py hashes SELECT * from projects, chapters, sessions, turns, sections and pages. The frozen runtime writes current ingest timestamps to project/chapter/session records. Fresh runs can therefore have different originals snapshot hashes even when all exported pages and scored evidence agree. Public reports do not contain the original databases, so this audit cannot establish that timestamps are the only cause of any snapshot difference; the differing hashes are retained."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-commit", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/reports/round2-recovery-crossrun-audit.json")
    args = parser.parse_args()
    result = audit(args.recovery_commit)
    result["audit_script_sha256"] = raw_sha(Path(__file__).read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "query_configuration_comparisons", "repeated_sample_comparisons", "query_row_differences", "sample_differences", "aggregate_differences")}))
    return 0 if result["status"] == "identical" else 2


if __name__ == "__main__":
    raise SystemExit(main())
