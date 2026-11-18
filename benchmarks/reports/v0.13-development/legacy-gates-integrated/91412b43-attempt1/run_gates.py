"""Execute the unchanged legacy wrapper against the final integrated source."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path('/workspace/scratch/428c08bef2bc')
SOURCE = BASE / 'v013-legacy-candidate'
BASELINE_SOURCE = BASE / 'v013-baseline'
DRIVER = BASE / 'v013-accuracy/scripts/validate_v013_legacy_gates.py'
PYTHON = BASE / '.venv/bin/python'
OUTPUT = Path(__file__).resolve().parent
COMMIT = '91412b438a0da95549cc9a3b85eccb4915359a2d'
BASELINE = '8044e4bafe18e73ea422af5eeb47ef961e65246c'
ENV = dict(os.environ, CC='gcc', MEMORY_BOOK_BUILD_NATIVE='1',
           PYTHONDONTWRITEBYTECODE='1', TIKTOKEN_CACHE_DIR=str(BASE / 'tokenizer-cache'))

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

spec = importlib.util.spec_from_file_location('unchanged_legacy_gate_driver', DRIVER)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
original_driver = subprocess.check_output(['git', 'show',
    '6cf692ba3595cb236c5b9ea050bf0f8730b53c4c:scripts/validate_v013_legacy_gates.py'], cwd=DRIVER.parents[1])
if DRIVER.read_bytes() != original_driver:
    raise ValueError('Legacy wrapper changed from its committed original')
receipt = {'schema': 'v013-integrated-legacy-execution-v1', 'status': 'running',
           'scope': 'Unchanged authored correctness gates; no latency, throughput or external product claim.',
           'started_at': utc(), 'candidate_commit': COMMIT, 'baseline_commit': BASELINE,
           'baseline_reuse': False,
           'baseline_execution_reason': 'The unchanged engineering wrapper replays both arms; no saved-baseline import path was added.',
           'driver': str(DRIVER), 'driver_sha256': sha(DRIVER),
           'executor_sha256': sha(Path(__file__)),
           'source_before_build': driver.source_identity(SOURCE, COMMIT),
           'baseline_before': driver.source_identity(BASELINE_SOURCE, BASELINE),
           'steps': []}

def save():
    (OUTPUT / 'orchestration.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')

def execute(name, command, cwd, timeout):
    step = {'name': name, 'command': [str(x) for x in command], 'cwd': str(cwd),
            'started_at': utc(), 'timeout_seconds': timeout,
            'stdout': name + '.stdout.log', 'stderr': name + '.stderr.log',
            'environment': {k: ENV[k] for k in ('CC', 'MEMORY_BOOK_BUILD_NATIVE',
                                               'PYTHONDONTWRITEBYTECODE', 'TIKTOKEN_CACHE_DIR')}}
    receipt['steps'].append(step)
    save()
    with (OUTPUT / step['stdout']).open('xb') as stdout, (OUTPUT / step['stderr']).open('xb') as stderr:
        try:
            result = subprocess.run(command, cwd=cwd, env=ENV, stdout=stdout, stderr=stderr, timeout=timeout)
            step.update(returncode=result.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            step.update(returncode=None, timed_out=True)
    step['finished_at'] = utc()
    for key in ('stdout', 'stderr'):
        path = OUTPUT / step[key]
        step[key + '_bytes'] = path.stat().st_size
        step[key + '_sha256'] = sha(path)
    save()
    print(json.dumps({'step': name, 'returncode': step['returncode'], 'timed_out': step['timed_out']}), flush=True)
    return step['returncode'] == 0 and not step['timed_out']

save()
try:
    built = execute('native-build', [str(PYTHON), 'setup.py', 'build_ext', '--inplace', '--force'], SOURCE, 120)
    if not built:
        raise RuntimeError('Forced candidate native build failed; original logs retained')
    receipt['source_after_build'] = driver.source_identity(SOURCE, COMMIT)
    if receipt['source_before_build']['files'] != receipt['source_after_build']['files']:
        raise RuntimeError('Source bytes changed during native build')
    saved = []
    for gate in ('engineering', 'short-page', 'directory'):
        target = OUTPUT / (gate + '-attempt1')
        command = [str(PYTHON), str(DRIVER), '--gate', gate, '--candidate-source', str(SOURCE),
                   '--candidate-commit', COMMIT, '--output', str(target)]
        if gate == 'engineering':
            command += ['--baseline-source', str(BASELINE_SOURCE)]
        okay = execute(gate, command, BASE, 1500)
        path = target / 'execution.json'
        execution = json.loads(path.read_bytes()) if path.exists() else None
        saved.append({'gate': gate, 'command_successful': okay,
                      'execution_file': str(path.relative_to(OUTPUT)),
                      'status': execution.get('status') if execution else None,
                      'accepted': execution.get('accepted') if execution else None,
                      'sha256': sha(path) if path.exists() else None})
        receipt['gates'] = saved
        save()
    receipt['source_after_gates'] = driver.source_identity(SOURCE, COMMIT)
    receipt['baseline_after'] = driver.source_identity(BASELINE_SOURCE, BASELINE)
    if receipt['source_after_gates'] != receipt['source_after_build'] or receipt['baseline_after'] != receipt['baseline_before']:
        raise RuntimeError('Runtime or native extension changed while gates ran')
    receipt['status'] = 'passed' if all(row['command_successful'] and row['status'] == 'completed'
                                       and row['accepted'] is True for row in saved) else 'failed'
except BaseException as error:
    import traceback
    receipt.update(status='failed', error={'type': type(error).__name__, 'message': str(error),
                                          'traceback': traceback.format_exc()})
finally:
    receipt['finished_at'] = utc()
    save()
print(json.dumps({'status': receipt['status'], 'output': str(OUTPUT)}))
sys.exit(0 if receipt['status'] == 'passed' else 1)
