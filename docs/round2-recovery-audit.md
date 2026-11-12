# Independent audit of the fixed-candidate recovery

The complete recovery result is commit `057b814ab809dec57d4fa4c75fe540d59a0f0027`
on `validation/round2-43207732852-1`. [Actions run 43207732852, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43207732852)
completed successfully. All ten stages completed; the registered strict assessment
returned zero. No retrieval, model call, candidate change or parameter adjustment
was performed for this independent audit.

## Independent completeness check

[The verification record](../benchmarks/reports/round2-recovery-independent-verification.json)
contains SHA-256 hashes for all **23 public files**: twenty stage raw/summary
files, the assessment, the Markdown report and the final checkpoint. A separate
checkout at the final result commit reran the existing strict summarizer. The
assessment was identical apart from its new `assessed_at` timestamp, and the
Markdown report was byte-identical. The original published files were restored
byte-for-byte after the comparison.

The verified matrix contains **32,256 started and finished search attempts**,
**3,072 distinct baseline/candidate native query/configuration pairs**, 256
questions and 614 required evidence annotations. Passing this check establishes
measurement completeness and integrity; it is not a declaration that every
quality or performance metric improved.

## Initial versus recovery evidence

[The cross-run audit](../benchmarks/reports/round2-recovery-crossrun-audit.json)
compares immutable Git objects from initial result commit
`150d37799098aa1fb1ddcebe5b42b18954adc035` and the final recovery commit. Only five
stages completed in both runs: export, baseline native, candidate native,
baseline component and candidate component.

Across these shared stages, **9,216 query/configuration rows** and **19,968
repeated non-timing sample projections** have no differences. The comparisons
include full scored rows, context and block hashes, evidence ranks, context
token counts, raw top-five hit identities/positions and identity hashes where
available. Every quality and diagnostic-group aggregate agrees. The dataset,
exported-page digest, diagnostic digest, corpus counts, frozen runtime hash and
evidence-attainability records also agree.

One database snapshot digest differs, repeated in all five shared reports:

| Snapshot | SHA-256 |
|---|---|
| Initial | `700b6780e9a09e1605f7bc0e8cd55bd39b3cd07c1118e1db5aaa4cdfd332bccf` |
| Recovery | `90beb7115aa9994226202a7d6e1d77fde7c580199836bdd6b9552bd49d6521b1` |

The audit therefore retains status **`completed_with_differences`**, rather than
silently treating the entire database snapshot as identical. The snapshot
function hashes all columns of the source tables. The frozen runtime writes
current ingestion times to project, chapter and session metadata, so a
difference is consistent with creating fresh archives at different times.
The original databases are not published; the public hashes alone cannot prove
that timestamps are the only differing fields. Both runs independently passed
their within-run original-source immutability checks.

No timing samples were combined or selected between runs. All final performance
comparisons use only the complete recovery host. The initial run did not finish
the external components or optional semantic stages, so this audit makes no
cross-run equivalence claim for those stages. The selection had already been
scored when the response-contract recovery was registered; the candidate and
all settings stayed fixed, without tuning or outcome-based run selection.

Reproduce the source-free comparison with:

```sh
python scripts/audit_round2_recovery.py --recovery-commit 057b814ab809dec57d4fa4c75fe540d59a0f0027
```

The command exits with status 2 when differences remain and writes the complete
diagnosis. This does not alter the separately successful strict matrix assessment.
