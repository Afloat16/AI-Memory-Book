"""Frozen public-source retrieval holdout, with offline provenance verification.

``check`` and ``self-test`` import no MemoryBook and execute zero retrieval calls.
``run`` requires exact committed evaluator and runtime identities. Never tune a
runtime against this holdout and continue to describe that runtime as unseen.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = "benchmarks/experiments/v014-public-holdout.json"
MANIFEST_PATH = "benchmarks/experiments/v014-public-holdout-provenance.json"
SCRIPT_PATH = "scripts/evaluate_v014_public_holdout.py"
PROTOCOL_ID = "v014-public-source-holdout-1"
ROLE_PREFIX = "ASSISTANT: "
FROZEN_FILES = (PROTOCOL_PATH, MANIFEST_PATH, SCRIPT_PATH)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def date(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "A source timestamp has no timezone")
    return result


def source_text(source):
    excerpt = source["excerpt"]
    return source["full_file"]["text"][excerpt["start"]:excerpt["end"]]


def original_turn(source):
    return ROLE_PREFIX + source_text(source)


def load_inputs():
    protocol_raw = (ROOT / PROTOCOL_PATH).read_bytes()
    manifest_raw = (ROOT / MANIFEST_PATH).read_bytes()
    protocol = json.loads(protocol_raw)
    manifest = json.loads(manifest_raw)
    require(protocol["protocol"] == manifest["protocol"] == PROTOCOL_ID,
            "Protocol labels differ")
    require(sha(manifest_raw) == protocol["manifest_sha256"], "Frozen manifest hash differs")
    require(sha((ROOT / SCRIPT_PATH).read_bytes()) == protocol["evaluator_sha256"],
            "Frozen evaluator hash differs; retain original and register a new protocol")
    for key in ("sources", "questions", "licenses", "commit_metadata"):
        require(sha(encoded(manifest[key])) == manifest["integrity"][key + "_sha256"],
                "Manifest component digest differs: " + key)
    source_ids, identities = {}, set()
    for source in manifest["sources"]:
        sid = source["id"]
        identity = source["project"], source["session_id"]
        require(sid not in source_ids and identity not in identities, "Duplicate source identity")
        source_ids[sid] = source
        identities.add(identity)
        full = source["full_file"]
        raw = full["text"].encode("utf-8")
        require(len(raw) == full["utf8_bytes"] and sha(raw) == full["sha256"],
                "Captured source bytes differ")
        require(git_blob(raw) == full["git_blob_sha1"] == full["upstream_tree_blob_sha1"],
                "Source does not match the exact upstream Git tree blob")
        require(source["project"] == "public:" + source["repository"], "Source namespace differs")
        commit = manifest["commit_metadata"][source["commit_metadata_key"]]
        require(source["commit"] == commit["commit"] and source["repository"] == commit["repository"]
                and source["tag"] == commit["tag_observed"], "Commit metadata binding differs")
        require(date(source["created_at"]) == date(commit["committer_date"]),
                "Ingested source time differs from the actual release commit")
        date(commit["author_date"])
        excerpt = source["excerpt"]
        lo, hi = excerpt["start"], excerpt["end"]
        require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(full["text"]),
                "Invalid source excerpt coordinates")
        require(sha(source_text(source).encode()) == excerpt["sha256"], "Excerpt bytes differ")
        require(len(full["text"][:lo].encode()) == excerpt["start_byte"]
                and len(full["text"][:hi].encode()) == excerpt["end_byte"],
                "UTF-8 excerpt coordinates differ")
        require(source_text(source).strip() == source_text(source),
                "Source normalization would alter the registered excerpt")
        require(source["license_sha256"] in manifest["licenses"], "Missing upstream license")
    for key, license_record in manifest["licenses"].items():
        raw = license_record["text"].encode()
        require(sha(raw) == key == license_record["sha256"]
                and git_blob(raw) == license_record["git_blob_sha1"], "License bytes differ")
    ids = set()
    for question in manifest["questions"]:
        require(question["id"] not in ids, "Duplicate question identity")
        ids.add(question["id"])
        require(question["temporal"] in {"relevance", "current"}, "Unregistered temporal mode")
        require(question["kind"] in {"answerable", "missing"}, "Unknown question kind")
        require(bool(question["required"]) == (question["kind"] == "answerable"),
                "Gold availability differs from question kind")
        for gold in question["required"]:
            source = source_ids[gold["source_id"]]
            require(source["project"] == question["project"], "Gold crosses project scope")
            lo, hi = gold["start"], gold["end"]
            require(type(lo) is int and type(hi) is int
                    and source["excerpt"]["start"] <= lo < hi <= source["excerpt"]["end"],
                    "Gold is outside the ingested source excerpt")
            require(source["full_file"]["text"][lo:hi] == gold["quote"]
                    and sha(gold["quote"].encode()) == gold["sha256"], "Gold is not exact source text")
        for source_id in question["expected_first_source_ids"]:
            require(source_ids[source_id]["project"] == question["project"],
                    "Expected source crosses project scope")
        if question["kind"] == "missing":
            absent = question["absent_field"]
            require(isinstance(absent, str) and absent, "Missing-field case has no field")
            require(all(absent.casefold() not in s["full_file"]["text"].casefold()
                        for s in manifest["sources"] if s["project"] == question["project"]),
                    "Missing-field label contradicts a selected original file")
    counts = {
        "projects": len({s["project"] for s in manifest["sources"]}),
        "release_commits": len(manifest["commit_metadata"]),
        "source_files": len(manifest["sources"]), "questions": len(manifest["questions"]),
        "answerable_questions": sum(q["kind"] == "answerable" for q in manifest["questions"]),
        "missing_questions": sum(q["kind"] == "missing" for q in manifest["questions"]),
        "required_spans": sum(len(q["required"]) for q in manifest["questions"]),
        "categories": dict(sorted(Counter(q["category"] for q in manifest["questions"]).items())),
    }
    require(all(manifest["integrity"][key] == value for key, value in counts.items()),
            "Manifest denominator differs")
    require(all(protocol["counts"][key] == value for key, value in counts.items()),
            "Protocol denominator differs")
    for project in {s["project"] for s in manifest["sources"]}:
        require(len({s["commit"] for s in manifest["sources"] if s["project"] == project}) == 2,
                "Each project must retain exactly two pinned release snapshots")
    return protocol, manifest


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def exact_commit(root, commit):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit or "")), "A full immutable Git SHA is required")
    require(git(root, "rev-parse", "--verify", commit + "^{commit}").decode().strip() == commit,
            "The requested commit cannot be resolved exactly")


def evaluator_identity(commit=None):
    result = {name: sha((ROOT / name).read_bytes()) for name in FROZEN_FILES}
    if commit is not None:
        exact_commit(ROOT, commit)
        for name in FROZEN_FILES:
            require(git(ROOT, "show", commit + ":" + name) == (ROOT / name).read_bytes(),
                    "Evaluator differs from frozen protocol commit: " + name)
    return {"commit": commit, "files": result, "sha256": sha(encoded(result))}


def runtime_identity(root, commit):
    exact_commit(root, commit)
    require(git(root, "rev-parse", "HEAD").decode().strip() == commit,
            "Runtime checkout HEAD differs from the requested commit")
    names = git(root, "ls-tree", "-r", "--name-only", commit, "--", "src/memory_book").decode().splitlines()
    require(bool(names), "Runtime source inventory is empty")
    hashes = {}
    for name in names:
        raw = (root / name).read_bytes()
        require(raw == git(root, "show", commit + ":" + name), "Uncommitted runtime change: " + name)
        hashes[name] = sha(raw)
    actual_py = {str(p.relative_to(root)) for p in (root / "src/memory_book").rglob("*.py")}
    require(actual_py <= set(names), "An untracked Python source could shadow the committed runtime")
    return {"commit": commit, "tree": git(root, "rev-parse", commit + "^{tree}").decode().strip(),
            "files": hashes, "sha256": sha(encoded(hashes))}


def cases(protocol, manifest):
    return {(mode, budget, question["id"]): question
            for mode in protocol["segmentation_modes"] for budget in protocol["retrieval"]["budgets_chars"]
            for question in manifest["questions"]}


def ranking_configuration(arm, ranking_scope):
    require((arm, ranking_scope) in {("baseline", "global"), ("candidate", "global"),
                                     ("candidate", "project")},
            "Only baseline_global, candidate_global and candidate_project are registered")
    return {"id": arm + "_" + ranking_scope, "arm": arm, "ranking_scope": ranking_scope,
            "constructor_options": {"ranking_scope": "project"} if ranking_scope == "project" else {},
            "constructor_semantics": "explicit_project" if ranking_scope == "project" else "omitted_default_global"}


def check_full_page(page, page_id, project, sources):
    require(page["id"] == page_id and page["offset"] == 0 and page["next_offset"] is None
            and page["total_chars"] == len(page["content"]), "Original page framing or pagination differs")
    require(page["breadcrumb"][0]["id"] == project, "Original page breadcrumb crosses project scope")
    refs = page["source_refs"]
    require(len(refs) == 1, "This one-file/one-turn fixture must have one original-page reference")
    ref = refs[0]
    source = sources.get((ref["project"], ref["session_id"]))
    require(source is not None and ref["project"] == project, "Original page references a foreign or unknown source")
    require(ref["turn_index"] == 0 and ref["message_indices"] == [0], "Original turn/message identity differs")
    lo, hi = ref["turn_start"], ref["turn_end"]
    turn = original_turn(source)
    require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(turn),
            "Invalid original-turn coordinates")
    require(ref["start"] == 0 and ref["end"] == len(page["content"])
            and turn[lo:hi] == page["content"], "Original page is not its exact source slice")
    require(date(page["created_at"]) == date(source["created_at"])
            and date(ref["created_at"]) == date(source["created_at"]), "Original source timestamp differs")
    return source, ref


def covered(intervals, lo, hi):
    position = lo
    for start, end in sorted(intervals):
        if end <= position:
            continue
        if start > position:
            return False
        position = end
        if position >= hi:
            return True
    return False


def score_valid_response(question, row, protocol, manifest):
    response, pages = row["response"], row["original_pages"]
    budget, limit = row["budget_chars"], protocol["retrieval"]["limit"]
    require(response["query"] == question["query"] and response["budget_chars"] == budget
            and response["strategy"] == "book" and response["cache_hit"] is False
            and response["temporal"]["requested"] == question["temporal"], "Returned request/cache contract differs")
    require(response["context_chars"] == len(response["context"]) <= budget
            and len(response["results"]) <= limit, "Returned context or result budget exceeded")
    scope = response.get("ranking_scope")
    if row["ranking_scope"] == "project":
        require(isinstance(scope, dict) and scope.get("requested") == "project"
                and scope.get("actual") in {"project", "global"},
                "Project ranking response does not disclose its actual route")
        actual_scope, fallback = scope["actual"], scope.get("fallback_reason")
        require(actual_scope != "global" or isinstance(fallback, str) and bool(fallback),
                "Global fallback from project ranking has no recorded reason")
    else:
        require(scope is None or isinstance(scope, dict) and scope.get("actual") == "global",
                "The default global configuration silently used another ranking scope")
        actual_scope, fallback = "global", None
    ids = [hit["id"] for hit in response["results"]]
    require(len(ids) == len(set(ids)) and set(ids) == set(pages), "Duplicate results or missing/extra page reads")
    sources = {(s["project"], s["session_id"]): s for s in manifest["sources"]}
    intervals, blocks, result_sources = defaultdict(list), [], []
    for hit in response["results"]:
        page = pages[hit["id"]]
        source, full_ref = check_full_page(page, hit["id"], question["project"], sources)
        result_sources.append(source["id"])
        require(hit["breadcrumb"][0]["id"] == question["project"]
                and hit["page_chars"] == len(page["content"])
                and date(hit["created_at"]) == date(source["created_at"]), "Hit scope, page length or timestamp differs")
        refs = hit["source_refs"]
        require(bool(refs), "An evidence hit has no source references")
        spans, cursor = [], 0
        for ref in refs:
            require((ref["project"], ref["session_id"], ref["turn_index"], ref["message_indices"])
                    == (source["project"], source["session_id"], 0, [0]), "Excerpt reference crosses original source identity")
            lo, hi = ref["start"], ref["end"]
            require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(page["content"]),
                    "Invalid page-relative excerpt coordinates")
            require(ref["turn_start"] == full_ref["turn_start"] + lo
                    and ref["turn_end"] == full_ref["turn_start"] + hi,
                    "Page and turn excerpt coordinates disagree")
            require(date(ref["created_at"]) == date(source["created_at"]), "Excerpt timestamp differs")
            fragment = page["content"][lo:hi]
            at = hit["text"].find(fragment, cursor)
            require(at >= cursor and all(c.isspace() or c == "…" for c in hit["text"][cursor:at]),
                    "Excerpt contains text not backed by the original source")
            cursor = at + len(fragment)
            spans.append([lo, hi])
            shift = source["excerpt"]["start"] - len(ROLE_PREFIX)
            intervals[source["id"]].append((ref["turn_start"] + shift, ref["turn_end"] + shift))
        require(all(c.isspace() or c == "…" for c in hit["text"][cursor:])
                and spans == hit["excerpt_spans"], "Unbacked suffix or altered excerpt spans")
        blocks.append(f'[{hit["id"]}] {source["project"]} / {source["session_id"]} | {hit["created_at"]}\n' + hit["text"])
    require("\n\n".join(blocks) == response["context"], "Context differs from exact verified citation blocks")
    assessment = response["temporal"].get("evidence_assessment", {})
    conflict_ids = {pid for group in assessment.get("conflicts", []) for pid in group["page_ids"]}
    extra_pages = row["conflict_pages"]
    require(set(extra_pages) == conflict_ids - set(pages), "Conflict-source follow-up inventory differs")
    for page_id in conflict_ids:
        check_full_page(pages.get(page_id, extra_pages.get(page_id)), page_id, question["project"], sources)
    matches = [covered(intervals[gold["source_id"]], gold["start"], gold["end"])
               for gold in question["required"]]
    expected = question["expected_first_source_ids"]
    return {"kind": question["kind"], "api_error": False, "integrity_ok": True,
            "integrity_error": None, "covered_gold": matches, "required_spans": len(matches),
            "matched_spans": sum(matches), "complete_evidence": bool(matches) and all(matches),
            "first_source_id": result_sources[0] if result_sources else None,
            "first_source_expected": (bool(result_sources) and result_sources[0] in expected) if expected else None,
            "missing_evidence_nonempty": question["kind"] == "missing" and bool(response["context"]),
            "context_chars": len(response["context"]), "assessment_status": assessment.get("status"),
            "requested_ranking_scope": row["ranking_scope"], "actual_ranking_scope": actual_scope,
            "ranking_fallback_reason": fallback}


def score_row(question, row, protocol, manifest):
    error = row.get("error")
    if not error:
        try:
            return score_valid_response(question, row, protocol, manifest)
        except (ValueError, KeyError, TypeError, IndexError) as problem:
            error = {"type": type(problem).__name__, "message": str(problem)}
    return {"kind": question["kind"], "api_error": row.get("error") is not None,
            "integrity_ok": False, "integrity_error": error,
            "covered_gold": [False] * len(question["required"]), "required_spans": len(question["required"]),
            "matched_spans": 0, "complete_evidence": False, "first_source_id": None,
            "first_source_expected": False if question["expected_first_source_ids"] else None,
            "missing_evidence_nonempty": None, "context_chars": None, "assessment_status": None,
            "requested_ranking_scope": row["ranking_scope"], "actual_ranking_scope": None,
            "ranking_fallback_reason": None}


def summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["segmentation"], row["budget_chars"], row["category"]].append(row["score"])
    groups = []
    for (mode, budget, category), scores in sorted(grouped.items()):
        groups.append({"segmentation": mode, "budget_chars": budget, "category": category,
                       "questions": len(scores), "answerable": sum(s["kind"] == "answerable" for s in scores),
                       "complete_evidence": sum(s["complete_evidence"] for s in scores),
                       "required_spans": sum(s["required_spans"] for s in scores),
                       "matched_spans": sum(s["matched_spans"] for s in scores),
                       "first_source_eligible": sum(s["first_source_expected"] is not None for s in scores),
                       "first_source_expected": sum(s["first_source_expected"] is True for s in scores),
                       "missing_evidence_nonempty": sum(s["missing_evidence_nonempty"] is True for s in scores),
                       "api_errors": sum(s["api_error"] for s in scores),
                       "integrity_errors": sum(not s["integrity_ok"] for s in scores)})
    return {"response_configurations": len(rows),
            "requested_ranking_scope_counts": dict(sorted(Counter(r["ranking_scope"] for r in rows).items())),
            "actual_ranking_scope_counts": dict(sorted(Counter(r["score"]["actual_ranking_scope"] or "error"
                                                              for r in rows).items())),
            "project_fallback_reasons": dict(sorted(Counter(r["score"]["ranking_fallback_reason"]
                    for r in rows if r["score"]["ranking_fallback_reason"]).items())),
            "all_requested_project_calls_used_project": (all(r["score"]["actual_ranking_scope"] == "project"
                    for r in rows if r["ranking_scope"] == "project")
                    if any(r["ranking_scope"] == "project" for r in rows) else None),
            "all_source_integrity_checks_pass": all(r["score"]["integrity_ok"] for r in rows),
            "all_answerable_configurations_complete": all(r["score"]["complete_evidence"]
                  for r in rows if r["score"]["kind"] == "answerable"),
            "groups": groups,
            "denominator_warning": "36 authored questions and 48 source spans repeat across modes/budgets; configurations are not independent questions. Turn/session modes both preserve the same single-turn input files.",
            "scope": "Retrieval of exact public code evidence only; no coding model, production conversation, calibrated abstention or timing claim."}


def payload(source):
    return {"project": source["project"], "project_name": source["repository"],
            "session_id": source["session_id"], "title": source["session_title"],
            "task_id": source["task_id"], "task_title": source["task_title"],
            "created_at": source["created_at"],
            "messages": [{"role": "assistant", "content": source_text(source)}]}


def worker(args):
    protocol, manifest = load_inputs()
    source, output = args.source.resolve(), args.output.resolve()
    configuration = ranking_configuration(args.arm, args.ranking_scope)
    evaluator = evaluator_identity(args.protocol_commit)
    before = runtime_identity(source, args.commit)
    if args.arm == "baseline":
        require(args.commit == protocol["baseline_commit"], "Baseline is not the registered v0.13 main source")
    import memory_book
    from memory_book._text_backend import BACKEND_NAME
    import memory_book.store as store
    require(Path(memory_book.__file__).resolve() == source / "src/memory_book/__init__.py"
            and Path(store.__file__).resolve() == source / "src/memory_book/store.py"
            and BACKEND_NAME == args.backend, "Loaded runtime/backend is not the selected frozen checkout")
    native = sys.modules.get("memory_book._native")
    binary = Path(native.__file__).resolve() if native is not None else None
    require(args.backend != "native" or (binary is not None and binary.parent == source / "src/memory_book"),
            "Forced-native run did not load the selected checkout's extension")
    output.mkdir(parents=True, exist_ok=False)
    proof = {"protocol": PROTOCOL_ID, "status": "started", "arm": args.arm,
             "ranking_scope": args.ranking_scope, "configuration": configuration,
             "started_at_utc": datetime.now(timezone.utc).isoformat(),
             "backend": BACKEND_NAME, "version": memory_book.__version__,
             "recall_version": store.RECALL_VERSION, "python": sys.version,
             "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
             "evaluator": evaluator, "source_before": before,
             "native_binary": {"path": str(binary), "sha256": sha(binary.read_bytes())} if binary else None,
             "recall_calls": 0, "source_followup_reads": 0, "database_inventory": []}
    write(output / "report.json", proof)
    (output / "frozen-protocol.json").write_bytes((ROOT / PROTOCOL_PATH).read_bytes())
    (output / "frozen-provenance.json").write_bytes((ROOT / MANIFEST_PATH).read_bytes())
    rows = []
    try:
        with (output / "raw.jsonl").open("x", encoding="utf-8") as raw, (output / "journal.jsonl").open("x", encoding="utf-8") as journal:
            for mode in protocol["segmentation_modes"]:
                db_path = output / (mode + ".sqlite")
                with memory_book.MemoryBook(db_path, segmentation=mode,
                        **protocol["ingestion_settings"], **configuration["constructor_options"]) as book:
                    observed_scope = getattr(book, "ranking_scope", None)
                    require(observed_scope == args.ranking_scope or
                            (args.arm == "baseline" and args.ranking_scope == "global" and observed_scope is None),
                            "Loaded book constructor does not match the registered ranking configuration")
                    receipts = [book.ingest(payload(s)) for s in sorted(manifest["sources"],
                                key=lambda item: (date(item["created_at"]), item["repository"], item["path"]))]
                    write(output / (mode + "-ingest.json"), receipts)
                    for budget in protocol["retrieval"]["budgets_chars"]:
                        for question in manifest["questions"]:
                            row = {"segmentation": mode, "budget_chars": budget, "case_id": question["id"],
                                   "ranking_scope": args.ranking_scope, "configuration_id": configuration["id"],
                                   "project": question["project"], "query": question["query"],
                                   "temporal": question["temporal"], "category": question["category"],
                                   "response": None, "original_pages": {}, "conflict_pages": {}, "error": None}
                            journal.write(json.dumps({"state": "started", "segmentation": mode,
                                           "budget_chars": budget, "case_id": question["id"],
                                           "configuration_id": configuration["id"]}) + "\n")
                            journal.flush()
                            try:
                                proof["recall_calls"] += 1
                                response = book.recall(question["query"], project=question["project"],
                                    temporal=question["temporal"], budget_chars=budget,
                                    limit=protocol["retrieval"]["limit"], use_cache=False,
                                    strategy="book", semantic=False, coverage=False)
                                row["response"] = response
                                for hit in response["results"]:
                                    proof["source_followup_reads"] += 1
                                    row["original_pages"][hit["id"]] = book.read(hit["id"], project=question["project"], limit=100000)
                                assessment = response["temporal"].get("evidence_assessment", {})
                                conflict_ids = {p for c in assessment.get("conflicts", []) for p in c["page_ids"]}
                                for pid in sorted(conflict_ids - row["original_pages"].keys()):
                                    proof["source_followup_reads"] += 1
                                    row["conflict_pages"][pid] = book.read(pid, project=question["project"], limit=100000)
                            except Exception as problem:
                                row["error"] = {"type": type(problem).__name__, "message": str(problem)}
                            row["score"] = score_row(question, row, protocol, manifest)
                            raw.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                            raw.flush()
                            os.fsync(raw.fileno())
                            rows.append(row)
                            journal.write(json.dumps({"state": "completed", "segmentation": mode,
                                           "budget_chars": budget, "case_id": question["id"],
                                           "configuration_id": configuration["id"]}) + "\n")
                            journal.flush()
                proof["database_inventory"].append({"segmentation": mode,
                    "observed_constructor_ranking_scope": observed_scope,
                    "ingest_calls": len(receipts), "pages": sum(r["pages"] for r in receipts),
                    "bytes": db_path.stat().st_size, "sha256": sha(db_path.read_bytes())})
        require(len(rows) == len(cases(protocol, manifest)), "The closed query matrix is incomplete")
        after = runtime_identity(source, args.commit)
        require(before == after and evaluator == evaluator_identity(args.protocol_commit),
                "Runtime or evaluator changed during the holdout")
        require(not binary or sha(binary.read_bytes()) == proof["native_binary"]["sha256"],
                "Loaded native binary changed during the holdout")
        proof.update(status="completed", source_after=after, summary=summary(rows))
    except BaseException as problem:
        proof.update(status="failed", error={"type": type(problem).__name__, "message": str(problem)},
                     partial_response_configurations=len(rows))
        (output / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        path = output / "raw.jsonl"
        if path.exists():
            data = path.read_bytes()
            compressed = gzip.compress(data, mtime=0)
            compressed_path = output / "raw.jsonl.gz"
            compressed_path.write_bytes(compressed)
            proof["raw"] = {"file": compressed_path.name, "sha256": sha(data), "bytes": len(data),
                            "compressed_sha256": sha(compressed), "compressed_bytes": len(compressed)}
            path.unlink()
        proof["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write(output / "report.json", proof)


def audit(output):
    protocol, manifest = load_inputs()
    report = json.loads((output / "report.json").read_text())
    require(report["protocol"] == PROTOCOL_ID and report["status"] == "completed", "Attempt did not complete")
    configuration = ranking_configuration(report["arm"], report["ranking_scope"])
    require(report["configuration"] == configuration, "Saved constructor/ranking configuration differs")
    if report["arm"] == "baseline":
        require(report["source_before"]["commit"] == protocol["baseline_commit"], "Saved baseline identity differs")
    require({d["segmentation"] for d in report["database_inventory"]} == set(protocol["segmentation_modes"])
            and len(report["database_inventory"]) == len(protocol["segmentation_modes"]),
            "Saved constructor-mode inventory differs")
    for inventory in report["database_inventory"]:
        observed = inventory["observed_constructor_ranking_scope"]
        require(observed == report["ranking_scope"] or
                (report["arm"] == "baseline" and report["ranking_scope"] == "global" and observed is None),
                "Saved actual book ranking scope differs")
    require(report["evaluator"] == evaluator_identity(report["evaluator"]["commit"]), "Frozen evaluator identity differs")
    require(report["source_before"] == report["source_after"], "Runtime identity changed")
    require((output / "frozen-protocol.json").read_bytes() == (ROOT / PROTOCOL_PATH).read_bytes()
            and (output / "frozen-provenance.json").read_bytes() == (ROOT / MANIFEST_PATH).read_bytes(),
            "Saved protocol or original sources differ")
    compressed = (output / report["raw"]["file"]).read_bytes()
    data = gzip.decompress(compressed)
    require(len(compressed) == report["raw"]["compressed_bytes"]
            and sha(compressed) == report["raw"]["compressed_sha256"]
            and len(data) == report["raw"]["bytes"] and sha(data) == report["raw"]["sha256"],
            "Original saved response bytes differ")
    rows = [json.loads(line) for line in data.splitlines()]
    expected, seen = cases(protocol, manifest), {}
    for row in rows:
        key = row["segmentation"], row["budget_chars"], row["case_id"]
        require(key in expected and key not in seen, "Duplicate or unregistered response configuration")
        question = expected[key]
        require(row["ranking_scope"] == report["ranking_scope"]
                and row["configuration_id"] == configuration["id"], "Mixed ranking configurations in one attempt")
        require(all(row[field] == question[field] for field in ("project", "query", "temporal", "category")),
                "Saved request does not match the frozen question")
        require(score_row(question, row, protocol, manifest) == row["score"],
                "Saved score differs from independently recomputed source coverage")
        seen[key] = row
    require(seen.keys() == expected.keys() and report["recall_calls"] == len(expected),
            "Saved closed-matrix inventory is incomplete")
    result = summary(rows)
    require(result == report["summary"], "Saved summary differs from raw-source recomputation")
    return {"status": "verified_saved_records", "new_recall_calls": 0,
            "source_commit": report["source_before"]["commit"], "backend": report["backend"],
            "configuration": configuration, "summary": result}, seen


def compare(baseline, candidate):
    first, old = audit(baseline)
    second, new = audit(candidate)
    require(first["backend"] == second["backend"], "Comparison backends differ")
    old_report = json.loads((baseline / "report.json").read_text())
    new_report = json.loads((candidate / "report.json").read_text())
    pair = old_report["configuration"]["id"], new_report["configuration"]["id"]
    require(pair in {("baseline_global", "candidate_global"), ("baseline_global", "candidate_project"),
                     ("candidate_global", "candidate_project")}, "Unregistered ranking-scope comparison")
    if pair[0] == "candidate_global":
        require(first["source_commit"] == second["source_commit"],
                "Within-candidate scope comparison must use one identical runtime commit")
    require(old_report["evaluator"] == new_report["evaluator"], "Comparison protocols differ")
    changes, regressions = [], []
    for key in old:
        a, b = old[key]["score"], new[key]["score"]
        quality_keys = set(a) - {"requested_ranking_scope", "actual_ranking_scope", "ranking_fallback_reason"}
        if any(a[key] != b[key] for key in quality_keys):
            changes.append({"cell": key, "baseline": a, "candidate": b})
        lost = [i for i, (x, y) in enumerate(zip(a["covered_gold"], b["covered_gold"])) if x and not y]
        if (lost or (a["first_source_expected"] is True and b["first_source_expected"] is not True)
                or (a["integrity_ok"] and not b["integrity_ok"])):
            regressions.append({"cell": key, "lost_required_span_indices": lost, "baseline": a, "candidate": b})
    return {"protocol": PROTOCOL_ID, "baseline_commit": first["source_commit"],
            "candidate_commit": second["source_commit"], "backend": first["backend"],
            "reference_configuration": old_report["configuration"],
            "candidate_configuration": new_report["configuration"],
            "responses_per_arm": len(old), "score_changes": changes, "regressions": regressions,
            "candidate_source_integrity_ok": second["summary"]["all_source_integrity_checks_pass"],
            "candidate_all_requested_project_calls_used_project": second["summary"]["all_requested_project_calls_used_project"],
            "candidate_all_answerable_complete": second["summary"]["all_answerable_configurations_complete"],
            "baseline_summary": first["summary"], "candidate_summary": second["summary"],
            "scope": "An independent public-code extraction holdout if not used for tuning; no production-task or calibrated-abstention claim."}


def self_test():
    # Synthetic scorer-only controls. They never import or call the retriever.
    source = {"id": "fixture", "project": "public:fixture/project", "session_id": "v1:config.txt",
              "created_at": "2023-01-01T00:00:00Z", "excerpt": {"start": 0, "end": 9},
              "full_file": {"text": "value=17."}}
    text = original_turn(source)
    ref = {"project": source["project"], "session_id": source["session_id"], "created_at": source["created_at"],
           "turn_index": 0, "message_indices": [0], "start": 0, "end": len(text),
           "turn_start": 0, "turn_end": len(text)}
    page = {"id": "p", "offset": 0, "next_offset": None, "content": text, "total_chars": len(text),
            "source_refs": [ref], "created_at": source["created_at"], "breadcrumb": [{"id": source["project"]}]}
    check_full_page(page, "p", source["project"], {(source["project"], source["session_id"]): source})
    rejected = 0
    for mutation in ("foreign", "coordinates", "fabrication", "timestamp"):
        bad = json.loads(json.dumps(page))
        if mutation == "foreign":
            bad["source_refs"][0]["project"] = "public:other/project"
        elif mutation == "coordinates":
            bad["source_refs"][0]["turn_start"] = 1
        elif mutation == "fabrication":
            bad["content"] = bad["content"].replace("17", "99")
        else:
            bad["created_at"] = "2024-01-01T00:00:00Z"
        try:
            check_full_page(bad, "p", source["project"], {(source["project"], source["session_id"]): source})
        except ValueError:
            rejected += 1
    require(rejected == 4, "A forged original-source control was accepted")
    require(covered([(0, 4), (4, 9)], 2, 8) and not covered([(0, 4), (5, 9)], 2, 8),
            "Contiguous source coverage does not distinguish an evidence gap")
    require(ranking_configuration("baseline", "global")["constructor_options"] == {}
            and ranking_configuration("candidate", "global")["constructor_options"] == {}
            and ranking_configuration("candidate", "project")["constructor_options"] == {"ranking_scope": "project"},
            "Constructor configuration changes the baseline or default path")
    try:
        ranking_configuration("baseline", "project")
    except ValueError:
        pass
    else:
        raise ValueError("An unregistered baseline ranking mode was accepted")
    protocol, manifest = load_inputs()
    return {"status": "passed", "synthetic_forgery_controls_rejected": rejected,
            "adjacent_interval_and_gap_controls": 2, "frozen_questions": len(manifest["questions"]),
            "ranking_configuration_controls": 4,
            "planned_configurations_per_arm_backend": len(cases(protocol, manifest)), "recall_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Verify frozen inputs without importing MemoryBook")
    sub.add_parser("self-test", help="Run source/scorer integrity controls with zero retrieval calls")
    for command in ("run", "worker"):
        p = sub.add_parser(command)
        p.add_argument("--source", type=Path, required=True)
        p.add_argument("--commit", required=True)
        p.add_argument("--protocol-commit", required=True)
        p.add_argument("--backend", choices=("python", "native"), required=True)
        p.add_argument("--arm", choices=("baseline", "candidate"), required=True)
        p.add_argument("--ranking-scope", choices=("global", "project"), default="global",
                       help="Global omits the new constructor argument; project explicitly selects it")
        p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("audit")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("compare")
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check":
        protocol, manifest = load_inputs()
        result = {"status": "verified_frozen_inputs", "counts": protocol["counts"],
                  "evaluator": evaluator_identity(), "recall_calls": 0,
                  "planned_configurations_per_arm_backend": len(cases(protocol, manifest))}
    elif args.command == "self-test":
        result = self_test()
    elif args.command == "audit":
        result, _ = audit(args.output.resolve())
    elif args.command == "compare":
        result = compare(args.baseline.resolve(), args.candidate.resolve())
    elif args.command == "worker":
        worker(args)
        result, _ = audit(args.output.resolve())
    else:
        load_inputs()
        ranking_configuration(args.arm, args.ranking_scope)
        evaluator_identity(args.protocol_commit)
        runtime_identity(args.source.resolve(), args.commit)
        require(not args.output.exists(), "Use a new immutable attempt directory")
        env = {**os.environ, "PYTHONPATH": str(args.source.resolve() / "src"),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
               "MEMORY_BOOK_TEXT_BACKEND": args.backend}
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker",
                        "--source", str(args.source.resolve()), "--commit", args.commit,
                        "--protocol-commit", args.protocol_commit, "--backend", args.backend,
                        "--arm", args.arm, "--ranking-scope", args.ranking_scope,
                        "--output", str(args.output.resolve())],
                       env=env, cwd=args.source.resolve(), check=True)
        result, _ = audit(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
