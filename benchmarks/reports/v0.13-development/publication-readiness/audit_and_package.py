"""Run the frozen publication auditor and preserve a losslessly verified package.

This helper does not fetch, build, install, publish, or change the repository.
All outputs go to one new caller-selected package directory. Failed attempts
retain their logs and cannot overwrite an earlier package.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
PART_BYTES = 262144


def require(condition, message):
    if not condition:
        raise ValueError(message)


def record(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), 'Evidence must be an ordinary directory')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Linked evidence entry: ' + str(path))
        if path.is_dir():
            continue
        require(path.is_file(), 'Special evidence entry: ' + str(path))
        name = path.relative_to(root).as_posix()
        result[name] = record(path.read_bytes())
    require(result, 'Empty evidence directory')
    return result


def command(argv, cwd, log):
    run = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True)
    raw = run.stdout + run.stderr
    with log.open('xb') as stream:
        stream.write(raw)
    require(run.returncode == 0,
            'Command failed with exit ' + str(run.returncode) + '; retained log: ' + str(log))
    return raw


def audit_command(args, evidence, output):
    return [sys.executable, '-B', args.repo_root / 'scripts/audit_comprehensive_release.py',
            '--evidence', evidence, '--repo-root', args.repo_root,
            '--source-commit', args.source_commit, '--version', args.version,
            '--runtime-sha256', args.runtime_sha256, '--native-baseline', args.native_baseline,
            '--run-id', str(args.run_id), '--run-attempt', str(args.run_attempt), '--output', output]


def execute(args):
    require(not args.output.exists() and not args.output.is_symlink(), 'Choose a fresh package directory')
    require(args.output.parent.is_dir(), 'Package parent must exist')
    require(args.evidence != args.output and args.evidence not in args.output.parents
            and args.output not in args.evidence.parents, 'Evidence and package must be separate trees')
    require(args.temporary_root != args.evidence and args.evidence not in args.temporary_root.parents
            and args.temporary_root != args.output and args.output not in args.temporary_root.parents,
            'Temporary work must be outside the evidence and publication package')
    args.output.mkdir()
    original_command = audit_command(args, args.evidence, args.output / 'audit.json')
    command(original_command, args.repo_root, args.output / 'audit.log')
    proof_bytes = (args.output / 'audit.json').read_bytes()
    proof = json.loads(proof_bytes)
    require(proof['status'] == 'passed' and proof['published'] is True, 'Publication audit did not pass')
    require(proof['source']['commit'] == args.source_commit
            and proof['source']['runtime_sha256'] == args.runtime_sha256
            and proof['workflow']['id'] == args.run_id
            and proof['workflow']['run_attempt'] == args.run_attempt,
            'Audit returned another source or run')
    files = inventory(args.evidence)
    require(all(files.get(name) == value for name, value in proof['staged_evidence'].items()),
            'Staged source bytes changed after the audit')
    parts_dir = args.output / 'evidence-parts'
    parts_dir.mkdir()
    with tempfile.TemporaryDirectory(prefix='publication-package-', dir=args.temporary_root) as temporary:
        temporary = Path(temporary)
        archive = temporary / 'original-evidence.tar.xz'
        with tarfile.open(archive, 'w:xz', format=tarfile.PAX_FORMAT, preset=6) as bundle:
            for name, expected in files.items():
                data = (args.evidence / name).read_bytes()
                require(record(data) == expected, 'Evidence changed before archiving: ' + name)
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                bundle.addfile(info, io.BytesIO(data))
        parts, archive_digest, archive_bytes = [], hashlib.sha256(), 0
        with archive.open('rb') as source:
            while data := source.read(PART_BYTES):
                name = f'evidence-parts/part-{len(parts):04d}.bin'
                with (args.output / name).open('xb') as destination:
                    destination.write(data)
                parts.append({'path': name, **record(data)})
                archive_digest.update(data)
                archive_bytes += len(data)
        manifest = {
            'schema_version': 1,
            'archive': {'path': 'original-evidence.tar.xz', 'bytes': archive_bytes,
                        'sha256': archive_digest.hexdigest(),
                        'transport': {'format': 'ordered-fixed-byte-parts-v1',
                                      'max_part_bytes': PART_BYTES, 'parts': parts}},
            'audit': {'path': 'audit.json', **record(proof_bytes)},
            'archive_files': len(files), 'audit_input_files': len(proof['staged_evidence']),
            'files': files, 'verified_lossless': False}
        write_json(args.output / 'evidence-manifest.json', manifest)
        shutil.copyfile(HERE / 'restore_evidence.py', args.output / 'restore_evidence.py')
        restored = temporary / 'restored-evidence'
        restore_raw = command([sys.executable, '-B', args.output / 'restore_evidence.py',
                               '--output', restored], HERE, args.output / 'restore.log')
        require(inventory(restored) == files, 'Restored file inventory differs')
        restored_audit = temporary / 'restored-audit.json'
        restored_command = audit_command(args, restored, restored_audit)
        command(restored_command, args.repo_root, args.output / 'restored-audit.log')
        restored_bytes = restored_audit.read_bytes()
        require(restored_bytes == proof_bytes, 'Restored audit is not byte-identical to the original proof')
        require(inventory(args.evidence) == files, 'Original evidence changed during packaging')
        verification = {
            'schema_version': 1, 'status': 'passed',
            'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
            'source_commit': args.source_commit, 'run_id': args.run_id, 'run_attempt': args.run_attempt,
            'original_audit_command': list(map(str, original_command)),
            'original_audit_sha256': record(proof_bytes)['sha256'],
            'restored_audit_sha256': record(restored_bytes)['sha256'],
            'restored_audit_byte_identical': True,
            'all_original_and_restored_files_byte_identical': True,
            'restore_result': json.loads(restore_raw),
            'restorer_sha256': record((args.output / 'restore_evidence.py').read_bytes())['sha256'],
            'packaging_script_sha256': record(Path(__file__).read_bytes())['sha256'],
            'scope': 'Original evidence was losslessly compressed and restored; the same frozen offline auditor was rerun. No builds, native execution, installer execution, measurements or publication.'}
        write_json(args.output / 'restoration-verification.json', verification)
        manifest['verified_lossless'] = True
        # This field becomes true only after byte-for-byte restoration and the
        # exact frozen audit both succeed. No earlier attempt is overwritten.
        (args.output / 'evidence-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    write_readme(args, proof, files, parts)
    return {'status': 'passed', 'output': str(args.output), 'source': proof['source'],
            'counts': proof['counts'], 'archive_files': len(files),
            'audit_input_files': len(proof['staged_evidence']), 'parts': len(parts),
            'original_and_restored_audit_sha256': record(proof_bytes)['sha256']}


def write_readme(args, proof, files, parts):
    counts = proof['counts']
    content = f'''# v{args.version} original publication proof

The frozen publication auditor passed against the original release evidence.
The evidence was then archived, restored and audited again with the same
source-bound validators. The original and restored proof JSON bytes match.
No build, native test, installation, quality evaluation or performance
experiment was rerun for this proof.

| Bound identity | Value |
| --- | --- |
| Published source | `{args.source_commit}` |
| Version and tag | `{args.version}`, `v{args.version}` |
| Release runtime SHA-256 | `{args.runtime_sha256}` |
| Native-source baseline | `{args.native_baseline}` |
| Publication run / attempt | `{args.run_id}` / `{args.run_attempt}` |
| Public release ID | `{proof['release']['id']}` |

The audit verifies **{counts['native_cells']} native cells**, **{counts['native_test_outcomes']:,}
discovered native-test outcomes**, comprising **{counts['native_passed']:,} passes** and
**{counts['native_skipped']} explicitly permitted optional skips**, and
**{counts['public_assets']} independently downloaded public assets**. The 30 cells share
the same source, release run and attempt. The original public-installer job
verifies the native wheel, version and default MCP/client dependencies.
Skips are recorded separately from passes.

- [audit.json](audit.json) contains all source, workflow, cell, receipt, log,
  public-asset and input hashes.
- [evidence-manifest.json](evidence-manifest.json) records the original archive
  digest and every file/part hash. All **{len(files)} files** are retained,
  including **{len(proof['staged_evidence'])} original auditor inputs**.
- [evidence-parts](evidence-parts) contains **{len(parts)} ordered parts** of at
  most 262,144 bytes. The complete archive is reconstructed only when needed;
  no duplicate full archive is stored here.
- [restore_evidence.py](restore_evidence.py) verifies parts, archive and all
  restored files before making a new output directory available.
- [restoration-verification.json](restoration-verification.json) records the
  successful byte-for-byte restoration and identical second audit.

The acquisition metadata and additional original collection responses, when
supplied by the collector, are preserved inside the archive. This audit checks
the consistency of acquired GitHub evidence. It is not an independently signed
attestation or a claim that native binaries were reproducibly rebuilt.

## Reproduce the offline audit

Restore to a new directory whose parent already exists:

```sh
python restore_evidence.py --output /absolute/path/to/restored-evidence
```

From a checkout containing the frozen auditor and validators at the published
source, with the native-baseline Git object available, run:

```sh
python -B scripts/audit_comprehensive_release.py \\
  --evidence /absolute/path/to/restored-evidence \\
  --repo-root /absolute/path/to/AI-Memory-Book \\
  --source-commit {args.source_commit} \\
  --version {args.version} \\
  --runtime-sha256 {args.runtime_sha256} \\
  --native-baseline {args.native_baseline} \\
  --run-id {args.run_id} \\
  --run-attempt {args.run_attempt} \\
  --output /absolute/path/to/new-audit.json
```

The output must not already exist. The auditor reads and checks the original
bytes; it performs no network requests, package installation or native execution.
'''
    with (args.output / 'README.md').open('x', encoding='utf-8') as stream:
        stream.write(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--runtime-sha256', required=True)
    parser.add_argument('--native-baseline', required=True)
    parser.add_argument('--temporary-root', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--run-attempt', type=int, required=True)
    args = parser.parse_args()
    args.repo_root = args.repo_root.resolve(strict=True)
    args.evidence = args.evidence.resolve(strict=True)
    args.temporary_root = args.temporary_root.resolve(strict=True)
    require(args.temporary_root.is_dir(), 'Temporary root must be an existing directory')
    args.output = args.output.absolute()
    require(args.run_id > 0 and args.run_attempt > 0, 'Positive run and attempt required')
    print(json.dumps(execute(args), sort_keys=True))
