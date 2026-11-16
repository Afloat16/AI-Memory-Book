"""Current native candidate cProfile diagnostic; no release speed claim."""
from __future__ import annotations
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
COMMIT = "b1434ca8b218d096d5506aaea02631ca31306d21"

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()

def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout

def main():
    output = OUT / "native_language_candidate_profile.json"
    if output.exists():
        raise ValueError("Preserve the first diagnostic; output already exists")
    source = ROOT / "src"
    def source_hashes():
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source / "memory_book").rglob("*"))
            if path.is_file() and path.suffix in {".py", ".c", ".so", ".pyd"}}
    hashes = source_hashes()
    sys.path[:0] = [str(source), str(ROOT)]
    os.environ["MEMORY_BOOK_TEXT_BACKEND"] = "native"
    from memory_book import MemoryBook
    import memory_book
    from scripts.benchmark_default_recall import dataset
    if Path(memory_book.__file__).resolve().parent != source / "memory_book":
        raise ValueError("Different runtime imported")
    data = dataset("synthetic61", None)
    report = {"schema_version": 1, "purpose": "Current C-extension candidate default-path cProfile diagnostic; profiler overhead included; no speed or quality claim.",
        "baseline_commit": COMMIT, "runtime_files_sha256": hashes,
        "runtime_manifest_sha256": digest(hashes),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "cohort": data.description(),
        "configuration": {"budget_chars": 2400, "limit": 5,
            "cache_size": 0, "use_cache": False, "semantic": False}, "profiles": {}}
    with tempfile.TemporaryDirectory(prefix="native-language-profile-", dir=OUT) as work:
        with MemoryBook(Path(work) / "memory.db", cache_size=0) as book:
            for label in ("ingestion", "native-char2400"):
                profiler = cProfile.Profile()
                if label == "ingestion":
                    profiler.enable()
                    results = [book.ingest(session) for session in data.sessions]
                    profiler.disable()
                    payload = {"sessions": len(results), "results_sha256": digest(results)}
                else:
                    rows = []
                    for case in data.queries:
                        profiler.enable()
                        response = book.recall(case.query, project=case.project,
                            budget_chars=2400, limit=5, use_cache=False)
                        profiler.disable()
                        response.pop("latency_ms")
                        rows.append({"query_id": case.id, "payload_sha256": digest(response)})
                    payload = {"queries": len(rows), "rows": rows}
                profiler.dump_stats(OUT / ("native_language_" + label + ".pstats"))
                stats = pstats.Stats(profiler)
                functions = []
                for (path, line, name), (primitive, total, own, cumulative, _) in stats.stats.items():
                    if "/memory_book/" not in path and path != "~":
                        continue
                    shown = "src/memory_book/" + path.split("/memory_book/", 1)[1] if "/memory_book/" in path else path
                    functions.append({"path": shown, "line": line, "function": name,
                        "primitive_calls": primitive, "total_calls": total,
                        "self_seconds": own, "cumulative_seconds": cumulative})
                report["profiles"][label] = {**payload, "profile_total_seconds": stats.total_tt,
                    "top_self": sorted(functions, key=lambda x: x["self_seconds"], reverse=True)[:35],
                    "top_cumulative": sorted(functions, key=lambda x: x["cumulative_seconds"], reverse=True)[:35]}
    report["runtime_files_sha256_after"] = source_hashes()
    report["runtime_sources_unchanged"] = hashes == report["runtime_files_sha256_after"]
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "profiles": {name: {
        "total_seconds": cell["profile_total_seconds"], "top_self": cell["top_self"][:10]}
        for name, cell in report["profiles"].items()}}, indent=2))

if __name__ == "__main__":
    main()
