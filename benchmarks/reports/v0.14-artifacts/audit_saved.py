#!/usr/bin/env python3
"""Run the unchanged frozen offline auditor against relocated v0.14 evidence.

    python audit_saved.py --repo /path/to/frozen-repo \
        --run /path/to/restored/v014-formal-attempt1 \
        --output /path/to/new-relocated-audit.json

Only copied manifest snapshot paths are relocated. The original manifest,
binding, response journals and runtime identities remain unchanged. The output
is the original auditor's JSON result; OUTPUT.relocation.json records all path
substitutions, original hashes, evaluator verification and the absence of new
retrieval. A temporary view links only entries within the saved run. Compressed
SQLite snapshots are materialized by the original auditor, so the temporary
filesystem needs at least 2 GiB free, or more when the registered concurrent
snapshot sizes plus the evaluator's 1 GB reserve require it.

This is an offline integrity/source audit, not a new retrieval measurement or an
independent quality benchmark. It does not load MemoryBook or replay queries.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import types


CHUNK_BYTES = 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PROTOCOL = "v014-paired-long-history-1"
FROZEN = (
    "benchmarks/v014_scale.py", "benchmarks/v014_workload.py", "benchmarks/v014_audit.py",
    "benchmarks/experiments/v014-long-history-plan.json", "tests/test_v014_scale.py",
    "benchmarks/v013_scale.py", "benchmarks/v013_workload.py",
)
MODULE_ORDER = (
    "benchmarks.v013_workload", "benchmarks.v014_workload", "benchmarks.v013_scale",
    "benchmarks.v014_scale", "benchmarks.v014_audit",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError(f"Invalid relative evidence path: {value!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"Control character in evidence path: {value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise ValueError(f"Evidence path is not canonical and relative: {value!r}")
    return parts


def regular_file(path):
    information = path.lstat()
    if not stat.S_ISREG(information.st_mode):
        raise ValueError(f"Expected a regular file without a symlink: {path}")
    return information


def read_json(path):
    regular_file(path)
    content = path.read_bytes()
    return json.loads(content.decode("utf-8"), object_pairs_hook=unique_object), hashlib.sha256(content).hexdigest()


def file_sha(path):
    regular_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as incoming:
        for chunk in iter(lambda: incoming.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fresh_json(path, value):
    # Exclusive creation is intentional: completed and failed attempts are never
    # silently replaced. A filesystem failure may leave a partial new output.
    with path.open("xb") as output:
        output.write(encoded(value))
        output.flush()
        os.fsync(output.fileno())


def evaluator_sources(repo, binding):
    identity = binding.get("evaluator", {})
    registered = identity.get("files", {})
    if identity.get("protocol") != PROTOCOL or set(registered) != set(FROZEN):
        raise ValueError("The run does not bind the complete frozen v0.14 evaluator file set")
    content, actual = {}, {}
    for relative in FROZEN:
        expected = registered[relative]
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise ValueError(f"Invalid evaluator hash: {relative}")
        parts = safe_relative(relative)
        path = repo.joinpath(*parts)
        if path.resolve(strict=True) != path:
            raise ValueError(f"Evaluator paths must not traverse symlinks: {relative}")
        regular_file(path)
        source = path.read_bytes()
        actual[relative] = hashlib.sha256(source).hexdigest()
        if actual[relative] != expected:
            raise ValueError(f"Repository evaluator differs from the original run binding: {relative}")
        content[relative] = source
    return content, {"protocol": PROTOCOL, "files": actual}


def validate_run_tree(run):
    """Do not expose a linked directory containing outward links or special files."""
    count = 0
    for directory, children, files in os.walk(run, followlinks=False):
        for name in children + files:
            path = Path(directory) / name
            information = path.lstat()
            if not (stat.S_ISREG(information.st_mode) or stat.S_ISDIR(information.st_mode)):
                raise ValueError(f"Saved run contains a symlink or special entry: {path}")
            count += int(stat.S_ISREG(information.st_mode))
    return count


def relocated_manifest(run, original):
    if original.get("status") != "completed":
        raise ValueError("Only a completed, immutable saved run can be audited")
    stages = original.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("The original manifest contains no stages")
    patched, mappings, snapshots = copy.deepcopy(original), [], {}
    for stage, target in zip(stages, patched["stages"]):
        snapshot = stage["snapshot"]
        old_path = snapshot["path"]
        if not isinstance(old_path, str) or not Path(old_path).is_absolute():
            raise ValueError("Original snapshot paths must be absolute")
        basename = Path(old_path).name
        safe_relative(basename)
        destination = run / "snapshots" / basename
        if destination.resolve(strict=True) != destination:
            raise ValueError(f"Relocated snapshot traverses a link: {destination}")
        information = regular_file(destination)
        if type(snapshot["bytes"]) is not int or information.st_size != snapshot["bytes"]:
            raise ValueError(f"Relocated snapshot size differs: {destination}")
        expected_sha = snapshot["sha256"]
        if not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
            raise ValueError(f"Invalid snapshot hash: {basename}")
        previous = snapshots.setdefault(basename, (expected_sha, snapshot["bytes"]))
        if previous != (expected_sha, snapshot["bytes"]):
            raise ValueError(f"Distinct snapshots collide at the same basename: {basename}")
        target["snapshot"]["path"] = str(destination)
        mappings.append({"stage": stage["spec"]["id"], "original_path": old_path,
                         "relocated_path": str(destination), "sha256": expected_sha,
                         "bytes": snapshot["bytes"]})
        for block in stage["measurements"]:
            components = safe_relative(block["output"])
            folder = run.joinpath(*components)
            if not folder.is_dir() or folder.resolve(strict=True) != folder:
                raise ValueError(f"Measurement directory is missing or traverses a link: {folder}")
    # Assert explicitly that there are no other manifest changes.
    restored = copy.deepcopy(patched)
    for old, new in zip(original["stages"], restored["stages"]):
        new["snapshot"]["path"] = old["snapshot"]["path"]
    if restored != original:
        raise AssertionError("Relocation altered fields other than snapshot paths")
    return patched, mappings


def required_temporary_bytes(manifest):
    by_id = {stage["spec"]["id"]: stage for stage in manifest["stages"]}
    if len(by_id) != len(manifest["stages"]):
        raise ValueError("Duplicate stage identifiers")

    def materialized_bytes(stage):
        snapshot = stage["snapshot"]
        encoding = snapshot.get("encoding", "raw")
        if encoding not in {"raw", "gzip"}:
            raise ValueError(f"Unknown snapshot encoding: {encoding}")
        size = snapshot.get("database_bytes", snapshot["bytes"])
        if type(size) is not int or size < 0:
            raise ValueError("Invalid registered materialized snapshot size")
        return size if encoding == "gzip" else 0

    peak = 0
    for stage in manifest["stages"]:
        needed = materialized_bytes(stage)
        if stage["spec"]["axis"] in {"source_replacement", "source_deletion"}:
            needed += materialized_bytes(by_id[stage["spec"]["parent"]])
        peak = max(peak, needed)
    minimum = max(2 * 1024 ** 3, peak + 1_000_000_000 + 64 * 1024 * 1024)
    return {"peak_concurrent_materialized_snapshot_bytes": peak,
            "required_free_bytes": minimum,
            "frozen_evaluator_reserve_bytes": 1_000_000_000}


class OfflineImports:
    """Refuse runtime imports and unbound benchmark modules during the audit."""

    def __init__(self):
        self.blocked = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "memory_book" or fullname.startswith("memory_book.") or fullname.startswith("benchmarks."):
            self.blocked.append(fullname)
            raise ImportError(f"Offline audit prohibits an unbound module or retrieval runtime import: {fullname}")
        return None


def load_frozen_auditor(repo, sources):
    # Source bytes are already hash checked. Loading those exact bytes avoids
    # stale .pyc files and executing an unbound benchmarks/__init__.py. Module
    # bodies and audit() remain byte-for-byte the registered implementation.
    if any(name == "benchmarks" or name.startswith("benchmarks.")
           or name == "memory_book" or name.startswith("memory_book.") for name in sys.modules):
        raise ValueError("Run audit_saved.py in a fresh Python process")
    guard = OfflineImports()
    sys.meta_path.insert(0, guard)
    package = types.ModuleType("benchmarks")
    package.__package__, package.__path__ = "benchmarks", [str(repo / "benchmarks")]
    sys.modules["benchmarks"] = package
    for name in MODULE_ORDER:
        relative = name.replace(".", "/") + ".py"
        module = types.ModuleType(name)
        module.__file__, module.__package__ = str(repo / relative), "benchmarks"
        sys.modules[name] = module
        setattr(package, name.rsplit(".", 1)[1], module)
        exec(compile(sources[relative], module.__file__, "exec"), module.__dict__)
    return sys.modules["benchmarks.v014_audit"], guard


def audit_saved(repo, run, output, work_dir):
    relocation_output = Path(str(output) + ".relocation.json")
    for path in (output, relocation_output):
        if os.path.lexists(path):
            raise FileExistsError(f"Evidence output already exists: {path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"Output parent does not exist: {path.parent}")
    if work_dir == run or run in work_dir.parents:
        raise ValueError("The temporary work directory must be outside the immutable saved run")
    if not work_dir.is_dir():
        raise FileNotFoundError(f"Temporary work directory does not exist: {work_dir}")
    binding, binding_sha = read_json(run / "binding.json")
    original, manifest_sha = read_json(run / "manifest.json")
    sources, verified_before = evaluator_sources(repo, binding)
    run_files = validate_run_tree(run)
    patched, mappings = relocated_manifest(run, original)
    space = required_temporary_bytes(patched)
    free_bytes = shutil.disk_usage(work_dir).free
    if free_bytes < space["required_free_bytes"]:
        raise ValueError(f"Offline audit needs {space['required_free_bytes']} free bytes on {work_dir}; available {free_bytes}")
    provenance = {
        "type": "v014-saved-evidence-relocation", "status": "started", "started_at": now(),
        "repo": str(repo), "run": str(run), "audit_output": str(output),
        "original_manifest_sha256": manifest_sha, "original_binding_sha256": binding_sha,
        "relocated_manifest_sha256": hashlib.sha256(encoded(patched)).hexdigest(),
        "manifest_changes": "Only stages[*].snapshot.path in a temporary copy",
        "snapshot_path_substitutions": mappings, "evaluator_before": verified_before,
        "run_regular_files": run_files, "space": {**space, "available_before_bytes": free_bytes},
        "new_retrieval_calls": 0, "retrieval_runtime_import_prohibited": True,
        "scope": "Unchanged frozen offline audit of saved responses and original source snapshots; no new quality measurements",
    }
    result, failure, guard = None, None, None
    try:
        auditor, guard = load_frozen_auditor(repo, sources)
        if auditor.scale.protocol_identity() != binding["evaluator"]:
            raise ValueError("Loaded frozen evaluator identity differs from the original binding")
        with tempfile.TemporaryDirectory(prefix="v014-relocated-audit-", dir=work_dir) as temporary:
            view = Path(temporary)
            for source in sorted(run.iterdir()):
                if source.name != "manifest.json":
                    (view / source.name).symlink_to(source, target_is_directory=source.is_dir())
            fresh_json(view / "manifest.json", patched)
            result = auditor.audit(view)
        provenance["temporary_view_removed"] = True
    except Exception as exc:
        failure = exc
        provenance["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    try:
        _, verified_after = evaluator_sources(repo, binding)
        provenance["evaluator_after"] = verified_after
        provenance["original_manifest_sha256_after"] = file_sha(run / "manifest.json")
        provenance["original_binding_sha256_after"] = file_sha(run / "binding.json")
        if (verified_before != verified_after or provenance["original_manifest_sha256_after"] != manifest_sha
                or provenance["original_binding_sha256_after"] != binding_sha):
            raise ValueError("Evaluator, original manifest or original binding changed during the offline audit")
    except Exception as exc:
        failure = failure or exc
        provenance["post_audit_verification_failure"] = {"type": type(exc).__name__, "message": str(exc)}
    provenance["blocked_import_attempts"] = guard.blocked if guard is not None else []
    provenance["finished_at"] = now()
    provenance["status"] = "failed" if failure else "completed"
    if failure:
        fresh_json(relocation_output, provenance)
        raise failure
    fresh_json(output, result)
    provenance["audit_output_sha256"] = file_sha(output)
    provenance["integrity_pass"] = bool(result.get("integrity_pass"))
    provenance["safety_and_quality_pass"] = bool(result.get("safety_and_quality_pass"))
    fresh_json(relocation_output, provenance)
    return result, relocation_output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, required=True, help="Repository with evaluator bytes matching binding.json")
    parser.add_argument("--run", type=Path, required=True, help="Restored completed v014 formal run directory")
    parser.add_argument("--output", type=Path, required=True, help="Fresh audit JSON; a .relocation.json sidecar is also created")
    parser.add_argument("--work-dir", type=Path, help="Temporary view/snapshot parent, defaults to the output parent")
    args = parser.parse_args(argv)
    try:
        repo, run = args.repo.expanduser().resolve(strict=True), args.run.expanduser().resolve(strict=True)
        supplied_output = args.output.expanduser().absolute()
        output = supplied_output.parent.resolve(strict=True) / supplied_output.name
        work_dir = (args.work_dir.expanduser().resolve(strict=True) if args.work_dir else output.parent)
        result, relocation = audit_saved(repo, run, output, work_dir)
        print(json.dumps({"status": "completed", "audit": str(output), "relocation": str(relocation),
                          "integrity_pass": result.get("integrity_pass"),
                          "safety_and_quality_pass": result.get("safety_and_quality_pass"),
                          "observations_audited": result.get("observations_audited"),
                          "new_retrieval_calls": 0}, indent=2))
        return 0 if result.get("integrity_pass") else 2
    except Exception as exc:
        print(f"Saved-evidence audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
