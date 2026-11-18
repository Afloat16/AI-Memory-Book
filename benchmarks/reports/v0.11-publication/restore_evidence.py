"""Restore the original publication evidence from bounded, hash-checked parts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ordinary_path(root, name):
    value = PurePosixPath(name)
    require(bool(name) and not value.is_absolute() and '..' not in value.parts
            and '\\' not in name and str(value) == name, 'Unsafe relative name: ' + name)
    path = root
    for part in value.parts:
        path = path / part
        require(not path.is_symlink(), 'Linked evidence path: ' + name)
    return path


def restore(output):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.is_dir(),
            'Choose a new output directory with an existing parent')
    manifest = json.loads((ROOT / 'evidence-manifest.json').read_text(encoding='utf-8'))
    proof = json.loads((ROOT / 'audit.json').read_text(encoding='utf-8'))
    archive = manifest['archive']
    transport = archive['transport']
    require(transport['format'] == 'ordered-fixed-byte-parts-v1'
            and transport['max_part_bytes'] == 262144, 'Unknown parts protocol')
    parts = transport['parts']
    require(parts and len({item['path'] for item in parts}) == len(parts), 'Missing or duplicate parts')
    require(all(manifest['files'].get(name) == record for name, record in proof['staged_evidence'].items()),
            'Manifest differs from the original audit inputs')
    with tempfile.TemporaryDirectory(prefix='v011-evidence-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        bundle = temporary / 'original-evidence.tar.xz'
        digest, size = hashlib.sha256(), 0
        with bundle.open('xb') as destination:
            for index, item in enumerate(parts):
                require(item['path'] == f'evidence-parts/part-{index:04d}.bin', 'Part order differs')
                path = ordinary_path(ROOT, item['path'])
                data = path.read_bytes()
                require(0 < len(data) <= 262144 and (index == len(parts) - 1 or len(data) == 262144),
                        'Unexpected part boundary')
                require(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'],
                        'Part size or hash mismatch: ' + item['path'])
                destination.write(data)
                digest.update(data)
                size += len(data)
        require(size == archive['bytes'] and digest.hexdigest() == archive['sha256'],
                'Original archive size or SHA-256 differs')
        staging = temporary / 'restored'
        staging.mkdir()
        with tarfile.open(bundle, 'r:xz') as source:
            members = source.getmembers()
            require(len(members) == len(manifest['files'])
                    and {member.name for member in members} == set(manifest['files']),
                    'Restored archive inventory differs')
            for member in members:
                require(member.isfile(), 'Only ordinary evidence files may be restored')
                expected = manifest['files'][member.name]
                require(member.size == expected['bytes'], 'Restored file size differs')
                data = source.extractfile(member).read()
                require(hashlib.sha256(data).hexdigest() == expected['sha256'],
                        'Restored file hash differs: ' + member.name)
                path = ordinary_path(staging, member.name)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as destination:
                    destination.write(data)
        staging.rename(output)
    return {'status': 'verified', 'output': str(output), 'parts': len(parts),
            'archive_bytes': size, 'archive_sha256': digest.hexdigest(),
            'restored_files': len(members), 'original_audit_inputs': len(proof['staged_evidence'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    print(json.dumps(restore(parser.parse_args().output), sort_keys=True))
