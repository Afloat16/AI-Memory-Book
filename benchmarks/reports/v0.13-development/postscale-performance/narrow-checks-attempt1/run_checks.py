"""Narrow source-bound regression execution; not a latency benchmark."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/workspace/scratch/428c08bef2bc/v013-performance')
OUTPUT = Path(__file__).resolve().parent
PYTHON = '/workspace/scratch/428c08bef2bc/.venv/bin/python'
COMMIT = 'f3b7e3133dcd05f080f84fed5ff21d57d67c27be'
MODULES = ['test_sparse_project_membership', 'test_scoped_query_batching',
           'test_directory_search', 'test_directory_snapshot', 'test_core',
           'test_semantic', 'test_token_budget', 'test_current_turn_recall',
           'test_current_token_recall']

def utc():
    return datetime.now(timezone.utc).isoformat()

def binding():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True)
    if head != COMMIT or dirty:
        raise RuntimeError('Candidate HEAD or tracked bytes differ from the frozen source')
    paths = sorted([*ROOT.joinpath('src/memory_book').glob('*.py'),
                    *ROOT.joinpath('src/memory_book').glob('*.c'),
                    *ROOT.joinpath('src/memory_book').glob('*.h'),
                    *[ROOT / 'tests' / (name + '.py') for name in MODULES]])
    return {'commit': head, 'tracked_dirty': dirty,
            'files_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}

env = dict(os.environ, CC='gcc', MEMORY_BOOK_BUILD_NATIVE='1', PYTHONDONTWRITEBYTECODE='1',
           PYTHONPATH=str(ROOT / 'src') + os.pathsep + str(ROOT),
           TIKTOKEN_CACHE_DIR='/workspace/scratch/428c08bef2bc/tokenizer-cache')
report = {'schema': 'v013-postscale-performance-narrow-checks-v1', 'status': 'running',
          'purpose': 'Regression checks only; elapsed times are not performance acceptance measurements.',
          'source_before': binding(), 'started_at': utc(), 'modules': MODULES, 'steps': []}

def save():
    (OUTPUT / 'receipt.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

def run(name, command, backend):
    step = {'name': name, 'command': command, 'cwd': str(ROOT), 'backend': backend,
            'started_at': utc(), 'stdout': name + '.stdout.log', 'stderr': name + '.stderr.log'}
    report['steps'].append(step)
    save()
    started = time.perf_counter()
    with (OUTPUT / step['stdout']).open('xb') as out, (OUTPUT / step['stderr']).open('xb') as err:
        try:
            result = subprocess.run(command, cwd=ROOT, env=dict(env, MEMORY_BOOK_TEXT_BACKEND=backend),
                                    stdout=out, stderr=err, timeout=600)
            step['exit_status'] = result.returncode
        except subprocess.TimeoutExpired:
            step.update(exit_status=None, timed_out=True)
    step.update(finished_at=utc(), elapsed_seconds=time.perf_counter() - started)
    for kind in ('stdout', 'stderr'):
        raw = (OUTPUT / step[kind]).read_bytes()
        step[kind + '_bytes'] = len(raw)
        step[kind + '_sha256'] = hashlib.sha256(raw).hexdigest()
    save()
    print(name, step.get('exit_status'), flush=True)
    return step.get('exit_status') == 0

save()
try:
    successful = run('native-build', [PYTHON, 'setup.py', 'build_ext', '--inplace', '--force'], 'native')
    identity = '''import hashlib,json,os,sqlite3,sys
from pathlib import Path
import memory_book
from memory_book import _text_backend
root=Path.cwd().resolve()
actual=Path(memory_book.__file__).resolve()
assert actual.parent==root/'src/memory_book'
assert _text_backend.BACKEND_NAME==os.environ['MEMORY_BOOK_TEXT_BACKEND']
native=Path(_text_backend.NATIVE.__file__).resolve() if _text_backend.NATIVE else None
assert native is None or native.parent==root/'src/memory_book'
print(json.dumps(dict(package_file=str(actual),backend=_text_backend.BACKEND_NAME,
 native_file=str(native) if native else None,
 native_sha256=hashlib.sha256(native.read_bytes()).hexdigest() if native else None,
 python=sys.version,sqlite=sqlite3.sqlite_version),indent=2))
'''
    tests = ('import json,sys,unittest; from pathlib import Path; '
             'sys.path.insert(0,str(Path.cwd()/"tests")); '
             f'modules={MODULES!r}; '
             'suite=unittest.defaultTestLoader.loadTestsFromNames(modules); '
             'r=unittest.TextTestRunner(verbosity=2).run(suite); '
             'print(json.dumps(dict(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),'
             'skipped=r.skipped,expected_failures=len(r.expectedFailures),'
             'unexpected_successes=len(r.unexpectedSuccesses),successful=r.wasSuccessful()))); '
             'sys.exit(0 if r.wasSuccessful() else 1)')
    if successful:
        for backend in ('native', 'python'):
            identified = run(backend + '-identity', [PYTHON, '-c', identity], backend)
            checked = run(backend + '-tests', [PYTHON, '-c', tests], backend) if identified else False
            successful = identified and checked and successful
    report['source_after'] = binding()
    if report['source_before'] != report['source_after']:
        raise RuntimeError('Source or tests changed while checks ran')
    report['status'] = 'passed' if successful else 'failed'
except BaseException as error:
    import traceback
    report.update(status='failed', error={'type': type(error).__name__, 'message': str(error),
                                         'traceback': traceback.format_exc()})
finally:
    report['finished_at'] = utc()
    save()
print(json.dumps({'status': report['status'], 'receipt': str(OUTPUT / 'receipt.json')}))
sys.exit(0 if report['status'] == 'passed' else 1)
