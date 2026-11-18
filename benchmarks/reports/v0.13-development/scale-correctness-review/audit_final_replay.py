"""Offline audit of the final source-bound small replay; performs no recall."""
from __future__ import annotations
import argparse, gzip, hashlib, json, subprocess, sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from benchmarks import v012_revision_eval as v012, v013_accuracy_eval as v013
from benchmarks.v013_scale import score as scale_score, stable_response
from benchmarks.v013_workload import cases, checkpoints


def read(path):
    return json.loads(path.read_text())


def rows(path):
    raw = path.read_bytes()
    if path.suffix == '.gz':
        raw = gzip.decompress(raw)
    return [json.loads(line) for line in raw.splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_slices(row):
    """Independently reconstruct the one-turn sources of these small probes."""
    sources = {(source['project'], source['session_id']): source for source in row['sources']}
    response = row['response']
    blocks = []
    for hit in response['results']:
        text = hit['text']
        coverage = [False] * len(text)
        for ref in hit['source_refs']:
            source = sources[ref['project'], ref['session_id']]
            assert ref['turn_index'] == 0
            body = '\n\n'.join(message['role'].upper() + ': ' + message['content']
                               for message in source['messages'])
            lo, hi = ref['turn_start'], ref['turn_end']
            assert 0 <= lo < hi <= len(body)
            assert ref['end'] - ref['start'] == hi - lo
            fragment = body[lo:hi]
            start = text.find(fragment)
            assert start >= 0
            assert datetime.fromisoformat(ref['created_at'].replace('Z', '+00:00')) == datetime.fromisoformat(
                source['created_at'].replace('Z', '+00:00'))
            for index in range(start, start + len(fragment)):
                coverage[index] = True
            if row['request'].get('project') is not None:
                assert ref['project'] == row['request']['project']
        assert all(covered or char.isspace() or char == '…' for covered, char in zip(coverage, text))
        ref = hit['source_refs'][0]
        blocks.append(f"[{hit['id']}] {ref['project']} / {ref['session_id']} | {ref['created_at']}\n" + text)
    assert response['context'] == '\n\n'.join(blocks)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    quality, pair_counts, source_files = {}, {}, None
    for kind, evaluator, attempt, expected in [('62', v013, 2, 496), ('38', v012, 1, 304)]:
        backend_rows = {}
        for backend in ('python', 'native'):
            path = HERE / f'final-{kind}-{backend}-attempt{attempt}'
            audit = evaluator.audit(path)
            report = read(path / 'report.json')
            assert report['source_before']['commit'] == a.source
            assert report['recall_version'] == 26 and audit['responses'] == expected
            files = report['source_before']['files']
            assert source_files is None or source_files == files
            source_files = files
            auto = [cell for cell in audit['summary'] if cell['mode'] == 'auto' and cell['kind'] == 'answerable']
            assert len(auto) == 4 and all(cell['first_correct'] == cell['cases'] == cell['complete_evidence'] for cell in auto)
            if kind == '62':
                assert sum(cell['assessment_correct'] for cell in audit['summary']) == expected
                assert sum(cell['occurrence_intent_correct'] for cell in audit['summary']) == expected
            quality[kind + '-' + backend] = {'responses': expected, 'auto_answerable_cells': auto}
            backend_rows[backend] = rows(path / 'raw.jsonl.gz')
            prior = HERE / f'integrated-{kind}-{backend}-attempt1'
            comparison = evaluator.compare(prior, path)
            assert not comparison['score_changes'] and not comparison['regressions']
            assert not comparison['relevance_payload_changes']
            assert not comparison.get('occurrence_history_payload_changes')
        assert len(backend_rows['python']) == len(backend_rows['native'])
        assert all(stable_response(left) == stable_response(right)
                   for left, right in zip(backend_rows['python'], backend_rows['native']))
        pair_counts[kind] = expected
    expected_py = {name: digest for name, digest in source_files.items() if name.endswith('.py')}
    scale = {}
    for backend in ('python', 'native'):
        path = HERE / f'final-64-{backend}-attempt1'
        receipt, raw = read(path / 'receipt.json'), rows(path / 'raw.jsonl')
        assert receipt['source_commit'] == a.source and receipt['runtime_files'] == expected_py
        assert sha(path / 'raw.jsonl') == receipt['raw_sha256']
        assert [row['case'] for row in raw] == [case for case in cases() if case['surface'] == 'recall']
        for row in raw:
            assert row['score'] == scale_score(row['response'], row['case'], checkpoints()[0])
            assert not row['score']['source_errors']
        assert sum(row['score']['complete'] is True for row in raw) == 56
        assert all(row['score']['required_ranks'] == [2, 1] for row in raw if row['case']['category'] == 'multi_source')
        scale[backend] = raw
    assert all(stable_response(left) == stable_response(right) for left, right in zip(scale['python'], scale['native']))
    pair_counts['64'] = 64
    controls = {}
    for name, expected in [('reference-only', 18), ('checklist', 2), ('checklist-revision', 2), ('report-fact', 2),
                           ('reference-negation', 3), ('quoted-frame', 4), ('quoted-colon', 2), ('unicode-forms', 2),
                           ('revocation', 2)]:
        backend_rows = {}
        for backend in ('python', 'native'):
            path = HERE / f'final-{name}-{backend}-attempt1'
            receipt, raw = read(path / 'receipt.json'), rows(path / 'raw.jsonl')
            assert receipt.get('source', receipt.get('source_commit')) == a.source
            assert receipt.get('runtime_files', receipt.get('source_files_sha256')) == expected_py
            assert sha(path / 'raw.jsonl') == receipt['raw_sha256']
            assert len(raw) == receipt['responses'] == receipt['passed'] == expected
            for row in raw:
                original_slices(row)
                first = row['response']['results'][0]['source_refs'][0]['session_id']
                expected_first = row.get('expected_first', row.get('expected', {}).get('first_session'))
                assert first == expected_first and row['passed'] is True
                if name in ('checklist', 'checklist-revision', 'report-fact', 'revocation') and expected_first != 'decision':
                    assert not row['response']['temporal'].get('nondecision_priority')
            backend_rows[backend] = raw
        assert all(stable_response(left) == stable_response(right)
                   for left, right in zip(backend_rows['python'], backend_rows['native']))
        controls[name] = {'responses_per_backend': expected, 'passed_per_backend': expected}
        pair_counts[name] = expected
    old_reviews = {}
    for backend in ('python', 'native'):
        path = HERE / f'final-original-review-{backend}-attempt1'
        receipt, raw = read(path / 'receipt.json'), read(path / 'raw.json')
        assert receipt['runtime_head'] == a.source and receipt['runtime_files_sha256'] == expected_py
        assert receipt['responses'] == len(raw) == 13 and sha(path / 'raw.json') == receipt['raw_sha256']
        prior = HERE / f'integrated-original-review-{backend}-attempt1'
        assert sha(path / 'inputs.json') == sha(prior / 'inputs.json')
        assert stable_response(raw) == stable_response(read(prior / 'raw.json'))
        old_reviews[backend] = raw
    assert stable_response(old_reviews['python']) == stable_response(old_reviews['native'])
    pair_counts['original-review'] = 13
    for backend in ('python', 'native'):
        log = (HERE / f'final-controls-{backend}-attempt1.log').read_text()
        assert 'Ran 10 tests in ' in log and log.rstrip().endswith('OK')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT)
    assert all(hashlib.sha256(git('show', a.source + ':' + name)).hexdigest() == digest
               for name, digest in source_files.items())
    result = {'status': 'passed', 'scope': 'Development small replays after inspecting scale failures; no formal scale or external competitor claim.',
              'source': a.source, 'recall_version': 26, 'source_files': source_files,
              'quality': quality, 'scale': {'responses_per_backend': 64, 'answerable_complete': '56/56',
                  'multi_source_required_ranks': [2, 1], 'current_first': '16/24', 'source_errors': 0,
                  'missing_controls': 8}, 'independent_controls': controls,
              'original_review_entries_per_backend': 13, 'unit_methods_per_backend': 10,
              'backend_equal_pairs': pair_counts, 'total_backend_equal_pairs': sum(pair_counts.values()),
              'runtime_0a48_quality_score_regressions': 0,
              'retained_limitations': ['Pure-prose 最终输出维度/current.phase_size remain unchanged in the original review.',
                  'Unicode/name and report-facet guards are conservative syntactic rules, not universal natural-language interpretation.',
                  'Missing-result/assessment metadata does not prove absence across an entire archive.'],
              'auditor_sha256': sha(Path(__file__))}
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'source', 'scale', 'total_backend_equal_pairs')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
