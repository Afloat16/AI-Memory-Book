"""Native SQLite callsite observations on exact LM; no speed or fresh claims.

Independent prospective diagnostic. C spans are partial observations; implicit
cursor iteration is explicitly unattributed. A missing binding blocks all calls.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from types import BuiltinMethodType
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = "round5-lm-sql-attribution-1"
BRANCH = "validation/v033-lm-sql-attribution-1"
TRIGGER = "refs/heads/ci/v033-lm-sql-attribution-1"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SCOPE = ROOT / "benchmarks/experiments/round5-lm-sql-attribution-scope.json"
SCOPE_SHA = "0b3a249df45a25a00f76f4ad2c6e0cfa56fc7147a19e982fca429884c5ef1269"
SOURCE_BINDING = ROOT / "benchmarks/experiments/round5-lm-sql-attribution-source.json"
OLD = ROOT / "benchmarks/experiments/round5-development-attempt-i.json"
OLD_SHA = "02067bdd4c38bd1fcd2a3feef5974aa7bf9eac213e6009ddd64ead37356b7ad5"
REFERENCE_COMMIT = "761eaf5c9ca47c93dea25f73104eb259304df68a"
SOURCE_COMMIT = "49f10e7dec006e3a5760c93623a650dc7b6338d6"
RUNTIME_SHA = "fa56d26927ca625414ae9c9265ab285f2f8e714ec7ed015170e0bdd82d8a5bcd"
SCRIPT_PATH = "scripts/round5_lm_sql_attribution.py"
TEST_PATH = "tests/test_round5_lm_sql_attribution.py"
WORKFLOW_PATH = ".github/workflows/round5-lm-sql-attribution.yml"
COHORTS = ("synthetic61", "public1015")
CONFIG_NAMES = ("native-char4000", "native-token512", "native-token1024", "native-token2048")
NATIVE_CONNECTION, NATIVE_CURSOR = sqlite3.Connection, sqlite3.Cursor
NATIVE_ROW, NATIVE_CONNECT = sqlite3.Row, sqlite3.connect
PRIMARY_METHODS = frozenset(("Connection.execute", "Cursor.fetchall", "Cursor.fetchone"))


class PublicationError(RuntimeError):
    pass


class ObserverFailure(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def parse_remote(raw):
    fields = raw.split()
    if not fields:
        return None
    if len(fields) != 2 or fields[1] != "refs/heads/" + BRANCH or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise PublicationError("Unexpected remote result-ref response")
    return fields[0]


def remote_head():
    return parse_remote(git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH))


def publish(message):
    """One non-force push; reject divergent refs and never retry ambiguous writes."""
    journal = STATE / "publication.json"
    if (PUBLIC / "publication-failure.json").exists():
        raise PublicationError("Publication already failed; artifact-only preservation")
    expected = read(journal)["expected_remote"]
    parent = git("rev-parse", "HEAD")
    try:
        if remote_head() != expected:
            raise PublicationError("Another writer owns or advanced the result ref")
        if expected is not None and parent != expected:
            raise PublicationError("Local result ancestry changed")
        if git("diff", "--cached", "--name-only"):
            raise PublicationError("Unrelated staged changes")
        subprocess.run(["git", "add", "--sparse", "--", str(PUBLIC.relative_to(ROOT))], cwd=ROOT, check=True)
        staged = git("diff", "--cached", "--name-only").splitlines()
        prefix = str(PUBLIC.relative_to(ROOT)) + "/"
        if not staged or any(not path.startswith(prefix) for path in staged):
            raise PublicationError("Checkpoint contains missing or unrelated files")
        subprocess.run(["git", "commit", "-m", message + " [skip ci]"], cwd=ROOT, check=True)
        head = git("rev-parse", "HEAD")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH],
                                cwd=ROOT, capture_output=True, text=True)
        observed = remote_head()
        if pushed.returncode or observed != head:
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected, "local_commit": head,
                "observed_remote": observed, "push_returncode": pushed.returncode,
                "stdout": pushed.stdout, "stderr": pushed.stderr,
                "policy": "No automatic write or measurement retry; retain artifacts."})
            raise PublicationError("Push failed or did not verify at the expected commit")
        save(journal, {"expected_remote": head})
        print(json.dumps({"checkpoint": head, "branch": BRANCH, "message": message}), flush=True)
    except BaseException as error:
        if not (PUBLIC / "publication-failure.json").exists():
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected,
                "error": type(error).__name__ + ": " + str(error),
                "policy": "No automatic retry; inspect remote ref and artifact evidence."})
        raise


def verify_files(files, directory=ROOT):
    for path, expected in files.items():
        if sha(directory / path) != expected:
            raise ValueError("Frozen file changed: " + path)


def source_files(directory):
    return {str(path.relative_to(directory)): sha(path)
            for path in sorted((directory / "src").rglob("*")) if path.is_file()}


def runtime_sha(directory):
    """The unchanged published engine_source_hash boundary, without importing it."""
    package = directory / "src/memory_book"
    value = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        value.update(path.relative_to(package).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return value.hexdigest()


def verify_exact_source(directory, identity):
    if (directory.is_symlink() or (directory / "src").is_symlink()
            or any(path.is_symlink() for path in (directory / "src").rglob("*"))):
        raise ValueError("Runtime source contains a symlink")
    if source_files(directory) != identity["files_sha256"]:
        raise ValueError("Runtime source changed")
    if runtime_sha(directory) != identity["runtime_sha256"]:
        raise ValueError("Runtime aggregate SHA changed")


def inventory_difference(actual, expected):
    return {
        "added": {name: actual[name] for name in sorted(set(actual) - set(expected))},
        "missing": {name: expected[name] for name in sorted(set(expected) - set(actual))},
        "changed": {name: {"expected": expected[name], "actual": actual[name]}
                    for name in sorted(set(actual) & set(expected)) if actual[name] != expected[name]},
    }


def full_export_files(directory):
    return {path.relative_to(directory).as_posix(): sha(path) for path in sorted(directory.rglob("*"))
            if path.is_file() and not path.is_symlink()}


def correctness_inventory(directory, identity, before):
    """Retain differences in the unmeasured test copy; never relax a runtime guard."""
    actual = source_files(directory)
    difference = inventory_difference(actual, identity["files_sha256"])
    full_after = full_export_files(directory)
    full_difference = inventory_difference(full_after, before)
    errors, bytecode = [], {}
    if difference["missing"] or difference["changed"] or full_difference["missing"] or full_difference["changed"]:
        errors.append("A frozen source or fixture file changed or disappeared")
    if any(path.is_symlink() for path in directory.rglob("*")):
        errors.append("Correctness export contains a symlink")
    expected_caches = {
        Path(importlib.util.cache_from_source(str(directory / source))).relative_to(directory).as_posix(): source
        for source in identity["files_sha256"] if source.endswith(".py")}
    for name in full_difference["added"]:
        path = directory / name
        source_name = expected_caches.get(name)
        if source_name is None:
            errors.append("Unexpected added file: " + name)
            continue
        candidate = directory / source_name
        raw = path.read_bytes()
        if len(raw) < 16 or raw[:4] != importlib.util.MAGIC_NUMBER:
            errors.append("Unexpected added file: " + name)
        else:
            bytecode[name] = {"sha256": sha(path), "bytes": len(raw),
                "header_hex": raw[:16].hex(), "compiled_source": source_name,
                "compiled_source_sha256": sha(candidate)}
    if runtime_sha(directory) != identity["runtime_sha256"]:
        errors.append("Correctness runtime aggregate changed")
    return {"source_inventory": actual, "difference": difference,
            "full_export_inventory": full_after, "full_export_difference": full_difference,
            "generated_bytecode": bytecode, "errors": errors,
            "policy": "All files remain preserved. This export is never used for corpus preparation, profiling or timing."}


def archive_correctness_export(directory):
    """Keep the complete test export, including generated files and failures."""
    output = PUBLIC / "correctness-export.tar.gz"
    temporary = output.with_name(output.name + ".partial")
    with temporary.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                archive.add(directory, arcname="correctness-export")
        raw.flush()
        os.fsync(raw.fileno())
    temporary.replace(output)
    return {"path": output.relative_to(ROOT).as_posix(), "bytes": output.stat().st_size,
            "sha256": sha(output), "contents": "Complete exact-source correctness export and artificial fixture residue; no development corpus was downloaded yet."}



def scope_value():
    if sha(SCOPE) != SCOPE_SHA:
        raise ValueError("Prospective SQL attribution scope bytes changed")
    return read(SCOPE)


def runtime_identity():
    value = scope_value()["runtime"]
    if value["commit"] != SOURCE_COMMIT or value["runtime_sha256"] != RUNTIME_SHA:
        raise ValueError("Only the exact registered LM runtime is eligible")
    return {key: value[key] for key in ("commit", "runtime_sha256", "files_sha256")}


def archive_source(directory, identity):
    """Reviewed regular-file Git archive boundary with explicit destination."""
    directory.mkdir(parents=True, exist_ok=False)
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", identity["commit"]], cwd=ROOT, check=True)
    archive_path = directory.parent / (directory.name + ".tar")
    subprocess.run(["git", "archive", "--format=tar", "--output=" + str(archive_path),
                    identity["commit"], "src", "tests"], cwd=ROOT, check=True)
    with tarfile.open(archive_path) as stream:
        for member in stream.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] not in ("src", "tests") or ".." in parts:
                raise ValueError("Unexpected source archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Nonregular source archive member")
        stream.extractall(directory)
    archive_path.unlink()
    verify_exact_source(directory, identity)
    return directory


def frozen_filename_map(directory, identity, extra_paths=()):
    """All filesystem operations precede installation of any profile callback."""
    verify_exact_source(directory, identity)
    result = {str((directory / path).resolve()): {"path": path, "sha256": checksum}
              for path, checksum in identity["files_sha256"].items()}
    for path in extra_paths:
        result[str(path.resolve())] = {
            "path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
    return result


class SiteCatalog:
    """Only builtin frame/code metadata is read during observation."""
    def __init__(self, filenames, rules):
        self.filenames = dict(filenames)
        self.rules = tuple(rules)
        self.keys, self.sites, self.code_references = {}, [], {}

    def location(self, frame):
        if frame is None:
            return None
        code = frame.f_code
        self.code_references[id(code)] = code
        origin = self.filenames.get(code.co_filename)
        return {"path": origin["path"] if origin else code.co_filename,
            "source_sha256": origin["sha256"] if origin else None,
            "function": code.co_name, "qualname": getattr(code, "co_qualname", code.co_name),
            "first_line": code.co_firstlineno, "line": frame.f_lineno, "offset": frame.f_lasti}

    @staticmethod
    def line_matches(site, rule, prefix=""):
        line = site["line"]
        return (line in rule.get(prefix + "lines", ())
                or any(lo <= line <= hi for lo, hi in rule.get(prefix + "line_ranges", ())))

    def category(self, method, location, caller):
        unknown = "unclassified_primary" if method in PRIMARY_METHODS else "other_sqlite_builtin"
        if location["source_sha256"] is None:
            return unknown
        for rule in self.rules:
            if "path_prefixes" in rule:
                if any(location["path"].startswith(p) for p in rule["path_prefixes"]):
                    return rule["category"]
                continue
            if (location["path"] != "src/memory_book/store.py"
                    or location["qualname"] != rule["function"]
                    or method not in rule["methods"]
                    or not self.line_matches(location, rule)):
                continue
            if "caller_function" in rule:
                if (caller is None or caller["path"] != "src/memory_book/store.py"
                        or caller["source_sha256"] is None
                        or caller["qualname"] != rule["caller_function"]
                        or not self.line_matches(caller, rule, "caller_")):
                    continue
            return rule["category"]
        return unknown

    def identify(self, frame, method):
        caller = frame.f_back
        key = (id(frame.f_code), frame.f_lineno, frame.f_lasti, method,
               id(caller.f_code) if caller else None,
               caller.f_lineno if caller else None, caller.f_lasti if caller else None)
        index = self.keys.get(key)
        if index is not None:
            return index
        location, upper = self.location(frame), self.location(caller)
        index = len(self.sites)
        self.sites.append({"site_id": index, "method": method,
            "location": location, "caller": upper,
            "category": self.category(method, location, upper)})
        self.keys[key] = index
        return index


class SQLiteObserver:
    """Strict native C-event pairing; no SQLite mutation and no user values."""
    def __init__(self, catalog, clock=time.perf_counter_ns):
        self.catalog, self.clock = catalog, clock
        self.stack, self.spans = [], []
        self.events, self.target_events = Counter(), Counter()
        self.bookkeeping_ns, self.callback_failure = 0, None
        self.started, self.finished = False, False
        self.wall_start_ns, self.wall_end_ns = None, None

    @staticmethod
    def native_method(arg):
        if type(arg) is not BuiltinMethodType:
            return None
        receiver = arg.__self__
        if type(receiver) is NATIVE_CONNECTION:
            owner = "Connection"
        elif type(receiver) is NATIVE_CURSOR:
            owner = "Cursor"
        else:
            return None
        # Attributes belong to an exact builtin method, never a user receiver.
        return owner + "." + arg.__name__

    def __call__(self, frame, event, arg):
        entered = self.clock()
        try:
            self.events[event] += 1
            if event not in ("c_call", "c_return", "c_exception"):
                return
            method = self.native_method(arg)
            if method is None:
                return
            self.target_events[event] += 1
            if event == "c_call":
                site = self.catalog.identify(frame, method)
                row = {"sequence": len(self.spans),
                    "parent_sequence": self.stack[-1]["row"]["sequence"] if self.stack else None,
                    "site_id": site, "method": method, "status": "open",
                    "start_ns": None, "end_ns": None, "inclusive_ns": None,
                    "child_inclusive_ns": 0, "exclusive_ns": None}
                self.spans.append(row)
                item = {"frame": frame, "callable": arg, "row": row}
                row["start_ns"] = self.clock()
                self.stack.append(item)
            else:
                if not self.stack:
                    raise ObserverFailure("SQLite exit without entry")
                item = self.stack[-1]
                # Artificial real-CPython probes must establish this identity.
                if item["frame"] is not frame or item["callable"] is not arg:
                    raise ObserverFailure("SQLite exit is not the exact LIFO entry")
                row = item["row"]
                inclusive = entered - row["start_ns"]
                exclusive = inclusive - row["child_inclusive_ns"]
                if inclusive < 0 or exclusive < 0:
                    raise ObserverFailure("Impossible monotonic native span")
                row.update(end_ns=entered, inclusive_ns=inclusive, exclusive_ns=exclusive,
                    status="exception" if event == "c_exception" else "returned")
                self.stack.pop()
                if self.stack:
                    self.stack[-1]["row"]["child_inclusive_ns"] += inclusive
        except BaseException as error:
            self.callback_failure = {"type": type(error).__name__, "event": event,
                "open_sequences": [v["row"]["sequence"] for v in self.stack]}
            raise ObserverFailure("Observer callback failed; preserve partial spans") from None
        finally:
            spent = self.clock() - entered
            if spent < 0:
                self.callback_failure = {"type": "NonMonotonicCallbackClock", "event": event}
                raise ObserverFailure("Observer clock moved backward")
            self.bookkeeping_ns += spent

    def begin(self):
        if self.started or sys.getprofile() is not None:
            self.callback_failure = {"type": "ObserverAlreadyStarted" if self.started else "ExistingProfiler"}
            raise ObserverFailure("Observer cannot start twice or replace another profiler")
        self.started = True
        self.wall_start_ns = self.clock()
        sys.setprofile(self)

    def finish(self):
        if not self.started or self.finished:
            self.callback_failure = {"type": "ObserverLifecycleMisuse", "started": self.started, "finished": self.finished}
            raise ObserverFailure("Observer finish requires one active observation")
        current = sys.getprofile()
        sys.setprofile(None)
        self.wall_end_ns = self.clock()
        self.finished = True
        if current is not self and self.callback_failure is None:
            self.callback_failure = {"type": "ProfileCallbackReplaced"}
            raise ObserverFailure("Profile callback was unexpectedly replaced")
        if self.wall_end_ns < self.wall_start_ns:
            self.callback_failure = {"type": "NonMonotonicObservationClock"}
        if self.stack and self.callback_failure is None:
            self.callback_failure = {"type": "UnclosedNativeStack"}
        if self.stack or self.callback_failure:
            raise ObserverFailure("Observer has invalid or incomplete target events")

    def report(self):
        wall = (self.wall_end_ns - self.wall_start_ns
                if self.wall_start_ns is not None and self.wall_end_ns is not None else None)
        closed = [row for row in self.spans if row["status"] != "open"]
        exclusive = sum(row["exclusive_ns"] for row in closed)
        return {"valid": self.started and self.finished and wall is not None and wall >= 0
                and not self.stack and self.callback_failure is None,
            "started": self.started, "finished": self.finished,
            "events": dict(self.events), "target_events": dict(self.target_events),
            "non_target_events": sum(self.events.values()) - sum(self.target_events.values()),
            "callback_bookkeeping_ns": self.bookkeeping_ns, "callback_failure": self.callback_failure,
            "open_sequences": [v["row"]["sequence"] for v in self.stack],
            "recall_wall_ns_including_observer": wall, "observed_exclusive_builtin_ns": exclusive,
            "unattributed_wall_ns": wall - exclusive if wall is not None else None,
            "unattributed_meaning": "Python, implicit cursor iteration, unobserved SQLite and profiler overhead; not Python-only.",
            "spans": self.spans}


def native_book_identity(book):
    from memory_book import store
    if (type(book.db) is not NATIVE_CONNECTION or book._native_db is not book.db
            or book.db.row_factory is not NATIVE_ROW or book.db.text_factory is not str
            or sqlite3.Connection is not NATIVE_CONNECTION or sqlite3.Cursor is not NATIVE_CURSOR
            or sqlite3.Row is not NATIVE_ROW or sqlite3.connect is not NATIVE_CONNECT
            or store._NATIVE_CONNECTION is not NATIVE_CONNECTION
            or store._NATIVE_CURSOR is not NATIVE_CURSOR or store._NATIVE_ROW is not NATIVE_ROW):
        raise ObserverFailure("Ordinary native MemoryBook identity changed")
    return book.db


def observe_call(observer, callable_, *args, **kwargs):
    observer.begin()
    try:
        return callable_(*args, **kwargs)
    finally:
        observer.finish()


def summarize_observations(rows, sites):
    summaries = {}
    for query in rows:
        for span in query["observation"]["spans"]:
            site = sites[span["site_id"]]
            key = (site["site_id"], span["method"])
            entry = summaries.setdefault(key, {"site_id": key[0], "method": key[1],
                "category": site["category"], "calls": 0, "returned": 0, "exceptions": 0,
                "open": 0, "inclusive_ns": 0, "exclusive_ns": 0})
            entry["calls"] += 1
            entry[{"returned": "returned", "exception": "exceptions", "open": "open"}[span["status"]]] += 1
            if span["inclusive_ns"] is not None:
                entry["inclusive_ns"] += span["inclusive_ns"]
                entry["exclusive_ns"] += span["exclusive_ns"]
    return list(summaries.values())


def artificial_calibration(catalog):
    """One fixed invented batch; no best-of, correction or engine comparison."""
    deltas = []
    for _ in range(1000):
        before = time.perf_counter_ns()
        deltas.append(time.perf_counter_ns() - before)
    off, on = [], []
    with sqlite3.connect(":memory:") as connection:
        for _ in range(128):
            start = time.perf_counter_ns()
            connection.execute("SELECT 1").fetchone()
            off.append(time.perf_counter_ns() - start)
        for _ in range(128):
            observer = SQLiteObserver(catalog)
            observe_call(observer, lambda: connection.execute("SELECT 1").fetchone())
            on.append(observer.report())
    return {"status": "completed", "clock": vars(time.get_clock_info("perf_counter")),
        "clock_pair_deltas_ns": deltas, "off_then_on_fixed_order": True,
        "unobserved_native_operation_wall_ns": off, "observed_native_operations": on,
        "sites": catalog.sites, "corpus_calls": 0,
        "interpretation": "Invented callback/clock illustration only; never subtract from corpus spans or infer engine speed."}


def require_binding():
    # First action in run(): no Git claim, download, import or corpus call.
    if not SOURCE_BINDING.is_file():
        raise ValueError("Missing committed diagnostic binding; no claim or download is allowed")
    raise ValueError("Diagnostic evaluator is not frozen yet; no corpus execution")


def run():
    require_binding()


def self_test(source):
    if source is None:
        raise ValueError("Artificial integration requires an explicit exact LM export")
    source = source.resolve()
    verify_exact_source(source, runtime_identity())
    os.environ["SQL_ATTRIBUTION_TEST_SOURCE"] = str(source)
    sys.path[:0] = [str(source / "src"), str(ROOT)]
    import memory_book
    if Path(memory_book.__file__).resolve().parent != source / "src/memory_book":
        raise ValueError("Artificial fixture imported another source")
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_round5_lm_sql_attribution")
    expected = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"expected": expected, "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped), "passed": result.wasSuccessful(),
        "source_commit": SOURCE_COMMIT, "runtime_sha256": runtime_sha(source),
        "script_sha256": sha(Path(__file__)), "corpus_calls": 0}
    print(json.dumps(receipt), flush=True)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == expected and not result.skipped else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fixture-export", "self-test", "run"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.mode == "fixture-export":
        if args.source is None:
            parser.error("--source is required")
        archive_source(args.source, runtime_identity())
    elif args.mode == "self-test":
        self_test(args.source)
    else:
        run()
