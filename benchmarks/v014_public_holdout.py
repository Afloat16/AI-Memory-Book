"""Frozen transfer evaluation on independently captured real upstream sources.

This evaluates retrieval evidence, not generated answers or coding success.
The runtime implementers must not inspect/tune against this holdout before
their candidate is frozen. Any subsequent tuning consumes it as development.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/fixtures/v014_public_holdout"
PROTOCOL = "v014-public-source-holdout-v1"
sys.path.append(str(ROOT))
from scripts.validate_v011_revision_recovery import source_identity


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def source_chunks(text, cap=700):
    """Original, whole-line slices; never fabricate claims or rewrite code."""
    chunks, pending = [], ""
    for line in text.splitlines(keepends=True):
        if pending and len(pending) + len(line) > cap:
            chunks.append(pending)
            pending = ""
        pending += line
    if pending:
        chunks.append(pending)
    assert "".join(chunks) == text
    return chunks


def dataset():
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    sources, sessions = {}, []
    for entry in manifest["sources"]:
        raw = (FIXTURE / entry["file"]).read_bytes()
        if len(raw) != entry["bytes"] or sha(raw) != entry["sha256"]:
            raise ValueError("Frozen source bytes differ: " + entry["file"])
        if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != entry["git_blob_sha"]:
            raise ValueError("Upstream Git blob verification failed")
        if entry["kind"] != "source":
            continue
        key = (entry["project"].removeprefix("public-"), entry["phase"], Path(entry["upstream_path"]).name)
        sources[key] = entry
        messages = [{"role": "user", "content": chunk} for chunk in source_chunks(raw.decode("utf-8"))]
        sessions.append({"project": entry["project"], "session_id": entry["file"],
                         "task_id": Path(entry["upstream_path"]).name,
                         "task_title": "HTTP transport " + Path(entry["upstream_path"]).name,
                         "title": entry["repo"] + " " + entry["tag"] + " " + entry["upstream_path"],
                         "created_at": entry["created_at"], "messages": messages})
    cases = []

    def gold(project, phase, filename, quote):
        entry = sources[(project, phase, filename)]
        chunks = source_chunks((FIXTURE / entry["file"]).read_text(encoding="utf-8"))
        if not any(quote in text for text in chunks):
            raise ValueError("Gold must be contained in one unchanged source chunk: " + quote)
        return {"session_id": entry["file"], "quote": quote, "upstream_url": entry["source_url"]}

    def add(project, suffix, query, required, category="current"):
        cases.append({"id": project + ":" + suffix, "project": "public-" + project,
                      "query": query, "required": required, "category": category})

    current = {
        "httpx": [
            ("timeout", "What is the current DEFAULT_TIMEOUT_CONFIG timeout?", "_config.py", "DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)"),
            ("connections", "What is the current DEFAULT_LIMITS max_connections value?", "_config.py", "DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)"),
            ("keepalive", "当前 DEFAULT_LIMITS 的 max_keepalive_connections 是多少？", "_config.py", "DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)"),
            ("redirects", "What is the current DEFAULT_MAX_REDIRECTS value?", "_config.py", "DEFAULT_MAX_REDIRECTS = 20"),
            ("expiry", "What is the current Limits constructor keepalive_expiry default?", "_config.py", "keepalive_expiry: float | None = 5.0,"),
            ("http1", "Is http1 enabled by default in the current Client constructor?", "_client.py", "http1: bool = True,"),
            ("http2", "Is http2 enabled by default in the current Client constructor?", "_client.py", "http2: bool = False,"),
            ("environment", "What is the current Client trust_env default?", "_client.py", "trust_env: bool = True,"),
        ],
        "httpcore": [
            ("connections", "What is the current ConnectionPool max_connections default?", "connection_pool.py", "max_connections: int | None = 10,"),
            ("keepalive", "What is the current max_keepalive_connections constructor default?", "connection_pool.py", "max_keepalive_connections: int | None = None,"),
            ("expiry", "What is the current ConnectionPool keepalive_expiry default?", "connection_pool.py", "keepalive_expiry: float | None = None,"),
            ("http1", "Is http1 enabled in the current ConnectionPool constructor?", "connection_pool.py", "http1: bool = True,"),
            ("http2", "Is http2 enabled in the current ConnectionPool constructor?", "connection_pool.py", "http2: bool = False,"),
            ("retries", "What is the current ConnectionPool retries default?", "connection_pool.py", "retries: int = 0,"),
            ("read", "当前 HTTP11Connection 的 READ_NUM_BYTES 是多少？", "http11.py", "READ_NUM_BYTES = 64 * 1024"),
            ("event", "What is the current HTTP11Connection MAX_INCOMPLETE_EVENT_SIZE?", "http11.py", "MAX_INCOMPLETE_EVENT_SIZE = 100 * 1024"),
        ],
        "requests": [
            ("blocking", "What is the current DEFAULT_POOLBLOCK default?", "adapters.py", "DEFAULT_POOLBLOCK = False"),
            ("pool", "当前 DEFAULT_POOLSIZE 是多少？", "adapters.py", "DEFAULT_POOLSIZE = 10"),
            ("retries", "What is the current DEFAULT_RETRIES value?", "adapters.py", "DEFAULT_RETRIES = 0"),
            ("timeout", "What is the current DEFAULT_POOL_TIMEOUT value?", "adapters.py", "DEFAULT_POOL_TIMEOUT = None"),
            ("environment", "What value does the current Session assign self.trust_env?", "sessions.py", "self.trust_env = True"),
            ("verify", "What value does the current Session assign self.verify?", "sessions.py", "self.verify = True"),
            ("stream", "What value does the current Session assign self.stream?", "sessions.py", "self.stream = False"),
            ("cert", "What value does the current Session assign self.cert?", "sessions.py", "self.cert = None"),
        ],
        "urllib3": [
            ("methods", "Which current DEFAULT_ALLOWED_METHODS does Retry use?", "retry.py", '["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"]'),
            ("status", "What are the current RETRY_AFTER_STATUS_CODES?", "retry.py", "RETRY_AFTER_STATUS_CODES = frozenset([413, 429, 503])"),
            ("headers", "Which current DEFAULT_REMOVE_HEADERS_ON_REDIRECT headers are removed?", "retry.py", '["Cookie", "Authorization", "Proxy-Authorization"]'),
            ("backoff", "当前 DEFAULT_BACKOFF_MAX 是多少？", "retry.py", "DEFAULT_BACKOFF_MAX = 120"),
            ("total", "What is the current Retry total constructor default?", "retry.py", "total: bool | int | None = 10,"),
            ("factor", "What is the current Retry backoff_factor default?", "retry.py", "backoff_factor: float = 0,"),
            ("pool", "What is the current HTTPConnectionPool maxsize default?", "connectionpool.py", "maxsize: int = 1,"),
            ("blocking", "What is the current HTTPConnectionPool block default?", "connectionpool.py", "block: bool = False,"),
        ],
    }
    for project, entries in current.items():
        for suffix, query, filename, quote in entries:
            add(project, suffix, query, [gold(project, "current", filename, quote)])
    add("httpx", "multi", "What are the current DEFAULT_TIMEOUT_CONFIG and the Client http2 default?", [gold("httpx", "current", "_config.py", "DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)"), gold("httpx", "current", "_client.py", "http2: bool = False,")], "multi_source")
    add("httpcore", "multi", "What are the current ConnectionPool max_connections and HTTP11Connection READ_NUM_BYTES?", [gold("httpcore", "current", "connection_pool.py", "max_connections: int | None = 10,"), gold("httpcore", "current", "http11.py", "READ_NUM_BYTES = 64 * 1024")], "multi_source")
    add("requests", "multi", "What are the current DEFAULT_POOLSIZE and Session self.trust_env defaults?", [gold("requests", "current", "adapters.py", "DEFAULT_POOLSIZE = 10"), gold("requests", "current", "sessions.py", "self.trust_env = True")], "multi_source")
    add("urllib3", "multi", "What are the current DEFAULT_BACKOFF_MAX and HTTPConnectionPool maxsize defaults?", [gold("urllib3", "current", "retry.py", "DEFAULT_BACKOFF_MAX = 120"), gold("urllib3", "current", "connectionpool.py", "maxsize: int = 1,")], "multi_source")
    add("httpx", "history", "In the old 0.13.3 source, what did DEFAULT_POOL_LIMITS specify?", [gold("httpx", "old", "_config.py", "DEFAULT_POOL_LIMITS = PoolLimits(max_keepalive=10, max_connections=100)")], "historical")
    add("httpcore", "history", "In the old 0.9.1 source, what was SyncHTTP11Connection READ_NUM_BYTES?", [gold("httpcore", "old", "http11.py", "READ_NUM_BYTES = 4096")], "historical")
    add("requests", "history", "In the old v2.22.0 source, what was DEFAULT_POOLSIZE?", [gold("requests", "old", "adapters.py", "DEFAULT_POOLSIZE = 10")], "historical")
    add("urllib3", "history", "In the old 1.25.11 source, what was DEFAULT_REDIRECT_HEADERS_BLACKLIST?", [gold("urllib3", "old", "retry.py", 'DEFAULT_REDIRECT_HEADERS_BLACKLIST = frozenset(["Authorization"])')], "historical")
    missing = {"httpx": ("DEFAULT_POOLSIZE", "RETRY_AFTER_STATUS_CODES"), "httpcore": ("DEFAULT_TIMEOUT_CONFIG", "DEFAULT_REMOVE_HEADERS_ON_REDIRECT"), "requests": ("READ_NUM_BYTES", "DEFAULT_BACKOFF_MAX"), "urllib3": ("DEFAULT_TIMEOUT_CONFIG", "DEFAULT_POOLSIZE")}
    for project, identifiers in missing.items():
        bodies = "\n".join(m["content"] for s in sessions if s["project"] == "public-" + project for m in s["messages"])
        for i, identifier in enumerate(identifiers):
            if identifier in bodies:
                raise ValueError("Missing-case identifier unexpectedly exists")
            add(project, f"missing-{i}", f"What is the current {identifier} value in this project?", [], "missing")
    return sessions, cases


def verify_response(case, response, pages, originals, budget):
    if (response["query"] != case["query"] or response["strategy"] != "book"
            or response["cache_hit"] is not False or response["budget_chars"] != budget
            or response["temporal"]["requested"] != "auto" or len(response["results"]) > 5
            or len(response["context"]) > budget or response["context_chars"] != len(response["context"])):
        raise ValueError("Request, budget, cache or framing changed")
    ids = [h["id"] for h in response["results"]]
    if len(set(ids)) != len(ids) or set(ids) != set(pages):
        raise ValueError("Missing/duplicate original-page proof")
    blocks, verified = [], []
    for hit in response["results"]:
        page = pages[hit["id"]]
        if len(page["source_refs"]) != 1 or not hit["source_refs"]:
            raise ValueError("Unexpected source mapping")
        ref = page["source_refs"][0]
        key = (ref["project"], ref["session_id"], ref["turn_index"])
        source = originals.get(key)
        original = source["text"] if source else None
        if (key[0] != case["project"] or original is None or page["content"] != original
                or page["id"] != hit["id"] or page["next_offset"] is not None or page["offset"] != 0
                or page["total_chars"] != len(original) or hit["page_chars"] != len(original)
                or hit["breadcrumb"][0]["id"] != case["project"] or page["breadcrumb"][0]["id"] != case["project"]
                or [ref[k] for k in ("start", "end", "turn_start", "turn_end")] != [0, len(original), 0, len(original)]):
            raise ValueError("Original text, project, page or coordinates changed")
        expected_date = datetime.fromisoformat(source["created_at"].replace("Z", "+00:00"))
        if (any(datetime.fromisoformat(stamp.replace("Z", "+00:00")) != expected_date
                for stamp in (hit["created_at"], page["created_at"], ref["created_at"]))
                or ref["message_indices"] != [key[2]]):
            raise ValueError("Original timestamp or message identity changed")
        fragments, spans = [], []
        for part in hit["source_refs"]:
            lo, hi = part["turn_start"], part["turn_end"]
            if ((part["project"], part["session_id"], part["turn_index"]) != key
                    or type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(original)
                    or part["start"] != lo or part["end"] != hi or part["message_indices"] != [key[2]]
                    or datetime.fromisoformat(part["created_at"].replace("Z", "+00:00")) != expected_date):
                raise ValueError("Excerpt has unsupported source coordinates")
            fragments.append(original[lo:hi])
            spans.append([lo, hi])
            verified.append((key[1], original[lo:hi]))
        if spans != hit["excerpt_spans"] or any(fragment not in hit["text"] for fragment in fragments):
            raise ValueError("Excerpt lacks its original slice")
        remainder = hit["text"]
        for fragment in fragments:
            remainder = remainder.replace(fragment, "", 1)
        if remainder.strip(" \t\r\n…"):
            raise ValueError("Unsupported excerpt text")
        blocks.append(f'[{hit["id"]}] {key[0]} / {key[1]} | {hit["created_at"]}\n' + hit["text"])
    if "\n\n".join(blocks) != response["context"]:
        raise ValueError("Context contains unaudited text")
    matches = [any(session == gold["session_id"] and gold["quote"] in text for session, text in verified) for gold in case["required"]]
    coverage = response.get("evidence_coverage", {})
    return {"required_spans": len(matches), "matched_spans": sum(matches),
            "complete": bool(matches) and all(matches), "missing": case["category"] == "missing",
            "returned_context": bool(response["context"]), "coverage_status": coverage.get("status", "absent"),
            "missing_identifiers": coverage.get("missing_identifiers", []), "source_integrity": True}


def frozen_identity(commit):
    names = ["benchmarks/v014_public_holdout.py", "tests/test_v014_public_holdout.py", "scripts/capture_v014_public_holdout.py"]
    names += [p.relative_to(ROOT).as_posix() for p in FIXTURE.iterdir() if p.is_file()]
    hashes = {}
    for name in sorted(names):
        raw = (ROOT / name).read_bytes()
        if raw != subprocess.check_output(["git", "-C", str(ROOT), "show", commit + ":" + name]):
            raise ValueError("Holdout differs from its frozen protocol commit")
        hashes[name] = sha(raw)
    return {"commit": commit, "files": hashes, "sha256": sha(json.dumps(hashes, sort_keys=True).encode())}


def worker(args):
    from memory_book import MemoryBook
    import memory_book
    from memory_book._text_backend import BACKEND_NAME
    if Path(memory_book.__file__).resolve().parent != args.source.resolve() / "src/memory_book" or BACKEND_NAME != args.backend:
        raise ValueError("Actual imported source/backend differs")
    identity = source_identity(args.source, args.commit)
    protocol = frozen_identity(args.protocol_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    sessions, cases = dataset()
    originals = {(s["project"], s["session_id"], i): {"text": "USER: " + m["content"], "created_at": s["created_at"]}
                 for s in sessions for i, m in enumerate(s["messages"])}
    proof = {"protocol": PROTOCOL, "protocol_identity": protocol, "source": identity,
             "backend": BACKEND_NAME, "python": sys.version, "platform": platform.platform(), "status": "started"}
    dump(args.output / "report.json", proof)
    rows = []
    try:
        with MemoryBook(args.output / "memory.db", segmentation="turn", min_page_chars=0) as book:
            started = time.perf_counter()
            for clone in range(9):
                for session in sessions:
                    payload = dict(session)
                    if clone:
                        payload["project"] = f'clone-{clone}-{session["project"]}'
                    book.ingest(payload)
            proof["ingest_seconds"] = time.perf_counter() - started
            proof["stats"] = book.stats()
            proof["target_page_counts"] = {s["project"]: book.db.execute("SELECT count(*) FROM pages WHERE project_id=?", (s["project"],)).fetchone()[0] for s in sessions}
            with gzip.open(args.output / "responses.jsonl.gz", "xt", encoding="utf-8") as stream:
                for budget in (1200, 2400):
                    for case in cases:
                        response = book.recall(case["query"], project=case["project"], budget_chars=budget, limit=5, temporal="auto", use_cache=False)
                        pages = {hit["id"]: book.read(hit["id"], project=case["project"], limit=12000) for hit in response["results"]}
                        score = verify_response(case, response, pages, originals, budget)
                        row = {"case_id": case["id"], "category": case["category"], "budget_chars": budget,
                               "response": response, "original_pages": pages, "score": score}
                        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                        stream.flush()
                        rows.append(row)
        proof["status"] = "completed"
        proof["summary"] = []
        for budget in (1200, 2400):
            group = [r for r in rows if r["budget_chars"] == budget]
            scores = [r["score"] for r in group]
            proof["summary"].append({"budget_chars": budget, "queries": len(scores), "answerable": sum(not s["missing"] for s in scores),
                                     "complete": sum(s["complete"] for s in scores), "required_spans": sum(s["required_spans"] for s in scores),
                                     "matched_spans": sum(s["matched_spans"] for s in scores), "source_errors": 0,
                                     "missing_diagnosed": sum(s["missing"] and s["coverage_status"] == "insufficient_evidence" for s in scores),
                                     "answerable_flagged_insufficient": sum(not s["missing"] and s["coverage_status"] == "insufficient_evidence" for s in scores),
                                     "coverage_status_counts": dict(Counter(s["coverage_status"] for s in scores))})
        proof["source_after"] = source_identity(args.source, args.commit)
        proof["raw_sha256"] = sha((args.output / "responses.jsonl.gz").read_bytes())
    except BaseException as exc:
        proof.update(status="failed", error=repr(exc), completed_responses=len(rows))
        raise
    finally:
        dump(args.output / "report.json", proof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("describe", "run", "worker"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--protocol-commit")
    parser.add_argument("--backend", choices=("native", "python"), default="native")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "describe":
        sessions, cases = dataset()
        print(json.dumps({"protocol": PROTOCOL, "target_projects": len({s["project"] for s in sessions}), "sources": len(sessions),
                          "target_turns": sum(len(s["messages"]) for s in sessions), "clone_copies": 8,
                          "expected_pages": 9 * sum(len(s["messages"]) for s in sessions), "queries": len(cases),
                          "categories": dict(Counter(c["category"] for c in cases)), "budgets": [1200, 2400], "observations_per_backend_arm": 2 * len(cases)}, indent=2))
    elif not all((args.source, args.commit, args.protocol_commit, args.output)):
        parser.error("run/worker requires source, commit, protocol-commit and output")
    elif args.command == "worker":
        worker(args)
    else:
        env = os.environ.copy()
        env.update(PYTHONPATH=str(args.source.resolve() / "src"), MEMORY_BOOK_TEXT_BACKEND=args.backend, PYTHONHASHSEED="0")
        command = [sys.executable, str(Path(__file__).resolve()), "worker", "--source", str(args.source.resolve()), "--commit", args.commit,
                   "--protocol-commit", args.protocol_commit, "--backend", args.backend, "--output", str(args.output.resolve())]
        subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
