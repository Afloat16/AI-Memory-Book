"""Two frozen review variants; not part of either existing benchmark gold."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runtime', type=Path, required=True)
    ap.add_argument('--source-commit', required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = args.runtime.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol_path = Path(__file__).with_name('protocol.json')
    protocol = json.loads(protocol_path.read_text())
    source_files = {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted((root / 'src/memory_book').glob('*.py'))}
    for name, digest in source_files.items():
        expected = subprocess.check_output(['git', 'show', args.source_commit + ':' + name], cwd=root)
        assert sha(expected) == digest, name
    head_before = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    sys.path.insert(0, str(root / 'src'))
    from memory_book import MemoryBook
    from memory_book._text_backend import BACKEND_NAME
    import memory_book.store as store
    assert BACKEND_NAME == os.environ['MEMORY_BOOK_TEXT_BACKEND']
    rows = []
    for case in protocol['cases']:
        with MemoryBook(':memory:', segmentation='turn', cache_size=0) as book:
            ingestions = [book.ingest(source) for source in case['sources']]
            response = book.recall(**case['request'], use_cache=False)
            first = response['results'][0]['source_refs'][0]['session_id'] if response['results'] else None
            promotions = response.get('temporal', {}).get('nondecision_priority', {}).get('promotions', 0)
            row = {'id': case['id'], 'sources': case['sources'], 'request': case['request'], 'ingestions': ingestions, 'response': response,
                   'observed': {'first_session': first, 'nondecision_promotions': promotions},
                   'expected': case['expected'], 'passed': first == case['expected']['first_session'] and promotions == 0}
            rows.append(row)
            with (out / 'raw.jsonl').open('a', encoding='utf8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush(); os.fsync(stream.fileno())
    source_after = {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted((root / 'src/memory_book').glob('*.py'))}
    assert source_files == source_after
    head_after = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    assert head_before == head_after
    native = []
    if BACKEND_NAME == 'native':
        from memory_book import _native
        path = Path(_native.__file__)
        native.append({'name': path.name, 'sha256': sha(path.read_bytes())})
    receipt = {'status': 'completed', 'source_commit': args.source_commit, 'worktree_head': head_before, 'source_files_sha256': source_files,
               'recall_version': store.RECALL_VERSION, 'backend': BACKEND_NAME, 'native': native, 'protocol_sha256': sha(protocol_path.read_bytes()),
               'probe_sha256': sha(Path(__file__).read_bytes()), 'raw_sha256': sha((out / 'raw.jsonl').read_bytes()), 'responses': len(rows),
               'passed': sum(r['passed'] for r in rows), 'failed': sum(not r['passed'] for r in rows)}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'source_files_sha256'}))


if __name__ == '__main__':
    main()
