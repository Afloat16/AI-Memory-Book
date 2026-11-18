"""Build a factual run2 readout from the frozen independent audit and original ZIP.

No MemoryBook imports, ingestion, retrieval, database restoration, or new timing.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import json
import statistics
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--audit', type=Path, required=True)
p.add_argument('--archive', type=Path, required=True)
p.add_argument('--repo-root', type=Path, required=True)
p.add_argument('--output-dir', type=Path, required=True)
a = p.parse_args()
a.output_dir.mkdir(parents=True, exist_ok=True)
sha = lambda b: hashlib.sha256(b).hexdigest()
audit_raw = a.audit.read_bytes()
j = json.loads(audit_raw)
expected_archive = '47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac'
expected_candidate = 'e0e2515f6e16404cfb9b676cd2eab01ce84b81cc'
expected_auditor = 'c9bc8c58405968c3f81bc2ec6cacbdcc39f020ac22f61ed16128c5d8046866f9'
assert j['status'] == 'passed_saved_record_integrity'
assert j['run_id'] == 44331778554 and j['run_attempt'] == 1
assert j['binding']['runtimes']['candidate']['commit'] == expected_candidate
assert j['archive_sha256'] == expected_archive and j['script_sha256'] == expected_auditor
assert a.archive.stat().st_size == 29394152 and sha(a.archive.read_bytes()) == expected_archive
with ZipFile(a.archive) as z:
    manifest_raw = z.read('run/manifest.json')
    m = json.loads(manifest_raw)
    inventory_raw = z.read('artifact-files.json')
    ci_audit = json.loads(z.read('independent-audit.json'))
    workflow = json.loads(z.read('workflow-status.json'))
    registered = json.loads(z.read('registered-matrix.json'))
    infos = z.infolist()
    assert len(infos) == 570 and sum(i.file_size for i in infos) == 85698042
    assert ci_audit['measurement_complete'] and not ci_audit['issues']
    assert workflow['candidate_commit'] == expected_candidate
    for s in m['stages'].values():
        assert s['summary']['quality'] == j['stages'][s['spec']['id']]['quality']

module_bindings = {}
for name in ('benchmarks/v013_scale.py', 'benchmarks/v013_workload.py', 'scripts/audit_v013_scale_ci.py'):
    raw = (a.repo_root / name).read_bytes()
    committed = subprocess.check_output(['git', '-C', str(a.repo_root), 'show', expected_candidate + ':' + name])
    assert raw == committed, name
    module_bindings[name] = sha(raw)
assert module_bindings['scripts/audit_v013_scale_ci.py'] == ci_audit['auditor_sha256']

quality_delta = {}
for name, s in m['stages'].items():
    records = {arm: {r['case']: r for r in rows} for arm, rows in s['summary']['quality_case_records'].items()}
    changed = {'became_complete': [], 'became_incomplete': [], 'current_first_improved': [],
               'current_first_regressed': [], 'source_error_regressions': []}
    for key, before in records['baseline'].items():
        b, c = before['score'], records['candidate'][key]['score']
        if b['complete'] is False and c['complete'] is True:
            changed['became_complete'].append(key)
        if b['complete'] is True and c['complete'] is False:
            changed['became_incomplete'].append(key)
        if b['current_source_first'] is False and c['current_source_first'] is True:
            changed['current_first_improved'].append(key)
        if b['current_source_first'] is True and c['current_source_first'] is False:
            changed['current_first_regressed'].append(key)
        if not b['source_errors'] and c['source_errors']:
            changed['source_error_regressions'].append(key)
    changed['candidate_multi_source_ranks'] = {key:r['score']['required_ranks'] for key,r in records['candidate'].items() if key.endswith(':multi_source')}
    quality_delta[name] = changed

all_timing = [r for s in j['stages'].values() for r in s['timing']]
modes = ('cold-result-cache', 'warm-result-cache', 'uncached-directory')
directions = {}
for mode in modes:
    rows = [r for r in all_timing if r['mode'] == mode]
    directions[mode] = {
        'groups':len(rows),
        'pooled_p50_faster':sum(r['candidate_over_baseline_p50'] < 1 for r in rows),
        'pooled_p50_slower':sum(r['candidate_over_baseline_p50'] > 1 for r in rows),
        'median_paired_p50_faster':sum(r['paired_round_candidate_over_baseline_p50']['median'] < 1 for r in rows),
        'median_paired_p50_slower':sum(r['paired_round_candidate_over_baseline_p50']['median'] > 1 for r in rows),
        'p95_faster':sum(r['candidate_wall_ms']['p95_nearest_rank'] < r['baseline_wall_ms']['p95_nearest_rank'] for r in rows),
        'p95_slower':sum(r['candidate_wall_ms']['p95_nearest_rank'] > r['baseline_wall_ms']['p95_nearest_rank'] for r in rows),
    }
    old = j['performance_direction_counts'][mode]
    assert directions[mode]['pooled_p50_faster'] == old['candidate_p50_faster']
    assert directions[mode]['pooled_p50_slower'] == old['candidate_p50_slower']

binding = {
    'schema':'v013-scale-run2-independent-review-binding-v1',
    'run_id':44331778554, 'run_attempt':1, 'github_artifact_id':14439324717,
    'artifact_identity_origin':'Official artifact identity supplied by root after download; local bytes and frozen auditor independently checked the same SHA256.',
    'archive':{'filename':a.archive.name,'bytes':a.archive.stat().st_size,'sha256':expected_archive,
               'members':len(infos),'uncompressed_bytes':sum(i.file_size for i in infos)},
    'frozen_protocol':j['binding']['protocol'],'runtimes':j['binding']['runtimes'],
    'frozen_independent_auditor':{'commit':'0217221e49acd4858ab1874b882ae5e5bc94034d',
        'path':'benchmarks/reports/v0.13-development/scale-run2-review/audit_scale_zip_v2.py','sha256':expected_auditor},
    'review_time_imported_module_git_bindings':module_bindings,
    'original_manifest_sha256':sha(manifest_raw),'original_inventory_sha256':sha(inventory_raw),
    'independent_audit':{'filename':'scale-run2-saved-response-review.json','sha256':sha(audit_raw),
        'status':j['status'],'checks':j['checks'],'totals':j['totals']},
    'quality_case_deltas':quality_delta,'performance_direction_definitions_and_counts':directions,
    'source_and_binary_boundary':j['source_binary_boundary'],
    'memory_book_api_calls_in_this_review':0,'database_restoration_performed':False,
    'interpretation':'Saved-record integrity is separate from retrieval quality and performance. Run2 reuses the frozen workload after development informed by run1, and is not an unseen benchmark or an external-product scale comparison.'}

b = j['quality_all_stages_per_arm']['baseline']
c = j['quality_all_stages_per_arm']['candidate']
lines = []
def add(text=''):
    lines.append(text)
def table(headers, rows):
    add('| ' + ' | '.join(headers) + ' |')
    add('| ' + ' | '.join('---' for _ in headers) + ' |')
    for row in rows:
        add('| ' + ' | '.join(str(x) for x in row) + ' |')
    add()
def ms(value):
    return f'{value:.4f}'
def timing(checkpoint, case, mode):
    return next(r for r in j['stages'][checkpoint]['timing'] if r['case']==case and r['mode']==mode)

add('# v0.13 longitudinal experiment: independent run2 review')
add()
add('The candidate recovered complete required evidence for every answerable recall configuration in this frozen synthetic workload. Speed is mixed: 37 of 49 cold-result-cache groups and 7 of 49 warm-result-cache groups have a higher candidate pooled p50; all 14 directory-navigation groups have a lower candidate pooled p50. Missing-answer queries still return context. These results do not establish universal correctness, reliable abstention, or superiority over other products.')
add()
add('All numbers below are derived from the original ZIP and the unchanged, independently executed [saved-response auditor](audit_scale_zip_v2.py). The [complete audit JSON](scale-run2-saved-response-review.json), [source/archive binding](scale-run2-review-binding.json), and [review receipt](scale-run2-review-receipt.json) retain exact hashes and definitions. Run1 and its failed attempts remain separate evidence.')
add()
add('## Identity and integrity')
add()
table(['Item','Observed identity'],[
    ['Run / attempt','44331778554 / 1'],['GitHub artifact ID','14439324717'],
    ['Candidate',expected_candidate],['Baseline',j['binding']['runtimes']['baseline']['commit']],
    ['Frozen protocol commit','b3fd165cb632c439ff28873fdba7f33e9d258178'],
    ['Original ZIP bytes','29,394,152'],['Original ZIP SHA256',expected_archive],
    ['ZIP members / uncompressed bytes','570 / 85,698,042'],
    ['Retained inventory files verified',j['retained_files_hash_verified']],
    ['Independent integrity checks',f"{j['checks']:,}"],
    ['Original API measurements',f"{j['totals']['primary_measurements']:,} = {j['totals']['quality_calls']:,} quality + {j['totals']['performance_calls']:,} performance"],
    ['Accepted arm blocks / original source references',f"{j['totals']['completed_blocks']} / {j['totals']['source_refs_checked']:,}"],
    ['New MemoryBook calls during this review',0]])
add('The audit reconstructed source page IDs, source coordinates, frozen scores, navigation/read chains, sample schedules, medians, nearest-rank p95 values, and paired-round ratios. All 84 accepted blocks completed without missing calls, API errors, cache-mode mismatches or unindexed raw tails. The original records show every arm restored from its baseline snapshot and no overlapping measured worker processes. This saved-response review did not restore a database or rebuild the historical hosted binaries; native import paths and binary hashes were checked against the retained worker identities.')
add()
add('## Correctness: retain the denominators')
add()
table(['Metric','Baseline','Candidate'],[
    ['Recall configurations',b['recall']['queries'],c['recall']['queries']],
    ['Complete answerable recall',f"{b['recall']['complete']}/{b['recall']['answerable']}",f"{c['recall']['complete']}/{c['recall']['answerable']}"],
    ['Required recall evidence spans covered',f"{b['recall']['covered_spans']}/{b['recall']['required_spans']}",f"{c['recall']['covered_spans']}/{c['recall']['required_spans']}"],
    ['Current-source-first recall',f"{b['recall']['current_source_first']}/{b['recall']['current_first_eligible']}",f"{c['recall']['current_source_first']}/{c['recall']['current_first_eligible']}"],
    ['Recall with stale evidence before current',b['recall']['stale_before_current'],c['recall']['stale_before_current']],
    ['Missing-answer queries returning context',f"{b['recall']['returned_context_for_missing']}/{b['recall']['missing_queries']}",f"{c['recall']['returned_context_for_missing']}/{c['recall']['missing_queries']}"],
    ['Complete directory navigation/read queries',f"{b['directory']['complete']}/{b['directory']['answerable']}",f"{c['directory']['complete']}/{c['directory']['answerable']}"],
    ['Quality outputs with source errors',b['recall']['source_error_outputs']+b['directory']['source_error_outputs'],c['recall']['source_error_outputs']+c['directory']['source_error_outputs']],
    ['Performance calls with incomplete evidence',sum(s['performance_calls_with_incomplete_evidence'].get('baseline',0) for s in j['stages'].values()),sum(s['performance_calls_with_incomplete_evidence'].get('candidate',0) for s in j['stages'].values())]])
add('There are 64 recall questions and 8 directory questions reused across seven checkpoints per arm, not 504 independent new questions. Of the 64 recall questions, 56 are answerable and 8 deliberately lack the requested answer. The 392/392 result is 56 answerable questions times seven checkpoints; it does not turn the 56 nonempty missing-answer outputs into successful abstentions.')
add()
add('All 56 baseline incomplete quality configurations are the eight multi-source questions repeated across the seven stages. They become complete in the candidate. All 56 candidate multi-source outputs retain required ranks `[2, 1]`: the boundary evidence is first and the current policy is second. Thus current-source-first remains 112/168, not 168/168. The 32 early stale-first current-question configurations improve; no previously complete answerable case becomes incomplete and no previously correct current-first case regresses under the frozen scoring criteria. The exact changed case IDs are retained in the binding JSON.')
add()
quality_rows=[]
for name,s in j['stages'].items():
    q=s['quality']
    quality_rows.append([name,f"{s['actual_pages']:,}",f"{q['baseline']['recall']['complete']}/56",f"{q['candidate']['recall']['complete']}/56",f"{q['baseline']['recall']['current_source_first']}/24",f"{q['candidate']['recall']['current_source_first']}/24",'8/8 each'])
table(['Checkpoint','Real pages','Baseline complete','Candidate complete','Baseline current first','Candidate current first','Directory complete'],quality_rows)
add('The source checks found no cross-project source error in either arm. That is evidence of preserved isolation in the measured cases, not a new isolation advantage over the baseline. Original baseline failures remain in `quality_failures`, including archive member names, gzip offsets, byte counts and response hashes. The 840 baseline performance calls missing required multi-source evidence remain in the timing tables; correctness is not traded for a faster label.')
add()
add('## Growth, age and layout controls')
add()
table(['Checkpoint','Foreign pages','Additional target-history pages','Projects','Sessions','SQLite snapshot bytes'],[
    [name,s['spec']['foreign_pages'],s['spec']['own_pages'],s['projects'],s['sessions'],s['database_bytes']] for name,s in j['stages'].items()])
add('The corpus was built through actual MemoryBook.ingest calls with explicit turn segmentation. The initial target histories have 16 pages each; two inactive target histories remain fixed while six active or newcomer histories grow. The peak corpus has 100,000 pages across 788 exact projects. This is a deterministic synthetic engineering history, not a production trace, a default-adaptive-segmentation measurement, a million-page test, or a scale comparison with the historical external baselines. The optional 200,000-page profile was not executed.')
add()
add('The age pair uses fresh databases with the same content and ingest order, shifting all source dates by 3,650 days. The layout pair preserves the final logical corpus and source IDs while changing physical ingest order. For each pair and each arm, all 72 evidence projections are unchanged. The replacement stage updates six source histories at fixed total size. The original control checks and fingerprints are retained in the audit and ZIP.')
add()
fixed=[timing(k,'routing-archive:directory','uncached-directory')['candidate_wall_ms']['p50'] for k in ('age-reference-1024','foreign-10016','foreign-50016')]
add(f'The fixed inactive project is not constant-cost as unrelated projects grow: its candidate directory-chain p50 rises from {ms(fixed[0])} ms at 1,024 total pages to {ms(fixed[1])} ms at 10,016 and {ms(fixed[2])} ms at 50,016. Global FTS work and physical layout still matter.')
add()
layout_rows=[]
for case,mode in [('routing-archive:current','cold-result-cache'),('routing-archive:historical','cold-result-cache'),('routing-archive:directory','uncached-directory'),('ranking-next:directory','uncached-directory')]:
    before=timing('own-100000',case,mode)
    after=timing('interleaved-100000',case,mode)
    layout_rows.append([case,mode,ms(before['baseline_wall_ms']['p50']),ms(before['candidate_wall_ms']['p50']),ms(after['baseline_wall_ms']['p50']),ms(after['candidate_wall_ms']['p50'])])
table(['Case','Mode','Clustered baseline p50 ms','Clustered candidate p50 ms','Interleaved baseline p50 ms','Interleaved candidate p50 ms'],layout_rows)
add('The unchanged output projections do not imply equal performance across layouts. Both layouts are shown so the best contiguous-project result cannot hide the cost of an old project whose rows are interleaved with similar projects.')
add()
add('## Performance definitions and every group')
add()
add('The six arm orders are AB, BA, BA, AB, AB, BA. Each performance recall question has 30 cold-result-cache and 90 warm-result-cache samples per arm per checkpoint; each directory chain has 30 samples. The p95 is the nearest-rank empirical quantile. These are single-host observations, not confidence intervals or general service-level guarantees. Initialization, snapshot restoration, scoring and raw journaling are outside each API timer. A directory sample times the complete locator → section → source-read chain.')
add()
add('Cold means the recall-result cache was cleared before the call. It does not flush SQLite pager state, OS page cache or helper caches. Warm means a verified hit of the saved recall-result cache. Each paired-round ratio divides that round’s candidate median by its baseline median; the median of those six ratios is separate from the ratio of pooled p50 values.')
add()
table(['Mode','Groups','Pooled p50 faster / slower','Median paired p50 faster / slower','p95 faster / slower'],[
    [mode,x['groups'],f"{x['pooled_p50_faster']} / {x['pooled_p50_slower']}",f"{x['median_paired_p50_faster']} / {x['median_paired_p50_slower']}",f"{x['p95_faster']} / {x['p95_slower']}"] for mode,x in directions.items()])
add('All seven warm groups with a higher candidate pooled p50 are `training-core:multi_source`, one at each checkpoint. Those baseline responses are incomplete and the candidate responses are complete; both timings are retained without treating unequal evidence quality as equivalent work. The largest cold pooled p50 ratio is approximately 1.564, so the candidate is not uniformly faster. Differences very close to 1 are reported as measured signs, not statistical significance claims.')
add()
for mode in modes:
    add('### ' + mode)
    add()
    add('All groups are included. B = baseline, C = candidate. C/B below 1 means lower candidate latency; above 1 means higher latency. Times are milliseconds.')
    add()
    rows=[]
    for r in all_timing:
        if r['mode']!=mode: continue
        paired=r['paired_round_candidate_over_baseline_p50']
        rows.append([r['checkpoint'],r['case'],r['baseline_wall_ms']['n'],ms(r['baseline_wall_ms']['p50']),ms(r['candidate_wall_ms']['p50']),ms(r['baseline_wall_ms']['p95_nearest_rank']),ms(r['candidate_wall_ms']['p95_nearest_rank']),f"{r['candidate_over_baseline_p50']:.6f}",f"{paired['median']:.6f}",'higher' if r['candidate_over_baseline_p50']>1 else 'lower'])
    table(['Checkpoint','Case','n/arm','B p50','C p50','B p95','C p95','Pooled C/B','Median paired C/B','Candidate p50'],rows)
add('## Host and resource boundary')
add()
add(f"Host: {j['host']['cpu']}, {j['host']['logical_cpu_count']} logical CPUs, {j['host']['platform']}; Python {j['host']['python']}; SQLite {j['host']['sqlite']}. The workflow uses Ubuntu 24.04. The measurement manifest started at {m['started_at_utc']} and last saved at {m['last_saved_at_utc']}; that interval includes construction, restoration and orchestration, so it is not a per-query latency measurement.")
add()
resource_rows=[]
for arm in ('baseline','candidate'):
    resources=[r for s in j['stages'].values() for r in s['resources'] if r['arm']==arm]
    peaks=[r['process_lifetime_peak_rss_bytes']/1048576 for r in resources]
    resource_rows.append([arm,len(resources),f'{min(peaks):.3f}',f'{max(peaks):.3f}'])
table(['Arm','Worker processes','Minimum lifetime peak RSS MiB','Maximum lifetime peak RSS MiB'],resource_rows)
add('RSS is a worker process lifetime high-water mark, not isolated per-call memory allocation. Round 0 also executes 72 quality calls before its timed work; later rounds do not. SQLite snapshot sizes appear above, and worker storage/initialization records remain in the full audit JSON. The saved-response review checks the recorded restoration hashes; it does not independently restore excluded database snapshots.')
add()
add('Run1 used an Intel Xeon host, while this run uses AMD EPYC. Performance benefits here are computed only against the baseline paired within run2. Absolute run1-to-run2 latency changes are not attributed to the candidate. Run2 was executed after inspecting run1 failures and developing fixes; the protocol and gold stayed frozen, but the workload is no longer unseen. Older 38/62-question, engineering, short-page, directory-contract, CI and external-library results retain their separate sources and denominators.')
add()
add('## Reproduce the saved-record audit')
add()
add('Obtain the exact original ZIP matching the SHA256 above, then run the frozen auditor with these arguments. This command reads saved records and does not execute retrieval:')
add()
add('```sh')
add('python benchmarks/reports/v0.13-development/scale-run2-review/audit_scale_zip_v2.py \\')
add('  --repo-root /path/to/AI-Memory-Book \\')
add('  --archive /path/to/original-artifact-44331778554-1.zip \\')
add('  --output /path/to/new-independent-review.json \\')
add('  --expected-zip-sha256 ' + expected_archive + ' \\')
add('  --run-id 44331778554 --run-attempt 1 \\')
add('  --candidate ' + expected_candidate)
add('```')
add()
add('The output path must be new: the auditor deliberately refuses to overwrite a previous report. The frozen source commits must be available locally, and the registered protocol/score files must retain their recorded bytes.')
add()

summary_raw=('\n'.join(lines)).encode()
summary_path=a.output_dir/'scale-run2-summary.md'
binding_path=a.output_dir/'scale-run2-review-binding.json'
binding_raw=(json.dumps(binding,ensure_ascii=False,indent=2)+'\n').encode()
for path,raw in ((summary_path,summary_raw),(binding_path,binding_raw)):
    with path.open('xb') as f:f.write(raw)
receipt={
    'schema':'v013-scale-run2-independent-review-receipt-v1','created_at':datetime.now(timezone.utc).isoformat(),
    'status':'passed_saved_record_integrity','run_id':44331778554,'run_attempt':1,
    'auditor_frozen_commit':'0217221e49acd4858ab1874b882ae5e5bc94034d','auditor_sha256':expected_auditor,
    'original_audit_exit_code_observed':0,'audit_started_at':j['started_at'],'audit_finished_at':j['finished_at'],
    'audit_checks':j['checks'],'original_measurement_counts':j['totals'],
    'archive_sha256':expected_archive,'candidate_source':expected_candidate,
    'files':{a.audit.name:{'bytes':len(audit_raw),'sha256':sha(audit_raw)},summary_path.name:{'bytes':len(summary_raw),'sha256':sha(summary_raw)},binding_path.name:{'bytes':len(binding_raw),'sha256':sha(binding_raw)},Path(__file__).name:{'bytes':Path(__file__).stat().st_size,'sha256':sha(Path(__file__).read_bytes())}},
    'all_primary_timing_groups_reported':len(all_timing),'memory_book_api_calls':0,
    'database_restoration_performed':False,'original_run1_files_modified':False,
    'interpretation':'This receipt records an audit of previously measured data. The 166409 checks are integrity/scoring/statistical assertions, not additional benchmark questions or API calls.'}
receipt_path=a.output_dir/'scale-run2-review-receipt.json'
with receipt_path.open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'summary':str(summary_path),'binding':str(binding_path),'receipt':str(receipt_path),
                  'quality_deltas':{key:sum(len(v[key]) for v in quality_delta.values()) for key in ('became_complete','became_incomplete','current_first_improved','current_first_regressed','source_error_regressions')},
                  'performance_directions':directions,'summary_bytes':len(summary_raw)}))
