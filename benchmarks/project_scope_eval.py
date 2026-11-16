"""Execute an authored project-scope contract diagnostic without a model.

This is development/regression evidence, not retrieval accuracy, an access-control
audit, or an external-product benchmark. The old API's intentionally global reads
are controls. An unsupported ``project`` argument is never a successful rejection.
Run this unchanged evaluator against separate imported baseline/candidate trees.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile


VERSION = "project-scope-development-v1"
PROJECTS = ("similar/alpha", "similar/alpha-copy", "similar/beta", "Similar/alpha")
FOLLOWUPS = ("chapter", "section", "read")
VOLATILE_KEYS = frozenset(("latency_ms", "cache_hit", "updated_at"))


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def original_turn(session):
    return "\n\n".join(f"{message['role'].upper()}: {message['content']}"
                        for message in session["messages"])


def workload():
    """Four distinct IDs share all human-readable and task/session names."""
    sessions = []
    for kind, day in (("decision", 1), ("constraint", 2), ("long-log", 3)):
        for index, project in enumerate(PROJECTS):
            marker = f"scope_marker_{index + 1}"
            if kind == "decision":
                question = "What is the retry_limit for this service?"
                answer = (f"retry_limit={11 + index}. The approved service setting belongs to {marker}. "
                          "Other engineering projects can use a conflicting setting.")
            elif kind == "constraint":
                question = "What is the retry safety constraint?"
                answer = (f"The service must preserve request ordering and return the original error. "
                          f"This project's constraint owner is {marker}.")
            else:
                question = "Which diagnostic records belong to this service?"
                answer = "\n\n".join(
                    f"Record {n}: {marker} observed a service retry; preserve the original response "
                    "when the worker restarts. This is diagnostic history, not a configuration change."
                    for n in range(12))
            sessions.append({"project": project, "project_name": "same-service",
                             "session_id": kind, "task_id": "service-runtime",
                             "task_title": "same runtime task", "title": "same service discussion",
                             "created_at": f"2026-10-{day:02d}T09:00:00+00:00",
                             "messages": [{"role": "user", "content": question},
                                          {"role": "assistant", "content": answer}]})
    replacement = json.loads(json_bytes(sessions[0]))
    replacement["messages"][1]["content"] = replacement["messages"][1]["content"].replace(
        "retry_limit=11.", "retry_limit=111.")
    return {"projects": list(PROJECTS), "sessions": sessions, "replacement": replacement,
            "same_names": ["project_name", "task_id", "task_title", "session_id", "title"],
            "budgets": {"recall_chars": 2400, "recall_limit": 5,
                        "directory_limit": 1, "page_read_limit": 47}}


def runtime_identity(module):
    root = Path(inspect.getfile(module)).resolve().parent
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob("*.py"))}
    return {"imported_runtime_root": str(root), "files": files, "sha256": digest(files)}


def canonical_response(value):
    """Keep all evidence/IDs/coordinates, omitting only explicitly volatile data.

    Project creation times are ingestion wall-clock metadata, unlike session and
    evidence creation times. Only their exact location in toc/project responses
    is normalized. No evidence content or source reference is normalized.
    """
    if isinstance(value, list):
        return [canonical_response(item) for item in value]
    if isinstance(value, dict):
        result = {key: canonical_response(item) for key, item in value.items()
                  if key not in VOLATILE_KEYS}
        if "project" in result and isinstance(result["project"], dict):
            result["project"].pop("created_at", None)
        if {"chapters", "sessions", "pages", "name", "id"} <= result.keys():
            result.pop("created_at", None)
        return result
    return value


def recall_errors(response, project, sources, quote=None, cache_hit=None):
    errors = []
    if response.get("context_chars") != len(response.get("context", "")):
        errors.append("incorrect context character count")
    if len(response.get("context", "")) > 2400:
        errors.append("context budget exceeded")
    if not response.get("results"):
        errors.append("expected in-project evidence is missing")
    if quote and quote not in response.get("context", ""):
        errors.append("required source quote is missing")
    if cache_hit is not None and response.get("cache_hit") is not cache_hit:
        errors.append("cache hit state differs from the requested warm/cold state")
    for hit in response.get("results", []):
        text = hit.get("text", "")
        if text not in response.get("context", ""):
            errors.append("returned snippet is absent from context")
        covered = [False] * len(text)
        if not hit.get("source_refs"):
            errors.append("missing source references")
        for ref in hit.get("source_refs", []):
            identity = (ref.get("project"), ref.get("session_id"), ref.get("turn_index"))
            source = sources.get(identity)
            lo, hi = ref.get("turn_start"), ref.get("turn_end")
            if identity[0] != project:
                errors.append("cross-project source reference")
            if source is None or type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(source):
                errors.append("invalid source coordinates")
                continue
            fragment = source[lo:hi]
            position = text.find(fragment)
            if position < 0 or ref.get("end", 0) - ref.get("start", 0) != hi - lo:
                errors.append("snippet differs from its cited source")
                continue
            for i in range(position, position + len(fragment)):
                covered[i] = True
        if any(not seen and not char.isspace() and char != "…" for seen, char in zip(covered, text)):
            errors.append("snippet contains unsupported text")
    return errors


def page_errors(response, project, sources):
    errors = []
    if not response.get("breadcrumb") or response["breadcrumb"][0].get("id") != project:
        errors.append("wrong project breadcrumb")
    text = response.get("content", "")
    offset = response.get("offset", 0)
    covered = [False] * len(text)
    if not response.get("source_refs") and text:
        errors.append("page text has no source references")
    for ref in response.get("source_refs", []):
        source = sources.get((ref.get("project"), ref.get("session_id"), ref.get("turn_index")))
        lo, hi = ref.get("turn_start"), ref.get("turn_end")
        a, b = ref.get("start"), ref.get("end")
        if ref.get("project") != project:
            errors.append("page reference is from a different project")
        if (source is None or any(type(v) is not int for v in (lo, hi, a, b))
                or not 0 <= lo < hi <= len(source) or not offset <= a < b <= offset + len(text)):
            errors.append("invalid page source coordinates")
            continue
        if source[lo:hi] != text[a - offset:b - offset]:
            errors.append("page text differs from cited source")
        for i in range(a - offset, b - offset):
            covered[i] = True
    if any(not seen and not char.isspace() for seen, char in zip(covered, text)):
        errors.append("unattributed page text")
    return errors


def directory_source_errors(project, pages, sources):
    """Require the directory walk to cover original source text independently.

    Directory counts and IDs alone could agree with one another while omitting a
    page. Coverage is checked against the authored session text instead.
    """
    wanted = {identity: [False] * len(text) for identity, text in sources.items() if identity[0] == project}
    errors = []
    for page in pages:
        errors.extend(page_errors(page, project, sources))
        if page.get("offset") != 0 or page.get("next_offset") is not None:
            errors.append("directory completeness received a partial page")
        for ref in page.get("source_refs", []):
            identity = (ref.get("project"), ref.get("session_id"), ref.get("turn_index"))
            covered = wanted.get(identity)
            lo, hi = ref.get("turn_start"), ref.get("turn_end")
            if covered is not None and type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(covered):
                for position in range(lo, hi):
                    covered[position] = True
    for identity, covered in wanted.items():
        if any(not seen and not char.isspace() for seen, char in zip(covered, sources[identity])):
            errors.append(f"directory omitted original source text: {identity[1]}")
    return errors


def classify_outcome(expected, response, error, supported, validator):
    """An absent API, arbitrary exception, or empty answer cannot fake a pass."""
    if not supported and error and error["type"] == "TypeError":
        return "unsupported", ["this runtime does not accept the project assertion"]
    if expected in ("KeyError", "ValueError"):
        return ("passed", []) if error and error["type"] == expected else (
            "failed", [f"expected {expected}; got {error['type'] if error else 'a successful response'}"])
    if error:
        return "failed", [f"unexpected {error['type']}"]
    errors = validator(response) if validator else []
    return ("failed" if errors else "passed"), errors


def summarize(rows):
    return {category: dict(Counter(row["outcome"] for row in rows if row["category"] == category))
            for category in sorted({row["category"] for row in rows})}


def run(output):
    import memory_book
    from memory_book import MemoryBook
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reserved = ("dataset.json", "raw.jsonl", "report.json")
    if any((output / name).exists() for name in reserved):
        raise ValueError("output already contains a run; choose a fresh directory")
    dataset = workload()
    (output / "dataset.json").write_bytes(json.dumps(dataset, ensure_ascii=False, indent=2).encode() + b"\n")
    before = runtime_identity(memory_book)
    evaluator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    capabilities = {method: "project" in inspect.signature(getattr(MemoryBook, method)).parameters
                    for method in FOLLOWUPS}
    sources = {(s["project"], s["session_id"], 0): original_turn(s) for s in dataset["sessions"]}
    rows, identities = [], {}
    with tempfile.TemporaryDirectory(prefix="project-scope-") as temporary, \
            MemoryBook(Path(temporary) / "memory.db") as book, \
            (output / "raw.jsonl").open("w", encoding="utf-8") as trace:
        for source in dataset["sessions"]:
            book.ingest(source)
        for project in PROJECTS:
            chapter = book.chapter(book.toc(project)["chapters"][0]["id"])
            sections = chapter["sections"]
            decision = next(section for section in sections if section["session_id"] == "decision")
            identities[project] = {"chapter": chapter["id"], "section": decision["id"],
                                   "page": decision["pages"][0]["id"],
                                   "sections": [section["id"] for section in sections],
                                   "pages": [page["id"] for section in sections for page in section["pages"]]}

        def capture(case_id, category, method, args=(), kwargs=None, *, expected="response",
                    validator=None, require_assertion=False, compatibility=False):
            kwargs = kwargs or {}
            response = error = None
            try:
                response = getattr(book, method)(*args, **kwargs)
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
            supported = not require_assertion or capabilities[method]
            outcome, errors = classify_outcome(expected, response, error, supported, validator)
            row = {"case_id": case_id, "category": category, "operation": method,
                   "arguments": {"positional": list(args), "keywords": kwargs},
                   "expected": expected, "capability_supported": supported,
                   "outcome": outcome, "validation_errors": errors,
                   "response": response, "error": error, "compatibility_case": compatibility}
            if response is not None:
                row["canonical_response_sha256"] = digest(canonical_response(response))
            rows.append(row)
            trace.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            trace.flush()
            return response

        def equal(actual, expected, message):
            return [] if actual == expected else [message]

        for index, project in enumerate(PROJECTS):
            ids = identities[project]
            recall_kwargs = {"project": project, "session": "decision", "temporal": "relevance"}
            capture(f"{index}:recall-cold", "explicit_project_recall", "recall", ("retry_limit",), recall_kwargs,
                    validator=lambda r, p=project, i=index: recall_errors(r, p, sources, f"retry_limit={11+i}.", False),
                    compatibility=True)
            capture(f"{index}:legacy-read", "global_read_control", "read", (ids["page"],),
                    validator=lambda r, p=project: page_errors(r, p, sources), compatibility=True)
            capture(f"{index}:legacy-chapter", "legacy_directory", "chapter", (ids["chapter"],),
                    validator=lambda r, p=project: equal(r["project_id"], p, "wrong project chapter"),
                    compatibility=True)
            capture(f"{index}:legacy-section", "legacy_directory", "section", (ids["section"],),
                    validator=lambda r, i=ids: equal([p["id"] for p in r["pages"]], [i["page"]], "wrong pages"),
                    compatibility=True)
            capture(f"{index}:scoped-read", "asserted_followup", "read", (ids["page"],), {"project": project},
                    validator=lambda r, p=project: page_errors(r, p, sources), require_assertion=True)
            capture(f"{index}:scoped-read-slice", "asserted_followup", "read", (ids["page"],),
                    {"project": project, "offset": 13, "limit": 47},
                    validator=lambda r, p=project: page_errors(r, p, sources) + equal(len(r["content"]), 47, "wrong slice length"),
                    require_assertion=True)
            capture(f"{index}:scoped-chapter", "asserted_followup", "chapter", (ids["chapter"],), {"project": project},
                    validator=lambda r, p=project: equal(r["project_id"], p, "wrong project chapter"), require_assertion=True)
            capture(f"{index}:scoped-section", "asserted_followup", "section", (ids["section"],), {"project": project},
                    validator=lambda r, i=ids: equal([p["id"] for p in r["pages"]], [i["page"]], "wrong pages"),
                    require_assertion=True)
            other = PROJECTS[(index + 1) % len(PROJECTS)]
            capture(f"{index}:conflicting-recall-chapter", "conflicting_recall_filter", "recall", ("retry_limit",),
                    {"project": project, "chapter": identities[other]["chapter"]},
                    validator=lambda r: equal((r["results"], r["context"]), ([], ""), "mismatched filter returned evidence"),
                    compatibility=True)

        # Return to each cache key after the other projects have populated theirs.
        for index, project in enumerate(PROJECTS):
            capture(f"{index}:recall-hot-after-other-projects", "interleaved_hot_cache", "recall", ("retry_limit",),
                    {"project": project, "session": "decision", "temporal": "relevance"},
                    validator=lambda r, p=project, i=index: recall_errors(r, p, sources, f"retry_limit={11+i}.", True),
                    compatibility=True)
            for foreign in PROJECTS:
                if foreign == project:
                    continue
                for method, key in (("chapter", "chapter"), ("section", "section"), ("read", "page")):
                    capture(f"{index}:foreign-{PROJECTS.index(foreign)}-{method}", "foreign_id_assertion", method,
                            (identities[foreign][key],), {"project": project}, expected="KeyError", require_assertion=True)
            for method, key in (("chapter", "chapter"), ("section", "section"), ("read", "page")):
                capture(f"{index}:unknown-project-{method}", "unknown_project_assertion", method,
                        (identities[project][key],), {"project": "missing-project"}, expected="KeyError", require_assertion=True)

        for invalid in ("", "   ", 12):
            for method, key in (("chapter", "chapter"), ("section", "section"), ("read", "page")):
                capture(f"invalid-{repr(invalid)}-{method}", "invalid_project_assertion", method,
                        (identities[PROJECTS[0]][key],), {"project": invalid}, expected="ValueError", require_assertion=True)

        # Both old and new unbound APIs deliberately permit global discovery.
        capture("unbound-session-collision", "unbound_global_control", "recall", ("retry_limit",),
                {"session": "decision", "temporal": "relevance"},
                validator=lambda r: equal({ref["project"] for hit in r["results"] for ref in hit["source_refs"]},
                                          set(PROJECTS), "global control did not retrieve all four project sources"),
                compatibility=True)

        # Browse every section/page through explicit scope, using actual returned IDs.
        for index, project in enumerate(PROJECTS):
            ids = identities[project]
            chapter = capture(f"{index}:directory-first-chapter", "paginated_directory", "chapter", (ids["chapter"],),
                              {"project": project, "limit": 1, "page_limit": 1}, require_assertion=True,
                              validator=lambda r: equal((len(r["sections"]), r["next_offset"]), (1, 1), "invalid chapter pagination"))
            if chapter is None:
                continue
            observed_sections, observed_pages, full_pages = [], [], []
            offset = 0
            while chapter is not None:
                for section in chapter["sections"]:
                    observed_sections.append(section["id"])
                    page_offset = 0
                    while True:
                        directory = capture(f"{index}:section-{len(observed_sections)}-offset-{page_offset}",
                                            "paginated_directory", "section", (section["id"],),
                                            {"project": project, "offset": page_offset, "limit": 1}, require_assertion=True,
                                            validator=lambda r: [] if len(r["pages"]) == 1 else ["page directory is missing or unbounded"])
                        if directory is None:
                            break
                        for page in directory["pages"]:
                            observed_pages.append(page["id"])
                            full = capture(f"{index}:page-{page['id']}-full", "complete_source_read", "read", (page["id"],),
                                           {"project": project}, require_assertion=True,
                                           validator=lambda r, p=project: page_errors(r, p, sources))
                            if full is not None:
                                full_pages.append(full)
                            capture(f"{index}:page-{page['id']}-slice", "paginated_source_read", "read", (page["id"],),
                                    {"project": project, "offset": 0, "limit": 47}, require_assertion=True,
                                    validator=lambda r, p=project: page_errors(r, p, sources))
                        if directory["next_offset"] is None:
                            break
                        next_offset = directory["next_offset"]
                        if type(next_offset) is not int or next_offset <= page_offset:
                            raise ValueError("non-advancing section pagination")
                        page_offset = next_offset
                if chapter["next_offset"] is None:
                    break
                next_offset = chapter["next_offset"]
                if type(next_offset) is not int or next_offset <= offset:
                    raise ValueError("non-advancing chapter pagination")
                offset = next_offset
                chapter = capture(f"{index}:directory-chapter-offset-{offset}", "paginated_directory", "chapter", (ids["chapter"],),
                                  {"project": project, "offset": offset, "limit": 1, "page_limit": 1}, require_assertion=True,
                                  validator=lambda r: [] if len(r["sections"]) == 1 else ["chapter directory is missing or unbounded"])
            capture(f"{index}:directory-complete", "directory_completeness", "toc", (project,),
                    validator=lambda r, i=ids, s=observed_sections, p=observed_pages, f=full_pages, scope=project:
                        equal(s, i["sections"], "missing/repeated sections") + equal(p, i["pages"], "missing/repeated pages")
                        + directory_source_errors(scope, f, sources))

        replacement = dataset["replacement"]
        capture("replace-source", "source_replacement", "ingest", (replacement,))
        sources[(replacement["project"], replacement["session_id"], 0)] = original_turn(replacement)
        capture("old-page-after-replace", "source_replacement", "read", (identities[PROJECTS[0]]["page"],),
                expected="KeyError", compatibility=True)
        for index, project in enumerate(PROJECTS):
            expected_value = 111 if index == 0 else 11 + index
            capture(f"{index}:recall-after-replacement", "source_replacement", "recall", ("retry_limit",),
                    {"project": project, "session": "decision", "temporal": "relevance"},
                    validator=lambda r, p=project, v=expected_value: recall_errors(r, p, sources, f"retry_limit={v}.", False),
                    compatibility=True)
        removed = PROJECTS[1]
        capture("delete-one-project", "project_deletion", "delete_project", (removed,),
                validator=lambda r: equal(r, True, "expected existing project to be deleted"))
        capture("deleted-project-recall", "project_deletion", "recall", ("retry_limit",), {"project": removed},
                validator=lambda r: equal((r["results"], r["context"]), ([], ""), "deleted project remains visible"), compatibility=True)
        capture("deleted-project-page", "project_deletion", "read", (identities[removed]["page"],), expected="KeyError", compatibility=True)
        for index in (0, 2, 3):
            project = PROJECTS[index]
            value = 111 if index == 0 else 11 + index
            capture(f"{index}:survivor-recall", "project_deletion", "recall", ("retry_limit",),
                    {"project": project, "session": "decision", "temporal": "relevance"},
                    validator=lambda r, p=project, v=value: recall_errors(r, p, sources, f"retry_limit={v}.", False),
                    compatibility=True)

    after = runtime_identity(memory_book)
    failures = [row["case_id"] for row in rows if row["outcome"] == "failed"]
    stable = before == after and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == evaluator_hash
    report = {"version": VERSION, "status": "completed" if stable and not failures else "completed_with_failures",
              "evidence_level": "authored_development_contract_diagnostic",
              "created_at": datetime.now(timezone.utc).isoformat(), "runtime": before,
              "runtime_unchanged": before == after, "evaluator_sha256": evaluator_hash,
              "evaluator_unchanged": hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == evaluator_hash,
              "dataset_sha256": digest(dataset), "raw_sha256": hashlib.sha256((output / "raw.jsonl").read_bytes()).hexdigest(),
              "capabilities": capabilities, "projects": len(PROJECTS), "source_sessions": len(dataset["sessions"]),
              "identities": identities, "calls": len(rows), "summary": summarize(rows),
              "outcomes": dict(Counter(row["outcome"] for row in rows)), "failed_case_ids": failures,
              "compatibility_cases": {row["case_id"]: {"response_sha256": row.get("canonical_response_sha256"),
                                      "error": row["error"], "outcome": row["outcome"]}
                                      for row in rows if row["compatibility_case"]},
              "canonicalization": {"omitted_keys": sorted(VOLATILE_KEYS),
                                   "additional_omission": "project directory creation timestamps only; source created_at is retained"},
              "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
              "limitations": ["Synthetic development/regression inputs; no holdout, model, external product or production workload.",
                              "Project IDs are supplied by the caller; this does not infer which project the user intended.",
                              "The unbound API intentionally permits global reads; project filtering is not user access control.",
                              "Unsupported project assertions are recorded separately, never counted as successful rejection.",
                              "Directory/core contracts do not establish MCP/CLI/HTTP end-to-end behavior.",
                              "Counts are contract checks, not retrieval accuracy, answer accuracy, speed or security guarantees."]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def compare_reports(baseline, candidate):
    for key in ("version", "dataset_sha256", "evaluator_sha256", "canonicalization"):
        if baseline[key] != candidate[key]:
            raise ValueError(f"cannot compare different {key}")
    left, right = baseline["compatibility_cases"], candidate["compatibility_cases"]
    ids = sorted(set(left) | set(right))
    differences = [{"case_id": case_id, "baseline": left.get(case_id), "candidate": right.get(case_id)}
                   for case_id in ids if left.get(case_id) != right.get(case_id)]
    return {"version": VERSION, "dataset_sha256": candidate["dataset_sha256"],
            "evaluator_sha256": candidate["evaluator_sha256"], "compared_cases": len(ids),
            "equal_cases": len(ids) - len(differences), "differences": differences,
            "baseline_runtime_sha256": baseline["runtime"]["sha256"], "candidate_runtime_sha256": candidate["runtime"]["sha256"],
            "baseline_outcomes": baseline["outcomes"], "candidate_outcomes": candidate["outcomes"],
            "comparison_scope": "Complete canonical JSON responses or exact errors for existing documented APIs; new project assertions scored separately.",
            "status": "matched" if not differences else "different"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-baseline", type=Path)
    args = parser.parse_args()
    report = run(args.output)
    if args.compare_baseline:
        comparison = compare_reports(json.loads(args.compare_baseline.read_text()), report)
        (args.output / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "calls": report["calls"], "outcomes": report["outcomes"],
                      "runtime": report["runtime"]["sha256"], "output": str(args.output)}))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
