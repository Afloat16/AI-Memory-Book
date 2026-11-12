"""Explicit, offline semantic candidates over original page text.

This optional module is never imported by ordinary lexical recall. The model
and tokenizer are deliberately pinned: changing their bytes or the window and
pooling rules requires rebuilding the derived index. No source text is sent to
an endpoint, and downloading model artifacts is a separate, explicit operation.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any


SEMANTIC_VERSION = 1
# Retrieval ordering has its own cache identity. Changing fusion alone must
# neither change the verified model fingerprint nor rebuild identical vectors.
FUSION_VERSION = 3
MODEL_REPOSITORY = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_FILES = (
    {"path": "onnx/model_quint8_avx2.onnx", "bytes": 118453870,
     "sha256": "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f"},
    {"path": "tokenizer.json", "bytes": 9081518,
     "sha256": "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8"},
)
DIMENSIONS = 384
MAX_TOKENS = 128
OVERLAP_TOKENS = 32
CANDIDATE_LIMIT = 96
RRF_K = 60


class SemanticIndexError(RuntimeError):
    """The explicit derived index is missing, stale, or incompatible."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def verify_model_files(directory: str | Path) -> dict:
    """Verify exact local artifacts without network calls or optional imports."""
    root = Path(directory).expanduser().resolve()
    for entry in MODEL_FILES:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Missing or incorrect semantic model artifact: {entry['path']}; "
                             "prepare the pinned model before enabling semantic recall")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"Semantic model SHA-256 mismatch: {entry['path']}")
    return {"repository": MODEL_REPOSITORY, "revision": MODEL_REVISION,
            "files": list(MODEL_FILES), "dimensions": DIMENSIONS,
            "max_sequence_tokens": MAX_TOKENS, "overlap_tokens": OVERLAP_TOKENS,
            "pooling": "attention-mask mean pooling followed by L2 normalization",
            "semantic_version": SEMANTIC_VERSION}


class SemanticModel:
    """A verified CPU ONNX session, loaded only on explicit use.

    MemoryBook instances are not shared between threads. The same restriction
    applies to this tokenizer/session wrapper. One inference thread avoids
    silently taking every CPU on the caller's machine.
    """

    def __init__(self, directory: str | Path):
        started = time.perf_counter_ns()
        identity = verify_model_files(directory)
        # Recent ORT builds can create a telemetry uploader during import.
        # Set the process-lifetime opt-out before that initialization; the API
        # alone cannot prevent an earlier initialization event.
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise RuntimeError("Semantic recall needs the optional 'semantic' dependencies; "
                               "install ai-memory-book[semantic] from the source checkout") from exc
        # Also disable API-controlled events for older/Windows backends and
        # hosts which had already imported ORT before creating this model.
        ort.disable_telemetry_events()
        self.np = np
        self.identity = identity
        self.fingerprint = hashlib.sha256(_json(identity).encode()).hexdigest()
        root = Path(directory).expanduser().resolve()
        # Load the exact verified byte snapshot. A file replacement between
        # hashing and session construction must not change the identified model.
        blobs = {}
        for entry in MODEL_FILES:
            blob = (root / entry["path"]).read_bytes()
            if len(blob) != entry["bytes"] or hashlib.sha256(blob).hexdigest() != entry["sha256"]:
                raise ValueError("Semantic model artifacts changed during initialization")
            blobs[entry["path"]] = blob
        self.tokenizer = Tokenizer.from_str(blobs["tokenizer.json"].decode("utf-8"))
        self.tokenizer.no_padding()
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS, stride=OVERLAP_TOKENS)
        self.pad_id = self.tokenizer.token_to_id("<pad>")
        if self.pad_id is None:
            self.pad_id = self.tokenizer.token_to_id("[PAD]")
        if self.pad_id is None:
            raise ValueError("Pinned semantic tokenizer has no padding token")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(blobs[MODEL_FILES[0]["path"]],
                                           sess_options=options, providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}
        if not {"input_ids", "attention_mask"} <= self.input_names or self.input_names - {
                "input_ids", "attention_mask", "token_type_ids"}:
            raise ValueError("Unexpected inputs in the pinned semantic ONNX model")
        self.runtime = {name: importlib.metadata.version(name)
                        for name in ("onnxruntime", "tokenizers", "numpy")}
        self.load_ms = (time.perf_counter_ns() - started) / 1e6

    def _windows(self, text: str) -> list[tuple[int, int, Any]]:
        encoded = self.tokenizer.encode(text)
        result = []
        for window in [encoded, *encoded.overflowing]:
            offsets = [offset for offset, special in zip(window.offsets, window.special_tokens_mask)
                       if not special and offset[1] > offset[0]]
            if offsets:
                result.append((min(a for a, _ in offsets), max(b for _, b in offsets), window))
        return result

    def _encode(self, encodings: list[Any]):
        np = self.np
        if not encodings:
            return np.empty((0, DIMENSIONS), dtype="<f4")
        size = max(len(item.ids) for item in encodings)
        if size > MAX_TOKENS:
            raise ValueError("Semantic tokenizer exceeded its registered window length")
        ids = np.full((len(encodings), size), self.pad_id, dtype=np.int64)
        mask = np.zeros_like(ids)
        types = np.zeros_like(ids)
        for i, encoding in enumerate(encodings):
            length = len(encoding.ids)
            ids[i, :length] = encoding.ids
            mask[i, :length] = encoding.attention_mask
            types[i, :length] = encoding.type_ids
        inputs = {"input_ids": ids, "attention_mask": mask, "token_type_ids": types}
        output = self.session.run(None, {key: inputs[key] for key in self.input_names})[0]
        if output.ndim != 3 or output.shape != (len(encodings), size, DIMENSIONS):
            raise ValueError("Unexpected semantic hidden-state dimensions")
        weights = mask.astype(np.float32)[..., None]
        vectors = (output * weights).sum(axis=1) / weights.sum(axis=1).clip(min=1)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if not np.isfinite(vectors).all() or not np.isfinite(norms).all() or (norms <= 0).any():
            raise ValueError("Semantic model returned invalid vectors")
        return np.asarray(vectors / norms, dtype="<f4")

    def encode_pages(self, pages: list[dict]) -> list[tuple[str, int, int, int, bytes]]:
        """Encode complete page windows; return little-endian float32 blobs."""
        pending, references, vectors = [], [], []

        def flush() -> None:
            if pending:
                embeddings = self._encode(pending)
                vectors.extend((*ref, embedding.tobytes())
                               for ref, embedding in zip(references, embeddings))
                pending.clear()
                references.clear()

        for page in pages:
            for ordinal, (start, end, encoding) in enumerate(self._windows(page["content"])):
                pending.append(encoding)
                references.append((page["id"], ordinal, start, end))
                if len(pending) == 32:
                    flush()
        flush()
        return vectors

    def encode_query(self, query: str):
        return self._encode([window for _, _, window in self._windows(query)])


def build_index(db: sqlite3.Connection, model: SemanticModel) -> dict:
    """Encode a read snapshot and atomically publish only at its revision.

    Encoding holds no write transaction. Concurrent ingestion therefore wins
    normally and makes this build fail clearly instead of publishing stale
    vectors. The existing index is preserved on every failure.
    """
    started = time.perf_counter_ns()
    db.execute("BEGIN")
    try:
        revision = int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
        pages = [dict(row) for row in db.execute("SELECT id,content FROM pages ORDER BY id")]
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    fingerprint = hashlib.sha256(_json(pages).encode()).hexdigest()
    vectors = model.encode_pages(pages)
    report = {"revision": revision, "model_fingerprint": model.fingerprint,
              "model": model.identity, "runtime": model.runtime,
              "model_load_ms": model.load_ms, "pages": len(pages),
              "windows": len(vectors), "vector_bytes": sum(len(row[-1]) for row in vectors),
              "source_chars": sum(len(page["content"]) for page in pages),
              "source_sha256": fingerprint, "inference_threads": 1}
    db.execute("BEGIN IMMEDIATE")
    try:
        current = int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
        if current != revision:
            raise SemanticIndexError("Memory changed while building the semantic index; rebuild it")
        db.execute("""CREATE TABLE IF NOT EXISTS semantic_meta (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            revision INTEGER NOT NULL, model_fingerprint TEXT NOT NULL, metadata TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS semantic_vectors (
            page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL, char_start INTEGER NOT NULL, char_end INTEGER NOT NULL,
            vector BLOB NOT NULL, PRIMARY KEY(page_id,ordinal))""")
        db.execute("DELETE FROM semantic_vectors")
        db.executemany("INSERT INTO semantic_vectors VALUES(?,?,?,?,?)", vectors)
        report["build_ms"] = (time.perf_counter_ns() - started) / 1e6
        db.execute("INSERT OR REPLACE INTO semantic_meta VALUES(1,?,?,?)",
                   (revision, model.fingerprint, _json(report)))
        # The same revision may be reindexed with another model/implementation.
        # Clearing shared result caches cannot change the lexical answer.
        db.execute("DELETE FROM recall_cache")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    report["build_ms"] = (time.perf_counter_ns() - started) / 1e6
    return report


def check_index(db: sqlite3.Connection, revision: int, model: SemanticModel) -> dict:
    """Validate freshness inside the caller's retrieval read transaction."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='semantic_meta'").fetchone():
        raise SemanticIndexError("No semantic index; call build_semantic_index() explicitly")
    row = db.execute("SELECT revision,model_fingerprint,metadata FROM semantic_meta WHERE singleton=1").fetchone()
    if row is None or row["revision"] != revision or row["model_fingerprint"] != model.fingerprint:
        raise SemanticIndexError("Semantic index is stale or uses a different model; call build_semantic_index()")
    return json.loads(row["metadata"])


def rank_pages(db: sqlite3.Connection, model: SemanticModel, query: str,
               where: str, params: list) -> list[dict]:
    """Rank only requested scopes, then collapse windows and take 96 pages."""
    rows = db.execute("""SELECT p.id,p.rid,p.project_id,p.chapter_id,
        c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at,
        v.ordinal,v.vector FROM semantic_vectors v JOIN pages p ON p.id=v.page_id
        JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
        WHERE 1=1""" + where + " ORDER BY p.id,v.ordinal", params).fetchall()
    if not rows:
        return []
    query_vectors = model.encode_query(query)
    if not len(query_vectors):
        return []
    np = model.np
    best: dict[str, dict] = {}
    # Bound temporary matrix memory even when a scope contains a large archive.
    for start in range(0, len(rows), 4096):
        chunk = rows[start:start + 4096]
        if any(len(row["vector"]) != DIMENSIONS * 4 for row in chunk):
            raise SemanticIndexError("Semantic index vector dimensions are invalid; rebuild it")
        matrix = np.frombuffer(b"".join(row["vector"] for row in chunk), dtype="<f4").reshape(-1, DIMENSIONS)
        if not np.isfinite(matrix).all():
            raise SemanticIndexError("Semantic index contains non-finite values; rebuild it")
        # einsum avoids launching a separate BLAS thread pool for tiny queries.
        similarities = np.einsum("ij,kj->ik", matrix, query_vectors, optimize=False).max(axis=1)
        for row, similarity in zip(chunk, similarities):
            score = float(similarity)
            if row["id"] not in best or score > best[row["id"]]["semantic_similarity"]:
                item = {key: row[key] for key in row.keys() if key not in {"vector", "ordinal"}}
                item["semantic_similarity"] = score
                best[row["id"]] = item
    return sorted(best.values(), key=lambda row: (-row["semantic_similarity"], row["id"]))[:CANDIDATE_LIMIT]


def fuse_candidates(lexical: list[dict], semantic: list[dict]) -> list[dict]:
    """Preserve the existing lexical leader and the remaining RRF order.

    Equal-weight RRF(k=60) supplies each page's unchanged diagnostic score.
    The first existing lexical candidate is then promoted once; every other
    candidate keeps its RRF relative order. Scores need not be monotonic after
    this priority rule. No labels, thresholds, extra model calls or new pages
    are used, and pure-semantic retrieval remains unchanged.
    """
    combined: dict[str, dict] = {}
    for route in (lexical, semantic):
        for rank, row in enumerate(route, 1):
            page_id = row["id"]
            if page_id not in combined:
                combined[page_id] = {**row, "score": 0.0}
            combined[page_id]["score"] += 1 / (RRF_K + rank)
            if "semantic_similarity" in row:
                combined[page_id]["semantic_similarity"] = row["semantic_similarity"]
    ranked = sorted(combined.values(), key=lambda row: (-row["score"], row["id"]))
    if lexical and semantic:
        position = next(index for index, row in enumerate(ranked) if row["id"] == lexical[0]["id"])
        if position:
            ranked.insert(0, ranked.pop(position))
    return ranked
