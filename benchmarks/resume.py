"""Run an explicit frozen benchmark manifest sequentially, resuming checked stages.

Paths are relative to manifest ``cwd`` (itself relative to the manifest file).
Inputs are {"path": "src", "pattern": "**/*.py"} or {"path": "data.json"}.
Stages have unique ``id``, an ``argv`` array, and unique ``outputs`` file paths.
The exact argv token {python} means this interpreter; no shell is involved.
Optional ``runtime_commands`` are argv arrays (for example [["node", "--version"]]);
their outputs, installed distribution versions and SQLite version are frozen.
Changed source/data/commands require a new checkpoint. Missing or damaged
completed reports rerun that stage and every successor. JSON reports are parsed.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import zlib


RUNTIME_COMMAND_TIMEOUT = 10


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inputs(manifest: dict, cwd: Path) -> dict:
    files = {}
    for item in manifest["inputs"]:
        path = (cwd / item["path"]).resolve()
        paths = sorted(path.glob(item["pattern"])) if "pattern" in item else [path]
        paths = [candidate for candidate in paths if candidate.is_file()]
        if not paths:
            raise ValueError(f"Input has no files: {item}")
        for candidate in paths:
            files[str(candidate.resolve())] = _file_hash(candidate)
    return files


def _save(path: Path, state: dict) -> None:
    # Replace only after flushing a complete checkpoint; interruption cannot
    # turn the previous good JSON into a half-written checkpoint.
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def _lock(checkpoint: Path):
    # A separate stable inode survives checkpoint replacements. OS locks are
    # released even after a killed runner, unlike a mkdir-based stale lock.
    with checkpoint.with_name(checkpoint.name + ".lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("This checkpoint already has an active runner") from exc
        yield stream


def _outputs(stage: dict, cwd: Path) -> dict:
    result = {}
    for name in stage["outputs"]:
        path = cwd / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty report: {path}")
        if name.endswith((".json", ".json.gz")):
            opener = gzip.open if name.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as stream:
                report = json.load(stream)
            if isinstance(report, dict) and "validation" in report:
                if not isinstance(report["validation"], dict) or report["validation"].get("passed") is not True:
                    raise ValueError(f"Report validation failed: {path}")
        result[name] = _file_hash(path)
    return result


def _stamp(path: Path):
    if not path.exists():
        return None
    value = path.stat()
    return value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _stop(process: subprocess.Popen) -> None:
    if os.name == "nt":
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    else:
        # Popen starts a new session whose group ID is this exact child PID.
        # Clean that group even if the leader has already exited nonzero.
        def signal_group(value):
            try:
                os.killpg(process.pid, value)
            except ProcessLookupError:
                pass

        signal_group(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        finally:
            # Leader exit does not prove its workers exited. Nested Popen calls
            # may close our lock descriptor, so do not leave survivors behind.
            signal_group(signal.SIGKILL)
    process.wait()


def _run(argv: list[str], cwd: Path, timeout: float | None, lock_fd: int, *, capture=False):
    # On POSIX the child keeps the lock after even a SIGKILL of this runner;
    # a resume cannot overlap a benchmark orphan that is still finishing.
    options = {"pass_fds": (lock_fd,)} if os.name != "nt" else {}
    if capture:
        options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    with subprocess.Popen(argv, cwd=cwd, start_new_session=os.name != "nt", **options) as process:
        try:
            output = process.communicate(timeout=timeout) if capture else (None, None)
            code = process.wait(timeout=timeout)
            if code:
                raise subprocess.CalledProcessError(code, argv, output=output[0], stderr=output[1])
            return output
        except BaseException:
            _stop(process)
            raise


def _runtime(manifest: dict, cwd: Path, lock_fd: int) -> dict:
    # Repeated sys.path entries can expose the same installed distribution
    # several times. Freeze its normalized name/version once; retain distinct
    # versions of one name so a conflicting or changed installation still
    # invalidates the checkpoint. This records package metadata, not wheel-byte
    # identity; executable/model files can also be listed in manifest inputs.
    distributions = sorted({(re.sub(r"[-_.]+", "-", item.metadata.get("Name", "")).lower(),
                             item.version)
                            for item in importlib.metadata.distributions()})
    commands = []
    for arguments in manifest.get("runtime_commands", []):
        argv = [sys.executable if arg == "{python}" else arg for arg in arguments]
        stdout, stderr = _run(argv, cwd, RUNTIME_COMMAND_TIMEOUT, lock_fd, capture=True)
        commands.append({"argv": argv, "stdout": stdout, "stderr": stderr})
    return {"distributions": [list(item) for item in distributions],
            "sqlite": sqlite3.sqlite_version, "commands": commands}


def run(manifest_path: Path, checkpoint: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cwd = (manifest_path.resolve().parent / manifest.get("cwd", ".")).resolve()
    stages = manifest.get("stages", [])
    if manifest.get("version") != 1 or not manifest.get("inputs") or not stages or not cwd.is_dir():
        raise ValueError("Require version 1, existing cwd, nonempty inputs and stages")
    for item in manifest["inputs"]:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or not item["path"] or ("pattern" in item and not isinstance(item["pattern"], str))):
            raise ValueError("Each input requires a path string and optional glob pattern")
    commands = manifest.get("runtime_commands", [])
    if not isinstance(commands, list) or any(
            not isinstance(argv, list) or not argv or
            not all(isinstance(arg, str) and arg for arg in argv) for argv in commands):
        raise ValueError("runtime_commands must contain nonempty argv string arrays")
    ids, output_paths = set(), set()
    for stage in stages:
        if (not isinstance(stage.get("id"), str) or not stage["id"] or stage["id"] in ids
                or not isinstance(stage.get("argv"), list) or not stage["argv"]
                or not all(isinstance(arg, str) and arg for arg in stage["argv"])
                or not isinstance(stage.get("outputs"), list) or not stage["outputs"]
                or not all(isinstance(name, str) and name for name in stage["outputs"])):
            raise ValueError("Each stage requires a unique id, argv strings and output paths")
        ids.add(stage["id"])
        for name in stage["outputs"]:
            path = (cwd / name).resolve()
            if path in output_paths or path in (checkpoint.resolve(), Path(str(checkpoint.resolve()) + ".lock")):
                raise ValueError(f"Output paths must be unique and separate from checkpoint: {path}")
            output_paths.add(path)
    checkpoint = checkpoint.resolve()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with _lock(checkpoint) as lock:
        def inputs():
            result = _inputs(manifest, cwd)
            for path in (manifest_path.resolve(), Path(__file__).resolve()):
                result[str(path)] = _file_hash(path)
            return result

        identity = {"manifest_sha256": _digest(manifest), "cwd": str(cwd),
                    "python": sys.executable, "python_version": sys.version,
                    "inputs": inputs(), "runtime": _runtime(manifest, cwd, lock.fileno())}
        if output_paths.intersection(map(Path, identity["inputs"])):
            raise ValueError("Outputs must not overwrite frozen inputs")
        if str(checkpoint) in identity["inputs"]:
            raise ValueError("Checkpoint must not overwrite frozen inputs")
        state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
            "version": 1, "identity": identity, "stages": {}}
        if state.get("version") != 1 or state.get("identity") != identity:
            raise RuntimeError("Checkpoint identity changed (source, dataset, runtime or manifest); use a new checkpoint")
        rerun = False
        for stage in stages:
            stage_id = stage["id"]
            record = state["stages"].get(stage_id, {})
            if not rerun and record.get("status") == "completed":
                try:
                    valid = _outputs(stage, cwd) == record.get("outputs")
                except (OSError, ValueError, EOFError, zlib.error):
                    valid = False
                if valid:
                    print(f"skip {stage_id}: checked completed reports", flush=True)
                    continue
            # Any missing/invalid/incomplete stage invalidates its suffix.
            rerun = True
            for successor in stages[stages.index(stage):]:
                if successor["id"] != stage_id:
                    state["stages"].pop(successor["id"], None)
            if inputs() != identity["inputs"] or _runtime(manifest, cwd, lock.fileno()) != identity["runtime"]:
                raise RuntimeError("Frozen inputs or runtime changed; stopped before next stage")
            argv = [sys.executable if arg == "{python}" else arg for arg in stage["argv"]]
            record = {"status": "running", "argv": argv, "identity_sha256": _digest(identity),
                      "started_at": time.time(), "attempt": record.get("attempt", 0) + 1}
            state["stages"][stage_id] = record
            _save(checkpoint, state)
            print(f"run {stage_id}", flush=True)
            try:
                before = {name: _stamp(cwd / name) for name in stage["outputs"]}
                _run(argv, cwd, stage.get("timeout_seconds"), lock.fileno())
                if inputs() != identity["inputs"] or _runtime(manifest, cwd, lock.fileno()) != identity["runtime"]:
                    raise RuntimeError("Frozen inputs or runtime changed during stage")
                if any(old is not None and old == _stamp(cwd / name)
                       for name, old in before.items()):
                    raise ValueError("Stage left a pre-existing report unchanged")
                record.update(outputs=_outputs(stage, cwd), status="completed")
            except BaseException as exc:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                record["finished_at"] = time.time()
                _save(checkpoint, state)
        if inputs() != identity["inputs"] or _runtime(manifest, cwd, lock.fileno()) != identity["runtime"]:
            raise RuntimeError("Frozen inputs or runtime changed during completion checks")
        return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args(argv)

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt("Runner interrupted")

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        run(args.manifest, args.checkpoint)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, EOFError, zlib.error, subprocess.SubprocessError) as exc:
        print(f"Benchmark stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
