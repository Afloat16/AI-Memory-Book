#!/usr/bin/env python3
"""Authenticate and restore the split v0.14 evidence archive without executing it.

    python restore.py --manifest manifest.json --output /path/to/fresh-directory

The manifest lists an archive SHA-256/size, ordered sibling parts, and every
regular file expected inside the tar.gz. All parts and the complete compressed
archive are authenticated before the destination is created. Extraction uses
streaming reads, exclusive file creation, and no tarfile.extract()/extractall().
Archive ownership, permissions, timestamps, links and executable code are never
applied. A failed extraction leaves its fresh, incomplete destination in place;
retry with another new destination after resolving the reported error.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile


CHUNK_BYTES = 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def safe_path(value, *, sibling=False):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        raise ValueError(f"Invalid artifact path: {value!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"Control character in artifact path: {value!r}")
    if "\\" in value or ":" in value:
        raise ValueError(f"Non-portable artifact path: {value!r}")
    components = value.split("/")
    if any(part in {"", ".", ".."} for part in components):
        raise ValueError(f"Non-canonical artifact path: {value!r}")
    if any(len(part.encode("utf-8")) > 255 for part in components):
        raise ValueError(f"Artifact path component is too long: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or (sibling and len(components) != 1):
        raise ValueError(f"Artifact path is outside its permitted directory: {value!r}")
    return components


def checked_size(value, description):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid nonnegative byte count for {description}")
    return value


def checked_hash(value, description):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"Invalid SHA-256 for {description}")
    return value


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def regular_input(path):
    # O_NONBLOCK lets fstat reject a substituted FIFO instead of waiting for a
    # writer before the regular-file check can run. It is inert for normal files.
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    if path.is_symlink():
        raise ValueError(f"Artifact input must not be a symlink: {path}")
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Artifact input is not a regular file: {path}")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            yield stream, info
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_manifest(path):
    with regular_input(path) as (incoming, _):
        content = incoming.read()
    manifest = json.loads(content.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")
    archive = manifest.get("archive")
    parts, files = manifest.get("parts"), manifest.get("files")
    if not isinstance(archive, dict):
        raise ValueError("Manifest has no archive object")
    checked_size(archive.get("bytes"), "archive")
    checked_hash(archive.get("sha256"), "archive")
    if not isinstance(parts, list) or not parts or not isinstance(files, list) or not files:
        raise ValueError("Manifest must list at least one part and one regular file")
    if not isinstance(manifest.get("excluded", []), list):
        raise ValueError("Manifest excluded field must be a list")
    for items, kind in ((parts, "part"), (files, "file")):
        names = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"Invalid {kind} inventory record")
            safe_path(item.get("path"), sibling=kind == "part")
            if item["path"] in names:
                raise ValueError(f"Duplicate {kind} path: {item['path']}")
            names.add(item["path"])
            checked_size(item.get("bytes"), item["path"])
            checked_hash(item.get("sha256"), item["path"])
            if kind == "part" and item["bytes"] == 0:
                raise ValueError("An archive part must not be empty")
        if kind == "file":
            for name in names:
                components = safe_path(name)
                for index in range(1, len(components)):
                    if "/".join(components[:index]) in names:
                        raise ValueError(f"File/directory path collision: {name}")
    if sum(part["bytes"] for part in parts) != archive["bytes"]:
        raise ValueError("Part byte counts do not sum to the archive byte count")
    return manifest, hashlib.sha256(content).hexdigest()


def verify_parts(manifest, directory):
    """Complete the first authentication pass before making an output directory."""
    combined, total, identities = hashlib.sha256(), 0, []
    for part in manifest["parts"]:
        actual, count = hashlib.sha256(), 0
        with regular_input(directory / part["path"]) as (incoming, before):
            if before.st_size != part["bytes"]:
                raise ValueError(f"Part size differs: {part['path']}")
            for chunk in iter(lambda: incoming.read(CHUNK_BYTES), b""):
                actual.update(chunk)
                combined.update(chunk)
                count += len(chunk)
                total += len(chunk)
            after = os.fstat(incoming.fileno())
            if file_identity(before) != file_identity(after):
                raise ValueError(f"Part changed during authentication: {part['path']}")
        if count != part["bytes"] or actual.hexdigest() != part["sha256"]:
            raise ValueError(f"Part SHA-256 or size differs: {part['path']}")
        identities.append(file_identity(before))
    if total != manifest["archive"]["bytes"] or combined.hexdigest() != manifest["archive"]["sha256"]:
        raise ValueError("Concatenated archive SHA-256 or size differs")
    return identities


class PartStream(io.RawIOBase):
    """Concatenate verified parts and authenticate them again while consuming."""

    def __init__(self, directory, parts, identities):
        super().__init__()
        self.directory, self.parts, self.identities = directory, parts, identities
        self.index, self.incoming, self.manager = 0, None, None
        self.part_sha, self.part_bytes = None, 0
        self.archive_sha, self.archive_bytes = hashlib.sha256(), 0

    def readable(self):
        return True

    def readinto(self, target):
        if not target:
            return 0
        while self.index < len(self.parts):
            part = self.parts[self.index]
            if self.incoming is None:
                self.manager = regular_input(self.directory / part["path"])
                self.incoming, before = self.manager.__enter__()
                if file_identity(before) != self.identities[self.index]:
                    raise ValueError(f"Part changed after initial verification: {part['path']}")
                self.part_sha, self.part_bytes = hashlib.sha256(), 0
            chunk = self.incoming.read(len(target))
            if chunk:
                target[:len(chunk)] = chunk
                self.part_sha.update(chunk)
                self.archive_sha.update(chunk)
                self.part_bytes += len(chunk)
                self.archive_bytes += len(chunk)
                if self.part_bytes > part["bytes"]:
                    raise ValueError(f"Part grew during extraction: {part['path']}")
                return len(chunk)
            after = os.fstat(self.incoming.fileno())
            if (self.part_bytes != part["bytes"] or self.part_sha.hexdigest() != part["sha256"]
                    or file_identity(after) != self.identities[self.index]):
                raise ValueError(f"Part changed during extraction: {part['path']}")
            self.manager.__exit__(None, None, None)
            self.manager, self.incoming = None, None
            self.index += 1
        return 0

    def assert_complete(self, expected):
        if (self.index != len(self.parts) or self.archive_bytes != expected["bytes"]
                or self.archive_sha.hexdigest() != expected["sha256"]):
            raise ValueError("Archive was not consumed and authenticated in full")

    def close(self):
        if self.manager is not None:
            self.manager.__exit__(None, None, None)
            self.manager, self.incoming = None, None
        super().close()


class LimitedTarStream:
    """Bound decompressed bytes, including otherwise hidden tar metadata/padding."""

    def __init__(self, incoming, limit):
        self.incoming, self.remaining = incoming, limit

    def read(self, size=-1):
        request = self.remaining + 1 if size < 0 else min(size, self.remaining + 1)
        result = self.incoming.read(request)
        self.remaining -= len(result)
        if self.remaining < 0:
            raise ValueError("Decompressed tar exceeds its inventory-derived byte limit")
        return result


@contextmanager
def new_file(root_descriptor, components):
    """Create beneath the fresh directory without following any link components."""
    parent = os.dup(root_descriptor)
    try:
        for component in components[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        descriptor = os.open(components[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as output:
            yield output
    finally:
        os.close(parent)


def extract(manifest, directory, output, identities):
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("Secure restoration requires POSIX O_NOFOLLOW and directory descriptors")
    expected = {item["path"]: item for item in manifest["files"]}
    total_file_bytes = sum(item["bytes"] for item in expected.values())
    if shutil.disk_usage(output.parent).free < total_file_bytes + 64 * 1024 * 1024:
        raise ValueError("Insufficient free space for the registered files and a 64 MiB reserve")
    output.mkdir(mode=0o700, exist_ok=False)
    root_descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    # Allow normal PAX/GNU name metadata and standard record padding, while
    # bounding malformed or oversized hidden headers before tarfile parses them.
    tar_limit = (sum(((item["bytes"] + 511) // 512) * 512 for item in expected.values())
                 + len(expected) * (512 + 16384) + 1024 * 1024)
    seen = set()
    try:
        with PartStream(directory, manifest["parts"], identities) as raw:
            with io.BufferedReader(raw, CHUNK_BYTES) as compressed:
                with gzip.GzipFile(fileobj=compressed, mode="rb") as uncompressed:
                    bounded = LimitedTarStream(uncompressed, tar_limit)
                    with tarfile.open(fileobj=bounded, mode="r|", bufsize=65536) as archive:
                        for member in archive:
                            components = safe_path(member.name)
                            if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE} or member.issparse():
                                raise ValueError(f"Archive member is not an ordinary regular file: {member.name}")
                            if member.name not in expected or member.name in seen:
                                raise ValueError(f"Unexpected or duplicate archive member: {member.name}")
                            registered = expected[member.name]
                            if member.size != registered["bytes"]:
                                raise ValueError(f"Tar member size differs: {member.name}")
                            incoming = archive.extractfile(member)
                            if incoming is None:
                                raise ValueError(f"Tar member has no byte stream: {member.name}")
                            digest, written = hashlib.sha256(), 0
                            with incoming, new_file(root_descriptor, components) as destination:
                                for chunk in iter(lambda: incoming.read(CHUNK_BYTES), b""):
                                    written += len(chunk)
                                    if written > registered["bytes"]:
                                        raise ValueError(f"Tar member exceeds its registered size: {member.name}")
                                    destination.write(chunk)
                                    digest.update(chunk)
                                destination.flush()
                                os.fsync(destination.fileno())
                            if written != registered["bytes"] or digest.hexdigest() != registered["sha256"]:
                                raise ValueError(f"Restored file SHA-256 or size differs: {member.name}")
                            seen.add(member.name)
                        # Drain tarfile's own read-ahead buffer as well as gzip.
                        # This validates gzip trailers and rejects a hidden second
                        # tar archive or other nonzero data after the end marker.
                        for tail in iter(lambda: archive.fileobj.read(CHUNK_BYTES), b""):
                            if any(tail):
                                raise ValueError("Nonzero data follows the tar end marker")
                    if compressed.read(1):
                        raise ValueError("Unconsumed compressed archive data")
            raw.assert_complete(manifest["archive"])
        if seen != set(expected):
            missing = sorted(set(expected) - seen)
            raise ValueError(f"Archive is missing registered files: {missing[:10]}")
    finally:
        os.close(root_descriptor)
    return len(seen), total_file_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("manifest.json"))
    parser.add_argument("--output", type=Path, required=True, help="New directory; even an empty existing directory is refused")
    args = parser.parse_args(argv)
    try:
        supplied_manifest = args.manifest.expanduser().absolute()
        manifest, manifest_sha = read_manifest(supplied_manifest)
        directory = supplied_manifest.parent.resolve(strict=True)
        supplied_output = args.output.expanduser().absolute()
        if os.path.lexists(supplied_output):
            raise FileExistsError(f"Restoration requires a fresh destination: {supplied_output}")
        output = supplied_output.parent.resolve(strict=True) / supplied_output.name
        identities = verify_parts(manifest, directory)
        count, byte_count = extract(manifest, directory, output, identities)
        print(json.dumps({"status": "verified_and_restored", "output": str(output),
                          "manifest_sha256": manifest_sha, "archive": manifest["archive"],
                          "parts_verified": len(manifest["parts"]), "files_verified": count,
                          "file_bytes": byte_count, "archive_code_executed": False}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, EOFError, tarfile.TarError) as exc:
        print(f"Restore failed: {exc}\nAny fresh destination already created is incomplete; it was not overwritten or removed.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
