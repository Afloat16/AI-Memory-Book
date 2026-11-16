"""Native Book scope/directory contracts, separate from component quality."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
import traceback
import uuid

from benchmarks import engineering_components as components
from benchmarks import engineering_workflow as engineering
from benchmarks import memory_systems as legacy
from benchmarks import project_navigation_data as data
from benchmarks.competitors.memory_systems import write_json


class Probe:
    def __init__(self, identity, kind, request):
        self.row = {"case_id": identity, "kind": kind, "request": request, "calls": [], "checks": []}

    def call(self, method, function, *args, **kwargs):
        started = time.perf_counter_ns()
        value = {"method": method, "args": list(args), "kwargs": kwargs}
        try:
            value.update(status="ok", response=function(*args, **kwargs))
        except Exception as error:
            value.update(status="error", error_type=type(error).__name__, error=str(error))
        value["latency_ms"] = (time.perf_counter_ns() - started) / 1e6
        payload = value["response"] if value["status"] == "ok" else {key: value[key] for key in ("error_type", "error")}
        encoded = json.dumps(payload,
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        value["serialized_response_chars"] = len(encoded)
        value["serialized_response_utf8_bytes"] = len(encoded.encode("utf-8"))
        self.row["calls"].append(value)
        return value

    def need(self, condition, name):
        self.row["checks"].append({"check": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def response(self, call):
        self.need(call["status"] == "ok", "native_call_succeeded:" + call["method"])
        return call["response"]

    def finish(self):
        self.row["status"] = "passed"
        self.row["traffic"] = {
            "calls": len(self.row["calls"]),
            "serialized_response_chars": sum(call["serialized_response_chars"] for call in self.row["calls"]),
            "serialized_response_utf8_bytes": sum(call["serialized_response_utf8_bytes"] for call in self.row["calls"]),
            "latency_ms": sum(call["latency_ms"] for call in self.row["calls"]),
        }
        return self.row


def execute_probe(identity, kind, request, action):
    probe = Probe(identity, kind, request)
    try:
        action(probe)
        return probe.finish()
    except Exception:
        probe.row.update(status="failed", error=traceback.format_exc())
        return probe.row


def paginate(probe, method, function, *args, key, limit=2, **kwargs):
    values, offset, expected_total = [], 0, None
    for _ in range(1000):
        response = probe.response(probe.call(method, function, *args, offset=offset, limit=limit, **kwargs))
        page = response[key]
        probe.need(isinstance(page, list) and len(page) <= limit, "bounded_directory_page")
        total = response["total"]
        probe.need(type(total) is int and total >= 0, "valid_directory_total")
        if expected_total is None:
            expected_total = total
        probe.need(total == expected_total, "directory_total_stable")
        values.extend(page)
        continuation = response["next_offset"]
        if continuation is None:
            probe.need(len(values) == total, "complete_directory_pagination")
            return values
        probe.need(type(continuation) is int and continuation > offset, "forward_directory_continuation")
        offset = continuation
    raise AssertionError("directory pagination did not terminate")


def forbidden_body_keys(value):
    if isinstance(value, dict):
        return bool({"content", "text", "context"} & value.keys()) or any(forbidden_body_keys(v) for v in value.values())
    if isinstance(value, list):
        return any(forbidden_body_keys(v) for v in value)
    return False


def string_leaves(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from string_leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_leaves(item)


def directory_query(probe, book, request, documents):
    entries = paginate(probe, "search_directory", book.search_directory,
                       request["query"], request["project"], key="entries")
    identities = [entry["section_id"] for entry in entries]
    probe.need(len(identities) == len(set(identities)), "unique_directory_sections")
    for call in probe.row["calls"]:
        response = call["response"]
        probe.need(response["project"]["id"] == request["project"], "directory_exact_project")
        probe.need(response["match_fields"] == ["title", "question", "directory"], "metadata_search_fields")
        probe.need(not forbidden_body_keys(response), "directory_contains_no_source_body_fields")
        leaves = list(string_leaves(response))
        for document in documents.values():
            body = document["text"]
            assistant = body.partition("\n\nASSISTANT: ")[2]
            probe.need(not any(body in leaf or (assistant and assistant in leaf) for leaf in leaves),
                       "source_body_not_hidden_in_metadata_strings")
    for entry in entries:
        identity = entry["matched_page_id"]
        probe.need(identity in documents and documents[identity]["project"] == request["project"],
                   "directory_page_belongs_to_requested_book")
        # Each registered fixture is one short user/assistant turn. Its title
        # and question-derived section summary must contain that question only.
        probe.need(entry["title"] == documents[identity]["title"], "directory_original_question_title")
        probe.need(entry["summary"] == documents[identity]["title"], "directory_question_only_summary")
        probe.need(entry["breadcrumb"][0]["id"] == request["project"], "directory_breadcrumb_scope")
        probe.need(all(ref["project"] == request["project"] for ref in entry["source_refs"]),
                   "directory_reference_scope")
    if request["kind"] in ("body_only", "missing"):
        probe.need(not entries, "nonmetadata_text_does_not_match_directory")
    else:
        probe.need(any(entry["session_id"] == "active-config" for entry in entries),
                   "known_metadata_address_discoverable")


def read_chunks(probe, method, function, *args, project=None, source_hash=None):
    offset, pieces, total, revision_hash = 0, [], None, source_hash
    for _ in range(10000):
        kwargs = {"offset": offset, "limit": 128}
        if project is not None:
            kwargs["project"] = project
        if method == "read_turn" and revision_hash is not None:
            kwargs["source_hash"] = revision_hash
        response = probe.response(probe.call(method, function, *args, **kwargs))
        probe.need(response["offset"] == offset and len(response["content"]) <= 128, "bounded_exact_read_window")
        if total is None:
            total = response["total_chars"]
        probe.need(response["total_chars"] == total, "read_total_stable")
        if revision_hash is None:
            revision_hash = response["source_hash"]
        probe.need(response["source_hash"] == revision_hash, "source_revision_stable")
        if method == "read_turn":
            ref = response["source_ref"]
            probe.need((ref["project"], ref["session_id"], ref["turn_index"]) == tuple(args), "turn_source_identity")
            probe.need((ref["start"], ref["end"], ref["turn_start"], ref["turn_end"]) ==
                       (0, len(response["content"]), offset, offset + len(response["content"])), "turn_window_coordinates")
            probe.need(response["message_indices"] == [0, 1], "turn_message_identity")
        else:
            probe.need(response["breadcrumb"][0]["id"] == project, "page_read_project_guard")
        pieces.append(response["content"])
        continuation = response["next_offset"]
        if continuation is None:
            joined = "".join(pieces)
            probe.need(len(joined) == total, "complete_read_pagination")
            return joined, response, revision_hash
        probe.need(type(continuation) is int and continuation == offset + len(response["content"])
                   and continuation > offset, "contiguous_read_continuation")
        offset = continuation
    raise AssertionError("read pagination did not terminate")


def directory_roundtrip(probe, book, project, originals, addresses):
    # These are caller-known address descriptors, not expected quotes or policy.
    chapters = paginate(probe, "toc", book.toc, project, key="chapters")
    probe.need(all(chapter["project_id"] == project for chapter in chapters), "toc_project_scope")
    matches = [chapter for chapter in chapters if chapter["task_id"] == "task:" + data.MAIN_TASK]
    probe.need(len(matches) == 1, "exact_task_id_selected_despite_title_collision")
    chapter = matches[0]
    sections = paginate(probe, "chapter", book.chapter, chapter["id"], project=project,
                        key="sections", page_limit=1)
    matches = [section for section in sections if section["session_id"] == "active-config"]
    probe.need(len(matches) == 1, "caller_known_session_address_found")
    section = matches[0]
    pages = paginate(probe, "section", book.section, section["id"], project=project, key="pages", limit=1)
    probe.need(len(pages) == 1, "registered_short_source_has_one_page")
    page_id = pages[0]["id"]
    page_body, page, source_hash = read_chunks(probe, "read", book.read, page_id, project=project)
    probe.need(bool(page["source_refs"]), "page_exposes_original_source")
    ref = page["source_refs"][0]
    source_id = (ref["project"], ref["session_id"], ref["turn_index"])
    body, _, _ = read_chunks(probe, "read_turn", book.read_turn, *source_id, source_hash=source_hash)
    probe.need(source_id in originals and body == originals[source_id], "exact_original_turn_reconstruction")
    probe.need(page_body == body, "registered_page_and_original_turn_equal")
    probe.row["resolved_address"] = {"project": project, "chapter_id": chapter["id"],
                                     "section_id": section["id"], "page_id": page_id,
                                     "source": list(source_id)}
    addresses[project] = probe.row["resolved_address"]


def wrong_book(probe, book, project, foreign, kind):
    name = "read" if kind == "page" else kind
    method = getattr(book, name)
    identity = foreign[kind + "_id"]
    control = probe.call(name, method, identity, project=foreign["project"], limit=1)
    probe.need(control["status"] == "ok", "same_book_control_supported_and_readable")
    mismatch = probe.call(name, method, identity, project=project, limit=1)
    probe.need(mismatch["status"] == "error" and mismatch["error_type"] in ("KeyError", "ValueError"),
               "wrong_book_address_refused")


def scope_contracts(state, record=None):
    from memory_book import MemoryBook

    rows = []
    sources = [{"project": project, "session_id": "shared", "task_id": "task",
                "created_at": "2026-01-01T00:00:00Z", "messages": [
                    {"role": "user", "content": "scopecontracttoken record"},
                    {"role": "assistant", "content": f"scopecontracttoken exact value {value}."}]}
               for project, value in (("scope-a", "ALPHA17"), ("scope-ab", "BETA91"))]
    with MemoryBook(state / "scope-contracts.db", cache_size=4) as book:
        def request(identity, kwargs, expected, projects=()):
            def action(probe):
                value = probe.call("recall", book.recall, "scopecontracttoken", **kwargs)
                if expected == "error":
                    probe.need(value["status"] == "error" and value["error_type"] == "ValueError",
                               "ambiguous_or_invalid_scope_refused")
                else:
                    response = probe.response(value)
                    found = {ref["project"] for hit in response["results"] for ref in hit["source_refs"]}
                    probe.need(found == set(projects), "resolved_scope_has_exact_expected_projects")
            row = execute_probe("scope:" + identity, "scope", {"kwargs": kwargs, "expected": expected,
                                                               "expected_projects": list(projects)}, action)
            rows.append(row)
            if record is not None:
                record(row)

        request("empty", {}, "ok")
        book.ingest(sources[0])
        request("sole-book", {}, "ok", ["scope-a"])
        book.ingest(sources[1])
        chapter = next(item for item in book.toc("scope-a")["chapters"] if item["task_id"] == "task:task")
        request("multiple-books", {}, "error")
        request("multiple-books-limit-one", {"limit": 1}, "error")
        request("multiple-books-session-only", {"session": "shared"}, "error")
        request("known-chapter", {"chapter": chapter["id"]}, "ok", ["scope-a"])
        request("deliberate-global", {"all_projects": True}, "ok", ["scope-a", "scope-ab"])
        request("empty-project", {"project": ""}, "error")
        request("whitespace-project", {"project": "   "}, "error")
        request("unknown-project", {"project": "scope-missing"}, "ok")
        request("conflicting-project-chapter", {"project": "scope-ab", "chapter": chapter["id"]}, "ok")
        request("project-and-global", {"project": "scope-a", "all_projects": True}, "error")
        request("explicit-project", {"project": "scope-a"}, "ok", ["scope-a"])
        request("nonboolean-global", {"all_projects": 1}, "error")
    return rows, sources


def run_contracts(output, cache):
    import memory_book
    from memory_book import MemoryBook
    from benchmarks.project_navigation import source_identity

    output, cache = legacy.fresh_output(output), Path(cache).resolve()
    state = cache / "navigation-contracts" / uuid.uuid4().hex
    state.mkdir(parents=True)
    runtime_before, evaluator_before = engineering.runtime_identity(memory_book), source_identity()
    rows, visible, addresses = [], {}, {}
    with (output / "raw.jsonl").open("x", encoding="utf-8") as stream:
        def record(row):
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()

        try:
            with MemoryBook(state / "book.db", cache_size=0) as book:
                for step in data.workload():
                    for source in step["sessions"]:
                        book.ingest(source)
                        visible[(source["project"], source["session_id"])] = source
                originals = engineering.visible_sources(visible)
                documents = components.export_documents(book, visible)
                lookup = {doc["id"]: doc for doc in documents}
                write_json(output / "sources.json", list(visible.values()))
                write_json(output / "documents.json", documents)
                write_json(output / "directory-requests.json", data.directory_queries())
                def registry(probe):
                    projects = probe.response(probe.call("projects", book.projects))
                    probe.need({project["id"] for project in projects} == set(data.PROJECT_IDS), "exact_project_registry")
                    probe.need(len(projects) == len(data.PROJECT_IDS), "unique_project_registry")
                    probe.need(all(project["name"] == data.PROJECT_NAME for project in projects), "display_name_collision_retained")
                record(execute_probe("registry", "registry", {}, registry))
                for request in data.directory_queries():
                    record(execute_probe(request["id"], "directory", request,
                                         lambda probe, request=request: directory_query(probe, book, request, lookup)))
                for project in data.PROJECT_IDS:
                    record(execute_probe("roundtrip:" + project, "roundtrip",
                                         {"project": project, "task_id": data.MAIN_TASK, "session_id": "active-config"},
                                         lambda probe, project=project: directory_roundtrip(probe, book, project, originals, addresses)))
                for index, project in enumerate(data.PROJECT_IDS):
                    neighbor = data.PROJECT_IDS[(index + 1) % len(data.PROJECT_IDS)]
                    for kind in ("chapter", "section", "page"):
                        record(execute_probe(f"wrong-book:{project}:{kind}", "wrong_book",
                                             {"project": project, "foreign_project": neighbor, "address_kind": kind},
                                             lambda probe, project=project, neighbor=neighbor, kind=kind:
                                             wrong_book(probe, book, project, addresses[neighbor], kind)))
        except Exception:
            record({"case_id": "directory-runner", "kind": "runner", "status": "failed",
                    "request": {}, "calls": [], "checks": [], "error": traceback.format_exc()})
        try:
            _, scope_sources = scope_contracts(state, record=record)
            write_json(output / "scope-sources.json", scope_sources)
        except Exception:
            record({"case_id": "scope-runner", "kind": "runner", "status": "failed",
                    "request": {}, "calls": [], "checks": [], "error": traceback.format_exc()})
    runtime_after, evaluator_after = engineering.runtime_identity(memory_book), source_identity()
    failures = [{"case_id": row["case_id"], "stage": row["kind"], "error": row.get("error", "Failed contract")}
                for row in rows if row["status"] != "passed"]
    if runtime_before != runtime_after or evaluator_before != evaluator_after:
        failures.append({"stage": "identity", "error": "Runtime or evaluator changed during contracts"})
    report = {"version": "book-navigation-contracts-v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Native Python Book API engineering contracts; not competitor or ACL quality scores",
              "traffic_scope": "Canonical JSON serialization of core return values/error descriptions; not MCP/HTTP wire bytes or model tokens",
              "status": "passed" if not failures else "failed", "runtime": runtime_before, "evaluator": evaluator_before,
              "runtime_unchanged": runtime_before == runtime_after, "evaluator_unchanged": evaluator_before == evaluator_after,
              "runtime_final_sha256": runtime_after["sha256"], "evaluator_final_sha256": evaluator_after["sha256"],
              "dataset_sha256": engineering.sha(data.workload()), "case_count": len(rows),
              "kinds": {kind: {"cases": sum(row["kind"] == kind for row in rows),
                                "passed": sum(row["kind"] == kind and row["status"] == "passed" for row in rows)}
                        for kind in sorted({row["kind"] for row in rows})},
              "failures": failures, "records": [{"case_id": row["case_id"], "kind": row["kind"],
                                                   "status": row["status"], "traffic": row.get("traffic")}
                                                  for row in rows]}
    write_json(output / "report.json", report)
    return report
