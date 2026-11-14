"""C3 old-data development diagnosis only; never formal performance evidence."""
import cProfile
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pstats
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from memory_book import MemoryBook
from memory_book.token_budget import TokenCounter
from benchmarks.run import engine_source_hash
from scripts.benchmark_default_recall import dataset, digest

EXPECTED = "7a927601b5ce710059d5a2640b3642c58a2bd4985d9ccdc48f69159938ee3623"
PROFILE = ROOT / ".artifacts/round5-c4-profile-c3-token1024.json"
STATE = ROOT / ".artifacts/round5-c4-profile-c3-token1024"
DATABASE = ROOT / ".artifacts/round5-development-dbs/public1015.db"


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(value):
    temporary = PROFILE.with_suffix(".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(PROFILE)


class Cursor:
    def __init__(self, cursor, totals):
        self.cursor, self.totals = cursor, totals

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def measure(self, operation, *args):
        begin = time.perf_counter_ns()
        try:
            return operation(*args)
        finally:
            self.totals["fetch_ns"] += time.perf_counter_ns() - begin
            self.totals["fetch_calls"] += 1

    def fetchone(self):
        return self.measure(self.cursor.fetchone)

    def fetchall(self):
        return self.measure(self.cursor.fetchall)

    def __iter__(self):
        return self

    def __next__(self):
        return self.measure(next, self.cursor)


class Connection:
    def __init__(self, connection):
        self.connection, self.groups = connection, defaultdict(lambda: dict(execute_ns=0, fetch_ns=0, execute_calls=0, fetch_calls=0))

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, parameters=()):
        group = " ".join(re.sub(r"\?(?:,\?)+", "?LIST", statement).split())
        totals = self.groups[group]
        begin = time.perf_counter_ns()
        try:
            cursor = self.connection.execute(statement, parameters)
        finally:
            totals["execute_ns"] += time.perf_counter_ns() - begin
            totals["execute_calls"] += 1
        return Cursor(cursor, totals)


assert not PROFILE.exists()
STATE.mkdir(exist_ok=False)
assert engine_source_hash(ROOT / "src/memory_book") == EXPECTED
wal = Path(str(DATABASE) + "-wal")
assert not wal.exists() or wal.stat().st_size == 0
data = dataset("public1015", ROOT / ".artifacts/locomo10.json")
TokenCounter("cl100k_base").count("Initialize outside profiling.")
result = dict(status="running", boundary=__doc__, started_at=datetime.now(timezone.utc).isoformat(),
    runtime_sha256=EXPECTED, dataset_sha256=data.fingerprint, queries=len(data.queries),
    config=dict(budget_chars=8000, budget_tokens=1024, tokenizer="cl100k_base", use_cache=False),
    script_sha256=file_sha(Path(__file__)), source_db_sha256=file_sha(DATABASE), passes=[])
save(result)
try:
    for mode in ("cprofile", "sql_attribution"):
        db = STATE / (mode + ".db")
        shutil.copyfile(DATABASE, db)
        row = dict(mode=mode, samples=[])
        result["passes"].append(row)
        with MemoryBook(db, cache_size=0) as book:
            profile = cProfile.Profile()
            proxy = Connection(book.db) if mode == "sql_attribution" else None
            if proxy:
                book.db = proxy
            for case in data.queries:
                if mode == "cprofile":
                    profile.enable()
                try:
                    response = book.recall(case.query, project=case.project, **result["config"])
                finally:
                    if mode == "cprofile":
                        profile.disable()
                response.pop("latency_ms")
                row["samples"].append(dict(query_id=case.id, payload_sha256=digest(response)))
            if mode == "cprofile":
                profile.dump_stats(str(STATE / "calls.prof"))
                stats = pstats.Stats(profile)
                row["total_instrumented_seconds"] = stats.total_tt
                row["functions"] = [dict(path=name[0], line=name[1], name=name[2], primitive_calls=values[0], calls=values[1], self_seconds=values[2], cumulative_seconds=values[3])
                    for name, values in sorted(stats.stats.items(), key=lambda item: -item[1][2])]
            else:
                row["sql_groups"] = [dict(statement=statement, **totals) for statement, totals in sorted(proxy.groups.items(), key=lambda item: -(item[1]["execute_ns"] + item[1]["fetch_ns"]))]
                book.db = proxy.connection
        save(result)
        print(json.dumps({"completed_pass": mode, "calls": len(row["samples"])}), flush=True)
    assert result["passes"][0]["samples"] == result["passes"][1]["samples"]
    assert file_sha(DATABASE) == result["source_db_sha256"]
    assert engine_source_hash(ROOT / "src/memory_book") == EXPECTED
    result["status"] = "completed"
except BaseException as exc:
    result.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    raise
finally:
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(result)
