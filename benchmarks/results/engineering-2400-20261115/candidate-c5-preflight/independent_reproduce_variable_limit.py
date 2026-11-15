"""Independent three-route SQLite regression; no benchmark or scorer imports."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3

from memory_book import MemoryBook, store
from memory_book.text import query_terms


def record(identity, body):
    return {"project": "service", "session_id": identity, "task_id": "config",
            "title": "Status", "task_title": "Configuration",
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": "Status"},
                         {"role": "assistant", "content": body}]}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--variable-limit", type=int, default=192,
                    help="Use zero to leave the native SQLite limit unchanged.")
parser.add_argument("--limit", type=int, default=5)
args = parser.parse_args()
query = "current deployment worker lease.ttl"
source_path = Path(store.__file__)
source_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
with MemoryBook(":memory:", max_page_chars=10000, cache_size=0) as book:
    for index in range(96):
        book.ingest(record(f"exact-{index}", "deployment worker lease ttl. " * 2 +
                           "Equipment manifest retained. " * 45))
        book.ingest(record(f"stem-{index}", "deployments workers leases ttls. " * 10))
        book.ingest(record(f"value-{index}", f"Deployment worker lease.ttl={index + 10}. " +
                           "Equipment manifest retained. " * 150))
    tokens = " OR ".join('"' + token + '"' for token in query_terms(query))
    expression = f"({tokens}) AND body : ({tokens})"
    routes = []
    for table in ("pages_fts", "pages_stem_fts"):
        identities = [row[0] for row in book.db.execute(
            "SELECT s.external_id FROM " + table + " JOIN pages p ON p.rid=" + table +
            ".rowid JOIN sessions s ON s.id=p.session_pk WHERE " + table + " MATCH ? "
            "ORDER BY bm25(" + table + ",2.0,2.0,1.0,0.25),p.id LIMIT 96", [expression])]
        routes.append(identities)
    if args.variable_limit:
        book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, args.variable_limit)
    result, error = None, None
    try:
        result = book.recall(query, project="service", limit=args.limit, use_cache=False)
        result.pop("latency_ms", None)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    print(json.dumps({
        "scope": "One compatibility recall; no engineering scoring or timing.",
        "source_sha_before": source_before,
        "source_sha_after": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "variable_limit": book.db.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER),
        "recall_limit": args.limit,
        "ordinary_route_sizes": [len(route) for route in routes],
        "ordinary_union_size": len(set().union(*map(set, routes))),
        "error": error, "result": result, "transaction_after": book.db.in_transaction,
    }, ensure_ascii=False, indent=2))
