"""Source-bound v0.13 small development diagnostic with saved-row audits.

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
from benchmarks.v012_revision_cases import original_sources
from benchmarks.v013_accuracy_cases import workload
from benchmarks.v012_revision_eval import verify_and_score as verify_source_response
from scripts.validate_v011_revision_recovery import source_identity

BASELINE = "8044e4bafe18e73ea422af5eeb47ef961e65246c"
PROTOCOL = "v013-current-evidence-development-v1"
BUDGETS = (1200, 2400)
LIMITS = (1, 5)
MODES = ("auto", "relevance")
EVALUATOR_FILES = (
    "benchmarks/v013_accuracy_cases.py", "benchmarks/v013_accuracy_eval.py",
    "benchmarks/experiments/v013-accuracy-protocol.json",
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
    """Retain the unchanged original-source verifier and score new metadata separately."""
    score = verify_source_response(case, scenario, response, pages,
                                   mode=mode, budget=budget, limit=limit)
    assessment = response["temporal"].get("evidence_assessment")
    status = assessment.get("status") if isinstance(assessment, dict) else None
    expected = case["expected_assessment"] if mode == "auto" else "not_assessed"
    score.update(assessment_status=status, expected_assessment=expected,
                 assessment_correct=status == expected,
                 preserve_occurrences=response["temporal"]["preserve_occurrences"],
                 expected_preserve_occurrences=case["expected_preserve_occurrences"],
                 occurrence_intent_correct=response["temporal"]["preserve_occurrences"]
                     == case["expected_preserve_occurrences"])
    return score


def diagnostic_ids(response):
    assessment = response.get("temporal", {}).get("evidence_assessment") or {}
    conflicts = assessment.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise ValueError("Conflict diagnostics must be an explicit list")
    result = set()
    for conflict in conflicts:
        ids = conflict.get("page_ids")
        if not isinstance(ids, list) or len(ids) < 2 or len(set(ids)) != len(ids):
            raise ValueError("A potential conflict needs distinct source page IDs")
        result.update(ids)
    return result


def verify_diagnostics(case, scenario, response, pages):
    """Source metadata must obey the same exact project even outside the context."""
    wanted = diagnostic_ids(response)
    if set(pages) != wanted:
        raise ValueError("Missing or extra diagnostic source reads")
    originals = original_sources(scenario)
    for page_id, page in pages.items():
        if page["id"] != page_id or len(page["source_refs"]) != 1:
            raise ValueError("Diagnostic page identity differs")
        ref = page["source_refs"][0]
        identity = (ref["project"], ref["session_id"], ref["turn_index"])
        raw = originals.get(identity)
        if (identity[0] != case["project"] or raw is None or page["content"] != raw
                or page["offset"] != 0 or page["next_offset"] is not None
                or page["total_chars"] != len(raw)
                or [ref[k] for k in ("start", "end", "turn_start", "turn_end")]
                   != [0, len(raw), 0, len(raw)]
                or page["breadcrumb"][0]["id"] != case["project"]):
            raise ValueError("Diagnostic page crosses scope or changes original bytes")


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
        verify_diagnostics(case, scenario, row["response"], row["diagnostic_pages"])
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
                       "mean_context_chars": sum(s["context_chars"] for s in scores) / len(scores),
                       "assessment_correct": sum(s["assessment_correct"] for s in scores),
                       "occurrence_intent_correct": sum(s["occurrence_intent_correct"] for s in scores)})
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
                                    diagnostic_pages = {identity: book.read(identity, project=case["project"], limit=100000)
                                                        for identity in diagnostic_ids(response)}
                                    verify_diagnostics(case, scenario, response, diagnostic_pages)
                                    score = verify_and_score(case, scenario, response, pages, mode=mode, budget=budget, limit=limit)
                                    row = {**labels, "response": response, "original_pages": pages, "diagnostic_pages": diagnostic_pages, "score": score}
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
    changes, regressions, controls, temporal_controls = [], [], [], []
    for key in a:
        old, new = a[key], b[key]
        sa, sb = old["score"], new["score"]
        if sa != sb:
            changes.append({"cell": key, "before": sa, "after": sb})
        if key[1] == "auto" and ((sa["first_correct"] is True and sb["first_correct"] is not True)
                or sa["matched_spans"] > sb["matched_spans"]):
            regressions.append({"cell": key, "before": sa, "after": sb})
        if key[1] == "auto" and old["category"] in {"occurrence_control", "historical_control"} and any(
                old["response"][field] != new["response"][field]
                for field in ("results", "context", "candidate_count")):
            temporal_controls.append(key)
        if key[1] == "relevance" and any(old["response"][field] != new["response"][field]
                for field in ("results", "context", "candidate_count")):
            controls.append(key)
    return {"responses_per_arm": len(a), "score_changes": changes, "regressions": regressions,
            "relevance_payload_changes": controls, "occurrence_history_payload_changes": temporal_controls}


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
