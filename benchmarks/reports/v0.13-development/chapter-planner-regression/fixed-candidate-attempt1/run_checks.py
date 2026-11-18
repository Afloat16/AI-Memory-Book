"""Record the original chapter-planner failure and the bounded corrective gate."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path('/workspace/scratch/428c08bef2bc')
ROOT = BASE / 'v013-performance'
PYTHON = BASE / '.venv/bin/python'
spec = importlib.util.spec_from_file_location('legacy_source_identity', BASE / 'v013-accuracy/scripts/validate_v011_revision_recovery.py')
identity_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity_module)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--commit', required=True)
parser.add_argument('--mode', choices=('original-failure', 'fixed-modules'), required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
if any(output.iterdir()):
    raise ValueError('Evidence directory must be empty')

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

tests = ['test_round5_covering_index', 'test_sparse_project_membership']
selection = (['test_round5_covering_index.RecallCoveringIndexTests.test_selective_unbounded_chapter_and_session_routes_keep_index_choice']
             if args.mode == 'original-failure' else tests)
test_blobs = {}
for module in tests:
    path = 'tests/' + module + '.py'
    raw = (ROOT / path).read_bytes()
    expected = subprocess.check_output(['git', 'show', '4e4a8eb2fefe31a136033a37fcc844c36162ffae:' + path], cwd=ROOT)
    if raw != expected:
        raise ValueError('Original test bytes changed: ' + path)
    test_blobs[path] = sha(raw)
report = {'schema': 'v013-chapter-planner-regression-v1', 'status': 'running',
          'mode': args.mode, 'source_commit': args.commit, 'started_at': utc(),
          'source_before': identity_module.source_identity(ROOT, args.commit),
          'tests_bound_to_commit': '4e4a8eb2fefe31a136033a37fcc844c36162ffae',
          'test_files_sha256': test_blobs, 'test_selection': selection,
          'runner_sha256': sha(Path(__file__).read_bytes()), 'steps': [],
          'scope': 'Specific CI regression and unchanged module contracts, not performance acceptance.'}
env = dict(os.environ, CC='gcc', MEMORY_BOOK_BUILD_NATIVE='1', PYTHONDONTWRITEBYTECODE='1',
           PYTHONPATH=str(ROOT / 'src') + os.pathsep + str(ROOT),
           TIKTOKEN_CACHE_DIR=str(BASE / 'tokenizer-cache'))

def save():
    (output / 'receipt.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

def run(name, command, backend):
    step = {'name': name, 'command': command, 'cwd': str(ROOT), 'backend': backend,
            'started_at': utc(), 'stdout': name + '.stdout.log', 'stderr': name + '.stderr.log'}
    report['steps'].append(step)
    save()
    with (output / step['stdout']).open('xb') as stdout, (output / step['stderr']).open('xb') as stderr:
        try:
            result = subprocess.run(command, cwd=ROOT, env=dict(env, MEMORY_BOOK_TEXT_BACKEND=backend),
                                    stdout=stdout, stderr=stderr, timeout=600)
            step.update(returncode=result.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            step.update(returncode=None, timed_out=True)
    step['finished_at'] = utc()
    for key in ('stdout', 'stderr'):
        raw = (output / step[key]).read_bytes()
        step[key + '_bytes'] = len(raw)
        step[key + '_sha256'] = sha(raw)
    save()
    print(json.dumps({'step': name, 'returncode': step['returncode']}), flush=True)
    return step['returncode']

save()
try:
    if run('native-build', [str(PYTHON), 'setup.py', 'build_ext', '--inplace', '--force'], 'native') != 0:
        raise RuntimeError('Native build failed')
    report['source_after_build'] = identity_module.source_identity(ROOT, args.commit)
    if report['source_before']['files'] != report['source_after_build']['files']:
        raise RuntimeError('Runtime source changed during build')
    code = '''import hashlib,json,os,sqlite3,sys,unittest
from pathlib import Path
import memory_book
from memory_book import store,_text_backend
root=Path.cwd().resolve()
assert Path(memory_book.__file__).resolve().parent==root/'src/memory_book'
assert Path(store.__file__).resolve()==root/'src/memory_book/store.py'
assert _text_backend.BACKEND_NAME==os.environ['MEMORY_BOOK_TEXT_BACKEND']
native=Path(_text_backend.NATIVE.__file__).resolve() if _text_backend.NATIVE else None
assert native is None or native.parent==root/'src/memory_book'
proof=dict(package=str(Path(memory_book.__file__).resolve()),backend=_text_backend.BACKEND_NAME,
 native_file=str(native) if native else None,native_sha256=hashlib.sha256(native.read_bytes()).hexdigest() if native else None,
 recall_version=store.RECALL_VERSION,python=sys.version,sqlite=sqlite3.sqlite_version)
print(json.dumps(dict(imported=proof)),flush=True)
sys.path.insert(0,str(root/'tests'))
suite=unittest.defaultTestLoader.loadTestsFromNames(SELECTION)
r=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps(dict(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),
 skipped=r.skipped,expected_failures=len(r.expectedFailures),unexpected_successes=len(r.unexpectedSuccesses),successful=r.wasSuccessful())),flush=True)
sys.exit(0 if r.wasSuccessful() else 1)
'''.replace('SELECTION', repr(selection))
    results = {}
    for backend in ('native', 'python'):
        returncode = run(backend + '-tests', [str(PYTHON), '-c', code], backend)
        raw = (output / (backend + '-tests.stdout.log')).read_text().splitlines()
        value = json.loads(raw[-1]) if raw else None
        results[backend] = {'returncode': returncode, 'summary': value}
    report['results'] = results
    report['source_after_tests'] = identity_module.source_identity(ROOT, args.commit)
    if report['source_after_tests'] != report['source_after_build']:
        raise RuntimeError('Runtime or extension changed during tests')
    if args.mode == 'original-failure':
        reproduced = all(item['returncode'] == 1 and item['summary']['tests_run'] == 1
                         and item['summary']['failures'] == 1 and item['summary']['errors'] == 0
                         for item in results.values())
        report['status'] = 'original_failure_reproduced' if reproduced else 'unexpected_result'
    else:
        report['status'] = 'passed' if all(item['returncode'] == 0 and item['summary']['successful']
                                          for item in results.values()) else 'failed'
except BaseException as error:
    import traceback
    report.update(status='execution_error', error={'type': type(error).__name__, 'message': str(error),
                                                 'traceback': traceback.format_exc()})
finally:
    report['finished_at'] = utc()
    save()
print(json.dumps({'status': report['status'], 'output': str(output)}))
sys.exit(0 if report['status'] in ('original_failure_reproduced', 'passed') else 1)
