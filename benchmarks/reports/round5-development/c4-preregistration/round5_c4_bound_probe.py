"""Observe safe metadata-bound survivor counts; C3 retrieval remains unchanged."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from memory_book import MemoryBook
from memory_book.store import CURRENT_QUERY, HISTORICAL_QUERY
from memory_book.text import query_terms
from benchmarks.run import engine_source_hash
from scripts.benchmark_default_recall import dataset, digest

OUTPUT = ROOT / ".artifacts/round5-c4-bound-probe.json"
STATE = ROOT / ".artifacts/round5-c4-bound-probe"
SOURCE = "7a927601b5ce710059d5a2640b3642c58a2bd4985d9ccdc48f69159938ee3623"


class Cursor:
    def __init__(self, cursor, callback):
        self.cursor, self.callback = cursor, callback

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def fetchall(self):
        rows = self.cursor.fetchall()
        for row in rows:
            self.callback(row)
        return rows

    def __iter__(self):
        return self

    def __next__(self):
        row = next(self.cursor)
        self.callback(row)
        return row


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, parameters=()):
        normalized = " ".join(statement.split())
        if normalized == "BEGIN":
            self.routes, self.metadata, self.selected = [], [], []
        cursor = self.connection.execute(statement, parameters)
        if normalized.startswith("SELECT p.rid,p.id,bm25("):
            route = []
            self.routes.append(route)
            return Cursor(cursor, lambda row: route.append(dict(row)))
        if normalized.startswith("SELECT p.id,p.project_id,p.chapter_id,"):
            return Cursor(cursor, lambda row: self.metadata.append(dict(row)))
        if normalized.startswith("SELECT p.id,p.title,p.section_id,p.session_pk,"):
            self.selected = list(parameters)
        return cursor


assert not OUTPUT.exists()
STATE.mkdir(exist_ok=False)
assert engine_source_hash(ROOT / "src/memory_book") == SOURCE
prior = json.loads((ROOT / ".artifacts/round5-c4-profile-c3-token1024.json").read_bytes())
expected = {row["query_id"]: row["payload_sha256"] for row in prior["passes"][0]["samples"]}
database = ROOT / ".artifacts/round5-development-dbs/public1015.db"
assert not Path(str(database) + "-wal").stat().st_size
shutil.copyfile(database, STATE / "book.db")
data = dataset("public1015", ROOT / ".artifacts/locomo10.json")
report = dict(status="running", boundary=__doc__, started_at=datetime.now(timezone.utc).isoformat(),
    runtime_sha256=SOURCE, dataset_sha256=data.fingerprint, samples=[])
try:
    with MemoryBook(STATE / "book.db", cache_size=0) as book:
        proxy = Connection(book.db)
        book.db = proxy
        for case in data.queries:
            response = book.recall(case.query, project=case.project, budget_chars=8000, budget_tokens=1024, use_cache=False)
            response.pop("latency_ms")
            assert digest(response) == expected[case.id]
            exact, stem = proxy.routes
            fused = [row["id"] for row in exact] != [row["id"] for row in stem]
            erank = {row["id"]: i + 1 for i, row in enumerate(exact)}
            srank = {row["id"]: i + 1 for i, row in enumerate(stem)}
            scores = [{row["id"]: max(0.0, -row["rank"]) for row in route} for route in (exact, stem)]
            scales = [max(values.values(), default=1.0) or 1.0 for values in scores]
            base = {row["id"]: -row["rank"] for row in exact}
            if fused:
                base = {identity: 2 * scores[0].get(identity, 0.0) / scales[0] + scores[1].get(identity, 0.0) / scales[1] for identity in set(scores[0]) | set(scores[1])}
            assert all(math.isfinite(value) and value >= 0 for value in base.values())
            qset = set(query_terms(case.query))
            current = CURRENT_QUERY.search(case.query) and not HISTORICAL_QUERY.search(case.query)
            k = min(len(base), 20 if current or len(qset) > 1 else 5)
            floor = sorted(base.values(), reverse=True)[k - 1] if k else 0
            survivors = {identity for identity, value in base.items() if value * 1.15 >= floor}
            actual = {row["id"]: base[row["id"]] * (1 + 0.15 * len(qset & book._directory_tokens(row["chapter_title"] + " " + row["session_title"])) / len(qset)) for row in proxy.metadata}
            order = sorted(actual, key=(lambda identity: (-actual[identity], erank.get(identity, 97), srank.get(identity, 97), identity)) if fused else (lambda identity: (-actual[identity], identity)))
            assert not set(order[:k]) - survivors and not set(proxy.selected) - survivors
            assert response["candidate_count"] == len(base)
            report["samples"].append(dict(query_id=case.id, candidates=len(base), k=k, survivors=len(survivors),
                directory_pairs=len({(row["project_id"], row["chapter_id"], row["session_id"]) for row in proxy.metadata}),
                fused=fused, actual_top_k_retained=True, selected_pages_retained=True, payload_sha256=expected[case.id]))
        book.db = proxy.connection
    report["summary"] = dict(calls=len(report["samples"]), candidates=sum(row["candidates"] for row in report["samples"]),
        survivors=sum(row["survivors"] for row in report["samples"]), directory_pairs=sum(row["directory_pairs"] for row in report["samples"]),
        survivor_histogram=dict(sorted(Counter(row["survivors"] for row in report["samples"]).items())), fused_queries=sum(row["fused"] for row in report["samples"]))
    report["summary"]["candidate_work_reduction_percent"] = 100 * (1 - report["summary"]["survivors"] / report["summary"]["candidates"])
    assert engine_source_hash(ROOT / "src/memory_book") == SOURCE
    report["status"] = "completed"
except BaseException as exc:
    report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    raise
finally:
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report["summary"], sort_keys=True))
