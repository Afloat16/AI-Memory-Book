"""Development-only whole-workload profile without mutating production sources."""
from __future__ import annotations

import argparse
from collections import Counter
import cProfile
import hashlib
import json
import os
from pathlib import Path
import pstats
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]


def run(args):
    sys.path[:0] = [str(Path(args.source).resolve()), str(ROOT)]
    os.environ['MEMORY_BOOK_TEXT_BACKEND'] = 'native'
    from memory_book import MemoryBook, text
    from memory_book import _native
    from benchmarks.data import generate_dataset
    from benchmarks.public_data import load_locomo
    datasets = {'synthetic61': generate_dataset(seed=61, split='development', projects=8),
                'public1015': load_locomo(Path(args.locomo))}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result = {'status': 'development-profile-not-a-speed-comparison',
              'baseline_commit': '234891619d7bed88ddf3fae37e7f3e1b14a808b6',
              'native_sha256': hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest(),
              'python': sys.version, 'cohorts': {}}
    for name, data in datasets.items():
        print('profiling', name, flush=True)
        record = {'dataset': data.description(), 'stages': {}}
        with tempfile.TemporaryDirectory(prefix='profile-', dir=output) as directory:
            with MemoryBook(Path(directory) / 'memory.db', cache_size=0) as book:
                calls = Counter()
                def trace(frame, event, arg):
                    if event == 'c_call' and getattr(arg, '__self__', None) is _native:
                        calls[getattr(arg, '__name__', '?')] += 1
                stages = {
                    'ingest': lambda: [book.ingest(s) for s in data.sessions],
                    'recall_char2400': lambda: [book.recall(q.query, project=q.project, limit=5,
                        budget_chars=2400, use_cache=False) for q in data.queries],
                }
                for stage, action in stages.items():
                    profiler = cProfile.Profile()
                    start = time.perf_counter()
                    profiler.runcall(action)
                    elapsed = time.perf_counter() - start
                    profiler.dump_stats(str(output / (name + '-' + stage + '.pstats')))
                    stats = pstats.Stats(profiler)
                    entries = []
                    for (file, line, function), (primitive, total, own, cumulative, callers) in stats.stats.items():
                        entries.append({'file': file, 'line': line, 'function': function,
                                        'calls': total, 'own_s': own, 'cumulative_s': cumulative})
                    record['stages'][stage] = {'profiled_wall_s': elapsed,
                        'top_own': sorted(entries, key=lambda r: -r['own_s'])[:60],
                        'top_cumulative': sorted(entries, key=lambda r: -r['cumulative_s'])[:60]}
                    print(name, stage, round(elapsed, 3), flush=True)
                # A second, untimed replay observes actual native calls without
                # replacing any bound method or affecting identity guards.
                for stage, action in stages.items():
                    calls.clear()
                    if stage == 'ingest':
                        # Alter a title deterministically so ingestion performs
                        # work; this profile is separate from the formal input.
                        replay = [dict(s, title=s.get('title', '') + ' profile') for s in data.sessions]
                        action = lambda: [book.ingest(s) for s in replay]
                    sys.setprofile(trace)
                    try:
                        action()
                    finally:
                        sys.setprofile(None)
                    record['stages'][stage]['native_calls'] = dict(calls)
                record['excerpt_window_ready'] = text._native_excerpt_window_ready()
        result['cohorts'][name] = record
        (output / 'profile.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'output': str(output / 'profile.json'),
                      'cohorts': list(result['cohorts'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--locomo', required=True)
    parser.add_argument('--output', required=True)
    run(parser.parse_args())
