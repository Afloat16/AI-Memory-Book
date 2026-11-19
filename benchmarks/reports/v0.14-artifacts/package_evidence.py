"""Package an explicit evidence selection; restoration uses restore.py.

This authoring utility does not execute the selected programs or query a book.
Run after every selected experiment and review has stopped writing evidence.
The selection JSON contains roots and files as [source, archive_path] pairs.
Sources are relative to --workspace; archive paths are relative POSIX names.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


CHUNK = 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value):
    path = PurePosixPath(value)
    if (path.is_absolute() or not path.parts or ".." in path.parts
            or "\\" in value or path.as_posix() != value):
        raise ValueError(f"Unsafe archive name: {value!r}")
    return value


def package(args):
    workspace = Path(args.workspace).resolve()
    selection = json.loads(Path(args.selection).read_text())
    output = Path(args.output).resolve()
    archive = Path(args.archive).resolve()
    if archive.exists() or (output / "manifest.json").exists():
        raise FileExistsError("Use a new archive and an unpublished manifest destination")
    selected, excluded = {}, []

    def add(source, name):
        source = source.resolve()
        if not source.is_relative_to(workspace) or not source.is_file():
            raise ValueError(f"Missing or out-of-workspace selected file: {source}")
        name = safe_name(name)
        if name in selected:
            raise ValueError(f"Duplicate archive name: {name}")
        selected[name] = source

    for source_name, archive_name in selection.get("roots", []):
        root = (workspace / source_name).resolve()
        if not root.is_relative_to(workspace) or not root.is_dir():
            raise ValueError(f"Invalid selected root: {root}")
        for source in sorted(root.rglob("*")):
            if source.is_symlink():
                raise ValueError(f"Evidence selection contains a symlink: {source}")
            if not source.is_file():
                continue
            relative = source.relative_to(root)
            name = safe_name((PurePosixPath(archive_name) / relative.as_posix()).as_posix())
            reason = None
            if "__pycache__" in relative.parts or source.suffix in {".pyc", ".pyo"}:
                reason = "Reproducible interpreter cache, not an original measurement record."
            if len(relative.parts) == 1 and source.name in {
                    "working.sqlite", "working.sqlite-wal", "working.sqlite-shm"}:
                reason = "Mutable worker scratch database; every immutable stage snapshot is retained."
            if reason:
                excluded.append({"path": name, "bytes": source.stat().st_size, "reason": reason})
            else:
                add(source, name)
    for source_name, archive_name in selection.get("files", []):
        add(workspace / source_name, archive_name)

    files = [{"path": name, "bytes": source.stat().st_size, "sha256": sha256(source)}
             for name, source in sorted(selected.items())]
    if not files:
        raise ValueError("Empty evidence selection")
    archive.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with archive.open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for record in files:
                    source = selected[record["path"]]
                    member = tarfile.TarInfo(record["path"])
                    member.size = record["bytes"]
                    member.mode = 0o644
                    member.mtime = 0
                    with source.open("rb") as stream:
                        tar.addfile(member, stream)
                    if source.stat().st_size != record["bytes"] or sha256(source) != record["sha256"]:
                        raise ValueError(f"Evidence changed during packaging: {source}")

    parts = []
    with archive.open("rb") as stream:
        index = 1
        while chunk := stream.read(args.part_bytes):
            name = f"v014-evidence.tar.gz.part{index:03d}"
            path = output / name
            with path.open("xb") as target:
                target.write(chunk)
            parts.append({"path": name, "bytes": len(chunk),
                          "sha256": hashlib.sha256(chunk).hexdigest(),
                          "git_blob_sha": hashlib.sha1(b"blob " + str(len(chunk)).encode() + b"\0" + chunk).hexdigest()})
            index += 1
    manifest = {
        "format": "v014-evidence-archive-1",
        "archive": {"format": "tar.gz", "bytes": archive.stat().st_size, "sha256": sha256(archive)},
        "parts": parts, "files": files, "excluded": excluded,
        "selection": selection,
        "note": "Original payloads, failed attempts, source snapshots and provenance are retained byte for byte. Extraction performs a second full per-file verification; records must not be relabelled as different source commits.",
    }
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"archive_bytes": manifest["archive"]["bytes"], "archive_sha256": manifest["archive"]["sha256"],
                      "parts": len(parts), "files": len(files), "excluded": len(excluded)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--part-bytes", type=int, default=4 * 1024 * 1024)
    arguments = parser.parse_args()
    if arguments.part_bytes <= 0:
        parser.error("--part-bytes must be positive")
    package(arguments)
