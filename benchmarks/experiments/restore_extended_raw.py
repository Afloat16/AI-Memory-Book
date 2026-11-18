"""Verify and restore the v0.11 gzip evidence bundle into a new directory.

Only Python's standard library is used. Every compressed and original byte
digest is verified before creating an output directory. Existing output paths,
symlinked source paths and paths escaping the bundle are rejected. This helper
does not modify the frozen benchmark evaluator or interpret its quality scores.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat


FORMAT = "memory-book-raw-gzip-v1"
CHUNK = 1024 * 1024


def relative_path(value):
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise ValueError("Manifest paths must be relative POSIX paths without drive or stream syntax")
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/"))
            or path.as_posix() != value):
        raise ValueError(f"Unsafe manifest path: {value!r}")
    return path


def source_file(root, value):
    path = root
    parts = relative_path(value).parts
    for index, part in enumerate(parts):
        path = path / part
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"Symlinked source path: {value}")
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            raise ValueError(f"Non-directory source parent: {value}")
    if not stat.S_ISREG(mode) or not path.resolve().is_relative_to(root):
        raise ValueError(f"Source is not a regular file in the bundle: {value}")
    return path


def identity_fields(size, digest):
    if type(size) is not int or size < 0 or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid byte count or SHA-256 in manifest")


def verify_stream(stream, size, digest, sink=None):
    identity_fields(size, digest)
    actual_size, actual_hash = 0, hashlib.sha256()
    while chunk := stream.read(CHUNK):
        actual_size += len(chunk)
        if actual_size > size:
            raise ValueError("Stream exceeds its recorded original byte count")
        actual_hash.update(chunk)
        if sink is not None:
            sink.write(chunk)
    if actual_size != size or actual_hash.hexdigest() != digest:
        raise ValueError("Stream byte count or SHA-256 differs from manifest")


def verify_file(path, size, digest):
    with path.open("rb") as stream:
        verify_stream(stream, size, digest)


def verify_bundle(manifest_path):
    manifest_path = Path(manifest_path).absolute()
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Manifest must be an existing regular file")
    root = manifest_path.parent.resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("format") != FORMAT:
        raise ValueError("Unsupported raw archive manifest format")
    if not isinstance(manifest.get("archives"), list) or not manifest["archives"]:
        raise ValueError("Manifest has no archives")
    if not isinstance(manifest.get("preserved_files"), list):
        raise ValueError("Manifest has no preserved-file inventory")
    used = {manifest_path.name}
    for entry in manifest["archives"]:
        for name in ("raw_path", "gzip_path"):
            relative_path(entry[name])
            if entry[name] in used:
                raise ValueError(f"Repeated output path: {entry[name]}")
            used.add(entry[name])
        compressed = source_file(root, entry["gzip_path"])
        verify_file(compressed, entry["gzip_bytes"], entry["gzip_sha256"])
        with gzip.open(compressed, "rb") as stream:
            verify_stream(stream, entry["raw_bytes"], entry["raw_sha256"])
    for entry in manifest["preserved_files"]:
        relative_path(entry["path"])
        if entry["path"] in used:
            raise ValueError(f"Repeated output path: {entry['path']}")
        used.add(entry["path"])
        verify_file(source_file(root, entry["path"]), entry["bytes"], entry["sha256"])
    return root, manifest, manifest_bytes


def restore(manifest_path, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Output path already exists; choose a new directory")
    root, manifest, manifest_bytes = verify_bundle(manifest_path)
    output.mkdir(parents=True, exist_ok=False)
    # Exclusive file creation also protects against accidental repeated writes.
    for entry in manifest["preserved_files"]:
        target = output / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with source_file(root, entry["path"]).open("rb") as source, target.open("xb") as sink:
            verify_stream(source, entry["bytes"], entry["sha256"], sink)
    for entry in manifest["archives"]:
        compressed_target = output / entry["gzip_path"]
        compressed_target.parent.mkdir(parents=True, exist_ok=True)
        with source_file(root, entry["gzip_path"]).open("rb") as source, compressed_target.open("xb") as sink:
            verify_stream(source, entry["gzip_bytes"], entry["gzip_sha256"], sink)
        target = output / entry["raw_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(compressed_target, "rb") as source, target.open("xb") as sink:
            verify_stream(source, entry["raw_bytes"], entry["raw_sha256"], sink)
    with (output / Path(manifest_path).name).open("xb") as sink:
        sink.write(manifest_bytes)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--verify-only", action="store_true")
    action.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.verify_only:
        _, manifest, _ = verify_bundle(args.manifest)
        status = "verified"
    else:
        manifest = restore(args.manifest, args.output)
        status = "restored_and_verified"
    print(json.dumps({"status": status, "archived_files": len(manifest["archives"]),
                      "raw_bytes": sum(entry["raw_bytes"] for entry in manifest["archives"]),
                      "gzip_bytes": sum(entry["gzip_bytes"] for entry in manifest["archives"]),
                      "preserved_files": len(manifest["preserved_files"])}, indent=2))


if __name__ == "__main__":
    main()
