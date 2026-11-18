"""Acquire the exact public assets listed in one saved GitHub release response."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import urllib.request


def utc():
    return datetime.now(timezone.utc).isoformat()


def download(item, target):
    name = item['name']
    if Path(name).name != name or name in {'.', '..'}:
        raise ValueError('Unsafe asset name')
    path = target / name
    if path.exists():
        raise FileExistsError(path)
    request = urllib.request.Request(item['browser_download_url'], headers={'User-Agent': 'AI-Memory-Book-release-evidence'})
    started = utc()
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    if len(raw) != item['size']:
        raise ValueError('Asset size differs: ' + name)
    digest = hashlib.sha256(raw).hexdigest()
    if item.get('digest') and item['digest'] != 'sha256:' + digest:
        raise ValueError('GitHub asset digest differs: ' + name)
    with path.open('xb') as handle:
        handle.write(raw)
    return {'name': name, 'asset_id': item['id'], 'bytes': len(raw), 'sha256': digest,
            'source_url': item['browser_download_url'], 'started_at_utc': started,
            'completed_at_utc': utc(), 'method': 'HTTPS download of original public browser_download_url; redirects followed'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--release-id', type=int, required=True)
    parser.add_argument('--release-json', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    args = parser.parse_args()
    release = json.loads(args.release_json.read_text())
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        raise ValueError('Expected an explicit release version')
    if not re.fullmatch(r'[0-9a-f]{40}', args.source_commit) or args.release_id <= 0:
        raise ValueError('Expected an explicit full source commit and positive release ID')
    if (release['tag_name'] != 'v' + args.version
            or release['target_commitish'] != args.source_commit
            or release['id'] != args.release_id
            or release['draft'] or release['prerelease']):
        raise ValueError('Unexpected publication identity or channel')
    assets = release['assets']
    if len(assets) != 67 or len({x['name'] for x in assets}) != 67:
        raise ValueError('Expected 67 distinct public release assets')
    if args.record.exists():
        raise FileExistsError(args.record)
    args.target.mkdir(parents=True, exist_ok=True)
    records, failures = [], []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(download, item, args.target): item for item in assets}
        for future in as_completed(futures):
            item = futures[future]
            try:
                records.append(future.result())
            except Exception as exc:
                failures.append({'name': item['name'], 'type': type(exc).__name__,
                                 'message': str(exc)[:1000], 'at_utc': utc()})
    result = {'status': 'failed' if failures else 'passed', 'release_id': release['id'],
              'tag': release['tag_name'], 'assets': sorted(records, key=lambda x: x['name']),
              'failures': failures, 'completed_at_utc': utc(),
              'scope': 'Independent public-URL downloads; no copies from workflow archives'}
    args.record.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'assets': len(records), 'failures': len(failures)}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
