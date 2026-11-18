"""Source-bound v0.12 development diagnosis with independent saved-row checks.

This is not a holdout, a speed benchmark, or an external-product ranking.
Run only after committing the protocol, evaluator and selected runtime sources.
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
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from benchmarks.v012_revision_cases import original_sources, workload
from scripts.validate_v011_revision_recovery import source_identity

BASELINE = "78cc906d81818a16884de7de2e613e5a56346f93"
PROTOCOL = "v012-declaration-scope-development-v1"
BUDGETS = (1200, 2400)
LIMITS = (1, 5)
MODES = ("auto", "relevance")
EVALUATOR_FILES = (
    "benchmarks/v012_revision_cases.py", "benchmarks/v012_revision_eval.py",
    "benchmarks/experiments/v012-revision-evaluation-protocol.json",
    "scripts/validate_v011_revision_recovery.py",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def evaluator_identity():
    files = {name: sha((ROOT / name).read_bytes()) for name in EVALUATOR_FILES}
    return {"files": files, "sha256": sha(encoded(files)), "dataset_sha256": sha(encoded(workload()))}


def matrix():
    return {(case["id"], mode, budget, limit): (scenario, case)
            for scenario in workload() for case in scenario["cases"]
            for mode in MODES for budget in BUDGETS for limit in LIMITS}


def verify_and_score(case, scenario, response, pages, *, mode, budget, limit):
    """Validate full native framing and every original-source slice independently."""
    if (response["query"] != case["query"] or response["budget_chars"] != budget
            or response["cache_hit"] is not False or response["strategy"] != "book"
            or response["temporal"]["requested"] != mode
            or response["context_chars"] != len(response["context"])
            or len(response["context"]) > budget or len(response["results"]) > limit):
        raise ValueError("Request, temporal mode, cache, budget or result-count contract differs")
    originals = original_sources(scenario)
    sources = {(s["project"], s["session_id"], 0): s for s in scenario["sessions"]}
    ids = [hit["id"] for hit in response["results"]]
    if len(ids) != len(set(ids)) or set(ids) != set(pages):
        raise ValueError("Duplicate hits or missing/extra original-page follow-ups")
    blocks, sessions = [], []
    for hit in response["results"]:
        page = pages[hit["id"]]
        refs = hit["source_refs"]
        if not refs or len(page["source_refs"]) != 1:
            raise ValueError("Missing source or unexpected one-turn fixture mapping")
        full_ref = page["source_refs"][0]
        identity = (full_ref["project"], full_ref["session_id"], full_ref["turn_index"])
        original = originals.get(identity)
        if (identity[0] != case["project"] or original is None or page["id"] != hit["id"]
                or page["content"] != original or page["offset"] != 0
                or page["next_offset"] is not None or page["total_chars"] != len(original)
                or [full_ref[k] for k in ("start", "end", "turn_start", "turn_end")]
                   != [0, len(original), 0, len(original)]
                or full_ref["message_indices"] != [0]
                or hit["breadcrumb"][0]["id"] != case["project"]
                or page["breadcrumb"][0]["id"] != case["project"]
                or hit["page_chars"] != len(original)
                or hit["created_at"] != page["created_at"]):
            raise ValueError("Full page, original source, scope, coordinates or timestamp differs")
        recorded_date = datetime.fromisoformat(sources[identity]["created_at"].replace("Z", "+00:00"))
        if datetime.fromisoformat(hit["created_at"].replace("Z", "+00:00")) != recorded_date:
            raise ValueError("Returned timestamp differs from the original session")
        covered = [False] * len(hit["text"])
        spans = []
        for ref in refs:
            if ((ref["project"], ref["session_id"], ref["turn_index"]) != identity
                    or ref["message_indices"] != [0]):
                raise ValueError("Snippet reference crosses the original project/session/turn")
            lo, hi = ref["turn_start"], ref["turn_end"]
            if (type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(original)
                    or ref["start"] != lo or ref["end"] != hi):
                raise ValueError("Snippet source coordinates differ")
            fragment = original[lo:hi]
            start = hit["text"].find(fragment)
            if start < 0:
                raise ValueError("Snippet does not contain its exact original source slice")
            for offset in range(start, start + len(fragment)):
                covered[offset] = True
            spans.append([lo, hi])
        if (spans != hit["excerpt_spans"]
                or any(not seen and not char.isspace() and char != "…"
                       for seen, char in zip(covered, hit["text"]))):
            raise ValueError("Unsupported snippet text or altered excerpt coordinates")
        blocks.append(f'[{hit["id"]}] {identity[0]} / {identity[1]} | {hit["created_at"]}\n' + hit["text"])
        sessions.append(identity[1])
    if "\n\n".join(blocks) != response["context"]:
        raise ValueError("Context contains text outside exact citation framing and verified snippets")
    if case["kind"] == "empty_scope" and response["results"]:
        raise ValueError("An unknown project silently returned another scope")
    matched = []
    for gold in case["required"]:
        found = False
        for hit in response["results"]:
            for ref in hit["source_refs"]:
                identity = (ref["project"], ref["session_id"], ref["turn_index"])
                if (ref["session_id"] == gold["session_id"] and gold["quote"] in hit["text"]
                        and gold["quote"] in originals[identity][ref["turn_start"]:ref["turn_end"]]):
                    found = True
        matched.append(found)
    answerable = case["kind"] == "answerable"
    return {"kind": case["kind"], "required_spans": len(matched), "matched_spans": sum(matched),
            "complete_evidence": bool(matched) and all(matched),
            "first_session": sessions[0] if sessions else None,
            "expected_first": case["expected_first_session"],
            "first_correct": sessions[:1] == [case["expected_first_session"]] if answerable else None,
            "missing_evidence_nonempty": case["kind"] == "missing" and bool(response["context"]),
            "context_chars": len(response["context"])}


def validate_rows(rows):
    expected, seen = matrix(), {}
    for row in rows:
        key = (row["case_id"], row["mode"], row["budget_chars"], row["limit"])
        if key not in expected or key in seen:
            raise ValueError("Unknown or duplicate evaluation row")
        scenario, case = expected[key]
        if (row["project"] != case["project"] or row["query"] != case["query"]
                or row["category"] != case["category"] or row["scenario"] != scenario["id"]):
            raise ValueError("Case request or category labels differ from frozen dataset")
        score = verify_and_score(case, scenario, row["response"], row["original_pages"],
                                 mode=key[1], budget=key[2], limit=key[3])
        if score != row["score"]:
            raise ValueError("Producer score differs from independent original-source recomputation")
        seen[key] = row
    if seen.keys() != expected.keys():
        raise ValueError("Incomplete evaluation response matrix")
    return seen


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["mode"], row["budget_chars"], row["limit"], row["score"]["kind"])].append(row)
    result = []
    for (mode, budget, limit, kind), group in sorted(groups.items()):
        scores = [r["score"] for r in group]
        result.append({"mode": mode, "budget_chars": budget, "limit": limit, "kind": kind,
                       "cases": len(scores), "first_correct": sum(s["first_correct"] is True for s in scores),
                       "complete_evidence": sum(s["complete_evidence"] for s in scores),
                       "required_spans": sum(s["required_spans"] for s in scores),
                       "matched_spans": sum(s["matched_spans"] for s in scores),
                       "missing_evidence_nonempty": sum(s["missing_evidence_nonempty"] for s in scores),
                       "mean_context_chars": sum(s["context_chars"] for s in scores) / len(scores)})
    return result


def worker(args):
    import memory_book
    import memory_book.store as store
    from memory_book._text_backend import BACKEND_NAME
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if (Path(memory_book.__file__).resolve().parent != source / "src/memory_book"
            or Path(store.__file__).resolve() != source / "src/memory_book/store.py"
            or BACKEND_NAME != args.backend):
        raise ValueError("Actual package/store/backend differs from selected source")
    before, evaluator = source_identity(source, args.commit), evaluator_identity()
    loaded = sys.modules.get("memory_book._native")
    binary = Path(loaded.__file__).resolve() if loaded is not None else None
    if args.backend == "native" and (binary is None or binary.parent != source / "src/memory_book"):
        raise ValueError("Actual native extension is not from selected snapshot")
    proof = {"protocol": PROTOCOL, "status": "started", "backend": BACKEND_NAME,
             "python": sys.version, "platform": platform.platform(), "version": memory_book.__version__,
             "recall_version": store.RECALL_VERSION, "imported_package": str(Path(memory_book.__file__).resolve()),
             "source_before": before, "evaluator": evaluator,
             "loaded_native": {"path": str(binary), "sha256": sha(binary.read_bytes())} if binary else None}
    write(output / "report.json", proof)
    write(output / "dataset.json", workload())
    rows = []
    try:
        with (output / "raw.jsonl").open("x", encoding="utf-8") as raw, (output / "journal.jsonl").open("x", encoding="utf-8") as journal:
            for scenario in workload():
                with memory_book.MemoryBook(":memory:", segmentation="turn") as book:
                    for session in scenario["sessions"]:
                        book.ingest(session)
                    for case in scenario["cases"]:
                        for mode in MODES:
                            for budget in BUDGETS:
                                for limit in LIMITS:
                                    labels = {"case_id": case["id"], "scenario": scenario["id"],
                                              "project": case["project"], "query": case["query"],
                                              "category": case["category"], "mode": mode,
                                              "budget_chars": budget, "limit": limit}
                                    journal.write(json.dumps({**labels, "status": "started"}, ensure_ascii=False) + "\n")
                                    journal.flush()
                                    os.fsync(journal.fileno())
                                    response = book.recall(case["query"], project=case["project"], temporal=mode,
                                                           limit=limit, budget_chars=budget, use_cache=False)
                                    pages = {h["id"]: book.read(h["id"], project=case["project"], limit=100000)
                                             for h in response["results"]}
                                    score = verify_and_score(case, scenario, response, pages, mode=mode, budget=budget, limit=limit)
                                    row = {**labels, "response": response, "original_pages": pages, "score": score}
                                    raw.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                                    raw.flush()
                                    os.fsync(raw.fileno())
                                    rows.append(row)
                                    journal.write(json.dumps({**labels, "status": "completed"}, ensure_ascii=False) + "\n")
                                    journal.flush()
        validate_rows(rows)
        after = source_identity(source, args.commit)
        if before != after or evaluator != evaluator_identity() or (binary and sha(binary.read_bytes()) != proof["loaded_native"]["sha256"]):
            raise ValueError("Runtime/evaluator/native binary changed during execution")
        proof.update(status="completed", source_after=after, responses=len(rows), summary=summarize(rows))
    except BaseException as error:
        proof.update(status="failed", error={"type": type(error).__name__, "message": str(error)}, responses=len(rows))
        raise
    finally:
        path = output / "raw.jsonl"
        if path.exists():
            content = path.read_bytes()
            stored = gzip.compress(content, mtime=0)
            path.with_suffix(".jsonl.gz").write_bytes(stored)
            proof["raw"] = {"sha256": sha(content), "stored_sha256": sha(stored), "bytes": len(content)}
            path.unlink()
        write(output / "report.json", proof)


def audit(output):
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    if (report["status"] != "completed" or report["protocol"] != PROTOCOL
            or report["evaluator"] != evaluator_identity() or report["source_before"] != report["source_after"]
            or json.loads((output / "dataset.json").read_text(encoding="utf-8")) != workload()):
        raise ValueError("Report is incomplete or source/evaluator/dataset binding differs")
    raw = (output / "raw.jsonl.gz").read_bytes()
    decoded = gzip.decompress(raw)
    if (sha(raw) != report["raw"]["stored_sha256"] or sha(decoded) != report["raw"]["sha256"]
            or len(decoded) != report["raw"]["bytes"]):
        raise ValueError("Saved raw evidence hashes differ")
    rows = [json.loads(line) for line in decoded.splitlines()]
    validated = validate_rows(rows)
    if report["responses"] != len(validated) or report["summary"] != summarize(rows):
        raise ValueError("Saved summary differs from independent full-row recomputation")
    return {"status": "verified", "responses": len(validated), "summary": summarize(rows)}


def compare(first, second):
    for path in (first, second):
        audit(path)
    def load(path):
        return validate_rows([json.loads(line) for line in gzip.decompress((path / "raw.jsonl.gz").read_bytes()).splitlines()])
    a, b = load(first), load(second)
    changes, regressions, controls = [], [], []
    for key in a:
        old, new = a[key], b[key]
        sa, sb = old["score"], new["score"]
        if sa != sb:
            changes.append({"cell": key, "before": sa, "after": sb})
        if key[1] == "auto" and ((sa["first_correct"] is True and sb["first_correct"] is not True)
                or sa["matched_spans"] > sb["matched_spans"]):
            regressions.append({"cell": key, "before": sa, "after": sb})
        if key[1] == "relevance" and any(old["response"][field] != new["response"][field]
                for field in ("results", "context", "candidate_count")):
            controls.append(key)
    return {"responses_per_arm": len(a), "score_changes": changes, "regressions": regressions,
            "relevance_payload_changes": controls}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--backend", choices=("python", "native"), default="python")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--compare", type=Path, help="Compare an existing baseline output against --output")
    args = parser.parse_args()
    if args.audit:
        result = audit(args.output.resolve())
    elif args.compare:
        result = compare(args.compare.resolve(), args.output.resolve())
    elif args.worker:
        worker(args)
        result = audit(args.output.resolve())
    else:
        if not args.source or not args.commit:
            parser.error("--source and --commit are required for an immutable execution")
        if args.output.exists():
            parser.error("Use a new output path; previous attempts must be retained")
        env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(args.source.resolve() / "src"), str(ROOT))),
               "PYTHONDONTWRITEBYTECODE": "1", "MEMORY_BOOK_TEXT_BACKEND": args.backend}
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--source", str(args.source.resolve()),
                        "--commit", args.commit, "--backend", args.backend, "--output", str(args.output.resolve())],
                       env=env, cwd=args.source, check=True)
        result = audit(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
