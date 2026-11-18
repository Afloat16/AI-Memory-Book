#!/usr/bin/env python3
"""Check v0.12 README tables/plots against retained source-bound observations.

Offline only: no retrieval, upstream package or model execution. This verifies
saved evidence and documentation, not published-wheel installation or speed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_project_scope_native_replay import EVALUATOR_SHA256, expected_score, quality_summary

ENGINEERING = ROOT / "benchmarks/reports/v0.12-development/resumed-engineering-attempt2"
SEARCH = ROOT / "benchmarks/reports/v0.12-search-components/quality-attempt1"
DATASET = "87e8ccad3510fb7e8a4c68c9fa3f284473abf8381ef6444ad179e3d4196b3ac3"
SOURCE = "021a384567db5aa64fde155f090d2eb399f55c03"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def read(path):
    path = Path(path)
    return path.read_bytes() if path.exists() else gzip.decompress(Path(str(path) + ".gz").read_bytes())


def load(path):
    return json.loads(read(path))


def records(raw):
    return [json.loads(line) for line in raw.splitlines() if line]


def verify_raw(rows, dataset, backends):
    require(sha(canonical(dataset)) == DATASET, "Dataset differs")
    cases, snapshots, visible = {}, {}, {}
    for step in dataset:
        for session in step["sessions"]:
            visible[(session["project"], session["session_id"], 0)] = "\n\n".join(
                f"{item['role'].upper()}: {item['content']}" for item in session["messages"])
        snapshots[step["checkpoint"]] = dict(visible)
        for case in step["cases"]:
            require(case["id"] not in cases, "Duplicate question")
            cases[case["id"]] = case
    keys = [(r["case_id"], r["backend"], r["budget_chars"]) for r in rows]
    wanted = {(c, b, n) for c in cases for b in backends for n in (1200, 2400)}
    require(len(keys) == len(set(keys)) and set(keys) == wanted, "Incomplete/duplicate response matrix")
    for row in rows:
        case = cases[row["case_id"]]
        require(all(row[k] == case[k] for k in ("project", "query", "category", "checkpoint")), "Request identity differs")
        derived = expected_score(case, row["response"], snapshots[row["checkpoint"]], row["budget_chars"])
        require(derived == row["score"], "Saved score differs from source-derived score")
        require(not derived["source_errors"] and derived["within_budget"], "Source or budget failure")
    return quality_summary(rows)


def archived_search():
    manifest = load(SEARCH / "archive-manifest.json")
    chunks = []
    for part in manifest["archive"]["parts"]:
        raw = read(SEARCH / part["path"])
        require(len(raw) == part["bytes"] and sha(raw) == part["sha256"], "Search archive part differs")
        chunks.append(raw)
    raw = b"".join(chunks)
    require(len(raw) == manifest["archive"]["bytes"] and sha(raw) == manifest["archive"]["sha256"], "Search archive differs")
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as archive:
        members = archive.getmembers()
        require(len(members) == len(manifest["archived_files"]) and {m.name for m in members} == set(manifest["archived_files"]), "Search member inventory differs")
        for member in members:
            require(member.isfile(), "Search member is not a regular file")
            result[member.name] = archive.extractfile(member).read()
    for name in manifest["retained_files"]:
        result[name] = read(SEARCH / name)
    require(set(result) == set(manifest["original_files"]), "Search original inventory differs")
    for name, raw in result.items():
        expected = manifest["original_files"][name]
        require(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Search original differs: " + name)
    return result


def key(row):
    return row["backend"], row["budget_chars"]


def compact(row):
    def count(name, denominator):
        return round(row[name] * denominator)
    return [f"{count('evidence_recall', 80)}/80",
            f"{count('complete_evidence_rate', 72)}/72",
            f"{count('fixed_consumer_all_checks_pass_rate', 48)}/48",
            str(row["stale_only_cases"]),
            str(Decimal(str(row["mean_context_chars"])).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))]


def section(text, heading):
    start = text.index(heading) + len(heading)
    end = text.find("\n#", start)
    return text[start:] if end < 0 else text[start:end]


def cells(line):
    return [re.sub(r"[*,\s]", "", value).split("·", 1)[0] for value in line.strip().strip("|").split("|")]


def table_row(text, label):
    matches = [cells(line) for line in text.splitlines() if line.startswith("|") and label in line.split("|")[1]]
    require(len(matches) == 1, "Expected one table row for " + label)
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        require(not args.output.exists() and args.output.parent.is_dir(), "Use a new output path with an existing parent")
    require(sha(read(ROOT / "benchmarks/engineering_workflow.py")) == EVALUATOR_SHA256, "Frozen scoring fixture changed")
    acceptance = load(ROOT / "benchmarks/experiments/v012-source-acceptance.json")
    require(acceptance["source_commit"] == SOURCE, "Accepted source differs")
    for path, identity in acceptance["evidence"].items():
        raw = read(ROOT / path)
        require(len(raw) == identity["bytes"] and sha(raw) == identity["sha256"], "Accepted evidence differs: " + path)
    comparison = load(ENGINEERING / "comparison.json")
    require(comparison["candidate_commit"] == SOURCE and comparison["accepted"], "Engineering acceptance differs")
    for name, identity in comparison["raw_manifest"].items():
        stored = read(ENGINEERING / identity["stored_as"])
        require(sha(stored) == identity["stored_sha256"], "Compressed engineering record differs")
        raw = gzip.decompress(stored)
        require(len(raw) == identity["bytes"] and sha(raw) == identity["sha256"], "Original engineering record differs")
    summaries = {}
    for arm in ("baseline", "candidate"):
        for track, backends in (("native", ("book", "flat", "recent_history", "no_memory")), ("common-block", ("book",))):
            base = ENGINEERING / arm / track
            result = verify_raw(records(read(base / "raw.jsonl")), load(base / "dataset.json"), backends)
            reported = {key(r): r for r in load(base / "report.json")["summary"]}
            require(all(compact(row) == compact(reported[key(row)]) for row in result), "Engineering aggregate differs")
            summaries[arm, track] = {key(row): row for row in result}
    saved = archived_search()
    new = verify_raw(records(saved["raw.jsonl"]), json.loads(saved["dataset.json"]), ("lancedb_fts", "whoosh_bm25f_or"))
    projection = load(SEARCH / "summary.json")
    require(projection["source_report_sha256"] == sha(saved["report.json"]), "Search projection source differs")
    projected = {key(r): r for r in projection["summary"]}
    require(all(compact(r) == compact(projected[key(r)]) for r in new), "Search projection numbers differ")
    old = load(ROOT / "benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/report.json")
    extension = load(ROOT / "benchmarks/reports/v0.11-extended-lexical/verified-metrics.json")
    require(old["dataset_sha256"] == extension["audit"]["dataset_sha256"] == DATASET, "Historical dataset differs")
    metrics = {key(r): r for r in old["summary"] if r["backend"] != "book"}
    for r in extension["rows"]:
        if r["backend"] == "memvid_lex":
            continue
        metrics[key(r)] = {**r, "evidence_recall": r["matched_evidence"] / r["required_evidence"],
            "complete_evidence_rate": r["complete_cases"] / r["answerable_cases"],
            "fixed_consumer_all_checks_pass_rate": r["fixed_policy_passed"] / r["fixed_policy_cases"]}
    metrics.update({key(r): r for r in new})
    metrics.update(summaries["candidate", "common-block"])
    require(len(metrics) == 22, "Expected Book plus ten external configurations at two budgets")
    names = {"AI-Memory-Book": "book", "BM25S": "bm25s", "Whoosh": "whoosh_bm25f_or",
             "Haystack": "haystack_bm25", "LanceDB": "lancedb_fts", "billion-context": "billion",
             "claude-mem": "claude_mem", "Basic Memory": "basic_memory"}
    readmes = {}
    for filename, heading, shared in (("README.md", "### Compared with pinned open-source components\n", "Mem0 / Chroma / LangGraph"),
                                      ("README.zh-CN.md", "### 与已测开源组件对比\n", "共享 MiniLM")):
        text = (ROOT / filename).read_text(encoding="utf-8")
        table = section(text, heading)
        for name, backend in {**names, shared: "mem0"}.items():
            actual = table_row(table, name)[1:]
            require(actual == compact(metrics[backend, 2400]), f"README numeric row differs: {filename}/{name}: {actual}")
        require(("26" in text and "Whoosh" in text and "30/32" in text and "22/32" in text), "Missing scope or diagnosis disclosure")
        readmes[filename] = sha(text.encode())
    current = (ROOT / "docs/current-results.md").read_text(encoding="utf-8")
    table = section(current, "## Complete common-block results\n")
    lines = [cells(line) for line in table.splitlines() if line.startswith("|")][2:]
    require(len(lines) == 18, "Current results needs nine displayed rows per budget")
    current_names = {"Book": "book", "BM25S": "bm25s", "Whoosh": "whoosh_bm25f_or", "Haystack": "haystack_bm25",
                     "LanceDB": "lancedb_fts", "billion-context": "billion", "claude-mem": "claude_mem", "BasicMemory": "basic_memory", "Eachshared-MiniLM": "mem0"}
    for row in lines:
        backend = next(value for name, value in current_names.items() if row[0].startswith(name))
        require(row[2:] == compact(metrics[backend, int(row[1])]), "Current-result numeric row differs")
    chart = load(ROOT / "docs/readme-assets/chart-data.json")
    provenance = chart["provenance"]["coverage"]
    require(provenance["source_candidate"] == SOURCE, "Chart source differs")
    for name in ("candidate_comparison", "source_acceptance", "search_components_summary"):
        require(sha(read(ROOT / provenance[name])) == provenance[name + "_sha256"], "Chart evidence binding differs")
    chart_names = {"book": "book", "bm25s": "bm25s", "whoosh": "whoosh_bm25f_or", "haystack": "haystack_bm25", "lancedb": "lancedb_fts", "billion": "billion", "claude": "claude_mem", "basic": "basic_memory", "minilm": "mem0"}
    require({r["id"] for r in chart["coverage"]["rows"]} == set(chart_names), "Chart row inventory differs")
    for row in chart["coverage"]["rows"]:
        require(row["complete"] == round(metrics[chart_names[row["id"]], 2400]["complete_evidence_rate"] * 72), "Chart value differs")
    for index in range(1, 7):
        raw = read(ENGINEERING / f"candidate/common-block/documents-{index}.json")
        require(raw == saved[f"documents-{index}.json"], "Book/external supplied pages differ")
    architecture = section((ROOT / "docs/open-source-memory-comparison.md").read_text(encoding="utf-8"), "## Project families and engineering roles\n")
    architecture_rows = [line for line in architecture.splitlines() if line.startswith("| [")]
    require(len(architecture_rows) == 26, "Architecture family count differs")
    report = {"status": "verified", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Offline saved-response scoring and README/chart number checks; no retrieval, upstream rerun, timing or publication validation.",
        "source_commit": SOURCE, "acceptance_evidence_files_verified": len(acceptance["evidence"]),
        "engineering_responses_independently_rescored": 1600, "lancedb_whoosh_responses_independently_rescored": 320,
        "external_scored_configurations": 10, "readme_comparison_rows_checked": 18,
        "current_result_common_rows_checked": 18, "chart_rows_checked": 9,
        "same_source_page_bundles_verified": 6, "architecture_family_rows_checked": 26, "readme_sha256": readmes,
        "source_acceptance_sha256": sha(read(ROOT / "benchmarks/experiments/v012-source-acceptance.json")),
        "chart_data_sha256": sha(read(ROOT / "docs/readme-assets/chart-data.json"))}
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
