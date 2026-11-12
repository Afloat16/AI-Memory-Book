"""Download and verify the public artifacts pinned by the local answer plan.

This prepares a keyless local model; it does not start a server or run answers.
Model weights and binaries are cached under ignored .artifacts by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/local-answer-plan.json"


def verified(path: Path, entry: dict) -> bool:
    if not path.is_file() or path.stat().st_size != entry["bytes"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == entry["sha256"]


def download(url: str, path: Path, entry: dict) -> None:
    if verified(path, entry):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Memory-Book-reproducible-evaluation"})
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > entry["bytes"]:
                raise ValueError("Download exceeds pinned size")
            digest.update(block)
            output.write(block)
    if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
        raise ValueError(f"Artifact integrity mismatch: {path.name}")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".artifacts/local-answer")
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    model, server = plan["model"], plan["server"]
    cache = args.cache.resolve()
    archive = cache / server["asset"]
    model_path = cache / model["file"]
    download(f'https://github.com/{server["repository"]}/releases/download/{server["tag"]}/{server["asset"]}', archive, server)
    download(f'https://huggingface.co/{model["repository"]}/resolve/{model["revision"]}/{model["file"]}', model_path, model)
    binary_root = cache / server["tag"]
    binary_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as source:
        # Python's data filter rejects path traversal, links outside the
        # destination and special devices. The archive digest is checked first.
        source.extractall(binary_root, filter="data")
    servers = list(binary_root.rglob("llama-server"))
    if len(servers) != 1 or not servers[0].is_file():
        raise ValueError("Expected exactly one extracted llama-server executable")
    print(json.dumps({"model": str(model_path), "server": str(servers[0]),
                      "model_sha256": model["sha256"], "archive_sha256": server["sha256"]}))


if __name__ == "__main__":
    main()
