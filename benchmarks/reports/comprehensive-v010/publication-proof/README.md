# v0.10.0 publication proof

Published stable release: https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.10.0

Source/main/tag: `164f48c42e88bd096bf58827d8b2ba77a9048ae3`.
Release run `44009581198`, attempt 1; exact-source CI `44009581265`, all 11 jobs passed.

The immutable offline audit passed on its first execution. It connects all 30
native cells, 4,320 original test outcomes (4,245 passed and 75 named optional
skips), 11 original artifact ZIPs, eight actual job logs, all 67 independently
downloaded public assets and the real public installer to the exact source.
The tag, main and latest stable release were verified against the same commit.

## Files

- `publication-audit.json`: complete machine-readable proof with hashes for all
  97 staged inputs, original compiler/test/receipt details and public bytes.
- `publication-audit.log`: original successful offline audit output.
- `completion.json`: resolved publication gates and immutable experiment links.
- `text-evidence.tar.gz`: exact original metadata, eight raw decoded job logs,
  public text and receipts, tagged helper, five original cell-evidence ZIPs and
  acquisition ledgers. No native binary distribution is duplicated here.
- `text-evidence-manifest.json`: every retained input's original byte count and
  SHA-256, plus the archive digest.

The rejected first directory candidate, small-fixture regressions and initial
local diagnostic results remain unchanged at their existing evidence refs.
The component performance reports are separate from this delivery audit.

## Reproduction and storage scope

The audit script and acquisition contract are committed in the released source:
`docs/comprehensive-release-audit.md` and `scripts/audit_comprehensive_release.py`.
Extract the text bundle into an evidence directory to recover its original paths.
To repeat the complete original audit, also obtain the 32 original public binary
distributions and the remaining six original aggregate Actions ZIPs, and verify
them against `publication-audit.json`. The binary distributions are public
release assets; Actions ZIP availability follows the retained API `expires_at`
values. This Git checkpoint preserves the full execution text and receipt
chain, rather than claiming permanent retention of all Actions binary ZIPs.

The CI runs input is a documented exact-workflow selection from the complete
repository-runs API response because the connector does not expose the workflow
collection route. The original response, all three selected records and the
selection receipt are retained. No failed run or status was removed.

No build, native execution, package installation, measurement or workflow retry
was performed by the offline audit or by this preservation checkpoint.
