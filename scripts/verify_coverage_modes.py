"""Verify the final default and opt-in paths against frozen runtime snapshots.

This checks complete non-timing recall payloads, not just aggregate scores.
It makes no new quality or latency claim. Every corpus is now regression data.
Run as ``python -m scripts.verify_coverage_modes`` from the repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from benchmarks.data import generate_dataset
from benchmarks.public_data import load_locomo
from benchmarks.run import engine_source_hash
from benchmarks.token_compare import checkout_provenance
from benchmarks.transfer_data import load_transfer


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def worker(args):
    sys.path.insert(0, str(args.source.resolve()))
    import memory_book
    from memory_book import MemoryBook
    root = Path(memory_book.__file__).parent
    before = engine_source_hash(root)
    datasets = [generate_dataset(seed=61, split="development", projects=8),
                generate_dataset(seed=211, split="heldout", projects=8),
                load_locomo(args.locomo_path, split="heldout", max_queries=0),
                load_transfer()]
    reports = []
    for dataset in datasets:
        hashes = {}
        with MemoryBook(":memory:", cache_size=0) as book:
            for session in dataset.sessions:
                book.ingest(session)
            for budget in (2000, 8000):
                for case in dataset.queries:
                    options = {"coverage": True} if args.coverage else {}
                    response = book.recall(case.query, project=case.project, budget_chars=budget,
                                           limit=5, use_cache=False, **options)
                    if response["context_chars"] != len(response["context"]) or len(response["context"]) > budget:
                        raise ValueError("Budget or context-size invariant failed")
                    # All remaining fields participate, including IDs, order,
                    # text, source refs, exact scores, warnings and truncation.
                    response.pop("latency_ms")
                    hashes[f"{budget}:{case.id}"] = digest(response)
        reports.append({"dataset": dataset.description(), "payload_sha256": hashes})
    after = engine_source_hash(root)
    if before != after:
        raise ValueError("Measured source changed during mode verification")
    return {"label": args.label, "coverage_argument": args.coverage,
            "source_provenance": checkout_provenance(root),
            "source_sha256_before": before, "source_sha256_after": after,
            "source_unchanged": True, "corpora": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-src", type=Path, default=Path("../baseline-score/src"))
    parser.add_argument("--automatic-src", type=Path, default=Path("../baseline-conjunctive/src"))
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--locomo-path", type=Path, default=Path(".artifacts/data/locomo10.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/coverage-mode-equivalence.json"))
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--label", help=argparse.SUPPRESS)
    parser.add_argument("--coverage", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        args.output.write_text(json.dumps(worker(args), ensure_ascii=False), encoding="utf-8")
        return 0
    results = {}
    with tempfile.TemporaryDirectory(dir=Path.cwd().parent) as directory:
        modes = [("score-aware-default", args.score_src, False),
                 ("final-default", args.candidate_src, False),
                 ("frozen-automatic-clause", args.automatic_src, False),
                 ("final-opt-in-coverage", args.candidate_src, True)]
        for index, (label, source, coverage) in enumerate(modes):
            destination = Path(directory) / f"mode-{index}.json"
            command = [sys.executable, "-m", "scripts.verify_coverage_modes", "--worker",
                       "--source", str(source.resolve()), "--label", label,
                       "--locomo-path", str(args.locomo_path.resolve()), "--output", str(destination)]
            if coverage:
                command.append("--coverage")
            subprocess.run(command, check=True, timeout=600)
            results[label] = json.loads(destination.read_text(encoding="utf-8"))
            print(label + ": verified source and budgets", flush=True)
    comparisons = []
    for left, right in [("score-aware-default", "final-default"),
                        ("frozen-automatic-clause", "final-opt-in-coverage")]:
        differences, checked = [], 0
        a, b = results[left]["corpora"], results[right]["corpora"]
        if len(a) != len(b):
            raise ValueError("Mode corpus populations differ")
        for original, candidate in zip(a, b):
            if original["dataset"]["sha256"] != candidate["dataset"]["sha256"]:
                raise ValueError("Mode datasets differ")
            old, new = original["payload_sha256"], candidate["payload_sha256"]
            if old.keys() != new.keys():
                raise ValueError("Mode query populations differ")
            checked += len(old)
            differences.extend({"dataset_sha256": original["dataset"]["sha256"],
                                "query_budget_id": key} for key in old if old[key] != new[key])
        comparisons.append({"baseline": left, "candidate": right,
                            "complete_payloads_compared": checked, "differences": differences,
                            "equal": not differences})
    report = {"schema_version": 1, "purpose": "Final mode routing equivalence, not a new benchmark",
              "method": "Independent processes; compare complete recall payload hashes excluding only latency_ms; no text or answer labels published.",
              "budgets_chars": [2000, 8000], "limit": 5,
              "comparisons": comparisons, "workers": results,
              "validation": {"passed": all(item["equal"] for item in comparisons)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"comparisons": comparisons, "validation": report["validation"]}, indent=2))
    return 0 if report["validation"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
