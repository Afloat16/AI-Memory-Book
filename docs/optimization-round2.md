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
| Indexed-reference prototype | [`e96fca24`](https://github.com/Afloat16/AI-Memory-Book/commit/e96fca24bf80f38d0aa857a2ea11c8037a79a1ae), [run 43199279247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43199279247) | Complete reversible projection and token-cost prototype. Proceed with an explicit MCP server startup option, keeping the default tool schema, instructions and response unchanged. The implementation and actual SDK measurement must pass before its costs become a product claim. |
| Independent comparison tools | [`d0ff8624`](https://github.com/Afloat16/AI-Memory-Book/commit/d0ff86243ceeb8064a05965214d4c08ed4d64cfd) | Frozen new cohort, separate native/common-context evaluators, strict source/ledger/metric audits and workflow. Candidate binding is deliberately absent until development selection finishes. |
| Current upstream registration | [`d8126b6`](https://github.com/Afloat16/AI-Memory-Book/commit/d8126b6ff6c14220799377035565904f81d60248) | claude-mem 15.18.1 and current billion-context kernel, verified source pins and fictional scope smoke; ai-memory latest published release remains v3.4.5. Historical locks remain unchanged. |

## New cohort boundary

The independently authored HotpotQA diagnostic contains 256 questions, excludes every ID in the previously inspected 128-question cohort, and includes all 2,539 supplied paragraphs and 614 required support facts. Its ID digest is `912e3c8d0f26f1a247de321709a9528e76d08f8ad70f9d7c9169b97c638be11a`; its converted dataset digest is `19aa783140212cc6532581c2791e6384769b0647dd4f08e2db29687400a798ae`.

The source IDs, sampling policy and measurement matrix were saved at [`87e28c09`](https://github.com/Afloat16/AI-Memory-Book/commit/87e28c0977cf572f87fcf88181d88b55185360be) before candidate scoring. Algorithm development uses only the old synthetic, authored, public-conversation and original Hotpot cohorts. The new cohort is evaluated after the candidate source and protocol hashes are frozen. After that first evaluation it becomes regression evidence, not a new tuning set with an untouched label.

All cases are answerable and use supplied distractor paragraphs. This adds independent multi-hop evidence; it does not cover unrestricted Wikipedia retrieval, abstention, all domains or generated-answer accuracy.

## Preservation and next gate

Source, plans and completed result files are saved in Git; hosted jobs write public, source-free measurements to separate result branches. Model weights and licensed raw conversations remain outside the repository. An interrupted run must retain its attempt state and completed samples. Report-only audit fixes must re-use the saved raw observations, rather than selecting a new faster run.

Next: finish and verify the explicit indexed-reference implementation, freeze one candidate with optional Q2 semantics enabled as a separately reported stage, execute the registered independent matrix once, then update the final comparison, README and main after CI. The old complete-validation record remains valid for its own fixed source snapshot.
