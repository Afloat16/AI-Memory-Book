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
from types import BuiltinMethodType, MethodDescriptorType
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
NATIVE_DESCRIPTORS = {(owner, name): value for owner in (NATIVE_CONNECTION, NATIVE_CURSOR)
    for name, value in vars(owner).items() if type(value) is MethodDescriptorType}
PAIRING_ADDENDUM = ROOT / "benchmarks/experiments/round5-lm-sql-attribution-pairing-addendum.json"
PAIRING_ADDENDUM_SHA = "cf55b88d45ee7a0dca53abefa6dc651d7eceb36f6ae0e709919655c566c36d21"


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
    if sha(PAIRING_ADDENDUM) != PAIRING_ADDENDUM_SHA:
        raise ValueError("Reviewed native identity correction changed")
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
                    "child_inclusive_ns": 0, "exclusive_ns": None, "wrapper_is": None}
                self.spans.append(row)
                receiver = arg.__self__
                owner = type(receiver)
                descriptor = NATIVE_DESCRIPTORS.get((owner, arg.__name__))
                if descriptor is None:
                    raise ObserverFailure("Unsupported native builtin descriptor")
                item = {"frame": frame, "callable": arg, "receiver": receiver,
                    "owner": owner, "descriptor": descriptor, "name": arg.__name__, "row": row}
                row["start_ns"] = self.clock()
                self.stack.append(item)
            else:
                if not self.stack:
                    raise ObserverFailure("SQLite exit without entry")
                item = self.stack[-1]
                # The reviewed artificial witness shows fresh wrappers at inline exits.
                # Semantic native identity, not wrapper allocation, must be exact.
                receiver = arg.__self__
                owner = type(receiver)
                descriptor = NATIVE_DESCRIPTORS.get((owner, arg.__name__))
                checks = {"frame_is": item["frame"] is frame,
                    "receiver_is": item["receiver"] is receiver, "native_type_is": item["owner"] is owner,
                    "descriptor_is": descriptor is not None and item["descriptor"] is descriptor,
                    "method_same": item["name"] == arg.__name__}
                if not all(checks.values()):
                    self.callback_failure = {"type": "NativePairMismatch", "event": event,
                        "checks": checks, "wrapper_is": item["callable"] is arg,
                        "open_sequences": [v["row"]["sequence"] for v in self.stack]}
                    raise ObserverFailure("SQLite exit is not the exact LIFO native identity")
                item["row"]["wrapper_is"] = item["callable"] is arg
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
            if self.callback_failure is None:
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



def pack_bytes(path, raw):
    """Exclusive, lossless storage; never overwrite an earlier cell or partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if path.exists() or temporary.exists():
        raise ValueError("Preserve the existing observation storage")
    compressed = gzip.compress(raw, mtime=0)
    with temporary.open("xb") as stream:
        stream.write(compressed)
        stream.flush()
        os.fsync(stream.fileno())
    if gzip.decompress(temporary.read_bytes()) != raw:
        raise ValueError("Lossless observation storage failed")
    temporary.replace(path)
    return {"path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name,
        "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(compressed), "sha256": hashlib.sha256(compressed).hexdigest()}


def pack_value(path, value):
    return pack_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n").encode("utf-8"))


def append_ledger(stream, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    stream.write(raw)
    stream.flush()
    os.fsync(stream.fileno())


def cell_paths(cohort, configuration):
    if cohort not in COHORTS or configuration not in CONFIG_NAMES:
        raise ValueError("Unregistered diagnostic cell")
    name = cohort + "-" + configuration
    return {
        "name": name, "intent": PUBLIC / "cells" / (name + ".intent.json"),
        "output": PUBLIC / "cells" / (name + ".json.gz"),
        "ledger": STATE / "ledgers" / (name + ".jsonl"),
        "saved_ledger": PUBLIC / "cells" / (name + ".ledger.jsonl.gz"),
        "storage": PUBLIC / "cells" / (name + ".storage.json"),
    }


def claim_cell(cohort, configuration, binding_sha, expected_calls):
    paths = cell_paths(cohort, configuration)
    if any(path.exists() for key, path in paths.items() if key != "name"):
        raise ValueError("A diagnostic cell was already started; replay is forbidden")
    save(paths["intent"], {"attempt": ATTEMPT, "cell": paths["name"], "status": "started",
        "created_at": stamp(), "binding_sha256": binding_sha, "expected_calls": expected_calls,
        "corpus": "previously registered old cohort only", "replay_permitted": False})
    publish("bench: claim SQL attribution cell " + paths["name"])
    # publish() checks exact remote HEAD after its one non-force push.
    paths["ledger"].parent.mkdir(parents=True, exist_ok=True)
    return paths


def save_cell(paths, cell, sites):
    """Called by the worker after observation, including incomplete/failed cells."""
    cell["sites"] = list(sites)
    cell["callsite_summary"] = summarize_observations(cell["rows"], sites)
    storage = {"cell": pack_value(paths["output"], cell)}
    if paths["ledger"].exists():
        storage["ledger"] = pack_bytes(paths["saved_ledger"], paths["ledger"].read_bytes())
    save(paths["storage"], storage)
    publish("bench: preserve SQL attribution cell " + paths["name"])
    return storage


def audit_observation(value, sites):
    if (value.get("valid") is not True or value.get("started") is not True
            or value.get("finished") is not True or value.get("callback_failure") is not None
            or value.get("open_sequences") != []):
        raise ValueError("Invalid or incomplete native observation")
    rows = value["spans"]
    if [row["sequence"] for row in rows] != list(range(len(rows))):
        raise ValueError("Native call sequence changed")
    native_events = Counter()
    for row in rows:
        if row["site_id"] not in range(len(sites)) or row["method"] != sites[row["site_id"]]["method"]:
            raise ValueError("Native source site identity changed")
        if row["status"] not in ("returned", "exception") or type(row.get("wrapper_is")) is not bool:
            raise ValueError("Unclosed native span or missing wrapper observation")
        for field in ("start_ns", "end_ns", "inclusive_ns", "child_inclusive_ns", "exclusive_ns"):
            if type(row[field]) is not int or row[field] < 0:
                raise ValueError("Invalid native span clock")
        if (row["end_ns"] - row["start_ns"] != row["inclusive_ns"]
                or row["inclusive_ns"] - row["child_inclusive_ns"] != row["exclusive_ns"]):
            raise ValueError("Native span arithmetic does not reconcile")
        parent = row["parent_sequence"]
        if parent is not None:
            if type(parent) is not int or not 0 <= parent < row["sequence"]:
                raise ValueError("Invalid native nesting")
            ancestor = rows[parent]
            if not ancestor["start_ns"] <= row["start_ns"] <= row["end_ns"] <= ancestor["end_ns"]:
                raise ValueError("Native child lies outside parent")
        native_events["c_call"] += 1
        native_events["c_exception" if row["status"] == "exception" else "c_return"] += 1
    for row in rows:
        if row["child_inclusive_ns"] != sum(child["inclusive_ns"] for child in rows
                if child["parent_sequence"] == row["sequence"]):
            raise ValueError("Native exclusive sums double-count or omit children")
    if dict(native_events) != value["target_events"]:
        raise ValueError("Native event counts do not reconcile")
    if (any(type(n) is not int or n < 0 for n in value["events"].values())
            or any(value["events"].get(kind, 0) < n for kind, n in native_events.items())
            or value["non_target_events"] != sum(value["events"].values()) - sum(native_events.values())):
        raise ValueError("Callback event counters do not reconcile")
    exclusive = sum(row["exclusive_ns"] for row in rows)
    wall = value["recall_wall_ns_including_observer"]
    if (type(wall) is not int or wall < exclusive or value["observed_exclusive_builtin_ns"] != exclusive
            or value["unattributed_wall_ns"] != wall - exclusive
            or type(value["callback_bookkeeping_ns"]) is not int or value["callback_bookkeeping_ns"] < 0):
        raise ValueError("Observed and unattributed wall accounting changed")
    return True


def audit_cell(candidate, baseline, cohort, configuration, expected):
    for cell in (candidate, baseline):
        ids = [row["query_id"] for row in cell["rows"]]
        if (cell.get("status") != "completed" or cell.get("cohort") != cohort
                or cell.get("configuration") != configuration
                or cell.get("dataset_sha256") != expected["dataset_sha256"]
                or cell.get("queries") != expected["queries"] or len(ids) != expected["queries"]
                or len(set(ids)) != len(ids)
                or digest(ids) != expected["profile_query_order_sha256"]):
            raise ValueError("Profile data, count or complete order mismatch")
    mismatches = []
    for left, right in zip(baseline["rows"], candidate["rows"]):
        if left["query_id"] != right["query_id"]:
            raise ValueError("Reference and diagnostic rows were paired differently")
        for row in (left, right):
            if re.fullmatch(r"[0-9a-f]{64}", row["non_timing_payload_sha256"]) is None:
                raise ValueError("Invalid full non-timing payload digest")
        audit_observation(right["observation"], candidate["sites"])
        if left["non_timing_payload_sha256"] != right["non_timing_payload_sha256"]:
            mismatches.append({"cohort": cohort, "configuration": configuration,
                "query_id": right["query_id"], "baseline": left["non_timing_payload_sha256"],
                "observed": right["non_timing_payload_sha256"]})
    return {"cohort": cohort, "configuration": configuration, "queries": expected["queries"],
        "query_order_sha256": expected["profile_query_order_sha256"], "mismatches": mismatches,
        "all_full_non_timing_payloads_equal": not mismatches}


def profile_audit(value, old, references, producer_sha):
    """Retain all original profile predicates; the new producer identity is explicit."""
    if (value.get("status") != "completed" or value.get("expected_calls") != 4732
            or value.get("attempted_calls") != 4732 or value.get("completed_calls") != 4732
            or value.get("runtime_source_sha256") != RUNTIME_SHA
            or value.get("script_sha256") != producer_sha or value.get("scope_sha256") != SCOPE_SHA
            or value.get("helpers_sha256") != old["helpers_sha256"]
            or value.get("helper_dependency_sha256") != old["helper_dependency_sha256"]):
        raise ValueError("Incomplete or differently sourced diagnostic profile")
    expected_cells = [(cohort, config) for cohort in COHORTS for config in CONFIG_NAMES]
    if ([(c["cohort"], c["configuration"]) for c in value["cells"]] != expected_cells
            or len(references) != len(expected_cells)):
        raise ValueError("Complete diagnostic/reference cell inventory changed")
    records = [audit_cell(candidate, baseline, cohort, config, old["cohorts"][cohort])
        for candidate, baseline, (cohort, config) in zip(value["cells"], references, expected_cells)]
    mismatches = [row for cell in records for row in cell["mismatches"]]
    return {"attempt": ATTEMPT, "calls": 4732, "cells": records, "mismatches": mismatches,
        "all_full_non_timing_payloads_equal_to_v032_c2": not mismatches,
        "retrieval_calls_executed_by_audit": 0, "speed_claim": False, "fresh_rows_decoded": 0}


def prepare_references(old):
    """Read nine small pinned Git objects, without checking out historical reports."""
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", REFERENCE_COMMIT], cwd=ROOT, check=True)
    directory = STATE / "profile-references"
    directory.mkdir(exist_ok=False)
    manifest_path = old["profile"]["baseline_reference"]
    raw = subprocess.check_output(["git", "show", REFERENCE_COMMIT + ":" + manifest_path], cwd=ROOT)
    if hashlib.sha256(raw).hexdigest() != old["profile"]["baseline_manifest_sha256"]:
        raise ValueError("Saved baseline profile manifest changed")
    (directory / "manifest.json").write_bytes(raw)
    manifest = json.loads(raw)
    if (manifest["runtime_source_sha256"] != old["baseline"]["runtime_sha256"]
            or manifest["script_sha256"] != old["helpers_sha256"]["scripts/round4_development_profile.py"]
            or manifest["status"] != "completed" or manifest["completed_calls"] != 4732):
        raise ValueError("Saved baseline manifest has different source/counts")
    for cell in old["profile"]["baseline_cells"]:
        compressed = subprocess.check_output(["git", "show", REFERENCE_COMMIT + ":" + cell["path"]], cwd=ROOT)
        if len(compressed) != cell["bytes"] or hashlib.sha256(compressed).hexdigest() != cell["sha256"]:
            raise ValueError("Saved baseline compressed cell changed")
        raw = gzip.decompress(compressed)
        if hashlib.sha256(raw).hexdigest() != cell["uncompressed_sha256"]:
            raise ValueError("Saved baseline raw cell changed")
        (directory / Path(cell["path"]).name).write_bytes(compressed)


EVIDENCE = (
    {"kind": "design_review", "commit": "fa2018b98a297352fee527bcc120ed4fa27e3022",
     "path": "benchmarks/reports/round5-lm-sql-attribution-scope-independent-review.json",
     "sha256": "9f28ee3dc2fb0ab16142e1ded9152e96de47c9a362ae5bd333c3c6cfe9c86241"},
    {"kind": "source_review", "commit": "41e26421eccc281ea9639c882be1a9e2e787ec4a",
     "path": "benchmarks/reports/round5-ranked-normalization-lm-independent-source-review.json",
     "sha256": "530f905dff7626b5194035cbf63f6076d49c5caf1117c09e342f2090e84bca59"},
    {"kind": "lm_outcome", "commit": "128952ffd4f53a30f225feb98853a7f7f6ea7121",
     "path": "benchmarks/reports/round5-candidate-lm-development-1/independent-raw-audit.json",
     "sha256": "eb7c9fd7b032409e7ff4d39b3ce8b03838f1901abfc3b4806fd21a8f398fdb42"},
    {"kind": "pairing_witness", "commit": "056422edec1bd2c178afae33df57eca8848f3fd1",
     "path": "benchmarks/reports/round5-lm-sql-attribution-artificial/native-wrapper-witness.json",
     "sha256": "5a50c520bf8695388fd82e922d9ae19b5cb86c05e01f0f6f1d33fe7825bed6dc"},
)


def validate_reference(reference):
    if (re.fullmatch(r"[0-9a-f]{40}", reference.get("commit", "")) is None
            or re.fullmatch(r"[0-9a-f]{64}", reference.get("sha256", "")) is None
            or not reference.get("path", "").startswith("benchmarks/reports/")
            or ".." in Path(reference["path"]).parts or Path(reference["path"]).is_absolute()):
        raise ValueError("Invalid immutable evidence reference")


def git_reference(reference):
    validate_reference(reference)
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", reference["commit"]], cwd=ROOT, check=True)
    raw = subprocess.check_output(["git", "show", reference["commit"] + ":" + reference["path"]], cwd=ROOT)
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("Immutable evidence bytes changed")
    return raw


def validate_binding_value(value):
    scope = scope_value()
    identity = runtime_identity()
    if (value.get("status") != "frozen-after-artificial-proof-before-sql-attribution-corpus"
            or value.get("attempt") != ATTEMPT or value.get("runtime") != identity
            or value.get("scope_sha256") != SCOPE_SHA
            or value.get("pairing_addendum_sha256") != PAIRING_ADDENDUM_SHA
            or value.get("classification_sha256") != digest(scope["observer"]["source_mapping"])
            or value.get("planned_recall_calls") != 4732 or value.get("comparison_engine_calls") != 0
            or value.get("fresh_rows_decoded") != 0 or value.get("speed_claim") is not False):
        raise ValueError("Diagnostic binding changed its exact source or observation boundary")
    expected_files = {SCRIPT_PATH, TEST_PATH, WORKFLOW_PATH}
    if set(value.get("artifact_files_sha256", {})) != expected_files:
        raise ValueError("Missing exact observer/test/workflow inventory")
    verify_files(value["artifact_files_sha256"])
    for key, registered in (("helpers_sha256", "helpers_sha256"),
                            ("helper_dependency_sha256", "helper_dependencies_sha256")):
        if value.get(key) != scope["inherited_protocol"][registered]:
            raise ValueError("Original helper closure changed")
        verify_files(value[key])
    if sha(OLD) != OLD_SHA:
        raise ValueError("Original schedule binding changed")
    if value.get("prior_evidence") != list(EVIDENCE):
        raise ValueError("Prior source, design, failure/witness or LM result evidence changed")
    validate_reference(value["artificial_evidence"])
    if value.get("source_ci") != scope["prior_evidence"]["source_ci"]:
        raise ValueError("Original complete exact-LM CI changed")
    return value


def require_binding():
    # First action in run/preflight/worker. Do not move a claim or download above it.
    if not SOURCE_BINDING.is_file():
        raise ValueError("Missing committed diagnostic binding; no claim or download is allowed")
    value = validate_binding_value(read(SOURCE_BINDING))
    launch = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", launch) is None:
        raise ValueError("Missing exact hosted launch commit")
    for path in (Path(__file__).resolve(), ROOT / TEST_PATH, ROOT / WORKFLOW_PATH,
                 SCOPE, PAIRING_ADDENDUM, SOURCE_BINDING, OLD):
        raw = subprocess.check_output(["git", "show", launch + ":" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        if raw != path.read_bytes():
            raise ValueError("Diagnostic input differs from its exact launch commit")
    return value


def validate_evidence(value, kind):
    if kind == "design_review":
        valid = (value.get("status") == "accepted-prospective-diagnostic-design-for-implementation-only"
            and value.get("scope_sha256") == SCOPE_SHA and value.get("source_commit") == SOURCE_COMMIT
            and value.get("runtime_sha256") == RUNTIME_SHA and value.get("artificial_implementation_authorized") is True
            and value.get("retrieval_calls_executed_by_review") == 0 and value.get("fresh_rows_decoded") == 0)
    elif kind == "source_review":
        valid = (value.get("status") == "accepted-independent-source-review-of-combined-lm-before-corpus"
            and value.get("reviewed_source_commit") == SOURCE_COMMIT and value.get("runtime_sha256") == RUNTIME_SHA
            and value.get("performance_accepted") is False and value.get("corpus_calls_executed_by_review") == 0)
    elif kind == "lm_outcome":
        valid = (value.get("status") == "verified-development-result-below-target"
            and value.get("source_commit") == SOURCE_COMMIT and value.get("runtime_sha256") == RUNTIME_SHA
            and value.get("result_commit") == "ec296d79fc1a2ec9c4e3cadb48bddfd34cdb0213"
            and value.get("calls") == 4096 and value.get("complete_payload_pairs") == 2048
            and value.get("payload_mismatches") == 0 and len(value.get("cells", [])) == 8
            and value.get("all_summary_quantiles_reproduced") is True
            and value.get("pooled_p95_geomean_improvement_percent") == 4.791840281283378
            and value.get("formal_acceptance") is False
            and value.get("retrieval_calls_executed_by_audit") == 0 and value.get("fresh_rows_decoded") == 0)
    elif kind == "pairing_witness":
        rows = value.get("observed", {}).get("native_wrapper_probe", [])
        valid = (value.get("status") == "native-wrapper-identity-witness-from-artificial-input-only"
            and len(rows) == 9 and sum(row["wrapper_is"] is False for row in rows) == 8
            and all(all(row.get(key) is True for key in
                ("frame_is", "receiver_is", "native_type_is", "descriptor_is", "method_same")) for row in rows)
            and value["observed"]["unclosed_entries"] == 0
            and value.get("diagnostic_corpus_calls") == 0 and value.get("fresh_rows_decoded") == 0)
    else:
        raise ValueError("Unknown immutable evidence kind")
    if not valid:
        raise ValueError("Immutable evidence no longer proves its registered boundary")


def validate_artificial_evidence(value, bound):
    receipt = value.get("receipt", {})
    job = value.get("job", {})
    run = value.get("workflow_run", {})
    if (value.get("status") != "passed-artificial-observer-and-protocol-tests"
            or value.get("artifact_files_sha256") != bound["artifact_files_sha256"]
            or run.get("conclusion") != "success" or run.get("status") != "completed"
            or run.get("run_attempt") != 1
            or job.get("name") != "protocol-fixtures" or job.get("conclusion") != "success"
            or job.get("status") != "completed"
            or receipt.get("source_commit") != SOURCE_COMMIT or receipt.get("runtime_sha256") != RUNTIME_SHA
            or receipt.get("script_sha256") != bound["artifact_files_sha256"][SCRIPT_PATH]
            or receipt.get("test_file_sha256") != bound["artifact_files_sha256"][TEST_PATH]
            or receipt.get("workflow_file_sha256") != bound["artifact_files_sha256"][WORKFLOW_PATH]
            or type(receipt.get("expected")) is not int or receipt["expected"] <= 0
            or receipt.get("tests") != receipt["expected"] or receipt.get("passed") is not True
            or any(receipt.get(key) != 0 for key in ("errors", "failures", "skipped", "corpus_calls"))):
        raise ValueError("Complete artificial observer/protocol evidence is required")
    return receipt


def preflight_evidence(bound):
    records = []
    for reference in EVIDENCE:
        raw = git_reference(reference)
        validate_evidence(json.loads(raw), reference["kind"])
        records.append(dict(reference))
    raw = git_reference(bound["artificial_evidence"])
    artificial = json.loads(raw)
    validate_artificial_evidence(artificial, bound)
    code_commit = artificial["workflow_run"]["head_sha"]
    if re.fullmatch(r"[0-9a-f]{40}", code_commit or "") is None:
        raise ValueError("Artificial CI lacks an exact source commit")
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", code_commit], cwd=ROOT, check=True)
    for path, expected in bound["artifact_files_sha256"].items():
        content = subprocess.check_output(["git", "show", code_commit + ":" + path], cwd=ROOT)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Artificial CI covered different observer/test/workflow bytes")
    log = artificial["raw_log"]
    log_ref = {"commit": bound["artificial_evidence"]["commit"], **log}
    git_reference(log_ref)
    return {"status": "verified-before-claim", "created_at": stamp(),
        "source_commit": SOURCE_COMMIT, "runtime_sha256": RUNTIME_SHA,
        "evidence": records, "artificial_evidence": bound["artificial_evidence"],
        "binding_sha256": sha(SOURCE_BINDING), "retrieval_calls": 0, "fresh_rows_decoded": 0}


def runtime_environment():
    return {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "machine": platform.machine(),
        "python_executable_sha256": sha(Path(sys.executable).resolve()),
        "packages": {name: importlib.metadata.version(name) for name in ("mcp", "pydantic", "tiktoken", "regex")},
        "tokenizer_cache": {path.name: sha(path) for path in sorted(
            Path(os.environ["TIKTOKEN_CACHE_DIR"]).glob("*")) if path.is_file()},
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "clock": vars(time.get_clock_info("perf_counter")),
        "interpretation": "One hosted VM; instrumented mechanism spans only, no speed or memory comparison."}


def check_environment():
    expected = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0", "regex": "2026.11.9"}
    if (sys.version_info[:2] != (3, 12) or platform.system() != "Linux"
            or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"
            or os.environ.get("PYTHONHASHSEED") != "0"
            or {name: importlib.metadata.version(name) for name in expected} != expected):
        raise ValueError("Registered hosted environment changed")


def load_references(old):
    directory = STATE / "profile-references"
    return [json.loads(gzip.decompress((directory / Path(cell["path"]).name).read_bytes()))
            for cell in old["profile"]["baseline_cells"]]


def verify_reference_storage(old):
    directory = STATE / "profile-references"
    if sha(directory / "manifest.json") != old["profile"]["baseline_manifest_sha256"]:
        raise ValueError("Saved C2 manifest changed")
    for cell in old["profile"]["baseline_cells"]:
        path = directory / Path(cell["path"]).name
        raw = path.read_bytes()
        if (len(raw) != cell["bytes"] or hashlib.sha256(raw).hexdigest() != cell["sha256"]
                or hashlib.sha256(gzip.decompress(raw)).hexdigest() != cell["uncompressed_sha256"]):
            raise ValueError("Saved C2 gzip or complete raw bytes changed")


def guards(binding):
    if (sha(SCOPE) != SCOPE_SHA or sha(OLD) != OLD_SHA
            or sha(PAIRING_ADDENDUM) != PAIRING_ADDENDUM_SHA
            or sha(SOURCE_BINDING) != binding["source_binding_sha256"]):
        raise ValueError("Frozen diagnostic input changed")
    verify_files(binding["artifact_files_sha256"])
    verify_files(binding["helpers_sha256"])
    verify_files(binding["helper_dependency_sha256"])
    verify_exact_source(STATE / "sources/measurement", binding["runtime"])
    for name, expected in binding["preparation_files_sha256"].items():
        if sha(PUBLIC / name) != expected:
            raise ValueError("Bound preparation evidence changed")
    if sha(STATE / "locomo10.json") != binding["locomo_sha256"]:
        raise ValueError("Pinned old input changed")
    verify_reference_storage(read(OLD))
    check_environment()
    if runtime_environment() != binding["environment"]:
        raise ValueError("Bound hosted environment changed")


def run_correctness_export(directory):
    identity = runtime_identity()
    before = full_export_files(directory)
    save(PUBLIC / "correctness-export.intent.json", {"status": "started", "created_at": stamp(),
        "source_commit": SOURCE_COMMIT, "runtime_sha256": RUNTIME_SHA,
        "full_export_inventory": before, "test_file_sha256": sha(ROOT / TEST_PATH),
        "corpus_calls": 0, "policy": "Invented observer/protocol fixtures only; retain this export and never use it for the old corpus."})
    publish("bench: bind separate SQL observer correctness export")
    log_path = PUBLIC / "correctness.log.partial"
    returncode, error_type = None, None
    try:
        with log_path.open("xb") as log:
            returncode = subprocess.run([sys.executable, str(ROOT / SCRIPT_PATH), "self-test",
                "--source", str(directory), "--receipt", str(PUBLIC / "correctness.json")],
                cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                stdout=log, stderr=subprocess.STDOUT, timeout=180).returncode
    except BaseException as error:
        error_type = type(error).__name__
    inventory = correctness_inventory(directory, identity, before)
    inventory["archive"] = archive_correctness_export(directory)
    inventory["returncode"], inventory["execution_error_type"] = returncode, error_type
    save(PUBLIC / "correctness-export-audit.json", inventory)
    publish("bench: preserve SQL observer artificial correctness and complete export")
    if returncode != 0 or error_type or inventory["errors"]:
        raise ValueError("Artificial correctness or retained source inventory failed")


def prepare(bound):
    identity = runtime_identity()
    correctness = archive_source(STATE / "sources/correctness", identity)
    run_correctness_export(correctness)
    measurement = archive_source(STATE / "sources/measurement", identity)
    save(PUBLIC / "measurement-export.json", {"commit": SOURCE_COMMIT,
        "runtime_sha256": runtime_sha(measurement), "files_sha256": source_files(measurement),
        "correctness_export_reused": False})
    publish("bench: bind clean LM source before attribution preparation")
    old = read(OLD)
    prepare_references(old)
    verify_reference_storage(old)
    raw_spec = read(ROOT / "benchmarks/locomo_split.json")
    with urllib.request.urlopen(raw_spec["url"], timeout=60) as response:
        raw = response.read(raw_spec["bytes"] + 1)
    if len(raw) != raw_spec["bytes"] or hashlib.sha256(raw).hexdigest() != raw_spec["sha256"]:
        raise ValueError("Pinned old LoCoMo input changed")
    (STATE / "locomo10.json").write_bytes(raw)
    env = dict(os.environ, PYTHONPATH=str(measurement / "src") + os.pathsep + str(ROOT),
               PYTHONDONTWRITEBYTECODE="1")
    warmup = ("from memory_book.token_budget import TokenCounter; "
              "TokenCounter('cl100k_base').count('Prepare the reference tokenizer before profiling.')")
    subprocess.run([sys.executable, "-c", warmup], cwd=ROOT, env=env, check=True, timeout=120)
    verify_exact_source(measurement, identity)
    check_environment()
    names = ("preflight.json", "correctness-export.intent.json", "correctness.json",
             "correctness-export-audit.json", "correctness-export.tar.gz", "measurement-export.json")
    binding = {"attempt": ATTEMPT, "created_at": stamp(), "source_binding_sha256": sha(SOURCE_BINDING),
        "scope_sha256": SCOPE_SHA, "pairing_addendum_sha256": PAIRING_ADDENDUM_SHA,
        "workflow_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "runtime": identity, "artifact_files_sha256": bound["artifact_files_sha256"],
        "helpers_sha256": bound["helpers_sha256"], "helper_dependency_sha256": bound["helper_dependency_sha256"],
        "preparation_files_sha256": {name: sha(PUBLIC / name) for name in names},
        "locomo_sha256": raw_spec["sha256"], "environment": runtime_environment(),
        "profile_baseline_references": old["profile"], "calls_expected": 4732,
        "comparison_engine_calls": 0, "fresh_rows_decoded": 0, "speed_claim": False,
        "database_policy": "One fresh LM database per cohort inside the persistent worker; no historical database bytes or completed LM claim is reused."}
    save(PUBLIC / "binding.json", binding)
    publish("bench: freeze SQL attribution source environment and old references")
    return binding


def run():
    require_binding()


def self_test(source, receipt_path=None):
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
    module = sys.modules["tests.test_round5_lm_sql_attribution"]
    if Path(module.__file__).resolve() != ROOT / TEST_PATH:
        raise ValueError("Artificial suite imported another fixture module")
    expected = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"expected": expected, "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped), "passed": result.wasSuccessful(),
        "source_commit": SOURCE_COMMIT, "runtime_sha256": runtime_sha(source),
        "script_sha256": sha(Path(__file__)), "test_file_sha256": sha(ROOT / TEST_PATH),
        "workflow_file_sha256": sha(ROOT / WORKFLOW_PATH), "scope_sha256": SCOPE_SHA,
        "pairing_addendum_sha256": PAIRING_ADDENDUM_SHA, "corpus_calls": 0}
    if receipt_path is not None:
        save(receipt_path, receipt)
    print(json.dumps(receipt), flush=True)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == expected and not result.skipped else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fixture-export", "self-test", "run"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "fixture-export":
        if args.source is None:
            parser.error("--source is required")
        archive_source(args.source, runtime_identity())
    elif args.mode == "self-test":
        self_test(args.source, args.receipt)
    else:
        run()
