"""Verify strict evidence labels for an explicit or historical corpus plan.

This is a source-structure check, independent of retrieval rankings/outcomes.
It detects annotations split across continuation pages instead of silently
treating such labels as retrieval failures or dropping them from a score.
Without --corpora-json, retain the historical v0.3 corpus selections. New
evaluation plans should supply their exact corpora and source display labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from benchmarks.token_compare import validation_status


HISTORICAL_CORPORA = (
    {"corpus": "synthetic", "split": "development", "seed": 61, "projects": 8, "max_queries": 0},
    {"corpus": "synthetic", "split": "heldout", "seed": 113, "projects": 8, "max_queries": 0},
    {"corpus": "synthetic", "split": "heldout", "seed": 307, "projects": 8, "max_queries": 0},
    {"corpus": "locomo", "split": "development", "seed": 61, "projects": 8, "max_queries": 128},
    {"corpus": "locomo", "split": "heldout", "seed": 61, "projects": 8, "max_queries": 256},
)


def load_corpora(path: Path | None) -> list[dict]:
    """Reject ambiguous plans rather than silently applying historical defaults."""
    if path is None:
        return [dict(item) for item in HISTORICAL_CORPORA]
    corpora = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(corpora, list) or not corpora:
        raise ValueError("corpora JSON must be a nonempty list")
    required = {"corpus", "split", "seed", "projects", "max_queries"}
    for index, item in enumerate(corpora):
        if (not isinstance(item, dict) or not required <= item.keys()
                or item.keys() - required - {"label"}):
            raise ValueError(f"corpus {index} needs exactly corpus/split/seed/projects/max_queries and optional label")
        if item["corpus"] not in ("synthetic", "locomo") or item["split"] not in ("development", "heldout"):
            raise ValueError(f"corpus {index} has an unsupported corpus or split")
        if any(type(item[key]) is not int for key in ("seed", "projects", "max_queries")):
            raise ValueError(f"corpus {index} seed/projects/max_queries must be integers")
        if item["projects"] < 1 or item["max_queries"] < 0:
            raise ValueError(f"corpus {index} needs positive projects and nonnegative max_queries")
        if item["corpus"] == "synthetic" and item["max_queries"] != 0:
            raise ValueError(f"corpus {index}: synthetic loading has no query limit; use max_queries=0")
        if "label" in item and (not isinstance(item["label"], str) or not item["label"].strip()):
            raise ValueError(f"corpus {index} label must be a nonempty string")
    return corpora


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--baseline-label", default="v0.2.1",
                        help="Source display label; v0.2.1 is the historical default, not a version assertion")
    parser.add_argument("--candidate-label", default="candidate")
    parser.add_argument("--corpora-json", type=Path,
                        help="JSON file containing a list of corpus/split/seed/projects/max_queries entries, with optional label")
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/evidence-preflight.json"))
    args = parser.parse_args()
    if not args.baseline_label.strip() or not args.candidate_label.strip() or args.baseline_label == args.candidate_label:
        parser.error("baseline and candidate labels must be distinct and nonempty")
    try:
        corpora = load_corpora(args.corpora_json)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if any(item["corpus"] == "locomo" for item in corpora) and args.locomo_path is None:
        parser.error("--locomo-path is required for plans containing LoCoMo")
    records = []
    with tempfile.TemporaryDirectory(prefix="evidence-preflight-", dir=Path.cwd().parent) as directory:
        root = Path(directory)
        for selector, label, source, other_label in (
                ("baseline", args.baseline_label, args.baseline_src, args.candidate_label),
                ("candidate", args.candidate_label, args.candidate_src, args.baseline_label)):
            for index, corpus in enumerate(corpora):
                # Labels are presentation data. Numeric identities also keep
                # multiple query limits for the same split/seed distinct.
                identity = f"{selector}-{index}"
                output = root / (identity + ".json")
                command = [sys.executable, "-m", "benchmarks.component_eval", "--worker", "export",
                           "--baseline-src", str(args.baseline_src.resolve()), "--engine-src", str(source.resolve()),
                           "--baseline-label", label, "--candidate-label", other_label,
                           "--cache", str(root), "--corpus", corpus["corpus"], "--split", corpus["split"],
                           "--seed", str(corpus["seed"]), "--projects", str(corpus["projects"]),
                           "--max-queries", str(corpus["max_queries"]),
                           "--database", str(root / (identity + ".db")), "--bundle", str(root / (identity + "-pages.json")),
                           "--output", str(output)]
                if args.locomo_path is not None:
                    command += ["--locomo-path", str(args.locomo_path.resolve())]
                completed = subprocess.run(command, check=False)
                try:
                    result = json.loads(output.read_text(encoding="utf-8"))
                    if not isinstance(result, dict):
                        raise ValueError("worker report is not an object")
                except (OSError, ValueError) as error:
                    result = {"export_error": str(error)}
                records.append({**result, "label": label, "engine_selector": selector,
                                "requested_source": str(source.resolve()), "corpus_index": index,
                                "corpus_plan": dict(corpus),
                                "worker_exit_code": getattr(completed, "returncode", 0)})
    status = {"passed": True, "failures": []}
    failures = 0
    for record in records:
        status["failures"].extend({**failure, "corpus_index": record["corpus_index"]}
                                  for failure in validation_status([record])["failures"])
        missing = record.get("evidence_attainability", {}).get("unattainable_single_page_labels")
        if not isinstance(missing, list):
            status["failures"].append({"label": record["label"], "corpus_index": record["corpus_index"],
                                       "check": "export_report", "observed": record.get("export_error", "missing evidence check")})
        elif missing:
            failures += len(missing)
            status["failures"].append({"label": record["label"], "corpus_index": record["corpus_index"],
                                       "check": "unattainable_single_page_labels", "observed": len(missing)})
    status["passed"] = not status["failures"]
    report = {"schema_version": 2,
              "scope": ("explicit caller-supplied corpus plan, both baseline and candidate source" if args.corpora_json else
                        "historical v0.3 corpus plan, both baseline and candidate source; not a claim of coverage for later experiments"),
              "corpora": corpora,
              "plan_path": str(args.corpora_json.resolve()) if args.corpora_json else None,
              "source_labels": {"baseline": args.baseline_label, "candidate": args.candidate_label},
              "check": "every required and stale annotation fits a complete canonical page and its matching original source span",
              "unattainable_labels": failures, "records": records, "validation": status,
              "limitation": "The strict evaluator does not reconstruct one annotation across multiple returned pages. This preflight checks that no evaluated label is affected; it never removes labels."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "unattainable_labels": failures,
                      "validation_passed": status["passed"], "output": str(args.output)}))
    return 0 if status["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
