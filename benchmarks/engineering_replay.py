"""Frozen real-source history replay; retrieval evidence, never agent success.

verify performs no retrieval. bind requires committed evaluator/data and exact
runtime bytes. run claims the binding once, then uses isolated engine workers.
Source records and AI-authored gold are separate; workers hash the frozen gold
file for identity but never parse its annotations or give them to an engine.
"""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import sqlite3
import statistics
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
FIX = Path("benchmarks/fixtures")
PROTOCOL = FIX / "engineering_protocol.json"
MANIFEST = FIX / "engineering_source_manifest.json"
CASES = FIX / "engineering_cases.json"
UPSTREAM = FIX / "engineering_upstream.json"
GOLD = FIX / "engineering_gold.json"
ANCESTRY = FIX / "engineering_ancestry.json"
ARMS = ("flat-fts", "v0.3.4", "candidate", "billion-context")
LOCK = Path("benchmarks/competitors/billion-round2-lock.json")
STOP = frozenset("a an the in on at of to for from and or is are was were be been "
                 "what which where when how does do did with before after show "
                 "locate current earlier later our this that it its their them "
                 "we can by as rather than together into".split())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def atomic(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("xb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def append_event(path, event):
    with Path(path).open("ab") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def utc():
    return datetime.now(timezone.utc).isoformat()


def bounded_path(root, relative):
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def source_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def chunks(record):
    """Original nonoverlapping character intervals; never query-dependent."""
    text = record["text"]
    start = 0
    while start < len(text):
        end = min(start + 900, len(text))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline >= start:
                end = newline + 1
        line_start = text.count("\n", 0, start) + 1
        line_end = text.count("\n", 0, max(start, end - 1)) + 1
        block_id = record["id"] + f":{start}:{end}"
        title = (f'{record["repository"]} {record["commit"]} {record["path"]} '
                 f'lines {line_start}-{line_end} {record["committer_utc"]}')
        yield {"id": block_id, "source_id": record["id"],
               "project": record["repository"], "commit": record["commit"],
               "path": record["path"], "created_at": record["committer_utc"],
               "title": title, "text": text[start:end], "start_char": start,
               "end_char": end, "start_line": line_start, "end_line": line_end}
        start = end


def load_inputs(root=ROOT):
    root = Path(root)
    protocol, manifest = read_json(root / PROTOCOL), read_json(root / MANIFEST)
    for name, expected in manifest["input_hashes"].items():
        if digest(bounded_path(root, name).read_bytes()) != expected:
            raise ValueError("Frozen input differs: " + name)
    fixture_data = {}
    for entry in manifest["source_fixtures"]:
        path = bounded_path(root, entry["path"])
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or digest(raw) != entry["sha256"]:
            raise ValueError("Source fixture differs: " + entry["path"])
        fixture_data[entry["path"]] = json.loads(raw)
    records = {}
    for meta in manifest["records"]:
        original = fixture_data[meta["fixture"]]["records"][meta["record_index"]]
        raw = base64.b64decode(original["content"], validate=True)
        for key in ("repository", "commit", "path", "kind", "phase",
                    "committer_utc", "author_utc", "git_blob_sha"):
            if original[key] != meta[key]:
                raise ValueError("Source metadata differs: " + key)
        if (source_blob(raw) != original["git_blob_sha"]
                or len(raw) != meta["utf8_bytes"] or digest(raw) != meta["sha256"]):
            raise ValueError("Raw bytes do not match upstream Git blob")
        text = raw.decode("utf-8")
        if len(text) != meta["unicode_characters"] or meta["id"] in records:
            raise ValueError("Source identity/length mismatch")
        records[meta["id"]] = {**meta, "text": text}
    cases = read_json(root / CASES)["queries"]
    if (len(cases) != 20 or len({q["id"] for q in cases}) != 20
            or len(records) != 40 or sum(r["kind"] == "license" for r in records.values()) != 8):
        raise ValueError("The registered source/query denominator changed")
    proofs = read_json(root / ANCESTRY)["records"]
    ancestors = set()
    for p in proofs:
        if (not p["ancestor_verified"] or p["status"] != "ahead"
                or p["merge_base_sha"] != p["earlier"] or p["base_sha"] != p["earlier"]
                or p["behind_by"] != 0):
            raise ValueError("Invalid official ancestry receipt")
        ancestors.add((p["repo"], p["earlier"], p["later"]))
    if len(ancestors) != 12:
        raise ValueError("The registered ancestry matrix is incomplete")
    blocks = [b for r in records.values() if r["kind"] != "license" for b in chunks(r)]
    return {"protocol": protocol, "manifest": manifest, "cases": cases,
            "records": records, "blocks": blocks, "ancestors": ancestors}


def eligible_blocks(inputs, case):
    visible = case["public_input"]
    if visible["target_repo"] != case["project"]:
        raise ValueError("Public project inputs disagree")
    commit, cutoff = visible["snapshot_commit"], visible["availability_cutoff_utc"]
    result = []
    for block in inputs["blocks"]:
        if block["project"] != case["project"] or block["created_at"] > cutoff:
            continue
        if (block["commit"] == commit
                or (case["project"], block["commit"], commit) in inputs["ancestors"]):
            result.append(block)
    return sorted(result, key=lambda b: (b["created_at"], b["id"]))


def validate_gold(inputs, gold):
    if set(gold["queries"]) != {q["id"] for q in inputs["cases"]}:
        raise ValueError("Gold/query identities disagree")
    for case in inputs["cases"]:
        label = gold["queries"][case["id"]]
        allowed = {b["source_id"] for b in eligible_blocks(inputs, case)}
        if label["answerable"] != bool(label["required_spans"]):
            raise ValueError("Answerable label lacks original evidence")
        for span in label["required_spans"] + label["stale_spans"]:
            original = inputs["records"].get(span["source_id"])
            if original is None or original["kind"] == "license" or span["source_id"] not in allowed:
                raise ValueError("Gold refers to missing or future source")
            start, end = span["start_char"], span["end_char"]
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original["text"])
                    or original["text"][start:end] != span["quote"]
                    or digest(span["quote"].encode()) != span["quote_sha256"]):
                raise ValueError("Gold quote is not the exact original span")


def identifier_terms(text):
    literal = re.findall(r"\w+", text, flags=re.UNICODE)
    split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", split).replace("_", " ")
    pieces = re.findall(r"\w+", split, flags=re.UNICODE)
    return sorted({x.casefold() for x in literal + pieces if x})


class FlatFTS:
    def __init__(self, blocks, state):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE VIRTUAL TABLE evidence USING fts5(id UNINDEXED, metadata, text)")
        self.db.executemany("INSERT INTO evidence VALUES(?,?,?)", [
            (b["id"], " ".join(identifier_terms(b["title"])),
             " ".join(identifier_terms(b["text"]))) for b in blocks])
        self.metadata = {"implementation": "independent FTS5 BM25, literal and identifier pieces",
                         "sqlite": sqlite3.sqlite_version, "state_file_bytes": 0}

    def search(self, query, project):
        terms = [t for t in identifier_terms(query) if t not in STOP]
        if not terms:
            rows = []
        else:
            expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
            rows = self.db.execute(
                "SELECT id,bm25(evidence) score FROM evidence WHERE evidence MATCH ? "
                "ORDER BY score,id LIMIT 5", (expression,)).fetchall()
        payload = {"results": [{"id": row[0], "score": row[1]} for row in rows]}
        return [row[0] for row in rows], payload

    def close(self):
        self.db.close()


def runtime_hash(source):
    package = Path(source).resolve() / "memory_book"
    h = hashlib.sha256()
    paths = sorted(package.rglob("*.py"))
    if not paths or any(p.is_symlink() for p in paths):
        raise ValueError("Missing or symlinked runtime")
    for path in paths:
        h.update(path.relative_to(package).as_posix().encode() + b"\0")
        h.update(path.read_bytes() + b"\0")
    return h.hexdigest()


def git_bytes(commit, path):
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
                          check=True, capture_output=True).stdout


def verify_runtime(source, expected):
    source = Path(source).resolve()
    if runtime_hash(source) != expected["runtime_sha256"]:
        raise ValueError("Runtime byte hash differs from binding")
    package = source / "memory_book"
    committed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", expected["commit"], "--", "src/memory_book"],
        check=True, capture_output=True, text=True).stdout.splitlines()
    actual = {"src/memory_book/" + p.relative_to(package).as_posix(): p
              for p in package.rglob("*.py")}
    if set(actual) != {p for p in committed if p.endswith(".py")}:
        raise ValueError("Runtime file set differs from exact commit")
    for relative, path in actual.items():
        if path.read_bytes() != git_bytes(expected["commit"], relative):
            raise ValueError("Runtime file differs from exact commit: " + relative)


class BookEngine:
    def __init__(self, blocks, state, source, expected):
        source = Path(source).resolve()
        verify_runtime(source, expected)
        sys.path.insert(0, str(source))
        import memory_book
        from memory_book import MemoryBook
        if Path(memory_book.__file__).resolve().parent != source / "memory_book":
            raise ValueError("Imported a different MemoryBook")
        self.path = state / "book.sqlite3"
        self.book = MemoryBook(self.path, max_page_chars=900, cache_size=0)
        for block in blocks:
            self.book.ingest({"project": block["project"], "session_id": block["id"],
                             "title": block["title"], "task_id": block["path"],
                             "task_title": block["path"], "created_at": block["created_at"],
                             "messages": [{"role": "assistant", "content": block["text"]}]})
        self.metadata = {"source": expected, "imported_package": str(source / "memory_book"),
                         "stats_after_ingestion": self.book.stats(),
                         "boundary": "Python recall and native context assembly; original-block readback separate"}

    def search(self, query, project):
        payload = self.book.recall(query, project=project, budget_chars=100000,
                                   limit=5, use_cache=False, coverage=False, semantic=False)
        ids = []
        if len(payload["results"]) > 5:
            raise ValueError("Native result limit exceeded")
        for hit in payload["results"]:
            references = hit["source_refs"]
            mapped = {r["session_id"] for r in references}
            if len(mapped) != 1 or any(r["project"] != project for r in references):
                raise ValueError("Book hit does not map to one correctly scoped original block")
            ids.append(next(iter(mapped)))
        return ids, payload

    def close(self):
        self.metadata["stats_after_retrieval"] = self.book.stats()
        self.book.close()
        self.metadata["state_file_bytes"] = sum(
            p.stat().st_size for p in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm"))
            if p.exists())


class BillionEngine:
    def __init__(self, blocks, state, cache):
        sys.path.insert(0, str(ROOT))
        from benchmarks.competitors.billion import BillionKernel
        self.engine = BillionKernel(blocks, cache, offline=True, lock_path=ROOT / LOCK)
        self.metadata = {**self.engine.metadata, "state_file_bytes": 0,
                         "state_boundary": "No generated retrieval database; pinned source/cache and harness artifacts excluded"}

    def search(self, query, project):
        payload = self.engine.search(query, project=project, limit=5)
        return [r["ref"] for r in payload["results"]], payload

    def close(self):
        self.engine.close()


def source_block_text(block):
    return "[" + block["title"] + "]\n" + block["text"]


def pack_blocks(ids, block_map, budget, counter):
    kept, rendered = [], []
    for identity in ids:
        block = block_map[identity]
        text = source_block_text(block)
        proposed = "\n\n".join(rendered + [text])
        if counter(proposed) <= budget:
            kept.append(identity)
            rendered.append(text)
    context = "\n\n".join(rendered)
    return {"budget_tokens": budget, "block_ids": kept, "context": context,
            "context_sha256": digest(context.encode()), "context_tokens": counter(context)}


def checked_ids(native_ids, block_map, project, limit=5):
    if not isinstance(native_ids, list) or len(native_ids) > limit:
        raise ValueError("Invalid native result count")
    unique = []
    for identity in native_ids:
        if identity not in block_map or block_map[identity]["project"] != project:
            raise ValueError("Unknown, wrong-project or future source ID")
        if identity not in unique:
            unique.append(identity)
    return unique


def native_ids_from_payload(arm, payload, project):
    rows = payload["results"]
    if not isinstance(rows, list) or len(rows) > 5:
        raise ValueError("Saved native response has an invalid result count")
    if arm == "flat-fts":
        return [r["id"] for r in rows]
    if arm == "billion-context":
        return [r["ref"] for r in rows]
    identities = []
    for row in rows:
        refs = row["source_refs"]
        mapped = {r["session_id"] for r in refs}
        if len(mapped) != 1 or any(r["project"] != project for r in refs):
            raise ValueError("Saved Book reference scope differs")
        identities.append(next(iter(mapped)))
    return identities


def covered(span, blocks):
    intervals = sorted((b["start_char"], b["end_char"]) for b in blocks
                       if b["source_id"] == span["source_id"])
    cursor = span["start_char"]
    for start, end in intervals:
        if start > cursor:
            break
        if end > cursor:
            cursor = end
        if cursor >= span["end_char"]:
            return True
    return False


def evidence_score(label, blocks):
    required = label["required_spans"]
    matches = sum(covered(span, blocks) for span in required)
    ranks = []
    for span in required:
        ranks.append(next((i for i in range(1, len(blocks) + 1) if covered(span, blocks[:i])), None))
    first = min((r for r in ranks if r is not None), default=None)
    stale_ranks = [next((i for i in range(1, len(blocks) + 1) if covered(s, blocks[:i])), None)
                   for s in label["stale_spans"]]
    first_stale = min((r for r in stale_ranks if r is not None), default=None)
    return {"answerable": label["answerable"], "required_spans": len(required),
            "matched_spans": matches,
            "evidence_recall": matches / len(required) if required else None,
            "complete_evidence": matches == len(required) if required else None,
            "first_evidence_rank": first, "reciprocal_rank": 1 / first if first else 0 if required else None,
            "stale_evidence": first_stale is not None,
            "stale_only": first_stale is not None and first is None,
            "stale_before_current": first_stale is not None and first is not None and first_stale < first,
            "unsupported_nonempty": bool(blocks) if not required else None}


def evaluator_paths(inputs):
    paths = [Path(__file__).relative_to(ROOT), Path("tests/test_engineering_replay.py"),
             Path("docs/engineering-replay.md"), PROTOCOL, MANIFEST, CASES, UPSTREAM, GOLD, ANCESTRY,
             LOCK, Path("benchmarks/__init__.py"), Path("benchmarks/competitors/__init__.py"),
             Path("benchmarks/competitors/billion.py"), Path("benchmarks/competitors/billion_bridge.mjs"),
             Path("benchmarks/competitors/compile_billion.mjs"), Path("benchmarks/competitors/download.py")]
    paths += [Path(e["path"]) for e in inputs["manifest"]["source_fixtures"]]
    return sorted(set(paths))


def create_binding(args):
    inputs = load_inputs()
    validate_gold(inputs, read_json(ROOT / GOLD))
    baseline = {**inputs["protocol"]["baseline"], "source_root": str(Path(args.baseline_source).resolve())}
    candidate = {"commit": args.candidate_commit, "source_root": str(Path(args.candidate_source).resolve()),
                 "runtime_sha256": runtime_hash(args.candidate_source)}
    for source in (baseline, candidate):
        verify_runtime(source["source_root"], source)
    closure = {}
    for path in evaluator_paths(inputs):
        raw = (ROOT / path).read_bytes()
        if raw != git_bytes(args.evaluator_commit, path.as_posix()):
            raise ValueError("Commit evaluator/data before binding: " + path.as_posix())
        closure[path.as_posix()] = digest(raw)
    binding = {"schema_version": 1, "protocol": inputs["protocol"]["protocol"],
               "status": "frozen-before-first-replay-score", "created_at": utc(),
               "evaluator_commit": args.evaluator_commit, "evaluator_files": closure,
               "sources": {"v0.3.4": baseline, "candidate": candidate},
               "protocol_sha256": digest((ROOT / PROTOCOL).read_bytes()),
               "billion_cache": str(Path(args.billion_cache).resolve()),
               "expected_matrix": inputs["protocol"]["matrix"], "generation": "none"}
    atomic(args.output, binding, exclusive=True)
    return {"binding": str(args.output), "sha256": digest(Path(args.output).read_bytes()), "retrieval_calls": 0}


def validate_binding_identity(binding, protocol, protocol_sha256):
    if (binding.get("schema_version") != 1
            or binding.get("status") != "frozen-before-first-replay-score"
            or binding.get("generation") != "none"
            or binding.get("protocol") != protocol["protocol"]
            or binding.get("protocol_sha256") != protocol_sha256
            or binding.get("expected_matrix") != protocol["matrix"]
            or set(binding.get("sources", {})) != {"v0.3.4", "candidate"}):
        raise ValueError("Binding does not identify the registered protocol/matrix")
    baseline = binding["sources"]["v0.3.4"]
    if any(baseline.get(key) != value for key, value in protocol["baseline"].items()):
        raise ValueError("Binding replaced the registered baseline")
    for source in binding["sources"].values():
        if (not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", source.get("runtime_sha256", ""))
                or not isinstance(source.get("source_root"), str)):
            raise ValueError("Binding lacks an exact source identity")


def verify_binding(path):
    path = Path(path).resolve()
    relative = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    if raw != git_bytes("HEAD", relative):
        raise ValueError("Commit the exact binding before any replay execution")
    binding = json.loads(raw)
    inputs = load_inputs()
    validate_binding_identity(binding, inputs["protocol"], digest((ROOT / PROTOCOL).read_bytes()))
    if set(binding["evaluator_files"]) != {p.as_posix() for p in evaluator_paths(inputs)}:
        raise ValueError("Evaluator closure changed")
    for name, expected in binding["evaluator_files"].items():
        data = bounded_path(ROOT, name).read_bytes()
        if digest(data) != expected or data != git_bytes(binding["evaluator_commit"], name):
            raise ValueError("Bound evaluator/input identity differs: " + name)
    for expected in binding["sources"].values():
        verify_runtime(expected["source_root"], expected)
    return binding, digest(raw), inputs


def claim_key(binding):
    return digest(encoded({"protocol_sha256": binding["protocol_sha256"],
                           "runtime_pair": {name: value["runtime_sha256"]
                                            for name, value in binding["sources"].items()}}))


def plan_cases(cases):
    shuffled = list(cases)
    random.Random(7321).shuffle(shuffled)
    grouped = {}
    for case in shuffled:
        key = case["project"] + "@" + case["public_input"]["snapshot_commit"]
        grouped.setdefault(key, []).append(case)
    return list(grouped.items())


def verify_tokenizer():
    if importlib.metadata.version("tiktoken") != "0.12.0":
        raise ValueError("The reference tokenizer version changed")
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")
    return lambda text: len(encoding.encode(text, disallowed_special=()))


def make_engine(arm, blocks, state, binding):
    if arm == "flat-fts":
        return FlatFTS(blocks, state)
    if arm == "billion-context":
        return BillionEngine(blocks, state, Path(binding["billion_cache"]))
    source = binding["sources"][arm]
    return BookEngine(blocks, state, source["source_root"], source)


def worker(args):
    binding, binding_hash, inputs = verify_binding(args.binding)
    run_dir = Path(args.run_dir).resolve()
    claim = read_json(run_dir / "claim.json")
    if claim["binding_sha256"] != binding_hash or claim["run_dir"] != str(run_dir):
        raise ValueError("Worker lacks the exact claimed execution")
    shared_claim = ROOT / ".artifacts/engineering-replay-claims" / (claim_key(binding) + ".json")
    if read_json(shared_claim) != claim:
        raise ValueError("Worker claim differs from the immutable source-pair/protocol claim")
    counter = verify_tokenizer()
    report_path = run_dir / (args.arm + ".json")
    report = {"arm": args.arm, "binding_sha256": binding_hash, "status": "running",
              "rows": [], "setups": [], "started_at": utc(),
              "source_roots": binding["sources"], "gold_loaded_by_worker": False}
    atomic(report_path, report, exclusive=True)
    offset = ARMS.index(args.arm) * 20
    try:
        for view_index, (view, queries) in enumerate(plan_cases(inputs["cases"])):
            state = run_dir / "state" / args.arm / str(view_index)
            state.mkdir(parents=True, exist_ok=False)
            blocks = eligible_blocks(inputs, queries[0])
            block_map = {b["id"]: b for b in blocks}
            setup = {"view": view, "blocks": len(blocks), "source_blocks_sha256": digest(encoded(blocks))}
            start = time.perf_counter_ns()
            engine = make_engine(args.arm, blocks, state, binding)
            setup["setup_ms"] = (time.perf_counter_ns() - start) / 1e6
            try:
                for case in queries:
                    sequence = offset + len(report["rows"])
                    request = {"query_id": case["id"], "query": case["query"],
                               "public_input": case["public_input"], "limit": 5, "view": view}
                    intent = {"event": "intent", "sequence": sequence, "arm": args.arm,
                              "query_id": case["id"], "binding_sha256": binding_hash,
                              "request_sha256": digest(encoded(request)), "at": utc()}
                    append_event(run_dir / "attempts.jsonl", intent)
                    row = {**request, "sequence": sequence, "arm": args.arm, "category": case["category"]}
                    start = time.perf_counter_ns()
                    try:
                        native_ids, payload = engine.search(case["query"], case["project"])
                        row["lookup_wall_ms"] = (time.perf_counter_ns() - start) / 1e6
                        row["native_payload"] = payload
                        row["native_payload_tokens"] = counter(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                        read_start = time.perf_counter_ns()
                        ids = checked_ids(native_ids, block_map, case["project"])
                        selected = [block_map[identity] for identity in ids]
                        row["readback_ms"] = (time.perf_counter_ns() - read_start) / 1e6
                        row["native_ids"] = native_ids
                        row["selected_blocks"] = selected
                        row["source_block_reads"] = len(ids)
                        row["duplicate_native_ids"] = len(native_ids) - len(ids)
                        row["projections"] = []
                        for cap in (1024, 4096):
                            packing_start = time.perf_counter_ns()
                            projection = pack_blocks(ids, block_map, cap, counter)
                            projection["packing_ms"] = (time.perf_counter_ns() - packing_start) / 1e6
                            row["projections"].append(projection)
                        row["status"] = "complete"
                    except Exception:
                        row.update(status="error-or-unknown", elapsed_to_error_ms=(time.perf_counter_ns() - start) / 1e6,
                                   error=traceback.format_exc())
                        report["rows"].append(row)
                        append_event(run_dir / "attempts.jsonl", {"event": "completion", "sequence": sequence,
                                     "arm": args.arm, "query_id": case["id"], "status": row["status"],
                                     "row_sha256": digest(encoded(row)), "at": utc()})
                        atomic(report_path, report)
                        raise
                    report["rows"].append(row)
                    append_event(run_dir / "attempts.jsonl", {"event": "completion", "sequence": sequence,
                                 "arm": args.arm, "query_id": case["id"], "status": row["status"],
                                 "row_sha256": digest(encoded(row)), "at": utc()})
                    atomic(report_path, report)
            finally:
                engine.close()
                setup["metadata"] = engine.metadata
                report["setups"].append(setup)
                atomic(report_path, report)
        if args.arm in binding["sources"]:
            source = binding["sources"][args.arm]
            verify_runtime(source["source_root"], source)
        report["status"] = "complete"
    except Exception:
        report["status"] = "error-or-incomplete"
        report["error"] = traceback.format_exc()
        raise
    finally:
        report["finished_at"] = utc()
        try:
            import resource
            report["worker_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
        except ImportError:
            report["worker_peak_rss_bytes"] = None
        report["rss_scope"] = "Worker peak includes Python evaluator/source data. Live Node child RSS is not measured; no isolated product-RAM comparison."
        atomic(report_path, report)


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def summarize_cells(cells):
    groups = defaultdict(list)
    for cell in cells:
        groups[(cell["arm"], cell["budget_tokens"])].append(cell)
    summaries = []
    for (arm, cap), rows in sorted(groups.items()):
        answerable = [r for r in rows if r["score"]["answerable"]]
        unsupported = [r for r in rows if not r["score"]["answerable"]]
        total = sum(r["score"]["required_spans"] for r in answerable)
        summaries.append({"arm": arm, "budget_tokens": cap, "queries": len(rows),
                          "answerable": len(answerable), "unsupported": len(unsupported),
                          "evidence_recall": sum(r["score"]["matched_spans"] for r in answerable) / total if total else None,
                          "complete_evidence_rate": statistics.mean(r["score"]["complete_evidence"] for r in answerable) if answerable else None,
                          "mean_reciprocal_rank": statistics.mean(r["score"]["reciprocal_rank"] for r in answerable) if answerable else None,
                          "unsupported_nonempty_rate": statistics.mean(r["score"]["unsupported_nonempty"] for r in unsupported) if unsupported else None,
                          "mean_context_tokens": statistics.mean(r["context_tokens"] for r in rows)})
    return summaries


def audit_saved(binding_path, run_dir):
    binding, binding_hash, inputs = verify_binding(binding_path)
    gold = read_json(ROOT / GOLD)
    validate_gold(inputs, gold)
    counter = verify_tokenizer()
    run_dir = Path(run_dir)
    events = [json.loads(line) for line in (run_dir / "attempts.jsonl").read_text().splitlines()]
    if len(events) != 160:
        raise ValueError("Incomplete intent/completion ledger")
    case_map = {c["id"]: c for c in inputs["cases"]}
    cells, rows, costs = [], [], []
    for arm in ARMS:
        report = read_json(run_dir / (arm + ".json"))
        if report["status"] != "complete" or report["binding_sha256"] != binding_hash or report["gold_loaded_by_worker"]:
            raise ValueError("Incomplete or wrong-identity worker report")
        if len(report["rows"]) != 20 or {r["query_id"] for r in report["rows"]} != set(case_map):
            raise ValueError("Worker query denominator differs")
        planned = [case for _, queries in plan_cases(inputs["cases"]) for case in queries]
        for ordinal, row in enumerate(report["rows"]):
            case = case_map[row["query_id"]]
            view = case["project"] + "@" + case["public_input"]["snapshot_commit"]
            request = {"query_id": case["id"], "query": case["query"],
                       "public_input": case["public_input"], "limit": 5, "view": view}
            if (case["id"] != planned[ordinal]["id"] or row["arm"] != arm
                    or row["sequence"] != ARMS.index(arm) * 20 + ordinal
                    or row["status"] != "complete"
                    or any(row.get(k) != v for k, v in request.items())):
                raise ValueError("Saved request/order differs from the registered query")
            available = {b["id"]: b for b in eligible_blocks(inputs, case)}
            if row["native_ids"] != native_ids_from_payload(arm, row["native_payload"], case["project"]):
                raise ValueError("Saved rank IDs differ from the original native response")
            selected = checked_ids(row["native_ids"], available, case["project"])
            if row["selected_blocks"] != [available[x] for x in selected]:
                raise ValueError("Saved source readback differs")
            if (row["source_block_reads"] != len(selected)
                    or row["duplicate_native_ids"] != len(row["native_ids"]) - len(selected)
                    or row["native_payload_tokens"] != counter(json.dumps(
                        row["native_payload"], ensure_ascii=False, separators=(",", ":")))):
                raise ValueError("Saved read/payload accounting differs")
            for name in ("lookup_wall_ms", "readback_ms"):
                value = row[name]
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid observed timing")
            sequence = row["sequence"]
            pair = [e for e in events if e["sequence"] == sequence]
            if (len(pair) != 2 or [e["event"] for e in pair] != ["intent", "completion"]
                    or any(e["arm"] != arm or e["query_id"] != case["id"] for e in pair)
                    or pair[0]["binding_sha256"] != binding_hash
                    or pair[0]["request_sha256"] != digest(encoded(request))
                    or pair[1]["status"] != "complete"
                    or pair[1]["row_sha256"] != digest(encoded(row))):
                raise ValueError("Intent/completion identity mismatch")
            if [p["budget_tokens"] for p in row["projections"]] != [1024, 4096]:
                raise ValueError("Budget matrix differs")
            for projection in row["projections"]:
                value = projection["packing_ms"]
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid common packing timing")
                expected = pack_blocks(selected, available, projection["budget_tokens"], counter)
                if any(projection.get(k) != v for k, v in expected.items()):
                    raise ValueError("Saved common context differs from original blocks")
                visible = [available[x] for x in projection["block_ids"]]
                cells.append({"arm": arm, "query_id": case["id"], "category": case["category"],
                              **projection, "score": evidence_score(gold["queries"][case["id"]], visible)})
            rows.append(row)
        values = [r["lookup_wall_ms"] for r in report["rows"]]
        costs.append({"arm": arm, "lookup_samples": len(values), "lookup_mean_ms": statistics.mean(values),
                      "lookup_p50_ms": percentile(values, .5), "lookup_p95_ms": percentile(values, .95),
                      "setups": report["setups"], "worker_peak_rss_bytes": report["worker_peak_rss_bytes"],
                      "rss_scope": report["rss_scope"]})
    if {r["sequence"] for r in rows} != set(range(80)):
        raise ValueError("Missing/duplicate actual retrieval attempt")
    for case in inputs["cases"]:
        for cap in (1024, 4096):
            cells.append({"arm": "no-memory", "query_id": case["id"], "category": case["category"],
                          "budget_tokens": cap, "block_ids": [], "context": "", "context_tokens": 0,
                          "context_sha256": digest(b""), "lookup_wall_ms": None,
                          "score": evidence_score(gold["queries"][case["id"]], [])})
    summaries = summarize_cells(cells)
    baseline = {(c["query_id"], c["budget_tokens"]): c for c in cells if c["arm"] == "v0.3.4"}
    deltas = []
    for cell in (c for c in cells if c["arm"] != "v0.3.4"):
        before = baseline[cell["query_id"], cell["budget_tokens"]]
        changes = {}
        for name in ("evidence_recall", "complete_evidence", "reciprocal_rank"):
            a, b = before["score"][name], cell["score"][name]
            changes[name] = float(b) - float(a) if a is not None and b is not None else None
        changes["context_tokens"] = cell["context_tokens"] - before["context_tokens"]
        deltas.append({"arm": cell["arm"], "query_id": cell["query_id"],
                       "budget_tokens": cell["budget_tokens"], "changes": changes})
    return {"schema_version": 1, "protocol": binding["protocol"], "status": "complete-verified",
            "binding_sha256": binding_hash, "sources": binding["sources"],
            "evaluator_commit": binding["evaluator_commit"], "matrix": binding["expected_matrix"],
            "integrity_passed": True, "product_acceptance_evaluated": False,
            "generated_answers": 0, "generated_patches": 0, "upstream_test_executions": 0,
            "cells": cells, "summaries": summaries, "costs": costs, "all_deltas_vs_v034": deltas,
            "interpretation": "AI-authored questions over real source. External project/ancestry cutoff control; common source-readback contexts. No native as-of, generated-answer, patch-success, real-user or whole-agent speed claim."}


def run(args):
    binding, binding_hash, inputs = verify_binding(args.binding)
    validate_gold(inputs, read_json(ROOT / GOLD))
    verify_tokenizer()
    if subprocess.run(["node", "--version"], capture_output=True, text=True, check=True).stdout.strip() != "v24.22.1":
        raise ValueError("Node differs from the registered runtime")
    sys.path.insert(0, str(ROOT))
    from benchmarks.competitors.billion import prepare
    prepare(Path(binding["billion_cache"]), offline=True, lock_path=ROOT / LOCK)
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("Never reuse a replay output directory")
    claim_path = ROOT / ".artifacts/engineering-replay-claims" / (claim_key(binding) + ".json")
    claim = {"binding_sha256": binding_hash, "run_dir": str(output), "created_at": utc(),
             "sources": binding["sources"], "matrix": binding["expected_matrix"]}
    atomic(claim_path, claim, exclusive=True)
    output.mkdir(parents=True, exist_ok=False)
    atomic(output / "claim.json", claim, exclusive=True)
    execution = {"status": "claimed", "binding_sha256": binding_hash, "started_at": utc(),
                 "platform": platform.platform(), "python": sys.version, "workers": []}
    atomic(output / "execution.json", execution)
    try:
        for arm in ARMS:
            command = [sys.executable, str(Path(__file__).resolve()), "_worker", "--binding",
                       str(Path(args.binding).resolve()), "--run-dir", str(output), "--arm", arm]
            log = output / (arm + ".log")
            with log.open("wb") as stream:
                result = subprocess.run(command, env={**os.environ, "PYTHONHASHSEED": "0",
                                                      "PYTHONDONTWRITEBYTECODE": "1"},
                                        stdout=stream, stderr=subprocess.STDOUT)
            execution["workers"].append({"arm": arm, "argv": command, "returncode": result.returncode,
                                         "log_sha256": digest(log.read_bytes())})
            atomic(output / "execution.json", execution)
            if result.returncode:
                raise RuntimeError("Worker failed; preserve original evidence and do not retry: " + arm)
        report = audit_saved(args.binding, output)
        atomic(output / "report.json", report, exclusive=True)
        execution["status"] = "complete-verified"
        return {"output": str(output), "retrieval_calls": 80, "quality_cells": 200,
                "integrity_passed": True, "product_acceptance_evaluated": False}
    except Exception:
        execution.update(status="error-or-incomplete", error=traceback.format_exc())
        raise
    finally:
        execution["finished_at"] = utc()
        atomic(output / "execution.json", execution)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="Verify original bytes/labels/visibility; zero retrieval")
    bind = commands.add_parser("bind")
    bind.add_argument("--baseline-source", type=Path, required=True)
    bind.add_argument("--candidate-source", type=Path, required=True)
    bind.add_argument("--candidate-commit", required=True)
    bind.add_argument("--evaluator-commit", required=True)
    bind.add_argument("--billion-cache", type=Path, default=ROOT / ".artifacts/round7-billion-source")
    bind.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--binding", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--binding", type=Path, required=True)
    audit.add_argument("--run-dir", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    child = commands.add_parser("_worker", help=argparse.SUPPRESS)
    child.add_argument("--binding", type=Path, required=True)
    child.add_argument("--run-dir", type=Path, required=True)
    child.add_argument("--arm", choices=ARMS, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        inputs = load_inputs()
        gold = read_json(ROOT / GOLD)
        validate_gold(inputs, gold)
        result = {"verified_upstream_records": len(inputs["records"]), "source_blocks": len(inputs["blocks"]),
                  "queries": len(inputs["cases"]), "gold": gold["counts"], "retrieval_calls": 0,
                  "generated_answers": 0, "upstream_test_executions": 0}
    elif args.command == "bind":
        result = create_binding(args)
    elif args.command == "run":
        result = run(args)
    elif args.command == "audit":
        result = audit_saved(args.binding, args.run_dir)
        atomic(args.output, result, exclusive=True)
        result = {"audit": str(args.output), "integrity_passed": True, "new_retrieval_calls": 0}
    else:
        worker(args)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
