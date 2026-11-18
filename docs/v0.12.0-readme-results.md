# Current source results and evidence

The README reports the accepted **v0.12 source checkpoint**
`021a384567db5aa64fde155f090d2eb399f55c03`. The published **v0.12.0** release
at `62508a1ce681111ec5702c88e3aa42f67b9fc9c0` retains those accepted runtime
bytes and has completed exact-source CI, native-wheel installation and the
real public-URL installer gates. The quick start installs this published release.
[Original v0.12 delivery evidence and independent audit](../benchmarks/reports/v0.12-publication/README.md).

The prior v0.11 release keeps its [separate historical publication evidence](../benchmarks/reports/v0.11-publication/README.md);
its counts are not reused as new v0.12 executions.

The [v0.11 source results](v0.11.0-readme-results.md) and all failed development
attempts remain available. Historical external runs keep their original source,
package and model identities. New Book source results do not rerun every external
component or transfer old performance measurements to the new runtime.

## Source and experiment identities

| Evidence | Identity / execution |
|---|---|
| Published v0.11 baseline | `78cc906d81818a16884de7de2e613e5a56346f93` |
| Accepted v0.12 source | `021a384567db5aa64fde155f090d2eb399f55c03` |
| Published v0.12 source | `62508a1ce681111ec5702c88e3aa42f67b9fc9c0`; same accepted runtime digest |
| v0.12 exact-source CI | Run `44275753683`, attempt 1; 11 successful jobs |
| v0.12 delivery | Run `44275753685`, attempt 1; 30 native cells, 4,245 passes plus 75 permitted skips, 67 verified public assets and successful public installer |
| Accepted runtime | SHA-256 `2842f78c288454ea7348cb81cb6bd6a972cb26e003faaac64eb81f78b2ffa38b` |
| Engineering replay | 800 responses per runtime: 640 native-strategy and 160 Book common-block; all scores/source references/budgets independently checked |
| Engineering dataset | SHA-256 `87e8ccad3510fb7e8a4c68c9fa3f284473abf8381ef6444ad179e3d4196b3ac3` |
| Declaration diagnosis | 38 questions; 304 responses per backend/arm; 608 fresh candidate responses and 608 unchanged same-environment baseline responses reused |
| Short-page guard | 482 configurations per backend; original failures and control evidence retained |
| Directory rerun | Per backend: 119 contracts, 130 locator calls, 161 original-page reads, 80 distinct pages |
| Crowding replay | 144 actual responses across both versions/backends; 18/18 current-recovery calls per backend/arm |
| Corrected suffix review | 72 actual responses; original new regressions resolved, existing baseline failure retained |
| Complete local suite | 1,657 discovered; 1,655 passed; two Windows-only skips; zero failures/errors |
| LanceDB / Whoosh evaluator | Frozen at `8f0fa2ae81d938c6d47881468640d735e8b11c20` before quality queries |
| New external execution | 480 native searches, 320 packed responses, 984-event journal; independent offline audit passed |

The runtime digest is the source-byte aggregate defined by
`scripts.release.source_identity`; it is not an evaluator or native-binary digest.
The [source acceptance](../benchmarks/experiments/v012-source-acceptance.json)
binds every referenced report's byte count and SHA-256. The
[complete validation record](v0.12.0-validation.md) distinguishes actual executions,
reused baselines, original failures and completed publication checks. The source
acceptance JSON remains the original prepublication decision; its then-pending
delivery requirements are closed by the separate publication proof.

The engineering comparison has zero per-case score regressions. Its 104 changed
native score records and 34 changed common-block score records include source
ranks and context lengths; they are **not** 138 independent accuracy gains or
unchanged serialized responses. The actual gain is four additional complete
evidence cases at 1,200 characters in each packing track.

## Fixed workload and comparison boundary

| Property | Fixed setting |
|---|---|
| Workload | Authored synthetic engineering development/regression fixture |
| Scope | 8 projects, 4 algorithm families, 6 chronological checkpoints |
| Questions | 80 total: 72 answerable, 8 missing-evidence queries |
| Denominators | 80 required evidence spans; 48 fixed-policy cases |
| External candidate boundary | Same original page bodies, exact project scope, at most 5 native candidates |
| Common packing | Original whole blocks with citation framing; oversized blocks are skipped, without rewriting the query or supplementing candidates |
| Native excerpt track | Book plus repository scoped-flat-FTS, recent-history and no-memory strategies |
| Excluded conclusions | Coding-LLM accuracy, independent holdout performance, production task success, calibrated abstention, universal superiority |

All external rows in this comparison use the same workload and checkpoint
source-page digests, with 24/56/80/104/120/144 visible pages. The new
[LanceDB/Whoosh same-input audit](../benchmarks/reports/v0.12-search-components/same-input-audit.json)
checks byte-identical input files against the prior extension; the Book replay
retains the unchanged evaluator and its own exported source bundles. External
indexes are rebuilt at each checkpoint, so these runs do not establish native
update/delete lifecycle correctness. The last checkpoint has only 44 distinct
page bodies among 144 pages, including repeated maintenance text. This limits
the fixture's discrimination and generalization.

## Complete common-block results

Book's two rows come from the current accepted source replay. The six original
external configurations, the Haystack/BM25S extension and the LanceDB/Whoosh
extension retain their original pinned executions. The three shared-MiniLM
configurations are grouped for display, not counted as one execution or three
independent model evaluations.

| Component / tested mode | Budget | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| **Book, v0.12 source replay** | 2,400 | **80/80** | **72/72** | **48/48** | **0** | 1,798.9 |
| BM25S 0.3.16, native defaults | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,846.7 |
| Whoosh 2.7.4, BM25F / configured OR | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,457.8 |
| Haystack 3.5.0, native BM25 | 2,400 | 74/80 | 66/72 | 42/48 | 0 | 1,884.7 |
| LanceDB 0.41.0, native FTS | 2,400 | 72/80 | 64/72 | 40/48 | 4 | 1,876.7 |
| billion-context, pinned search kernel | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,955.0 |
| claude-mem, supplied-observation FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,488.5 |
| Basic Memory, explicit FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,333.1 |
| Each shared-MiniLM configuration | 2,400 | 55/80 | 47/72 | 25/48 | 4 | 1,963.1 |
| **Book, v0.12 source replay** | 1,200 | **80/80** | **72/72** | **48/48** | **0** | 1,041.5 |
| BM25S 0.3.16, native defaults | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 1,045.3 |
| Whoosh 2.7.4, BM25F / configured OR | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 884.5 |
| Haystack 3.5.0, native BM25 | 1,200 | 74/80 | 66/72 | 42/48 | 0 | 969.9 |
| LanceDB 0.41.0, native FTS | 1,200 | 72/80 | 64/72 | 40/48 | 4 | 1,035.8 |
| billion-context, pinned search kernel | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.5 |
| claude-mem, supplied-observation FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 848.0 |
| Basic Memory, explicit FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.6 |
| Each shared-MiniLM configuration | 1,200 | 55/80 | 47/72 | 25/48 | 4 | 1,036.7 |

**Book, BM25S and configured Whoosh tie on complete evidence and fixed-policy
counts at both budgets. Whoosh uses fewer mean packed characters than Book at
both budgets.** At 2,400 Book finds six more complete cases than Haystack and
eight more than LanceDB and each of the three historical lexical modes. It
recovers 25 more than each shared-MiniLM configuration. A better aggregate does
not imply a win on every question or a ranking of complete products. Characters
are not model tokens or billing costs. Displayed means use decimal round-half-up
to one decimal place; original reports retain exact values.

Mem0 (`infer=False`, Chroma provider), Chroma and LangGraph Store were executed
separately with the same real local MiniLM representation. Mem0 fact extraction,
claude-mem's observer and Basic Memory's default semantic/hybrid workflow were
not run. Whoosh's OR parser was explicitly selected before quality execution;
its default parser is AND. The other tested Whoosh analyzer/scorer settings
remain native defaults. LanceDB's native FTS uses an exact project prefilter.
Haystack, BM25S, LanceDB and Whoosh are framework/store/retrieval components,
not complete conversation-memory products. Source-mapping checks authenticate
adapter mappings to supplied originals, not identical native citation features.

BM25S and Whoosh complete 8/8 in each answerable category. Haystack has 2/8
historical decisions and 8/8 in the others. LanceDB has 4/8 bilingual and 4/8
historical-decision cases and 8/8 in the others. Historical per-category and
per-question records are retained unchanged. All ten scored external
configurations and Book return context for all eight missing-evidence questions;
this is not a measurement of model refusal or invented answers.

### Memvid: retained query limitation

`memvid-sdk==2.0.160`, explicit `mode="lex"`, returned native `hits=[]` for all
80 unchanged natural-language questions in all three repetitions. The adapter
did not discard candidates. Its 0/72 complete-evidence count remains in the raw
report; the README reports the configured-query limitation separately, rather
than assigning the whole product a zero-score ranking.

A separate 14-call diagnosis uses the first checkpoint's unchanged pages. The
original full question has no hits with or without scope; original-text keyword
controls retrieve source-verified pages. Diagnostic queries do not replace
scored questions. The tested API normalizes whitespace and adds metadata framing;
the adapter verifies the entire normalized text and frame/URI/project/title/time
identity before mapping back to original bytes. It does not establish byte-exact
native source reading. An all-empty result is not calibrated abstention.

[Protocol and pre-quality failures](../benchmarks/competitors/extended-lexical-plan.md)
· [Original report](../benchmarks/reports/v0.11-extended-lexical/attempt1/report.json)
· [Independent audit](../benchmarks/reports/v0.11-extended-lexical/attempt1/audit.json)
· [Diagnostic](../benchmarks/reports/v0.11-extended-lexical/memvid-query-diagnostic-1/report.json).

## Native excerpt strategies

These rows all come from the accepted source's fresh engineering replay. The
flat strategy shares the product's native excerpt assembler, so its 1,200-character
result also changes when that assembler changes; it is not a frozen external
implementation.

| Strategy | Budget | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| Book | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,798.9 |
| Scoped flat FTS | 2,400 | 60/80 | 52/72 | 28/48 | 14 | 1,801.3 |
| Recent history | 2,400 | 64/80 | 56/72 | 32/48 | 0 | 2,260.9 |
| No memory | 2,400 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |
| Book | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 1,196.6 |
| Scoped flat FTS | 1,200 | 60/80 | 52/72 | 28/48 | 14 | 1,154.6 |
| Recent history | 1,200 | 40/80 | 32/72 | 16/48 | 0 | 1,184.0 |
| No memory | 1,200 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |

At 2,400 Book recovers 20 more complete cases than scoped flat FTS and 16 more
than recent history with 20.4% fewer mean context characters. Recent history
has shorter citation headings and no top-five candidate limit. Native-excerpt
and common-block rows remain separate protocols even where their aggregate
counts agree.

### What changed at 1,200 characters

| Book source / packing | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|
| v0.11 / native excerpts | 76/80 | 68/72 | 48/48 | 0 | 1,195.9 |
| v0.12 / native excerpts | 80/80 | 72/72 | 48/48 | 0 | 1,196.6 |
| v0.11 / common blocks | 76/80 | 68/72 | 44/48 | 4 | 1,048.1 |
| v0.12 / common blocks | 80/80 | 72/72 | 48/48 | 0 | 1,041.5 |

The old four incomplete cases and four common-block stale-only outcomes are
retained in the baseline responses. Neither the original question/label set
nor the shared packer was changed. This is a development-fixture improvement,
not a new independent test set. Zero stale-only means no registered stale span
without any required span under that fixed metric; old and current text can
still coexist in a response.

## Declaration diagnosis and remaining limits

On the separately registered 38-question diagnostic, each auto-mode
budget/limit setting improves expected-first-source recovery from **22/32 to
30/32** answerable questions, on both backends. With limit one, complete evidence
improves by the same counts; with limit five it stays **32/32**. Both
`chinese-prose:0` and `chinese-prose:1` still select an earlier decision first;
the newer evidence appears with limit five. The six non-answerable/control
questions are reported separately, not added to the answerable denominator.

Current-state comparison now requires authenticated, statement-local comparable
declarations even within the original relevance pool. This prevents specific
unqualified recency transfers. It does not make BM25 a general authority model:
a sufficiently relevant agenda can still rank first, ambiguous prose can be
left unrecognized, equal-time conflicts are unresolved and missing-evidence
queries can return related records. Project binding guards accidental scope
changes within a configured connection; it is not multi-user authentication.
The finite supplement cap does not bound every database scan or source check.
[Every response, counterexample and correction](v0.12.0-validation.md).

## Architecture coverage and historical performance

The official-source review covers **26 external project families**, including
six retrieval/store libraries or frameworks. **Eleven external configurations**
have actually run on this fixture: ten scored configurations and Memvid's
separate query limitation. Hindsight, MemSearch and MCP Memory Service were
added through pinned documentation review, without runtime scores. Companion
LangMem remains grouped with LangGraph. [Complete modes and sources](open-source-memory-comparison.md).

The README's v0.10 semantic/directory and earlier native-core timings keep their
original source snapshots, costs and slower cases. v0.12 changes temporal
ordering and character/token assembly. Identical C/header bytes establish
component continuity only. No new latency comparison, product-wide speedup,
allocation win or combined percentage is inferred from the correctness runs.

## Reproduce and audit without replacing evidence

Use fresh output paths and the committed immutable baseline/candidate sources.
The [engineering replay driver](../scripts/validate_v012_engineering.py) verifies
actual runtime inventories and independently recomputes scores. The
[declaration evaluator](../benchmarks/v012_revision_eval.py) and
[pair auditor](../benchmarks/v012_revision_pair_audit.py) retain their frozen
protocol and before/after runtime identities. Repeated execution creates a new
attempt; it must not overwrite recorded successes or failures.

The [LanceDB/Whoosh evidence restorer](../benchmarks/reports/v0.12-search-components/README.md#evidence-and-lossless-restoration)
checks every compressed piece, original file and audit digest before offline
recomputation. It requires no upstream installation to verify saved records and
does not rerun ranking. Source checks, package installations, correctness
replays, CI and public-installer delivery are distinct evidence levels.
