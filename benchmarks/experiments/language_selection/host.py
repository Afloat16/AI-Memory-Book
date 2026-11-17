"""Isolated language experiment host; all product files remain frozen."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import sqlite3
import subprocess
import sys
import sysconfig
import traceback
import unicodedata
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import experiment as exp

VARIANTS = ['current', 'rust_same', 'c_table', 'rust_table', 'rust_window',
            'c_window', 'node_window', 'node_small', 'rust_metadata', 'c_metadata']
COHORTS = ['synthetic61', 'public1015', 'unicode_stress']
CONFIGS = list(exp.CONFIGS)
LOCOMO_URL = 'https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json'
LOCOMO_SHA = '79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4'


def git(*args, **kwargs):
    return subprocess.check_output(['git', *args], cwd=ROOT, **kwargs)


def execute(args, destination, env=None, timeout=600):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x') as stream:
        process = subprocess.Popen([str(a) for a in args], cwd=ROOT, env=env,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RuntimeError(f'Command exceeded {timeout}s; partial evidence: {destination}')
    if code:
        raise RuntimeError(f'Command failed ({code}); retained {destination}')


def host_identity():
    packages = {}
    for name in ('mcp', 'pydantic', 'setuptools', 'tiktoken'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {'python': sys.version, 'platform': platform.platform(), 'cpu_count': os.cpu_count(),
        'affinity': sorted(os.sched_getaffinity(0)), 'packages': packages,
        'cpu_model': next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                           if line.startswith('model name')), None),
        'gcc': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
        'rustc': subprocess.check_output(['rustc', '--version'], text=True).strip(),
        'cargo': subprocess.check_output(['cargo', '--version'], text=True).strip(),
        'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'node_executable_sha256': exp.file_hash(shutil.which('node')),
        'bash': subprocess.check_output(['bash', '--version'], text=True).splitlines()[0],
        'bash_executable_sha256': exp.file_hash(shutil.which('bash')),
        'sqlite': sqlite3.sqlite_version, 'unicode_database': unicodedata.unidata_version,
        'runner_image': {key: os.environ.get(key) for key in ('ImageOS', 'ImageVersion')},
        'workflow_run_id': os.environ.get('GITHUB_RUN_ID'),
        'workflow_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}


def preparation(output, env, phase):
    if output.exists():
        raise RuntimeError('Choose a new experiment directory; never overwrite an attempt')
    output.mkdir(parents=True)
    changed = git('diff', '--name-only', exp.BASELINE, 'HEAD').decode().splitlines()
    assert all(name.startswith('benchmarks/experiments/language_selection/') or
               name == '.github/workflows/language-selection-performance.yml' for name in changed), changed
    builds = output / 'builds'
    builds.mkdir()
    source = output / 'current/src/memory_book'
    source.parent.mkdir(parents=True)
    names = git('ls-tree', '-r', '--name-only', exp.BASELINE, 'src/memory_book').decode().splitlines()
    assert names == git('ls-tree', '-r', '--name-only', 'HEAD', 'src/memory_book').decode().splitlines()
    for name in names:
        raw = git('show', exp.BASELINE + ':' + name)
        if (ROOT / name).read_bytes() != raw:
            raise AssertionError('Product differs from the fixed baseline: ' + name)
        path = source / Path(name).relative_to('src/memory_book')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    ext = sysconfig.get_config_var('EXT_SUFFIX')
    binary = source / ('_native' + ext)
    flags = ['-shared', '-fPIC', '-O3', '-DNDEBUG', '-g', '-fwrapv', '-Wall',
             '-I' + sysconfig.get_path('include')]
    command = ['gcc', *flags, str(source / '_native.c'), '-o', str(binary)]
    execute(command, builds / 'current.log', env)
    exp.save(builds / 'current.json', {'command': command, 'binary_sha256': exp.file_hash(binary)})
    rust_outputs = {}
    for label, features in [('same', ''), ('table', 'table'), ('owned', 'owned-window')]:
        build_name = 'rust-core-table' if label == 'table' else 'rust-' + label
        target = builds / build_name
        cmd = [sys.executable, HERE / 'rust/build.py', '--package-source', source, '--output-dir', target]
        if features:
            cmd += ['--features', features]
        execute(cmd, builds / (build_name + '.log'), env)
        rust_outputs[label] = target
        if label == 'table':
            archive = Path(env['CARGO_TARGET_DIR']) / 'release/liblanguage_rust.a'
            shutil.copyfile(archive, target / 'liblanguage_rust.a')
    alternate = output / 'rust-same/src/memory_book'
    shutil.copytree(source, alternate, ignore=shutil.ignore_patterns('*.so', '__pycache__'))
    shutil.copyfile(rust_outputs['same'] / ('_native' + ext), alternate / ('_native' + ext))
    for label in ('c', 'rust'):
        target = builds / (label + '-table')
        cmd = [sys.executable, HERE / 'c_table/build.py', '--native-source', source / '_native.c',
               '--output', target]
        if label == 'rust':
            cmd += ['--rust-library', rust_outputs['table'] / 'liblanguage_rust.a']
        execute(cmd, builds / (label + '-table.log'), env)
    execute([sys.executable, HERE / 'c_owned/build.py', '--native-source', source / '_native.c',
             '--output', builds / 'c-owned'], builds / 'c-owned.log', env)
    for kind in ('rust', 'c'):
        execute([sys.executable, HERE / (kind + '_metadata/build.py'), '--python-source', source.parent,
            '--output', builds / (kind + '-metadata')], builds / (kind + '-metadata.log'), env)
    locomo = output / 'locomo10.json'
    raw = urlopen(LOCOMO_URL, timeout=60).read()
    assert hashlib.sha256(raw).hexdigest() == LOCOMO_SHA and len(raw) == 2805274
    locomo.write_bytes(raw)
    import tiktoken
    assert tiktoken.__version__ == '0.12.0'
    tiktoken.get_encoding('cl100k_base').encode('Warm vocabulary before timed workers.')
    sys.path[:0] = [str(source.parent), str(ROOT)]
    from memory_book import _native
    methods = sorted(name for name in dir(_native) if not name.startswith('_'))
    assert len(methods) == 22
    manifest = {'schema_version': 1, 'status': 'formal' if phase == 'formal' else 'preflight',
        'baseline_commit': exp.BASELINE, 'experiment_commit': git('rev-parse', 'HEAD').decode().strip(),
        'host': host_identity(), 'locomo': str(locomo), 'locomo_sha256': LOCOMO_SHA,
        'native_methods': methods, 'variants': {}}
    for variant in [*VARIANTS, 'aa_current', 'python_reference']:
        manifest['variants'][variant] = {'source': str(source.parent),
            'native_binary_sha256': exp.file_hash(binary), 'expected_runtime_registered_methods': []}
    manifest['variants']['python_reference'].pop('native_binary_sha256')
    manifest['variants']['rust_same'].update(source=str(alternate.parent),
        native_binary_sha256=exp.file_hash(alternate / ('_native' + ext)))
    for variant, label in [('c_table', 'c'), ('rust_table', 'rust')]:
        path = builds / (label + '-table') / ('_language_c_table' + ext)
        manifest['variants'][variant].update(plugin=str(path), plugin_binary_sha256=exp.file_hash(path),
            expected_runtime_registered_methods=['fold_excerpt_source'])
    rust_owned = rust_outputs['owned'] / ('_language_rust' + ext)
    manifest['variants']['rust_window'].update(rust_owned=str(rust_owned),
        rust_owned_sha256=exp.file_hash(rust_owned), expected_runtime_registered_methods=['excerpt_window'])
    c_owned = builds / 'c-owned' / ('_language_c_owned' + ext)
    manifest['variants']['c_window'].update(c_owned=str(c_owned),
        c_owned_sha256=exp.file_hash(c_owned), expected_runtime_registered_methods=['excerpt_window'])
    manifest['variants']['node_window']['expected_runtime_registered_methods'] = ['excerpt_window']
    manifest['variants']['node_small']['expected_runtime_registered_methods'] = ['terms_ascii', 'ascii_tokens', 'context_allocations']
    for kind in ('rust', 'c'):
        module_name = '_language_' + kind + '_metadata'
        path = builds / (kind + '-metadata') / (module_name + ext)
        manifest['variants'][kind + '_metadata'].update(metadata_plugin=str(path),
            metadata_module=module_name, metadata_plugin_sha256=exp.file_hash(path))
    tracked = git('ls-files', 'src/memory_book', 'benchmarks/experiments/language_selection',
                  'benchmarks/locomo_split.json', 'scripts/native_language_performance.py',
                  'tests/test_native_backend.py', 'tests/test_native_excerpt_backend.py',
                  'tests/test_native_window_backend.py',
                  'tests/test_round5_candidate_c4.py',
                  '.github/workflows/language-selection-performance.yml').decode().splitlines()
    tracked = sorted(set(tracked) | {str(p.relative_to(ROOT)) for p in (ROOT / 'benchmarks').glob('*.py')})
    bound = {}
    for name in tracked:
        path = ROOT / name
        assert path.read_bytes() == git('show', 'HEAD:' + name), 'Commit exact evaluator/candidate bytes first'
        bound[str(path)] = exp.file_hash(path)
    for runtime in (source, alternate):
        for path in runtime.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                bound[str(path)] = exp.file_hash(path)
    for spec in manifest['variants'].values():
        for key in ('plugin', 'rust_owned', 'c_owned', 'metadata_plugin'):
            if spec.get(key):
                bound[spec[key]] = exp.file_hash(spec[key])
    for path in builds.rglob('*'):
        if path.is_file() and path.suffix in ('.so', '.a') and 'target' not in path.relative_to(builds).parts:
            bound[str(path)] = exp.file_hash(path)
    bound[str(locomo)] = LOCOMO_SHA
    bound[str(Path(shutil.which('node')).resolve())] = manifest['host']['node_executable_sha256']
    bound[str(Path(shutil.which('bash')).resolve())] = manifest['host']['bash_executable_sha256']
    manifest['file_sha256'] = bound
    exp.save(output / 'manifest.json', manifest)
    return manifest


def make_plan(manifest, phase):
    plan = {'rounds': 6 if phase == 'formal' else 1, 'repeats': 2 if phase == 'formal' else 1,
        'variants': VARIANTS, 'cohorts': {}, 'configs': CONFIGS, 'primary_targets': [], 'stress_targets': [],
        'key_scenarios': [], 'benefit_percent': 5.0, 'regression_percent': 3.0,
        'minimum_improving_rounds': 5, 'bootstrap_resamples': 10000,
        'aa': {'rounds': 3 if phase == 'formal' else 0, 'repeats': 1,
               'cohort': 'public1015', 'configs': CONFIGS[:2], 'variants': ['current', 'aa_current'],
               'placement': {'before_main_rounds': [0, 2, 4] if phase == 'formal' else []}},
        'scope': 'Tested implementations at stated boundaries, not all possible programs in a language.',
        'cache_policy': 'Direct result cache disabled; MCP result cache cleared before every call. Other existing caches and OS/SQLite caches retained.',
        'adoption': 'No production changes in this experiment. Stress-only wins do not justify general migration.'}
    for name in COHORTS:
        data = exp.cohort(name, manifest['locomo'])
        plan['cohorts'][name] = {'query_ids': [q.id for q in data.queries],
                                'query_count': len(data.queries), 'dataset': data.description()}
        for config in CONFIGS:
            for metric in ('p50_ms', 'p95_ms'):
                target = {'cohort': name, 'configuration': config, 'metric': metric}
                plan['key_scenarios'].append(target)
                if config.endswith('char2400'):
                    plan['stress_targets' if name == 'unicode_stress' else 'primary_targets'].append(target)
        for metric in ('fresh_ingestion_ms', 'unchanged_ingestion_ms', 'changed_ingestion_ms'):
            target = {'cohort': name, 'configuration': 'ingestion', 'metric': metric}
            plan['key_scenarios'].append(target)
            if metric == 'fresh_ingestion_ms':
                plan['stress_targets' if name == 'unicode_stress' else 'primary_targets'].append(target)
    return plan


def make_schedule(plan):
    values = []
    for round_number in range(plan['rounds']):
        aa_round = round_number // 2
        if round_number % 2 == 0 and aa_round < plan['aa']['rounds']:
            aa_variants = ['current', 'aa_current'] if aa_round % 2 == 0 else ['aa_current', 'current']
            for variant in aa_variants:
                values.append({'key': f'aa-r{aa_round}-public1015-{variant}', 'phase': 'aa',
                    'variant': variant, 'cohort': 'public1015', 'round': aa_round,
                    'repeats': 1, 'configs': CONFIGS[:2]})
        shift = (round_number // 2) * 2
        variants = VARIANTS[shift:] + VARIANTS[:shift]
        if round_number % 2:
            variants = list(reversed(variants))
        for cohort in COHORTS:
            for variant in variants:
                values.append({'key': f'main-r{round_number}-{cohort}-{variant}', 'phase': 'main',
                    'variant': variant, 'cohort': cohort, 'round': round_number,
                    'repeats': plan['repeats'], 'configs': CONFIGS})
    return values


def checks(output, manifest, env):
    source = Path(manifest['variants']['current']['source'])
    build = output / 'builds'
    items = [
        ('rust-same', [HERE / 'rust/check.py', '--repo', ROOT, '--build', build / 'rust-same', '--python-source', source]),
        ('c-table', [HERE / 'c_table/check.py', '--source', source, '--build', build / 'c-table',
                     '--exhaustive', '--report', output / 'checks/c-table.json']),
        ('rust-table', [HERE / 'c_table/check.py', '--source', source, '--build', build / 'rust-table',
                        '--exhaustive', '--report', output / 'checks/rust-table.json']),
        ('rust-window', [HERE / 'rust/check_window.py', '--binary', manifest['variants']['rust_window']['rust_owned'],
            '--python-source', source, '--output', output / 'checks/rust-window.json']),
        ('rust-adapter', [HERE / 'rust/check_adapter.py', '--binary', manifest['variants']['rust_window']['rust_owned'],
            '--python-source', source, '--repo', ROOT, '--output', output / 'checks/rust-adapter.json']),
        ('c-window', [HERE / 'c_owned/check_window.py', '--binary', manifest['variants']['c_window']['c_owned'],
            '--python-source', source, '--output', output / 'checks/c-window.json']),
        ('c-adapter', [HERE / 'c_owned/check_adapter.py', '--binary', manifest['variants']['c_window']['c_owned'],
            '--python-source', source, '--repo', ROOT, '--output', output / 'checks/c-adapter.json']),
        ('c-owned-guards', [HERE / 'c_owned/check_guards.py', '--module', '_language_c_owned',
            '--binary', manifest['variants']['c_window']['c_owned'], '--python-source', source,
            '--output', output / 'checks/c-owned-guards.json']),
        ('rust-owned-guards', [HERE / 'c_owned/check_guards.py', '--module', '_language_rust',
            '--binary', manifest['variants']['rust_window']['rust_owned'], '--python-source', source,
            '--output', output / 'checks/rust-owned-guards.json']),
        ('node', [HERE / 'javascript/verify.py', '--source', source, '--output', output / 'checks/node.json']),
        ('node-guards', [HERE / 'javascript/check_window_guards.py', '--source', source,
                         '--kernel-report', output / 'checks/node.json',
                         '--output', output / 'checks/node-guards.json']),
        ('shell', [HERE / 'shell/check.py', '--source', source,
            '--inputs', HERE / 'javascript/captured-inputs.json', '--output', output / 'checks/shell.json']),
    ]
    for kind in ('rust', 'c'):
        spec = manifest['variants'][kind + '_metadata']
        items.append((kind + '-metadata', [HERE / 'rust_metadata/check.py', '--python-source', source,
            '--binary', spec['metadata_plugin'], '--module', spec['metadata_module'],
            '--output', output / 'checks' / (kind + '-metadata.json')]))
    (output / 'checks').mkdir()
    for name, command in items:
        print(exp.dump({'stage': 'correctness', 'check': name}), flush=True)
        execute([sys.executable, *command], output / 'logs' / ('check-' + name + '.log'), env)
    execute(['node', HERE / 'javascript/typecheck-runtime.mts', '--output',
        output / 'checks/typescript-runtime.json'], output / 'logs/check-typescript-runtime.log', env)


def measure(output, manifest, env, phase):
    plan = make_plan(manifest, phase)
    run = {'schema_version': 1, 'status': 'running', 'formal': phase == 'formal',
        'manifest': manifest, 'manifest_sha256': exp.digest(manifest), 'plan': plan,
        'schedule': make_schedule(plan), 'artifacts': {}, 'probes': [], 'file_sha256_after': {}}
    exp.save(output / 'run.json', run)
    try:
        checks(output, manifest, env)
        for variant in [*VARIANTS, 'python_reference']:
            for name in COHORTS:
                print(exp.dump({'stage': 'corpus-equivalence-and-dispatch', 'variant': variant, 'cohort': name}), flush=True)
                target = output / 'probes' / (variant + '-' + name + '.json')
                target.parent.mkdir(exist_ok=True)
                execute([sys.executable, HERE / 'experiment.py', 'probe', '--manifest', output / 'manifest.json',
                    '--variant', variant, '--cohort', name, '--output', target],
                    output / 'logs' / ('probe-' + variant + '-' + name + '.log'), env)
                probe = exp.read(target)
                if variant != 'current':
                    baseline = exp.read(output / 'probes' / ('current-' + name + '.json'))
                    assert all(probe[key] == baseline[key] for key in ('responses_sha256', 'ingestion_sha256', 'archive'))
                if variant in ('rust_window', 'c_window'):
                    assert probe['owned_window_dispatch']['completed'] > 0, 'Owned stage never ran'
                if variant in ('rust_metadata', 'c_metadata'):
                    assert probe['metadata_dispatch']['completed'] > 0, 'Metadata stage never ran'
                    assert probe['metadata_native_calls'].get('bounded_metadata', 0) > 0
                if variant == 'node_window':
                    assert probe['actual_node_operations'].get('excerpt_window', 0) > 0
                if variant == 'node_small':
                    assert probe['actual_node_operations'].get('terms_ascii', 0) > 0
                    assert probe['actual_node_operations'].get('context_allocations', 0) > 0
                run['probes'].append({'variant': variant, 'cohort': name,
                    'path': str(target.relative_to(output)), 'sha256': exp.file_hash(target)})
                exp.save(output / 'run.json', run)
        for item in run['schedule']:
            key = item['key']
            report = output / (key + '.json.gz')
            ledger = Path(str(report) + '.events.jsonl.gz')
            exp.save(output / (key + '.intent.json'), {'item': item, 'plan_sha256': exp.digest(plan)})
            print(exp.dump({'stage': 'measuring', 'worker': key}), flush=True)
            try:
                execute([sys.executable, HERE / 'experiment.py', 'worker', '--manifest', output / 'manifest.json',
                    '--variant', item['variant'], '--cohort', item['cohort'], '--round', str(item['round']),
                    '--repeats', str(item['repeats']), '--configs', ','.join(item['configs']), '--output', report],
                    output / 'logs' / (key + '.log'), env)
            finally:
                run['artifacts'][key] = {'report_sha256': exp.file_hash(report) if report.exists() else None,
                    'ledger_sha256': exp.file_hash(ledger) if ledger.exists() else None}
                exp.save(output / 'run.json', run)
        supplementary_diagnostics(output, manifest, env, phase)
        exp.verify_manifest(manifest)
        run['file_sha256_after'] = {path: exp.file_hash(path) for path in manifest['file_sha256']}
        run['status'] = 'completed'
    except BaseException as error:
        run.update(status='failed', error={'type': type(error).__name__, 'message': str(error),
                                          'traceback': traceback.format_exc()})
        raise
    finally:
        exp.save(output / 'run.json', run)


def supplementary_diagnostics(output, manifest, env, phase):
    """Separate helper evidence; these measurements cannot trigger adoption."""
    source = Path(manifest['variants']['current']['source'])
    destination = output / 'diagnostics'
    destination.mkdir()
    trials = [('rust-same', 'rust-loop=' + str(output / 'builds/rust-same') + '=_language_rust'),
              ('c-table', 'c-table=' + str(output / 'builds/c-table') + '=_language_c_table'),
              ('rust-table', 'rust-table=' + str(output / 'builds/rust-table') + '=_language_c_table')]
    for name, backend in trials:
        print(exp.dump({'stage': 'helper-diagnostics', 'comparison': name}), flush=True)
        execute([sys.executable, HERE / 'javascript/kernel_bench.py', '--source', source,
            '--inputs', HERE / 'javascript/captured-inputs.json', '--native-backend', backend,
            '--rounds', '6' if phase == 'formal' else '1',
            '--iterations', '64' if phase == 'formal' else '8',
            '--warmup', '256' if phase == 'formal' else '16',
            '--output', destination / (name + '.json')],
            output / 'logs' / ('diagnostic-' + name + '.log'), env)
    execute([sys.executable, HERE / 'shell/bench.py', '--source', source,
        '--inputs', HERE / 'javascript/captured-inputs.json', '--output', destination / 'shell.json',
        '--measure', '--rounds', '6' if phase == 'formal' else '1',
        '--iterations', '3' if phase == 'formal' else '1', '--warmup', '1' if phase == 'formal' else '0',
        '--cold-starts', '3' if phase == 'formal' else '1'], output / 'logs/diagnostic-shell.log', env)
    exp.save(destination / 'files.json', {str(p.relative_to(destination)): exp.file_hash(p)
        for p in sorted(destination.iterdir()) if p.is_file()})


def preserve(output):
    """Persist evidence on a new research ref using the user's verified identity."""
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return
    assert os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
    run_id = os.environ['GITHUB_RUN_ID']
    branch = 'validation/language-selection-results-' + run_id
    index = output.parent / ('evidence-index-' + run_id)
    env = {**os.environ, 'GIT_INDEX_FILE': str(index), 'GIT_AUTHOR_NAME': 'Afloat',
        'GIT_AUTHOR_EMAIL': 'ShuffleMonkey@163.com', 'GIT_COMMITTER_NAME': 'Afloat',
        'GIT_COMMITTER_EMAIL': 'ShuffleMonkey@163.com'}
    subprocess.run(['git', 'read-tree', 'HEAD'], cwd=ROOT, env=env, check=True)
    files = [(path, str(path.relative_to(output))) for path in sorted(output.rglob('*'))]
    files += [(output.parent / name, '__host__/' + name)
              for name in ('host.log', 'analyze.log', 'packages.json')]
    count = 0
    for path, relative in files:
        if (not path.is_file() or relative.startswith(('current/', 'rust-same/'))
                or any(part in ('cargo-target', 'target', '__pycache__') for part in Path(relative).parts)
                or path.suffix in ('.so', '.a', '.o') or path.name == 'locomo10.json'):
            continue
        destination = f'benchmarks/reports/language-selection/{run_id}/' + relative
        blob = subprocess.check_output(['git', 'hash-object', '-w', '--', str(path)], cwd=ROOT).decode().strip()
        subprocess.run(['git', 'update-index', '--add', '--cacheinfo', '100644', blob, destination],
                       cwd=ROOT, env=env, check=True)
        count += 1
    tree = subprocess.check_output(['git', 'write-tree'], cwd=ROOT, env=env).decode().strip()
    parent = git('rev-parse', 'HEAD').decode().strip()
    message = f'research: preserve language experiment {run_id} evidence\n'
    commit = subprocess.check_output(['git', 'commit-tree', tree, '-p', parent],
                                    cwd=ROOT, env=env, input=message.encode()).decode().strip()
    subprocess.run(['git', 'push', 'origin', commit + ':refs/heads/' + branch], cwd=ROOT, env=env, check=True)
    exp.save(output.parent / 'preservation.json', {'branch': branch, 'commit': commit, 'files': count})
    print(exp.dump({'evidence_branch': branch, 'evidence_commit': commit, 'files': count}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['run', 'preserve'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['preflight', 'formal'], default='formal')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command == 'preserve':
        preserve(output)
        return
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        assert os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
        assert os.environ.get('GITHUB_REPOSITORY') == 'Afloat16/AI-Memory-Book'
        if args.phase == 'formal':
            assert os.environ.get('GITHUB_REF') == 'refs/heads/validation/language-selection-formal-1'
    assert os.environ.get('PYTHONHASHSEED') == '0', 'Start host with PYTHONHASHSEED=0'
    env = os.environ.copy()
    env.update(PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1', MEMORY_BOOK_BUILD_NATIVE='1',
        CC='gcc', LDSHARED='gcc -shared', CARGO_TARGET_DIR=str(output.parent / 'cargo-target'),
        TIKTOKEN_CACHE_DIR=str(output.parent / 'token-cache'),
        OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    os.environ.update({key: env[key] for key in ('TIKTOKEN_CACHE_DIR', 'PYTHONDONTWRITEBYTECODE')})
    manifest = preparation(output, env, args.phase)
    measure(output, manifest, env, args.phase)


if __name__ == '__main__':
    main()
