"""Verify version-only runtime changes from existing Git objects; no recall."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BEFORE = '971504257ab03082a0557c638297d482c18f3876'
AFTER = '9ea37a7c72aec21b6f106d9631d72d72199e283b'
EVALUATORS = [
    'benchmarks/v013_accuracy_cases.py', 'benchmarks/v013_accuracy_eval.py',
    'benchmarks/v012_revision_cases.py', 'benchmarks/v012_revision_eval.py',
    'benchmarks/experiments/v013-accuracy-protocol.json',
    'benchmarks/experiments/v012-revision-evaluation-protocol.json',
    'scripts/validate_v011_revision_recovery.py',
]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def inventory(commit):
    result = {}
    raw = git('ls-tree', '-r', '--full-tree', '-z', commit, '--', 'src', 'setup.py', 'pyproject.toml', *EVALUATORS)
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        meta, name = entry.split(b'\t', 1)
        mode, kind, blob = meta.decode().split()
        assert kind == 'blob'
        path = name.decode()
        content = git('cat-file', 'blob', blob)
        result[path] = {'mode': mode, 'blob': blob, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    return result


def verify():
    before, after = inventory(BEFORE), inventory(AFTER)
    assert before.keys() == after.keys()
    changed = [name for name in before if before[name] != after[name]]
    assert set(changed) == {'src/memory_book/__init__.py', 'pyproject.toml'}
    substitutions = {'src/memory_book/__init__.py': (b'__version__ = "0.12.0"', b'__version__ = "0.13.0"'),
                     'pyproject.toml': (b'version = "0.12.0"', b'version = "0.13.0"')}
    for name, (old, new) in substitutions.items():
        left = git('show', BEFORE + ':' + name)
        right = git('show', AFTER + ':' + name)
        assert left.count(old) == 1 and left.replace(old, new, 1) == right
        assert before[name]['mode'] == after[name]['mode']
    return {'status': 'verified', 'measured_source': BEFORE, 'formal_scale_source': AFTER,
            'scope': 'All tracked src files, setup.py, pyproject.toml, and all seven evaluator/dataset/protocol files used by the preserved 62/38-case evaluation.',
            'files': len(before), 'byte_identical_files': len(before) - 2, 'version_only_files': changed,
            'versions': {'measured': '0.12.0', 'formal': '0.13.0'},
            'before': before, 'after': after,
            'interpretation': 'The measured retrieval algorithm, native C sources, MCP implementation, fixtures and scorer bytes are identical to the formal scale source. Only package version literals changed.',
            'limits': 'This is source-equivalence evidence, not a new execution on the formal source. Existing raw responses remain bound to their recorded measured source. Packaging and public-version behavior are covered by separately reported exact-source CI, not by this receipt.'}


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
