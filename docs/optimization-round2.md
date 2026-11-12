# Round two: optimization and independent comparison

Status: implementation and registered measurements complete. The selected runtime is `cbf626037b42f11f8bc5b6d46f56caac771e54ba`, source SHA-256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`. Publication retains this tested runtime and the complete results; final integration is gated by ordinary CI. This is a measured improvement release, not a claim to lead every repository on every metric.

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
| Independent comparison tools | [`d0ff8624`](https://github.com/Afloat16/AI-Memory-Book/commit/d0ff86243ceeb8064a05965214d4c08ed4d64cfd), recovery binding [`cb64db8`](https://github.com/Afloat16/AI-Memory-Book/commit/cb64db805f8f822fee00cc453c523cfa06c2ce8f) | Frozen cohort, separate native/common-context evaluators and strict source/ledger/metric audits. The candidate was bound before scoring; the explicit interface-only recovery retains that source and every registered setting. |
| Current upstream registration | [`d8126b6`](https://github.com/Afloat16/AI-Memory-Book/commit/d8126b6ff6c14220799377035565904f81d60248) | claude-mem 15.18.1 and current billion-context kernel, verified source pins and fictional scope smoke; ai-memory latest published release remains v3.4.5. Historical locks remain unchanged. |

## New cohort boundary

The fixed 256-question selection from the official HotpotQA distractor validation set excludes every ID in the previously inspected 128-question cohort and includes all 2,539 supplied paragraphs and 614 required support facts. Its ID digest is `912e3c8d0f26f1a247de321709a9528e76d08f8ad70f9d7c9169b97c638be11a`; its converted dataset digest is `19aa783140212cc6532581c2791e6384769b0647dd4f08e2db29687400a798ae`.

The source IDs, sampling policy and measurement matrix were saved at [`87e28c09`](https://github.com/Afloat16/AI-Memory-Book/commit/87e28c0977cf572f87fcf88181d88b55185360be) before candidate scoring. Algorithm development uses only the old synthetic, authored, public-conversation and original Hotpot cohorts. The new cohort is evaluated after the candidate source and protocol hashes are frozen. After that first evaluation it becomes regression evidence, not a new tuning set with an untouched label.

All cases are answerable and use supplied distractor paragraphs. This adds independent multi-hop evidence; it does not cover unrestricted Wikipedia retrieval, abstention, all domains or generated-answer accuracy.

## Preservation and completed gates

Source, plans and completed result files are saved in Git; hosted jobs write public, source-free measurements to separate result branches. Model weights and licensed raw conversations remain outside the repository. An interrupted run must retain its attempt state and completed samples. Report-only audit fixes must re-use the saved raw observations, rather than selecting a new faster run.

The selected source combines the exact-output lexical optimization, optional Q2 semantic fusion and opt-in indexed MCP references. It was frozen at [`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba), runtime SHA-256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`. The original binding was separately committed at [`364d8d4`](https://github.com/Afloat16/AI-Memory-Book/commit/364d8d4b7013c8c22ff06285d2bce969c7965717) before scoring; its [standard CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43201620625) passed all nine jobs.

Independent code review found no blocking source-preservation, offset, cache or default-compatibility issue. The integrated real MCP, lifecycle and token-budget checks passed (21 tests). One existing subprocess test needed explicit forwarding of a preloaded tokenizer-cache directory to run offline; its original budget/input assertions remain unchanged.

### First attempt and explicit recovery

[Run 43201620535](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43201620535) completed export, both lexical native stages and both Book component stages. Its first claude-mem query then failed in the evaluator: that adapter returns rows in `native_payload`, while the common evaluator accessed a nonexistent `results` field. A `dict.get` fallback also eagerly evaluated the missing field. This is an adapter-response parsing error, not a retrieval-quality result.

The failed [checkpoint](../benchmarks/reports/round2-43201620535-1-checkpoint.json), all completed raw/summary pairs and the failed claude-mem pair are preserved in this repository and at result commit [`150d377`](https://github.com/Afloat16/AI-Memory-Book/commit/150d37799098aa1fb1ddcebe5b42b18954adc035). This incomplete run is not presented as a complete cross-project comparison.

Recovery keeps the exact candidate source, cohort, upstream locks, budgets, repetitions and optional-mode choice. The [explicit registration](../benchmarks/round2_recovery.json), original binding bytes, helper diff, failed first fixture and successful second fixture are saved. Each of the three real external adapters passed two invented scoped questions, three repetitions, six budget projections and strict response/source/payload/read verification before another scored run. No source check or scoring formula was relaxed.

The recovery binding at [`cb64db8`](https://github.com/Afloat16/AI-Memory-Book/commit/cb64db805f8f822fee00cc453c523cfa06c2ce8f) fixes all 58 evaluator files and the original runtime. Its [ordinary CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43207565883) passed all nine jobs. [Run 43207732852](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43207732852) completed all 10 stages and strict assessment on one new host. All **32,256 timed calls** and **23 final files** are saved at [`057b814`](https://github.com/Afloat16/AI-Memory-Book/commit/057b814ab809dec57d4fa4c75fe540d59a0f0027). Observations from the two hosts are not pooled or selected by speed. The cohort is now regression data relative to any future algorithm development.

The indexed-format measurement is complete at result commit [`01191a1`](https://github.com/Afloat16/AI-Memory-Book/commit/01191a1439b9cdadd72ee31a2443ddb3bba2d9e9), with successful hosted and local audits of the same raw data. Default object responses match the original actual-SDK compact response hashes. Mean first-call savings do not imply every question saves tokens; every synthetic configuration includes first-call losses, and pooled p95 changes range from -0.88% to +0.96% across the 12 configurations. No provider billing or generated-answer claim follows from these reference counts.

The [independent strict verification](../benchmarks/reports/round2-recovery-independent-verification.json) confirms all file hashes and reproduces the exact report and assessment except its audit timestamp. Root separately recomputed all four paired comparison sets and the report without modifying any original file. The [cost audit](../benchmarks/reports/round2-43207732852-1-component-cost-audit.md) passes 1,536 first-pass cost records across six components. The [cross-run audit](round2-recovery-audit.md) preserves zero differences in 9,216 query/configuration rows and 19,968 repeated non-timing samples, but records five copies of one differing full original-store snapshot hash as `completed_with_differences`. Automatic write-time metadata is a plausible explanation; the retained public evidence does not prove it is the only cause.

## Current decisions and remaining limits

- The default lexical path preserves all 3,072 native contexts and improves p50/p95 in every current native configuration. Its measured source ingestion falls from 6.550 to 4.884 seconds. The separately balanced old-data performance report remains the broader latency evidence.
- Q2 is optional. In the 1,024-cl100k shared-page view it reaches 57.81% complete evidence, ahead of claude-mem FTS (48.83%) and ai-memory (53.91%), below billion-context (61.72%). The native API uses different packing and reaches 57.42% at 8,000 characters. The complete comparison includes all budgets and interfaces.
- The small-budget limit remains real: at native 8,000 characters / 512 o200k tokens, Q2 changes completeness from 42.19% to 41.02%. The older 66.72% to 66.26% LoCoMo whole-page regression remains an unchanged historical observation, not relabeled as this native-budget experiment.
- The latest low-overlap group has only nine questions. Paragraph-to-session/chapter mapping is a multi-source retrieval test, not private conversational transfer or unrestricted Wikipedia retrieval.
- Real generated answers and the native Book/ai-memory workflow were executed in the earlier fixed-model diagnostics. Their failures and costs remain preserved. This round does not remeasure current Q2/indexed-format answer quality or complete claude-mem/billion-context observation/compression workflows.
- Both READMEs display current configurations and the latest complete component matrix. Historical versions, unsuccessful experiments, all small-budget losses and full cost/resource boundaries stay in the detailed records.

Further ranking investigations use separate plans, source commits and old development data. They do not alter this frozen candidate or replace unfavorable rows in its report. The previous complete-validation record remains valid for its own fixed source snapshot.

## Separate bounded ranking follow-up

The [old-data novelty probe](novelty-probe.md) is complete: 12,123 actual calls,
both fixed alternatives, every budget/group/loss and the original presentation
audit failure are preserved. Removing the novelty bonus is rejected. The
0.25 cap gains three complete LoCoMo questions and three annotations at 512
tokens; the other eleven development cells have equal quality, with zero
individual evidence losses in these twelve cells. This does not establish
unchanged payloads, faster operation or generalization. The current default
and README comparison remain unchanged.

Before qualification scoring, a separate source at
[`b7d3cb9`](https://github.com/Afloat16/AI-Memory-Book/commit/b7d3cb90ce71017ebb2c34b1bf172652e1d102e4)
adds the necessary recall-cache version increment to the unchanged cap
formula. Persisted version-10 lexical and semantic results must miss after
upgrading; new results remain cacheable, original data stays unchanged and
compatible semantic vectors remain reusable. Two disk-reopen regression
tests pass, and forcing version 10 makes both fail at the expected cache-hit
check. This correction does not change the cache-disabled old probe.

The [qualification plan](../benchmarks/experiments/novelty-cap-qualification-plan.json)
and [source binding](../benchmarks/experiments/novelty-cap-qualification-binding.json)
were frozen at
[`186283d`](https://github.com/Afloat16/AI-Memory-Book/commit/186283dd0a2511b80e50ae185a03f488ac974c30)
before [run 43220260514](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43220260514),
attempt 1. The original 58 helpers remain unchanged; four new files have a
separate binding. Twelve invented workflow/gate tests and independent review
passed before scoring. Its explicit stopping rule is:
all 512-token axes first, then larger budgets only if every configuration has
zero individual complete-question and annotation losses. It uses the already
scored 256 questions as regression data. The cap is not adopted automatically;
any failed qualification is retained and stops this candidate without further
parameter tuning.

The controller saves a run checkpoint before preparation, then raw records,
summaries and a separate compressed attempt ledger after each worker. Failed
or interrupted workers retain any completed attempt records. The two Q2
workers must also have identical index vector bytes. A rejection leaves the
later phase explicitly `not-run`; it is never labeled a completed larger-budget
comparison. The [single-run result branch](https://github.com/Afloat16/AI-Memory-Book/tree/validation/novelty-cap-43220260514-1)
preserves progress while the qualification is running.
