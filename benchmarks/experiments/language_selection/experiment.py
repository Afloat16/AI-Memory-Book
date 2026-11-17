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


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def resource_usage(pid='self'):
    status = Path(f'/proc/{pid}/status').read_text()
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    sizes = {line.split(':', 1)[0]: int(line.split()[1]) * 1024
             for line in status.splitlines() if line.startswith(('VmRSS:', 'VmHWM:'))}
    ticks = os.sysconf('SC_CLK_TCK')
    return {'rss_bytes': sizes['VmRSS'], 'hwm_bytes': sizes['VmHWM'],
            'user_cpu_s': int(fields[11]) / ticks, 'system_cpu_s': int(fields[12]) / ticks}


class Ledger:
    def __init__(self, path):
        self.file = Path(path).open('xb')
        self.stream = gzip.GzipFile(filename='', mode='wb', fileobj=self.file, mtime=0)

    def event(self, event, config, case, repetition, row=None):
        value = {'event': event, 'configuration': config, 'query_id': case.id,
                 'repetition': repetition, 'row': row}
        self.stream.write((dump(value) + '\n').encode())
        self.stream.flush()
        self.file.flush()

    def close(self):
        self.stream.close()
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()


def verify_manifest(manifest):
    for path, expected in manifest.get('file_sha256', {}).items():
        if file_hash(path) != expected:
            raise AssertionError('Frozen source/input/binary changed: ' + path)
    if manifest.get('status') == 'formal':
        assert manifest.get('file_sha256'), 'Formal inputs must be bound'
        assert os.environ.get('PYTHONHASHSEED') == '0', 'Freeze hash seed before process startup'


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
        if variant in ('rust_window', 'c_window'):
            from memory_book import text as lexical
            sys.path.insert(0, str(HERE / 'rust'))
            from window_adapter import install
            module_name = '_language_rust' if variant == 'rust_window' else '_language_c_owned'
            module_spec = importlib.util.spec_from_file_location(module_name, spec.get('rust_owned') or spec['c_owned'])
            native_owned = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(native_owned)
            install(_native, lexical, native_owned)
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
    import memory_book
    from memory_book import _text_backend
    metadata_ready = None
    if spec.get('metadata_plugin'):
        from memory_book import store as memory_store
        sys.path.insert(0, str(HERE / 'rust_metadata'))
        adapter_spec = importlib.util.spec_from_file_location('language_metadata_adapter', HERE / 'rust_metadata/adapter.py')
        metadata_adapter = importlib.util.module_from_spec(adapter_spec)
        adapter_spec.loader.exec_module(metadata_adapter)
        module_spec = importlib.util.spec_from_file_location(spec['metadata_module'], spec['metadata_plugin'])
        metadata_native = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(metadata_native)
        metadata_ready = metadata_adapter.install(memory_store, metadata_native)
        assert metadata_ready is True, 'Metadata adapter failed to authenticate the frozen implementation'
        globals()['_language_metadata_module'] = metadata_native
    assert Path(memory_book.__file__).resolve().parent == Path(spec['source']).resolve() / 'memory_book'
    assert _text_backend.BACKEND_NAME == ('python' if variant == 'python_reference' else 'native')
    identity = {'variant': variant, 'requested': _text_backend.REQUESTED_BACKEND,
                'actual': _text_backend.BACKEND_NAME, 'source': spec['source'],
                'runtime_registered_methods': changed,
                'excerpt_window_ready': text._native_excerpt_window_ready()}
    if spec.get('metadata_plugin'):
        identity['metadata_binary_sha256'] = file_hash(spec['metadata_plugin'])
        identity['metadata_adapter_ready'] = metadata_ready
        assert identity['metadata_binary_sha256'] == spec['metadata_plugin_sha256']
    if extension is not None:
        identity['native_binary_sha256'] = file_hash(extension.__file__)
        if spec.get('native_binary_sha256'):
            assert identity['native_binary_sha256'] == spec['native_binary_sha256']
    if plugin is not None:
        identity['plugin'] = plugin.describe()
        assert identity['plugin']['table_enabled'] is True
        identity['plugin_binary_sha256'] = file_hash(spec['plugin'])
        if spec.get('plugin_binary_sha256'):
            assert identity['plugin_binary_sha256'] == spec['plugin_binary_sha256']
    for kind in ('rust_owned', 'c_owned'):
        if spec.get(kind):
            identity[kind + '_binary_sha256'] = file_hash(spec[kind])
            if spec.get(kind + '_sha256'):
                assert identity[kind + '_binary_sha256'] == spec[kind + '_sha256']
    if bridge is not None:
        identity['node_math_verified'] = bridge.math_verified
        identity['node_pid'] = bridge.process.pid
        identity['node_executable_sha256'] = file_hash(bridge.node)
    if 'expected_runtime_registered_methods' in spec:
        assert sorted(changed) == sorted(spec['expected_runtime_registered_methods'])
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


async def mcp_measure(args, manifest, data, config_id, attempts, db, work, sources, pages, counter, reference, ledger):
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
                receipt_path = Path(str(db) + '.server-start.json')
                assert receipt_path.exists(), 'Missing server activation receipt'
                receipt = read(receipt_path)
                assert receipt['identity']['variant'] == args.variant
                assert receipt['identity']['actual'] == ('python' if args.variant == 'python_reference' else 'native')
                resources['activation_receipt'] = receipt
                pid = receipt['pid']
                resources['server_before'] = resource_usage(pid)
                node_pid = receipt['identity'].get('node_pid')
                if node_pid:
                    resources['node_before'] = resource_usage(node_pid)
                for case, repetition in attempts:
                    cache.execute('DELETE FROM recall_cache')
                    cache.commit()
                    arguments = {'query': case.query, 'project': case.project, 'limit': 5,
                                 'budget_chars': config['budget_chars']}
                    if config['budget_tokens'] is not None:
                        arguments.update(budget_tokens=1024, tokenizer='cl100k_base')
                    ledger.event('started', config_id, case, repetition)
                    cpu = time.process_time_ns()
                    start = time.perf_counter_ns()
                    response = await client.call_tool('recall_memory', arguments)
                    elapsed = (time.perf_counter_ns() - start) / 1e6
                    cpu_ms = (time.process_time_ns() - cpu) / 1e6
                    if response.isError:
                        raise AssertionError('MCP returned an error')
                    payload = '\n'.join(part.text for part in response.content)
                    cached = cache.execute('SELECT payload FROM recall_cache').fetchall()
                    assert len(cached) == 1
                    native = json.loads(cached[0][0])
                    assert 'latency_ms' not in native
                    assert payload == _json(recall_payload(native))
                    row = reference.make_row(case, native, config, sources, pages, counter,
                        elapsed, cpu_ms, payload, response.model_dump_json(exclude_none=True), repetition=repetition)
                    ledger.event('completed', config_id, case, repetition, row)
                    assert not any(row['invariants'].values()), row['invariants']
                    rows.append(row)
                resources['server_after'] = resource_usage(pid)
                if node_pid:
                    resources['node_after'] = resource_usage(node_pid)
        cache.execute('DELETE FROM recall_cache')
        cache.commit()
    child_receipt = Path(str(db) + '.server.json')
    if child_receipt.exists():
        resources['server_receipt'] = read(child_receipt)
        child_receipt.unlink()
    Path(str(db) + '.server-start.json').unlink()
    return rows, resources

def worker(args):
    manifest = read(args.manifest)
    verify_manifest(manifest)
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
    ledger = Ledger(str(output) + '.events.jsonl.gz')
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
                            db, work, sources, pages, counter, reference, ledger))
                    else:
                        rows = []
                        for case, repetition in attempts:
                            options = {'project': case.project, 'limit': 5,
                                'budget_chars': config['budget_chars'], 'use_cache': False}
                            if config['budget_tokens'] is not None:
                                options.update(budget_tokens=1024, tokenizer='cl100k_base')
                            ledger.event('started', config_id, case, repetition)
                            cpu = time.process_time_ns()
                            start = time.perf_counter_ns()
                            value = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - start) / 1e6
                            cpu_ms = (time.process_time_ns() - cpu) / 1e6
                            value.pop('latency_ms')
                            row = reference.make_row(case, value, config, sources, pages, counter,
                                elapsed, cpu_ms, reference.dump(value), repetition=repetition)
                            ledger.event('completed', config_id, case, repetition, row)
                            assert not any(row['invariants'].values()), row['invariants']
                            rows.append(row)
                        resource = {'parent': resource_usage(),
                                    'node': resource_usage(bridge.process.pid) if bridge is not None else None}
                    report['configurations'][config_id] = {'rows': rows,
                        'latency': reference.summary([row['wall_ms'] for row in rows]), 'resources': resource}
                    save(output, report)
                report['archive_after'] = reference.archive_state(book.db)
                assert report['archive_before'] == report['archive_after']
                changed = []
                for session in data.sessions[:min(12, len(data.sessions))]:
                    messages = [dict(message) for message in session['messages']]
                    messages[-1]['content'] += '\nConfirmed source revision: preserve Unicode café 中文🙂.'
                    changed.append(dict(session, messages=messages))
                before_revision = book.revision
                started = time.perf_counter_ns()
                updated = [book.ingest(session) for session in changed]
                report['resources']['changed_ingestion_ms'] = (time.perf_counter_ns() - started) / 1e6
                report['changed_ingestion_sha256'] = digest(updated)
                assert all(not value['skipped'] for value in updated)
                assert book.revision == before_revision + len(changed)
                report['archive_changed'] = reference.archive_state(book.db)
                report['resources']['parent_after'] = resource_usage()
                report['resources']['node_after'] = resource_usage(bridge.process.pid) if bridge is not None else None
            verify_manifest(manifest)
            report['frozen_inputs_unchanged'] = True
            report['status'] = 'completed'
    except BaseException as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error),
                                             'traceback': traceback.format_exc()})
        raise
    finally:
        if bridge is not None:
            bridge.close()
        ledger.close()
        save(output, report)
        print(dump({'worker': output.name, 'status': report['status']}), flush=True)

def serve(args):
    manifest = read(args.manifest)
    _, extension, bridge, identity = activate(manifest, args.variant)
    from memory_book.cli import main
    save(str(args.db) + '.server-start.json', {'pid': os.getpid(), 'parent_pid': os.getppid(),
        'identity': identity, 'parent': resource_usage(),
        'node': resource_usage(bridge.process.pid) if bridge is not None else None})
    sys.argv = ['memory-book', '--db', args.db, 'mcp']
    try:
        main()
    finally:
        save(str(args.db) + '.server.json', {'identity': identity, 'parent': resource_usage(),
            'node': resource_usage(bridge.process.pid) if bridge is not None else None})
        if bridge is not None:
            bridge.close()

def probe(args):
    manifest = read(args.manifest)
    verify_manifest(manifest)
    MemoryBook, extension, bridge, identity = activate(manifest, args.variant)
    reference, original_turn_texts = dependencies()
    data = cohort(args.cohort, manifest['locomo'])
    hits, python_hits, actual_node, fallback, owned = Counter(), Counter(), Counter(), Counter(), Counter()
    methods = {id(getattr(extension, name)): name for name in manifest['native_methods']} if extension else {}
    original_methods = ({id(value): name for name, value in vars(bridge.native).items()}
                        if bridge is not None else {})
    metadata_dispatch, metadata_calls = Counter(), Counter()
    metadata_native = globals().get('_language_metadata_module')
    metadata_methods = ({id(metadata_native.bounded_metadata): 'bounded_metadata'}
                        if metadata_native is not None else {})
    def trace(frame, event, arg):
        if event == 'c_call' and id(arg) in methods:
            hits[methods[id(arg)]] += 1
        if event == 'c_call' and id(arg) in original_methods and id(arg) not in methods:
            fallback[original_methods[id(arg)]] += 1
        elif event == 'call' and frame.f_code.co_filename == str(HERE / 'javascript/client.py'):
            python_hits[frame.f_code.co_name] += 1
            if frame.f_code.co_name == 'invoke':
                actual_node[frame.f_locals['name']] += 1
        if (event == 'return' and frame.f_code.co_filename == str(HERE / 'rust/window_adapter.py')
                and frame.f_code.co_name == 'excerpt_window'):
            owned['calls'] += 1
            if 'value' in frame.f_locals and frame.f_locals['value'] is not NotImplemented:
                owned['completed'] += 1
            else:
                owned['fallback'] += 1
        if event == 'c_call' and id(arg) in metadata_methods:
            metadata_calls[metadata_methods[id(arg)]] += 1
        if (event == 'return' and frame.f_code.co_filename == str(HERE / 'rust_metadata/adapter.py')
                and frame.f_code.co_name == 'bounded_metadata_wrapper'):
            metadata_dispatch['calls'] += 1
            if 'result' in frame.f_locals and frame.f_locals['result'] is not NotImplemented:
                metadata_dispatch['completed'] += 1
            else:
                metadata_dispatch['fallback'] += 1
    with tempfile.TemporaryDirectory(prefix='language-probe-') as temporary:
        with MemoryBook(Path(temporary) / 'memory.db', cache_size=0) as book:
            sys.setprofile(trace)
            try:
                ingested = [book.ingest(session) for session in data.sessions]
                responses = []
                for q in data.queries:
                    value = book.recall(q.query, project=q.project, budget_chars=2400, limit=5, use_cache=False)
                    value.pop('latency_ms')
                    responses.append(value)
            finally:
                sys.setprofile(None)
            result = {'identity': identity, 'dataset': data.description(), 'native_calls': dict(hits),
                'bridge_calls': dict(python_hits), 'ingestion_sha256': digest(ingested),
                'actual_node_operations': dict(actual_node), 'bridge_native_fallback': dict(fallback),
                'owned_window_dispatch': {name: owned[name] for name in ('calls', 'completed', 'fallback')},
                'metadata_dispatch': {name: metadata_dispatch[name] for name in ('calls', 'completed', 'fallback')},
                'metadata_native_calls': dict(metadata_calls),
                'responses_sha256': digest(responses), 'archive': reference.archive_state(book.db),
                'instrumentation_removed': sys.getprofile() is None}
    if bridge is not None:
        bridge.close()
    if args.variant == 'rust_same':
        import ctypes
        library = ctypes.PyDLL(extension.__file__)
        library.language_rust_manifest.restype = ctypes.py_object
        linked_methods = library.language_rust_manifest()
        expected = {'terms_ascii', 'ascii_tokens', 'unicode_tokens', 'literal_positions',
                    'fold_excerpt_source', 'evidence_units'}
        assert len(linked_methods) == 22
        assert {item['name'] for item in linked_methods if item['replaced']} == expected
        assert all(item['flags'] == 1 for item in linked_methods)
        result['linked_methods'] = linked_methods
    verify_manifest(manifest)
    result['frozen_inputs_unchanged'] = True
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
