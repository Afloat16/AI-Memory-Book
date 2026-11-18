"""Audit and summarize original scale ZIP bytes without extraction or API calls."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys

REPO = Path('/workspace/scratch/428c08bef2bc/AI-Memory-Book')
ARCHIVE = Path('/workspace/scratch/428c08bef2bc/v013-scale-evidence/original-artifact-44314074983-1.zip')
OUTPUT = Path(__file__).with_name('scale-run1-saved-response-review.json')
EXPECTED_ZIP = 'a15df28d653c08dbd447e4ec3308c79df43ac7ebd997d8baab88706c92c1fed3'
sys.path.insert(0, str(REPO))
from benchmarks import v013_scale as scale
from benchmarks.v013_workload import cases, checkpoints, digest
from scripts.audit_v013_scale_ci import request_schedule, normalized_directory, page_id_violations

checks = 0
def require(value, label):
    global checks
    checks += 1
    if not value:
        raise AssertionError(label)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def metric(values):
    values = sorted(values)
    return {'n': len(values), 'p50': statistics.median(values),
            'p95_nearest_rank': values[math.ceil(.95 * len(values)) - 1],
            'min': values[0], 'max': values[-1]}

def relative(path):
    return 'run/' + str(PurePosixPath(path).relative_to(original_root))

report = {'schema': 'v013-scale-zip-independent-review-v1', 'run_id': 44314074983, 'run_attempt': 1,
          'started_at': datetime.now(timezone.utc).isoformat(), 'script_sha256': sha(Path(__file__).read_bytes()),
          'memory_book_api_calls': 0, 'archive_sha256': sha(ARCHIVE.read_bytes()),
          'boundary': 'Original ZIP read in memory. No database extraction/restoration, new retrieval, ingestion, or performance measurement.',
          'stages': {}, 'issues': []}
require(report['archive_sha256'] == EXPECTED_ZIP, 'GitHub ZIP digest')
configuration = scale.plan()
totals = Counter()
observed_intervals = []
with ZipFile(ARCHIVE) as archive:
    def raw(path):
        return archive.read(path)
    def js(path):
        return json.loads(raw(path))
    inventory = js('artifact-files.json')
    require(set(archive.namelist()) == set(inventory['retained']) | {'artifact-files.json'}, 'ZIP file inventory')
    for name, expected in inventory['retained'].items():
        payload = raw(name)
        require(len(payload) == expected['bytes'] and sha(payload) == expected['sha256'], 'retained artifact ' + name)
    report['retained_files_hash_verified'] = len(inventory['retained'])
    report['zip_files'] = len(archive.namelist())
    manifest = js('run/manifest.json')
    original_root = PurePosixPath(next(iter(manifest['stages'].values()))['build']['result_path']).parents[2]
    require(manifest['status'] == 'measurements_completed' and not manifest['interruptions']
            and not manifest['unexecuted_or_incomplete_cells'] and not manifest['unattached_attempt_directories'], 'completed matrix')
    require(manifest['binding']['protocol'] == scale.frozen_identity('b3fd165cb632c439ff28873fdba7f33e9d258178'), 'frozen protocol')
    specs = {s['id']: s for s in checkpoints('main')}
    require(set(manifest['stages']) == set(specs), 'all main checkpoints')
    runtimes = manifest['binding']['runtimes']
    for arm, expected_commit in [('baseline', '8044e4bafe18e73ea422af5eeb47ef961e65246c'), ('candidate', '9ea37a7c72aec21b6f106d9631d72d72199e283b')]:
        identity = runtimes[arm]
        require(identity['commit'] == expected_commit, 'arm source SHA')
        for name, wanted in identity['files'].items():
            committed = subprocess.check_output(['git', '-C', str(REPO), 'show', expected_commit + ':' + name])
            require(sha(committed) == wanted, arm + ': source Git bytes ' + name)
        require(digest(identity['files']) == identity['tracked_runtime_sha256'], 'tracked source digest algorithm')
        native = js(arm + '-native.json')
        require(native['commit'] == expected_commit and native['backend'] == 'native'
                and identity['native_extension_files'][PurePosixPath(native['extension_file']).name] == native['extension_sha256'], 'native proof binding')
    report['binding'] = {'protocol': manifest['binding']['protocol'], 'runtimes': {
        arm: {k: value[k] for k in ('commit', 'tracked_runtime_sha256', 'native_extension_files')}
        for arm, value in runtimes.items()}}
    report['host'] = manifest['host']
    report['source_binary_boundary'] = 'Tracked source bytes verified against Git. Historical native import path/hash proofs cross-checked; original hosted binaries are not present locally and are not claimed rebuilt.'
    all_quality = {}
    all_timing = []
    for checkpoint, stage in manifest['stages'].items():
        spec = specs[checkpoint]
        require(stage['spec'] == spec and stage['status'] == 'completed', 'stage spec/status')
        build = stage['build']['result']
        require(stage['build']['complete'] and build == js(relative(stage['build']['result_path'])), 'builder original result')
        require(build['actual_pages'] == spec['total_pages'] == build['fingerprint']['source_tables']['pages']['rows'], 'actual real-ingest pages')
        require(build['fingerprint'] == js('run/' + checkpoint + '/fingerprint.json'), 'original fingerprint')
        require(stage['control_checks'] == scale.check_control(spec, build['fingerprint'], manifest['stages']), 'source controls')
        require(stage['summary'] == js('run/' + checkpoint + '/summary.json'), 'original summary')
        require([(b['round'], b['arm']) for b in stage['blocks']] == [(i, a) for i, order in enumerate(configuration['measurement']['arm_order_by_round']) for a in order], 'strict paired round order')
        quality = defaultdict(list)
        timing = defaultdict(list)
        round_timing = defaultdict(list)
        failures, incomplete_performance, missing_context, resource_rows = [], Counter(), Counter(), []
        for block in stage['blocks']:
            arm, round_number = block['arm'], block['round']
            execution = block['execution']
            require(execution['complete'] and execution['returncode'] == 0 and not execution['timed_out'], 'completed accepted block')
            result = js(relative(execution['result_path']))
            require(result == execution['result'] and result['runtime'] == runtimes[arm], 'worker identity/result')
            require(result['fingerprint_after']['source_tables_sha256'] == build['fingerprint']['source_tables_sha256'], 'worker source invariant')
            require(block['restoration']['restored_database_sha256'] == stage['snapshot']['database_sha256']
                    and block['restoration']['restored_database_bytes'] == stage['snapshot']['database_bytes'], 'each arm identical baseline snapshot')
            require(result['imported'] == {k: js(arm + '-native.json')[k] for k in ('package_file', 'backend', 'extension_sha256', 'extension_file')}, 'actual worker imported extension')
            directory = str(PurePosixPath(relative(execution['result_path'])).parent)
            observations = [json.loads(line) for line in raw(directory + '/observations.jsonl').splitlines()]
            original_bytes = raw(directory + '/responses.jsonl.gz')
            selected, schedule = request_schedule(configuration, spec['revision'], round_number)
            require(len(observations) == len(schedule) == result['observations'], 'complete block call count')
            offset = 0
            for sequence, (row, expected) in enumerate(zip(observations, schedule), 1):
                require((row['case'], row['mode'], row.get('repetition'), row.get('warm_call')) == expected, 'exact call schedule')
                require(row['sequence'] == sequence and row['arm'] == arm and row['round'] == round_number, 'call identity')
                require(row['raw_gzip_offset'] == offset and row['raw_gzip_bytes'] > 0, 'gzip offset')
                packet = json.loads(gzip.decompress(original_bytes[offset:offset + row['raw_gzip_bytes']]))
                offset += row['raw_gzip_bytes']
                require(packet['sequence'] == sequence and packet['observation'] == {k:v for k,v in row.items() if k not in ('raw_gzip_offset', 'raw_gzip_bytes', 'raw_sha256')}, 'raw packet and compact row')
                original = packet['original_response']
                require(digest(original) == row['raw_sha256'] and digest(scale.stable_response(original)) == row['stable_response_sha256'], 'raw/stable hash')
                require(row['error'] is None, 'unexpected recorded API error')
                case = selected[row['case']]
                response = normalized_directory(original, configuration) if case['surface'] == 'directory' else original
                require(row['surface'] == case['surface'] and row['lifecycle'] == case['lifecycle'], 'case labels')
                if case['surface'] == 'recall':
                    require(response['query'] == case['query'] and response['budget_chars'] == 2400 and len(response['results']) <= 5, 'raw request/limit')
                violations, unverifiable = page_id_violations(response, case, spec)
                require(not violations and not unverifiable, 'independent source page IDs')
                rescored = scale.score(response, case, spec, 2400)
                require(rescored == row['score'], 'original source text/coordinate/gold score')
                cache_valid = response.get('cache_hit') is (row['mode'] == 'warm-result-cache') if case['surface'] == 'recall' and row['mode'] != 'quality' else True
                require(cache_valid and row['cache_mode_valid'], 'cold/warm cache actual mode')
                require(not rescored['source_errors'], 'source evidence support')
                totals['primary_measurements'] += 1
                totals['source_refs_checked'] += len(rescored['source_refs'])
                if row['mode'] == 'quality':
                    totals['quality_calls'] += 1
                    quality[arm].append({k: row[k] for k in ('case', 'surface', 'error', 'score', 'stable_response_sha256')})
                    if rescored['complete'] is False:
                        failures.append({'arm': arm, 'case': row['case'], 'query': case['query'], 'score': rescored,
                                         'original_archive_member': directory + '/responses.jsonl.gz',
                                         'gzip_offset': row['raw_gzip_offset'], 'gzip_bytes': row['raw_gzip_bytes'], 'raw_sha256': row['raw_sha256']})
                    if rescored['returned_context_for_missing']:
                        missing_context[arm] += 1
                else:
                    totals['performance_calls'] += 1
                    timing[arm, row['case'], row['mode']].append(row)
                    round_timing[round_number, arm, row['case'], row['mode']].append(row)
                    if rescored['complete'] is False:
                        incomplete_performance[arm] += 1
            require(offset == len(original_bytes), 'no missing/unindexed raw tail')
            totals['completed_blocks'] += 1
            observed_intervals.append((result['started_at_utc'], result['finished_at_utc'], checkpoint, arm, round_number))
            resource_rows.append({'arm': arm, 'round': round_number, 'initialization_wall_ns': result['initialization_wall_ns'],
                                  'process_lifetime_peak_rss_bytes': result['resources']['process_lifetime_peak_rss_bytes'],
                                  'storage_after': result['storage_after']['total_file_bytes']})
        require(dict(quality) == stage['summary']['quality_case_records'], 'full quality case records independently rebuilt')
        quality_totals = {arm: scale.quality_totals(values) for arm, values in quality.items()}
        require(quality_totals == stage['summary']['quality'], 'quality totals independently rebuilt')
        timing_rows = []
        for original in stage['summary']['timing']:
            key = original['arm'], original['case'], original['mode']
            values = timing[key]
            expected_n = 90 if original['mode'] == 'warm-result-cache' else 30
            require(len(values) == expected_n == original['attempted'] and original['errors'] == original['cache_mode_mismatches'] == 0, 'registered fixed samples')
            for field in ('wall_ns', 'process_cpu_ns'):
                require(metric([v[field] for v in values]) == original[field], 'independent p50/p95/min/max ' + field)
            timing_rows.append(original)
        for pair in stage['summary']['paired_round_ratios']:
            require(pair['eligible_equal_complete_samples'], 'paired equal-complete samples')
            for field in ('wall_ns', 'process_cpu_ns'):
                base = round_timing[pair['round'], 'baseline', pair['case'], pair['mode']]
                cand = round_timing[pair['round'], 'candidate', pair['case'], pair['mode']]
                ratio = statistics.median(r[field] for r in cand) / statistics.median(r[field] for r in base)
                require(ratio == pair[field + '_candidate_over_baseline_p50'], 'independent paired median ratio')
        by_arm = {arm:{r['case']:r for r in values} for arm,values in quality.items()}
        score_changes = [key for key in by_arm['baseline'] if by_arm['baseline'][key]['score'] != by_arm['candidate'][key]['score']]
        projection_changes = [key for key in by_arm['baseline'] if by_arm['baseline'][key]['score']['evidence_projection_sha256'] != by_arm['candidate'][key]['score']['evidence_projection_sha256']]
        all_quality[checkpoint] = by_arm
        comparative_timing = []
        for case, mode in sorted({(r['case'], r['mode']) for r in timing_rows}):
            both = {r['arm']:r for r in timing_rows if r['case'] == case and r['mode'] == mode}
            base, cand = both['baseline'], both['candidate']
            ratios = [r['wall_ns_candidate_over_baseline_p50'] for r in stage['summary']['paired_round_ratios'] if r['case'] == case and r['mode'] == mode]
            entry = {'checkpoint': checkpoint, 'case': case, 'mode': mode,
                     'baseline_wall_ms': {k:v / 1e6 if k != 'n' else v for k,v in base['wall_ns'].items()},
                     'candidate_wall_ms': {k:v / 1e6 if k != 'n' else v for k,v in cand['wall_ns'].items()},
                     'candidate_over_baseline_p50': cand['wall_ns']['p50'] / base['wall_ns']['p50'],
                     'baseline_over_candidate_p50': base['wall_ns']['p50'] / cand['wall_ns']['p50'],
                     'paired_round_candidate_over_baseline_p50': {'median':statistics.median(ratios),'min':min(ratios),'max':max(ratios)},
                     'baseline_cpu_ns':base['process_cpu_ns'], 'candidate_cpu_ns':cand['process_cpu_ns']}
            comparative_timing.append(entry); all_timing.append(entry)
        report['stages'][checkpoint] = {'spec':spec, 'actual_pages':build['actual_pages'],
            'projects':build['fingerprint']['source_tables']['projects']['rows'], 'sessions':build['fingerprint']['source_tables']['sessions']['rows'],
            'builder_ingest_calls':build['ingest_calls'], 'database_bytes':stage['snapshot']['database_bytes'],
            'source_tables_sha256':build['fingerprint']['source_tables_sha256'], 'controls':stage['control_checks'],
            'quality':quality_totals, 'score_changes_between_arms':score_changes, 'evidence_projection_changes_between_arms':projection_changes,
            'stable_json_changes_between_arms':sum(by_arm['baseline'][key]['stable_response_sha256'] != by_arm['candidate'][key]['stable_response_sha256'] for key in by_arm['baseline']),
            'quality_failures':failures, 'performance_calls_with_incomplete_evidence':dict(incomplete_performance),
            'missing_queries_with_nonempty_context':dict(missing_context), 'timing':comparative_timing, 'resources':resource_rows}
    controls = {}
    for checkpoint, reference in [('age-shift-1024','age-reference-1024'), ('interleaved-100000','own-100000')]:
        controls[checkpoint] = {}
        for arm in ('baseline','candidate'):
            current, old = all_quality[checkpoint][arm], all_quality[reference][arm]
            changed = [key for key in current if current[key]['score']['evidence_projection_sha256'] != old[key]['score']['evidence_projection_sha256']]
            require(len(changed) == len(manifest['stages'][checkpoint]['control_output_changes'][arm]['changed_evidence_projections']), 'counterfactual outputs')
            controls[checkpoint][arm] = {'compared_cases':len(current), 'changed_evidence_projections':changed}
    report['counterfactual_outputs'] = controls
    for earlier, later in zip(sorted(observed_intervals), sorted(observed_intervals)[1:]):
        require(earlier[1] <= later[0], 'measured worker processes do not overlap')
    require(totals['completed_blocks'] == 84 and totals['quality_calls'] == 1008 and totals['performance_calls'] == 12600 and totals['primary_measurements'] == 13608, 'final count matrix')
    report['totals'] = dict(totals)
    report['quality_all_stages_per_arm'] = {}
    for arm in ('baseline','candidate'):
        by_surface = {}
        for surface in ('recall','directory'):
            summed = Counter()
            for stage in report['stages'].values():
                summed.update(stage['quality'][arm][surface])
            by_surface[surface] = dict(summed)
        report['quality_all_stages_per_arm'][arm] = by_surface
    report['timing_scope'] = 'Single Ubuntu24.04 hosted runner. Directory is the complete navigation/read chain. Cold deletes only recall_cache; OS/pager/helper caches not flushed. p95 nearest rank at n30 cold/directory or n90 warm. Quality failures remain failures.'
    report['performance_direction_counts'] = {mode:{'comparisons':len(v := [r for r in all_timing if r['mode']==mode]),
        'candidate_p50_faster':sum(r['candidate_over_baseline_p50']<1 for r in v),
        'candidate_p50_slower':sum(r['candidate_over_baseline_p50']>1 for r in v),
        'min_candidate_over_baseline_p50':min(r['candidate_over_baseline_p50'] for r in v),
        'max_candidate_over_baseline_p50':max(r['candidate_over_baseline_p50'] for r in v)}
        for mode in ('cold-result-cache','warm-result-cache','uncached-directory')}
report.update(status='passed_saved_record_integrity', checks=checks, finished_at=datetime.now(timezone.utc).isoformat())
with OUTPUT.open('x',encoding='utf-8') as handle:
    json.dump(report,handle,ensure_ascii=False,indent=2);handle.write('\n')
print(json.dumps({'status':report['status'],'checks':checks,'totals':report['totals'],'output':str(OUTPUT),'performance_direction_counts':report['performance_direction_counts']}))
