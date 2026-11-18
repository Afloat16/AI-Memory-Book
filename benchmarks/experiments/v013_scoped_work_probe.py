"""Small development diagnosis of scoped-query work as foreign pages grow.

This is an authored, inspected pilot, not a preregistered benchmark. It creates
at most 1,920 one-page sessions per temporary database. Timing includes tracing
and VM callbacks; OS caches are not cleared. All original requests/responses,
inputs and actual SQL query plans are retained. No runtime is modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import cProfile
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pstats
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME


def payload(project, index):
    return {
        'project': project, 'project_name': 'Similar worker service',
        'session_id': 'checkpoint-' + str(index), 'task_id': 'policy-' + str(index % 3),
        'title': 'Production retry policy', 'task_title': 'Worker retry policy',
        'created_at': (datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)).isoformat(),
        'messages': [
            {'role': 'user', 'content': 'What is the production retry_limit configuration?'},
            {'role': 'assistant', 'content': 'production retry_limit=' + str(3 + index % 13)
             + '. Worker retry policy is recorded for recovery after an interruption. '
             + 'Keep the original production setting and its source. Checkpoint ' + str(index) + '.'}],
    }


def inputs(foreign_pages, layout, target_pages=120):
    total = target_pages + foreign_pages
    target_positions = (set(range(target_pages)) if layout == 'contiguous'
                        else {int(i * (total - 1) / (target_pages - 1)) for i in range(target_pages)})
    target_index = foreign_index = 0
    for position in range(total):
        if position in target_positions:
            yield payload('target', target_index)
            target_index += 1
        else:
            yield payload('foreign-' + str(foreign_index // 50), foreign_index)
            foreign_index += 1
    assert target_index == target_pages and foreign_index == foreign_pages


def stable(value):
    return {key: item for key, item in value.items() if key not in ('latency_ms', 'cache_hit')}


def call(book, name):
    if name == 'directory':
        return book.search_directory('production retry policy', project='target', limit=10)
    return book.recall('current production retry_limit' if name == 'current' else 'production retry_limit',
                       project='target', temporal='current' if name == 'current' else 'relevance',
                       budget_chars=2400, limit=5, use_cache=False)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    raw_rows, cells = [], []
    start = time.time()
    for layout in ('contiguous', 'interleaved'):
        for foreign_pages in (0, 120, 480, 1800):
            name = f'{layout}-{foreign_pages}'
            records = list(inputs(foreign_pages, layout))
            input_bytes = json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
            (output / (name + '-inputs.json.gz')).write_bytes(gzip.compress(input_bytes, mtime=0))
            with tempfile.TemporaryDirectory(prefix='scope-pilot-', dir=output.parent) as temporary:
                path = Path(temporary) / 'memory.db'
                ingestion = time.perf_counter()
                with MemoryBook(path, cache_size=0) as writer:
                    for record in records:
                        assert writer.ingest(record)['pages'] == 1
                    actual_pages = writer.db.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
                    assert actual_pages == len(records) <= 2000
                    span = writer.db.execute('SELECT MIN(rid),MAX(rid),COUNT(*) FROM pages WHERE project_id=?', ('target',)).fetchone()
                    bounds = writer._project_rowid_bounds('target')
                ingestion_ms = (time.perf_counter() - ingestion) * 1000
                cell = {'layout': layout, 'foreign_pages': foreign_pages, 'target_pages': 120,
                        'pages': actual_pages, 'target_rowid_span': list(span), 'project_bounds': bounds,
                        'input_sha256': hashlib.sha256(input_bytes).hexdigest(), 'ingestion_ms': ingestion_ms,
                        'database_bytes_after_close': path.stat().st_size, 'operations': {}}
                for operation in ('directory', 'relevance', 'current'):
                    initialized = time.perf_counter()
                    book = MemoryBook(path, cache_size=0)
                    init_ms = (time.perf_counter() - initialized) * 1000
                    statements, measurements, reference = [], [], None
                    try:
                        for repeat in range(3):
                            buckets = [0]
                            def progress():
                                buckets[0] += 1
                                return 0
                            traced = []
                            book.db.set_trace_callback(traced.append)
                            book.db.set_progress_handler(progress, 1000)
                            before = time.perf_counter_ns()
                            response = call(book, operation)
                            elapsed_ms = (time.perf_counter_ns() - before) / 1e6
                            book.db.set_trace_callback(None)
                            book.db.set_progress_handler(None, 0)
                            actual = stable(response)
                            if reference is not None:
                                assert actual == reference, 'Repeated same-database response changed'
                            reference = actual
                            if operation == 'directory':
                                assert all(row['project_id'] == 'target' for row in response['results'])
                            else:
                                assert all(ref['project'] == 'target' for row in response['results'] for ref in row['source_refs'])
                            raw_rows.append({'cell': name, 'operation': operation, 'repeat': repeat,
                                             'response': response})
                            measurements.append({'repeat': repeat, 'fresh_connection_first_call': repeat == 0,
                                                 'elapsed_ms_including_observers': elapsed_ms,
                                                 'vm_instruction_lower_bound': buckets[0] * 1000,
                                                 'trace_calls': len(traced)})
                            if repeat == 0:
                                statements = traced
                        observed = Counter(sql for sql in statements if not sql.startswith('--'))
                        plans = []
                        for sql, calls in observed.items():
                            if ' MATCH ' in sql and sql.lstrip().startswith('SELECT'):
                                plans.append({'sql': sql, 'calls': calls,
                                              'plan': [list(row) for row in book.db.execute('EXPLAIN QUERY PLAN ' + sql)]})
                        cell['operations'][operation] = {'initialize_ms': init_ms, 'measurements': measurements,
                                                         'sql': [{'statement': sql, 'count': count} for sql, count in observed.items()],
                                                         'fts_query_plans': plans}
                        if foreign_pages == 1800:
                            profiler = cProfile.Profile()
                            profiled = profiler.runcall(call, book, operation)
                            assert stable(profiled) == reference
                            buffer = io.StringIO()
                            pstats.Stats(profiler, stream=buffer).sort_stats('cumulative').print_stats(35)
                            (output / (name + '-' + operation + '-profile.txt')).write_text(buffer.getvalue())
                            raw_rows.append({'cell': name, 'operation': operation, 'repeat': 'profile',
                                             'response': profiled})
                    finally:
                        book.close()
                cells.append(cell)
                print(json.dumps({'cell': name, 'pages': actual_pages,
                                  'first_vm': {op: details['measurements'][0]['vm_instruction_lower_bound']
                                               for op, details in cell['operations'].items()}}), flush=True)
    raw_bytes = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in raw_rows).encode()
    (output / 'raw-responses.jsonl.gz').write_bytes(gzip.compress(raw_bytes, mtime=0))
    report = {'schema_version': 1, 'status': 'completed-development-diagnostic',
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'runtime_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted((ROOT / 'src/memory_book').glob('*.py'))},
              'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'python': sys.version, 'sqlite': sqlite3.sqlite_version, 'backend': BACKEND_NAME,
              'memory_book_module': str(sys.modules['memory_book'].__file__),
              'raw_response_rows': len(raw_rows), 'raw_sha256': hashlib.sha256(raw_bytes).hexdigest(),
              'elapsed_seconds': time.time() - start,
              'limits': ['Author-written inspected pilot; not an independent workload or formal performance result.',
                         'Result cache disabled; first-call readers have fresh SQLite connections but OS caches were not cleared.',
                         'Reported wall time includes SQL trace and 1000-instruction callbacks; compare work counts, not uninstrumented speed.',
                         'VM instruction counts omit any remainder below 1000; native internal work is not completely represented.',
                         'Foreign documents change global BM25 statistics; cross-database rank/score equality is not asserted.',
                         'All fixtures were built through normal production ingestion; no schema or runtime changes.'],
              'cells': cells}
    (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'output': str(output), 'rows': len(raw_rows)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
