# T1 development attempt 2 (evaluator v2)

This directory preserves the single registered eight-cell development attempt.
Cell reports and their complete started/finished ledgers are losslessly compressed.
No query or source text is published. The summary keeps every quality and cost gate.

To restore the exact ledgers before the unchanged offline auditor or a permitted
next-cell continuation:

```bash
python - <<'PYRESTORE'
import gzip, hashlib, json
from pathlib import Path
root = Path("benchmarks/reports/round5-title-reference-t1-development-2")
for archive in sorted(root.glob("*.attempts.jsonl.gz")):
    target = archive.with_suffix("")
    raw = gzip.decompress(archive.read_bytes())
    report = json.loads(gzip.decompress(root.joinpath(archive.name.removesuffix(".attempts.jsonl.gz")).read_bytes()))
    assert hashlib.sha256(raw).hexdigest() == report["ledger_sha256"]
    if target.exists():
        assert target.read_bytes() == raw
    else:
        target.write_bytes(raw)
PYRESTORE
```

Then run `scripts/round5_title_reference_eval_v2.py --audit` with the exact binding.
Read progress.json before resuming: a remotely marked started cell without its
complete report is interrupted and must not be silently replayed. Completed
source-free reports and ledgers, rather than the private SQLite snapshots, are
sufficient for the offline arithmetic/identity audit.

This attempt repeats the entire frozen matrix after the registered evaluator
query-echo repair. Attempt 1 remains failed and immutable. Do not combine their
observations or claim a speed gain by comparing the attempts.
