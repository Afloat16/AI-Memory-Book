"""Independently audit all saved suffix-probe rows without executing recall."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import traceback

PROBE_SHA = '73f941662352da8a11e78499cdec1cfec55ebef67f2fedbbb34f68ee04d34389'
BASELINE = '78cc906d81818a16884de7de2e613e5a56346f93'
CANDIDATE = '021a384567db5aa64fde155f090d2eb399f55c03'
VARIANTS = {
    'suffix_other_scope': 'Production retry_limit=99，旧值已撤销，此值仅用于 staging。',
    'suffix_pending': 'Production retry_limit=99，旧值已撤销，pending staging approval。',
    'safe_causal_control': 'Production retry_limit=7，旧值已因延迟测试失败而弃用。',
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def original_sessions(variant, count):
    def record(sid, body, date):
        return {'project': 'workers', 'session_id': sid, 'task_id': 'shared-task',
                'task_title': 'Worker configuration', 'title': 'Worker configuration',
                'created_at': date, 'messages': [{'role': 'assistant', 'content': body}]}
    result = [record(f'decision-{i}', 'Production retry_limit=3. ' + 'production retry_limit. ' * 12,
                     '2026-01-01T00:00:00Z') for i in range(count)]
    result.append(record('latest', VARIANTS[variant], '2026-10-01T00:00:00Z'))
    return result

def row_audit(row):
    sources = original_sessions(row['variant'], row['count'])
    require(row['sources'] == sources, 'Original scenario differs from retained probe')
    originals = {s['session_id']: 'ASSISTANT: ' + s['messages'][0]['content'] for s in sources}
    dates = {s['session_id']: datetime.fromisoformat(s['created_at'].replace('Z', '+00:00')).isoformat()
             for s in sources}
    response, pages = row['response'], row['original_pages']
    require(response['query'] == 'current production retry_limit' and response['budget_chars'] == 1200
            and response['context_chars'] == len(response['context']) <= 1200
            and response['temporal']['requested'] == row['mode'] and response['cache_hit'] is False
            and response['strategy'] == 'book' and len(response['results']) <= 1,
            'Request, mode, cache, result-count or budget contract differs')
    ids = [hit['id'] for hit in response['results']]
    require(len(ids) == len(set(ids)) and set(pages) == set(ids), 'Duplicate or missing page follow-up')
    blocks, sessions = [], []
    for hit in response['results']:
        page = pages[hit['id']]
        require(bool(hit['source_refs']), 'Missing snippet source')
        sid = hit['source_refs'][0]['session_id']
        require(sid in originals, 'Unknown source session')
        original, date = originals[sid], dates[sid]
        expected_ref = {'project': 'workers', 'session_id': sid, 'turn_index': 0,
                        'message_indices': [0], 'start': 0, 'end': len(original),
                        'turn_start': 0, 'turn_end': len(original), 'created_at': date}
        require(page['id'] == hit['id'] and page['content'] == original and page['offset'] == 0
                and page['next_offset'] is None and page['total_chars'] == len(original)
                and hit['page_chars'] == len(original) and page['source_refs'] == [expected_ref]
                and page['created_at'] == hit['created_at'] == date
                and page['breadcrumb'][0]['id'] == hit['breadcrumb'][0]['id'] == 'workers',
                'Full original page/source/scope/timestamp differs')
        covered = [False] * len(hit['text'])
        for ref in hit['source_refs']:
            require(ref['project'] == 'workers' and ref['session_id'] == sid
                    and ref['turn_index'] == 0 and ref['message_indices'] == [0]
                    and ref['created_at'] == date, 'Snippet attribution differs')
            lo, hi = ref['turn_start'], ref['turn_end']
            require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(original)
                    and ref['start'] == lo and ref['end'] == hi, 'Invalid original coordinates')
            fragment = original[lo:hi]
            start = hit['text'].find(fragment)
            require(start >= 0, 'Snippet differs from original source slice')
            for i in range(start, start + len(fragment)):
                covered[i] = True
        require(all(seen or char.isspace() or char == '…' for seen, char in zip(covered, hit['text']))
                and hit['excerpt_spans'] == [[ref['start'], ref['end']] for ref in hit['source_refs']],
                'Unsupported snippet text or altered excerpt coordinates')
        blocks.append(f"[{hit['id']}] workers / {sid} | {date}\n" + hit['text'])
        sessions.append(sid)
    require('\n\n'.join(blocks) == response['context'], 'Unverified text outside citation framing')
    require(row['first_session'] == (sessions[0] if sessions else None), 'Producer first-source label differs')

def arm_audit(path, expected_commit, expected_backend):
    report = json.loads((path / 'report.json').read_text())
    source = report['before']
    require(report['status'] == 'completed' and source == report['after']
            and source['commit'] == expected_commit and source['backend'] == expected_backend,
            'Arm source/status/backend binding differs')
    package = Path(source['package']).resolve()
    checkout = package.parents[2]
    require(package == checkout / 'src/memory_book/__init__.py', 'Unexpected actual package path')
    git = lambda *args: subprocess.check_output(['git', '-C', str(checkout), *args])
    names = git('ls-tree', '-r', '--name-only', expected_commit, 'src/memory_book').decode().splitlines()
    require(source['files'] == {name: sha(git('show', expected_commit + ':' + name)) for name in names},
            'Recorded runtime differs from complete requested Git source')
    rows = json.loads((path / 'raw.json').read_text())
    expected = {(variant, count, mode) for variant in VARIANTS for count in (2, 8, 104)
                for mode in ('relevance', 'current')}
    found = {}
    for row in rows:
        key = row['variant'], row['count'], row['mode']
        require(key in expected and key not in found, 'Unexpected or duplicate case')
        row_audit(row)
        found[key] = row
    require(set(found) == expected, 'Incomplete response matrix')
    require(report['summary'] == [{key: row[key] for key in ('variant', 'count', 'mode', 'first_session')}
                                  for row in rows], 'Producer summary differs from checked rows')
    return found

def payload(row):
    return {key: value for key, value in row['response'].items() if key != 'latency_ms'}

def run(root):
    execution = json.loads((root / 'execution.json').read_text())
    probe = Path(execution['probe_path'])
    require(execution['status'] == 'completed' and execution['probe_sha256'] == PROBE_SHA
            and sha(probe.read_bytes()) == PROBE_SHA, 'The unchanged frozen probe is not authenticated')
    entries = {entry['arm']: entry for entry in execution['arms']}
    require(set(entries) == {'baseline-python', 'candidate-python', 'baseline-native', 'candidate-native'}
            and len(execution['arms']) == 4, 'Execution arm inventory differs')
    arms = {}
    for name, entry in entries.items():
        variant, backend = name.split('-')
        expected_commit = BASELINE if variant == 'baseline' else CANDIDATE
        require(entry['exit_code'] == 0 and entry['unchanged'] is True
                and entry['source_before'] == entry['source_after'], 'Execution failed or changed source')
        source = entry['source_before']
        require(source['commit'] == expected_commit and source['backend'] == backend
                and source['python'] == execution['python'] and source['executable'] == execution['executable'],
                'Interpreter/backend/commit differs from replay registration')
        if backend == 'native':
            binary = Path(source['binary'])
            require(binary.parent == Path(source['package']).parent
                    and sha(binary.read_bytes()) == source['native_sha256'], 'Native binary binding differs')
        else:
            require(source['binary'] is None, 'Python arm unexpectedly loaded a native extension')
        arms[name] = arm_audit(root / name, expected_commit, backend)
        arm_source = json.loads((root / name / 'report.json').read_text())['before']
        require(arm_source['files'] == source['files'] and arm_source['package'] == source['package'],
                'Wrapper and actual probe source bindings differ')
    comparisons = []
    for backend in ('python', 'native'):
        before, after = arms['baseline-' + backend], arms['candidate-' + backend]
        negative, positive, relevance_changes = [], [], []
        for key, old in before.items():
            new = after[key]
            item = {'cell': list(key), 'baseline': old['first_session'], 'candidate': new['first_session']}
            if key[2] == 'current':
                (positive if key[0] == 'safe_causal_control' else negative).append(item)
            elif any(old['response'][field] != new['response'][field]
                     for field in ('results', 'context', 'candidate_count')):
                relevance_changes.append(list(key))
        comparisons.append({'backend': backend, 'responses_per_arm': len(before),
            'negative_cells': negative, 'positive_cells': positive,
            'new_incorrect_promotions': [x for x in negative if x['baseline'] != 'latest' and x['candidate'] == 'latest'],
            'baseline_known_incorrect_promotions': [x for x in negative if x['baseline'] == 'latest'],
            'candidate_incorrect_promotions': [x for x in negative if x['candidate'] == 'latest'],
            'positive_updates_recovered': sum(x['candidate'] == 'latest' for x in positive),
            'relevance_payload_changes': relevance_changes})
    consistency = {}
    for arm in ('baseline', 'candidate'):
        a, b = arms[arm + '-python'], arms[arm + '-native']
        consistency[arm] = [list(key) for key in a if payload(a[key]) != payload(b[key])
                            or a[key]['original_pages'] != b[key]['original_pages']]
    previous = root.parent / 'resumed-suffix-scope-review-attempt1'
    baseline_previous = arm_audit(previous / 'baseline', BASELINE, 'python')
    baseline_repeat_changes = [list(key) for key in baseline_previous
                              if payload(baseline_previous[key]) != payload(arms['baseline-python'][key])
                              or baseline_previous[key]['original_pages'] != arms['baseline-python'][key]['original_pages']]
    accepted = all(not row['candidate_incorrect_promotions'] and row['positive_updates_recovered'] == 3
                   and not row['relevance_payload_changes'] for row in comparisons)
    return {'status': 'verified', 'accepted': accepted, 'responses': sum(map(len, arms.values())),
            'comparisons': comparisons, 'backend_payload_differences_excluding_only_latency': consistency,
            'original_baseline_replay_differences_excluding_only_latency': baseline_repeat_changes,
            'source_scope_budget_coordinates_and_framing_verified': True,
            'probe_sha256': PROBE_SHA, 'auditor_sha256': sha(Path(__file__).read_bytes()),
            'files': {str(path.relative_to(root)): sha(path.read_bytes())
                      for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'audit.json'},
            'scope': 'Two authored negative formulations and one positive control across three sizes. Backend/size repeats are not independent quality questions; no latency claim.'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Use a fresh audit output path')
    try:
        result = run(args.root)
    except BaseException as error:
        result = {'status': 'failed', 'error': {'type': type(error).__name__, 'message': str(error),
                                              'traceback': traceback.format_exc()}}
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        raise
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'accepted', 'responses', 'comparisons',
          'backend_payload_differences_excluding_only_latency', 'original_baseline_replay_differences_excluding_only_latency')},
          ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
