"""Development review: can short-page completion displace a current turn?

This scans a declared small budget range, not an independent quality fixture
or speed experiment. It compares the existing character allocator with the
proposed pure postprocessor on the same imported runtime. Preserve all findings.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from memory_book import MemoryBook
import memory_book.store as store
from memory_book.context_budget import complete_short_pages
from tests.test_current_turn_recall import same_page_session


def identity():
    files = [Path(store.__file__).resolve(), ROOT / "src/memory_book/context_budget.py",
             ROOT / "tests/test_current_turn_recall.py", Path(__file__).resolve()]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Retain old attempts; use a new output file")
    before = identity()
    report = {"kind": "working-tree development review; no release-source or performance claim",
              "source_before": before, "budget_range": [400, 1600, 5],
              "short_record_sizes": [180, 230], "observations": [], "regressions": []}
    allocator = store._context_allocations
    try:
        for short_size in report["short_record_sizes"]:
            with MemoryBook(":memory:") as book:
                source = same_page_session()
                book.ingest(source)
                for i in range(2):
                    short = copy.deepcopy(source)
                    short["session_id"] = "memo-" + str(i)
                    body = "Gradient accumulation steps require checking the original decision. "
                    body += "Supporting administrative detail. " * 8
                    short["messages"] = [{"role": "assistant", "content": body[:short_size - 11]}]
                    book.ingest(short)
                for budget in range(400, 1601, 5):
                    request = {"query": "current gradient accumulation steps", "project": "trainer",
                               "limit": 3, "budget_chars": budget, "use_cache": False}
                    control = book.recall(**request)
                    with patch.object(store, "_context_allocations",
                                      side_effect=lambda pages, cap: complete_short_pages(allocator(pages, cap))):
                        candidate = book.recall(**request)
                    present = lambda result: "steps are now 2" in result["context"]
                    cell = {"short_record_chars": short_size, "budget_chars": budget,
                            "control_current_present": present(control), "candidate_current_present": present(candidate)}
                    report["observations"].append(cell)
                    if present(control) and not present(candidate):
                        report["regressions"].append({**cell, "control": control, "candidate": candidate,
                            "original_pages": {hit["id"]: book.read(hit["id"], project="trainer", limit=100000)
                                               for result in (control, candidate) for hit in result["results"]}})
        report["source_after"] = identity()
        report["source_unchanged"] = before == report["source_after"]
        report["status"] = "completed" if report["source_unchanged"] else "source_changed"
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "observations": len(report["observations"]),
                      "regressions": len(report["regressions"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
