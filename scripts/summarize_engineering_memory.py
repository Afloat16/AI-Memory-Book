"""Audit and summarize the four retained engineering development blocks.

Accepts the original directory or the committed gzip-compressed raw records.
Quality cases are counted once; repeated calls contribute only timing samples.
No confidence interval or general superiority claim is inferred from fixtures.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
import statistics

BLOCKS = ("1-baseline", "2-candidate", "3-candidate", "4-baseline")


def read_text(path):
    path = Path(path)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes()).decode()


def read(path):
    return json.loads(read_text(path))


def rows(path):
    return [json.loads(line) for line in read_text(path).splitlines() if line]


def timing(values, *, nearest=False):
    values = sorted(values)
    position = .95 * (len(values) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    p95 = (values[math.ceil(.95 * len(values)) - 1] if nearest else
           values[lo] + (values[hi] - values[lo]) * (position - lo))
    return {"samples": len(values), "p50_ms": statistics.median(values), "p95_ms": p95,
            "p95_method": "nearest_rank" if nearest else "linear_interpolation"}


def index_rows(entries):
    indexed = {(r["case_id"], r["backend"], r["budget_chars"]): r for r in entries}
    if len(indexed) != len(entries):
        raise ValueError("Duplicate quality cases")
    return indexed


def paired(first, second):
    if set(first) != set(second):
        raise ValueError("Unmatched quality cases")
    return {
        "complete_evidence_wins": sorted(k for k in first if not first[k]["score"]["complete_evidence"]
                                         and second[k]["score"]["complete_evidence"]),
        "complete_evidence_losses": sorted(k for k in first if first[k]["score"]["complete_evidence"]
                                           and not second[k]["score"]["complete_evidence"]),
    }


def summarize(root):
    root = Path(root)
    execution = read(root / "execution.json")
    if execution["order"] != ["baseline", "candidate", "candidate", "baseline"]:
        raise ValueError("Unexpected block order")
    if len(execution["blocks"]) != 12 or any(r["exit_code"] for r in execution["blocks"]):
        raise ValueError("Incomplete execution matrix")
    data, reports, targets = {}, {}, {}
    identities = {"baseline": set(), "candidate": set()}
    datasets, evaluators = set(), {"workflow": set(), "components": set()}
    for block in BLOCKS:
        arm = block.split("-", 1)[1]
        targets[block] = read(root / (block + "-targeted.json"))
        for kind in ("workflow", "components"):
            report = reports[(block, kind)] = read(root / (block + "-" + kind) / "report.json")
            if (report["status"] != "completed" or not report["runtime_unchanged"]
                    or not report["evaluator_unchanged"]):
                raise ValueError("Incomplete run or changing source")
            identities[arm].add(report["runtime"]["sha256"])
            datasets.add(report["dataset_sha256"])
            evaluators[kind].add(report["evaluator_sha256"] if kind == "workflow" else report["evaluator"]["sha256"])
            for cell in report["summary"]:
                if any(cell[k] for k in ("budget_violations", "source_validation_failures", "repeat_output_changes")):
                    raise ValueError("Integrity failure")
            entries = data[(block, kind)] = rows(root / (block + "-" + kind) / "raw.jsonl")
            index_rows(entries)
            expected = report["case_count"] * len(report["settings"]["budgets_chars"]) * (4 if kind == "workflow" else 2)
            if len(entries) != expected:
                raise ValueError("Incomplete quality matrix")
    if any(len(v) != 1 for v in identities.values()) or len(datasets) != 1 or any(len(v) != 1 for v in evaluators.values()):
        raise ValueError("Runtime or fixture mismatch across blocks")
    # Every repeated quality result must agree, not just the aggregate rate.
    for kind in ("workflow", "components"):
        for first, second in (("1-baseline", "4-baseline"), ("2-candidate", "3-candidate")):
            a, b = index_rows(data[(first, kind)]), index_rows(data[(second, kind)])
            if set(a) != set(b) or any(a[k]["score"] != b[k]["score"] for k in a):
                raise ValueError("Quality changed between repeated blocks")
    result = {"schema": "engineering-development-summary-v1", "integrity_passed": True,
              "evidence_level": "synthetic_development_only", "order": execution["order"],
              "runtime_sha256": {k: next(iter(v)) for k, v in identities.items()},
              "dataset_sha256": next(iter(datasets)), "targeted": {}, "workflow": {}, "components": {},
              "call_counts": {
                  "targeted": sum(len(report["rows"]) for report in targets.values()),
                  "workflow": sum(len(r["latency_ms"]) for block in BLOCKS for r in data[(block, "workflow")]),
                  "external_components": sum(len(r["samples"]) for block in BLOCKS
                      for r in rows(root / (block + "-components") / "native.jsonl"))},
              "limitations": ["Development fixtures informed changes; no independent holdout.",
                  "Fixed policy consumer, no LLM code generation or time-to-correct-patch measurement.",
                  "External common whole-block packing differs from native bounded excerpts.",
                  "Search interface timings cannot establish complete product speed ratios."]}
    control_fingerprints = {}
    for block, report in targets.items():
        if len(report["rows"]) != 720 or any(not r["source_valid"] or not r["budget_valid"] for r in report["rows"]):
            raise ValueError("Targeted replay failed integrity checks")
        for row in report["rows"]:
            if row["mode"] == "current":
                continue
            payload = {k: v for k, v in row["response"].items() if k != "latency_ms"}
            fingerprint = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            expected = control_fingerprints.setdefault(row["case_id"], fingerprint)
            if fingerprint != expected:
                raise ValueError("Ordinary/historical control output changed")
    result["unchanged_control_cases"] = len(control_fingerprints)
    for mode in ("current", "historical-control", "ordinary-control"):
        result["targeted"][mode] = {}
        for arm in identities:
            selected = [r for block in BLOCKS if arm in block for r in targets[block]["rows"] if r["mode"] == mode]
            result["targeted"][mode][arm] = {
                **timing([r["wall_ms"] for r in selected], nearest=True),
                "correction_visible_calls": sum(r["correction_visible"] for r in selected),
                "distinct_cases": len({r["case_id"] for r in selected})}
    for budget in (1200, 2400):
        cell = {}
        for arm in identities:
            first = "1-baseline" if arm == "baseline" else "2-candidate"
            source = reports[(first, "workflow")]
            cell[arm] = next(c for c in source["summary"] if c["backend"] == "book" and c["budget_chars"] == budget).copy()
            values = [v for block in BLOCKS if arm in block for r in data[(block, "workflow")]
                      if r["backend"] == "book" and r["budget_chars"] == budget for v in r["latency_ms"]]
            cell[arm]["pooled_timing"] = timing(values)
        select = lambda block, kind, backend: {r["case_id"]: r for r in data[(block, kind)]
                                              if r["backend"] == backend and r["budget_chars"] == budget}
        cell["paired"] = paired(select("1-baseline", "workflow", "book"), select("2-candidate", "workflow", "book"))
        result["workflow"][str(budget)] = cell
        result["components"][str(budget)] = {
            "candidate_vs_billion": paired(select("2-candidate", "components", "billion"), select("2-candidate", "components", "book")),
            "quality": {arm: [c for c in reports[(block, "components")]["summary"] if c["budget_chars"] == budget]
                        for arm, block in (("baseline", "1-baseline"), ("candidate", "2-candidate"))}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"integrity_passed": result["integrity_passed"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
