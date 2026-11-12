# Capped novelty: strict regression qualification

**Status: the registered run is in progress. No candidate has been adopted.**
The current product remains the frozen round-two lexical default with optional
Q2 semantics. This experiment decides whether one fixed ranking change is
eligible for further compatibility and performance work.

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

The final decision and all executed configuration results will be recorded
below after the registered phase gate completes. The product default and the
README's current comparison remain unchanged during this qualification.
