"""Run the official ai-memory release's native FTS5 or hybrid MCP search.

This is a page-retrieval component comparison. Its /admin/search endpoint is
also what the native search CLI calls; it is not the optional embedding-backed
MCP memory_query pipeline. The native write/read/search code is never replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import platform
import secrets
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
from typing import Any, Iterable

from .download import fetch_bytes

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "ai-memory-lock.json"


def prepare(cache_dir: Path, *, offline: bool = False) -> Path:
    """Download and verify an immutable official Linux x86-64 release."""
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise RuntimeError("The pinned ai-memory binary adapter requires Linux x86-64")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    cache_dir = Path(cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / f"ai-memory-linux-x86_64-{lock['version']}.tar.gz"
    if not archive.exists():
        if offline:
            raise FileNotFoundError(f"Missing pinned archive: {archive}")
        data = fetch_bytes(lock["asset_url"])
        if hashlib.sha256(data).hexdigest() != lock["archive_sha256"]:
            raise ValueError("ai-memory release archive SHA-256 does not match pin")
        archive.write_bytes(data)
    data = archive.read_bytes()
    if len(data) != lock["archive_bytes"] or hashlib.sha256(data).hexdigest() != lock["archive_sha256"]:
        raise ValueError("ai-memory release archive integrity check failed")
    binary = cache_dir / f"ai-memory-{lock['version']}"
    # Extract only specific regular members. Do not unpack hooks or install
    # services; neither the current user's data nor their client setup is used.
    with tarfile.open(archive, "r:gz") as source:
        for expected, destination in (
            ("ai-memory", binary),
            ("LICENSE", cache_dir / f"ai-memory-{lock['version']}-LICENSE"),
        ):
            members = [
                item for item in source.getmembers()
                if item.isfile() and PurePosixPath(item.name).parts == (expected,)
            ]
            if len(members) != 1:
                raise ValueError(f"Expected one release member: {expected}")
            stream = source.extractfile(members[0])
            if stream is None:
                raise ValueError(f"Could not read release member: {expected}")
            member_data = stream.read()
            if expected == "ai-memory" and hashlib.sha256(member_data).hexdigest() != lock["binary_sha256"]:
                raise ValueError("ai-memory executable integrity check failed")
            if not destination.exists() or destination.read_bytes() != member_data:
                destination.write_bytes(member_data)
    binary.chmod(0o755)
    return binary


def prepare_models(cache_dir: Path, *, offline: bool = False) -> dict[str, Any]:
    """Fetch the three exact model files pinned by the upstream Rust loader."""
    model = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["embedding_model"]
    root = Path(cache_dir).resolve() / "models" / model["name"]
    root.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    downloaded = 0
    for entry in model["files"]:
        target = root / entry["name"]
        if not target.exists():
            if offline:
                raise FileNotFoundError(f"Missing pinned embedding model: {target}")
            data = fetch_bytes(model["base_url"] + "/" + entry["name"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError(f"Embedding model SHA-256 mismatch: {entry['name']}")
            target.write_bytes(data)
            downloaded += len(data)
        data = target.read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Embedding model integrity check failed: {entry['name']}")
    return {
        "name": model["name"],
        "dimensions": 384,
        "input_token_limit": 512,
        "files": model["files"],
        "downloaded_bytes": downloaded,
        "prepare_ms": (time.perf_counter() - start) * 1000,
    }


class AiMemoryNative:
    """An isolated native server containing exactly the supplied shared pages."""

    def __init__(
        self,
        documents: Iterable[dict[str, Any]],
        cache_dir: Path,
        *,
        offline: bool = False,
        timeout: float = 60,
        retrieval: str = "fts",
    ) -> None:
        if retrieval not in {"fts", "hybrid"}:
            raise ValueError("retrieval must be 'fts' or 'hybrid'")
        self.retrieval = retrieval
        docs = list(documents)
        self._documents = {doc["id"]: doc for doc in docs}
        if len(self._documents) != len(docs):
            raise ValueError("Document ids must be unique")
        for doc in docs:
            for key in ("id", "project", "title", "text"):
                if not isinstance(doc.get(key), str):
                    raise TypeError(f"Document {key} must be a string")
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        begin = time.perf_counter()
        cache_dir = Path(cache_dir).resolve()
        binary = prepare(cache_dir, offline=offline)
        self._temporary = tempfile.TemporaryDirectory(prefix="native-data-", dir=cache_dir)
        self._data_dir = Path(self._temporary.name)
        config = self._data_dir / "config.toml"
        model_metadata = None
        if retrieval == "hybrid":
            model_metadata = prepare_models(cache_dir, offline=offline)
            (self._data_dir / "models").symlink_to(cache_dir / "models", target_is_directory=True)
            # Explicit local makes a missing/broken model a hard error, avoiding
            # an accidental FTS fallback labeled as an embedding comparison.
            config.write_text('embedding_provider = "local"\n', encoding="utf-8")
        else:
            config.write_text('embedding_provider = "none"\n', encoding="utf-8")
        with socket.socket() as free_port:
            free_port.bind(("127.0.0.1", 0))
            self._port = free_port.getsockname()[1]
        self._token = secrets.token_urlsafe(32)
        self._log = (self._data_dir / "server.log").open("w+", encoding="utf-8")
        self._closed = False
        self._connection: http.client.HTTPConnection | None = None
        self._process = subprocess.Popen(
            [
                str(binary), "--data-dir", str(self._data_dir),
                "--config", str(config), "serve", "--transport", "http",
                "--bind", f"127.0.0.1:{self._port}", "--no-watcher",
            ],
            stdout=self._log,
            stderr=self._log,
            # Do not inherit real provider tokens, routing, or user config.
            env={
                "PATH": os.defpath,
                "LANG": "C.UTF-8",
                "AI_MEMORY_AUTH_TOKEN": self._token,
            },
        )
        self._by_page_id: dict[str, str] = {}
        self._locations: dict[str, tuple[str, str]] = {}
        self._workspace = "benchmark"
        self._rpc_id = 0
        try:
            deadline = time.monotonic() + timeout
            while True:
                if self._process.poll() is not None:
                    self._log.flush()
                    self._log.seek(0)
                    raise RuntimeError("ai-memory exited at startup:\n" + self._log.read()[-6000:])
                try:
                    self._request("GET", "/admin/search", query={"q": "startup-probe", "limit": 1})
                    break
                except (OSError, http.client.HTTPException):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("ai-memory server startup timed out")
                    time.sleep(0.02)
            startup_ms = (time.perf_counter() - begin) * 1000
            self._initialize_mcp()
            ingest_start = time.perf_counter()
            for doc in docs:
                path = f"pages/{hashlib.sha256(doc['id'].encode()).hexdigest()}.md"
                written, _ = self._request("POST", "/admin/write-page", body={
                    "workspace": self._workspace,
                    "project": doc["project"],
                    "path": path,
                    "body": doc["text"],
                    "title": doc["title"],
                    "tier": "episodic",
                    "tags": [],
                    "pinned": False,
                })
                self._by_page_id[written["page_id"]] = doc["id"]
                self._locations[doc["id"]] = (doc["project"], path)
            ingest_ms = (time.perf_counter() - ingest_start) * 1000
            embedding_report = None
            embedding_wait_ms = 0.0
            if retrieval == "hybrid" and docs:
                embedding_report, embedding_wait_ms = self._request(
                    "POST", "/admin/embed", body={
                        "workspace": self._workspace,
                        "project": "",
                        "reembed": False,
                        "dry_run": False,
                        "all_projects": True,
                    },
                    timeout=600,
                )
                if embedding_report.get("failed", 0):
                    raise RuntimeError(f"Native embedding backfill failed: {embedding_report}")
            self.metadata = {
                "name": (
                    "ai-memory native MCP hybrid with local MiniLM"
                    if retrieval == "hybrid"
                    else "ai-memory native CLI/HTTP FTS5 page retrieval"
                ),
                "repository": lock["repository"],
                "version": lock["version"],
                "commit": lock["commit"],
                "asset_url": lock["asset_url"],
                "archive_sha256": lock["archive_sha256"],
                "binary_sha256": lock["binary_sha256"],
                "license": lock["license"],
                "implementation": "unmodified official release executable",
                "comparison_scope": "shared-page retrieval component",
                "search_route": (
                    "/mcp tools/call memory_query"
                    if retrieval == "hybrid"
                    else "/admin/search (same as native ai-memory search CLI)"
                ),
                "embedding_provider": "local" if retrieval == "hybrid" else "none",
                "embedding_model": model_metadata,
                "embedding_backfill_report": embedding_report,
                "embedding_backfill_ms": embedding_wait_ms,
                "llm_provider": "none (upstream default)",
                "watcher": "disabled; writes index through native HTTP route",
                "native_page_tier": "episodic",
                "documents": len(docs),
                "startup_ms": startup_ms,
                "ingest_ms": ingest_ms,
                "setup_ms": (time.perf_counter() - begin) * 1000,
                "latency_scope": "persistent loopback HTTP client through native response decode",
            }
        except Exception:
            self.close()
            raise

    def _request(
        self,
        method: str,
        route: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> tuple[Any, float]:
        if self._closed:
            raise RuntimeError("ai-memory adapter is closed")
        if query:
            route += "?" + urllib.parse.urlencode(query)
        content = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        if self._connection is None:
            self._connection = http.client.HTTPConnection("127.0.0.1", self._port, timeout=timeout)
        self._connection.timeout = timeout
        if self._connection.sock is not None:
            self._connection.sock.settimeout(timeout)
        start = time.perf_counter()
        try:
            self._connection.request(
                method, route, body=content,
                headers={
                    "Authorization": "Bearer " + self._token,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            response = self._connection.getresponse()
            raw = response.read()
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ai-memory HTTP {response.status}: {raw.decode('utf-8')[:3000]}")
            decoded = json.loads(raw)
        except Exception:
            self._connection.close()
            self._connection = None
            raise
        return decoded, (time.perf_counter() - start) * 1000

    def _initialize_mcp(self) -> None:
        self._rpc_id += 1
        response, _ = self._request("POST", "/mcp", body={
            "jsonrpc": "2.0", "id": self._rpc_id, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "ai-memory-book-benchmark", "version": "1"},
            },
        })
        if "error" in response:
            raise RuntimeError(f"Native MCP initialization failed: {response['error']}")

    def _mcp_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._rpc_id += 1
        rpc, elapsed = self._request("POST", "/mcp", body={
            "jsonrpc": "2.0", "id": self._rpc_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "error" in rpc:
            raise RuntimeError(f"Native MCP error: {rpc['error']}")
        native = rpc["result"]
        if native.get("isError"):
            raise RuntimeError(f"Native MCP tool error: {native}")
        text = "\n".join(part["text"] for part in native["content"] if part["type"] == "text")
        return {
            "decoded": json.loads(text),
            "native_payload": native,
            "native_text": text,
            "roundtrip_ms": elapsed,
        }

    def search(
        self,
        query: str,
        project: str | None = None,
        limit: int = 5,
        preview_chars: int = 200,
    ) -> dict[str, Any]:
        if self.retrieval == "hybrid":
            return self.search_mcp(query, project, limit, preview_chars)
        return self.search_fts(query, project, limit, preview_chars)

    def search_fts(
        self,
        query: str,
        project: str | None = None,
        limit: int = 5,
        preview_chars: int = 200,
    ) -> dict[str, Any]:
        """Native results and parallel stable ids; native snippet length is fixed.

        preview_chars is accepted for the common adapter signature but cannot
        change the upstream API. Metadata records the native snippet behavior.
        """
        if limit < 1:
            raise ValueError("limit must be positive")
        params: dict[str, Any] = {"q": query, "limit": limit}
        if project is not None:
            params.update(workspace=self._workspace, project=project)
        native, elapsed = self._request("GET", "/admin/search", query=params)
        return {
            "results": native,
            "hit_ids": [self._by_page_id.get(hit.get("id")) for hit in native],
            "search_ms": elapsed,
            "bridge_ms": elapsed,
            "latency_scope": "native HTTP roundtrip, not isolated SQL time",
            "preview_policy": "native FTS5 snippet, unmodified",
        }

    def search_mcp(
        self,
        query: str,
        project: str | None = None,
        limit: int = 5,
        preview_chars: int = 200,
        *,
        explain: bool = False,
    ) -> dict[str, Any]:
        """Call native memory_query, with its shipped stream fusion unchanged."""
        if limit < 1:
            raise ValueError("limit must be positive")
        args: dict[str, Any] = {"query": query, "limit": limit}
        if project is None:
            # Global retrieval is FTS-only in upstream, even with local
            # embeddings enabled. Do not silently substitute a different API.
            args["global"] = True
        else:
            args.update(workspace=self._workspace, project=project)
        if explain:
            args["explain"] = True
        response = self._mcp_call("memory_query", args)
        native = response["decoded"]
        hits = native.get("hits", [])
        return {
            "results": hits,
            "hit_ids": [self._by_page_id.get(hit.get("id")) for hit in hits],
            "native_payload": response["native_payload"],
            "native_text": response["native_text"],
            "decoded_native": native,
            "search_ms": response["roundtrip_ms"],
            "bridge_ms": response["roundtrip_ms"],
            "latency_scope": "native MCP HTTP roundtrip, not isolated retrieval time",
            "preview_policy": "native memory_query snippets, unmodified",
            "global_fts_only": project is None,
        }

    def read(self, document_id: str) -> dict[str, Any]:
        """Fetch the actual native page body; count this payload when consumed."""
        project, path = self._locations[document_id]
        if self.retrieval == "hybrid":
            response = self._mcp_call("memory_read_page", {
                "workspace": self._workspace, "project": project, "path": path,
            })
            return {
                "result": response["decoded"],
                "native_payload": response["native_payload"],
                "native_text": response["native_text"],
                "read_ms": response["roundtrip_ms"],
            }
        native, elapsed = self._request("GET", "/admin/read-page", query={
            "workspace": self._workspace, "project": project, "path": path,
        })
        return {"result": native, "read_ms": elapsed}

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        if self._connection:
            self._connection.close()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._log.close()
        self._temporary.cleanup()

    def __enter__(self) -> "AiMemoryNative":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--retrieval", choices=("fts", "hybrid"), default="fts")
    args = parser.parse_args()
    bundle = json.loads(args.input.read_text(encoding="utf-8"))
    with AiMemoryNative(
        bundle["documents"], args.cache, offline=args.offline, retrieval=args.retrieval
    ) as engine:
        rows = []
        for query in bundle["queries"]:
            row = {
                "query_id": query["id"],
                **engine.search(query["query"], query.get("project"), args.limit),
            }
            row["native_reads"] = [
                {"document_id": identity, **engine.read(identity)}
                for identity in row["hit_ids"] if identity is not None
            ]
            rows.append(row)
        result = {"metadata": engine.metadata, "queries": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
