"""Read-only cross-check of saved v0.13 legacy evidence; no MemoryBook calls."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo-root', type=Path, required=True)
parser.add_argument('--evidence-root', type=Path, required=True)
parser.add_argument('--candidate', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
ROOT = args.repo_root.resolve()
EVIDENCE = args.evidence_root.resolve()
OUTPUT = args.output.resolve()
BASELINE = '8044e4bafe18e73ea422af5eeb47ef961e65246c'
CANDIDATE = args.candidate
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_json(path):
    return json.loads(path.read_bytes())

def rows(path):
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

checks = 0
def check(condition, detail):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(detail)

blob_cache = {}
def committed_bytes(commit, path):
    key = commit, path
    if key not in blob_cache:
        blob_cache[key] = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':' + path])
    return blob_cache[key]

report = {'schema': 'independent-saved-legacy-review-v1', 'started_at': datetime.now(timezone.utc).isoformat(),
          'candidate_commit': CANDIDATE, 'baseline_commit': BASELINE, 'memory_book_api_calls': 0,
          'scope': 'Saved evidence and source coordinates only; no retrieval, ingestion or performance measurement.',
          'review_script_sha256': sha(Path(__file__).read_bytes()), 'gates': {}}
for gate in ('engineering', 'short-page', 'directory'):
    root = EVIDENCE / (gate + '-attempt1')
    execution = read_json(root / 'execution.json')
    check(execution['status'] == 'completed' and execution['accepted'] is True, gate + ': status')
    check(execution['source_before'] == execution['source_after'], gate + ': runtime identity')
    check(execution['inputs_before'] == execution['inputs_after'], gate + ': evaluator identity')
    for label, identity in execution['source_before'].items():
        check(identity['commit'] == (BASELINE if label == 'baseline' else CANDIDATE), gate + ': commit')
        for name, expected in identity['files'].items():
            check(sha(committed_bytes(identity['commit'], name)) == expected, gate + ': committed runtime ' + name)
    for binding in execution['inputs_before'].values():
        if not isinstance(binding, dict) or 'commit' not in binding or 'files' not in binding:
            continue
        for name, expected in binding['files'].items():
            raw = committed_bytes(binding['commit'], name)
            check(sha(raw) == expected['sha256'] and len(raw) == expected['bytes'], gate + ': committed evaluator ' + name)
    for original, entry in execution['compression_manifest'].items():
        archive = (root / entry['stored_as']).read_bytes()
        raw = gzip.decompress(archive)
        check(sha(archive) == entry['stored_sha256'] and sha(raw) == entry['sha256'] and len(raw) == entry['bytes'], gate + ': compressed ' + original)
    check(all(a['returncode'] == 0 and not a['timed_out'] for a in execution['attempts']), gate + ': process receipts')
    report['gates'][gate] = {'execution_sha256': sha((root / 'execution.json').read_bytes()),
                           'lossless_archives_checked': len(execution['compression_manifest']),
                           'source_and_evaluator_identity': 'verified_against_git_blobs'}

for scorer_path in ('scripts/audit_project_scope_native_replay.py', 'benchmarks/v012_short_page_guard_eval.py'):
    check((ROOT / scorer_path).read_bytes() == committed_bytes(BASELINE, scorer_path),
          'independent auditor imported exact baseline scorer: ' + scorer_path)
report['scorer_bindings'] = {name: sha((ROOT / name).read_bytes()) for name in
                           ('scripts/audit_project_scope_native_replay.py', 'benchmarks/v012_short_page_guard_eval.py')}
report['evidence_root'] = str(EVIDENCE)
score_module = load_module('legacy_independent_score', ROOT / 'scripts/audit_project_scope_native_replay.py')
engineering = {}
matrix = {}
for arm in ('baseline', 'candidate'):
    engineering[arm] = {}
    for kind in ('native', 'common-block'):
        root = EVIDENCE / 'engineering-attempt1' / arm / kind
        dataset = read_json(root / 'dataset.json')
        visible, sources, cases = {}, {}, {}
        for step in dataset:
            for session in step['sessions']:
                visible[(session['project'], session['session_id'])] = session
            sources[step['checkpoint']] = {(s['project'], s['session_id'], 0): '\n\n'.join(m['role'].upper() + ': ' + m['content'] for m in s['messages']) for s in visible.values()}
            cases.update({case['id']: case for case in step['cases']})
        saved = rows(root / 'raw.jsonl.gz')
        keys = [(r['case_id'], r['backend'], r['budget_chars']) for r in saved]
        expected_backends = ('book', 'flat', 'no_memory', 'recent_history') if kind == 'native' else ('book',)
        expected = {(c, b, budget) for c in cases for b in expected_backends for budget in (1200, 2400)}
        check(len(keys) == len(set(keys)) and set(keys) == expected, arm + kind + ': exact matrix')
        for row in saved:
            derived = score_module.expected_score(cases[row['case_id']], row['response'], sources[row['checkpoint']], row['budget_chars'])
            check(derived == row['score'], arm + kind + ': independent source/score ' + row['case_id'])
        matrix[arm, kind] = {key: row['score'] for key, row in zip(keys, saved)}
        engineering[arm][kind] = {'responses': len(saved), 'backends': dict(Counter(r['backend'] for r in saved)),
                                 'source_error_outputs': sum(bool(r['score']['source_errors']) for r in saved)}
for kind in ('native', 'common-block'):
    check(matrix['baseline', kind] == matrix['candidate', kind], kind + ': unchanged complete score matrix')
report['gates']['engineering'].update({'results': engineering, 'score_changes': 0,
    'interpretation': '800 configurations per source include 480 no_memory/recent_history/flat controls and 320 book configurations; no score regression, not 800 fully correct book answers.'})

# The frozen checker only reconstructs sources and inspects supplied responses.
short = load_module('legacy_short_saved', ROOT / 'benchmarks/v012_short_page_guard_eval.py')
short_results = {}
for backend in ('python', 'native'):
    root = EVIDENCE / 'short-page-attempt1' / backend
    stored = read_json(root / 'report.json')
    raw = gzip.decompress((root / 'raw.jsonl.gz').read_bytes())
    check(sha(raw) == stored['raw_sha256'] and sha((root / 'raw.jsonl.gz').read_bytes()) == stored['archive_sha256'], 'short: hashes')
    derived = short.validate_rows([json.loads(line) for line in raw.splitlines()])
    check(derived == stored['summary'], 'short: independently source-checked summaries')
    short_results[backend] = derived
report['gates']['short-page']['results'] = short_results

directory = {}
for backend in ('python', 'native'):
    root = EVIDENCE / 'directory-attempt1' / backend
    protocol, stored = read_json(root / 'protocol.json'), read_json(root / 'report.json')
    raw = gzip.decompress((root / 'raw.jsonl.gz').read_bytes())
    saved = [json.loads(line) for line in raw.splitlines()]
    check(sha(raw) == stored['raw_records']['sha256'] and len(raw) == stored['raw_records']['bytes'], 'directory: raw hashes')
    check([r['sequence'] for r in saved] == list(range(1, len(saved) + 1)), 'directory: sequence')
    check((root / 'protocol.json').read_bytes() == committed_bytes(BASELINE, 'benchmarks/experiments/v011-directory-navigation-protocol-v2.json'), 'directory: exact old fixture')
    sources, chapters = {}, {}
    source_sessions = protocol['dataset']['sessions']
    ingests = [r for r in saved if r['operation'] == 'ingest']
    check([r['request'] for r in ingests] == source_sessions, 'directory: actual original ingest requests')
    for session, row in zip(source_sessions, ingests):
        chapters[(session['project'], session['task_id'])] = row['response']['chapter_id']
        for turn, start in enumerate(range(0, len(session['messages']), 2)):
            sources[session['project'], session['session_id'], turn] = '\n\n'.join(m['role'].upper() + ': ' + m['content'] for m in session['messages'][start:start + 2])
    cases = {c['id']: c for c in protocol['dataset']['cases']}
    allowed_chapters, allowed_sections, allowed_pages = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    read_count = ref_count = expected_errors = 0
    unique_pages = set()
    for row in saved:
        if row['operation'] == 'ingest':
            continue
        case, request, operation = cases[row['case_id']], row['request'], row['operation']
        if 'error' in row:
            check(row['error']['type'] == case.get('expected_error'), 'directory: expected error')
            expected_errors += 1
            continue
        value = row['response']
        if operation == 'search_directory':
            expected_ids = {chapters[tuple(path)] for path in case.get('expected_chapters', [])}
            check(value['evidence'] is False and value['total'] == len(expected_ids), 'directory: locator scope/count')
            for chapter in value['results']:
                check(chapter['chapter_id'] in expected_ids, 'directory: expected chapter')
                allowed_chapters[row['case_id']][chapter['chapter_id']] = chapter['project_id']
                for section in chapter['sections']:
                    allowed_sections[row['case_id']][section['section_id']] = (chapter['project_id'], chapter['chapter_id'])
        elif operation == 'chapter':
            check(allowed_chapters[row['case_id']][request['chapter_id']] == request['project'] == value['project_id'], 'directory: chapter followed from locator')
        elif operation == 'section':
            project, chapter = allowed_sections[row['case_id']][request['section_id']]
            check(request['project'] == project and value['chapter_id'] == chapter, 'directory: section followed from locator')
            for page in value['pages']:
                allowed_pages[row['case_id']][page['id']] = (project, chapter, request['section_id'])
        elif operation == 'read':
            project, chapter, section = allowed_pages[row['case_id']][request['page_id']]
            check(request['project'] == project and [n['id'] for n in value['breadcrumb'][:3]] == [project, chapter, section], 'directory: scoped read chain')
            check(value['id'] == request['page_id'] and value['offset'] == 0 and value['next_offset'] is None, 'directory: full read')
            position = 0
            for ref in sorted(value['source_refs'], key=lambda r: r['start']):
                source = sources[ref['project'], ref['session_id'], ref['turn_index']]
                check(ref['project'] == project and ref['start'] == position, 'directory: project/gap')
                check(value['content'][ref['start']:ref['end']] == source[ref['turn_start']:ref['turn_end']], 'directory: exact source coordinates')
                check(ref['message_indices'] == [ref['turn_index'] * 2, ref['turn_index'] * 2 + 1], 'directory: message indices')
                position = ref['end']; ref_count += 1
            check(position == len(value['content']) == value['total_chars'], 'directory: complete original text')
            unique_pages.add(value['id']); read_count += 1
    check(len(stored['cases']) == len(cases) == 119 and all(c['status'] == 'passed' for c in stored['cases']), 'directory: cases')
    directory[backend] = {'logical_cases': len(cases), 'raw_records': len(saved), 'operations': dict(Counter(r['operation'] for r in saved)),
                          'source_checked_reads': read_count, 'source_refs_checked': ref_count, 'unique_pages': len(unique_pages),
                          'expected_errors_preserved': expected_errors, 'source_mismatches': 0}
report['gates']['directory']['results'] = directory
report.update(status='passed', checks=checks, finished_at=datetime.now(timezone.utc).isoformat())
with OUTPUT.open('x', encoding='utf-8') as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2); handle.write('\n')
print(json.dumps({'status': report['status'], 'checks': checks, 'output': str(OUTPUT)}))
