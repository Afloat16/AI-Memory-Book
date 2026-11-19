"""Post-protocol AST scope audit of saved v0.14 public-source responses.

The allowed coordinates are frozen using source and question semantics before
opening response artifacts. This script performs no MemoryBook query. Keep the
original v2 file-level quote scores alongside these stricter scope scores.
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "v014-public-source-scope-audit-v1"
HOLDOUT_COMMIT = "2a73098f492652da5bd3c072e2ca5590acfc61cb"
PLAN = "benchmarks/experiments/v014-public-scope-audit.json"
FROZEN_FILES = ("benchmarks/v014_public_scope_audit.py", PLAN,
                "tests/test_v014_public_scope_audit.py")

# These bindings come from the named classes/fields in the questions, not from
# any retrieved result. A module, class attribute, constructor parameter, and
# initializer assignment are distinct evidence scopes.
BINDINGS = {
    "httpx": {
        "timeout": [("module", "", "DEFAULT_TIMEOUT_CONFIG")],
        "connections": [("module", "", "DEFAULT_LIMITS")],
        "keepalive": [("module", "", "DEFAULT_LIMITS")],
        "redirects": [("module", "", "DEFAULT_MAX_REDIRECTS")],
        "expiry": [("parameter", "Limits.__init__", "keepalive_expiry")],
        "http1": [("parameter", "Client.__init__", "http1")],
        "http2": [("parameter", "Client.__init__", "http2")],
        "environment": [("parameter", "Client.__init__", "trust_env")],
        "multi": [("module", "", "DEFAULT_TIMEOUT_CONFIG"),
                  ("parameter", "Client.__init__", "http2")],
        "history": [("module", "", "DEFAULT_POOL_LIMITS")],
    },
    "httpcore": {
        "connections": [("parameter", "ConnectionPool.__init__", "max_connections")],
        "keepalive": [("parameter", "ConnectionPool.__init__", "max_keepalive_connections")],
        "expiry": [("parameter", "ConnectionPool.__init__", "keepalive_expiry")],
        "http1": [("parameter", "ConnectionPool.__init__", "http1")],
        "http2": [("parameter", "ConnectionPool.__init__", "http2")],
        "retries": [("parameter", "ConnectionPool.__init__", "retries")],
        "read": [("class", "HTTP11Connection", "READ_NUM_BYTES")],
        "event": [("class", "HTTP11Connection", "MAX_INCOMPLETE_EVENT_SIZE")],
        "multi": [("parameter", "ConnectionPool.__init__", "max_connections"),
                  ("class", "HTTP11Connection", "READ_NUM_BYTES")],
        "history": [("class", "SyncHTTP11Connection", "READ_NUM_BYTES")],
    },
    "requests": {
        "blocking": [("module", "", "DEFAULT_POOLBLOCK")],
        "pool": [("module", "", "DEFAULT_POOLSIZE")],
        "retries": [("module", "", "DEFAULT_RETRIES")],
        "timeout": [("module", "", "DEFAULT_POOL_TIMEOUT")],
        "environment": [("assignment", "Session.__init__", "self.trust_env")],
        "verify": [("assignment", "Session.__init__", "self.verify")],
        "stream": [("assignment", "Session.__init__", "self.stream")],
        "cert": [("assignment", "Session.__init__", "self.cert")],
        "multi": [("module", "", "DEFAULT_POOLSIZE"),
                  ("assignment", "Session.__init__", "self.trust_env")],
        "history": [("module", "", "DEFAULT_POOLSIZE")],
    },
    "urllib3": {
        "methods": [("class", "Retry", "DEFAULT_ALLOWED_METHODS")],
        "status": [("class", "Retry", "RETRY_AFTER_STATUS_CODES")],
        "headers": [("class", "Retry", "DEFAULT_REMOVE_HEADERS_ON_REDIRECT")],
        "backoff": [("class", "Retry", "DEFAULT_BACKOFF_MAX")],
        "total": [("parameter", "Retry.__init__", "total")],
        "factor": [("parameter", "Retry.__init__", "backoff_factor")],
        "pool": [("parameter", "HTTPConnectionPool.__init__", "maxsize")],
        "blocking": [("parameter", "HTTPConnectionPool.__init__", "block")],
        "multi": [("class", "Retry", "DEFAULT_BACKOFF_MAX"),
                  ("parameter", "HTTPConnectionPool.__init__", "maxsize")],
        "history": [("class", "Retry", "DEFAULT_REDIRECT_HEADERS_BLACKLIST")],
    },
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_holdout(root):
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("_v014_frozen_public_holdout", root / "benchmarks/v014_public_holdout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.frozen_identity(HOLDOUT_COMMIT)
    return module


def char_offset(lines, lineno, utf8_column):
    """AST columns are UTF-8 bytes; MemoryBook coordinates are code points."""
    return sum(map(len, lines[:lineno - 1])) + len(lines[lineno - 1].encode()[:utf8_column].decode())


def bounds(lines, node):
    return (char_offset(lines, node.lineno, node.col_offset),
            char_offset(lines, node.end_lineno, node.end_col_offset))


def scope_node(tree, owner):
    node = tree
    for name in owner.split(".") if owner else []:
        matches = [child for child in node.body if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                   and child.name == name]
        if len(matches) != 1:
            raise ValueError("Ambiguous or absent declared scope: " + owner)
        node = matches[0]
    return node


def target_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = target_name(node.value)
        return parent + "." + node.attr if parent else None
    return None


def assignments_in(node, nested=False):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            yield child
        if nested:
            yield from assignments_in(child, nested=True)


def declaration_locations(text, binding, quote):
    """Bind a quote to the intended declaration, not merely an equal literal."""
    tree, lines = ast.parse(text), text.splitlines(keepends=True)
    kind, owner, field = binding
    node = scope_node(tree, owner)
    candidates = []
    if kind == "parameter":
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise ValueError("Parameter owner is not a function")
        arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        args = [arg for arg in arguments if arg.arg == field]
        if len(args) != 1:
            raise ValueError("Named constructor parameter missing or ambiguous")
        arg = args[0]
        start = char_offset(lines, arg.lineno, arg.col_offset)
        header_end = char_offset(lines, node.body[0].lineno, node.body[0].col_offset)
        if not text.startswith(quote, start) or start + len(quote) > header_end:
            raise ValueError("Gold is not the exact named parameter declaration")
        candidates = [(start, start + len(quote), arg.lineno)]
    else:
        if kind == "module" and not isinstance(node, ast.Module):
            raise ValueError("Module binding selected a nested scope")
        if kind == "class" and not isinstance(node, ast.ClassDef):
            raise ValueError("Class binding selected a different scope")
        if kind == "assignment" and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise ValueError("Initializer binding selected a different scope")
        if kind not in {"module", "class", "assignment"}:
            raise ValueError("Unknown binding kind")
        for assignment in assignments_in(node, nested=kind == "assignment"):
            targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
            if not any(target_name(target) == field for target in targets):
                continue
            lo, hi = bounds(lines, assignment)
            at = text.find(quote, lo, hi)
            while at >= 0:
                candidates.append((at, at + len(quote), text.count("\n", 0, at) + 1))
                at = text.find(quote, at + 1, hi)
    if len(candidates) != 1:
        raise ValueError(f"Expected one exact source declaration for {binding}, got {len(candidates)}")
    return candidates


def anchors_for(text, chunks, binding, quote):
    anchors = []
    for start, end, line in declaration_locations(text, binding, quote):
        offset = 0
        for turn, chunk in enumerate(chunks):
            if offset <= start and end <= offset + len(chunk):
                anchors.append({"turn_index": turn, "turn_start": 6 + start - offset,
                                "turn_end": 6 + end - offset, "source_start": start,
                                "source_end": end, "source_line": line,
                                "binding": {"kind": binding[0], "owner": binding[1], "field": binding[2]}})
                break
            offset += len(chunk)
        else:
            raise ValueError("Scoped quote crosses the unchanged holdout chunk boundary")
    return anchors


def build_plan(holdout):
    sessions, cases = holdout.dataset()
    by_id = {row["session_id"]: row for row in sessions}
    entries = []
    for case in cases:
        project, suffix = case["id"].split(":", 1)
        bindings = [] if case["category"] == "missing" else BINDINGS[project][suffix]
        if len(bindings) != len(case["required"]):
            raise ValueError("Scope bindings do not cover the frozen gold")
        required = []
        for gold, binding in zip(case["required"], bindings):
            source = by_id[gold["session_id"]]
            chunks = [message["content"] for message in source["messages"]]
            text = "".join(chunks)
            required.append({"session_id": gold["session_id"], "quote": gold["quote"],
                             "source_sha256": sha(text.encode()),
                             "allowed_anchors": anchors_for(text, chunks, binding, gold["quote"])})
        entries.append({"id": case["id"], "project": case["project"], "category": case["category"],
                        "query": case["query"], "required": required})
    return {"protocol": PROTOCOL, "parent_holdout_commit": HOLDOUT_COMMIT,
            "parent_holdout_identity": holdout.frozen_identity(HOLDOUT_COMMIT),
            "scope": "Post-protocol stricter class/function/declaration-coordinate audit; preserve original v2 file-level quote results.",
            "freeze_boundary": "Allowed coordinates derived exclusively from pinned source AST and question semantics before this auditor read any holdout response. No retrieval is executed or repeated.",
            "coordinate_basis": "Original whole-line chunking is unchanged; one USER prefix adds six Unicode code points to source-turn offsets. AST byte columns are explicitly converted to Unicode code-point offsets.",
            "cases": entries}


def strict_score(case, response):
    """Call only after the frozen parent verifier authenticated all excerpts."""
    matches = []
    for gold in case["required"]:
        matched = False
        for hit in response["results"]:
            for ref in hit["source_refs"]:
                if ref["project"] != case["project"] or ref["session_id"] != gold["session_id"]:
                    continue
                for anchor in gold["allowed_anchors"]:
                    if (ref["turn_index"] == anchor["turn_index"]
                            and ref["turn_start"] <= anchor["turn_start"]
                            and ref["turn_end"] >= anchor["turn_end"]
                            and gold["quote"] in hit["text"]):
                        matched = True
        matches.append(matched)
    return {"required_spans": len(matches), "matched_spans": sum(matches),
            "complete": bool(matches) and all(matches), "required_matches": matches,
            "missing": case["category"] == "missing"}


def frozen_identity(commit):
    hashes = {}
    for name in FROZEN_FILES:
        raw = (ROOT / name).read_bytes()
        frozen = subprocess.check_output(["git", "-C", str(ROOT), "show", commit + ":" + name])
        if raw != frozen:
            raise ValueError("Scope-audit file differs from its frozen commit: " + name)
        hashes[name] = sha(raw)
    return {"commit": commit, "files": hashes}


def audit(args, holdout):
    identity = frozen_identity(args.audit_commit)
    plan = json.loads((ROOT / PLAN).read_text())
    if plan != build_plan(holdout):
        raise ValueError("Frozen AST scope plan differs from pinned source/question derivation")
    cases = {case["id"]: case for case in plan["cases"]}
    sessions, parent_cases = holdout.dataset()
    parent_cases = {case["id"]: case for case in parent_cases}
    originals = {(s["project"], s["session_id"], i): {"text": "USER: " + m["content"], "created_at": s["created_at"]}
                 for s in sessions for i, m in enumerate(s["messages"])}
    # Response artifacts are first opened only here, after both freezes pass.
    report_raw = (args.responses / "report.json").read_bytes()
    report = json.loads(report_raw)
    if report.get("protocol_identity") != plan["parent_holdout_identity"]:
        raise ValueError("Response parent protocol identity differs")
    raw_bytes = (args.responses / "responses.jsonl.gz").read_bytes()
    if report.get("raw_sha256") is not None and sha(raw_bytes) != report["raw_sha256"]:
        raise ValueError("Original response archive hash differs")
    rows, seen = [], set()
    for line in gzip.decompress(raw_bytes).splitlines():
        row = json.loads(line)
        key = row["case_id"], row["budget_chars"]
        if key in seen or key[0] not in cases or key[1] not in {1200, 2400}:
            raise ValueError("Duplicate or unknown original response row")
        seen.add(key)
        if row.get("verification_error") or row.get("error"):
            rows.append({"case_id": key[0], "budget_chars": key[1],
                         "original_error": row.get("verification_error", row.get("error")),
                         "file_level_score": row.get("score"), "scope_score": None})
            continue
        original_score = holdout.verify_response(parent_cases[key[0]], row["response"], row["original_pages"], originals, key[1])
        if original_score != row["score"]:
            raise ValueError("Saved parent score differs from the frozen verifier")
        strict = strict_score(cases[key[0]], row["response"])
        if strict["matched_spans"] > original_score["matched_spans"]:
            raise ValueError("Stricter scope unexpectedly increased file-level coverage")
        rows.append({"case_id": key[0], "budget_chars": key[1], "file_level_score": original_score,
                     "scope_score": strict})
    expected = {(case, budget) for case in cases for budget in (1200, 2400)}
    result = {"protocol": PROTOCOL, "audit_identity": identity,
              "parent_report_sha256": sha(report_raw), "parent_response_archive_sha256": sha(raw_bytes),
              "parent_source": report.get("source"), "parent_status": report.get("status"),
              "complete_matrix": seen == expected, "unobserved_cells": sorted(expected - seen),
              "scope_boundary": plan["scope"], "new_retrieval_calls": 0, "rows": rows, "summary": []}
    for budget in (1200, 2400):
        selected = [row for row in rows if row["budget_chars"] == budget]
        valid = [row for row in selected if row.get("scope_score") is not None]
        result["summary"].append({"budget_chars": budget, "observed_rows": len(selected),
            "validated_rows": len(valid), "original_verification_errors": len(selected) - len(valid),
            "original_file_complete": sum(row["file_level_score"]["complete"] for row in valid),
            "strict_scope_complete": sum(row["scope_score"]["complete"] for row in valid),
            "strict_scope_matched_spans": sum(row["scope_score"]["matched_spans"] for row in valid),
            "strict_scope_required_spans": sum(row["scope_score"]["required_spans"] for row in valid)})
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("protocol", "complete_matrix", "new_retrieval_calls", "summary")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "audit"))
    parser.add_argument("--holdout-root", type=Path, default=ROOT)
    parser.add_argument("--audit-commit")
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    holdout = load_holdout(args.holdout_root)
    if args.command == "freeze":
        plan = build_plan(holdout)
        with (ROOT / PLAN).open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"protocol": PROTOCOL, "cases": len(plan["cases"]),
                          "required_scoped_spans": sum(len(case["required"]) for case in plan["cases"]),
                          "response_artifacts_read": 0}, indent=2))
    else:
        if not args.audit_commit or not args.responses or not args.output:
            parser.error("audit requires audit-commit, responses, and output")
        audit(args, holdout)


if __name__ == "__main__":
    main()
