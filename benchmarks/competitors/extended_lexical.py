"""Pinned upstream lexical components, with transport and source checks only.

All tokenization and ranking run in the installed upstream packages. This
module does not implement a search engine, rewrite queries, or inspect gold.
The worker runs in a separate, explicitly selected Python environment.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import traceback
from urllib.parse import quote

from benchmarks.competitors.memory_systems import (
    PythonComponent, ROOT, sanitized_environment, sha_file, validate_documents,
)
from benchmarks.competitors.memory_systems_worker import block_python_network, serializable

LOCK_PATH = Path(__file__).with_name("extended-lexical-lock.json")
BACKENDS = ("haystack_bm25", "bm25s", "memvid_lex")


def package_identity():
    """Verify pinned versions and hashed installed files, including native code.

    The lock also retains the hashes of the installed distribution archives.
    Generated entrypoints/bytecode with no wheel digest are not fabricated into
    the archive identity. The pinned Memvid archive contains one incorrect
    RECORD entry; that exact entry is checked against the original wheel member
    instead, retaining its original declared digest/size. No general mismatch
    waiver is allowed. File manifests reduce to a canonical SHA-256.
    """
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    result = {}
    for name, spec in sorted(lock["packages"].items()):
        dist = importlib.metadata.distribution(name)
        if dist.version != spec["version"]:
            raise ValueError(f"Expected {name}=={spec['version']}; found {dist.version}")
        hashes, native, archive_verified = {}, {}, {}
        for entry in dist.files or ():
            if entry.hash is None or entry.hash.mode != "sha256":
                continue
            path = dist.locate_file(entry)
            actual = sha_file(path)
            encoded = base64.urlsafe_b64encode(bytes.fromhex(actual)).decode().rstrip("=")
            known = spec.get("original_archive_member_exceptions", {}).get(str(entry))
            if known:
                if ("sha256=" + entry.hash.value != known["record_hash"]
                        or entry.size != known["record_size"] or actual != known["sha256"]
                        or path.stat().st_size != known["bytes"]):
                    raise ValueError(f"Installed file differs from pinned original archive member: {name}/{entry}")
                archive_verified[str(entry)] = known
            elif encoded != entry.hash.value:
                raise ValueError(f"Installed upstream file differs from wheel: {name}/{entry}")
            hashes[str(entry)] = actual
            if path.suffix in (".so", ".pyd", ".dll", ".dylib"):
                native[str(entry)] = actual
        if not hashes:
            raise ValueError(f"No verifiable installed files for {name}")
        if set(spec.get("original_archive_member_exceptions", {})) - hashes.keys():
            raise ValueError(f"Missing pinned original archive member for {name}")
        record = dist.read_text("RECORD")
        if record is None:
            raise ValueError(f"Missing wheel RECORD for {name}")
        result[name] = {
            "version": dist.version, "verified_files": len(hashes),
            "files_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "record_sha256": hashlib.sha256(record.encode()).hexdigest(),
            "native_files": native,
            "original_archive_members_verified": archive_verified,
        }
    return result


def result_identity(response):
    """Repeated output equality covers ranking, native scores, and original text.

    Complete native responses (including variable timing diagnostics) are also
    retained. Timing fields never enter the quality/stability decision.
    """
    value = {key: response[key] for key in ("hit_ids", "records", "scores")}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


class ExtendedLexical(PythonComponent):
    """Reuse the frozen request/source-validation protocol, with a new worker."""

    def __init__(self, backend, documents, state, *, python=sys.executable, timeout=180):
        if backend not in BACKENDS:
            raise ValueError("Unknown extended lexical component")
        docs = list(documents)
        self.documents = validate_documents(docs)
        self.state = Path(state).resolve()
        self.state.mkdir(parents=True, exist_ok=False)
        self.timeout = timeout
        self.closed = False
        self.counter = 0
        self.responses = queue.Queue()
        self.stderr_tail = []
        self.stderr_file = (self.state / "stderr.log").open("w", encoding="utf-8")
        env = sanitized_environment(self.state, self.state / "cache")
        temporary = self.state / "tmp"
        temporary.mkdir()
        env.update({"HAYSTACK_TELEMETRY_ENABLED": "false", "DD_TRACE_ENABLED": "false",
                    "MEMVID_TELEMETRY": "0", "TMPDIR": str(temporary)})
        started = time.perf_counter_ns()
        self.process = subprocess.Popen(
            [str(python), "-m", "benchmarks.competitors.extended_lexical", "--backend", backend,
             "--state", str(self.state)], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.threads = [threading.Thread(target=self._stdout, daemon=True),
                        threading.Thread(target=self._stderr, daemon=True)]
        for thread in self.threads:
            thread.start()
        try:
            self.metadata = self._request({"op": "init", "documents": [
                {key: doc[key] for key in ("id", "project", "title", "text", "created_at")}
                for doc in docs]})
            self.metadata["startup_and_index_roundtrip_ms"] = (time.perf_counter_ns() - started) / 1e6
        except BaseException:
            self.close()
            raise


class HaystackBM25:
    def __init__(self, documents, state):
        from haystack import Document
        from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
        from haystack.document_stores.in_memory import InMemoryDocumentStore

        validate_documents(documents)
        self.store = InMemoryDocumentStore()
        self.store.write_documents([
            Document(id=doc["id"], content=doc["text"], meta={
                "project": doc["project"], "title": doc["title"], "created_at": doc["created_at"]})
            for doc in documents
        ])
        self.retriever = InMemoryBM25Retriever(document_store=self.store, top_k=5)
        self.metadata = {
            "classification": "retrieval framework component; no pipeline or generator",
            "mode": "InMemoryBM25Retriever with unmodified InMemoryDocumentStore defaults",
            "search_api": "InMemoryBM25Retriever.run(query, filters, top_k)",
            "scope": "native exact meta.project equality filter before top-k",
            "indexed_text": "full original page body; title stored as metadata",
            "store_configuration": self.store.to_dict(),
            "retriever_configuration": self.retriever.to_dict(),
            "persistent": False, "model_calls": 0,
        }

    def search(self, query, project, limit):
        native = self.retriever.run(query=query, filters={
            "field": "meta.project", "operator": "==", "value": project}, top_k=limit)
        rows = native["documents"]
        records = [{"id": row.id, "project": row.meta["project"], "text": row.content} for row in rows]
        return {"hit_ids": [row.id for row in rows], "records": records,
                "scores": [row.score for row in rows],
                "native_payload": {"documents": [row.to_dict() for row in rows]}}

    def close(self):
        self.store.shutdown()


class BM25Sparse:
    def __init__(self, documents, state):
        import bm25s

        validate_documents(documents)
        self.corpora, self.indexes = {}, {}
        for project in sorted({doc["project"] for doc in documents}):
            corpus = [dict(doc) for doc in documents if doc["project"] == project]
            tokens = bm25s.tokenize([doc["text"] for doc in corpus], show_progress=False)
            index = bm25s.BM25()
            index.index(tokens, show_progress=False)
            self.corpora[project], self.indexes[project] = corpus, index
        self.metadata = {
            "classification": "lexical retrieval library; not an AI memory product",
            "mode": "BM25S native default Lucene BM25 and native default tokenizer",
            "search_api": "bm25s.tokenize + BM25.retrieve",
            "scope": "one native index per project, selected before retrieval; adapter-level partition",
            "indexed_text": "full original page body; title retained only in corpus payload",
            "tokenization": {"lower": True, "stopwords": "english", "stemmer": None,
                             "token_pattern": r"(?u)\b\w\w+\b"},
            "ranking": {"method": "lucene", "k1": 1.5, "b": 0.75, "delta": 0.5,
                        "backend": "numpy", "csc_backend": "numpy", "dtype": "float32"},
            "zero_score_policy": "retain upstream top-k including zero scores; no adapter threshold",
            "persistent": False, "model_calls": 0,
        }

    def search(self, query, project, limit):
        import bm25s

        if project not in self.indexes:
            return {"hit_ids": [], "records": [], "scores": [],
                    "native_payload": {"results": [], "scores": [], "absent_namespace": True}}
        corpus = self.corpora[project]
        tokens = bm25s.tokenize([query], show_progress=False)
        rows, scores = self.indexes[project].retrieve(
            tokens, corpus=corpus, k=min(limit, len(corpus)), show_progress=False)
        records = [{"id": doc["id"], "project": doc["project"], "text": doc["text"]}
                   for doc in rows[0]]
        return {"hit_ids": [row["id"] for row in records], "records": records,
                "scores": scores[0].tolist(),
                "native_payload": {"results": rows.tolist(), "scores": scores.tolist()}}

    def close(self):
        pass


def memvid_record(hit, frame, documents, project):
    """Validate a native Memvid hit before common-source materialization.

    Its lexical result normalizes whitespace and appends metadata. This is not
    represented as a byte-exact native source reader: the unchanged common
    packer receives the original supplied page only after exact equality of the
    complete normalized body plus known native framing, metadata and identity.
    """
    metadata = frame.get("extra_metadata", {})
    identity = json.loads(metadata["page_id"])
    native_project = json.loads(metadata["project"])
    expected_uri = f"memory-book://{quote(project, safe='')}/{quote(identity, safe='')}"
    if (identity not in documents or native_project != project
            or documents[identity]["project"] != project
            or hit.get("uri") != expected_uri or frame.get("uri") != expected_uri
            or hit.get("frame_id") != frame.get("id")
            or set(metadata) != {"page_id", "project"}):
        raise ValueError("Memvid native frame changed identity or crossed project scope")
    doc = documents[identity]
    if (hit.get("title") != doc["title"] or frame.get("title") != doc["title"]
            or hit.get("tags") != [] or frame.get("tags") != []
            or hit.get("labels") != ["text"] or frame.get("labels") != ["text"]
            or frame.get("timestamp") != int(datetime.fromisoformat(doc["created_at"]).timestamp())):
        raise ValueError("Memvid frame metadata differs from the supplied-page protocol")
    text = doc["text"]
    expected = (text + f"\ntitle: {doc['title']}\nuri: {expected_uri}\nlabels: text"
                + "\npage_id: " + json.dumps(identity, ensure_ascii=False)
                + "\nproject: " + json.dumps(project, ensure_ascii=False))
    native_text = " ".join(hit.get("text", "").split())
    if native_text != " ".join(expected.split()):
        raise ValueError("Memvid hit omits or changes the supplied original body")
    return {"id": identity, "project": native_project, "text": text}


class MemvidLexical:
    def __init__(self, documents, state):
        from memvid_sdk import create

        self.documents = validate_documents(documents)
        self.memory = create(str(state / "memory.mv2"), enable_lex=True, enable_vec=False)
        frames = []
        for doc in documents:
            uri = f"memory-book://{quote(doc['project'], safe='')}/{quote(doc['id'], safe='')}"
            frame = self.memory.put(
                title=doc["title"], text=doc["text"], search_text=doc["text"], uri=uri,
                metadata={"page_id": doc["id"], "project": doc["project"]},
                timestamp=int(datetime.fromisoformat(doc["created_at"]).timestamp()), enable_embedding=False,
                auto_tag=False, extract_dates=False,
            )
            frames.append({"id": doc["id"], "native_frame_id": frame, "uri": uri})
        self.metadata = {
            "classification": "memory backend lexical component; no generation or semantic search",
            "mode": "Memvid SDK put + find(mode=lex), compiled Tantivy engine",
            "search_api": "Memvid.find(mode=lex, scope=URI-prefix, k=5); Memvid.frame",
            "scope": "native URI-prefix scope; no result post-filter or refill",
            "indexed_text": "original body plus native title/URI/metadata framing",
            "ingestion": {"auto_tag": False, "extract_dates": False, "enable_embedding": False,
                          "search_text": "unchanged original page body", "timestamp": "source ISO time converted to epoch seconds"},
            "source_mapping": "native frame identity/metadata and exact complete normalized body plus known native framing checked; common pack restores supplied original whitespace",
            "native_byte_exact_read_tested": False,
            "frames": frames, "native_stats": self.memory.stats(),
            "persistent": True, "model_calls": 0,
        }
        if self.metadata["native_stats"].get("vec_index_bytes", 0):
            raise ValueError("Unexpected Memvid vector index in lexical-only protocol")

    def search(self, query, project, limit):
        native = self.memory.find(query, k=limit, mode="lex", snippet_chars=100000,
                                  scope=f"memory-book://{quote(project, safe='')}/")
        frames = [self.memory.frame(hit["uri"]) for hit in native["hits"]]
        records = [memvid_record(hit, frame, self.documents, project)
                   for hit, frame in zip(native["hits"], frames)]
        return {"hit_ids": [record["id"] for record in records], "records": records,
                "scores": [hit["score"] for hit in native["hits"]],
                "native_payload": native, "native_frames": frames}

    def close(self):
        self.memory.close()


CLASSES = {"haystack_bm25": HaystackBM25, "bm25s": BM25Sparse, "memvid_lex": MemvidLexical}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    protocol, component, attempts = sys.stdout, None, []
    try:
        for line in sys.stdin:
            request = None
            try:
                request = json.loads(line)
                with redirect_stdout(sys.stderr):
                    if request["op"] == "init":
                        if component is not None:
                            raise ValueError("Worker already initialized")
                        packages = package_identity()
                        attempts = block_python_network()
                        started = time.perf_counter_ns()
                        component = CLASSES[args.backend](request["documents"], args.state)
                        if attempts:
                            raise RuntimeError("Component attempted Python network access during setup")
                        result = {"backend": args.backend, "packages": packages,
                                  "supplied_pages": len(request["documents"]),
                                  "native_setup_and_index_ms": (time.perf_counter_ns() - started) / 1e6,
                                  "network_policy": "Python INET tripwire; telemetry disabled; no model/service configured",
                                  **component.metadata}
                    elif request["op"] == "search":
                        if component is None:
                            raise ValueError("Worker not initialized")
                        started = time.perf_counter_ns()
                        result = component.search(request["query"], request["project"], request["limit"])
                        result["search_ms"] = (time.perf_counter_ns() - started) / 1e6
                        if attempts:
                            raise RuntimeError("Component attempted Python network access during search")
                        result["network_attempts"] = len(attempts)
                    else:
                        raise ValueError("Unknown worker operation")
                payload = {"id": request["id"], "result": serializable(result)}
            except Exception:
                payload = {"id": request.get("id") if request else None, "error": traceback.format_exc()}
            protocol.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
            protocol.flush()
    finally:
        if component is not None:
            with redirect_stdout(sys.stderr):
                component.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
