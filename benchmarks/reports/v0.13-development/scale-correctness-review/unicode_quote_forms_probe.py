"""Frozen review: non-ASCII quotation forms must not gain new reporting-frame authority."""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--source', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
root = a.runtime.resolve()
sys.path.insert(0, str(root / 'src'))
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME
assert BACKEND_NAME == 'python'
sha = lambda b: hashlib.sha256(b).hexdigest()
files = {str(f.relative_to(root)): sha(f.read_bytes()) for f in sorted((root / 'src/memory_book').glob('*.py'))}
assert all(sha(subprocess.check_output(['git', 'show', a.source + ':' + name], cwd=root)) == value
           for name, value in files.items())
rows = []
for left, right in [('＂', '＂'), ('〝', '〞')]:
    old = 'Approved configuration: access_limit=30. ' + 'access_limit record. ' * 12
    new = 'The log quotes another task: ' + left + 'First note. 当前配置: access_limit=12。' + right
    def record(sid, text, newer=False):
        return {'project': 'engine', 'task_id': 'configuration', 'session_id': sid,
                'created_at': '2026-06-01T00:00:00Z' if newer else '2026-01-01T00:00:00Z',
                'messages': [{'role': 'assistant', 'content': text}]}
    sources = [record('old', old), record('new', new, True)]
    request = {'query': 'current access_limit', 'project': 'engine', 'limit': 1, 'use_cache': False}
    with MemoryBook(':memory:', segmentation='turn') as book:
        [book.ingest(s) for s in sources]
        response = book.recall(**request)
    first = response['results'][0]['source_refs'][0]['session_id']
    row = {'marks': [left, right], 'sources': sources, 'request': request, 'response': response,
           'expected_first': 'old', 'first': first, 'passed': first == 'old'}
    rows.append(row)
    with (a.output / 'raw.jsonl').open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
r = {'source': a.source, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
     'runtime_files': files, 'responses': len(rows), 'passed': sum(x['passed'] for x in rows),
     'raw_sha256': sha((a.output / 'raw.jsonl').read_bytes()), 'probe_sha256': sha(Path(__file__).read_bytes())}
(a.output / 'receipt.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps({k: v for k, v in r.items() if k != 'runtime_files'}))
