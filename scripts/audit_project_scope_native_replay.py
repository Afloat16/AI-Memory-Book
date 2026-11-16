#!/usr/bin/env python3
"""Independently audit the frozen 80-case native engineering replay.

This reader imports neither the evaluator nor MemoryBook. It checks the complete
case matrix, source spans, quality fields, recorded digests, and byte-equivalent
JSON responses. It supports plain files and losslessly compressed .gz files.
The fixed-consumer truth table is valid only for the evaluator digest below:
each family's first vector distinguishes its policies, and the remaining
registered boundary vectors pass for every non-abstaining policy.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess


EVALUATOR_SHA256 = "3d1c53ef016a7143c86cf1326f2bf5b5cf7260863e91225d9a7e09a9773cdc6e"
BASELINE_COMMIT = "0572e65e198503f55ad4117619606b17a4c67540"
CANDIDATE_COMMIT = "cf51473e841a3a38df7c7c857cf51e0e14eb1861"
EXECUTION_LOCAL_COMMIT = "e1fb65e7898153206e3928d3a181b74eeb38e18a"
EXECUTION_TREE = "4ced86d8c83275962c8700cbe5827f2b90adab4e"
BACKENDS = ("book", "flat", "no_memory", "recent_history")
BUDGETS = (1200, 2400)
POLICIES = {
    "routing": ("edge_policy", ("reject_negative", "bellman_ford"), 3),
    "ranking": ("tie_policy", ("stable_input", "id_ascending"), 3),
    "splitting": ("split_policy", ("row_modulo", "whole_group", "chronological"), 2),
    "attention": ("all_masked_policy", ("uniform", "zeros"), 3),
}
RESPONSE_EXCLUSIONS = frozenset({"latency_ms", "cache_hit"})
TIMING_SUMMARY_FIELDS = frozenset({"retrieval_p50_ms", "retrieval_p95_ms"})


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Audit:
    def __init__(self):
        self.checks = 0
        self.failures = []

    def check(self, condition, location, kind):
        self.checks += 1
        if not condition:
            self.failures.append({"location": location, "kind": kind})

    def equal(self, actual, expected, location, kind):
        self.check(canonical(actual) == canonical(expected), location, kind)


def read_bytes(path):
    compressed = Path(str(path) + ".gz")
    if path.exists():
        raw = path.read_bytes()
        if compressed.exists() and gzip.decompress(compressed.read_bytes()) != raw:
            raise ValueError(f"plain and compressed files differ: {path}")
        return raw
    return gzip.decompress(compressed.read_bytes())


def expected_score(case, response, sources, budget):
    """Derive every saved score field from the visible sources and response."""
    errors = []
    context = response["context"]
    for index, hit in enumerate(response["results"]):
        text = hit["text"]
        covered = set()
        if text not in context:
            errors.append(f"hit {index}: snippet absent from context")
        if not hit.get("source_refs"):
            errors.append(f"hit {index}: missing source references")
        for ref in hit.get("source_refs", []):
            identity = (ref.get("project"), ref.get("session_id"), ref.get("turn_index"))
            original = sources.get(identity)
            low, high = ref.get("turn_start"), ref.get("turn_end")
            if identity[0] != case["project"]:
                errors.append(f"hit {index}: cross-project source")
            if (original is None or type(low) is not int or type(high) is not int
                    or not 0 <= low < high <= len(original)):
                errors.append(f"hit {index}: invalid original source span")
                continue
            fragment = original[low:high]
            position = text.find(fragment)
            if position < 0 or ref.get("end", 0) - ref.get("start", 0) != high - low:
                errors.append(f"hit {index}: source slice does not match snippet")
            else:
                covered.update(range(position, position + len(fragment)))
        if any(index not in covered and char != "…" and not char.isspace()
               for index, char in enumerate(text)):
            errors.append(f"hit {index}: unsupported snippet characters")

    def rank(evidence):
        quote = evidence["quote"]
        if quote not in context:
            return None
        for position, hit in enumerate(response["results"], 1):
            if quote not in hit["text"]:
                continue
            for ref in hit.get("source_refs", []):
                if (ref.get("project"), ref.get("session_id")) != (case["project"], evidence["session_id"]):
                    continue
                original = sources.get((case["project"], evidence["session_id"], ref.get("turn_index")), "")
                low, high = ref.get("turn_start", 0), ref.get("turn_end", 0)
                if type(low) is int and type(high) is int and quote in original[low:high]:
                    return position
        return None

    ranks = [rank(evidence) for evidence in case["required"]]
    stale = [rank(evidence) for evidence in case["stale"]]
    matched = sum(value is not None for value in ranks)
    result = {
        "answerable": bool(ranks), "required_evidence": len(ranks),
        "matched_evidence": matched, "complete_evidence": bool(ranks) and matched == len(ranks),
        "evidence_ranks": ranks, "stale_evidence_ranks": stale,
        "stale_only": any(value is not None for value in stale) and matched == 0,
        "missing_evidence_nonempty_context": not ranks and bool(context),
        "context_chars": len(context), "within_budget": len(context) <= budget,
        "source_errors": errors, "returned_blocks": len(response["results"]),
    }
    if case["consumer_family"]:
        field, allowed, count = POLICIES[case["consumer_family"]]
        pattern = re.compile(r"\b" + re.escape(field) + r"\s*=\s*(" + "|".join(allowed) + r")\b")
        choices = [(hit.get("created_at", ""), -index, match.group(1))
                   for index, hit in enumerate(response["results"]) if hit["text"] in context
                   for match in pattern.finditer(hit["text"])]
        selected = None
        if choices:
            choose = min if re.search(r"\boriginal\b|最初", case["query"], re.IGNORECASE) else max
            selected = choose(choices)[2]
        if selected is None:
            consumer = {"selected_policy": None, "checks": 0, "passed": 0,
                        "all_passed": False, "abstained": True}
        else:
            # Independent truth table of the fixed, hash-bound input vectors.
            passed = [selected == case["consumer_expected_policy"]] + [True] * (count - 1)
            consumer = {"selected_policy": selected, "checks": count, "passed": sum(passed),
                        "all_passed": all(passed), "abstained": False, "per_check_passed": passed}
        result["fixed_consumer"] = consumer
    return result


def summary(rows):
    result = []
    for budget, backend in sorted({(row["budget_chars"], row["backend"]) for row in rows}):
        selected = [row for row in rows if (row["budget_chars"], row["backend"]) == (budget, backend)]
        scores = [row["score"] for row in selected]
        answerable = [score for score in scores if score["answerable"]]
        consumers = [score["fixed_consumer"] for score in scores if "fixed_consumer" in score]
        required = sum(score["required_evidence"] for score in scores)
        result.append({
            "backend": backend, "budget_chars": budget, "cases": len(selected),
            "answerable_cases": len(answerable),
            "evidence_recall": sum(score["matched_evidence"] for score in scores) / required if required else None,
            "complete_evidence_rate": sum(score["complete_evidence"] for score in answerable) / len(answerable) if answerable else None,
            "fixed_consumer_cases": len(consumers),
            "fixed_consumer_all_checks_pass_rate": sum(value["all_passed"] for value in consumers) / len(consumers) if consumers else None,
            "stale_only_cases": sum(score["stale_only"] for score in scores),
            "missing_evidence_nonempty_cases": sum(score["missing_evidence_nonempty_context"] for score in scores),
            "budget_violations": sum(not score["within_budget"] for score in scores),
            "source_validation_failures": sum(bool(score["source_errors"]) for score in scores),
            "mean_context_chars": statistics.mean(score["context_chars"] for score in scores),
            "retrieval_samples": sum(len(row["latency_ms"]) for row in selected),
            "repeat_output_changes": sum(not row["repeat_outputs_equal"] for row in selected),
        })
    return result


def quality_summary(rows):
    result = []
    for cell in summary(rows):
        selected = [row for row in rows if row["backend"] == cell["backend"] and row["budget_chars"] == cell["budget_chars"]]
        scores = [row["score"] for row in selected]
        result.append({**cell,
            "evidence_spans_recovered": sum(score["matched_evidence"] for score in scores),
            "evidence_spans_required": sum(score["required_evidence"] for score in scores),
            "complete_evidence_cases": sum(score["complete_evidence"] for score in scores),
            "fixed_policy_passes": sum(score.get("fixed_consumer", {}).get("all_passed", False) for score in scores),
            "incomplete_evidence_case_ids": [row["case_id"] for row in selected if row["score"]["answerable"] and not row["score"]["complete_evidence"]],
        })
    return result


def verify_run(audit, folder, commit, repo):
    raw_bytes = {name: read_bytes(folder / name) for name in ("dataset.json", "raw.jsonl", "report.json")}
    dataset = json.loads(raw_bytes["dataset.json"])
    report = json.loads(raw_bytes["report.json"])
    rows = [json.loads(line) for line in raw_bytes["raw.jsonl"].splitlines() if line]
    label = folder.name
    audit.equal(report["status"], "completed", label, "completed")
    audit.equal(report["evaluator_sha256"], EVALUATOR_SHA256, label, "registered_evaluator")
    audit.equal(report["dataset_sha256"], digest(canonical(dataset)), label, "dataset_digest")
    audit.check(report["runtime_unchanged"] and report["evaluator_unchanged"], label, "frozen_during_execution")
    audit.equal(report["runtime"]["sha256"], report["runtime_final_sha256"], label, "final_runtime_identity")
    audit.equal(report["settings"], {"budgets_chars": list(BUDGETS), "repeats": 1, "noise_per_step": 2,
                "result_cache": False, "segmentation": "adaptive", "limit": 5}, label, "fixed_configuration")
    git_paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit, "--", "src/memory_book"], cwd=repo, text=True).splitlines()
    git_files = {str(Path(name).relative_to("src/memory_book")): digest(subprocess.check_output(
        ["git", "show", f"{commit}:{name}"], cwd=repo)) for name in git_paths if name.endswith(".py")}
    audit.equal(report["runtime"]["files"], git_files, label, "runtime_matches_source_commit")
    audit.equal(report["runtime"]["sha256"], digest(canonical(git_files)), label, "runtime_map_digest")
    evaluator = subprocess.check_output(["git", "show", f"{commit}:benchmarks/engineering_workflow.py"], cwd=repo)
    audit.equal(digest(evaluator), EVALUATOR_SHA256, label, "unchanged_committed_evaluator")
    cases, snapshots, visible = {}, {}, {}
    for step in dataset:
        for session in step["sessions"]:
            visible[(session["project"], session["session_id"], 0)] = "\n\n".join(
                f"{message['role'].upper()}: {message['content']}" for message in session["messages"])
        snapshots[step["checkpoint"]] = dict(visible)
        for case in step["cases"]:
            audit.check(case["id"] not in cases, label, "unique_case")
            cases[case["id"]] = case
    audit.equal(len(cases), 80, label, "fixed_case_count")
    expected = {(case, backend, budget) for case in cases for backend in BACKENDS for budget in BUDGETS}
    keyed = {}
    for row in rows:
        key = (row["case_id"], row["backend"], row["budget_chars"])
        location = label + "/" + "/".join(map(str, key))
        audit.check(key not in keyed, location, "unique_raw_row")
        keyed[key] = row
        case = cases[row["case_id"]]
        for field in ("category", "checkpoint", "query", "project"):
            audit.equal(row[field], case[field], location, "case_metadata_" + field)
        audit.equal(row["visible_sessions"], len(snapshots[case["checkpoint"]]), location, "chronological_snapshot_size")
        recalculated = expected_score(case, row["response"], snapshots[case["checkpoint"]], row["budget_chars"])
        audit.equal(row["score"], recalculated, location, "complete_score_recomputation")
        audit.check(not recalculated["source_errors"], location, "source_integrity")
        audit.check(recalculated["within_budget"], location, "context_budget")
        stable = {key: value for key, value in row["response"].items() if key != "latency_ms"}
        audit.equal(row["output_sha256"], [digest(canonical(stable))], location, "recorded_output_digest")
        audit.equal(len(row["latency_ms"]), 1, location, "single_execution")
        audit.equal(row["repeat_outputs_equal"], True, location, "single_execution_flag")
    audit.equal(sorted(keyed), sorted(expected), label, "complete_matrix")
    def quality_only(cells):
        return [{key: value for key, value in cell.items() if key not in TIMING_SUMMARY_FIELDS} for cell in cells]
    audit.equal(quality_only(report["summary"]), summary(rows), label, "aggregate_quality")
    audit.equal(sorted(report["by_category"]), sorted({row["category"] for row in rows}), label, "category_inventory")
    for category, cells in report["by_category"].items():
        audit.equal(quality_only(cells), summary([row for row in rows if row["category"] == category]),
                    label + "/" + category, "category_quality")
    return {"dataset": dataset, "report": report, "rows": rows, "keyed": keyed,
            "files": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in raw_bytes.items()}}


def git_object_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{40}", value) is None:
        raise ValueError("source identities must be full 40-character hexadecimal Git object IDs")
    return value.lower()


def candidate_identity(repo, *, candidate_commit=None, candidate_tree=None, execution_local_commit=None):
    supplied = (candidate_commit, candidate_tree, execution_local_commit)
    explicit = any(value is not None for value in supplied)
    if explicit and not all(value is not None for value in supplied):
        raise ValueError("candidate_commit, candidate_tree and execution_local_commit must be provided together")
    candidate_commit, candidate_tree, execution_local_commit = map(
        git_object_id, supplied if explicit else (CANDIDATE_COMMIT, EXECUTION_TREE, EXECUTION_LOCAL_COMMIT))
    published_tree = subprocess.check_output(["git", "rev-parse", "--verify", candidate_commit + "^{tree}"],
                                             cwd=repo, text=True).strip()
    if explicit:
        # Overrides are caller-supplied registrations, never identities learned
        # from the reports being checked. Require both actual commit objects
        # and their complete trees before reading any saved results.
        for label, commit in (("candidate", candidate_commit), ("execution", execution_local_commit)):
            actual = subprocess.check_output(["git", "rev-parse", "--verify", commit + "^{commit}"],
                                             cwd=repo, text=True).strip()
            if actual != commit:
                raise ValueError(f"{label} identity must name the exact commit object")
            tree = (published_tree if commit == candidate_commit else subprocess.check_output(
                ["git", "rev-parse", "--verify", commit + "^{tree}"], cwd=repo, text=True).strip())
            if tree != candidate_tree:
                raise ValueError(f"{label} Git tree differs from the explicitly registered candidate tree")
    return {"execution_local_commit": execution_local_commit,
            "recorded_execution_tree": candidate_tree, "published_commit": candidate_commit,
            "published_tree": published_tree, "same_tree": published_tree == candidate_tree,
            "reproduction": (
                "The explicitly registered published and execution commits are read from Git and must have the supplied tree; reports cannot supply source identities."
                if explicit else
                "Only published commits are read by this auditor; the local execution commit is retained as provenance and need not exist in a fresh checkout.")}


def run(root, repo, *, candidate_commit=None, candidate_tree=None, execution_local_commit=None):
    provenance = candidate_identity(repo, candidate_commit=candidate_commit, candidate_tree=candidate_tree,
                                    execution_local_commit=execution_local_commit)
    candidate_commit = provenance["published_commit"]
    audit = Audit()
    audit.equal(provenance["published_tree"], provenance["recorded_execution_tree"],
                "candidate", "published_tree_matches_recorded_execution_tree")
    runs = {"baseline": verify_run(audit, root / "native-baseline", BASELINE_COMMIT, repo),
            "candidate": verify_run(audit, root / "native-candidate", candidate_commit, repo)}
    baseline, candidate = runs["baseline"], runs["candidate"]
    audit.equal(baseline["dataset"], candidate["dataset"], "paired", "identical_workload")
    audit.equal(baseline["files"]["dataset.json"], candidate["files"]["dataset.json"], "paired", "identical_workload_bytes")
    counts, pairs = Counter(), []
    for key in sorted(baseline["keyed"].keys() & candidate["keyed"].keys()):
        left, right = baseline["keyed"][key], candidate["keyed"][key]
        stable = [{field: value for field, value in row["response"].items() if field not in RESPONSE_EXCLUSIONS}
                  for row in (left, right)]
        equal = canonical(stable[0]) == canonical(stable[1])
        audit.check(equal, "/".join(map(str, key)), "entire_nontiming_response_equivalence")
        audit.equal(left["score"], right["score"], "/".join(map(str, key)), "entire_score_equivalence")
        counts[(key[1], "compared")] += 1
        counts[(key[1], "equal")] += int(equal)
        pairs.append({"case_id": key[0], "backend": key[1], "budget_chars": key[2],
                      "baseline_response_sha256": digest(canonical(stable[0])),
                      "candidate_response_sha256": digest(canonical(stable[1])), "equal": equal})
    manifest_path = root / "compression-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest["files"]:
            archive = (root / item["compressed_path"]).read_bytes()
            raw = gzip.decompress(archive)
            audit.equal({"sha256": digest(raw), "bytes": len(raw)},
                        {"sha256": item["original_sha256"], "bytes": item["original_bytes"]},
                        item["original_path"], "lossless_compression")
            audit.equal(digest(archive), item["compressed_sha256"], item["compressed_path"], "compressed_digest")
    quality = {name: quality_summary(value["rows"]) for name, value in runs.items()}
    return {
        "schema": "project-scope-native-replay-audit-v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not audit.failures else "failed", "checks": audit.checks,
        "failure_count": len(audit.failures), "failures": audit.failures,
        "source_commits": {"baseline": BASELINE_COMMIT, "candidate": candidate_commit},
        "candidate_source_provenance": provenance,
        "evaluator_sha256": EVALUATOR_SHA256, "dataset_sha256": baseline["report"]["dataset_sha256"],
        "runtime_sha256": {name: value["report"]["runtime"]["sha256"] for name, value in runs.items()},
        "raw_files": {name: value["files"] for name, value in runs.items()},
        "response_comparison": {"excluded_top_level_fields": sorted(RESPONSE_EXCLUSIONS),
            "excluded_quality_or_source_fields": [], "book_responses_compared": counts[("book", "compared")],
            "book_responses_equal": counts[("book", "equal")], "all_strategy_responses_compared": len(pairs),
            "all_strategy_responses_equal": sum(item["equal"] for item in pairs),
            "by_backend": {backend: {"compared": counts[(backend, "compared")], "equal": counts[(backend, "equal")]}
                           for backend in BACKENDS}, "pairs": pairs},
        "book_quality": {name: [cell for cell in cells if cell["backend"] == "book"] for name, cells in quality.items()},
        "all_strategy_quality": quality,
        "limitations": [
            "The unchanged 80 questions are synthetic development regression cases; there is no new holdout or coding LLM.",
            "This is native Book excerpt packing, separate from the historical six-external-component whole-block comparison.",
            "Only one execution per query/budget/strategy was requested. Raw timing is retained, but concurrent work and uncontrolled caches preclude a performance claim or repeated-output stability claim.",
            "The auditor independently recomputes every saved score field; fixed-consumer checks use the truth table of the exact hash-bound handwritten vectors, not generated-code accuracy.",
            "Response comparison drops only top-level latency_ms and cache_hit; source spans, context, diagnostics, result order, revision and every quality field are retained. Runtime/version identities are outside responses and audited separately.",
            "All eight missing-evidence questions return nonempty Book context at each budget; complete answerable-evidence coverage is not universal correctness or reliable abstention.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("benchmarks/reports/v0.7.0-project-scope"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-commit", type=git_object_id,
                        help="Explicit candidate commit; requires both other identity options")
    parser.add_argument("--candidate-tree", type=git_object_id,
                        help="Explicit full candidate Git tree; checked against both commits")
    parser.add_argument("--execution-local-commit", type=git_object_id,
                        help="Explicit execution commit; must exist locally and share the candidate tree")
    args = parser.parse_args()
    if any(value is not None for value in (args.candidate_commit, args.candidate_tree, args.execution_local_commit)):
        if not all(value is not None for value in (args.candidate_commit, args.candidate_tree, args.execution_local_commit)):
            parser.error("--candidate-commit, --candidate-tree and --execution-local-commit must be provided together")
    result = run(args.root, args.repo, candidate_commit=args.candidate_commit, candidate_tree=args.candidate_tree,
                 execution_local_commit=args.execution_local_commit)
    output = args.output or args.root / "native-replay-audit.json"
    with output.open("x", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(json.dumps({key: result[key] for key in ("status", "checks", "failure_count")}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
