"""Execute unmodified upstream ReMe chunking, indexing and BM25 search."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

from .memory_systems import sha_bytes, sha_file, validate_documents
from .memory_systems_worker import block_python_network
from .reme import dependency_identity, load_lock, source_identity


def original_path(doc):
    """Filesystem-safe identity without case folding or project normalization."""
    project = hashlib.sha256(doc["project"].encode("utf-8")).hexdigest()
    page = hashlib.sha256(doc["id"].encode("utf-8")).hexdigest()
    return f"pages/{project}/{page}.txt"


def authenticate_chunk(doc, node, chunks, relative):
    """Require native parsing to preserve one entire supplied original page."""
    if len(chunks) != 1:
        raise ValueError("ReMe protocol requires exactly one native chunk per original page")
    chunk = chunks[0]
    if node.path != relative or chunk.path != relative or node.chunk_ids != [chunk.id]:
        raise ValueError("Native ReMe file/chunk identities do not match the original file")
    if chunk.text != doc["text"]:
        raise ValueError("ReMe native parser changed original text")
    end_line = 1 + doc["text"].count("\n") - int(doc["text"].endswith("\n"))
    expected_id = sha_bytes(" ".join([relative, "1", str(end_line), doc["text"]]).encode("utf-8"))
    if chunk.start_line != 1 or chunk.end_line != end_line or chunk.id != expected_id:
        raise ValueError("Native ReMe chunk has invalid original coordinates or content hash")
    return chunk


def authenticate_results(native, originals, chunks, project, limit):
    """Reject bad native evidence instead of filtering, expanding or reordering."""
    if not isinstance(native, list) or len(native) > limit:
        raise ValueError("ReMe exceeded the registered native candidate limit")
    records = []
    seen = set()
    for row in native:
        if not isinstance(row, dict) or row.get("path") not in originals:
            raise ValueError("Unmapped native ReMe source path")
        doc = originals[row["path"]]
        expected = chunks[row["path"]]
        if doc["project"] != project:
            raise ValueError("Native ReMe returned a foreign project")
        if doc["id"] in seen:
            raise ValueError("Native ReMe returned duplicate original pages")
        if (row.get("id") != expected["id"] or row.get("text") != doc["text"]
                or row.get("start_line") != expected["start_line"]
                or row.get("end_line") != expected["end_line"]):
            raise ValueError("Native ReMe returned changed source text or coordinates")
        records.append({"id": doc["id"], "project": doc["project"], "text": row["text"]})
        seen.add(doc["id"])
    json.dumps(native, ensure_ascii=False, allow_nan=False)
    return records


class NativeReMe:
    def __init__(self, documents, state):
        docs = list(documents)
        self.documents = validate_documents(docs)
        self.workspace = Path(state).resolve() / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=False)
        # Only this isolated worker changes cwd. Upstream standalone components
        # deliberately use cwd for their workspace and derived metadata paths.
        os.chdir(self.workspace)
        from reme.components.file_chunker import DefaultFileChunker
        from reme.components.file_store import LocalFileStore

        self.store = LocalFileStore(embedding_store="")
        self.chunker = DefaultFileChunker()
        self.loop = asyncio.new_event_loop()
        self.originals = {}
        self.chunks = {}
        self.project_paths = {}
        self.closed = False
        started = time.perf_counter_ns()
        try:
            self.loop.run_until_complete(self._index(docs))
        except BaseException:
            self.close()
            raise
        self.metadata = {
            "mode": "native original-text file chunker + local BM25 component",
            "index_api": "DefaultFileChunker.chunk -> LocalFileStore.upsert",
            "search_api": "LocalFileStore.keyword_search -> BM25Index.retrieve_filtered",
            "source_files_unmodified": True,
            "original_page_files_unmodified": True,
            "candidate_unit": "one complete original page per native FileChunk",
            "page_count": len(docs), "native_chunk_count": len(self.chunks),
            "project_count": len(self.project_paths),
            "project_filter": "exact project ID -> exact native paths before BM25 top-k",
            "project_mapping_is_access_control": False,
            "project_id_normalization": "none",
            "embedding_store": None, "llm_constructed": False,
            "semantic_search": False, "reranker": False,
            "native_defaults": {
                "chunk_byte_size": self.chunker.chunk_byte_size,
                "overlap_byte_size": self.chunker.overlap_byte_size,
                "k1": self.store.keyword_index.k1, "b": self.store.keyword_index.b,
                "tokenizer": type(self.store.keyword_index.tokenizer).__name__,
                "filter_stopwords": self.store.keyword_index.tokenizer.filter_stopwords,
                "stopwords_sha256": sha_file(self.store.keyword_index.tokenizer.stopwords_path),
            },
            "source_mapping": [{
                "id": doc["id"], "project": doc["project"], "native_path": path,
                "original_sha256": sha_bytes(doc["text"].encode("utf-8")),
                "native_chunk_id": self.chunks[path]["id"],
                "start_line": self.chunks[path]["start_line"],
                "end_line": self.chunks[path]["end_line"],
            } for path, doc in self.originals.items()],
            "index_ms": (time.perf_counter_ns() - started) / 1e6,
        }

    async def _index(self, docs):
        await self.store.start()
        await self.chunker.start()
        if self.store.embedding_store is not None:
            raise ValueError("The registered ReMe component must not construct embeddings")
        for doc in docs:
            relative = original_path(doc)
            if relative in self.originals:
                raise ValueError("Native original file identity collision")
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(doc["text"].encode("utf-8"))
            node, chunks = await self.chunker.chunk(path)
            chunk = authenticate_chunk(doc, node, chunks, relative)
            if path.read_bytes() != doc["text"].encode("utf-8"):
                raise ValueError("ReMe ingestion modified an original source file")
            await self.store.upsert([(node, chunks)])
            self.originals[relative] = doc
            self.chunks[relative] = chunk.model_dump(mode="json")
            self.project_paths.setdefault(doc["project"], []).append(relative)
        if len(self.store.file_chunks) != len(docs):
            raise ValueError("ReMe index did not retain every original page")
        await self.store.dump()

    def search(self, query, project, limit):
        if not isinstance(query, str) or not isinstance(project, str) or not project:
            raise ValueError("Expected unchanged query and explicit exact project ID")
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("Invalid registered ReMe candidate limit")
        # Empty paths are a real native filter matching no chunk. Do not omit
        # this key for an unknown project, which would broaden to all files.
        search_filter = {"paths": list(self.project_paths.get(project, []))}
        started = time.perf_counter_ns()
        rows = self.loop.run_until_complete(self.store.keyword_search(query, limit, search_filter))
        search_ms = (time.perf_counter_ns() - started) / 1e6
        native = [row.model_dump(mode="json") for row in rows]
        records = authenticate_results(native, self.originals, self.chunks, project, limit)
        for row in native:
            if (self.workspace / row["path"]).read_bytes() != row["text"].encode("utf-8"):
                raise ValueError("Native ReMe result no longer matches its original file")
        return {"hit_ids": [r["id"] for r in records], "records": records,
                "native_payload": native, "native_search_filter": search_filter,
                "search_ms": search_ms}

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.loop.run_until_complete(self.chunker.close())
        finally:
            try:
                self.loop.run_until_complete(self.store.close())
            finally:
                self.loop.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--identity", action="store_true")
    args = parser.parse_args()
    identity = {"source": source_identity(args.source), "dependencies": dependency_identity()}
    if args.identity:
        print(json.dumps(identity, ensure_ascii=False, allow_nan=False))
        return
    if args.state is None:
        parser.error("--state is required for a worker")
    source = args.source.resolve()
    sys.path.insert(0, str(source))
    attempts = block_python_network()
    component = None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            try:
                with redirect_stdout(sys.stderr):
                    if request["op"] == "init":
                        if component is not None:
                            raise ValueError("ReMe worker already initialized")
                        component = NativeReMe(request["documents"], args.state)
                        import reme

                        if Path(reme.__file__).resolve() != source / "reme" / "__init__.py":
                            raise ValueError("Worker imported ReMe outside the verified source tree")
                        if reme.__version__ != load_lock()["source"]["declared_source_version"]:
                            raise ValueError("Unexpected upstream source version")
                        result = {**identity, **component.metadata,
                                  "python_network_attempts": list(attempts)}
                    elif request["op"] == "search" and component is not None:
                        result = component.search(request["query"], request["project"], request["limit"])
                    else:
                        raise ValueError("Invalid or uninitialized ReMe worker operation")
                    if attempts:
                        raise RuntimeError("ReMe attempted network access during native execution")
                reply = {"id": request["id"], "result": result}
            except Exception:
                reply = {"id": request.get("id"), "error": traceback.format_exc()}
            print(json.dumps(reply, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        with redirect_stdout(sys.stderr):
            if component is not None:
                component.close()
            source_identity(source)
        if attempts:
            raise RuntimeError("ReMe worker recorded blocked network attempts")


if __name__ == "__main__":
    main()
