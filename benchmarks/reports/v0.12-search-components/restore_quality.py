"""Losslessly restore the frozen quality attempt without changing evaluator inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent / 'quality-attempt1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(root, name):
    relative = PurePosixPath(name)
    require(bool(name) and not relative.is_absolute() and '..' not in relative.parts
            and '\\' not in name and str(relative) == name, 'Unsafe evidence path')
    path = root
    for part in relative.parts:
        path = path / part
        require(not path.is_symlink(), 'Linked evidence file')
    return path


def verify_bytes(data, expected, label):
    require(len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'],
            'Original evidence hash or size differs: ' + label)
    return data


def restore(output):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.is_dir(), 'Use a new destination with an existing parent')
    manifest = json.loads((ROOT / 'archive-manifest.json').read_text(encoding='utf-8'))
    require(manifest['format'] == 'v012-search-components-lossless-parts-v1', 'Unknown archive format')
    original = manifest['original_files']
    proof_bytes = verify_bytes((ROOT / 'audit.json').read_bytes(), original['audit.json'], 'audit.json')
    proof = json.loads(proof_bytes)
    require(set(original) == set(proof['files']) | {'audit.json'} and all(
        original[name]['sha256'] == digest for name, digest in proof['files'].items()),
        'Original input inventory differs from the frozen audit proof')
    retained, archived = manifest['retained_files'], manifest['archived_files']
    require(len(retained) + len(archived) == len(original) and not set(retained) & set(archived)
            and set(retained) | set(archived) == set(original), 'Archive input partition differs')
    archive = manifest['archive']
    require(archive['max_part_bytes'] == 262144 and archive['parts'], 'Unknown part boundary')
    with tempfile.TemporaryDirectory(prefix='v012-quality-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        bundle, staging = temporary / 'inputs.tar.xz', temporary / 'restored'
        staging.mkdir()
        digest, size = hashlib.sha256(), 0
        with bundle.open('xb') as stream:
            for index, part in enumerate(archive['parts']):
                require(part['path'] == f'raw-evidence-parts/part-{index:04d}.bin', 'Part order differs')
                data = verify_bytes(safe_path(ROOT, part['path']).read_bytes(), part, part['path'])
                require(0 < len(data) <= 262144
                        and (index == len(archive['parts']) - 1 or len(data) == 262144), 'Invalid part size')
                stream.write(data)
                digest.update(data)
                size += len(data)
        require(size == archive['bytes'] and digest.hexdigest() == archive['sha256'], 'Archive digest differs')
        with tarfile.open(bundle, 'r:xz') as source:
            members = source.getmembers()
            require(len(members) == len(archived) and {m.name for m in members} == set(archived),
                    'Archive member inventory differs')
            for member in members:
                require(member.isfile() and member.size == original[member.name]['bytes'], 'Invalid archive member')
                data = verify_bytes(source.extractfile(member).read(), original[member.name], member.name)
                path = safe_path(staging, member.name)
                require(path.parent == staging, 'Expected flat original evaluator output')
                with path.open('xb') as stream:
                    stream.write(data)
        for name in retained:
            data = verify_bytes(safe_path(ROOT, name).read_bytes(), original[name], name)
            with safe_path(staging, name).open('xb') as stream:
                stream.write(data)
        staging.rename(output)
    return {'status': 'verified', 'restored_files': len(original), 'audited_input_files': len(proof['files']),
            'parts': len(archive['parts']), 'archive_sha256': digest.hexdigest(), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    print(json.dumps(restore(parser.parse_args().output), sort_keys=True))
