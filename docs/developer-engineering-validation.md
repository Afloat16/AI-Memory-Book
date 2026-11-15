# Developer engineering validation

This report covers the current source's identifier retrieval, current-turn token
packing, schema-4 migration and database maintenance. The runtime was compared
with the source at upstream
[`a0de3f48`](https://github.com/Afloat16/AI-Memory-Book/commit/a0de3f48a7f585393c9b32b49ffcd3d29e6a5f3e).
It is a source validation, not a new published wheel release.

The [retained evidence](../benchmarks/reports/developer-engineering-20261115/)
contains reports, compressed raw responses, the dataset, source identities,
default-profile checks, migration checks and CLI transcripts. Original frozen
experiments remain unchanged. The existing evaluators and the 80-question
workload were not edited or retuned for these results.

## Changes exercised

| Capability | Concrete verification |
|---|---|
| Code identifier spelling | Acronym, camel-case, snake-case, digit-bearing and qualified identifiers; original spelling and source coordinates retained |
| Current decision under a token cap | The complete page fits the character allowance but exceeds the token allowance; verified fallback units stay within the comparable current turn |
| Existing archives | Schema migration, interruption before and after a 128-page batch boundary, concurrent openers, stable source/page identities, unchanged re-import skipping |
| Old writers | Real baseline processes attempt insert, replacement, relinking, session deletion and project deletion after migration; each incompatible transaction rolls back |
| Archive operations | Active WAL, concurrent commits, structural and runtime checks, existing-target races, deadlines and failure cleanup |
| Developer workflow | Five synthetic sessions, four projects, original page/source reads, repeated import, backup and recall from the independent copy |

The schema migration changes only derived lexical indexes when upgrading schema
3 to 4. It advances the revision, invalidates recall caches and leaves the source
hashing version unchanged. An optional semantic index must be explicitly rebuilt
after that revision change. Upgrade and restart every writer sharing the file;
see [deployment](deployment.md#current-main-and-schema-4).

## Regression and installed-package checks

The verified baseline passed **995 tests**. The integrated current source passed
**1039 tests**, with no failures, errors or skips in this environment: Linux,
Python 3.12, MCP 1.30.0, tiktoken 0.12.0, tomlkit 0.15.2 and pyarrow 26.0.1.
These are local results, not a claim that every supported OS/Python combination
was exercised here.

Some historical tests originally read frozen evaluator inputs directly from the
current checkout. Their input set includes the covering-index test that now
needs to check schema 4. Explicit historical fixtures preserve the original
bytes and hashes while the live test checks the current schema. Production
registration gates, recorded hashes and acceptance thresholds are unchanged;
negative tests still corrupt those temporary inputs and verify rejection.

An independently built wheel was installed without dependencies in a fresh
environment. Seven actual commands verified package import, canonical import,
identifier recall, database checking, online backup and identical evidence from
the copied archive. MCP was absent. This verifies the standard-library path and
new module packaging; it does not publish or rename that local wheel.

The larger CLI example ran **24 commands and 52 checks**. It recovered the
Bellman-Ford decision and failed prototype, `JSONLReader` input and split
constraints, the original `HTTPParser` contract and the inference project's
current value 32. The other project's value 256 stayed out of that query. Four
page reads and four source-session reads verified the actual returned spans;
all five unchanged sessions skipped on re-import.

## Token-only correction reproduction

A page contains an earlier value 8 and a later correction to 2. The full page is
117 tokens, while the current turn with its citation is 68 tokens. Both tested
reference encodings reproduce the same issue and correction:

| Budget and encoder | Baseline | Current behavior |
|---|---|---|
| 4000 characters, 90 tokens, `cl100k_base` | Old turn 0; current value missing | Current turn 1 and reason; 68 tokens |
| 4000 characters, 90 tokens, `o200k_base` | Old turn 0; current value missing | Current turn 1 and reason; 68 tokens |
| 4000 characters, at least 117 tokens | Full page | Full page retained |

The baseline happened to choose the right turn with smaller 68/73-token limits;
increasing the cap could reintroduce the old turn. New regressions cover this
non-monotonic fallback, unallocated selected pages, previous blocks consuming
the global budget, incomplete source authentication, fences and read-snapshot
consistency. The fix does not make every query monotonic in quality and does not
assert that a later statement is true.

Independent integration checks also exercised **48 combinations** of naming
changes, same-page/separate-turn layouts, character truncation and both token
encodings. They retained the corrected value and original source coordinates.

## Native engineering replay

The unchanged synthetic workload contains eight projects, six chronological
checkpoints and 80 questions: 72 answerable, 80 required evidence spans, 48
fixed-policy consumers and eight missing-evidence questions. Only history
available at each checkpoint is visible. All four native strategies are retained
in the raw output, including no-memory; the table focuses on Book before/after.

| Native setting | Evidence spans | Complete evidence | Policy checks | Mean characters | Stale-only cases |
|---|---:|---:|---:|---:|---:|
| Baseline, 1200 characters | 72/80 | 64/72 | 44/48 | 1196.0 | 0 |
| Current, 1200 characters | 74/80 | 66/72 | 46/48 | 1196.0 | 2 |
| Baseline, 2400 characters | 76/80 | 68/72 | 44/48 | 1812.0 | 0 |
| **Current, 2400 characters** | **78/80** | **70/72** | **46/48** | **1818.9** | **2** |

At both budgets, the two training historical-decision questions gain complete
evidence and pass their fixed consumer. No previously successful complete-case
or policy-case result becomes a failure. There is nevertheless a material
negative change: the two already-failing bilingual `split_policy` cases now
return an older decision without the required current evidence, increasing
stale-only cases from zero to two. The fixed consumer previously abstained on
those questions; it now chooses the old `row_modulo`/`whole_group` policies
instead of the required `whole_group`/`chronological` policies. This worsening
error mode is retained explicitly, not counted as an improvement. Aliases are
lexical features, not translation or global decision authority.

At the current 2400-character setting, flat FTS has **52/72 complete evidence**
and **28/48 passing policies**, versus Book's **70/72** and **46/48**. Recent
history has **56/72** and **32/48**. Flat FTS shares the current index, project
scope and packer; recent-history packing uses its original, different practical
strategy. Details remain in the individual reports.

The default-profile check executes 160 calls and confirms **80/80 complete
non-timing responses** equal explicit 2400/5 calls and this iteration's saved
explicit replay. Its unchanged verifier uses field names such as `historical`
and `frozen`; [reference.json](../benchmarks/reports/developer-engineering-20261115/default-profile/reference.json)
identifies the reference as this current explicit run, not the earlier release
experiment. Only `latency_ms` is excluded from response equality.

## Actual open-source component replay

The actual billion-context kernel remains pinned to
[`9674cfaf`](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15).
Both engines receive identical complete pages, project scope and top-five limits;
the common packer admits whole blocks under the same character budget. This is
a separate track from native excerpts.

| Whole-block setting | Complete evidence | Policy checks |
|---|---:|---:|
| Baseline Book, 1200 | 44/72 | 20/48 |
| Current Book, 1200 | 58/72 | 34/48 |
| billion-context kernel, 1200 | **64/72** | **40/48** |
| Baseline Book, 2400 | 68/72 | 44/48 |
| **Current Book, 2400** | **70/72** | **46/48** |
| billion-context kernel, 2400 | 64/72 | 40/48 |

At 2400 characters, current Book has **eight paired complete-evidence wins and
two losses** against the kernel. All eight wins are historical queries; both
losses are the bilingual training queries. Mean context is 1818.875 versus 1955
characters, a 6.96% reduction in this track. At 1200 characters the pairing is
eight wins and fourteen losses, so the low-budget disadvantage remains. The
kernel has zero stale-only cases at both budgets; current Book has two at 2400.
At 1200, current Book has six stale-only cases, down from fourteen in its
baseline whole-block replay.

These results compare a fixed component interface. Book retains hierarchy/FTS
metadata, and the engines expose different timing boundaries. They do not imply
that Book is faster than the complete upstream product, or better on every
workload. Mem0, claude-mem and Letta Code were not run in this replay.

## Integrity and measurement limits

Both native and component tracks retain both budgets, all strategies and all
failures. Source validation and budget violations are zero; repeated calls have
identical outputs. The current native 2400-character timings are p50 **1.573 ms**
and p95 **2.700 ms** over 240 calls. Result caching is disabled, but SQLite and OS
caches remain. The baseline and candidate runs were not an isolated,
counterbalanced performance experiment; do not interpret their timing delta as
a measured speedup or regression.

The cases are synthetic development material, not an independent holdout. A
fixed consumer extracts configuration and runs handwritten algorithm variants;
its pass rate is not LLM-generated code accuracy. All eight missing-evidence
questions return some related context. Production task success, coding time,
total model cost and adversarial multi-user behavior were not measured.

The backup checks establish SQLite structure, integrity and foreign keys.
`runtime_state` separately reports whether the current runtime's metadata is
ready, needs migration or needs repair. Neither field certifies factual truth
or all possible semantic-index inconsistencies. A pre-migration snapshot and
matching runtime remain necessary for downgrade recovery.

## Reproduce

Install the current source as described in the
[developer guide](engineering-workflows.md), then run:

```bash
python -m unittest discover -s tests -v
python -m benchmarks.engineering_workflow --output ./validation/native --repeats 3 --budget-chars 1200 2400
python -m benchmarks.engineering_components --output ./validation/components --repeats 3 --budget-chars 1200 2400
```

The component runner additionally needs Node.js and the locked upstream source.
Full historical provenance tests require a committed source tree, the retained
repository fixtures and an absolute interpreter path without `..`. The optional
SDK fast-path tests are certified against MCP 1.30.0; use that version when
reproducing this complete local test count. Unavailable optional dependencies
otherwise change the test/skip matrix. No private conversation corpus or model
API credentials are required for these replays.
