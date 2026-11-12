"""Actual Book/native ai-memory replay, consolidation and paired-answer diagnostic.

The registered small authored corpus is regression data. Native summaries and
observations are never fabricated. Raw prompts/responses and sandbox databases
stay under .artifacts; an atomic checkpoint survives between every operation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import os
from pathlib import Path
import re
import secrets
import socket
import statistics
import subprocess
import threading
import time
from urllib import error, parse, request
import uuid

from benchmarks.answer_eval import (PROMPT, NoRedirect, answer_scores, call_endpoint, database_file_bytes,
                                    completion_url, digest, json_bytes,
                                    provider_usage)
from benchmarks.competitors.ai_memory import LOCK_PATH, prepare, prepare_models
from benchmarks.run import engine_source_hash
from benchmarks.resume import _lock
from benchmarks.local_answer_server import verified_runtime
from benchmarks.token_compare import TokenCounter, checkout_provenance, latency_summary
from benchmarks.transfer_data import DATA, load_transfer

HERE = Path(__file__).resolve().parent
PLAN = HERE / "experiments/full-workflow-plan.json"
ANSWERS = HERE / "experiments/full-workflow-answers.json"
VERSION = "native-workflow-1.0"


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(json_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def append(path, value):
    with Path(path).open("ab") as stream:
        stream.write(json_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


@contextmanager
def model_server(args, root):
    if not args.launch_server:
        yield {"ownership": "external", "artifact_verification": "unverified external process",
               "endpoint": args.base_url}
        return
    cache = args.model_cache.resolve()
    # Share the strict file/link verifier with the answer experiment. Its
    # 4096-context command is not launched here: this workflow retains its
    # independently registered 16384-context command below.
    runtime = verified_runtime(cache)
    binary = Path(runtime["argv"][0])
    model = Path(runtime["argv"][runtime["argv"].index("--model") + 1])
    endpoint = parse.urlsplit(args.base_url)
    if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
            or endpoint.port is None or endpoint.path != "/v1"
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
        raise ValueError("Self-launch needs an explicit http://127.0.0.1:PORT/v1 endpoint")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", endpoint.port))
    argv = [str(binary), "--model", str(model), "--alias", args.model, "--host", "127.0.0.1",
            "--port", str(endpoint.port), "--ctx-size", "16384", "--threads", "4", "--parallel", "1",
            "--seed", "42", "--no-cache-prompt", "--cache-ram", "0", "--n-gpu-layers", "0"]
    log_path = root / "llama-server.log"
    with log_path.open("ab") as log:
        start = time.perf_counter()
        lock_fd = getattr(args, "lock_fd", None)
        options = {"pass_fds": (lock_fd,)} if os.name != "nt" and lock_fd is not None else {}
        process = subprocess.Popen(argv, stdout=log, stderr=log,
            env={"PATH": os.defpath, "LANG": "C.UTF-8", "LD_LIBRARY_PATH": str(binary.parent)}, **options)
        metadata = {"ownership": "spawned_by_this_runner", "argv": argv,
                    "model_sha256": runtime["model_sha256"], "archive_sha256": runtime["server_archive_sha256"],
                    "extracted_binary_sha256": file_sha256(binary), "server_pid": process.pid,
                    "runtime_files": runtime["runtime_files"], "runtime_symlinks": runtime["runtime_symlinks"],
                    "runtime_unchanged": None, "completed": False}
        try:
            deadline = time.monotonic() + 120
            opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Pinned llama-server exited; inspect preserved log")
                try:
                    with opener.open(f"http://127.0.0.1:{endpoint.port}/health", timeout=2) as response:
                        health = json.loads(response.read())
                    if health.get("status") == "ok":
                        break
                except (OSError, ValueError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Pinned llama-server readiness timeout")
                time.sleep(.1)
            metadata["ready_ms"] = (time.perf_counter() - start) * 1000
            yield metadata
            if process.poll() is not None:
                raise RuntimeError("Owned workflow model server exited during evaluation")
            metadata["completed"] = True
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            log.flush()
            metadata["log_sha256"] = file_sha256(log_path)
            metadata["exit_code"] = process.returncode
            try:
                metadata["runtime_unchanged"] = verified_runtime(cache) == runtime
                if not metadata["runtime_unchanged"]:
                    raise ValueError("Owned workflow model runtime changed during evaluation")
            except BaseException:
                metadata["runtime_unchanged"] = False
                metadata["completed"] = False
                raise
            finally:
                # Preserve final verification even when a failure prevents the
                # outer workflow from producing its normal completion report.
                append(root / "model-server-verification.jsonl", metadata)


def inputs():
    plan = json.loads(PLAN.read_bytes())
    labels = json.loads(ANSWERS.read_bytes())
    if hashlib.sha256(DATA.read_bytes()).hexdigest() != labels["source_sha256"]:
        raise ValueError("Registered source bytes changed")
    dataset = load_transfer()
    if len(dataset.sessions) != 42 or len(dataset.queries) != 36:
        raise ValueError("Registered cohort count changed")
    if set(labels["answers"]) != {q.id for q in dataset.queries}:
        raise ValueError("Answer IDs do not exactly cover the frozen cohort")
    cases = []
    for q in dataset.queries:
        answers = labels["answers"][q.id]
        if bool(answers) != q.answerable or any(not isinstance(a, str) or not a.strip() for a in answers):
            raise ValueError("Frozen answerability or answer shape mismatch")
        cases.append({"id": q.id, "query": q.query, "project": q.project,
                      "category": q.category, "answerable": q.answerable, "answers": answers})
    sessions = []
    for original in dataset.sessions:
        session = {**original, "messages": [
            {**m, "content": f"[Source date: {original['created_at']}] {m['content']}"}
            for m in original["messages"]]}
        if any(len(m["content"].encode()) > 2000 for m in session["messages"]):
            raise ValueError("Source exceeds registered native assistant capture boundary")
        sessions.append(session)
    return plan, sessions, cases


def session_id(session):
    return str(uuid.uuid5(uuid.NAMESPACE_OID,
                         "memory-book-native-workflow-v1:" + session["project"] + ":" + session["session_id"]))


def hook_events(session):
    sid = session_id(session)
    base = {"session_id": sid, "cwd": "/workflow/" + session["project"]}
    def event(name, extra, capture=False):
        params = {"event": name, "agent": "claude-code", "workspace": "workflow",
                  "project": session["project"], "session_id": sid}
        if capture:
            params["capture_assistant"] = "1"
        return {"url": "/hook?" + parse.urlencode(params), "body": {**base, **extra}}
    result = [event("session-start", {"hook_event_name": "SessionStart", "source": "startup"})]
    for message in session["messages"]:
        if message["role"] == "user":
            result.append(event("user-prompt-submit", {"hook_event_name": "UserPromptSubmit",
                                                       "prompt": message["content"]}))
        elif message["role"] == "assistant":
            result.append(event("stop", {"hook_event_name": "Stop", "_ai_memory_assistant": {
                "version": 1, "excerpt": message["content"]}}, True))
        else:
            raise ValueError("Unsupported role in registered replay")
    result.append(event("session-end", {"hook_event_name": "SessionEnd", "reason": "exit"}))
    return result


@contextmanager
def recording_proxy(target, trace):
    """Forward actual native calls unchanged to one explicit loopback model."""
    target_url = completion_url(target)
    if parse.urlsplit(target_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("This registered local experiment requires a loopback endpoint")
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            attempt = str(uuid.uuid4())
            start = time.perf_counter()
            with lock:
                append(trace, {"event": "started", "attempt": attempt,
                               "request_sha256": hashlib.sha256(raw).hexdigest(),
                               "request": json.loads(raw)})
            status, response = 502, b'{}'
            try:
                req = request.Request(target_url, raw, {"Content-Type": "application/json"}, method="POST")
                with request.build_opener(request.ProxyHandler({}), NoRedirect()).open(req, timeout=180) as upstream:
                    status, response = upstream.status, upstream.read()
            except error.HTTPError as exc:
                status, response = exc.code, exc.read()
            except (OSError, TimeoutError):
                pass
            try:
                decoded = json.loads(response)
                if not isinstance(decoded, dict):
                    decoded = {}
            except (ValueError, TypeError):
                decoded = {}
            with lock:
                append(trace, {"event": "completed", "attempt": attempt, "http_status": status,
                               "elapsed_ms": (time.perf_counter() - start) * 1000,
                               "response_sha256": hashlib.sha256(response).hexdigest(),
                               "usage": provider_usage(decoded.get("usage")), "response": decoded})
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            try:
                self.wfile.write(response)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class NativeWorkflow:
    def __init__(self, root, cache, proxy_url, model, lock_fd=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.rpc_id = 0
        start = time.perf_counter()
        binary = prepare(cache, offline=True)
        self.embedding = prepare_models(cache, offline=True)
        if not (self.root / "models").exists():
            (self.root / "models").symlink_to(Path(cache).resolve() / "models", target_is_directory=True)
        config = self.root / "config.toml"
        config.write_text('embedding_provider = "local"\nllm_provider = "openai-compat"\n'
                          f'llm_model = {json.dumps(model)}\nllm_base_url = {json.dumps(proxy_url)}\n'
                          'consolidate_on_session_end = false\n'
                          '[consolidation]\nmax_input_tokens = 10000\nmax_output_tokens = 1000\n', encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.log = (self.root / "server.log").open("ab")
        options = {"pass_fds": (lock_fd,)} if os.name != "nt" and lock_fd is not None else {}
        self.process = subprocess.Popen([str(binary), "--data-dir", str(self.root), "--config", str(config),
            "serve", "--transport", "http", "--bind", f"127.0.0.1:{self.port}", "--no-watcher"],
            stdout=self.log, stderr=self.log, env={"PATH": os.defpath, "LANG": "C.UTF-8",
            "AI_MEMORY_AUTH_TOKEN": self.token, "LLM_API_KEY": "workflow-local-only",
            "AI_MEMORY_LLM_API_KEY": "workflow-local-only"}, **options)
        try:
            deadline = time.monotonic() + 60
            while True:
                if self.process.poll() is not None:
                    raise RuntimeError("Native server startup failed; see preserved sandbox server.log")
                try:
                    self.http("GET", "/admin/search?q=workflow-startup-probe&limit=1")
                    break
                except (OSError, error.URLError):
                    if time.monotonic() > deadline:
                        raise TimeoutError("Native server readiness timeout")
                    time.sleep(.1)
            self.http("POST", "/mcp", {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "memory-book-native-workflow", "version": VERSION}}})
        except Exception:
            self.close()
            raise
        self.startup_ms = (time.perf_counter() - start) * 1000

    def http(self, method, route, body=None):
        raw = None if body is None else json_bytes(body)
        req = request.Request(f"http://127.0.0.1:{self.port}" + route, raw, {
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token}, method=method)
        start = time.perf_counter()
        attempt = str(uuid.uuid4())
        trace = self.root / "native-http-trace.jsonl"
        append(trace, {"event": "started", "attempt": attempt, "method": method, "route": route,
                       "request_sha256": hashlib.sha256(raw or b"").hexdigest()})
        try:
            with request.build_opener(request.ProxyHandler({}), NoRedirect()).open(req, timeout=240) as response:
                response_bytes = response.read()
                decoded = json.loads(response_bytes)
            append(trace, {"event": "completed", "attempt": attempt, "status": response.status,
                           "elapsed_ms": (time.perf_counter() - start) * 1000,
                           "response_sha256": hashlib.sha256(response_bytes).hexdigest(), "response": decoded})
            return decoded
        except Exception as exc:
            append(trace, {"event": "error", "attempt": attempt, "error_type": type(exc).__name__,
                           "elapsed_ms": (time.perf_counter() - start) * 1000})
            raise

    def call(self, name, arguments):
        self.rpc_id += 1
        start = time.perf_counter()
        rpc = self.http("POST", "/mcp", {"jsonrpc": "2.0", "id": self.rpc_id,
            "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        native = rpc.get("result", {})
        text = "\n".join(c["text"] for c in native.get("content", []) if c.get("type") == "text")
        try:
            decoded = json.loads(text) if text else None
        except ValueError:
            decoded = None
        return {"ok": "error" not in rpc and not native.get("isError"), "decoded": decoded,
                "native_text": text, "rpc": rpc, "elapsed_ms": (time.perf_counter() - start) * 1000}

    def capture(self, session):
        pending = hook_events(session)
        attempts = []
        for _ in range(60):
            if not pending:
                break
            ack = self.http("POST", "/hook/batch", pending)
            indices = ack.get("accepted_indices", list(range(ack.get("accepted", 0))))
            if any(type(i) is not int or i < 0 or i >= len(pending) for i in indices):
                raise ValueError("Invalid native hook acceptance indices")
            attempts.append({"sent": len(pending), "ack": ack})
            pending = [item for i, item in enumerate(pending) if i not in set(indices)]
            if pending:
                time.sleep(.5)
        return {"ok": not pending, "session_id": session_id(session), "attempts": attempts,
                "source_sha256": digest(session), "remaining_events": len(pending)}

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()


def native_units(text):
    """Intact native paragraphs/sentences with exact offsets; no gold input."""
    units = []
    for match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        start, end = match.span()
        for sentence in re.finditer(r".+?(?:[。！？]|[.!?](?=\s|$)|$)", text[start:end], re.S):
            a, b = start + sentence.start(), start + sentence.end()
            while a < b and text[a].isspace():
                a += 1
            if a < b:
                units.append((a, b))
    return units


def pack_native(blocks, counter, budget=512, chars=8000):
    selected, retained = [], []
    def fit(identity, text, start, end):
        block = f"[{identity} chars={start}:{end}]\n{text[start:end]}"
        context = "\n\n".join(selected + [block])
        if len(context) <= chars and counter.count(context) <= budget:
            selected.append(block)
            retained.append({"source": identity, "start": start, "end": end,
                             "source_sha256": hashlib.sha256(text.encode()).hexdigest()})
            return True
        return False
    for identity, text in blocks:
        if not fit(identity, text, 0, len(text)):
            for a, b in native_units(text):
                fit(identity, text, a, b)
    context = "\n\n".join(selected)
    return {"context": context, "context_tokens": counter.count(context), "sources": retained,
            "input_blocks": len(blocks), "input_characters": sum(len(t) for _, t in blocks)}


def native_recall(native, case, counter):
    start = time.perf_counter()
    scope = {"workspace": "workflow", "project": case["project"]}
    search = native.call("memory_query", {**scope, "query": case["query"], "limit": 5, "answer": False})
    if not search["ok"] or not isinstance(search["decoded"], dict):
        raise ValueError("Native query failed")
    reads, blocks, seen = [], [], set()
    for hit in search["decoded"].get("hits", []):
        path = hit.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("Native page hit lacks a path")
        identity = case["project"] + "/" + path
        if identity in seen:
            continue
        seen.add(identity)
        result = native.call("memory_read_page", {**scope, "path": path, "max_chars": 64000})
        reads.append(result)
        if not result["ok"] or not isinstance(result["decoded"], dict):
            raise ValueError("Native page read failed")
        body = result["decoded"].get("body")
        if not isinstance(body, str) or result["decoded"].get("truncated"):
            raise ValueError("Native page body missing or truncated")
        blocks.append((identity, body))
    for hit in search["decoded"].get("raw_hits", []):
        sid = hit.get("session_id")
        if not isinstance(sid, str) or not sid:
            raise ValueError("Native raw hit lacks its session identity")
        identity = case["project"] + "/observations/" + sid
        if identity in seen:
            continue
        seen.add(identity)
        result = native.call("memory_read_session_observations", {
            **scope, "session_id": sid, "limit": 200, "body_max_chars": 16384})
        reads.append(result)
        decoded = result["decoded"]
        if not result["ok"] or not isinstance(decoded, dict):
            raise ValueError("Native session read failed")
        observations = decoded.get("observations", [])
        if decoded.get("total", len(observations)) > len(observations):
            raise ValueError("Native observations would require pagination")
        for observation in observations:
            text = observation.get("body")
            if isinstance(text, str) and text:
                blocks.append((identity + "/" + str(observation.get("id", "unknown")), text))
    retrieval_ms = (time.perf_counter() - start) * 1000
    packed = pack_native(blocks, counter)
    return {**packed, "retrieval_ms": retrieval_ms,
            "packing_ms": (time.perf_counter() - start) * 1000 - retrieval_ms,
            "search": search, "reads": reads,
                "native_returned_tokens": counter.count(search["native_text"]) + sum(counter.count(r["native_text"]) for r in reads),
                "search_calls": 1, "read_calls": len(reads)}


def usage_summary(rows, key):
    result = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        known = [r.get(key, {}).get(field) for r in rows]
        numbers = [n for n in known if n is not None]
        result[field] = {"attempts": len(rows), "reported_calls": len(numbers),
                         "known_subtotal": sum(numbers),
                         "total_if_complete": sum(numbers) if len(numbers) == len(rows) else None}
    return result


def operation_succeeded(key, record):
    if record["status"] != "completed":
        return False
    result = record.get("result", {})
    if not result.get("ok", True):
        return False
    if key.startswith("native-consolidate:"):
        decoded = result.get("decoded")
        return bool(isinstance(decoded, dict) and decoded.get("page_id")
                    and decoded.get("dry_run") is False
                    and isinstance(decoded.get("new_body_markdown"), str)
                    and decoded["new_body_markdown"].strip())
    if key == "native-embed":
        return type(result.get("failed")) is int and result["failed"] == 0
    return True


def wall_summary(records):
    known = [r["elapsed_ms"] for r in records if r.get("elapsed_ms") is not None]
    return {"operations": len(records), "reported_operations": len(known),
            "known_subtotal_ms": sum(known),
            "total_if_complete_ms": sum(known) if len(known) == len(records) else None}


def summarize(report, trace):
    events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    started = {e["attempt"]: e for e in events if e["event"] == "started"}
    completed = {e["attempt"]: e for e in events if e["event"] == "completed"}
    model_calls = [completed.get(k, {"usage": provider_usage(None), "http_status": None}) for k in started]
    engines = []
    for engine in ("book", "ai-memory"):
        rows = [r for r in report["answers"].values() if r["engine"] == engine]
        scored = [r for r in rows if r["answerable"]]
        absent = [r for r in rows if not r["answerable"]]
        contexts = [r for k, r in report["stages"].items() if k.startswith("context:" + engine + ":") and r["status"] == "completed"]
        mean = lambda seq: statistics.fmean(seq) if seq else None
        phases = {}
        for prefix in (["book-ingest:"] if engine == "book" else ["native-capture:", "native-consolidate:", "native-embed"]):
            paired = [(k, r) for k, r in report["stages"].items() if k.startswith(prefix)]
            selected = [r for _, r in paired]
            phases[prefix.rstrip(":")] = {**wall_summary(selected),
                "completed": sum(r["status"] == "completed" for r in selected),
                "successful": sum(operation_succeeded(k, r) for k, r in paired)}
        engines.append({"engine": engine, "answer_attempts": len(rows),
            "successful_answers": sum(r["status"] == "ok" for r in rows),
            "truncated_answers": sum(r.get("finish_reason") == "length" for r in rows),
            "answerable_queries": len(scored), "unsupported_queries": len(absent),
            "normalized_exact_match": mean([r["scores"]["normalized_exact_match"] for r in scored]),
            "lexical_token_f1": mean([r["scores"]["lexical_token_f1"] for r in scored]),
            "exact_abstention_rate": mean([float(r["scores"]["abstained"]) for r in absent]),
            "phases": phases, "answer_usage": usage_summary(rows, "provider_usage"),
            "answer_latency": latency_summary([r["endpoint_roundtrip_ms"] for r in rows if r.get("endpoint_roundtrip_ms") is not None]),
            "mean_context_tokens": mean([r["result"]["context_tokens"] for r in contexts]),
            "mean_returned_tokens": mean([r["result"]["native_returned_tokens"] for r in contexts]),
            "retrieval_reported_queries": len(contexts),
            "retrieval_known_subtotal_ms": sum(r["result"]["retrieval_ms"] for r in contexts),
            "retrieval_total_if_complete_ms": (sum(r["result"]["retrieval_ms"] for r in contexts)
                                                if len(contexts) == 36 else None),
            "retrieval_calls": sum(r["result"].get("search_calls", 1) for r in contexts),
            "followup_read_calls": sum(r["result"].get("read_calls", 0) for r in contexts),
            "packing_known_subtotal_ms": sum(r["result"].get("packing_ms", 0) for r in contexts),
            "summary_model_calls": 0 if engine == "book" else len(started),
            "summary_usage": usage_summary([] if engine == "book" else model_calls, "usage")})
    return {"engines": engines, "native_model_attempts": len(started),
            "native_model_completed": len(completed), "native_model_http_errors": sum(c.get("http_status") != 200 for c in model_calls),
            "unmeasured": ["interactive host capture", "filesystem watcher overhead", "adaptive agent reads", "provider billing", "electricity"],
            "interpretation": "36 previously authored diagnostic questions and one small CPU model; no universal product ranking. Phase clocks have different native transport boundaries."}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with _lock(root / "checkpoint.json") as lock:
        args.lock_fd = lock.fileno()
        return run_locked(args)


def active_source_root():
    """Accept only imported package bytes matching the registered checkout."""
    import memory_book
    from memory_book import MemoryBook
    expected = (HERE.parent / "src/memory_book").resolve()
    imported_package = Path(memory_book.__file__).resolve()
    imported_class = Path(inspect.getfile(MemoryBook)).resolve()
    actual = imported_package.parent
    if (not imported_package.is_file() or imported_package.name != "__init__.py"
            or imported_class != actual / "store.py"
            or engine_source_hash(actual) != engine_source_hash(expected)):
        raise ValueError("Imported memory_book runtime is not the source tree recorded by this workflow")
    # Hash only the imported package, never the entire site-packages directory.
    # A byte-identical installed wheel is valid and reports its actual path.
    return actual


def run_locked(args):
    from memory_book import MemoryBook
    plan, sessions, cases = inputs()
    if args.model != plan["model"]["served_alias"]:
        raise ValueError("Model alias differs from the registered workflow experiment")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    checkpoint, trace = root / "checkpoint.json", root / "native-model-trace.jsonl"
    source = active_source_root()
    files = [Path(__file__), PLAN, ANSWERS, HERE / "answer_eval.py", HERE / "token_compare.py",
             HERE / "transfer_data.py", HERE / "data.py", HERE / "run.py", HERE / "resume.py", DATA, LOCK_PATH,
             HERE / "competitors/ai_memory.py", HERE / "competitors/download.py",
             HERE / "experiments/local-answer-plan.json", HERE / "local_answer_server.py",
             HERE / "experiments/local-answer-execution.json"]
    identity = {"source_sha256": engine_source_hash(source), "inputs": {str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                "registered_checkout_source_sha256": engine_source_hash(HERE.parent / "src"),
                "sessions_sha256": digest(sessions), "model": args.model, "endpoint": args.base_url,
                "launch_server": args.launch_server,
                "plan": plan, "source_provenance": checkout_provenance(source)}
    # Git HEAD may advance on documentation-only commits; compare actual bytes.
    identity_hash = digest({k: v for k, v in identity.items() if k != "source_provenance"})
    if checkpoint.exists():
        if not args.resume:
            raise ValueError("Output exists; use --resume to retain completed operations")
        report = json.loads(checkpoint.read_bytes())
        if report["identity_sha256"] != identity_hash:
            raise ValueError("Source, plan, gold, endpoint or evaluator changed on resume")
        for record in report["stages"].values():
            if record["status"] == "running":
                record["status"] = "interrupted_unknown_outcome"
    else:
        report = {"evaluator": VERSION, "identity": identity, "identity_sha256": identity_hash,
                  "stages": {}, "answers": {}, "status": "running"}
    def save():
        atomic(checkpoint, report)
    def stage(key, operation):
        if key in report["stages"]:
            return report["stages"][key]
        record = {"status": "running"}
        report["stages"][key] = record
        save()
        start = time.perf_counter()
        try:
            record.update(status="completed", result=operation())
        except Exception as exc:
            record.update(status="error", error_type=type(exc).__name__, error_message=str(exc)[:500])
        record["elapsed_ms"] = (time.perf_counter() - start) * 1000
        save()
        return record
    save()
    counter = TokenCounter("cl100k_base")
    book_start = time.perf_counter()
    book = MemoryBook(root / "book.db", cache_size=0)
    report.setdefault("book_startups_ms", []).append((time.perf_counter() - book_start) * 1000)
    with book, model_server(args, root) as server_metadata, recording_proxy(args.base_url, trace) as proxy:
        report.setdefault("model_server_runs", []).append(server_metadata)
        save()
        for session in sessions:
            stage("book-ingest:" + session_id(session), lambda s=session: book.ingest(s))
        native = NativeWorkflow(root / "ai-memory", args.cache, proxy, args.model, args.lock_fd)
        report.setdefault("native_startups", []).append({"startup_ms": native.startup_ms, "embedding": native.embedding})
        save()
        try:
            for session in sessions:
                sid = session_id(session)
                captured = stage("native-capture:" + sid, lambda s=session: native.capture(s))
                if captured["status"] == "completed" and captured["result"]["ok"]:
                    stage("native-consolidate:" + sid, lambda sid=sid: native.call("memory_consolidate", {
                        "session_id": sid, "dry_run": False, "multi_page": False}))
            stage("native-embed", lambda: native.http("POST", "/admin/embed", {
                "workspace": "workflow", "project": "", "reembed": False,
                "dry_run": False, "all_projects": True}))
            for index, case in enumerate(cases):
                order = ("book", "ai-memory") if index % 2 == 0 else ("ai-memory", "book")
                for engine in order:
                    key = engine + ":" + case["id"]
                    def get_context():
                        if engine == "ai-memory":
                            return native_recall(native, case, counter)
                        start = time.perf_counter()
                        result = book.recall(case["query"], project=case["project"], budget_chars=8000,
                                             budget_tokens=512, tokenizer="cl100k_base", limit=5)
                        return {"context": result["context"], "context_tokens": counter.count(result["context"]),
                                "retrieval_ms": (time.perf_counter() - start) * 1000, "packing_ms": 0,
                                "native_returned_tokens": counter.count(json.dumps(result, ensure_ascii=False)),
                                "sources": result["results"]}
                    context = stage("context:" + key, get_context)
                    if key in report["answers"]:
                        continue
                    row = {"engine": engine, "id": case["id"], "answerable": case["answerable"],
                           "status": "interrupted", "provider_usage": provider_usage(None),
                           "endpoint_roundtrip_ms": None, "scores": {"normalized_exact_match": 0.0,
                           "lexical_token_f1": 0.0 if case["answerable"] else None, "abstained": False}}
                    report["answers"][key] = row
                    save()
                    if context["status"] != "completed":
                        row["status"] = "retrieval_error"
                    else:
                        text = context["result"]["context"]
                        if counter.count(text) > 512 or len(text) > 8000:
                            raise ValueError("Context budget invariant failed")
                        body = {"model": args.model, "temperature": 0.0, "max_tokens": 128,
                                "messages": [{"role": "system", "content": PROMPT},
                                {"role": "user", "content": f"Question: {case['query']}\n\nHistorical evidence:\n{text}"}]}
                        row["request_sha256"] = digest(body)
                        result = call_endpoint(completion_url(args.base_url), body, None, 180)
                        row.update(result)
                        if row["status"] == "ok" and row["served_model"] != args.model:
                            row["status"] = "model_identity_mismatch"
                        if row["status"] == "ok":
                            row["scores"] = answer_scores(row["answer"], case)
                    save()
        finally:
            native.close()
    report["source_unchanged"] = engine_source_hash(source) == identity["source_sha256"]
    report["book_storage_closed"] = database_file_bytes(root / "book.db")
    report["native_storage_bytes"] = sum(path.stat().st_size for path in (root / "ai-memory").rglob("*")
                                         if path.is_file() and not path.is_symlink())
    report["summary"] = summarize(report, trace)
    finished = len(report["answers"]) == 72 and report["source_unchanged"]
    problems = any(not operation_succeeded(k, r) for k, r in report["stages"].items())
    problems = problems or any(r["status"] != "ok" for r in report["answers"].values())
    report["status"] = ("completed_with_failures" if problems else "completed") if finished else "incomplete"
    save()
    public = {"evaluator": VERSION, "identity": identity, "identity_sha256": identity_hash,
              "status": report["status"], "summary": report["summary"], "answers": list(report["answers"].values()),
              "stage_statuses": {k: {f: v for f, v in r.items() if f != "result"} for k, r in report["stages"].items()},
              "capture_results": {k: r.get("result") for k, r in report["stages"].items()
                                  if k.startswith("native-capture:")},
              "embedding_result": report["stages"].get("native-embed", {}).get("result"),
              "consolidation_outputs": {k: r.get("result") for k, r in report["stages"].items() if k.startswith("native-consolidate:")},
              "contexts": {k: {f: v for f, v in r.get("result", {}).items() if f not in {"search", "reads"}}
                           for k, r in report["stages"].items() if k.startswith("context:")},
              "native_startups": report.get("native_startups"),
              "book_startups_ms": report.get("book_startups_ms"),
              "model_server_runs": report.get("model_server_runs"),
              "storage": {"book": report["book_storage_closed"], "native_directory_bytes": report["native_storage_bytes"],
                          "native_boundary": "Persistent native sandbox including logs, SQLite and wiki Git history; shared embedding model symlink excluded."},
              "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "native_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest() if trace.exists() else None}
    events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    public["native_model_calls"] = [{k: v for k, v in event.items() if k != "request"} for event in events]
    public["native_http_trace_sha256"] = file_sha256(root / "ai-memory/native-http-trace.jsonl")
    atomic(args.summary, public)
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:18081/v1")
    parser.add_argument("--model", default="qwen2.5-0.5b-instruct-q4_k_m")
    parser.add_argument("--cache", type=Path, default=Path(".artifacts/competitors/ai-memory"))
    parser.add_argument("--launch-server", action="store_true")
    parser.add_argument("--model-cache", type=Path, default=Path(".artifacts/local-answer"))
    parser.add_argument("--output", type=Path, default=Path(".artifacts/full-workflow"))
    parser.add_argument("--summary", type=Path, default=Path("benchmarks/results/full-workflow-transfer36.json"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        plan, sessions, cases = inputs()
        print(json.dumps({"queries": len(cases), "sessions": len(sessions),
                          "plan_sha256": digest(plan), "sessions_sha256": digest(sessions),
                          "answers_sha256": hashlib.sha256(ANSWERS.read_bytes()).hexdigest(),
                          "model_calls": 0}, ensure_ascii=False))
    else:
        report = run(args)
        return 0 if report["status"] == "completed" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
