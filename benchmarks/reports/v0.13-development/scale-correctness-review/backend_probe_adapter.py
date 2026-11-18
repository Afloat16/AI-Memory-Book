"""Replay an original Python-only review probe using an explicitly bound backend.

The single transformed statement is the backend assertion. Original source
fixtures, requests, output writes and checks remain byte-identical in the
executed program; both hashes and the exact substitution are recorded.
"""
import argparse, hashlib, json, os, re, sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--probe', type=Path, required=True)
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--source', required=True)
p.add_argument('--backend', choices=['python', 'native'], required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
assert os.environ['MEMORY_BOOK_TEXT_BACKEND'] == a.backend
probe = a.probe.resolve()
original = probe.read_text()
replacement = "assert BACKEND_NAME == os.environ['MEMORY_BOOK_TEXT_BACKEND']"
adapted, substitutions = re.subn(r"assert BACKEND_NAME\s*==\s*'python'", replacement, original)
assert substitutions == 1
sys.argv = [str(probe), '--runtime', str(a.runtime.resolve()), '--source', a.source,
            '--output', str(a.output)]
exec(compile(adapted, str(probe), 'exec'), {'__name__': '__main__', '__file__': str(probe)})
sha = lambda raw: hashlib.sha256(raw).hexdigest()
receipt = {'scope': 'Backend assertion adapter; original inputs and expectations unchanged.',
           'probe': probe.name, 'backend': a.backend, 'source': a.source,
           'original_probe_sha256': sha(original.encode()), 'executed_probe_sha256': sha(adapted.encode()),
           'adapter_sha256': sha(Path(__file__).read_bytes()), 'replacement': replacement,
           'substitutions': substitutions}
if a.backend == 'native':
    from memory_book import _native
    receipt['native_sha256'] = sha(Path(_native.__file__).read_bytes())
(a.output / 'adapter-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
