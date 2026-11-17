#!/usr/bin/env python3
"""Paired chapter-directory measurements against exact historical methods.

Both arms read the same frozen archive. Fixture creation, validation, tracing,
materialization audits and report writes are outside the latency timers. Raw
observations are appended immediately and partial reports survive failures.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "238c8058f723a203eaca99f94d924ab77de4c0b3"
SOURCE = "src/memory_book/store.py"
PLAN = "benchmarks/directory-runtime-plan.json"
CONFIGURATIONS = [(sections, pages) for sections in (1, 20, 100) for pages in (1, 20, 100)]


def exact_bytes(value):
    # Keep insertion order too: the golden check covers emitted JSON as well as dictionaries.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def git(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


class Recorder:
    def __init__(self, output):
        self.output = output.resolve()
        self.events_path = self.output.with_suffix(".events.jsonl")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if self.output.exists() or self.events_path.exists():
            raise FileExistsError("benchmark outputs already exist; select a new output path")
        self.events = self.events_path.open("x", encoding="utf-8")

    def event(self, value):
        self.events.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        self.events.flush()
        os.fsync(self.events.fileno())

    def save(self, report):
        descriptor, temporary = tempfile.mkstemp(prefix=self.output.name + ".", suffix=".tmp", dir=self.output.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.output)
        finally:
            Path(temporary).unlink(missing_ok=True)


def baseline_type(commit):
    source = git("show", f"{commit}:{SOURCE}")
    tree = ast.parse(source)
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"_integer", "_string"}]
    book = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MemoryBook")
    methods = [node for node in book.body if isinstance(node, ast.FunctionDef) and node.name in {"chapter", "section"}]
    if len(helpers) != 2 or len(methods) != 2:
        raise ValueError("baseline directory methods or validators are missing")
    extracted = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                                *helpers, ast.ClassDef(name="BaselineDirectory", bases=[], keywords=[],
                                                      body=methods, decorator_list=[])], type_ignores=[])
    namespace = {"json": json}
    exec(compile(ast.fix_missing_locations(extracted), f"{commit}:{SOURCE}", "exec"), namespace)
    return namespace["BaselineDirectory"], {"commit": commit, "source_sha256": sha256(source),
        "blob": git("rev-parse", f"{commit}:{SOURCE}").decode().strip(),
        "extracted": ["_integer", "_string", "MemoryBook.chapter", "MemoryBook.section"]}


def create_fixture(book):
    chapter = None
    for project, count in (("directory-target", 100), ("directory-unrelated", 3)):
        for number in range(count):
            paragraphs = [f"Session {number:03d}, evidence {part:03d}: retain this exact directory source and all original constraints, including Unicode text 原始证据."
                          for part in range(130)]
            saved = book.ingest({"project": project, "project_name": "Directory benchmark",
                "session_id": f"session-{number:03d}", "task_id": "directory-task",
                "task_title": "A bounded directory", "title": f"Session {number:03d}",
                "created_at": f"2026-10-0{number % 3 + 1}T08:00:00Z",
                "messages": [{"role": "user", "content": f"Which evidence belongs to session {number:03d}?"},
                             {"role": "assistant", "content": "\n\n".join(paragraphs)}]})
            if project == "directory-target":
                chapter = saved["chapter_id"]
    # Freeze incidental creation timestamps so the fixture digest is reproducible.
    book.db.execute("UPDATE projects SET created_at='2026-10-01T00:00:00Z',updated_at='2026-10-01T00:00:00Z'")
    book.db.execute("UPDATE chapters SET updated_at='2026-10-01T00:00:00Z'")
    book.db.execute("UPDATE sessions SET updated_at='2026-10-01T00:00:00Z'")
    counts = [row[0] for row in book.db.execute("SELECT COUNT(*) FROM pages WHERE chapter_id=? GROUP BY section_id", (chapter,))]
    if len(counts) != 100 or min(counts) <= 100:
        raise AssertionError("fixture must have 100 target sections with more than 100 pages each")
    digest = hashlib.sha256()
    tables = {}
    for table in ("projects", "chapters", "sessions", "sections", "pages"):
        tables[table] = 0
        for row in book.db.execute(f"SELECT * FROM {table} ORDER BY " + ("rid" if table == "pages" else "id")):
            digest.update(exact_bytes([table, list(row)]))
            digest.update(b"\n")
            tables[table] += 1
    return chapter, {"sha256": digest.hexdigest(), "tables": tables, "target_sections": len(counts),
        "target_pages_per_section": {"minimum": min(counts), "maximum": max(counts)},
        "project": "directory-target", "chapter_id": chapter, "segmentation": "adaptive",
        "max_page_chars": 128, "sqlite_storage": "temporary on-disk WAL archive",
        "freeze": "same connection for timed arms; query_only=ON; separate audit connection"}


def directory_readers(book, historical, chapter, sections, page_limit):
    baseline = historical()
    baseline.db = book.db
    options = {"project": "directory-target", "limit": sections, "page_limit": page_limit}
    return {"baseline": lambda: baseline.chapter(chapter, **options),
            "candidate": lambda: book.chapter(chapter, **options)}


def audit(reader, db, evaluated):
    statements = []
    evaluated.clear()
    db.set_trace_callback(statements.append)
    try:
        result = reader()
    finally:
        db.set_trace_callback(None)
    if db.in_transaction:
        raise AssertionError("directory reader leaked a transaction")
    previews = sum(len(section["pages"]) for section in result["sections"])
    if len(evaluated) != previews:
        raise AssertionError("directory evaluated content outside its returned page previews")
    return result, {"select_count": sum(sql.lstrip().upper().startswith("SELECT") for sql in statements),
        "statement_count": len(statements), "materialized_previews": previews,
        "content_length_evaluations": len(evaluated), "statements": statements}


def measure(operation):
    wall = time.perf_counter_ns()
    cpu = time.process_time_ns()
    try:
        result = operation()
    except BaseException as exc:
        cpu_ns = time.process_time_ns() - cpu
        wall_ns = time.perf_counter_ns() - wall
        return None, {"wall_ns": wall_ns, "process_cpu_ns": cpu_ns}, exc
    cpu_ns = time.process_time_ns() - cpu
    wall_ns = time.perf_counter_ns() - wall
    return result, {"wall_ns": wall_ns, "process_cpu_ns": cpu_ns}, None


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize(configuration):
    result = {}
    for metric in ("wall_ns", "process_cpu_ns"):
        arms = {arm: [sample[metric] for trial in configuration["rounds"] for sample in trial["arms"][arm]]
                for arm in ("baseline", "candidate")}
        medians = {arm: statistics.median(values) for arm, values in arms.items()}
        paired = [ratio(statistics.median(sample[metric] for sample in trial["arms"]["candidate"]),
                        statistics.median(sample[metric] for sample in trial["arms"]["baseline"]))
                  for trial in configuration["rounds"]]
        result[metric] = {"median_per_call": medians, "paired_candidate_over_baseline": paired,
                          "median_paired_ratio": statistics.median(value for value in paired if value is not None)}
    return result


def run(args, recorder, report):
    sys.path.insert(0, str(ROOT / "src"))
    from memory_book import MemoryBook
    from memory_book import store

    historical, provenance = baseline_type(args.baseline_commit)
    source_bytes = (ROOT / SOURCE).read_bytes()
    report["sources"] = {"baseline": provenance, "candidate": {"source_sha256": sha256(source_bytes),
        "head": git("rev-parse", "HEAD").decode().strip(),
        "source_status": git("status", "--porcelain", "--", SOURCE).decode().strip()},
        "harness_sha256": sha256(Path(__file__).read_bytes()), "protocol_sha256": sha256((ROOT / PLAN).read_bytes())}
    report["native_backend_loaded"] = store._NATIVE is not None
    recorder.save(report)
    with tempfile.TemporaryDirectory(prefix="memory-book-directory-runtime-") as temporary:
        path = Path(temporary) / "fixture.db"
        with MemoryBook(path, segmentation="adaptive", max_page_chars=128, min_page_chars=0) as fixture:
            chapter, report["fixture"] = create_fixture(fixture)
        with MemoryBook(path) as book, MemoryBook(path) as audit_book:
            book.db.execute("PRAGMA query_only=ON")
            audit_book.db.execute("PRAGMA query_only=ON")
            evaluated = []
            audit_book.db.create_function("length", 1, lambda value: evaluated.append(1) or len(value))
            for sections, page_limit in CONFIGURATIONS:
                identity = f"sections-{sections}-pages-{page_limit}"
                configuration = {"id": identity, "sections": sections, "page_limit": page_limit,
                                 "audit": {}, "rounds": []}
                report["configurations"].append(configuration)
                audit_readers = directory_readers(audit_book, historical, chapter, sections, page_limit)
                expected = None
                for arm in ("baseline", "candidate"):
                    result, measurements = audit(audit_readers[arm], audit_book.db, evaluated)
                    serialized = exact_bytes(result)
                    if expected is None:
                        expected = serialized
                    elif serialized != expected:
                        raise AssertionError(f"{identity}: audit output differs from baseline")
                    measurements["output_sha256"] = sha256(serialized)
                    configuration["audit"][arm] = measurements
                configuration["exact_equality"] = True
                recorder.event({"event": "audit", "configuration": identity, "audit": configuration["audit"]})
                recorder.save(report)
                if args.validate_only:
                    continue
                readers = directory_readers(book, historical, chapter, sections, page_limit)
                for arm in ("baseline", "candidate"):
                    for _ in range(2):
                        if exact_bytes(readers[arm]()) != expected:
                            raise AssertionError(f"{identity}: warmup output differs from baseline")
                for number in range(args.rounds):
                    order = ["baseline", "candidate"] if number % 2 == 0 else ["candidate", "baseline"]
                    trial = {"round": number, "order": order, "arms": {}}
                    configuration["rounds"].append(trial)
                    for position, arm in enumerate(order):
                        trial["arms"][arm] = []
                        for call in range(args.iterations):
                            result, measurement, error = measure(readers[arm])
                            observation = {"call": call, **measurement}
                            trial["arms"][arm].append(observation)
                            if error is None:
                                serialized = exact_bytes(result)
                                observation.update(output_sha256=sha256(serialized), exact_equality=serialized == expected)
                                if serialized != expected:
                                    error = AssertionError(f"{identity}: timed {arm} output differs from baseline")
                            if error is not None:
                                observation["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
                            recorder.event({"event": "call", "configuration": identity, "round": number,
                                            "order_position": position, "arm": arm, **observation})
                            if error is not None:
                                raise error
                            if book.db.in_transaction:
                                raise AssertionError("timed directory reader leaked a transaction")
                            del result
                        recorder.save(report)
                    recorder.event({"event": "round_completed", "configuration": identity, "round": number})
                    recorder.save(report)
                configuration["summary"] = summarize(configuration)
                recorder.save(report)
            if book.db.total_changes or audit_book.db.total_changes:
                raise AssertionError("a measurement connection changed the frozen archive")
    if (ROOT / SOURCE).read_bytes() != source_bytes:
        raise AssertionError("candidate source changed during measurement")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-commit", default=BASELINE_COMMIT)
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--validate-only", action="store_true", help="perform only untimed fixture and contract audits")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.baseline_commit):
        parser.error("baseline-commit must be a full lowercase Git commit SHA")
    if args.rounds < 2 or args.rounds > 20 or args.rounds % 2 or not 1 <= args.iterations <= 1000:
        parser.error("rounds must be even and between 2 and 20; iterations must be between 1 and 1000")
    recorder = Recorder(args.output)
    report = {"schema_version": 1, "protocol": "directory-runtime-v1", "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
                        "cpu_count": os.cpu_count(), "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")},
        "arguments": {**vars(args), "output": str(args.output)}, "configurations": [],
        "protocol_parameters_match": args.rounds == 4 and args.iterations == 20 and args.baseline_commit == BASELINE_COMMIT,
        "events_path": str(recorder.events_path),
        "scope": "chapter directory component only; no recall or end-to-end speedup claim"}
    try:
        recorder.save(report)
        recorder.event({"event": "started", "arguments": report["arguments"]})
        run(args, recorder, report)
        report["status"] = "validated" if args.validate_only else "completed"
        recorder.event({"event": report["status"], "configurations": len(report["configurations"])})
        returncode = 0
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        recorder.event({"event": "failed", "error": report["error"]})
        print(f"Directory benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        returncode = 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        recorder.save(report)
        recorder.events.close()
    print(json.dumps({"status": report["status"], "configurations": len(report["configurations"]),
                      "report": str(recorder.output), "events": str(recorder.events_path)}))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
