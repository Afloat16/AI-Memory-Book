# v0.3.1 completed continuation — 2026-11-13

This continuation completes the registered round-three work that was interrupted
during evidence transfer. The published v0.3.0 baseline is
`dd2f88be742ed330269e7dd5915b6f75089d7fef`; the accepted v0.3.1 runtime remains
`2d199b93f650eccd3dd239178822b31001b880e3`.

## Completed decisions

| Work | Durable result | Decision |
|---|---|---|
| Formal default-retrieval performance | 47,320 calls, 16 workers, four balanced rounds | Complete payload equality; numeric gate passes with 11.3587% pooled p95 improvement |
| Empty-database startup resource review | Original +4.8384 ms / +14.0423% mean retained; independent source/SQL review and separate 80-sample diagnostic | Accept disclosed startup tradeoff; original automatic acceptance stays false |
| Project-statistics quality experiment | All eight original workers, ledgers and 8,082 calls reconstructed and independently checked | Reject after 14 registered loss checks; no rerun, retuning or shipment |
| Frozen same-host repository comparison | Run43267797247, result `c99f20531053b1c164fc5a5d3fa8e0c831eeb4de`, ten stages and 9,216 search calls | Complete-verified; zero default payload differences |
| Parallel preparation recovery | One executed registration and two unused preparations retain distinct identities | Adopt existing execution; no additional scoring |

The [completed optimization record](optimization-round3.md) gives all ten
performance cells and the accepted implementation. The
[current comparison](comparison.md) reports the measured claude-mem advantage,
ai-memory/billion-context quality gaps, Q2 small-budget losses, actual native
payloads and each component's interface boundary.
[Release notes](releases/v0.3.1.md) explain the resulting product behavior.

## Durable evidence and provenance

[Run reconciliation](round3-reconciliation.md) identifies the actual source,
binding and manifest, plus both unused preparations. Its linked machine-readable
record prevents an earlier preparation audit from being relabeled as an audit
of a different execution. Actual evaluator bytes and hash gates stay intact.

The previous interrupted upload remains in Git at `2bd5f27`; all original
workers and recovered data are retained, including the rejected candidate.
Performance evidence remains at `35b8618`, and the final comparison is
`c99f205`. Recovery and audit checkpoints preserve source and source-free
diagnostic work even where it is not part of the active frozen evaluator.

Source/plan commits precede expensive operations. Each hosted stage is committed
with its attempt ledger before the next stage. Large report recovery and
integration reuse existing Git objects; successful work does not depend on
one final chat/blob upload. Original experiment files and older releases remain
unchanged in their immutable histories.

The [release procedure](releasing.md) separately requires nine successful CI
jobs on the exact final commit, a matching main/tag, seven checked assets and
installation through the real public release URL. The release manifest supplies
the final source, package and installer hashes.
