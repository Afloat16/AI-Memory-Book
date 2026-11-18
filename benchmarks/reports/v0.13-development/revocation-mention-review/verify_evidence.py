"""Offline verification of preserved review-fix outputs; performs no recall."""
from pathlib import Path
import gzip, hashlib, json, sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SOURCE = '971504257ab03082a0557c638297d482c18f3876'
sys.path.insert(0, str(ROOT / 'benchmarks'))
import v012_revision_eval as v012
import v013_accuracy_eval as v013


def sha(value):
    return hashlib.sha256(value).hexdigest()


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in ('latency_ms', 'cache_hit')}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def verify():
    result = {'source': SOURCE, 'normalization': 'Recursively omit latency_ms and cache_hit only; preserve all other response, source, score and diagnostic fields.', 'matrices': [], 'backend_equivalence': []}
    all_rows = {}
    for version, evaluator, expected in [('v013', v013, 496), ('v012', v012, 304)]:
        for backend in ('python', 'native'):
            name = f'{version}-{backend}-attempt1'
            path = OUT / name
            audit = evaluator.audit(path)
            report = json.loads((path / 'report.json').read_text())
            rows = [json.loads(line) for line in gzip.decompress((path / 'raw.jsonl.gz').read_bytes()).splitlines()]
            assert audit['status'] == 'verified' and audit['responses'] == expected
            assert report['backend'] == backend and report['recall_version'] == 24
            assert report['source_before']['commit'] == SOURCE
            assert report['source_after'] == report['source_before']
            assert (report['loaded_native'] is not None) == (backend == 'native')
            auto = [r for r in report['summary'] if r['mode'] == 'auto' and r['kind'] == 'answerable']
            assert len(auto) == 4 and all(r['cases'] == r['first_correct'] == r['complete_evidence'] for r in auto)
            if version == 'v013':
                assert all(r['score']['assessment_correct'] and r['score']['occurrence_intent_correct'] for r in rows)
            all_rows[name] = rows
            result['matrices'].append({'path': name, 'status': audit['status'], 'responses': expected, 'cases': len({r['case_id'] for r in rows}), 'runtime_sha256': report['source_before']['source_sha256'], 'evaluator': report['evaluator'], 'native': report['loaded_native'], 'auto_answerable_cells': auto, 'assessment_labels_correct': sum(r['score'].get('assessment_correct', False) for r in rows) if version == 'v013' else None})
        left = all_rows[f'{version}-python-attempt1']
        right = all_rows[f'{version}-native-attempt1']
        assert stable(left) == stable(right)
        result['backend_equivalence'].append({'matrix': version, 'rows': len(left), 'equal': True})
    review = []
    expected_inputs = '3ff77042210278bf1322a9e46702d10db4387b9784597dd3bd9263d6a9649718'
    for backend in ('python', 'native'):
        path = OUT / f'original-review-{backend}-attempt1'
        receipt = json.loads((path / 'receipt.json').read_text())
        raw = (path / 'raw.json').read_bytes()
        rows = json.loads(raw)
        journal = [json.loads(line) for line in (path / 'raw.jsonl').read_text().splitlines()]
        assert receipt['runtime_head'] == SOURCE and receipt['backend'] == backend
        assert sha(raw) == receipt['raw_sha256'] and rows == journal and len(rows) == receipt['responses'] == 13
        assert sha((path / 'inputs.json').read_bytes()) == receipt['inputs_sha256'] == expected_inputs
        review.append(rows)
    assert stable(review[0]) == stable(review[1])
    result['backend_equivalence'].append({'matrix': 'independent-review', 'entries': 13, 'direct_responses': 12, 'bound_MCP_SDK_groups': 1, 'equal': True})
    result['review_input_sha256'] = expected_inputs
    result['review_observations'] = []
    for item in review[0]:
        if 'response' not in item:
            continue
        response = item['response']
        temporal = response.get('temporal', {})
        assessment = temporal.get('evidence_assessment', {})
        result['review_observations'].append({'case': item['case'], 'request': item['request'], 'first_session': response['results'][0]['source_refs'][0]['session_id'] if response['results'] else None, 'assessment': assessment.get('status'), 'conflicts': len(assessment.get('conflicts', [])), 'nondecision_promotions': temporal.get('nondecision_priority', {}).get('promotions', 0)})
    previous = OUT.parent / 'assessment-review-fix'
    result['unchanged_original_matrices'] = []
    for name, rows in all_rows.items():
        old = [json.loads(line) for line in gzip.decompress((previous / name / 'raw.jsonl.gz').read_bytes()).splitlines()]
        assert stable(rows) == stable(old)
        result['unchanged_original_matrices'].append({'matrix': name, 'rows': len(rows), 'equal_to_source_57': True})
    for backend, rows in zip(('python', 'native'), review):
        old = json.loads((previous / f'review-{backend}-attempt1/raw.json').read_text())
        assert stable(rows) == stable(old)
        result['unchanged_original_matrices'].append({'matrix': f'original-review-{backend}', 'entries': len(rows), 'equal_to_source_57': True})
    protocol_bytes = (OUT / 'protocol.json').read_bytes()
    protocol = json.loads(protocol_bytes)
    result['passive_variants'] = []
    for arm, source, version, expected_passed in [('baseline', '57db3a81b7f6eaad38933e9b72e5b43e6eaf3a53', 23, 0), ('candidate', SOURCE, 24, 2)]:
        backend_rows = []
        for backend in ('python', 'native'):
            path = OUT / f'{arm}-{backend}-attempt1'
            receipt = json.loads((path / 'receipt.json').read_text())
            raw = (path / 'raw.jsonl').read_bytes()
            assert receipt['source_commit'] == source and receipt['recall_version'] == version
            assert receipt['backend'] == backend and receipt['protocol_sha256'] == sha(protocol_bytes)
            assert receipt['raw_sha256'] == sha(raw)
            rows = [json.loads(line) for line in raw.splitlines()]
            assert len(rows) == receipt['responses'] == 2
            for row, case in zip(rows, protocol['cases']):
                assert row['id'] == case['id'] and row['sources'] == case['sources'] and row['request'] == case['request']
                first = row['response']['results'][0]['source_refs'][0]['session_id']
                promotions = row['response']['temporal'].get('nondecision_priority', {}).get('promotions', 0)
                assert row['observed'] == {'first_session': first, 'nondecision_promotions': promotions}
                assert row['expected'] == case['expected']
                assert row['passed'] == (first == case['expected']['first_session'] and promotions == 0)
            assert sum(row['passed'] for row in rows) == receipt['passed'] == expected_passed
            assert receipt['failed'] == 2 - expected_passed
            backend_rows.append(rows)
            result['passive_variants'].append({'arm': arm, 'backend': backend, 'source': source, 'passed': expected_passed, 'failed': 2 - expected_passed, 'observations': [{'id': row['id'], **row['observed']} for row in rows]})
        assert stable(backend_rows[0]) == stable(backend_rows[1])
    result['status'] = 'verified'
    return result


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
