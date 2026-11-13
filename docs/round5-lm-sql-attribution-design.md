# Prospective LM SQLite callsite attribution

## Status and boundary

This is the design checkpoint for one new mechanism diagnostic, `round5-lm-sql-attribution-1`. It contains no observer implementation, workflow, executable diagnostic binding or measurement. Root review is required before the next implementation stage. No diagnostic corpus calls, candidate comparisons, fresh selection or fresh decoding have occurred.

The only runtime is LM commit `49f10e7dec006e3a5760c93623a650dc7b6338d6`, aggregate runtime SHA-256 `fa56d26927ca625414ae9c9265ab285f2f8e714ec7ed015170e0bdd82d8a5bcd`. The adjacent JSON scope freezes all 18 source files, the original helpers and dependency closure, the eight saved C2 references, the complete sequence and the proposed observation rules.

The [complete independent LM audit](https://github.com/Afloat16/AI-Memory-Book/blob/128952ffd4f53a30f225feb98853a7f7f6ea7121/benchmarks/reports/round5-candidate-lm-development-1/independent-raw-audit.json) records GM p95 improvement 4.791840281283378% and public char4000 improvement 5.430823483528835%, below the original 10% goals. It retains public token512 p95 regression and smaller p50 increases. This diagnostic neither replaces that result nor reruns its paired measurement.

## Minimal reuse and new code

Use one new `scripts/round5_lm_sql_attribution.py`, one focused test module, one new workflow and one exact source/evaluator binding, all only after this design is reviewed. Keep every existing runtime, helper, scope, binding and report unchanged.

The [original profile helper](https://github.com/Afloat16/AI-Memory-Book/blob/8df838aa47e009caa8173b2ccb32fad93e4b8f90/scripts/round4_development_profile.py) enables and disables cProfile for each recall. A second `sys.setprofile` hook cannot simply be stacked over those calls. The new producer must therefore copy the small fixed loop into its own named module, import the unchanged original `CONFIGS` and `fingerprint`, and use the unchanged `benchmark_default_recall.dataset` loader. It must record its own script hash. It must not monkeypatch cProfile, modify the original helper or claim the original producer identity.

Reuse the proven exact source exports, full inventory checks, Git/gzip reads and serialized expected-head publication from the [LM controller](https://github.com/Afloat16/AI-Memory-Book/blob/8df838aa47e009caa8173b2ccb32fad93e4b8f90/scripts/round5_lm_development.py). A small diagnostic validator retains every existing profile audit predicate for counts, dataset identity, complete query order and response digests; only producer identity and observation output fields differ.

The one worker makes exactly 4,732 recalls: 168 synthetic queries and 1,015 public queries, each under the original four configurations. Each cohort is shuffled once with seed 41061, then that complete order is reused. The worker constructs one new database per cohort and retains the same MemoryBook across its four configurations. It does not run a baseline engine or ABBA workers. Tokenizer warmup, ingestion, reference reads and publication remain outside observation.

## Observable boundaries

The new observer uses `sys.setprofile` only during a single recall, in the worker's existing thread. It requires no previous callback and removes itself in `finally`. It recognizes ordinary native SQLite bound builtins without replacing connections, cursors or factories.

| Category | Fixed LM source sites | Observed boundary |
| --- | --- | --- |
| FTS candidates | `MemoryBook.recall` 810–812, shared fetch helper 253/257 with that upper caller | execute and fetchall |
| Directory metadata | recall 892–897, the same fetch helper with this upper caller | execute and fetchall |
| Revision and project bounds | revision 439; bounds 675–679 | execute and fetchone |
| Novelty bodies | recall 1016–1019 | initial execute only |
| Selected source pages | recall 1100–1104 | initial execute only |
| Excerpt highlights | highlighted bodies 352–354 | execute and fetchall |
| Original turn units | recall 1150–1153 | initial execute only |
| Transaction boundaries | recall 739, 1155, 1157 | execute |

The JSON scope freezes the source SHA, exact line ranges, function identity and optional disabled paths. Raw events also retain code first line, current line, bytecode offset and necessary upper caller metadata. Unknown sites and other delivered ordinary SQLite builtins remain explicit buckets; none are dropped. Exact and stem FTS candidate routes share a source site and stay combined. Neither SQL nor frame locals are inspected to distinguish them.

The observer records each target C span, successful return or exception with a per-query sequence, parent sequence, site, method and monotonic timestamps. A strict stack pairs nested events. Inclusive and exclusive sums are both retained, so nested calls do not silently inflate totals. Mismatched pairs, negative spans or an unclosed target stack invalidate and preserve the stage.

## Necessary interpretation limits

The novelty, selected-page and original-turn code consumes cursors through implicit iteration. Those SQLite steps need not produce the `fetchall` or `fetchone` C-call events this observer collects. Their execute spans are therefore incomplete query-consumption times.

The report may compare shares of **observed exclusive builtin spans**. It cannot report exhaustive SQL cost, Python-only residual time or uninstrumented latency. Recall wall time outside those spans remains explicitly unattributed: Python work, implicit cursor iteration, other unobserved SQLite work and profiler overhead.

Use `time.perf_counter_ns`; freeze and report clock placement and clock metadata. Keep callback event counts and callback bookkeeping time separately. Those figures omit interpreter dispatch cost and are not a full overhead correction. A single fixed artificial calibration batch may expose clock/callback costs on an invented in-memory SELECT operation, retaining every observation. It must not select a best repetition, adjust corpus timings or become a candidate speed comparison.

## Artificial proof before any corpus use

The focused fixtures must demonstrate:

1. Real native C-call/return and C-exception pairing, plus nested calls through an invented SQLite UDF on a second ordinary connection. The measured MemoryBook never receives that UDF.
2. Fake-clock arithmetic, exception unwind, partial event retention and fail-closed mismatched stacks.
3. Actual LM fixed source/line classification, including the shared fetch helper reached from two different upper callsites, multiline calls and unknown sites.
4. A small invented MemoryBook example has identical complete payload with observation on/off, still takes native tuple fetch at line 253, restores the shipping row factory and retains ordinary native connection identity.
5. Missing, extra, reordered and duplicated reference rows, bad source/helper/producer hashes or changed payload digests are rejected and retained.
6. Cell intent is published and read back before calls; output is published before the next cell; ambiguous publication stops; a started stage cannot be replayed.

Correctness runs in a separate exact LM source export. Preserve that complete export and inventory differences. A new clean export is then checked against all 18 source hashes and the runtime aggregate before measurement and before every cell. The observer never relaxes a runtime guard.

## Checkpoints and replay prevention

The future namespace is independent:

- Staging: `staging/v033-lm-sql-attribution`
- Trigger: `ci/v033-lm-sql-attribution-1`
- Results: `validation/v033-lm-sql-attribution-1`
- Reports: `benchmarks/reports/round5-lm-sql-attribution-1/`

A new exact binding must lock scope, observer/evaluator, classification map, runtime and successful artificial CI before any claim or data download. It must verify the prior LM source review and complete raw audit. Missing or mismatched binding fails immediately. Root retains trigger authority.

One persistent worker is the only Git publisher while it executes. Before each of eight cells it publishes an immutable intent and verifies the exact remote head. After each cell it saves and publishes every query digest, raw C span, summary and hash before entering the next cell. The parent waits and later reads the expected-head journal; it does not race the worker.

Each query receives a local fsynced started record before observation and a finished record after observation. Gzip preserves complete raw outputs with compressed and uncompressed hashes. Failure paths preserve available partial events, partial query logs and `log.partial`; the workflow always step only preserves evidence. No preservation step calls retrieval.

A hard VM loss can lose the current cell's unpushed bytes. The already-published cell intent still marks the stage incomplete and forbids replay. This is per-cell remote durability, not per-event remote durability.

There is one attempt and no hidden retry. Any ambiguous push, source drift, observer failure or runtime error stops further calls. A later repair would require a new prospective scope and attempt. All eight cells and all 4,732 payload/order checks are required for complete status; there is no timing-based early stopping, favorable-cell selection or release acceptance.

## Review requested

Approve or revise this narrow observation boundary before implementation. The material tradeoff is explicit: the low-intrusion native C observer can separate the visible execute/fetch boundaries while preserving native guards, but cannot assign all implicit cursor iteration cost. Expanding that boundary would be a separate design decision.
