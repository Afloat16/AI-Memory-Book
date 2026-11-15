"""Tiny current-query regression; imports no workload, scoring, or gold table.

Run with PYTHONPATH selecting one runtime. This makes one recall call and
reports returned source sessions; it is not a performance measurement.
"""
from pathlib import Path
import argparse
import hashlib
import json

from memory_book import MemoryBook
from memory_book import store
from memory_book.text import query_terms


def source(identity, body, day):
    return {
        "project": "cache-services", "session_id": identity,
        "task_id": "service-settings", "task_title": "Redis and Memcache service settings",
        "title": "Service configuration", "created_at": day + "T09:00:00Z",
        "messages": [{"role": "user", "content": "Service configuration"},
                     {"role": "assistant", "content": body}],
    }


source_path = Path(store.__file__)
source_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--query", default="current Redis service retry_limit")
query = parser.parse_args().query
with MemoryBook(":memory:", max_page_chars=10000, cache_size=0) as book:
    book.ingest(source("redis-value", "Redis service retry_limit=3. " +
                       "Redis service retry_limit. " * 20, "2026-01-01"))
    book.ingest(source("memcache-value", "Redis service audit finished. Memcache retry_limit=9. " +
                       "Equipment manifest reviewed by operators during the handover. " * 60,
                       "2026-11-01"))
    for index in range(128):
        book.ingest(source(f"inspection-{index}", f"Inspection {index}. " +
                           "Redis service retry_limit inspected. " * 10, "2026-06-01"))
    tokens = " OR ".join('"' + token + '"' for token in query_terms(query))
    expression = f"({tokens}) AND body : ({tokens})"
    routes = [row[0] for row in book.db.execute(
        "SELECT s.external_id FROM pages_fts JOIN pages p ON p.rid=pages_fts.rowid "
        "JOIN sessions s ON s.id=p.session_pk WHERE pages_fts MATCH ? AND p.project_id=? "
        "ORDER BY bm25(pages_fts,2.0,2.0,1.0,0.25),p.id LIMIT 96",
        [expression, "cache-services"])]
    result = book.recall(query, project="cache-services", limit=1, budget_chars=4000, use_cache=False)
    print(json.dumps({
        "source_sha_before": source_before,
        "source_sha_after": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "recall_version": store.RECALL_VERSION,
        "original_route_top3": routes[:3],
        "wrong_entity_in_original96": "memcache-value" in routes,
        "result_sessions": [hit["source_refs"][0]["session_id"] for hit in result["results"]],
        "context": result["context"], "candidate_count": result["candidate_count"],
    }, ensure_ascii=False, indent=2))
