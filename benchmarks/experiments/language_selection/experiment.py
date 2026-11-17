"""Isolated complete-output language comparison; never edits product sources.

Each worker is a fresh process. Profiles/probes and all result validation run
outside timers. The MCP path uses the official SDK and the unchanged server.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import timedelta
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASELINE = '234891619d7bed88ddf3fae37e7f3e1b14a808b6'
CONFIGS = {
    'direct-char2400': {'surface': 'direct', 'budget_chars': 2400, 'budget_tokens': None},
    'mcp-char2400': {'surface': 'mcp', 'budget_chars': 2400, 'budget_tokens': None},
    'direct-token1024': {'surface': 'direct', 'budget_chars': 8000, 'budget_tokens': 1024},
    'mcp-token1024': {'surface': 'mcp', 'budget_chars': 8000, 'budget_tokens': 1024},
}


def dump(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (dump(value) + '\n').encode()
    if path.suffix == '.gz':
        raw = gzip.compress(raw, mtime=0)
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_bytes(raw)
    temporary.replace(path)


def activate(manifest, variant):
    spec = manifest['variants'][variant]
    sys.path[:0] = [spec['source'], str(ROOT)]
    os.environ['MEMORY_BOOK_TEXT_BACKEND'] = 'python' if variant == 'python_reference' else 'native'
    extension, plugin, bridge = None, None, None
    if variant != 'python_reference':
        from memory_book import _native
        extension = _native
        before = {name: getattr(_native, name) for name in manifest['native_methods']}
        if spec.get('plugin'):
            path = Path(spec['plugin'])
            module_spec = importlib.util.spec_from_file_location('_language_c_table', path)
            plugin = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(plugin)
            plugin.install_into(_native)
        if variant.startswith('node_'):
            sys.path.insert(0, str(HERE / 'javascript'))
            from client import NodeClient
            bridge = NodeClient(native=_native)
            names = (['excerpt_window'] if variant == 'node_window' else
                     ['terms_ascii', 'ascii_tokens', 'context_allocations'])
            for name in names:
                setattr(_native, name, getattr(bridge, name))
        changed = [name for name in before if getattr(_native, name) is not before[name]]
    else:
        changed = []
    from memory_book import MemoryBook, text
    from memory_book import _text_backend
    identity = {'variant': variant, 'requested': _text_backend.REQUESTED_BACKEND,
                'actual': _text_backend.BACKEND_NAME, 'source': spec['source'],
                'runtime_registered_methods': changed,
                'excerpt_window_ready': text._native_excerpt_window_ready()}
    if extension is not None:
        identity['native_binary_sha256'] = hashlib.sha256(Path(extension.__file__).read_bytes()).hexdigest()
    if plugin is not None:
        identity['plugin'] = plugin.describe()
        identity['plugin_binary_sha256'] = hashlib.sha256(Path(spec['plugin']).read_bytes()).hexdigest()
    if bridge is not None:
        identity['node_math_verified'] = bridge.math_verified
        identity['node_pid'] = bridge.process.pid
    if variant != 'python_reference' and not identity['excerpt_window_ready']:
        raise AssertionError('An unrelated native excerpt guard fell back')
    return MemoryBook, extension, bridge, identity


def dependencies():
    sys.path.insert(0, str(ROOT))
    from scripts import native_language_performance as reference
    from benchmarks.run import original_turn_texts
    return reference, original_turn_texts


def cohort(name, locomo):
    from benchmarks.data import generate_dataset, Dataset, QueryCase
    from benchmarks.public_data import load_locomo
    if name == 'synthetic61':
        return generate_dataset(seed=61, split='development', projects=8)
    if name == 'public1015':
        return load_locomo(Path(locomo))
    # Purpose-built diagnostic stress input: a stated scenario, not an estimate
    # of production-language proportions or retrieval quality.
    data = Dataset(seed=171117, split='development', variant='unicode_stress_v1')
    texts = ['Straße café cafe\u0301 İSTANBUL Å ﬃ résumé 中文🙂',
             'ＡＢＣ ﬁleName 数据隔离👩\u200d💻 Ångström λογική',
             'Unicode原文坐标 müssen stabil bleiben. naïve façade \u0308']
    for i in range(12):
        key = f'project{i % 3}'
        messages = []
        for j in range(8):
            token = f'case{i}item{j}'
            messages.extend([{'role': 'user', 'content': f'Explain {token} Unicode offset behavior'},
                {'role': 'assistant', 'content': (texts[(i+j) % len(texts)] + ' ') * 35 +
                    f' {token} offset is {i * 8 + j}. Preserve exact original coordinates.'}])
            data.queries.append(QueryCase(f'unicode-{i}-{j}', token + ' cafe Unicode offset', 'unicode_stress', key))
        data.sessions.append({'project': key, 'session_id': f'unicode-session{i}', 'task_id': 'unicode',
            'title': f'Unicode session {i}', 'created_at': '2025-04-17T09:00:00Z', 'messages': messages})
    return data


def order(queries, round_number, configuration, repeats):
    result = []
    for repetition in range(repeats):
        items = list(queries)
        random.Random(171117 + round_number * 1009 + repetition * 97 + configuration).shuffle(items)
        result.extend((case, repetition) for case in items)
    return result


def descendants_usage(reference, bridge):
    return reference.usage(bridge.process.pid) if bridge is not None else None


async def mcp_measure(args, manifest, data, config_id, attempts, db, work, sources, pages, counter, reference, output):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import _json, recall_payload
    config = CONFIGS[config_id]
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0'}
    command = [str(Path(__file__).resolve()), 'serve', '--manifest', str(Path(args.manifest).resolve()),
               '--variant', args.variant, '--db', str(db), '--package', 'memory_book']
    parameters = StdioServerParameters(command=sys.executable, args=command, env=env, cwd=str(work))
    rows = []
    with sqlite3.connect(db) as cache:
        start = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=60)) as client:
                initialized = await client.initialize()
                resources = {'startup_to_initialize_ms': (time.perf_counter_ns() - start) / 1e6}
                schema = await client.list_tools()
                resources.update(tool_schema_sha256=digest(schema.model_dump(exclude_none=True)),
                    instructions_sha256=digest(initialized.instructions or ''))
                pid = reference.server_pid(db)
                resources['server_before'] = reference.usage(pid)
                for case, repetition in attempts:
                    cache.execute('DELETE FROM recall_cache')
                    cache.commit()
                    arguments = {'query': case.query, 'project': case.project, 'limit': 5,
                                 'budget_chars': config['budget_chars']}
                    if config['budget_tokens'] is not None:
                        arguments.update(budget_tokens=1024, tokenizer='cl100k_base')
                    start = time.perf_counter_ns()
                    response = await client.call_tool('recall_memory', arguments)
                    elapsed = (time.perf_counter_ns() - start) / 1e6
                    if response.isError:
                        raise AssertionError('MCP returned an error')
                    payload = '\n'.join(part.text for part in response.content)
                    cached = cache.execute('SELECT payload FROM recall_cache').fetchall()
                    assert len(cached) == 1
                    native = json.loads(cached[0][0])
                    assert payload == _json(recall_payload(native))
                    row = reference.make_row(case, native, config, sources, pages, counter,
                        elapsed, 0.0, payload, response.model_dump_json(exclude_none=True), repetition=repetition)
                    assert not any(row['invariants'].values()), row['invariants']
                    rows.append(row)
                resources['server_after'] = reference.usage(pid)
                # The child reports its own Node process separately; parent RSS
                # is never presented as the memory cost of a two-process bridge.
        cache.execute('DELETE FROM recall_cache')
        cache.commit()
    child_receipt = Path(str(db) + '.server.json')
    if child_receipt.exists():
        resources['server_receipt'] = read(child_receipt)
        child_receipt.unlink()
    return rows, resources


def worker(args):
    manifest = read(args.manifest)
    activation_start = time.perf_counter_ns()
    MemoryBook, extension, bridge, identity = activate(manifest, args.variant)
    activation_ms = (time.perf_counter_ns() - activation_start) / 1e6
    reference, original_turn_texts = dependencies()
    data = cohort(args.cohort, manifest['locomo'])
    output = Path(args.output)
    assert not output.exists(), 'Never overwrite a completed or failed attempt'
    report = {'status': 'running', 'variant': args.variant, 'cohort': args.cohort, 'round': args.round,
        'dataset': data.description(), 'identity': identity, 'manifest_sha256': digest(manifest),
        'configurations': {}, 'resources': {'experimental_activation_ms': activation_ms}, 'error': None}
    save(output, report)
    try:
        with tempfile.TemporaryDirectory(prefix='language-worker-', dir=output.parent) as temporary:
            work = Path(temporary)
            db = work / 'memory.db'
            started = time.perf_counter_ns()
            with MemoryBook(db, cache_size=0) as book:
                report['resources']['new_database_ms'] = (time.perf_counter_ns() - started) / 1e6
                started = time.perf_counter_ns()
                ingested = [book.ingest(session) for session in data.sessions]
                report['resources']['fresh_ingestion_ms'] = (time.perf_counter_ns() - started) / 1e6
                report['ingestion_sha256'] = digest(ingested)
                report['archive_before'] = reference.archive_state(book.db)
                started = time.perf_counter_ns()
                replayed = [book.ingest(session) for session in data.sessions]
                report['resources']['unchanged_ingestion_ms'] = (time.perf_counter_ns() - started) / 1e6
                assert all(item['skipped'] for item in replayed)
                report['unchanged_sha256'] = digest(replayed)
                sources = original_turn_texts(data)
                pages = {row['id']: row['content'] for row in book.db.execute('SELECT id,content FROM pages')}
                for index, config_id in enumerate(args.configs.split(',')):
                    config = CONFIGS[config_id]
                    counter = None
                    if config['budget_tokens'] is not None:
                        import tiktoken
                        assert tiktoken.__version__ == '0.12.0'
                        counter = tiktoken.get_encoding('cl100k_base')
                        counter.encode('Warm vocabulary outside timing.')
                    attempts = order(data.queries, args.round, index, args.repeats)
                    if config['surface'] == 'mcp':
                        rows, resource = asyncio.run(mcp_measure(args, manifest, data, config_id, attempts,
                            db, work, sources, pages, counter, reference, output))
                    else:
                        rows = []
                        for case, repetition in attempts:
                            options = {'project': case.project, 'limit': 5,
                                'budget_chars': config['budget_chars'], 'use_cache': False}
                            if config['budget_tokens'] is not None:
                                options.update(budget_tokens=1024, tokenizer='cl100k_base')
                            start = time.perf_counter_ns()
                            value = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - start) / 1e6
                            value.pop('latency_ms')
                            row = reference.make_row(case, value, config, sources, pages, counter,
                                elapsed, 0.0, reference.dump(value), repetition=repetition)
                            assert not any(row['invariants'].values()), row['invariants']
                            rows.append(row)
                        resource = {'parent': reference.usage(), 'node': descendants_usage(reference, bridge)}
                    report['configurations'][config_id] = {'rows': rows,
                        'latency': reference.summary([row['wall_ms'] for row in rows]), 'resources': resource}
                    save(output, report)
                report['archive_after'] = reference.archive_state(book.db)
                assert report['archive_before'] == report['archive_after']
                # Changed-ingestion timing is after the query matrix so every
                # timed query sees the same frozen original corpus.
                changed = []
                for session in data.sessions[:min(12, len(data.sessions))]:
                    changed.append(dict(session, title=session.get('title', '') + ' updated'))
                started = time.perf_counter_ns()
                updated = [book.ingest(session) for session in changed]
                report['resources']['changed_ingestion_ms'] = (time.perf_counter_ns() - started) / 1e6
                report['changed_ingestion_sha256'] = digest(updated)
                report['archive_changed'] = reference.archive_state(book.db)
                report['resources']['parent_after'] = reference.usage()
                report['resources']['node_after'] = descendants_usage(reference, bridge)
            report['status'] = 'completed'
    except BaseException as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error),
                                             'traceback': traceback.format_exc()})
        raise
    finally:
        if bridge is not None:
            bridge.close()
        save(output, report)
        print(dump({'worker': output.name, 'status': report['status']}), flush=True)


def serve(args):
    manifest = read(args.manifest)
    _, extension, bridge, identity = activate(manifest, args.variant)
    reference, _ = dependencies()
    from memory_book.cli import main
    sys.argv = ['memory-book', '--db', args.db, 'mcp']
    try:
        main()
    finally:
        save(str(args.db) + '.server.json', {'identity': identity, 'parent': reference.usage(),
                                           'node': descendants_usage(reference, bridge)})
        if bridge is not None:
            bridge.close()


def probe(args):
    manifest = read(args.manifest)
    MemoryBook, extension, bridge, identity = activate(manifest, args.variant)
    reference, original_turn_texts = dependencies()
    data = cohort(args.cohort, manifest['locomo'])
    hits, python_hits = Counter(), Counter()
    methods = {id(getattr(extension, name)): name for name in manifest['native_methods']} if extension else {}
    def trace(frame, event, arg):
        if event == 'c_call' and id(arg) in methods:
            hits[methods[id(arg)]] += 1
        elif event == 'call' and frame.f_code.co_filename == str(HERE / 'javascript/client.py'):
            python_hits[frame.f_code.co_name] += 1
        elif event == 'c_return':
            pass
    with tempfile.TemporaryDirectory(prefix='language-probe-') as temporary:
        with MemoryBook(Path(temporary) / 'memory.db', cache_size=0) as book:
            sys.setprofile(trace)
            try:
                ingested = [book.ingest(s) for s in data.sessions]
                responses = []
                for q in data.queries:
                    value = book.recall(q.query, project=q.project, budget_chars=2400, limit=5, use_cache=False)
                    value.pop('latency_ms')
                    responses.append(value)
            finally:
                sys.setprofile(None)
            result = {'identity': identity, 'dataset': data.description(), 'native_calls': dict(hits),
                'bridge_calls': dict(python_hits), 'ingestion_sha256': digest(ingested),
                'responses_sha256': digest(responses), 'archive': reference.archive_state(book.db),
                'instrumentation_removed': sys.getprofile() is None}
    if bridge is not None:
        bridge.close()
    save(args.output, result)
    print(dump({'probe': args.variant, 'cohort': args.cohort, 'outputs': result['responses_sha256']}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['worker', 'serve', 'probe'])
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--variant', required=True)
    parser.add_argument('--cohort', default='synthetic61')
    parser.add_argument('--output')
    parser.add_argument('--db')
    parser.add_argument('--package')
    parser.add_argument('--round', type=int, default=0)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--configs', default='direct-char2400,mcp-char2400')
    args = parser.parse_args()
    globals()[args.command](args)


if __name__ == '__main__':
    main()
