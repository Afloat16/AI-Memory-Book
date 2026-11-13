# Independent audit of recovered round-three quality evidence

**The original project-statistics screen is complete and the candidate is
rejected.** All eight worker recordings and all **8,082 original recall calls**
were recovered from the interrupted upload. The registered gate has **14 loss
checks and 10 improvement checks**. Project-local FTS statistics therefore stay
out of the release and out of the new-cohort comparison.

This audit executed **zero new retrieval or model calls**. It verifies saved
bytes and recomputes their recorded metrics. The four cohorts are old
development/regression data, not a fresh test of generalization. These are
evidence-retrieval metrics, not generated-answer accuracy.

## Original evidence and recovery boundary

The immutable upload checkpoint is
[`2bd5f27d1ae478c1735f36b5354fddd81114182b`](https://github.com/Afloat16/AI-Memory-Book/commit/2bd5f27d1ae478c1735f36b5354fddd81114182b).
It contains eight original files for the first four workers and 48 of the 78
advertised transfer chunks. The upload stopped before its original transfer
manifest was saved.

| Original bytes | Recovered content |
|---|---|
| Four `.worker.json.gz` files and four `.ledger.jsonl` files | Both modes for synthetic61 and authored36 |
| Complete transfer groups 00–03 | Both modes for hotpot128, with their matching ledgers |
| Complete transfer groups 04–07 | Both modes for public1015, with their matching ledgers |
| Incomplete group 08 | The aggregate's complete controller metadata and a prefix of its worker array |

The missing tail of group 08 does **not** contain missing retrieval rows:
the complete worker files already preserve those rows independently. Its
1,179,648 compressed bytes decode to 9,401,417 bytes before truncation. All
controller metadata occurs before the worker array and survives intact,
including the eight original worker attempts, their actual zero exit codes,
the final validation, the paired comparisons and the original rejection.

The audit reconstructs the complete canonical JSON using that metadata and
the intact original workers. **Every available decoded prefix byte matches
the reconstruction.** The original complete aggregate gzip remains
unavailable; the new aggregate is a verified reconstruction, not a claim that
the missing compressed bytes were recovered.

The original run finished at `2026-11-12T15:14:39.092623+00:00`.
The source, data, evaluator, tokenizer and recorded timing identities remain
those of that original run. Recovery adds no replacement samples.

## Verification

The [independent audit script](../scripts/audit_round3_quality_independent.py) reads the
fixed Git commit and performs the following checks before reporting a gate:

- Complete gzip members pass decompression and trailer validation. Worker
  identities come from their own cohort/mode fields; each ledger is matched
  by the worker's embedded SHA256 rather than an assumed transfer filename.
- Every call has its original ordered start and completion events. All
  **16,164 ledger events** match the corresponding 8,082 row hashes.
- Source commits/hashes, the dataset identity and query IDs, the frozen
  evaluator and binding, all three budgets, the query ordering and every
  recorded source/scope/cache/budget invariant are checked.
- Recorded summary values are recomputed from the saved rows. Evidence rank
  accounting, paired case/group identities, unscoped payload equality,
  derived-index build/switch continuity and storage accounting are checked.
- The original frozen validator, comparisons and screening decision all
  agree. There are 4,017 candidate calls with project statistics enabled and
  24 unscoped candidate calls that correctly retain the global path.
- The reconstructed aggregate matches the entire surviving original prefix.
  No exit code, missing request, runtime result or controller status is
  invented.

The machine-readable
[independent recovery audit](../benchmarks/reports/round3-quality-independent-audit.json)
records all 56 input hashes, the recovered identities, every aggregate/group
gate loss, all 12 comparison cells and hashes binding the complete paired
details. Its compact summaries avoid duplicating the original large reports.

An independently published hosted recovery also passed:
[run 43266603949](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43266603949),
saved at
[`f0f6a5eeaa797c01fcba12e17882c9089f44df87`](https://github.com/Afloat16/AI-Memory-Book/commit/f0f6a5eeaa797c01fcba12e17882c9089f44df87).
The local audit checked its
[recovery manifest](https://github.com/Afloat16/AI-Memory-Book/blob/f0f6a5eeaa797c01fcba12e17882c9089f44df87/benchmarks/reports/round3-project-stats-recovery-43266603949-1/recovery-manifest.json):
**56/56 input sizes, Git blob IDs and SHA256 hashes agree**, as do the original
validation, the complete screening decision and the reconstructed JSON hash.

| Identity | SHA256 |
|---|---|
| Reconstructed complete canonical JSON | `5319394dbff4ba833ac7795219947ae26a550bb2010620aab38a2c037fd07f9b` |
| Original compressed prefix | `244ab099bb4351f06bf2f677156cd9c31235a3b0563211075d190203a5949cc8` |
| Original decoded prefix | `09f896400de53204a356f3c5aa4d78669f1e6a3c04749f6462e23e9c14fd1ed3` |

The hosted result preserves all worker bytes, ledgers, per-question gains and
losses, groups, costs and the incomplete original aggregate prefix. Its
[complete original screen](https://github.com/Afloat16/AI-Memory-Book/blob/f0f6a5eeaa797c01fcba12e17882c9089f44df87/benchmarks/reports/round3-project-stats-recovery-43266603949-1/round3-project-stats-20261112-1.md)
is the full result, including resource measurements.

## Quality result

All cells use top five results, an 8,000-character cap and `cl100k_base`.
Complete-evidence rate uses answerable questions: 152/168 synthetic61,
30/36 authored36, 649/1,015 public1015 and 128/128 hotpot128. Unsupported
questions remain in the experiment and its separate unsupported-response gate.

| Cohort | Tokens | Complete evidence: global / project-local | Evidence recall: global / project-local | Complete gains / losses |
|---|---:|---:|---:|---:|
| synthetic61 | 512 | 85.53% / 82.24% | 86.36% / 83.52% | 0 / 5 |
| synthetic61 | 1,024 | 92.11% / 91.45% | 93.18% / 92.61% | 0 / 1 |
| synthetic61 | 2,048 | 92.11% / 91.45% | 93.18% / 92.61% | 0 / 1 |
| authored36 | 512 | 86.67% / 86.67% | 88.89% / 88.89% | 0 / 0 |
| authored36 | 1,024 | 86.67% / 86.67% | 88.89% / 88.89% | 0 / 0 |
| authored36 | 2,048 | 86.67% / 86.67% | 88.89% / 88.89% | 0 / 0 |
| public1015 | 512 | 66.41% / 65.64% | 62.18% / 62.18% | 13 / 18 |
| public1015 | 1,024 | 72.88% / 74.27% | 69.54% / 70.94% | 13 / 4 |
| public1015 | 2,048 | 72.88% / 74.27% | 69.54% / 71.07% | 13 / 4 |
| hotpot128 | 512 | 35.16% / 50.78% | 66.99% / 74.84% | 28 / 8 |
| hotpot128 | 1,024 | 48.44% / 67.19% | 74.51% / 83.99% | 28 / 4 |
| hotpot128 | 2,048 | 48.44% / 67.19% | 74.51% / 83.99% | 28 / 4 |

The Hotpot improvements are substantial, but the preregistered rule requires
non-regression in **every** cohort/budget cell and in qualifying primary
512-token groups. It does not permit improvements on one cohort to cancel
losses on another.

The fourteen failed checks comprise six synthetic aggregate checks, four
synthetic 512-token group checks, the public1015 512-token complete-evidence
check and three public 512-token group checks. For example, synthetic
multiple-evidence completeness falls from **41.67% to 20.83%**, and public
cross-session completeness falls from **10.53% to 6.58%**. These groups meet
the registered minimum size. All individual gains and losses remain in the
original saved report.

The source of this rejected candidate is
`2b51f72b63ff14053c92713858347edb2d572971`; the control is v0.3.0 at
`dd2f88be742ed330269e7dd5915b6f75089d7fef`. This quality decision is separate
from the guarded rowid-range performance candidate. The original quality
candidate is closed under the registered protocol, with no retuning or
additional scoring in this recovery.

## Reproduce the independent audit

Fetch the exact evidence commit and materialize its eight original files and
48 transfer blobs before an offline audit. In a partial clone, missing objects
are reported instead of triggering an unbounded implicit network fetch.

```bash
python scripts/audit_round3_quality_independent.py --check
```

The checked-in report is deterministic. `--check` verifies it without changing
any source or report. For a separate copy, pass a new `--output` path; an
existing output is never overwritten.
