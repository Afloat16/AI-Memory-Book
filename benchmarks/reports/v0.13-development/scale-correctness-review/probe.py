"""Post-scale development reproduction of unchanged frozen 1024-page cases."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, subprocess, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
FROZEN = '9ea37a7c72aec21b6f106d9631d72d72199e283b'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-commit', required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    source = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted((ROOT / 'src/memory_book').glob('*.py'))}
    for name, value in source.items():
        assert digest(git('show', args.source_commit + ':' + name)) == value, name
    for name in ('benchmarks/v013_workload.py', 'benchmarks/v013_scale.py', 'benchmarks/experiments/v013-long-history-plan.json'):
        assert (ROOT / name).read_bytes() == git('show', FROZEN + ':' + name), name
    sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'benchmarks')]
    import memory_book.store as runtime
    from memory_book import MemoryBook
    from memory_book._text_backend import BACKEND_NAME
    from v013_workload import sessions, checkpoints, encoded, cases
    from v013_scale import score, page_identity_errors
    assert BACKEND_NAME == os.environ['MEMORY_BOOK_TEXT_BACKEND']
    protocol = json.loads((OUT / 'protocol.json').read_text())
    spec = checkpoints()[0]
    inputs = b''.join(encoded(record) + b'\n' for record in sessions(spec))
    assert inputs == gzip.decompress((OUT / 'inputs.jsonl.gz').read_bytes())
    requests = [case for case in cases() if case['surface'] == 'recall']
    assert requests == json.loads((OUT / 'cases.json').read_text())
    options = protocol['request_options']
    trace = []
    active = None
    original_groups = runtime._declaration_groups

    def traced_groups(db, pool, matched, contents, references, **kwargs):
        result = original_groups(db, pool, matched, contents, references, **kwargs)
        if active and active['category'] in ('current', 'multi_source') and active['project'] == 'routing-archive':
            analysis = kwargs.get('source_analysis') or {}
            observations = []
            for item in pool:
                rid = item['rid']
                statements = []
                if rid in analysis.get('complete_sources', set()):
                    for clause, origin in runtime._declaration_clauses(contents[rid], references[rid]):
                        for binding in runtime._FIELD_BINDING.finditer(clause):
                            identity = runtime._field_identity(binding['name'])
                            prefix = runtime._declaration_qualifier(clause, binding, identity, prose=False)
                            statements.append({'clause': clause, 'field': binding['name'], 'prefix': prefix,
                                               'scope': runtime._declaration_scope(prefix) if prefix is not None else None})
                observations.append({'rid': rid, 'session': item['session_id'], 'score': item['score'],
                                     'matched_terms': sorted(matched.get(rid, ())), 'statements': statements})
            trace.append({'case': active['id'], 'pool': observations,
                          'groups': [{'chapter': key[0], 'fields': sorted(key[1]), 'scope': key[2],
                                      'sessions': [pool[index]['session_id'] for index in positions]}
                                     for key, positions in result[0].items()], 'diagnostic': result[1]})
        return result

    runtime._declaration_groups = traced_groups
    rows = []
    try:
        with MemoryBook(':memory:', segmentation='turn', max_page_chars=900, min_page_chars=0, cache_size=0) as book:
            ingested = [book.ingest(json.loads(line)) for line in inputs.splitlines()]
            page_count = book.db.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
            assert page_count == spec['total_pages'] == 1024
            for case in requests:
                active = case
                response = book.recall(case['query'], project=case['project'], use_cache=False, **options)
                assessment = score(response, case, spec)
                assessment['source_errors'].extend(page_identity_errors(book, response, case['project']))
                row = {'case': case, 'request': {'query': case['query'], 'project': case['project'], 'use_cache': False, **options},
                       'response': response, 'score': assessment}
                rows.append(row)
                with (output / 'raw.jsonl').open('a', encoding='utf8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n');stream.flush();os.fsync(stream.fileno())
    finally:
        runtime._declaration_groups = original_groups
    (output / 'candidate-pool-trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2) + '\n')
    assert source == {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted((ROOT / 'src/memory_book').glob('*.py'))}
    summary = {}
    for category in sorted({r['case']['category'] for r in rows}):
        selected = [r['score'] for r in rows if r['case']['category'] == category]
        summary[category] = {'cases': len(selected), 'complete': sum(s['complete'] is True for s in selected),
                             'current_source_first': sum(s['current_source_first'] is True for s in selected),
                             'source_errors': sum(len(s['source_errors']) for s in selected),
                             'required_ranks': [s['required_ranks'] for s in selected]}
    receipt = {'status': 'completed', 'scope': 'Development reproduction after viewing scale failures; no formal timing claim.',
               'source_commit': args.source_commit, 'worktree_head': git('rev-parse', 'HEAD').decode().strip(),
               'runtime_files': source, 'recall_version': runtime.RECALL_VERSION, 'backend': BACKEND_NAME,
               'inputs_sha256': digest(inputs), 'cases_sha256': digest((OUT / 'cases.json').read_bytes()),
               'protocol_sha256': digest((OUT / 'protocol.json').read_bytes()), 'probe_sha256': digest(Path(__file__).read_bytes()),
               'spec': spec, 'source_sessions': len(ingested), 'pages': page_count, 'responses': len(rows),
               'raw_sha256': digest((output / 'raw.jsonl').read_bytes()), 'summary': summary}
    if BACKEND_NAME == 'native':
        from memory_book import _native
        receipt['loaded_native_sha256'] = digest(Path(_native.__file__).read_bytes())
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('runtime_files',)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
