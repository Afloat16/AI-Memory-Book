# Round two: optimization and independent comparison

Status: in progress. The stable main branch remains `cb7486b4937a3ecb7ccbf94a746c0bbbf44eb41f` until the chosen implementation, complete measurements and final CI are verified.

## Objective and acceptance

Improve retrieval quality, latency, preparation cost, memory and returned tokens. Use the same source corpus, tokenizer, budgets and repetition policy within each comparison. Keep native interface costs separate from common-context retrieval quality. Retain failed candidates and negative results; a component measurement does not establish that a whole product wins every workload.

README should present the current recommended implementation and its latest verified advantages. Historical runs, full curves, failures and operating boundaries belong in the detailed reports.

## Durable checkpoints

| Track | Saved source / result | Current evidence |
|---|---|---|
| Default lexical performance | [`841cedb0`](https://github.com/Afloat16/AI-Memory-Book/commit/841cedb0cc52ff2b199e7c24832b64973a2e306d) | Equivalent ASCII tokenization, whole-string Unicode normalization with fewer repeated category checks, per-excerpt character fold reuse, per-session directory indexing |
| Performance execution | [Run 43194664986](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43194664986), raw result [`558bac1`](https://github.com/Afloat16/AI-Memory-Book/commit/558bac1) | All 56,784 timed calls and payload/source/index checks completed. The dictionary-order audit issue was repaired and the same raw measurement passed [independent audit 43196379004](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43196379004), with zero new retrieval calls. [Full performance report](default-recall-performance.md). |
| Q1 semantic score fusion | [`82d10914`](https://github.com/Afloat16/AI-Memory-Book/commit/82d10914), [run 43194168722](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43194168722) | Complete old-data development matrix. Improves several conversation cohorts; regresses on old HotpotQA. Not promoted as a universal replacement. |
| Q2 lexical anchor | [`6286564e`](https://github.com/Afloat16/AI-Memory-Book/commit/6286564e33f09db9863a80613771722c32ba363b), [run 43196880064](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43196880064) | All 48,492 development calls completed. Aggregate complete evidence and annotation recall match or exceed the original RRF in all 12 old cohort/budget settings. Selected for the next validation as the optional semantic policy; lexical remains the default. Per-question losses, the public cross-session 512-token loss and cross-run control differences remain in the full report. |
| Indexed source references | [`27975628`](https://github.com/Afloat16/AI-Memory-Book/commit/27975628863c2b95a0bb33e2147fec35416e2ebe), [formal run 43203389371](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43203389371) | Complete 56,784-call actual-SDK measurement on the frozen integrated runtime: 7,098 distinct payload pairs and all 6,868 archived reference entries pass reversible-value checks. Default metadata remains unchanged. Public/default-budget compact response text saves 19.63% o200k tokens; full first-call reference count saves 8.15%. Every configuration, first-call loss and latency tradeoff remains in the report. The earlier per-call-parameter prototype stays separately preserved. |
| Independent comparison tools | [`d0ff8624`](https://github.com/Afloat16/AI-Memory-Book/commit/d0ff86243ceeb8064a05965214d4c08ed4d64cfd) | Frozen new cohort, separate native/common-context evaluators, strict source/ledger/metric audits and workflow. Candidate binding is deliberately absent until development selection finishes. |
| Current upstream registration | [`d8126b6`](https://github.com/Afloat16/AI-Memory-Book/commit/d8126b6ff6c14220799377035565904f81d60248) | claude-mem 15.18.1 and current billion-context kernel, verified source pins and fictional scope smoke; ai-memory latest published release remains v3.4.5. Historical locks remain unchanged. |

## New cohort boundary

The independently authored HotpotQA diagnostic contains 256 questions, excludes every ID in the previously inspected 128-question cohort, and includes all 2,539 supplied paragraphs and 614 required support facts. Its ID digest is `912e3c8d0f26f1a247de321709a9528e76d08f8ad70f9d7c9169b97c638be11a`; its converted dataset digest is `19aa783140212cc6532581c2791e6384769b0647dd4f08e2db29687400a798ae`.

The source IDs, sampling policy and measurement matrix were saved at [`87e28c09`](https://github.com/Afloat16/AI-Memory-Book/commit/87e28c0977cf572f87fcf88181d88b55185360be) before candidate scoring. Algorithm development uses only the old synthetic, authored, public-conversation and original Hotpot cohorts. The new cohort is evaluated after the candidate source and protocol hashes are frozen. After that first evaluation it becomes regression evidence, not a new tuning set with an untouched label.

All cases are answerable and use supplied distractor paragraphs. This adds independent multi-hop evidence; it does not cover unrestricted Wikipedia retrieval, abstention, all domains or generated-answer accuracy.

## Preservation and next gate

Source, plans and completed result files are saved in Git; hosted jobs write public, source-free measurements to separate result branches. Model weights and licensed raw conversations remain outside the repository. An interrupted run must retain its attempt state and completed samples. Report-only audit fixes must re-use the saved raw observations, rather than selecting a new faster run.

The selected source combines the exact-output lexical optimization, optional Q2 semantic fusion and opt-in indexed MCP references. It was frozen at [`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba), runtime SHA-256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`. The original binding was separately committed at [`364d8d4`](https://github.com/Afloat16/AI-Memory-Book/commit/364d8d4b7013c8c22ff06285d2bce969c7965717) before scoring; its [standard CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43201620625) passed all nine jobs.

Independent code review found no blocking source-preservation, offset, cache or default-compatibility issue. The integrated real MCP, lifecycle and token-budget checks passed (21 tests). One existing subprocess test needed explicit forwarding of a preloaded tokenizer-cache directory to run offline; its original budget/input assertions remain unchanged.

### First attempt and explicit recovery

[Run 43201620535](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43201620535) completed export, both lexical native stages and both Book component stages. Its first claude-mem query then failed in the evaluator: that adapter returns rows in `native_payload`, while the common evaluator accessed a nonexistent `results` field. A `dict.get` fallback also eagerly evaluated the missing field. This is an adapter-response parsing error, not a retrieval-quality result.

The failed [checkpoint](../benchmarks/reports/round2-43201620535-1-checkpoint.json), all completed raw/summary pairs and the failed claude-mem pair are preserved in this repository and at result commit [`150d377`](https://github.com/Afloat16/AI-Memory-Book/commit/150d37799098aa1fb1ddcebe5b42b18954adc035). This incomplete run is not presented as a complete cross-project comparison.

Recovery keeps the exact candidate source, cohort, upstream locks, budgets, repetitions and optional-mode choice. The evaluator fix and a new binding must be recorded explicitly, with the original binding retained. Before another scored run, fictional data must exercise each real external component through response mapping, payload/read accounting, six budget projections and strict report verification. The complete matrix will then run on one new host under a new run identity; observations from the two hosts will not be pooled or selected by speed. The cohort is now regression data relative to any future algorithm development.

The indexed-format measurement is complete at result commit [`01191a1`](https://github.com/Afloat16/AI-Memory-Book/commit/01191a1439b9cdadd72ee31a2443ddb3bba2d9e9), with successful hosted and local audits of the same raw data. Default object responses match the original actual-SDK compact response hashes. Mean first-call savings do not imply every question saves tokens; every synthetic configuration includes first-call losses, and pooled p95 changes range from -0.88% to +0.96% across the 12 configurations. No provider billing or generated-answer claim follows from these reference counts.

Next: complete the registered comparison recovery, then update the final comparison, README and main after CI. The old complete-validation record remains valid for its own fixed source snapshot.
