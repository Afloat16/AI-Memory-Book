"""Run installed upstream memory packages behind an isolated JSON transport.

Only input mapping, serialization, integrity checks and lifecycle live here.
All lexical ranking, vector ranking and embeddings execute upstream code.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
from dataclasses import asdict, is_dataclass
from datetime import datetime
import importlib.metadata
import json
from pathlib import Path
import socket
import sys
import time
import traceback

from benchmarks.competitors.memory_systems import (
    LOCK_PATH, installed_identity, model_artifacts, validate_documents,
)


def serializable(value):
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return serializable(asdict(value))
    if hasattr(value, "tolist"):
        return serializable(value.tolist())
    return value


def collection_configuration_json(collection):
    """Retain Chroma's public JSON configuration, not its live EF objects."""
    configuration = collection.configuration_json
    if not isinstance(configuration, dict):
        raise TypeError("Chroma configuration_json must be a JSON object")
    # Fail rather than stringify or omit an unsupported native configuration.
    json.dumps(configuration, allow_nan=False)
    return configuration


def block_python_network():
    """Tripwire after public artifact preparation; never fabricate a response."""
    attempts = []
    previous = socket.socket.connect
    previous_ex = socket.socket.connect_ex

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            attempts.append(str(address))
            raise RuntimeError("Measured memory component attempted a network connection")
        return previous(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            attempts.append(str(address))
            raise RuntimeError("Measured memory component attempted a network connection")
        return previous_ex(sock, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    return attempts


def real_embedding(cache):
    metadata = model_artifacts(cache)
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    if ONNXMiniLM_L6_V2._MODEL_SHA256 != metadata["archive_sha256"]:
        raise ValueError("Installed official embedding implementation changed model identity")
    # This changes only the application-owned cache location. Model execution,
    # tokenizer, pooling, normalization and truncation stay upstream defaults.
    ONNXMiniLM_L6_V2.DOWNLOAD_PATH = Path(metadata["cache_directory"])
    embedding = ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])
    return embedding, metadata


class BasicMemoryText:
    def __init__(self, docs, state, cache):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from basic_memory.repository.search_reader import SearchReader
        from basic_memory.repository.search_scope import ProjectScope
        from basic_memory.repository.sqlite_search_query import SQLiteFts

        self.docs = validate_documents(docs)
        self.projects = {p: n + 1 for n, p in enumerate(sorted({d["project"] for d in docs}))}
        self.reverse_projects = {v: k for k, v in self.projects.items()}
        self.loop = asyncio.new_event_loop()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{state / 'basic-memory.db'}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.readers = {project: SearchReader(ProjectScope.single(identifier), SQLiteFts(self.sessions))
                        for project, identifier in self.projects.items()}
        self.loop.run_until_complete(self._index(docs))
        self.metadata = {
            "mode": "explicit text/FTS supplied-entity component; not default hybrid",
            "search_api": "SearchReader.search + SQLiteFts.search",
            "query_preparation": "official prepare_search_query and relaxed_fts_fallback_eligible",
            "indexing": "official accepted-note row builder, insert parameters and FTS schema",
            "semantic_search": False, "reranker": False,
        }

    async def _index(self, docs):
        from basic_memory.models.search import CREATE_SEARCH_INDEX
        from basic_memory.indexing.accepted_note_search import build_accepted_note_search_row
        from basic_memory.repository.accepted_note_search_repository import (
            accepted_note_search_insert_params, accepted_note_search_insert_statement,
        )

        async with self.sessions.begin() as session:
            await session.execute(CREATE_SEARCH_INDEX)
            for number, doc in enumerate(docs, 1):
                row = build_accepted_note_search_row(
                    entity_id=number, title=doc["title"], note_type="note",
                    entity_metadata={}, permalink=doc["id"], file_path=doc["id"] + ".md",
                    search_content=doc["text"], created_at=datetime.fromisoformat(doc["created_at"]),
                    updated_at=datetime.fromisoformat(doc["created_at"]),
                    project_id=self.projects[doc["project"]],
                )
                await session.execute(accepted_note_search_insert_statement(session),
                                      accepted_note_search_insert_params(row, include_full_content_grams=True))

    async def _search(self, query, project, limit):
        from basic_memory.schemas.search import SearchQuery, SearchRetrievalMode
        from basic_memory.services.search_service import (
            prepare_search_query, relaxed_fts_fallback_eligible,
        )

        native_query = SearchQuery(text=query, retrieval_mode=SearchRetrievalMode.FTS)
        prepared = prepare_search_query(native_query)
        if prepared is None or project not in self.readers:
            return [], False
        relaxed = relaxed_fts_fallback_eligible(native_query, prepared.search_text,
                                               prepared.retrieval_mode)
        rows = await self.readers[project].search(prepared, limit=limit, offset=0,
                                                allow_relaxed=relaxed)
        return rows, relaxed

    def search(self, query, project, limit):
        rows, relaxed = self.loop.run_until_complete(self._search(query, project, limit))
        records = [{"id": row.permalink, "project": self.reverse_projects[row.project_id],
                    "text": row.content_snippet} for row in rows]
        return {"hit_ids": [r["id"] for r in records], "records": records,
                "native_payload": serializable(rows), "native_allow_relaxed": relaxed}

    def close(self):
        self.loop.run_until_complete(self.engine.dispose())
        self.loop.close()


class ChromaMemory:
    def __init__(self, docs, state, cache):
        import chromadb
        from chromadb.config import Settings

        self.embedding, model = real_embedding(cache)
        self.client = chromadb.PersistentClient(path=str(state / "chroma"),
                                              settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.create_collection("engineering_original_pages",
                                                        embedding_function=self.embedding)
        if docs:
            self.collection.add(ids=[d["id"] for d in docs], documents=[d["text"] for d in docs],
                                metadatas=[{"project": d["project"], "title": d["title"],
                                            "source_created_at": d["created_at"]} for d in docs])
        self.metadata = {"mode": "local vector retrieval infrastructure",
                         "search_api": "Collection.query(query_texts, where, n_results)",
                         "model": model, "indexed_fields": ["original page body"],
                         "collection_configuration": collection_configuration_json(self.collection),
                         "default_metric_retained": True, "persistent": True}

    def search(self, query, project, limit):
        native = self.collection.query(query_texts=[query], n_results=limit,
                                       where={"project": project},
                                       include=["documents", "metadatas", "distances"])
        records = [{"id": identity, "project": metadata["project"], "text": body}
                   for identity, metadata, body in zip(native["ids"][0],
                                                       native["metadatas"][0], native["documents"][0])]
        return {"hit_ids": native["ids"][0], "records": records, "native_payload": serializable(native)}

    def close(self):
        self.client._system.stop()


class LangGraphMemory:
    def __init__(self, docs, state, cache):
        from langgraph.store.memory import InMemoryStore

        self.embedding, model = real_embedding(cache)

        def embed(texts):
            return [vector.tolist() for vector in self.embedding(list(texts))]

        self.store = InMemoryStore(index={"dims": 384, "embed": embed, "fields": ["text"]})
        for doc in docs:
            self.store.put((doc["project"], "original_pages"), doc["id"], dict(doc))
        self.metadata = {"mode": "explicit indexed semantic store; not unindexed default",
                         "search_api": "InMemoryStore.search(namespace, query, limit)",
                         "model": model, "indexed_fields": ["text"], "dimensions": 384,
                         "metric": "upstream cosine similarity", "persistent": False}

    def search(self, query, project, limit):
        rows = self.store.search((project, "original_pages"), query=query, limit=limit)
        native = [{"namespace": list(row.namespace), "key": row.key, "value": row.value,
                   "score": row.score, "created_at": row.created_at, "updated_at": row.updated_at}
                  for row in rows]
        records = [{"id": row.key, "project": row.value["project"], "text": row.value["text"]}
                   for row in rows]
        return {"hit_ids": [r["id"] for r in records], "records": records,
                "native_payload": serializable(native)}

    def close(self):
        pass


class Mem0RawMemory:
    def __init__(self, docs, state, cache):
        from langchain.embeddings.base import Embeddings
        from mem0 import Memory

        self.embedding, model = real_embedding(cache)
        embedding = self.embedding

        class RealMiniLM(Embeddings):
            """Interface adaptation only; every vector is official ONNX output."""
            def embed_documents(self, texts):
                return [vector.tolist() for vector in embedding(list(texts))]

            def embed_query(self, text):
                return self.embed_documents([text])[0]

        self.memory = Memory.from_config({
            "embedder": {"provider": "langchain", "config": {"model": RealMiniLM(), "embedding_dims": 384}},
            "vector_store": {"provider": "chroma", "config": {
                "collection_name": "engineering_original_pages", "path": str(state / "mem0-chroma")}},
            "llm": {"provider": "ollama", "config": {"ollama_base_url": "http://127.0.0.1:9"}},
            "history_db_path": str(state / "mem0-history.db"),
        })
        self.native_ids = {}
        self.ingestion_responses = []
        for doc in docs:
            result = self.memory.add([{"role": "user", "content": doc["text"]}],
                                     user_id=doc["project"], infer=False,
                                     metadata={"page_id": doc["id"], "source_project": doc["project"],
                                               "title": doc["title"], "source_created_at": doc["created_at"]})
            self.ingestion_responses.append(result)
            items = result["results"]
            if len(items) != 1 or items[0].get("memory") != doc["text"]:
                raise ValueError("Mem0 infer=False did not preserve one exact original page")
            self.native_ids[items[0]["id"]] = doc["id"]
        self.metadata = {"mode": "infer=False raw-memory retrieval, not default fact extraction",
                         "search_api": "Memory.search(query, filters={user_id:project}, top_k=5)",
                         "model": model, "vector_store": "native Chroma local persistent provider",
                         "llm": "native Ollama client at 127.0.0.1:9; unused; no service or key",
                         "inference": False, "rerank": False, "threshold": "native default 0.1",
                         "ingestion_responses": serializable(self.ingestion_responses)}

    def search(self, query, project, limit):
        native = self.memory.search(query, filters={"user_id": project}, top_k=limit)
        rows = native["results"]
        records = []
        for row in rows:
            metadata = row.get("metadata") or {}
            identity = self.native_ids[row["id"]]
            if metadata.get("page_id") != identity or row.get("user_id") != project:
                raise ValueError("Mem0 returned inconsistent original page/user metadata")
            records.append({"id": identity, "project": metadata["source_project"], "text": row["memory"]})
        return {"hit_ids": [r["id"] for r in records], "records": records,
                "native_payload": serializable(native)}

    def close(self):
        self.memory.vector_store.client._system.stop()


CLASSES = {"basic_memory": BasicMemoryText, "chroma": ChromaMemory,
           "langgraph": LangGraphMemory, "mem0": Mem0RawMemory}
PACKAGE_NAMES = {
    "basic_memory": ["basic-memory", "sqlalchemy", "aiosqlite"],
    "chroma": ["chromadb", "onnxruntime", "tokenizers"],
    "langgraph": ["langgraph-checkpoint", "langchain-core", "chromadb", "onnxruntime", "tokenizers"],
    "mem0": ["mem0ai", "chromadb", "langchain", "langchain-core", "ollama", "onnxruntime", "tokenizers"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=CLASSES)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    protocol = sys.stdout
    if args.prepare:
        with redirect_stdout(sys.stderr):
            lock = json.loads(LOCK_PATH.read_text())
            packages = installed_identity(lock["packages"])
            model = model_artifacts(args.cache, download=True)
            embedding, _ = real_embedding(args.cache)
            vectors = embedding(["Public component installation check."])
            if len(vectors) != 1 or len(vectors[0]) != 384:
                raise ValueError("Official model returned an unexpected dimension")
        protocol.write(json.dumps({"status": "prepared", "packages": packages,
                                   "model": model, "real_embedding_dimensions": 384}) + "\n")
        return 0
    if args.backend is None:
        parser.error("--backend is required unless --prepare is used")
    component = None
    attempts = []
    try:
        for line in sys.stdin:
            request = None
            try:
                request = json.loads(line)
                with redirect_stdout(sys.stderr):
                    if request["op"] == "init":
                        if component is not None:
                            raise ValueError("Worker already initialized")
                        packages = installed_identity(PACKAGE_NAMES[args.backend])
                        if args.backend != "basic_memory":
                            model_artifacts(args.cache)  # fail before any provider can download
                        attempts = block_python_network()
                        started = time.perf_counter_ns()
                        component = CLASSES[args.backend](request["documents"], args.state, args.cache)
                        if attempts:
                            raise RuntimeError("Component attempted network access during setup")
                        result = {"backend": args.backend, "packages": packages,
                                  "supplied_pages": len(request["documents"]),
                                  "native_setup_and_index_ms": (time.perf_counter_ns() - started) / 1e6,
                                  "network_policy": "Python INET connections denied after preparation; telemetry disabled",
                                  **component.metadata}
                    elif request["op"] == "search":
                        if component is None:
                            raise ValueError("Worker not initialized")
                        started = time.perf_counter_ns()
                        result = component.search(request["query"], request["project"], request["limit"])
                        result["search_ms"] = (time.perf_counter_ns() - started) / 1e6
                        if attempts:
                            raise RuntimeError("Component attempted network access during retrieval")
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
