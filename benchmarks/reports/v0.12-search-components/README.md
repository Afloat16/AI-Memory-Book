# Actual LanceDB and Whoosh component extension

The first registered quality attempt completed successfully under frozen
evaluator commit `8f0fa2ae81d938c6d47881468640d735e8b11c20`. Independent offline
recomputation verified **480 native searches**, **320 packed responses**, and
the complete **984-event execution journal**. Original queries, exact scopes,
all original page bodies, native ordering/scores and the two character budgets
were preserved. Both upstream installations matched their preregistered full
file/RECORD/version closure before and after every checkpoint worker.

| Actual component configuration | Chars | Required spans | Complete evidence | Fixed-policy checks | Stale-only | Mean context chars |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LanceDB 0.41.0 native FTS | 1,200 | 72/80 | 64/72 | 40/48 | 4 | 1,035.75 |
| LanceDB 0.41.0 native FTS | 2,400 | 72/80 | 64/72 | 40/48 | 4 | 1,876.7 |
| Whoosh 2.7.4 BM25F, explicit OR parser | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 884.45 |
| Whoosh 2.7.4 BM25F, explicit OR parser | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,457.825 |

Each cell has 80 original questions, including 72 answerable and eight
missing-evidence cases. Both components return nonempty context for all eight
missing-evidence queries. There are zero source-validation failures, budget
violations or repeated-output changes in the recorded matrix. Three repeats
are stability observations, not extra independent questions. No speed ranking
is inferred from diagnostic timing fields.

These are actual upstream **search-component configurations**, not full memory
products. Whoosh's `OrGroup` is explicitly configured; its default query parser
uses AND. StandardAnalyzer and default BM25F ranking remain unchanged. LanceDB
uses its native FTS defaults and exact native project prefilter. Neither worker
receives gold labels or rewritten queries. The
[frozen protocol](../../competitors/v012_search_components.protocol.md) describes
the boundaries and complete 17-distribution/3015-file installation lock.

## Comparability and retained limits

[same-input-audit.json](same-input-audit.json) verifies that the dataset digest
and all six supplied-page JSON files are byte-identical to the earlier actual
Haystack/BM25S/Memvid extension. The shared whole-block packer and top-five
candidate limit are unchanged. This permits a comparison of those configured
rows; it does not rerun earlier components or establish generalization beyond
the authored development fixture.

Whoosh ties the previously recorded Book result at 2,400 characters and reaches
more complete cases at 1,200 characters than the earlier Book common-pack row.
It also uses less mean context at 2,400 in this fixture. These observations must
be retained when describing Book's engineering advantages; they do not support
a claim of universal dominance. Any new Book runtime needs its own same-input
replay before it is compared here.

Both API smoke attempts and the nine source/matrix-integrity unit checks remain
under their original directories. The first smoke's incomplete evaluator
inventory is disclosed in the protocol; it was corrected before any quality
query. The second marker-only smoke passed all ten native scope queries,
including prefix, quoted literal, absent scope and the five-result cap.

## Evidence and lossless restoration

- [Original report text](quality-attempt1/report.md) and
  [summary projection](quality-attempt1/summary.json) provide readable results.
  The projection copies recorded values and identifies the original report hash.
- [Independent audit](quality-attempt1/audit.json) records every original
  evaluator-input hash and the independently verified response counts.
- [Archive manifest](quality-attempt1/archive-manifest.json) identifies five
  large original files retained as compressed fixed pieces, each at most
  262,144 bytes. All smaller source bundles, checkpoint records and logs remain
  directly available. The original file bytes and auditor inputs are unchanged.
- [Execution record](quality-attempt1-execution.json) retains the actual command,
  frozen evaluator commit, timestamps, selected interpreter and exit status.

Restore into a new directory with an existing parent:

```sh
python benchmarks/reports/v0.12-search-components/restore_quality.py \
  --output /absolute/path/to/restored-quality-attempt1
```

The restorer checks every piece, the complete compressed archive, the exact
original input inventory and every restored file against the original audit.
It neither executes upstream search nor edits any report. Use the unchanged
evaluator source from commit `8f0fa2ae81d938c6d47881468640d735e8b11c20` to rerun
the offline audit on the restored directory. The original runtime Git objects
must be available. Installation of LanceDB or Whoosh is unnecessary for that
offline audit.
