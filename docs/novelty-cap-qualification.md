# Capped novelty: strict regression qualification

**Final decision: reject the cap candidate and retain the current product.**
Stage A completed all 4,096 registered calls. Every one of the eight paired
512-token settings loses complete questions, with zero complete-question gains.
Stage B remains explicitly `not-run`; its 8,192 planned calls were not executed.
The candidate was not tuned or retried after this result, and its runtime code
was not adopted.

The [old-data development probe](novelty-probe.md) found three additional
complete LoCoMo questions and three additional annotations at 512 tokens,
with no evidence losses in its twelve development settings. That result
justifies a qualification attempt; it does not establish that other budgets,
corpora or the Q2 route are unaffected.

## Source, registration and scope

The [plan](../benchmarks/experiments/novelty-cap-qualification-plan.json) and
[binding](../benchmarks/experiments/novelty-cap-qualification-binding.json)
were committed at
[`186283d`](https://github.com/Afloat16/AI-Memory-Book/commit/186283dd0a2511b80e50ae185a03f488ac974c30)
before [run 43220260514](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43220260514),
attempt 1. Four new evaluator/workflow/plan/test files are independently bound;
the 58 original round-two helpers retain their original hashes. Twelve
invented control-flow tests and independent code review passed before scoring.

| Item | Registered value |
|---|---|
| Current runtime | `cbf626037b42f11f8bc5b6d46f56caac771e54ba` |
| Current runtime SHA-256 | `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57` |
| Cap runtime | `b7d3cb90ce71017ebb2c34b1bf172652e1d102e4` |
| Cap runtime SHA-256 | `b3bab146b37346dfcaf80457d8b7372834a4b04eec676ab926516a3d051378db` |
| Plan SHA-256 | `3c8e18fd3af2c7f4edcacecdb1f4903be12914d2669daf58acc3c56960dec105` |
| Binding SHA-256 | `38d08b808c6289eec447a8205847abe0b3ef41d23aef237a02accad338ba66fb` |
| Corpus | The previously scored 256 HotpotQA questions, 614 annotations and 3,769 canonical pages |
| Modes | Current/cap, each with default lexical retrieval and optional Q2 |
| Native axes | 2,000/8,000 characters; cl100k_base/o200k_base; top 5; coverage disabled |
| Stage A | 512 tokens, one pass, 4,096 calls |
| Stage B | Only after A qualifies: 1,024/2,048 tokens, one pass, 8,192 calls |
| Query-result cache | Disabled in every scored call |
| Generative model calls | Zero |

These are **previously scored regression questions**, not unseen validation or
a new domain. Each supplied paragraph maps to a source session/chapter. The
scorer retains the original denominator, including the annotation that the
fixed page representation cannot fully contain in one canonical page. The
experiment does not repeat competitors, generated answers or complete memory
workflows. Single-pass setup, latency and memory measurements are diagnostics,
not a performance claim.

## What the candidate changes

The existing query-term novelty multiplier is capped at 1.25; its first
selected page, base scores, temporal handling, candidate limits, exact/stem
fusion, source content and token assembly remain unchanged. There is no new
parameter search in this qualification.

The development source at `506f1c6` changed only that ranking expression. Before
qualification scoring, the separate `b7d3cb9` source also increments
`RECALL_VERSION` from 10 to 11. Result caches persist in SQLite, so a ranking
upgrade must have a distinct cache key. Disk-reopen tests cover both lexical
and semantic caches: old results remain stored but are not reused; fresh
results can be cached; original sessions, revision and semantic vectors remain
unchanged. Forcing version 10 makes both tests detect the stale-cache behavior.
The old cache-disabled development measurements remain bound to their original
source and are not rewritten.

## Qualification gates and interruption records

Every configuration in each mode must have **zero complete-question losses
and zero annotation losses**. Gains cannot offset a loss elsewhere. This is
stricter than the development probe's aggregate non-regression screen.
Source, scope, exact token budget, metadata and input-identity checks must pass.
The two Q2 workers in a phase must also have byte-identical semantic vector
rows under the same pinned model and one inference thread.

All four A workers complete before its decision. A quality rejection leaves B
explicitly `not-run`. An infrastructure or integrity error is recorded as
`failed-incomplete`, also preventing B. The direct B-worker entry independently
recomputes and checks A's qualified decision. The formal entry points accept
only the dedicated Actions ref and first attempt.

A checkpoint is published before preparation and around each worker. Raw
records, summaries and separate compressed attempt ledgers are saved to the
[run-specific Git branch](https://github.com/Afloat16/AI-Memory-Book/tree/validation/novelty-cap-43220260514-1).
Interrupted workers retain their available completed attempt records; missing
summaries are never labeled complete. The Actions artifact also has an exact
ledger fallback and does not upload the private source corpus, models or
databases.

## Complete stage-A results

Every row is **512 tokens**, with 256 answerable questions and 614 required annotations. Each arrow is **current → cap**. Gains/losses are paired within the configuration; the same questions appear in multiple rows, so row losses must not be summed and called distinct questions.

| Mode | Chars | Tokenizer | Complete questions (of 256) | Complete % | Evidence recall % | MRR | Complete G/L | Annotation G/L |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Default lexical | 2,000 | cl100k_base | 62 → 61 | 24.2188 → 23.8281 | 55.3746 → 55.0489 | 0.7578 → 0.7568 | 0 / 1 | 0 / 2 |
| Default lexical | 2,000 | o200k_base | 62 → 61 | 24.2188 → 23.8281 | 55.5375 → 55.0489 | 0.7588 → 0.7568 | 0 / 1 | 0 / 3 |
| Default lexical | 8,000 | cl100k_base | 106 → 103 | 41.4062 → 40.2344 | 68.7296 → 68.0782 | 0.8519 → 0.8506 | 0 / 3 | 1 / 5 |
| Default lexical | 8,000 | o200k_base | 108 → 105 | 42.1875 → 41.0156 | 69.0554 → 68.4039 | 0.8519 → 0.8506 | 0 / 3 | 1 / 5 |
| Q2 | 2,000 | cl100k_base | 62 → 60 | 24.2188 → 23.4375 | 55.0489 → 54.5603 | 0.7542 → 0.7549 | 0 / 2 | 0 / 3 |
| Q2 | 2,000 | o200k_base | 61 → 59 | 23.8281 → 23.0469 | 54.7231 → 54.2345 | 0.7533 → 0.7539 | 0 / 2 | 0 / 3 |
| Q2 | 8,000 | cl100k_base | 106 → 105 | 41.4062 → 41.0156 | 68.2410 → 68.0782 | 0.8558 → 0.8558 | 0 / 1 | 1 / 2 |
| Q2 | 8,000 | o200k_base | 105 → 104 | 41.0156 → 40.6250 | 68.2410 → 68.0782 | 0.8558 → 0.8558 | 0 / 1 | 1 / 2 |

All eight settings violate the registered zero-loss gate. Some have one annotation gain alongside more annotation losses; those gains do not offset a loss. In this run the aggregate complete-evidence rate and annotation recall also decrease in every setting, so the rejection is not only a consequence of the stricter per-question rule.

### Context and single-pass timing diagnostics

Token counts below use the active budget tokenizer and include the native cited context. They are not full Python response payloads, MCP envelopes or provider bills. These one-pass timings retain all 256 samples per configuration. They do not establish a speed improvement or replace the separately balanced performance study.

| Mode | Chars | Tokenizer | Mean context tokens, current → cap | p50 ms, current → cap | p95 ms, current → cap | Mean ms, current → cap |
|---|---:|---|---:|---:|---:|---:|
| Default lexical | 2,000 | cl100k_base | 484.746 → 484.695 | 9.337 → 9.355 | 15.034 → 14.989 | 9.667 → 9.723 |
| Default lexical | 2,000 | o200k_base | 482.941 → 482.547 | 10.067 → 10.065 | 15.697 → 15.607 | 10.348 → 10.332 |
| Default lexical | 8,000 | cl100k_base | 478.457 → 478.762 | 7.214 → 7.253 | 11.009 → 10.982 | 7.443 → 7.446 |
| Default lexical | 8,000 | o200k_base | 478.672 → 478.949 | 8.048 → 8.099 | 11.871 → 11.902 | 8.250 → 8.258 |
| Q2 | 2,000 | cl100k_base | 487.621 → 487.316 | 19.002 → 19.277 | 30.495 → 30.594 | 19.904 → 20.317 |
| Q2 | 2,000 | o200k_base | 486.332 → 486.254 | 19.721 → 20.143 | 30.593 → 31.934 | 20.624 → 21.249 |
| Q2 | 8,000 | cl100k_base | 477.094 → 477.391 | 16.728 → 17.453 | 25.864 → 25.989 | 17.496 → 18.010 |
| Q2 | 8,000 | o200k_base | 477.719 → 477.668 | 17.618 → 18.309 | 26.626 → 27.946 | 18.350 → 19.013 |

### Preparation and resource diagnostics

| Worker | Ingestion s | Total setup s | Setup tree RSS MiB | Query tree RSS MiB | Worker peak RSS MiB | Live state MiB |
|---|---:|---:|---:|---:|---:|---:|
| current-default | 6.266 | 6.297 | 335.48 | 248.80 | 811.00 | 35.50 |
| cap-default | 6.257 | 6.292 | 335.64 | 249.01 | 811.00 | 35.50 |
| current-q2 | 6.263 | 255.665 | 1012.52 | 1006.96 | 1034.57 | 52.83 |
| cap-q2 | 5.795 | 257.535 | 1011.11 | 1005.82 | 1033.46 | 52.83 |

RSS includes the Python evaluator, corpus and live descendants; 20 ms sampling is an observed lower bound, and shared mappings can be counted more than once. The worker peak is a separate OS high-water value. Live state includes SQLite main/WAL/SHM files before close and excludes the attempt ledger and model caches; it is not peak disk usage or pure product memory.

Current/cap Q2 model loading took 1.180/1.186 seconds and index construction took 248.186/250.518 seconds. Both built 4,566 windows over 3,769 pages, with 7,013,376 vector bytes. Index-building and ingestion code did not change. These single-pass phase observations are retained without attributing a speed effect to the ranking formula. Both lexical and semantic query-result caches remained empty.

## Final records and independent verification

The immutable [result commit `6e3fa53`](https://github.com/Afloat16/AI-Memory-Book/commit/6e3fa539ae24aaa83886294e7bc4eef374b31c6d) contains all **19 original public files**. The [checkpoint](../benchmarks/reports/novelty-cap-43220260514-1-checkpoint.json), [exact A gate](../benchmarks/results/novelty-cap-43220260514-1/A-gate.json) and [qualification decision](../benchmarks/results/novelty-cap-43220260514-1/qualification.json) agree: A is `rejected`, B is `not-run`, and no B samples or files exist.

The [independent strict verification](../benchmarks/reports/novelty-cap-43220260514-1-independent-verification.json) checks every original file, raw/summary projection, independent compressed ledger, source pin, phase axis, denominator and gate. A second read-only standard-library review independently recomputed the same per-ID/per-annotation changes without calling the original checker. All 4,096 starts and finishes match; source, scope, page projection, context-size, token-budget and token-metadata errors are zero.

Both Q2 index digests are `c3d23f4c4b8141eb5f17d7a53faf9a95af69ff3b0ada08f1685ca11c212a7ce9`, covering 4,566 vector rows and all 7,013,376 vector bytes with the same page/offset identity. This proves equality of the stored index vectors. Query embeddings were not separately recorded or compared.

The [current-control content audit](../benchmarks/reports/novelty-cap-43220260514-1-current-control-audit.json) also checks the unchanged current source against the earlier complete round-two run: **1,024 lexical and 1,024 Q2 query/configuration records** have identical context hashes, block order, completeness and evidence ranks. This does not compare full response payloads, database snapshots or timings; no timings from the two hosts are pooled.

The [qualification workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43220260514) ends with GitHub status `failure` because the registered quality-rejection exit code is 2. Export and all four scored workers exit 0, and artifact preservation succeeds. This is a completed rejection, not an infrastructure failure. The separately bound [implementation CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43220095494) passes all nine jobs.

The old LoCoMo development gain remains a valid observation under its fixed source and scope. It did not transfer to this regression qualification. Both READMEs therefore keep the previously verified default/Q2 implementation and current complete component comparison; the rejected candidate stays in these research records. No larger-budget, old-cohort-Q2, competitor, generation or performance follow-up is started for this rejected candidate.
