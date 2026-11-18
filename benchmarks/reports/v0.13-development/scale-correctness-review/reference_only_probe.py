"""Frozen authored controls for whole-source no-change reports; not a holdout."""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--source', required=True)
p.add_argument('--backend', choices=['python', 'native'], required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
root = a.runtime.resolve()
sys.path.insert(0, str(root / 'src'))
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME
assert BACKEND_NAME == a.backend
sha = lambda b: hashlib.sha256(b).hexdigest()
files = {str(f.relative_to(root)): sha(f.read_bytes()) for f in sorted((root / 'src/memory_book').glob('*.py'))}
assert all(sha(subprocess.check_output(['git', 'show', a.source + ':' + name], cwd=root)) == value
           for name, value in files.items())
safe = 'We inspected task_limit logs. No new value was selected.'
cases = [
    ('inspection', 'We inspected the logs for task_limit. No new value was selected.', None, 'decision'),
    ('check', 'We checked task_limit during the review. The configuration remains unchanged.', None, 'decision'),
    ('examination', 'The review examined task_limit records. This discussion proposes no approved parameter change.', None, 'decision'),
    ('navigation_title', safe, 'Engine inspection 12', 'decision'),
    ('unrelated_object', 'We inspected another_limit logs. No new value was selected.', None, 'review'),
    ('negated_report', 'We did not inspect task_limit logs. No new value was selected.', None, 'review'),
    ('revocation_english', safe + ' The previous value has been revoked.', None, 'review'),
    ('revocation_chinese', safe + ' 旧值已被撤销。', None, 'review'),
    ('withdrawal_english', safe + ' Do not use the previous setting.', None, 'review'),
    ('withdrawal_chinese', safe + ' 旧配置不再适用。', None, 'review'),
    ('subject_scope', 'Staging staff inspected task_limit logs. No new value was selected.', None, 'review'),
    ('relation_scope', 'We inspected task_limit in staging_only. No new value was selected.', None, 'review'),
    ('quoted_ascii', 'Earlier notes said "' + safe + '"', None, 'review'),
    ('quoted_unicode', 'Earlier notes said “' + safe + '”', None, 'review'),
    ('user_withdrawal', safe, 'Do not use the previous setting.', 'review'),
    ('user_scope', safe, 'Staging inspection 12', 'review'),
    ('user_binding', safe, 'Production task_limit=99.', 'review'),
    ('unknown_assistant_claim', safe + ' A separate safety boundary must pass.', None, 'review'),
]
rows = []
for case, text, user, expected in cases:
    def record(sid, messages, newer=False):
        return {'project': 'engine', 'task_id': 'configuration', 'task_title': 'Engine parameter configuration',
                'session_id': sid, 'created_at': '2026-06-01T00:00:00Z' if newer else '2026-01-01T00:00:00Z',
                'messages': messages}
    messages = ([{'role': 'user', 'content': user}] if user is not None else [])
    messages.append({'role': 'assistant', 'content': text + ' task_limit records. ' * 12})
    sources = [record('decision', [{'role': 'assistant', 'content': 'Approved configuration: task_limit=12.'}]),
               record('review', messages, True)]
    request = {'query': 'current task_limit', 'project': 'engine', 'limit': 1, 'use_cache': False}
    with MemoryBook(':memory:', segmentation='turn') as book:
        [book.ingest(s) for s in sources]
        response = book.recall(**request)
    first = response['results'][0]['source_refs'][0]['session_id']
    row = {'case': case, 'sources': sources, 'request': request, 'response': response,
           'expected_first': expected, 'first': first, 'passed': first == expected}
    rows.append(row)
    with (a.output / 'raw.jsonl').open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
r = {'source': a.source, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
     'runtime_files': files, 'backend': BACKEND_NAME, 'responses': len(rows),
     'passed': sum(x['passed'] for x in rows), 'failed_cases': [x['case'] for x in rows if not x['passed']],
     'raw_sha256': sha((a.output / 'raw.jsonl').read_bytes()), 'probe_sha256': sha(Path(__file__).read_bytes())}
if BACKEND_NAME == 'native':
    from memory_book import _native
    r['native_sha256'] = sha(Path(_native.__file__).read_bytes())
(a.output / 'receipt.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps({k: v for k, v in r.items() if k != 'runtime_files'}))
