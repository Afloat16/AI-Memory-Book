"""Frozen authored contracts for directory discovery and scoped source reads.

This is a new-API contract experiment, not a baseline quality/speed comparison
or an independent holdout. Its protocol contains every input and expectation.
The locator receives only public query/scope/pagination arguments, never labels.

Inspect the frozen input without executing the locator::

    PYTHONPATH=src python -m benchmarks.directory_navigation --describe

Execute once after committing the protocol; output must be a new directory::

    PYTHONPATH=src python -m benchmarks.directory_navigation --output PATH
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "benchmarks/experiments/v011-directory-navigation-protocol.json"
SCHEMA = "directory-navigation-contracts-v1"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load_protocol():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    require(protocol["schema"] == SCHEMA, "Wrong protocol schema")
    require(protocol["dataset_sha256"] == digest(protocol["dataset"]), "Frozen fixture changed")
    require(protocol["evaluator_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "Frozen evaluator changed; retain the original and register a new attempt")
    return protocol


def runtime_identity():
    import memory_book
    from memory_book._text_backend import BACKEND_NAME, NATIVE
    package = Path(memory_book.__file__).resolve().parent
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(package.iterdir()) if p.is_file() and p.suffix in {".py", ".c", ".h"}}
    extension = None
    if NATIVE is not None:
        path = Path(NATIVE.__file__).resolve()
        extension = {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"version": memory_book.__version__, "package": str(package),
            "backend": BACKEND_NAME, "files": files,
            "extension": extension, "sha256": digest({"files": files, "extension": extension})}


def git_identity():
    def run(*args):
        completed = subprocess.run(["git", *args], cwd=ROOT, text=True,
                                   capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else None
    return {"head": run("rev-parse", "HEAD"),
            "relevant_status": run("status", "--porcelain", "--", "src/memory_book",
                                   "benchmarks/directory_navigation.py", str(PROTOCOL.relative_to(ROOT)))}


def original_sources(dataset):
    """Reconstruct the fixture's paired user/assistant turns independently."""
    sources, chapters = {}, {}
    for source in dataset["sessions"]:
        key = (source["project"], source["task_id"])
        chapter = chapters.setdefault(key, {"pages": 0, "sessions": set()})
        chapter["sessions"].add(source["session_id"])
        messages = source["messages"]
        require(len(messages) % 2 == 0, "Fixture requires paired user/assistant messages")
        for turn, index in enumerate(range(0, len(messages), 2)):
            pair = messages[index:index + 2]
            require([message["role"] for message in pair] == ["user", "assistant"], "Unexpected fixture roles")
            sources[(source["project"], source["session_id"], turn)] = {
                "text": "\n\n".join(f"{message['role'].upper()}: {message['content']}" for message in pair),
                "message_indices": [index, index + 1],
            }
            chapter["pages"] += 1
    return sources, chapters


def validate_navigation_shape(response):
    require(response["result_type"] == "directory" and response["evidence"] is False,
            "Directory discovery was represented as answer evidence")

    def inspect(value):
        if isinstance(value, dict):
            require(not {"context", "content", "source_refs", "excerpt"} & value.keys(),
                    "Locator returned a source-evidence field")
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    inspect(response)


def validate_original(page, project, chapter_id, section_id, sources):
    require(page["offset"] == 0 and page["next_offset"] is None,
            "Follow-up did not read the complete page")
    require([node["id"] for node in page["breadcrumb"][:3]] == [project, chapter_id, section_id],
            "Follow-up crossed the project/chapter/section boundary")
    position = 0
    for ref in sorted(page["source_refs"], key=lambda item: item["start"]):
        require(ref["project"] == project, "Original source belongs to a different project")
        identity = (ref["project"], ref["session_id"], ref["turn_index"])
        require(identity in sources, "Original source identity is not in the frozen fixture")
        original = sources[identity]
        require(ref["start"] == position, "Original source spans overlap or leave a gap")
        require(page["content"][ref["start"]:ref["end"]]
                == original["text"][ref["turn_start"]:ref["turn_end"]],
                "Follow-up text does not match its original source coordinates")
        require(ref["message_indices"] == original["message_indices"], "Wrong original message indices")
        position = ref["end"]
    require(position == len(page["content"]) == page["total_chars"], "Source spans omit page text")


def run(output):
    from memory_book import MemoryBook
    from memory_book.directory import search_directory

    protocol = load_protocol()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", protocol)
    runtime_before = runtime_identity()
    dataset = protocol["dataset"]
    sources, chapter_expectations = original_sources(dataset)
    report = {
        "schema": SCHEMA, "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": protocol["scope"], "baseline": protocol["baseline"],
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "dataset_sha256": protocol["dataset_sha256"],
        "evaluator_sha256": protocol["evaluator_sha256"],
        "runtime_before": runtime_before, "git": git_identity(),
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "sqlite": sqlite3.sqlite_version},
        "timing_policy": "No latency metric or speed comparison is collected.",
        "cases": [], "failures": [],
    }
    write_json(output / "report.json", report)
    operations = Counter()
    chapters_followed, sections_followed, pages_followed = set(), set(), set()
    raw_path = output / "raw.jsonl"
    sequence = 0

    with raw_path.open("x", encoding="utf-8") as raw, MemoryBook(output / "archive.db", segmentation="turn") as book:
        def call(case_id, operation, request, function):
            nonlocal sequence
            sequence += 1
            operations[operation] += 1
            record = {"sequence": sequence, "case_id": case_id,
                      "operation": operation, "request": request}
            try:
                result = function()
                record["response"] = result
            except Exception as exc:
                record["error"] = {"type": type(exc).__name__, "message": str(exc)}
                raw.write(encoded(record).decode() + "\n")
                raw.flush()
                raise
            raw.write(encoded(record).decode() + "\n")
            raw.flush()
            return result

        chapter_ids = {}
        for source in dataset["sessions"]:
            result = call("ingest", "ingest", source, lambda source=source: book.ingest(source))
            chapter_ids[(source["project"], source["task_id"])] = result["chapter_id"]
        chapter_paths = {identity: path for path, identity in chapter_ids.items()}
        revision = book.revision
        report["archive"] = {"projects": len({source["project"] for source in dataset["sessions"]}),
                             "sessions": len(dataset["sessions"]), "chapters": len(chapter_ids),
                             "pages": len(sources), "revision": revision}

        for case in dataset["cases"]:
            case_id = case["id"]
            outcome = {"id": case_id, "category": case["category"], "status": "running"}
            start_sequence = sequence + 1
            seen = []
            request = dict(case["request"])
            if "chapter_ref" in request:
                request["chapter"] = chapter_ids[tuple(request.pop("chapter_ref"))]
            expected_error = case.get("expected_error")
            try:
                expected_ids = {chapter_ids[tuple(path)] for path in case.get("expected_chapters", [])}
                while True:
                    current_request = dict(request)
                    response = call(case_id, "search_directory", current_request,
                                    lambda: search_directory(book, **current_request))
                    require(expected_error is None, "Expected a scope/validation error but the API succeeded")
                    validate_navigation_shape(response)
                    require(response["revision"] == revision, "Directory revision changed without writes")
                    require(response["scope"] == {"project": request.get("project"), "chapter": request.get("chapter")},
                            "Locator inferred or changed the requested scope")
                    require(response["total"] == len(expected_ids), "Wrong number of distinct matching chapters")
                    require(len(response["results"]) <= request.get("limit", 10), "Chapter limit exceeded")
                    for item in response["results"]:
                        chapter_id, project = item["chapter_id"], item["project_id"]
                        require(chapter_id in expected_ids and chapter_id not in seen, "Unexpected or duplicate chapter")
                        seen.append(chapter_id)
                        path = chapter_paths[chapter_id]
                        expected = chapter_expectations[path]
                        require(project == path[0], "Chapter has the wrong project")
                        require(item["pages_total"] == expected["pages"], "Incorrect chapter page count")
                        require(item["sessions_total"] == len(expected["sessions"]), "Incorrect session count")
                        require(item["sections_total"] == expected["pages"], "Incorrect turn-section count")
                        require(len(item["sections"]) <= 5, "Section preview limit exceeded")
                        require(item["sections_truncated"] == (item["matching_sections_total"] > len(item["sections"])),
                                "Wrong section-preview continuation flag")
                        chapter_request = {"chapter_id": chapter_id, "project": project, "limit": 100, "page_limit": 100}
                        chapter = call(case_id, "chapter", chapter_request, lambda: book.chapter(**chapter_request))
                        chapters_followed.add(chapter_id)
                        require(chapter["project_id"] == project, "Chapter follow-up crossed projects")
                        real_sections = {section["id"] for section in chapter["sections"]}
                        for preview in item["sections"]:
                            section_id = preview["section_id"]
                            require(section_id in real_sections, "Section preview is not in the located chapter")
                            section_request = {"section_id": section_id, "project": project, "limit": 100}
                            section = call(case_id, "section", section_request, lambda: book.section(**section_request))
                            sections_followed.add(section_id)
                            require(preview["session_pk"] == section["session_pk"]
                                    and preview["session_id"] == section["session_id"], "Wrong preview session identity")
                            require(preview["pages_total"] == section["total"], "Incorrect section page count")
                            for page in section["pages"]:
                                read_request = {"page_id": page["id"], "project": project, "limit": 100000}
                                original = call(case_id, "read", read_request, lambda: book.read(**read_request))
                                pages_followed.add(page["id"])
                                validate_original(original, project, chapter_id, section_id, sources)
                    next_offset = response["next_offset"]
                    if next_offset is None:
                        break
                    require(case.get("paginate", False), "Unexpected unrequested pagination")
                    require(next_offset > request.get("offset", 0), "Pagination did not advance")
                    request["offset"] = next_offset
                require(set(seen) == expected_ids, "Pagination omitted an expected chapter")
                outcome["status"] = "passed"
            except Exception as exc:
                if expected_error is not None and type(exc).__name__ == expected_error:
                    outcome["status"] = "passed"
                    outcome["expected_error_observed"] = expected_error
                else:
                    outcome["status"] = "failed"
                    outcome["failure"] = {"type": type(exc).__name__, "message": str(exc)}
                    report["failures"].append({"case_id": case_id, **outcome["failure"]})
            outcome.update({"raw_sequence_start": start_sequence, "raw_sequence_end": sequence,
                            "returned_chapters": len(seen)})
            report["cases"].append(outcome)
            write_json(output / "report.json", report)

    runtime_after = runtime_identity()
    report["runtime_after"] = runtime_after
    if runtime_before != runtime_after:
        report["failures"].append({"type": "RuntimeChanged", "message": "Runtime bytes changed during the run"})
    if report["protocol_sha256"] != hashlib.sha256(PROTOCOL.read_bytes()).hexdigest():
        report["failures"].append({"type": "ProtocolChanged", "message": "Frozen protocol changed during the run"})
    if report["evaluator_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        report["failures"].append({"type": "EvaluatorChanged", "message": "Evaluator changed during the run"})
    report["status"] = "failed" if report["failures"] else "passed"
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {
        "logical_cases": len(report["cases"]),
        "passed_cases": sum(case["status"] == "passed" for case in report["cases"]),
        "failed_cases": sum(case["status"] == "failed" for case in report["cases"]),
        "categories": dict(Counter(case["category"] for case in report["cases"])),
        "operations": dict(operations),
        "unique_chapters_followed": len(chapters_followed),
        "unique_sections_followed": len(sections_followed),
        "unique_pages_read": len(pages_followed),
        "interpretation": "Authored contract cases and repeated follow-up reads, not answer accuracy or independent quality samples.",
    }
    report["raw_records"] = {"path": "raw.jsonl", "rows": sequence,
                             "bytes": raw_path.stat().st_size,
                             "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()}
    write_json(output / "report.json", report)
    print(json.dumps({"status": report["status"], "output": str(output),
                      "summary": report["summary"], "failures": report["failures"]}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--describe", action="store_true")
    group.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.describe:
        protocol = load_protocol()
        print(json.dumps({"schema": protocol["schema"], "scope": protocol["scope"],
                          "baseline": protocol["baseline"],
                          "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                          "dataset_sha256": protocol["dataset_sha256"],
                          "evaluator_sha256": protocol["evaluator_sha256"],
                          "sessions": len(protocol["dataset"]["sessions"]),
                          "cases": len(protocol["dataset"]["cases"])}, ensure_ascii=False, indent=2))
        return 0
    return run(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
