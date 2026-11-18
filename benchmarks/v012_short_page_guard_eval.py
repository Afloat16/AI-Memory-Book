"""Verify the fixed 482 short-page review configurations on committed source.

The earlier exploratory probe retains complete before/after payloads for its
34 regressions and presence observations for all 482 configurations. This
driver retains every new payload and checks every original source slice.
Its evidence is a development regression check, not a held-out accuracy score.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from benchmarks.engineering_workflow import evidence_rank, source_errors
from scripts.validate_v011_revision_recovery import source_identity
from tests.test_current_turn_recall import same_page_session

ORIGINAL = "benchmarks/reports/v0.12-development/evaluation/short-page-review-attempt1.json"
PINS = {
    ORIGINAL: "bef1bc2e3bf02963f56aaffb2f935ba86970263255cf6a730cb0a942627f3e51",
    "benchmarks/experiments/v012-short-page-review-probe.py": "56e0fbccc4c633c4b57283abcb672d23f82119d630d3e23ce4c2621a9dc5610c",
    "tests/test_current_turn_recall.py": "548f37050123c96683d1d648c031aca4a2de50dbddd9a16b702f578ecf96b6fe",
}
PROTOCOL = "v012-protected-current-span-review-v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def binding():
    for name, expected in PINS.items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise ValueError("Original review or fixture changed: " + name)
    files = tuple(PINS) + ("benchmarks/v012_short_page_guard_eval.py", "benchmarks/engineering_workflow.py",
                          "scripts/validate_v011_revision_recovery.py")
    return {name: sha((ROOT / name).read_bytes()) for name in files}


def fixture(size):
    source = same_page_session()
    sessions = [source]
    for index in range(2):
        short = copy.deepcopy(source)
        short["session_id"] = "memo-" + str(index)
        body = "Gradient accumulation steps require checking the original decision. "
        body += "Supporting administrative detail. " * 8
        short["messages"] = [{"role": "assistant", "content": body[:size - 11]}]
        sessions.append(short)
    originals, pages = {}, {}
    for session in sessions:
        turns = []
        for ordinal, start in enumerate(range(0, len(session["messages"]), 2)):
            text = "\n\n".join(m["role"].upper() + ": " + m["content"]
                              for m in session["messages"][start:start + 2])
            originals[(session["project"], session["session_id"], ordinal)] = text
            turns.append(text)
        pages[session["session_id"]] = "\n\n".join(turns)
    return sessions, originals, pages


def observed(response, pages, size, budget):
    _, originals, full_bodies = fixture(size)
    if (response["query"] != "current gradient accumulation steps" or response["budget_chars"] != budget
            or response["context_chars"] != len(response["context"]) or len(response["context"]) > budget
            or response["cache_hit"] is not False or response["strategy"] != "book"
            or response["temporal"]["requested"] != "auto" or len(response["results"]) > 3):
        raise ValueError("Request, temporal, cache, result count or budget differs")
    errors = source_errors(response, originals, "trainer")
    if errors:
        raise ValueError("Original source check failed: " + str(errors))
    ids = [hit["id"] for hit in response["results"]]
    if len(ids) != len(set(ids)) or set(ids) != set(pages):
        raise ValueError("Duplicate result or missing/extra original page follow-up")
    blocks = []
    for hit in response["results"]:
        page = pages[hit["id"]]
        session = hit["source_refs"][0]["session_id"]
        if (page["id"] != hit["id"] or page["content"] != full_bodies.get(session)
                or page["offset"] != 0 or page["next_offset"] is not None
                or page["total_chars"] != len(page["content"]) or hit["page_chars"] != len(page["content"])
                or page["created_at"] != hit["created_at"]
                or page["breadcrumb"][0]["id"] != "trainer" or hit["breadcrumb"][0]["id"] != "trainer"
                or any(ref["project"] != "trainer" or ref["session_id"] != session for ref in page["source_refs"])):
            raise ValueError("Original follow-up page differs from the frozen session")
        for ref in hit["source_refs"]:
            if page["content"][ref["start"]:ref["end"]] != originals[("trainer", session, ref["turn_index"])][ref["turn_start"]:ref["turn_end"]]:
                raise ValueError("Absolute page offsets differ from original-turn offsets")
        blocks.append(f'[{hit["id"]}] trainer / {session} | {hit["created_at"]}\n' + hit["text"])
    if response["context"] != "\n\n".join(blocks):
        raise ValueError("Context contains unsupported text outside verified snippets and framing")
    return evidence_rank({"session_id": "s1", "quote": "steps are now 2"}, response, originals, "trainer") is not None


def controls():
    binding()
    original = json.loads((ROOT / ORIGINAL).read_text(encoding="utf-8"))
    expected = {(size, budget) for size in (180, 230) for budget in range(400, 1601, 5)}
    values = {}
    for row in original["observations"]:
        key = (row["short_record_chars"], row["budget_chars"])
        if key not in expected or key in values or type(row["control_current_present"]) is not bool:
            raise ValueError("Original control inventory differs")
        values[key] = row["control_current_present"]
    if (values.keys() != expected or original["status"] != "completed" or not original["source_unchanged"]
            or original["source_before"] != original["source_after"] or len(original["regressions"]) != 34):
        raise ValueError("Original working-tree observation is incomplete or changed")
    # Complete original payloads exist for these 34 specifically observed
    # regressions; independently check those instead of fabricating missing
    # original payloads for the other 448 configurations.
    bad = set()
    for row in original["regressions"]:
        key = (row["short_record_chars"], row["budget_chars"])
        if key in bad or key not in expected or not values[key]:
            raise ValueError("Original regression inventory differs")
        for label, wanted in (("control", True), ("candidate", False)):
            response = row[label]
            pages = {hit["id"]: row["original_pages"][hit["id"]] for hit in response["results"]}
            if observed(response, pages, *key) is not wanted:
                raise ValueError("Original complete regression payload contradicts the recorded observation")
        bad.add(key)
    return values, bad


def validate_rows(rows):
    expected, original_regressions = controls()
    seen, losses, retained_regressions = {}, [], []
    for row in rows:
        key = (row["short_record_chars"], row["budget_chars"])
        if key not in expected or key in seen:
            raise ValueError("Unknown or duplicate guard-check configuration")
        present = observed(row["response"], row["original_pages"], *key)
        if row["current_present"] is not present or row["control_current_present"] is not expected[key]:
            raise ValueError("Guard producer's evidence claim differs from source-checked observation")
        if expected[key] and not present:
            losses.append(key)
        if key in original_regressions and present:
            retained_regressions.append(key)
        seen[key] = row
    if seen.keys() != expected.keys():
        raise ValueError("Incomplete 482-configuration guard check")
    return {"configurations": len(seen), "recorded_control_current_present": sum(expected.values()),
            "current_present": sum(r["current_present"] for r in rows), "lost_recorded_controls": losses,
            "original_regressions": len(original_regressions),
            "original_regressions_recovered": len(retained_regressions),
            "original_control_payloads_independently_verified": 34,
            "other_original_controls": "presence observations only; no missing original payloads reconstructed"}


def worker(args):
    import memory_book
    import memory_book.store as store
    from memory_book._text_backend import BACKEND_NAME
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if (Path(memory_book.__file__).resolve().parent != source / "src/memory_book"
            or Path(store.__file__).resolve() != source / "src/memory_book/store.py" or BACKEND_NAME != args.backend):
        raise ValueError("Actual imported source/backend differs")
    before, evaluator = source_identity(source, args.commit), binding()
    module = sys.modules.get("memory_book._native")
    binary = Path(module.__file__).resolve() if module is not None else None
    if args.backend == "native" and (binary is None or binary.parent != source / "src/memory_book"):
        raise ValueError("Actual native extension differs from selected worktree")
    report = {"protocol": PROTOCOL, "status": "started", "source_before": before,
              "backend": BACKEND_NAME, "python": sys.version, "evaluator": evaluator,
              "loaded_native": {"path": str(binary), "sha256": sha(binary.read_bytes())} if binary else None}
    write(output / "report.json", report)
    original, _ = controls()
    rows = []
    try:
        with (output / "raw.jsonl").open("x", encoding="utf-8") as raw:
            for size in (180, 230):
                sessions, _, _ = fixture(size)
                with memory_book.MemoryBook(":memory:") as book:
                    for session in sessions:
                        book.ingest(session)
                    for budget in range(400, 1601, 5):
                        response = book.recall("current gradient accumulation steps", project="trainer", limit=3,
                                               budget_chars=budget, use_cache=False)
                        pages = {h["id"]: book.read(h["id"], project="trainer", limit=100000) for h in response["results"]}
                        row = {"short_record_chars": size, "budget_chars": budget,
                               "response": response, "original_pages": pages,
                               "control_current_present": original[(size, budget)],
                               "current_present": observed(response, pages, size, budget)}
                        raw.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                        raw.flush()
                        os.fsync(raw.fileno())
                        rows.append(row)
        summary = validate_rows(rows)
        after = source_identity(source, args.commit)
        if before != after or binding() != evaluator or (binary and sha(binary.read_bytes()) != report["loaded_native"]["sha256"]):
            raise ValueError("Source/evaluator/native extension changed during guard review")
        report.update(status="completed", source_after=after, summary=summary,
                      accepted=not summary["lost_recorded_controls"] and summary["original_regressions_recovered"] == 34)
    except BaseException as error:
        report.update(status="failed", accepted=False, error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        raw_path = output / "raw.jsonl"
        if raw_path.exists():
            content = raw_path.read_bytes()
            archive = gzip.compress(content, mtime=0)
            raw_path.with_suffix(".jsonl.gz").write_bytes(archive)
            report["raw_sha256"] = sha(content)
            report["archive_sha256"] = sha(archive)
            raw_path.unlink()
        write(output / "report.json", report)
    print(json.dumps({"status": report["status"], "accepted": report["accepted"], "summary": report["summary"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--backend", choices=("python", "native"), default="native")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args)
    else:
        if args.output.exists():
            parser.error("Use a new output path; earlier attempts remain intact")
        env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(args.source.resolve() / "src"), str(ROOT))),
               "PYTHONDONTWRITEBYTECODE": "1", "MEMORY_BOOK_TEXT_BACKEND": args.backend}
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--source", str(args.source.resolve()),
                        "--commit", args.commit, "--backend", args.backend, "--output", str(args.output.resolve())],
                       env=env, cwd=args.source, check=True)


if __name__ == "__main__":
    main()
