"""Derive reported comparisons from complete frozen records, retaining all IDs.

After the manifest finishes, run from the repository root:
    PYTHONPATH=. python scripts/assess_recall_quality.py

This verifies every completed stage's output hashes before writing the assessment
and a durable copy of the completed execution checkpoint. It runs no benchmark.
"""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from benchmarks.token_compare import summarize_rows

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    path = ROOT / path
    if path.suffix == '.gz':
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text())


def pair(name, cohorts=None):
    report = read(f'benchmarks/results/{name}.json.gz')
    assert report['validation']['passed']
    result = {'artifact': f'{name}.json.gz', 'dataset': report['dataset'], 'budgets': []}
    old, new = report['engines']
    result['sources'] = [{k: e[k] for k in ('label', 'source_sha256_before', 'source_sha256_after', 'source_provenance')} for e in (old, new)]
    for a, b in zip(old['configurations'], new['configurations']):
        assert a['budget_chars'] == b['budget_chars']
        aa, bb = ({r['id']: r for r in x['query_results']} for x in (a, b))
        assert aa.keys() == bb.keys()
        groups = cohorts or {'all': set(aa)}
        for label, ids in groups.items():
            ids = set(ids) & aa.keys()
            ar, br = ([rows[i] for i in sorted(ids)] for rows in (aa, bb))
            result['budgets'].append({
                'cohort': label, 'budget_chars': a['budget_chars'],
                'old': summarize_rows(ar), 'new': summarize_rows(br),
                'evidence_gained': sum(max(0, bb[i]['matched_evidence'] - aa[i]['matched_evidence']) for i in ids),
                'evidence_lost': sum(max(0, aa[i]['matched_evidence'] - bb[i]['matched_evidence']) for i in ids),
                'complete_queries_gained': sum(bb[i]['complete'] and not aa[i]['complete'] for i in ids),
                'complete_queries_lost': sum(aa[i]['complete'] and not bb[i]['complete'] for i in ids),
                'quality_changed_query_ids': [i for i in sorted(ids) if (aa[i]['matched_evidence'], aa[i]['complete']) != (bb[i]['matched_evidence'], bb[i]['complete'])],
                'latency_scope': 'whole measured population, not a separately timed cohort',
                'old_latency': a['latency'], 'new_latency': b['latency']})
    result['categories'] = {str(c['budget_chars']): c['by_category'] for c in new['configurations']}
    return result


def main():
    state = read('.artifacts/recall-quality-checkpoint.json')
    manifest = read('benchmarks/recall_quality_manifest.json')
    assert all(state['stages'][s['id']]['status'] == 'completed' for s in manifest['stages'])
    for stage in manifest['stages']:
        record = state['stages'][stage['id']]
        for filename in stage['outputs']:
            expected = record['outputs'][filename]
            if hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Completed output changed: {filename}')
    regression = read('benchmarks/results/recall-final-public-regression.json.gz')
    expanded = read('benchmarks/results/recall-final-public-expanded.json.gz')
    previous = {r['id'] for r in regression['engines'][0]['configurations'][0]['query_results']}
    all_ids = {r['id'] for r in expanded['engines'][0]['configurations'][0]['query_results']}
    assert previous <= all_ids
    cohorts = {'previous_256': previous, 'additional_759': all_ids - previous, 'all_1015': all_ids}
    pairs = [pair('recall-final-synthetic-' + str(seed)) for seed in (61, 211, 509)]
    pairs += [pair('recall-final-public-development'), pair('recall-final-public-expanded', cohorts), pair('recall-final-main-expanded', cohorts)]
    native = read('benchmarks/results/recall-final-components-public.json.gz')
    assert native['validation']['passed']
    engines = []
    for e in native['engines']:
        engines.append({k: v for k, v in e.items() if k not in ('native_query_costs', 'packed_configurations')})
        engines[-1]['packed_configurations'] = [{k: v for k, v in c.items() if k != 'query_results'} for c in e['packed_configurations']]
    comparisons = []
    candidate = next(e for e in engines if e['engine_selector'] == 'candidate')
    for competitor in engines:
        if competitor['engine_selector'] not in ('billion-context', 'ai-memory-hybrid'):
            continue
        for a, b in zip(candidate['packed_configurations'], competitor['packed_configurations']):
            assert (a['tokenizer'], a['budget_tokens']) == (b['tokenizer'], b['budget_tokens'])
            name = a['tokenizer']
            comparisons.append({'competitor': competitor['label'], 'tokenizer': name, 'token_budget': a['budget_tokens'],
                'evidence_recall_at_least_equal': a['metrics']['evidence_recall'] >= b['metrics']['evidence_recall'],
                'complete_evidence_at_least_equal': a['metrics']['complete_evidence_rate'] >= b['metrics']['complete_evidence_rate'],
                'mean_common_context_tokens_lower': a['metrics']['mean_context_tokens'][name] < b['metrics']['mean_context_tokens'][name],
                'candidate_evidence_recall': a['metrics']['evidence_recall'], 'competitor_evidence_recall': b['metrics']['evidence_recall'],
                'candidate_complete_evidence_rate': a['metrics']['complete_evidence_rate'], 'competitor_complete_evidence_rate': b['metrics']['complete_evidence_rate'],
                'candidate_mean_context_tokens': a['metrics']['mean_context_tokens'][name], 'competitor_mean_context_tokens': b['metrics']['mean_context_tokens'][name],
                'latency_superiority': 'not established: different component/transport boundaries',
                'generated_answer_superiority': 'not measured'})
    preflight = read('benchmarks/results/recall-final-preflight.json')
    assert preflight['validation']['passed'] and preflight['unattainable_labels'] == 0
    upgrades = {name: read('benchmarks/reports/recall-final-upgrade-' + name + '.json')['summary'] for name in ('synthetic', 'public')}
    mcp = {name: read('benchmarks/reports/recall-final-mcp-' + name + '.summary.json') for name in ('synthetic', 'public')}
    for name, report in mcp.items():
        assert all(e['same_evidence_detail_comparison']['all_contexts_identical'] for e in report['engines'] if e['same_evidence_detail_comparison']['queries'])
    result = {'schema_version': 1, 'status': 'frozen evaluation completed; universal lower-cost equal-or-better answer quality not established',
        'candidate_runtime_commit': '6f5299004642618e606d001b4c574e1bae572a7e',
        'candidate_source_sha256': '191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85',
        'completed_stages': len(manifest['stages']), 'completed_output_hashes_verified': True,
        'execution_checkpoint': '../reports/recall-final-run-checkpoint.json',
        'public_cohort_sizes': {k: len(v) for k, v in cohorts.items()},
        'paired_results': pairs, 'native_components': engines, 'common_context_comparisons': comparisons,
        'mcp': mcp, 'upgrades': upgrades,
        'preflight': {'source_corpus_checks': len(preflight['records']), 'unattainable_labels': preflight['unattainable_labels'], 'validation': preflight['validation']},
        'notes': ['No heldout outcome was used to select another source change.', 'Additional public queries share conversations with the regression set.',
                  'Common-page context tokens and native response tokens are distinct consumption surfaces.',
                  'Native ai-memory read costs follow search plus every mapped top-k page, not a minimum-read agent policy.',
                  'Quality is exact source-evidence delivery, not generated-answer accuracy; no paid model calls or API keys were used.']}
    path = ROOT / 'benchmarks/results/recall-final-assessment.json'
    (ROOT / 'benchmarks/reports/recall-final-run-checkpoint.json').write_bytes(
        (ROOT / '.artifacts/recall-quality-checkpoint.json').read_bytes())
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(path.relative_to(ROOT))
    for p in pairs:
        for b in p['budgets']:
            if b['cohort'] not in ('all', 'all_1015'):
                continue
            print(p['artifact'], b['cohort'], b['budget_chars'], 'recall', b['old']['evidence_recall'], b['new']['evidence_recall'], 'complete', b['old']['complete_evidence_rate'], b['new']['complete_evidence_rate'], 'tokens', b['old']['mean_context_tokens']['o200k_base'], b['new']['mean_context_tokens']['o200k_base'], 'p50/p95', b['old_latency']['p50_ms'], b['new_latency']['p50_ms'], b['old_latency']['p95_ms'], b['new_latency']['p95_ms'])
    print('COMPONENTS', json.dumps(comparisons))
    for name, report in mcp.items():
        for e in report['engines']:
            a = e['aggregate']['first_call_after_cache_clear']
            print('MCP', name, e['label'], a['tokens']['o200k_base']['response_text']['mean'], a['wall_ms'])


if __name__ == '__main__':
    main()
