"""Run the unchanged saved suffix probe on frozen source snapshots."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path('/workspace/scratch/b92339f83b53/AI-Memory-Book')
BASELINE = Path('/workspace/scratch/b92339f83b53/AI-Memory-Book-baseline')
OUT = ROOT / 'benchmarks/reports/v0.12-development/resumed-suffix-scope-review-attempt2'
PROBE = ROOT / 'benchmarks/reports/v0.12-development/resumed-suffix-scope-review-attempt1/probe.py'
PROBE_SHA = '73f941662352da8a11e78499cdec1cfec55ebef67f2fedbbb34f68ee04d34389'
COMMITS = {'baseline': '78cc906d81818a16884de7de2e613e5a56346f93',
           'candidate': '021a384567db5aa64fde155f090d2eb399f55c03'}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def snapshot(root, expected, backend):
    git = lambda *a: subprocess.check_output(['git', '-C', str(root), *a])
    assert git('rev-parse', 'HEAD').decode().strip() == expected
    names = git('ls-tree', '-r', '--name-only', expected, 'src/memory_book').decode().splitlines()
    files = {name: sha((root / name).read_bytes()) for name in names}
    assert files == {name: sha(git('show', expected + ':' + name)) for name in names}
    env = {**os.environ, 'PYTHONPATH': str(root / 'src'),
           'PYTHONDONTWRITEBYTECODE': '1', 'MEMORY_BOOK_TEXT_BACKEND': backend}
    inspect = subprocess.check_output([sys.executable, '-c',
        "import json,sys,memory_book;from memory_book._text_backend import BACKEND_NAME;"
        "n=sys.modules.get('memory_book._native');"
        "print(json.dumps({'package':memory_book.__file__,'backend':BACKEND_NAME,"
        "'binary':n.__file__ if n else None,'python':sys.version,'executable':sys.executable}))"],
        env=env, cwd=root).decode()
    loaded = json.loads(inspect)
    assert Path(loaded['package']).resolve() == root / 'src/memory_book/__init__.py'
    assert loaded['backend'] == backend
    if backend == 'native':
        binary = Path(loaded['binary']).resolve()
        assert binary.parent == root / 'src/memory_book'
        loaded['native_sha256'] = sha(binary.read_bytes())
    else:
        assert loaded['binary'] is None
    return {'commit': expected, 'files': files, **loaded}

def main():
    OUT.mkdir(exist_ok=False)
    assert sha(PROBE.read_bytes()) == PROBE_SHA
    report = {'status': 'started', 'kind': 'unchanged_frozen_suffix_probe_replay',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'probe_path': str(PROBE), 'probe_sha256': PROBE_SHA,
              'driver_sha256': sha(Path(__file__).read_bytes()),
              'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
              'arms': [], 'scope': 'Development counterexample review; native runs are separately reported consistency checks.'}
    write(OUT / 'execution.json', report)
    try:
        for backend in ('python', 'native'):
            for arm, source in (('baseline', BASELINE), ('candidate', ROOT)):
                name = arm + '-' + backend
                before = snapshot(source, COMMITS[arm], backend)
                command = [sys.executable, str(PROBE), '--source', str(source), '--output', str(OUT / name)]
                env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                       'MEMORY_BOOK_TEXT_BACKEND': backend}
                entry = {'arm': name, 'command': command, 'source_before': before,
                         'environment': {key: env[key] for key in ('PYTHONDONTWRITEBYTECODE', 'MEMORY_BOOK_TEXT_BACKEND')}}
                report['arms'].append(entry)
                write(OUT / 'execution.json', report)
                with (OUT / (name + '.log')).open('x') as log:
                    process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                entry['exit_code'] = process.returncode
                entry['source_after'] = snapshot(source, COMMITS[arm], backend)
                entry['unchanged'] = entry['source_before'] == entry['source_after']
                assert process.returncode == 0 and entry['unchanged']
                assert sha(PROBE.read_bytes()) == PROBE_SHA
                write(OUT / 'execution.json', report)
        report['status'] = 'completed'
    except BaseException as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        write(OUT / 'execution.json', report)
    print(json.dumps({'status': report['status'], 'arms': [entry['arm'] for entry in report['arms']]}))

if __name__ == '__main__':
    main()
