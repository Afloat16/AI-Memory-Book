"""Pinned LanceDB and Whoosh search APIs; no gold, query rewriting or ranking code."""
from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stdout
import hashlib
import importlib.metadata
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import traceback

from benchmarks.competitors.memory_systems import (
    PythonComponent, ROOT, sanitized_environment, sha_file, validate_documents,
)
from benchmarks.competitors.memory_systems_worker import block_python_network, serializable

LOCK_PATH = Path(__file__).with_name('v012_search_components.lock.json')
BACKENDS = ('lancedb_fts', 'whoosh_bm25f_or')


def installed_packages():
    """Hash every RECORD-listed installed file and verify all declared digests."""
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    environment = default_environment()
    environment['extra'] = ''
    pending, packages = ['lancedb', 'Whoosh'], {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in packages:
            continue
        dist = importlib.metadata.distribution(name)
        entries = dist.files
        if not entries:
            raise ValueError('Distribution has no complete installed file inventory: ' + name)
        files, native = {}, {}
        for entry in sorted(entries, key=str):
            path = Path(dist.locate_file(entry))
            if not path.is_file() or path.is_symlink():
                raise ValueError('Missing or linked installed distribution file: ' + str(entry))
            digest, size = sha_file(path), path.stat().st_size
            if entry.hash is not None:
                if entry.hash.mode != 'sha256':
                    raise ValueError('Unsupported upstream RECORD digest: ' + str(entry))
                encoded = base64.urlsafe_b64encode(bytes.fromhex(digest)).decode().rstrip('=')
                if encoded != entry.hash.value or entry.size != size:
                    raise ValueError('Installed file differs from upstream RECORD: ' + str(entry))
            record = {'sha256': digest, 'bytes': size,
                      'record_digest': str(entry.hash) if entry.hash is not None else None,
                      'record_bytes': entry.size}
            files[str(entry)] = record
            if path.suffix in ('.so', '.pyd', '.dll', '.dylib'):
                native[str(entry)] = digest
        record_entries = [entry for entry in entries if str(entry).endswith('.dist-info/RECORD')]
        if len(record_entries) != 1:
            raise ValueError('Missing or ambiguous distribution RECORD: ' + name)
        record_path = Path(dist.locate_file(record_entries[0]))
        requirements = list(dist.requires or [])
        active = []
        for declaration in requirements:
            requirement = Requirement(declaration)
            if requirement.marker is None or requirement.marker.evaluate(environment):
                dependency = canonicalize_name(requirement.name)
                installed_version = importlib.metadata.version(dependency)
                if not requirement.specifier.contains(installed_version, prereleases=True):
                    raise ValueError('Resolved dependency violates upstream requirement: ' + declaration)
                if requirement.extras:
                    raise ValueError('New dependency extras need a registered closure: ' + declaration)
                active.append(dependency)
                pending.append(dependency)
        packages[name] = {'version': dist.version, 'requirements': requirements,
                          'active_dependencies': sorted(set(active)), 'files': files,
                          'files_sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
                          'record_sha256': sha_file(record_path), 'native_files': native}
    return dict(sorted(packages.items()))


def package_identity():
    lock = json.loads(LOCK_PATH.read_text(encoding='utf-8'))
    actual = installed_packages()
    if actual != lock['packages']:
        raise ValueError('Installed package bytes, RECORD or dependency closure differ from the pre-quality lock')
    return {name: {key: spec[key] for key in ('version', 'active_dependencies', 'files_sha256',
                                             'record_sha256', 'native_files')}
            | {'installed_files': len(spec['files'])} for name, spec in actual.items()}


def result_identity(response):
    value = {key: response[key] for key in ('hit_ids', 'records', 'scores', 'native_payload', 'request')}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


class SearchComponents(PythonComponent):
    """Use the existing isolated request transport, with a new pinned worker."""

    def __init__(self, backend, documents, state, *, python=sys.executable, timeout=180):
        if backend not in BACKENDS:
            raise ValueError('Unknown registered search component')
        docs = list(documents)
        self.documents = validate_documents(docs)
        self.state = Path(state).resolve()
        self.state.mkdir(parents=True, exist_ok=False)
        self.timeout, self.closed, self.counter = timeout, False, 0
        self.responses, self.stderr_tail = queue.Queue(), []
        self.stderr_file = (self.state / 'stderr.log').open('w', encoding='utf-8')
        env = sanitized_environment(self.state, self.state / 'cache')
        temporary = self.state / 'tmp'
        temporary.mkdir()
        env.update({'TMPDIR': str(temporary), 'LANCEDB_DISABLE_TELEMETRY': '1',
                    'PYTHONPYCACHEPREFIX': str(self.state / 'unused-pycache')})
        started = time.perf_counter_ns()
        self.process = subprocess.Popen(
            [str(python), '-B', '-m', 'benchmarks.competitors.v012_search_components',
             '--backend', backend, '--state', str(self.state)], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', bufsize=1)
        self.threads = [threading.Thread(target=self._stdout, daemon=True),
                        threading.Thread(target=self._stderr, daemon=True)]
        for thread in self.threads:
            thread.start()
        try:
            self.metadata = self._request({'op': 'init', 'documents': [
                {key: doc[key] for key in ('id', 'project', 'title', 'text', 'created_at')} for doc in docs]})
            self.metadata['startup_and_index_roundtrip_ms'] = (time.perf_counter_ns() - started) / 1e6
        except BaseException:
            self.close()
            raise

    def verify_packages(self):
        return self._request({'op': 'verify'})


class LanceFTS:
    def __init__(self, documents, state):
        import lancedb
        from lancedb.index import FTS

        validate_documents(documents)
        self.database = lancedb.connect(str(state / 'lance'))
        self.table = self.database.create_table('pages', data=documents)
        config = FTS()
        self.table.create_index('text', config=config)
        self.metadata = {
            'classification': 'embedded database native FTS component; no vector or model calls',
            'search_api': "table.search(original_query, query_type='fts', fts_columns='text').where(exact_project, prefilter=True).limit(5).to_list()",
            'scope': 'native exact project predicate before top-k; no result filtering or refill',
            'indexed_text': 'complete original text only; other fields stored unchanged',
            'index_configuration': serializable(vars(config)),
            'query_operator': 'unmodified native FTS query default OR',
            'persistent': True, 'model_calls': 0,
        }

    def search(self, query, project, limit):
        predicate = "project = '" + project.replace("'", "''") + "'"
        rows = self.table.search(query, query_type='fts', fts_columns='text').where(
            predicate, prefilter=True).limit(limit).to_list()
        records = [{key: row[key] for key in ('id', 'project', 'text')} for row in rows]
        return {'hit_ids': [row['id'] for row in records], 'records': records,
                'scores': [row['_score'] for row in rows], 'native_payload': {'rows': rows}}

    def close(self):
        self.table = None
        self.database.close()


class WhooshBM25F:
    def __init__(self, documents, state):
        from whoosh.fields import Schema, ID, TEXT, STORED
        from whoosh import index
        from whoosh.qparser import QueryParser, OrGroup

        validate_documents(documents)
        directory = state / 'whoosh'
        directory.mkdir()
        schema = Schema(id=ID(stored=True, unique=True), project=ID(stored=True),
                        text=TEXT(stored=True), title=STORED, created_at=STORED)
        self.index = index.create_in(str(directory), schema)
        writer = self.index.writer()
        for document in documents:
            writer.add_document(**document)
        writer.commit()
        self.searcher = self.index.searcher()
        self.parser = QueryParser('text', schema=self.index.schema, group=OrGroup)
        self.metadata = {
            'classification': 'full-text retrieval library; not an AI memory product',
            'search_api': 'QueryParser(text, group=OrGroup).parse(original_query); Searcher.search(filter=Term(project), limit=5)',
            'scope': 'native exact ID Term filter before top-k; no result filtering or refill',
            'indexed_text': 'complete original text; TEXT default StandardAnalyzer; title/time stored only',
            'parser_group': 'OrGroup (explicit nondefault; default QueryParser uses AndGroup)',
            'ranking': {'name': 'native default BM25F', 'B': self.searcher.weighting.B,
                        'K1': self.searcher.weighting.K1},
            'persistent': True, 'model_calls': 0,
        }

    def search(self, query, project, limit):
        from whoosh.query import Term

        parsed = self.parser.parse(query)
        native = self.searcher.search(parsed, filter=Term('project', project), limit=limit)
        hits = [{'fields': dict(hit), 'docnum': hit.docnum, 'score': hit.score} for hit in native]
        records = [{key: hit['fields'][key] for key in ('id', 'project', 'text')} for hit in hits]
        return {'hit_ids': [row['id'] for row in records], 'records': records,
                'scores': [hit['score'] for hit in hits],
                'native_payload': {'hits': hits, 'parsed_query': str(parsed),
                                   'scored_length': native.scored_length()}}

    def close(self):
        self.searcher.close()
        self.index.close()


CLASSES = {'lancedb_fts': LanceFTS, 'whoosh_bm25f_or': WhooshBM25F}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=BACKENDS, required=True)
    parser.add_argument('--state', required=True, type=Path)
    args = parser.parse_args()
    protocol, component, attempts, initial = sys.stdout, None, [], None
    try:
        for line in sys.stdin:
            request = None
            try:
                request = json.loads(line)
                with redirect_stdout(sys.stderr):
                    if request['op'] == 'init':
                        if component is not None:
                            raise ValueError('Worker already initialized')
                        initial = package_identity()
                        attempts = block_python_network()
                        started = time.perf_counter_ns()
                        component = CLASSES[args.backend](request['documents'], args.state)
                        if attempts:
                            raise RuntimeError('Component attempted Python network access during setup')
                        result = {'backend': args.backend, 'packages': initial,
                                  'supplied_pages': len(request['documents']),
                                  'native_setup_and_index_ms': (time.perf_counter_ns() - started) / 1e6,
                                  'network_policy': 'Python INET tripwire; no model/service configured; not an OS sandbox',
                                  **component.metadata}
                    elif request['op'] == 'search':
                        if component is None:
                            raise ValueError('Worker not initialized')
                        started = time.perf_counter_ns()
                        result = component.search(request['query'], request['project'], request['limit'])
                        result['search_ms'] = (time.perf_counter_ns() - started) / 1e6
                        result['request'] = {key: request[key] for key in ('query', 'project', 'limit')}
                        if attempts:
                            raise RuntimeError('Component attempted Python network access during search')
                        result['network_attempts'] = len(attempts)
                    elif request['op'] == 'verify':
                        actual = package_identity()
                        if initial != actual or attempts:
                            raise ValueError('Upstream installation or network policy changed during execution')
                        result = {'packages': actual, 'packages_unchanged': True, 'network_attempts': len(attempts)}
                    else:
                        raise ValueError('Unknown operation')
                payload = {'id': request['id'], 'result': serializable(result)}
            except Exception:
                payload = {'id': request.get('id') if request else None, 'error': traceback.format_exc()}
            protocol.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + '\n')
            protocol.flush()
    finally:
        if component is not None:
            with redirect_stdout(sys.stderr):
                component.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
