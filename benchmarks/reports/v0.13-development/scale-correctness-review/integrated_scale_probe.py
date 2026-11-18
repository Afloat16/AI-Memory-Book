"""Select an external committed runtime for the unchanged saved 64-case probe.

Only ROOT (the runtime and Git source root) differs. OUT continues to select
the original frozen inputs/protocol. The original probe checks its unchanged
workload/scorer/protocol and preserves each response before scoring.
"""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--source', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
probe = Path(__file__).with_name('probe.py')
spec = importlib.util.spec_from_file_location('_unchanged_scale_replay', probe)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = a.runtime.resolve()
sys.argv = [str(probe), '--source-commit', a.source, '--output', str(a.output)]
module.main()
receipt = {'scope': 'Runtime-root adapter only; no fixture/query/scorer changes.',
           'runtime': str(a.runtime.resolve()), 'source': a.source,
           'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'original_probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest()}
(a.output / 'adapter-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
