"""Explicitly download and verify the registered local semantic model.

Only public model artifacts are downloaded. Runtime retrieval never invokes
this script and never downloads a model automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memory_book.semantic import MODEL_FILES, MODEL_REPOSITORY, MODEL_REVISION, verify_model_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/models/semantic")
    args = parser.parse_args()
    directory = args.output.expanduser().resolve()
    for entry in MODEL_FILES:
        target = directory / entry["path"]
        if target.is_file() and target.stat().st_size == entry["bytes"]:
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() == entry["sha256"]:
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        request = urllib.request.Request(
            f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{entry['path']}",
            headers={"User-Agent": "AI-Memory-Book-explicit-semantic-model-preparation"})
        size, digest = 0, hashlib.sha256()
        try:
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    size += len(block)
                    if size > entry["bytes"]:
                        raise ValueError("Semantic artifact exceeds its registered size")
                    digest.update(block)
                    stream.write(block)
            if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
                raise ValueError(f"Semantic artifact integrity mismatch: {entry['path']}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    identity = verify_model_files(directory)
    print(json.dumps({"directory": str(directory), "model": identity}, ensure_ascii=False))


if __name__ == "__main__":
    main()
