"""Run billion-context's real searchBlocks(), with pinned source integrity.

Only transport and input adaptation live here. Ranking, tokenization, document
feature caching, and previews execute upstream TypeScript after syntax erasure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, Iterable

from .download import fetch_bytes

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "billion-lock.json"


def _verify(data: bytes, entry: dict[str, Any]) -> None:
    blob = b"blob " + str(len(data)).encode() + b"\0" + data
    if (
        len(data) != entry["bytes"]
        or hashlib.sha256(data).hexdigest() != entry["sha256"]
        or hashlib.sha1(blob).hexdigest() != entry["git_blob_sha"]
    ):
        raise ValueError(f"Upstream integrity check failed: {entry['path']}")


def prepare(cache_dir: Path, *, node: str = "node", offline: bool = False) -> Path:
    """Fetch exact upstream files, verify them, then erase TypeScript syntax.

    cache_dir is the upstream source root. An existing connector-populated
    cache works offline; a normal internet-connected runner fetches missing
    files from raw.githubusercontent.com at the immutable commit.
    """
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    source_root = Path(cache_dir).resolve()
    source_root.mkdir(parents=True, exist_ok=True)
    for entry in lock["files"]:
        target = source_root / entry["path"]
        if target.exists():
            data = target.read_bytes()
        else:
            if offline:
                raise FileNotFoundError(f"Missing pinned source: {target}")
            url = (
                f"https://raw.githubusercontent.com/{lock['repository']}/"
                f"{lock['commit']}/{entry['path']}"
            )
            data = fetch_bytes(url, timeout=45)
            _verify(data, entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        _verify(data, entry)
    # Recreate generated JavaScript on every process setup: never trust a
    # stale or modified generated cache as an upstream implementation.
    output_root = source_root / ".memory-book-js"
    result = subprocess.run(
        [
            node,
            str(HERE / "compile_billion.mjs"),
            str(source_root),
            str(output_root),
            str(LOCK_PATH),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "Could not erase upstream TypeScript. Node 24+ is required.\n"
            + result.stderr[-8000:]
        )
    return output_root


class BillionKernel:
    """Persistent upstream search process; no model/API credentials required."""

    def __init__(
        self,
        documents: Iterable[dict[str, Any]],
        cache_dir: Path,
        node: str = "node",
        *,
        offline: bool = False,
        timeout: float = 60.0,
    ) -> None:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        docs = list(documents)
        ids: set[str] = set()
        for doc in docs:
            for key in ("id", "project", "title", "text"):
                if not isinstance(doc.get(key), str):
                    raise TypeError(f"Document {key} must be a string")
            if doc["id"] in ids:
                raise ValueError(f"Duplicate document id: {doc['id']}")
            ids.add(doc["id"])
        begin = time.perf_counter()
        compiled = prepare(Path(cache_dir), node=node, offline=offline)
        self._timeout = timeout
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._stderr: list[str] = []
        self._closed = False
        self._process = subprocess.Popen(
            [node, str(HERE / "billion_bridge.mjs"), str(compiled)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            initialized = self._request({
                "op": "init",
                "documents": [
                    {key: doc[key] for key in ("id", "project", "title", "text")}
                    for doc in docs
                ],
            })
        except Exception:
            self.close()
            raise
        self.metadata = {
            "name": "billion-context native search kernel",
            "repository": lock["repository"],
            "commit": lock["commit"],
            "source_url": lock["source_url"],
            "license": lock["license"],
            "source_manifest_sha256": hashlib.sha256(
                LOCK_PATH.read_bytes()
            ).hexdigest(),
            "implementation": "unchanged upstream TypeScript; Node syntax erasure",
            "comparison_scope": "shared-page lexical retrieval component",
            "document_kind": "message",
            "uniform_document_role": "assistant",
            "setup_ms": (time.perf_counter() - begin) * 1000,
            **initialized,
        }

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr.append(line)
            if len(self._stderr) > 100:
                del self._stderr[:50]

    def _request(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("billion-context adapter is closed")
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        try:
            line = self._responses.get(timeout=self._timeout)
        except queue.Empty as error:
            self.close()
            raise TimeoutError("billion-context subprocess did not respond") from error
        if line is None:
            raise RuntimeError("billion-context subprocess exited:\n" + "".join(self._stderr))
        result = json.loads(line)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def search(
        self,
        query: str,
        project: str | None = None,
        limit: int = 5,
        preview_chars: int = 200,
    ) -> dict[str, Any]:
        """Return native results unchanged, plus kernel and IPC timings."""
        if limit < 1 or preview_chars < 1:
            raise ValueError("limit and preview_chars must be positive")
        start = time.perf_counter()
        response = self._request({
            "op": "search",
            "query": query,
            "project": project,
            "limit": limit,
            "preview_chars": preview_chars,
        })
        response["bridge_ms"] = (time.perf_counter() - start) * 1000
        return response

    def clear_cache(self) -> None:
        """Clear only the upstream document-feature cache, for a labeled run."""
        self._request({"op": "clear_cache"})

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        process = self._process
        if process.stdin:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in (process.stdout, process.stderr):
            if stream:
                stream.close()

    def __enter__(self) -> "BillionKernel":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node", default="node")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    bundle = json.loads(args.input.read_text(encoding="utf-8"))
    with BillionKernel(
        bundle["documents"], args.cache, node=args.node, offline=args.offline
    ) as engine:
        rows = [
            {
                "query_id": query["id"],
                **engine.search(query["query"], query.get("project"), args.limit),
            }
            for query in bundle["queries"]
        ]
        result = {"metadata": engine.metadata, "queries": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
