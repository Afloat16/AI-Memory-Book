"""Verify strict evidence labels are attainable in every published v0.3 corpus.

This is a source-structure check, independent of retrieval rankings/outcomes.
It detects annotations split across continuation pages instead of silently
treating such labels as retrieval failures or dropping them from a score.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--locomo-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/evidence-preflight.json"))
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix="evidence-preflight-", dir=Path.cwd().parent) as directory:
        root = Path(directory)
        for label, source in (("v0.2.1", args.baseline_src), ("candidate", args.candidate_src)):
            for corpus, split, seed, limit in (("synthetic", "development", 61, 0),
                ("synthetic", "heldout", 113, 0), ("synthetic", "heldout", 307, 0),
                ("locomo", "development", 61, 128), ("locomo", "heldout", 61, 256)):
                identity = f"{label}-{corpus}-{split}-{seed}"
                output = root / (identity + ".json")
                command = [sys.executable, "-m", "benchmarks.component_eval", "--worker", "export",
                           "--baseline-src", str(args.baseline_src.resolve()), "--engine-src", str(source.resolve()),
                           "--cache", str(root), "--corpus", corpus, "--split", split, "--seed", str(seed),
                           "--projects", "8", "--max-queries", str(limit), "--locomo-path", str(args.locomo_path.resolve()),
                           "--database", str(root / (identity + ".db")), "--bundle", str(root / (identity + "-pages.json")),
                           "--output", str(output)]
                subprocess.run(command, check=True)
                result = json.loads(output.read_text())
                records.append({"label": label, **result})
    failures = sum(len(record["evidence_attainability"]["unattainable_single_page_labels"]) for record in records)
    report = {"schema_version": 1, "scope": "all newly published v0.3 corpora, both baseline and candidate source",
              "check": "every required and stale annotation fits a complete canonical page and its matching original source span",
              "unattainable_labels": failures, "records": records,
              "limitation": "The strict evaluator does not reconstruct one annotation across multiple returned pages. This preflight checks that no evaluated label is affected; it never removes labels."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "unattainable_labels": failures, "output": str(args.output)}))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
