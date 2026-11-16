"""Read-only diagnostic: profile native v0.8.0 with an in-memory database.

Run from repository root with PYTHONPATH=src:. MEMORY_BOOK_TEXT_BACKEND=native.
These cProfile elapsed-time shares locate candidate work; they are not formal
performance claims, CPU utilization measurements, or a backend speed comparison.
"""
import cProfile
import hashlib
import json
import platform
import pstats
import subprocess
import time
from pathlib import Path

from benchmarks.data import generate_dataset
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME, NATIVE

OUT = Path('.artifacts/v09-profile')
SOURCES = ('src/memory_book/text.py', 'src/memory_book/store.py',
           'src/memory_book/_native.c')


def hashes():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCES}


def capture(label, function):
    profile = cProfile.Profile()
    start = time.perf_counter()
    profile.runcall(function)
    elapsed = time.perf_counter() - start
    stats = pstats.Stats(profile)
    rows = []
    for (filename, line, function), values in stats.stats.items():
        primitive, total, own, cumulative, _ = values
        rows.append(dict(filename=filename, line=line, function=function,
                         primitive_calls=primitive, total_calls=total,
                         self_seconds=own, cumulative_seconds=cumulative,
                         self_pct=100 * own / stats.total_tt,
                         cumulative_pct=100 * cumulative / stats.total_tt))
    return dict(label=label, elapsed_wall_seconds=elapsed,
                profile_total_seconds=stats.total_tt, total_calls=stats.total_calls,
                functions=rows,
                top_cumulative=sorted(rows, key=lambda r: r['cumulative_seconds'],
                                      reverse=True)[:35],
                top_self=sorted(rows, key=lambda r: r['self_seconds'],
                                reverse=True)[:35])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = hashes()
    dataset = generate_dataset(seed=61, split='development', projects=8)
    book = MemoryBook(':memory:', cache_size=0)

    def ingest():
        for session in dataset.sessions:
            book.ingest(session)

    def query():
        for case in dataset.queries:
            book.recall(case.query, project=case.project, budget_chars=2400,
                        limit=5, use_cache=False)

    try:
        fresh = capture('ingest-fresh', ingest)
        unchanged = capture('ingest-unchanged', ingest)
        query()
        recall = capture('recall-3-passes', lambda: [query() for _ in range(3)])
        result = dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                      text=True).strip(),
                      backend=BACKEND_NAME, native_path=NATIVE.__file__,
                      python=platform.python_version(), cohort=dataset.description(),
                      max_page_chars=900, budget_chars=2400, cache_size=0,
                      database=':memory:', input_hashes_before=before,
                      input_hashes_after=hashes(), profiles=[fresh, unchanged, recall])
        destination = OUT / 'synthetic61-native-rerun.json'
        destination.write_text(json.dumps(result, indent=2) + '\n')
        print(destination)
    finally:
        book.close()


if __name__ == '__main__':
    main()
