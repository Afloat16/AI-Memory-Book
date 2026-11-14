"""Prepare engineering-agent trials without inventing model execution.

``prepare`` and ``inspect`` are usable offline. ``run`` deliberately fails
closed: this version has no verified hidden-test isolation/agent backend.
The reusable JSONL collector preserves unverified CLI events, not task scores.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

from benchmarks.resume import _lock


VERSION = "engineering-agent-preparation-1"
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_EVENT_BYTES = 8 * 1024 * 1024
BUDGET_FIELDS = {"wall_seconds", "model_calls", "tool_calls", "input_tokens", "output_tokens"}
SPEC_FIELDS = {"schema_version", "episode_id", "window_id", "project", "visible_until",
               "workspace_files", "conditions", "model", "budgets", "tool_policy", "prompt"}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json(raw):
    def invalid(value):
        raise ValueError("Non-finite JSON value")
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)


def _save_new(path, value):
    with path.open("xb") as stream:
        stream.write(json_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Expected a short lowercase identifier")
    return value


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Workspace files need normalized relative POSIX paths")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or str(path) != value or any(p in {"..", ".git"} for p in path.parts):
        raise ValueError("Workspace paths cannot escape the snapshot or include Git history")
    return path


def _plain_file(root, name):
    path = root
    for part in _relative(name).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed in prepared inputs")
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Prepared inputs must be regular files")
    return path


def _files(root, names):
    result = {}
    for name in names:
        path = _plain_file(root, name)
        result[name] = {"sha256": sha256(path.read_bytes()),
                        "executable": bool(path.stat().st_mode & 0o111)}
    return result


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) != SPEC_FIELDS or spec["schema_version"] != 1:
        raise ValueError("Expected the complete engineering preparation v1 specification")
    for key in ("episode_id", "window_id"):
        _identifier(spec[key])
    for key in ("project", "prompt"):
        if not isinstance(spec[key], str) or not spec[key].strip():
            raise ValueError("Project and prompt must be explicit")
    if not isinstance(spec["visible_until"], str):
        raise ValueError("The visible-history cutoff must be an ISO timestamp")
    cutoff = datetime.fromisoformat(spec["visible_until"].replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("The visible-history cutoff needs a timezone")
    names = spec["workspace_files"]
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError("List each visible workspace file exactly once")
    for name in names:
        _relative(name)
    budgets = spec["budgets"]
    if (not isinstance(budgets, dict) or set(budgets) != BUDGET_FIELDS
            or any(type(v) is not int or v < 1 for v in budgets.values())):
        raise ValueError("All five explicit budgets must be positive integers")
    if not isinstance(spec["tool_policy"], dict) or not spec["tool_policy"]:
        raise ValueError("An explicit tool policy is required")
    model = spec["model"]
    if model is not None and (not isinstance(model, dict) or set(model) != {"id", "cli_version"}
                             or any(not isinstance(v, str) or not v.strip() for v in model.values())):
        raise ValueError("Model is null or an explicit id and CLI version")
    conditions = spec["conditions"]
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("At least one preparation condition is required")
    ids = []
    for condition in conditions:
        if not isinstance(condition, dict) or set(condition) != {"id", "memory_policy", "implementation_sha256"}:
            raise ValueError("Each condition needs id, memory policy and implementation hash")
        ids.append(_identifier(condition["id"]))
        if condition["memory_policy"] not in {"none", "raw_history", "book", "component"}:
            raise ValueError("Unknown memory policy")
        pin = condition["implementation_sha256"]
        if pin is not None and (not isinstance(pin, str) or not SHA256.fullmatch(pin)):
            raise ValueError("Implementation hash must be SHA256 or null while preparing")
    if len(set(ids)) != len(ids):
        raise ValueError("Condition identifiers must be unique")
    return spec


def evaluator_hashes():
    here = Path(__file__).resolve()
    return {here.name: sha256(here.read_bytes()), "resume.py": sha256(here.with_name("resume.py").read_bytes())}


def prepare(snapshot, specification, output):
    """Copy only explicitly visible files; never invoke a product or model."""
    snapshot, specification, output = Path(snapshot), Path(specification), Path(output)
    if snapshot.is_symlink() or output.is_symlink():
        raise ValueError("Preparation roots cannot be symlinks")
    snapshot, output = snapshot.resolve(), output.resolve()
    if not snapshot.is_dir() or snapshot == output or snapshot in output.parents or output in snapshot.parents:
        raise ValueError("Snapshot and output must be separate, nonoverlapping directories")
    raw = specification.read_bytes()
    spec = validate_spec(_json(raw))
    files = _files(snapshot, spec["workspace_files"])
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _save_new(output / "specification.json", spec)
    workspaces = {}
    for condition in spec["conditions"]:
        relative = "conditions/" + condition["id"] + "/workspace"
        workspace = output / relative
        workspace.mkdir(parents=True)
        for name, metadata in files.items():
            source = _plain_file(snapshot, name)
            data = source.read_bytes()
            if sha256(data) != metadata["sha256"]:
                raise ValueError("Snapshot changed during preparation; retain this incomplete directory")
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o755 if metadata["executable"] else 0o644)
        (workspace.parent / "memory-state").mkdir()
        workspaces[condition["id"]] = relative
    if _files(snapshot, spec["workspace_files"]) != files:
        raise ValueError("Snapshot changed during preparation; retain this incomplete directory")
    identity = {"specification_sha256": sha256(json_bytes(spec)), "snapshot_files": files,
                "evaluator": evaluator_hashes()}
    report = {"evaluator": VERSION, "status": "prepared_no_model_calls", "identity": identity,
              "identity_sha256": sha256(json_bytes(identity)), "workspaces": workspaces,
              "actual_model_calls": 0, "quality_evidence": False,
              "isolation": "Separate copies are not hidden-test isolation"}
    _save_new(output / "prepared.json", report)
    return report


def inspect_prepared(output):
    output = Path(output)
    if output.is_symlink():
        raise ValueError("Prepared root cannot be a symlink")
    prepared = _json(_plain_file(output, "prepared.json").read_bytes())
    spec = validate_spec(_json(_plain_file(output, "specification.json").read_bytes()))
    identity = prepared["identity"]
    if (prepared.get("evaluator") != VERSION
            or prepared.get("identity_sha256") != sha256(json_bytes(identity))
            or identity["specification_sha256"] != sha256(json_bytes(spec))
            or identity["evaluator"] != evaluator_hashes()):
        raise ValueError("Prepared identity or evaluator changed")
    expected = {c["id"]: "conditions/" + c["id"] + "/workspace" for c in spec["conditions"]}
    if prepared["workspaces"] != expected:
        raise ValueError("Prepared workspace mapping changed")
    for relative in expected.values():
        workspace = output / relative
        for directory in (workspace, workspace.parent, workspace.parent.parent):
            if directory.is_symlink():
                raise ValueError("Workspace directories cannot be symlinks")
        if _files(workspace, spec["workspace_files"]) != identity["snapshot_files"]:
            raise ValueError("Prepared workspace changed")
        descendants = list(workspace.rglob("*"))
        if any(p.is_symlink() for p in descendants):
            raise ValueError("Workspace descendants cannot be symlinks")
        actual = {p.relative_to(workspace).as_posix() for p in descendants if not p.is_dir()}
        if actual != set(spec["workspace_files"]):
            raise ValueError("Unexpected files appeared in the prepared workspace")
        memory = workspace.parent / "memory-state"
        if memory.is_symlink() or not memory.is_dir() or any(memory.iterdir()):
            raise ValueError("Initial memory state must be an empty, independent directory")
    return prepared, spec


def authentication_status():
    """Use only the official read-only status command; never retain its text."""
    cli = shutil.which("codex")
    if cli is None:
        return {"status": "cli_unavailable", "exit_code": None}
    try:
        result = subprocess.run([cli, "login", "status"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unknown", "exit_code": None}
    return {"status": "available" if result.returncode == 0 else "unavailable",
            "exit_code": result.returncode}


def inspect(output, *, check_auth=False):
    prepared, spec = inspect_prepared(output)
    auth = authentication_status() if check_auth else {"status": "not_checked", "exit_code": None}
    blockers = ["hidden_test_isolation_not_verified", "bounded_agent_backend_not_connected"]
    if auth["status"] != "available":
        blockers.append("authentication_" + auth["status"])
    if spec["model"] is None:
        blockers.append("model_not_frozen")
    if any(c["memory_policy"] != "none" and c["implementation_sha256"] is None for c in spec["conditions"]):
        blockers.append("memory_implementations_not_frozen")
    return {"status": "blocked", "prepared_identity_sha256": prepared["identity_sha256"],
            "authentication": auth, "blockers": blockers, "actual_model_calls": 0,
            "quality_evidence": False, "budgets_recorded_not_enforced": spec["budgets"]}


def run(output):
    # No CLI exec path or --force switch exists. A successful login, sandbox
    # label, ordinary worktree or user-supplied receipt cannot enable scoring.
    return inspect(output, check_auth=True)


def capture_cli_events(output, condition, attempt_id, stream_factory):
    """Durably collect a byte stream, without attesting its origin.

    This reusable primitive does not launch a CLI or produce model-quality
    evidence. The callback is invoked only after the intent has been fsynced;
    a future verified backend can therefore launch its process in that callback.
    All directories, including interrupted/empty ones, are non-replayable.
    """
    if not callable(stream_factory):
        raise TypeError("An event-stream callback is required")
    prepared, _ = inspect_prepared(output)
    _identifier(condition)
    _identifier(attempt_id)
    if condition not in prepared["workspaces"]:
        raise ValueError("Unknown prepared condition")
    parent = Path(output) / "attempts" / condition
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or parent.parent.is_symlink():
        raise ValueError("Attempt directories cannot be symlinks")
    attempt = parent / attempt_id
    with _lock(parent / (attempt_id + ".jsonl")):
        attempt.mkdir(mode=0o700, exist_ok=False)
        with (attempt / "ledger.jsonl").open("xb") as ledger, (attempt / "stdout.jsonl").open("xb") as raw:
            def append(value):
                ledger.write(json_bytes(value) + b"\n")
                ledger.flush()
                os.fsync(ledger.fileno())
            append({"kind": "capture_intent", "prepared_identity_sha256": prepared["identity_sha256"],
                    "condition": condition, "attempt_id": attempt_id,
                    "origin": "unverified_cli_event_stream", "quality_evidence": False})
            counts, usage, invalid, total = Counter(), [], 0, 0
            try:
                for index, line in enumerate(stream_factory()):
                    if not isinstance(line, bytes):
                        raise TypeError("CLI capture requires bytes")
                    raw.write(line)
                    raw.flush()
                    os.fsync(raw.fileno())
                    total += len(line)
                    event = None
                    try:
                        if not line.endswith(b"\n") or len(line) > MAX_EVENT_BYTES:
                            raise ValueError("Incomplete or oversized CLI event")
                        event = _json(line)
                        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"]:
                            raise ValueError("CLI event needs a string type")
                    except (ValueError, UnicodeError):
                        invalid += 1
                        event = None
                    if event is not None and isinstance(event, dict) and isinstance(event.get("type"), str):
                        counts[event["type"]] += 1
                        reported = event.get("usage")
                        if isinstance(reported, dict):
                            usage.append({"event_index": index, "event_type": event["type"],
                                          "reported_counts": {k: v for k, v in reported.items()
                                                              if type(v) is int and v >= 0}})
                    append({"kind": "event_observed", "index": index, "sha256": sha256(line),
                            "bytes": len(line), "valid_json_event": event is not None and
                            isinstance(event, dict) and isinstance(event.get("type"), str)})
                result = {"status": "invalid_events" if invalid else "captured_unverified",
                          "event_type_counts": dict(counts), "invalid_events": invalid,
                          "stdout_bytes": total, "reported_usage_events": usage,
                          "actual_model_calls": None, "complete_model_usage": None,
                          "quality_evidence": False}
                append({"kind": "capture_finished", **result})
                _save_new(attempt / "capture.json", result)
                return result
            except BaseException as exc:
                append({"kind": "capture_interrupted", "error_type": type(exc).__name__,
                        "model_outcome_and_cost": "unknown", "quality_evidence": False})
                raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--snapshot", type=Path, required=True)
    prep.add_argument("--specification", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    examine = commands.add_parser("inspect")
    examine.add_argument("--prepared", type=Path, required=True)
    examine.add_argument("--check-auth", action="store_true")
    execute = commands.add_parser("run")
    execute.add_argument("--prepared", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.snapshot, args.specification, args.output)
        elif args.command == "inspect":
            result = inspect(args.prepared, check_auth=args.check_auth)
        else:
            result = run(args.prepared)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "invalid_preparation", "error_type": type(exc).__name__,
                          "actual_model_calls": 0, "quality_evidence": False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 2 if args.command == "run" else 0


if __name__ == "__main__":
    sys.exit(main())
