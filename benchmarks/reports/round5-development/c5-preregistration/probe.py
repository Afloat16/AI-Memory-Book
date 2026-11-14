"""One observational C4 count trace, with four cold bounded-memo simulations.

Every real count still executes. Instrumented count duration is work-attribution
evidence only, never an end-to-end latency or release speed claim.
"""
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "candidate-v0.3.3-c4/src"
sys.path[:0] = [str(SOURCE), str(ROOT)]
from memory_book import MemoryBook
from memory_book.token_budget import TokenCounter, _ORDINARY_COUNT
from benchmarks.run import engine_source_hash
from scripts.benchmark_default_recall import dataset, digest, indexed_content
from benchmarks.semantic_eval import source_snapshot

RUNTIME = "1c7c644c5187332e6fb5034fef0e232b5c1ae1e5f352b53fea90f7fd8acc4fb3"
OUTPUT = ROOT / ".artifacts/round5-c5-token-reuse-probe.json"
STATE = ROOT / ".artifacts/round5-c5-token-reuse-probe"
SETTINGS = ((256, 1048576), (512, 1048576), (512, 2097152), (1024, 4194304))


class Memo:
    def __init__(self, entries, limit):
        self.label = f"{entries}-entries-{limit}-text-object-bytes"
        self.entries, self.limit = entries, limit
        self.items = OrderedDict()
        self.bytes = 0
        self.stats = dict(hit_calls=0, hit_utf8_bytes=0, hit_count_duration_ns=0, evictions=0,
                          oversized=0, peak_entries=0, peak_text_object_bytes=0, peak_container_bytes=0)

    def lookup(self, key):
        if key in self.items:
            self.items.move_to_end(key)
            return self.items[key][0]
        return None

    def finish(self, key, count, size, utf8_bytes, duration, hit):
        if hit:
            assert self.items[key][0] == count
            self.stats["hit_calls"] += 1
            self.stats["hit_utf8_bytes"] += utf8_bytes
            self.stats["hit_count_duration_ns"] += duration
        elif size > self.limit:
            self.stats["oversized"] += 1
        else:
            while self.items and (len(self.items) >= self.entries or self.bytes + size > self.limit):
                _, (_, old_size) = self.items.popitem(last=False)
                self.bytes -= old_size
                self.stats["evictions"] += 1
            self.items[key] = (count, size)
            self.bytes += size
        self.stats["peak_entries"] = max(self.stats["peak_entries"], len(self.items))
        self.stats["peak_text_object_bytes"] = max(self.stats["peak_text_object_bytes"], self.bytes)
        self.stats["peak_container_bytes"] = max(self.stats["peak_container_bytes"], sys.getsizeof(self.items))
        assert len(self.items) <= self.entries and self.bytes <= self.limit

    def snapshot(self):
        return {**self.stats, "current_entries": len(self.items), "current_text_object_bytes": self.bytes,
                "entry_limit": self.entries, "text_object_byte_limit": self.limit}


assert not OUTPUT.exists()
STATE.mkdir(exist_ok=False)
assert engine_source_hash(SOURCE / "memory_book") == RUNTIME
reference_path = ROOT / ".artifacts/round5-c4-full-paired/public1015-0-candidate.json"
reference_raw = reference_path.read_bytes()
reference = json.loads(reference_raw)
original = next(cell["rows"] for cell in reference["cells"] if cell["configuration"] == "native-token1024")
data = dataset("public1015", ROOT / ".artifacts/locomo10.json")
cases = {case.id: case for case in data.queries}
assert len(original) == len(cases) == 1015 and {row["query_id"] for row in original} == set(cases)
counter = TokenCounter("cl100k_base")
counter.count("Initialize outside the observed calls.")
encoding_identity = (id(counter.encoding), id(counter.encoding._core_bpe))
database = ROOT / ".artifacts/round5-development-dbs/public1015.db"
assert not Path(str(database) + "-wal").stat().st_size
shutil.copyfile(database, STATE / "book.db")
memos = [Memo(*setting) for setting in SETTINGS]
report = dict(status="running", boundary=__doc__, runtime_source_commit="0141adf1dde6cd69cf96d8eea23f4b6ebab36477",
    runtime_sha256=RUNTIME, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    reference_sha256=hashlib.sha256(reference_raw).hexdigest(), dataset_sha256=data.fingerprint,
    order="Exact saved C4 development public round0/native-token1024 shuffled order; one pass, initially empty per-connection simulations.",
    eligible="Native str inputs beginning with '[' and containing a citation LF plus nonempty evidence; other exact count calls are observed but never simulated as cacheable.",
    memory_boundary="Capacity counts sys.getsizeof(str), not character count. Container/key/count overhead is separate; no query/result cache is simulated.",
    started_at=datetime.now(timezone.utc).isoformat(), queries=[], count_trace=[], cold_prefixes={})
pending = {}
current = None


def observe(frame, event, value):
    if frame.f_code is not _ORDINARY_COUNT.__code__ or event not in ("call", "return"):
        return
    if event == "call":
        text, owner = frame.f_locals["text"], frame.f_locals["self"]
        raw = text.encode("utf-8", "surrogatepass")
        eligible = type(text) is str and text.startswith("[") and "\n" in text and bool(text.partition("\n")[2])
        key = (owner.name, id(owner.encoding), id(owner.encoding._core_bpe), text)
        assert key[1:3] == encoding_identity
        hits = [memo.lookup(key) is not None for memo in memos] if eligible else [False] * len(memos)
        pending[id(frame)] = (key, hits, dict(query_id=current["query_id"], caller=frame.f_back.f_code.co_name,
            text_sha256=hashlib.sha256(raw).hexdigest(), text_chars=len(text), utf8_bytes=len(raw),
            text_object_bytes=sys.getsizeof(text), eligible=eligible), time.perf_counter_ns())
    else:
        duration = time.perf_counter_ns()
        key, hits, row, began = pending.pop(id(frame))
        duration -= began
        row.update(count_duration_ns=duration, count=value, cache_hits={memo.label: hit for memo, hit in zip(memos, hits)})
        assert type(value) is int
        if row["eligible"]:
            for memo, hit in zip(memos, hits):
                memo.finish(key, value, row["text_object_bytes"], row["utf8_bytes"], duration, hit)
        report["count_trace"].append(row)
        current["count_calls"] += 1
        current["eligible_calls"] += int(row["eligible"])


def save():
    temporary = OUTPUT.with_suffix(".partial")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(OUTPUT)


save()
try:
    with MemoryBook(STATE / "book.db", cache_size=0) as book:
        before = (source_snapshot(book.db), indexed_content(book.db), book.revision)
        for sequence, expected in enumerate(original, 1):
            case = cases[expected["query_id"]]
            current = dict(query_id=case.id, count_calls=0, eligible_calls=0)
            previous = sys.getprofile()
            sys.setprofile(observe)
            try:
                response = book.recall(case.query, project=case.project, budget_chars=8000,
                                       budget_tokens=1024, tokenizer="cl100k_base", use_cache=False)
            finally:
                sys.setprofile(previous)
            response.pop("latency_ms")
            current["payload_sha256"] = digest(response)
            assert current["payload_sha256"] == expected["payload_sha256"]
            report["queries"].append(current)
            if sequence in (1, 10, 50, 100, 256, 512, 1015):
                report["cold_prefixes"][str(sequence)] = {memo.label: memo.snapshot() for memo in memos}
            if sequence % 128 == 0:
                save()
        assert before == (source_snapshot(book.db), indexed_content(book.db), book.revision)
        assert book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0
    report["totals"] = {key: sum(row[key] for row in report["count_trace"]) for key in ("utf8_bytes", "count_duration_ns")}
    report["totals"].update(count_calls=len(report["count_trace"]), eligible_calls=sum(row["eligible"] for row in report["count_trace"]),
        eligible_utf8_bytes=sum(row["utf8_bytes"] for row in report["count_trace"] if row["eligible"]),
        eligible_count_duration_ns=sum(row["count_duration_ns"] for row in report["count_trace"] if row["eligible"]))
    report["simulations"] = {memo.label: memo.snapshot() for memo in memos}
    assert engine_source_hash(SOURCE / "memory_book") == RUNTIME
    report["status"] = "completed"
except BaseException as exc:
    report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    raise
finally:
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
print(json.dumps({"totals": report.get("totals"), "simulations": report.get("simulations")}, sort_keys=True))
