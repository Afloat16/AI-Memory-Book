"""Own and attest the pinned local answer process; never reuse an external server.

This launcher is for the registered 4096-context answer experiment. Its process
and artifact record binds the actual run ledger to the frozen server arguments.
It is separate from the 16384-context native workflow experiment.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tarfile
import time
from urllib import request

from benchmarks.answer_eval import NoRedirect, digest, json_bytes

HERE = Path(__file__).resolve().parent
PLAN = HERE / "experiments/local-answer-plan.json"
EXECUTION = HERE / "experiments/local-answer-execution.json"


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(json_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def verified_runtime(cache):
    """Check model, archive, every extracted file and library symlink."""
    cache = Path(cache).resolve()
    plan = json.loads(PLAN.read_bytes())
    model, server = plan["model"], plan["server"]
    model_path, archive = cache / model["file"], cache / server["asset"]
    for path, pin in ((model_path, model), (archive, server)):
        if path.stat().st_size != pin["bytes"] or file_hash(path) != pin["sha256"]:
            raise ValueError("Pinned local answer model/server artifact integrity failed")
    root = cache / server["tag"]
    files, links = {}, {}
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            path = root / member.name
            path.resolve().relative_to(root.resolve())
            if member.isfile():
                stream = package.extractfile(member)
                expected = hashlib.sha256(stream.read()).hexdigest() if stream else None
                if path.is_symlink() or not path.is_file() or file_hash(path) != expected:
                    raise ValueError("Extracted local answer runtime differs from its pinned archive")
                files[member.name] = expected
            elif member.issym():
                if not path.is_symlink() or os.readlink(path) != member.linkname:
                    raise ValueError("Extracted local answer runtime symlink differs from its archive")
                links[member.name] = member.linkname
            elif not member.isdir():
                raise ValueError("Unexpected member in pinned local answer runtime")
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() or path.is_symlink()}
    if actual != set(files) | set(links):
        raise ValueError("Unregistered files in local answer runtime directory")
    binaries = [root / name for name in files if Path(name).name == "llama-server"]
    if len(binaries) != 1:
        raise ValueError("Expected exactly one pinned llama-server")
    execution = json.loads(EXECUTION.read_bytes())
    argv = list(execution["server_argv"])
    if argv[0] != "llama-server" or argv[argv.index("--model") + 1] != model["file"]:
        raise ValueError("Registered server command has an unexpected executable/model")
    argv[0] = str(binaries[0])
    argv[argv.index("--model") + 1] = str(model_path)
    if argv[argv.index("--host") + 1] != "127.0.0.1":
        raise ValueError("Registered local answer server must use loopback")
    port = int(argv[argv.index("--port") + 1])
    endpoint = f"http://127.0.0.1:{port}/v1"
    return {"model_sha256": model["sha256"], "server_archive_sha256": server["sha256"],
            "runtime_files": files, "runtime_symlinks": links, "argv": argv,
            "endpoint": endpoint, "plan_sha256": file_hash(PLAN),
            "execution_plan_sha256": file_hash(EXECUTION),
            "launcher_sha256": file_hash(__file__)}


def validate_proof(proof_path, prepared, prefix, cache):
    """Refuse a local-model result supported only by downloaded file hashes."""
    proof = json.loads(Path(proof_path).read_bytes())
    expected = {"runtime": verified_runtime(cache), "prepared_sha256": file_hash(prepared)}
    if proof.get("identity") != expected or proof.get("identity_sha256") != digest(expected):
        raise ValueError("Owned local server proof differs from the registered artifacts or prepared inputs")
    runs = proof.get("runs", [])
    if not runs or runs[-1].get("status") != "completed" or not runs[-1].get("runtime_unchanged"):
        raise ValueError("Owned local server has no completed verified run")
    for suffix, field in ((".jsonl", "trace_sha256"), (".summary.json", "summary_sha256")):
        if runs[-1].get(field) != file_hash(Path(str(prefix) + suffix)):
            raise ValueError("Owned server proof is not bound to these actual answer results")
    if any(run.get("status") not in {"completed", "failed", "interrupted_unknown_outcome"} for run in runs):
        raise ValueError("Owned local server proof has an unresolved process")
    return proof


@contextmanager
def owned_server(cache, prepared, prefix, *, resume=False, lock_fd=None):
    runtime = verified_runtime(cache)
    identity = {"runtime": runtime, "prepared_sha256": file_hash(prepared)}
    proof_path = Path(str(prefix) + ".server.json")
    if proof_path.exists():
        if not resume:
            raise ValueError("Owned server proof exists; preserve it or explicitly resume")
        proof = json.loads(proof_path.read_bytes())
        if proof.get("identity") != identity or proof.get("identity_sha256") != digest(identity):
            raise ValueError("Owned server identity changed before resume")
        for old in proof["runs"]:
            if old["status"] == "running":
                old["status"] = "interrupted_unknown_outcome"
    else:
        if resume:
            raise ValueError("Resume requires the original owned server proof")
        proof = {"schema_version": 1, "ownership": "spawned_by_registered_local_answer_runner",
                 "identity": identity, "identity_sha256": digest(identity), "runs": []}
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    argv = runtime["argv"]
    port = int(argv[argv.index("--port") + 1])
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    record = {"status": "running", "started_at_unix": time.time()}
    proof["runs"].append(record)
    atomic(proof_path, proof)
    log_path = Path(str(prefix) + f".server-{len(proof['runs'])}.log")
    process = None
    with log_path.open("xb") as log:
        try:
            start = time.perf_counter()
            options = {"pass_fds": (lock_fd,)} if os.name != "nt" and lock_fd is not None else {}
            process = subprocess.Popen(argv, stdout=log, stderr=log,
                env={"PATH": os.defpath, "LANG": "C.UTF-8",
                     "LD_LIBRARY_PATH": str(Path(argv[0]).parent)}, **options)
            record["pid"] = process.pid
            atomic(proof_path, proof)
            deadline = time.monotonic() + 120
            opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Pinned local answer server exited before readiness")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                        health = json.loads(response.read())
                    if health.get("status") == "ok":
                        break
                except (OSError, ValueError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Pinned local answer server readiness timed out")
                time.sleep(.1)
            record["ready_ms"] = (time.perf_counter() - start) * 1000
            atomic(proof_path, proof)
            yield runtime["endpoint"]
            if process.poll() is not None:
                raise RuntimeError("Owned local answer server exited during the run")
            record["runtime_unchanged"] = verified_runtime(cache) == runtime
            if not record["runtime_unchanged"]:
                raise ValueError("Owned local answer runtime changed during execution")
            record["trace_sha256"] = file_hash(Path(str(prefix) + ".jsonl"))
            record["summary_sha256"] = file_hash(Path(str(prefix) + ".summary.json"))
            record["status"] = "completed"
        except BaseException as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                record["exit_code"] = process.returncode
            log.flush()
            record["log_sha256"] = file_hash(log_path)
            record["finished_at_unix"] = time.time()
            atomic(proof_path, proof)
