"""Offline integrity/source audit of the two unchanged resumed protocols.

This adds no retrieval calls and changes neither evaluator nor recorded output.
Cross-backend directory comparison excludes only each chapter's ingestion-time
updated_at; that descriptive comparison is not a newly defined acceptance gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import subprocess


CANDIDATE = "01032a691abdc4fddfd10f61c9e61f260f9decb3"
BASELINE = "78cc906d81818a16884de7de2e613e5a56346f93"
PROBE_SHA = "0f699741b6c75bb51e9829323e29d8b3ee6f06ba25be6852efa13897ba2d21a8"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def bound_source(repo, identity, commit):
    require(identity["commit"] == commit, "Wrong source commit")
    names = subprocess.check_output(["git", "-C", str(repo), "ls-tree", "-r", "--name-only",
                                     commit, "src/memory_book"]).decode().splitlines()
    require(set(names) == set(identity["files"]), "Incomplete tracked source inventory")
    for name in names:
        original = subprocess.check_output(["git", "-C", str(repo), "show", commit + ":" + name])
        require(sha(original) == identity["files"][name], "Source hash differs: " + name)
    require(identity["source_sha256"] == sha(json.dumps(identity["files"], sort_keys=True).encode()),
            "Source aggregate differs")


def audit_directory(repo, root):
    execution = read(root / "execution.json")
    require(execution["status"] == "completed" and execution["source_unchanged"] is True,
            "Directory execution did not complete with stable source")
    require(execution["source_before"] == execution["source_after"], "Directory source changed")
    bound_source(repo, execution["source_before"], CANDIDATE)
    all_rows, summaries = {}, {}
    for backend in ("native", "python"):
        folder = root / backend
        report, protocol = read(folder / "report.json"), read(folder / "protocol.json")
        raw = (folder / "raw.jsonl").read_bytes()
        rows = [json.loads(line) for line in raw.splitlines()]
        require(report["status"] == "passed" and not report["failures"], "Directory failure recorded")
        require(report["git"] == {"head": CANDIDATE, "relevant_status": ""}, "Wrong directory source binding")
        require(report["runtime_before"] == report["runtime_after"], "Directory imported runtime changed")
        runtime = report["runtime_before"]
        require(runtime["backend"] == backend, "Wrong directory backend")
        for name, digest in runtime["files"].items():
            require(execution["source_before"]["files"]["src/memory_book/" + name] == digest,
                    "Actual directory import differs from bound source")
        require(sha(raw) == report["raw_records"]["sha256"] and len(raw) == report["raw_records"]["bytes"],
                "Directory raw bytes differ")
        require(len(rows) == report["raw_records"]["rows"] == 597, "Wrong directory raw matrix")
        require([r["sequence"] for r in rows] == list(range(1, len(rows) + 1)), "Noncontiguous raw rows")
        require(protocol["dataset_sha256"] == sha(encoded(protocol["dataset"])) == report["dataset_sha256"],
                "Directory fixture differs")
        evaluator = subprocess.check_output(["git", "-C", str(repo), "show", CANDIDATE + ":benchmarks/directory_navigation.py"])
        frozen_protocol = subprocess.check_output(["git", "-C", str(repo), "show", CANDIDATE + ":benchmarks/experiments/v011-directory-navigation-protocol-v2.json"])
        require(protocol == json.loads(frozen_protocol), "Saved protocol differs from committed protocol")
        require(sha(evaluator) == protocol["evaluator_sha256"] == report["evaluator_sha256"], "Evaluator binding differs")
        require(sha(frozen_protocol) == report["protocol_sha256"], "Protocol binding differs")
        originals, chapter_ids = {}, {}
        ingests = [r for r in rows if r["operation"] == "ingest"]
        require([r["request"] for r in ingests] == protocol["dataset"]["sessions"], "Ingestion fixture differs")
        for row in ingests:
            source = row["request"]
            chapter_ids[(source["project"], source["task_id"])] = row["response"]["chapter_id"]
            messages = source["messages"]
            for i in range(0, len(messages), 2):
                text = "\n\n".join(m["role"].upper() + ": " + m["content"] for m in messages[i:i + 2])
                originals[(source["project"], source["session_id"], i // 2)] = (text, [i, i + 1])
        cases = {case["id"]: case for case in protocol["dataset"]["cases"]}
        require(len(cases) == len(report["cases"]) == 119, "Wrong case matrix")
        require({case["id"] for case in report["cases"]} == set(cases), "Missing or extra case")
        for outcome in report["cases"]:
            require(outcome["status"] == "passed", "Case did not pass")
            case = cases[outcome["id"]]
            selected = [r for r in rows if r["case_id"] == case["id"]]
            require(selected[0]["sequence"] == outcome["raw_sequence_start"]
                    and selected[-1]["sequence"] == outcome["raw_sequence_end"], "Case row boundaries differ")
            expected = {chapter_ids[tuple(item)] for item in case.get("expected_chapters", [])}
            seen = []
            for row in selected:
                if row["operation"] != "search_directory":
                    continue
                if "expected_error" in case:
                    require(row.get("error", {}).get("type") == case["expected_error"], "Expected scope error missing")
                    continue
                require("error" not in row, "Unexpected locator error")
                response, request = row["response"], row["request"]
                require(response["evidence"] is False and response["result_type"] == "directory", "Metadata marked as evidence")
                require(response["scope"] == {"project": request.get("project"), "chapter": request.get("chapter")}, "Search scope changed")
                require(response["total"] == len(expected), "Wrong chapter total")
                seen.extend(item["chapter_id"] for item in response["results"])
            require(len(seen) == len(set(seen)) and set(seen) == expected, "Incomplete/duplicate chapter pagination")
        reads = [r for r in rows if r["operation"] == "read"]
        pages = set()
        for row in reads:
            response, request = row["response"], row["request"]
            require(response["id"] == request["page_id"] and response["breadcrumb"][0]["id"] == request["project"], "Read crossed page/project scope")
            require(response["offset"] == 0 and response["next_offset"] is None, "Incomplete original page")
            position = 0
            for ref in sorted(response["source_refs"], key=lambda ref: ref["start"]):
                require(ref["project"] == request["project"] and ref["start"] == position, "Read source gap or wrong project")
                original, indices = originals[(ref["project"], ref["session_id"], ref["turn_index"])]
                require(ref["message_indices"] == indices, "Original message identity differs")
                require(response["content"][ref["start"]:ref["end"]] == original[ref["turn_start"]:ref["turn_end"]], "Original text/coordinates differ")
                position = ref["end"]
            require(position == len(response["content"]) == response["total_chars"], "Source coverage incomplete")
            pages.add(response["id"])
        operations = dict(Counter(row["operation"] for row in rows))
        require(operations == report["summary"]["operations"], "Reported operation counts differ")
        require(len(reads) == 161 and len(pages) == 80, "Wrong original-page matrix")
        summaries[backend] = {"contracts": len(cases), "raw_rows": len(rows), "operations": operations,
                              "original_reads_verified": len(reads), "distinct_original_pages": len(pages),
                              "raw_sha256": sha(raw), "source_unchanged": True}
        all_rows[backend] = rows
    timestamp_rows = 0
    for native, python in zip(all_rows["native"], all_rows["python"]):
        if native == python:
            continue
        require(native["operation"] == python["operation"] == "chapter", "Unexpected backend raw difference")
        a, b = json.loads(json.dumps(native)), json.loads(json.dumps(python))
        a["response"].pop("updated_at")
        b["response"].pop("updated_at")
        require(a == b, "Backend payload differs beyond chapter updated_at")
        timestamp_rows += 1
    return {"backends": summaries, "cross_backend_comparison": {
        "same_records_except_chapter_ingestion_updated_at": True,
        "rows_with_only_that_difference": timestamp_rows,
        "interpretation": "Descriptive offline comparison; raw timestamps remain unchanged."}}


def audit_crowding(repo, root):
    report = read(root / "report.json")
    require(report["status"] == "completed" and report["accepted"] is True, "Crowding run not accepted")
    require(report["baseline_commit"] == BASELINE and report["candidate_commit"] == CANDIDATE, "Wrong crowding source pair")
    require(report["probe_sha256"] == PROBE_SHA, "Original probe differs")
    driver = subprocess.check_output(["git", "-C", str(repo), "show", CANDIDATE + ":scripts/validate_v012_revision_recovery.py"])
    require(sha(driver) == report["driver_sha256"], "Crowding driver binding differs")
    require({(a["backend"], a["arm"]) for a in report["attempts"]} == set(itertools.product(("native", "python"), ("baseline", "candidate"))), "Missing or extra crowding arm")
    expected = set(itertools.product((4, 100, 1000), ("current", "relevance"), (1, 5), range(3)))
    summaries = {}
    total = 0
    for backend in ("native", "python"):
        arms = {}
        for arm, commit in (("baseline", BASELINE), ("candidate", CANDIDATE)):
            folder = root / (backend + "-" + arm)
            identity, raw = read(folder / "identity.json"), read(folder / "raw.json")
            require(identity["status"] == "completed" and identity["backend"] == raw["backend"] == backend, "Wrong actual backend/completion")
            require(identity["source_before"] == identity["source_after"], "Crowding source changed")
            bound_source(repo, identity["source_before"], commit)
            require(raw["git_head"] == commit and raw["probe_sha256"] == PROBE_SHA, "Wrong actual probe import/source")
            require(identity["raw_sha256"] == sha((folder / "raw.json").read_bytes()), "Crowding raw changed")
            require(len(raw["observations"]) == identity["independently_verified_responses"] == 36, "Wrong arm response count")
            rows = {}
            for row in raw["observations"]:
                key = tuple(row[k] for k in ("old_count", "mode", "limit", "repeat"))
                require(key in expected and key not in rows, "Duplicate/unknown crowding row")
                result = row["result"]
                require(result["query"] == "retry_limit" and result["budget_chars"] == 2400
                        and result["context_chars"] == len(result["context"]) <= 2400 and not result["cache_hit"], "Query/budget/cache differs")
                sessions = []
                require(1 <= len(result["results"]) <= row["limit"], "Wrong result limit")
                for item in result["results"]:
                    require(len(item["source_refs"]) == 1, "Unexpected source span count")
                    ref = item["source_refs"][0]
                    session = ref["session_id"]
                    if session == "new":
                        original = "ASSISTANT: retry_limit=7. The short accepted revision replaces the original configuration."
                    else:
                        require(session.startswith("old-") and session[4:].isdigit() and 0 <= int(session[4:]) < row["old_count"], "Unknown source session")
                        original = "ASSISTANT: retry_limit=3. " + "retry_limit. " * 12
                    require(ref["project"] == item["breadcrumb"][0]["id"] == "workers" and ref["turn_index"] == 0 and ref["message_indices"] == [0], "Wrong original/project identity")
                    require([ref[k] for k in ("start", "end", "turn_start", "turn_end")] == [0, len(original), 0, len(original)]
                            and item["excerpt_spans"] == [[0, len(original)]] and item["page_chars"] == len(original)
                            and item["text"] == original and item["truncated"] is False and original in result["context"], "Wrong original text/coordinates")
                    sessions.append(session)
                require(row["new_present"] == ("new" in sessions) and row["first_session"] == sessions[0], "Recovery label differs")
                rows[key] = row
            require(set(rows) == expected, "Incomplete crowding matrix")
            arms[arm] = rows
            total += len(rows)
        differences = []
        for key in sorted(expected):
            if key[1] != "relevance":
                continue
            a, b = dict(arms["baseline"][key]["result"]), dict(arms["candidate"][key]["result"])
            a.pop("latency_ms"); b.pop("latency_ms")
            if a != b:
                differences.append(key)
        recovery = {arm: sum(row["new_present"] for key, row in rows.items() if key[1] == "current") for arm, rows in arms.items()}
        require(not differences and recovery == {"baseline": 18, "candidate": 18}, "Crowding retained behavior differs")
        require(report["comparisons"][backend]["current_new_present"] == recovery
                and report["comparisons"][backend]["relevance_payload_differences_excluding_only_latency"] == [], "Crowding summary differs")
        summaries[backend] = {"current_recovery_per_18_calls": recovery, "relevance_payload_differences_excluding_only_latency": differences}
    return {"verified_responses": total, "backends": summaries,
            "interpretation": "Retains published v0.11 recovery; no new improvement or performance claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--crowding", type=Path, default=Path(__file__).resolve().parent.parent / "resumed-crowding-attempt1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Refusing to overwrite an audit")
    output = {"schema": "v012-resumed-directory-crowding-offline-audit-v1", "status": "passed",
              "candidate_commit": CANDIDATE, "baseline_commit": BASELINE,
              "audit_script_sha256": sha(Path(__file__).read_bytes()),
              "directory": audit_directory(args.repo, args.directory),
              "crowding": audit_crowding(args.repo, args.crowding)}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
