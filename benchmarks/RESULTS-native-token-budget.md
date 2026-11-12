# Completed native token-budget validation

The interrupted eight-stage protocol is complete. All stages passed the fixed budget, source-coordinate, tokenizer, repeated-context, unchanged-source and old-native-block preservation gates.

These are original-evidence retrieval measurements. Complete evidence is the fraction of answerable questions for which every annotated evidence span is present; it is not generated-answer accuracy.

## 512-token results

Both native policies use the same character cap, scope, five-page limit and `cl100k_base` tokenizer. The baseline returns its native cited excerpts and then uses exact whole-block first-fit packing. The candidate enforces the token limit during native assembly and can add intact original source units.

| Cohort | Questions / answerable | Character cap | Old native complete evidence | New native complete evidence | Additional complete questions | Old / new p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | 168 / 152 | 2000 | 84.21% | 92.11% | 12 | 27.510 / 97.668 |
| development-synthetic61 | 168 / 152 | 8000 | 72.37% | 85.53% | 20 | 13.442 / 45.684 |
| regression-synthetic211 | 168 / 152 | 2000 | 78.95% | 81.58% | 4 | 92.052 / 50.525 |
| regression-synthetic211 | 168 / 152 | 8000 | 68.42% | 84.21% | 24 | 13.195 / 53.650 |
| regression-synthetic509 | 168 / 152 | 2000 | 78.95% | 81.58% | 4 | 19.620 / 33.677 |
| regression-synthetic509 | 168 / 152 | 8000 | 68.42% | 84.21% | 24 | 15.772 / 44.004 |
| regression-synthetic883 | 168 / 152 | 2000 | 78.95% | 81.58% | 4 | 19.145 / 33.755 |
| regression-synthetic883 | 168 / 152 | 8000 | 68.42% | 84.21% | 24 | 12.550 / 26.448 |
| regression-synthetic1297 | 168 / 152 | 2000 | 78.95% | 81.58% | 4 | 10.633 / 20.189 |
| regression-synthetic1297 | 168 / 152 | 8000 | 68.42% | 84.21% | 24 | 7.146 / 15.305 |
| regression-public1015 | 1015 / 649 | 2000 | 48.69% | 48.84% | 1 | 8.570 / 9.978 |
| regression-public1015 | 1015 / 649 | 8000 | 65.33% | 66.41% | 7 | 7.120 / 10.076 |
| regression-authored36 | 36 / 30 | 2000 | 86.67% | 86.67% | 0 | 1.637 / 1.807 |
| regression-authored36 | 36 / 30 | 8000 | 86.67% | 86.67% | 0 | 1.644 / 1.721 |
| external-hotpot128 | 128 / 128 | 2000 | 21.88% | 21.88% | 0 | 11.516 / 12.819 |
| external-hotpot128 | 128 / 128 | 8000 | 34.38% | 35.16% | 1 | 7.873 / 9.188 |

No annotated evidence, complete questions or already-fitting baseline native blocks were lost in any measured configuration. This is a measured invariant for these cohorts; it is not a claim of perfect recall on arbitrary future archives.

## Reproducible scope and costs

Each stage evaluates character caps 2,000/8,000, token caps 512/1,024/2,048, both `cl100k_base` and `o200k_base`, and three uncached repetitions in sequential workers. Historical full-page packing at its distinct 100,000-character retrieval cap is retained separately in each full report. It must not be relabeled as the baseline's native excerpt policy.

Exact token assembly performs extra work to recover intact evidence. Its p95 can exceed plain excerpt packing. The separate development optimization compares the previous native-token implementation with the stable-prefix implementation; do not mix that speed comparison with the older no-native-token baseline in the table above. All timing samples are host-specific and use warm OS/SQLite caches.

Model summaries and embedding queries are absent from this lexical path. Ingestion is measured separately in every worker. These runs do not measure actual generated answers or native observer/compression/answer costs of competitor projects.

## Data boundaries

The synthetic seeds and LoCoMo cohort are regression data; new synthetic seeds share templates. The authored 36-case diagnostic is also previously observed. The 128 HotpotQA distractor questions were selected and hash-frozen before candidate scoring and add an independently authored external multi-hop diagnostic. This scoped sample is not broad cross-domain or full-Wikipedia validation. It becomes regression data after this run.

## Complete evidence files

Every linked summary has an adjacent `.json.gz` with all per-query source/context hashes, evidence gains/losses, category metrics and a Markdown table. The originally interrupted manifest, checkpoint and completed development result remain preserved.

- [development-synthetic61](results/native-completion-development-synthetic61.summary.json)
- [regression-synthetic211](results/native-completion-regression-synthetic211.summary.json)
- [regression-synthetic509](results/native-completion-regression-synthetic509.summary.json)
- [regression-synthetic883](results/native-completion-regression-synthetic883.summary.json)
- [regression-synthetic1297](results/native-completion-regression-synthetic1297.summary.json)
- [regression-public1015](results/native-completion-regression-public1015.summary.json)
- [regression-authored36](results/native-completion-regression-authored36.summary.json)
- [external-hotpot128](results/native-completion-external-hotpot128.summary.json)

The aggregate checks and input hashes are in [native-completion-assessment.json](reports/native-completion-assessment.json). The [completion manifest](native-completion-manifest.json) and [performance plan](experiments/native-token-performance-plan.json) specify the frozen sources and commands.


## Public and external budget curves

These native-policy curves use the 8,000-character cap. Timing includes native recall and any separate exact packing, with three uncached repetitions. Tokens include source citations and separators but exclude enclosing MCP/HTTP metadata. Full 2,000-character curves, first/repeat-pass timings and category metrics remain in each stage report and the assessment JSON.

| Cohort | Tokenizer / cap | Old / new evidence recall | Old / new complete evidence | Old / new mean context tokens | Old / new p50 ms | Old / new p95 ms | Old / new mean ms |
|---|---|---:|---:|---:|---:|---:|---:|
| regression-public1015 | cl100k_base / 512 | 61.17% / 62.18% | 65.33% / 66.41% | 444.5 / 491.9 | 5.333 / 8.020 | 7.120 / 10.076 | 5.464 / 8.089 |
| regression-public1015 | cl100k_base / 1024 | 69.54% / 69.54% | 72.88% / 72.88% | 855.5 / 861.1 | 5.572 / 6.282 | 7.392 / 8.260 | 5.787 / 6.477 |
| regression-public1015 | cl100k_base / 2048 | 69.54% / 69.54% | 72.88% / 72.88% | 867.1 / 867.1 | 5.622 / 6.096 | 7.452 / 7.967 | 5.742 / 6.274 |
| regression-public1015 | o200k_base / 512 | 62.06% / 62.82% | 65.95% / 66.72% | 446.6 / 492.7 | 6.096 / 9.661 | 7.900 / 11.994 | 6.211 / 9.673 |
| regression-public1015 | o200k_base / 1024 | 69.54% / 69.54% | 72.88% / 72.88% | 839.3 / 842.2 | 6.482 / 7.222 | 8.383 / 9.231 | 6.700 / 7.388 |
| regression-public1015 | o200k_base / 2048 | 69.54% / 69.54% | 72.88% / 72.88% | 845.0 / 845.0 | 6.537 / 7.128 | 8.484 / 8.945 | 6.638 / 7.263 |
| external-hotpot128 | cl100k_base / 512 | 66.34% / 66.99% | 34.38% / 35.16% | 451.4 / 479.4 | 5.319 / 6.584 | 7.873 / 9.188 | 5.479 / 6.706 |
| external-hotpot128 | cl100k_base / 1024 | 74.51% / 74.51% | 48.44% / 48.44% | 802.3 / 804.0 | 5.509 / 5.623 | 8.052 / 8.221 | 5.677 / 5.781 |
| external-hotpot128 | cl100k_base / 2048 | 74.51% / 74.51% | 48.44% / 48.44% | 805.8 / 805.8 | 5.634 / 5.733 | 8.219 / 8.343 | 5.781 / 5.874 |
| external-hotpot128 | o200k_base / 512 | 66.34% / 66.99% | 34.38% / 35.16% | 451.6 / 479.0 | 5.725 / 7.586 | 8.306 / 10.380 | 5.927 / 7.776 |
| external-hotpot128 | o200k_base / 1024 | 74.51% / 74.51% | 48.44% / 48.44% | 801.1 / 802.9 | 6.113 / 6.386 | 8.709 / 9.046 | 6.231 / 6.581 |
| external-hotpot128 | o200k_base / 2048 | 74.51% / 74.51% | 48.44% / 48.44% | 804.6 / 804.6 | 6.120 / 6.355 | 8.767 / 8.898 | 6.310 / 6.500 |

## Historical 512-token policy

The earlier 66.72% to 66.26% cl100k_base result used full source pages and shared whole-block packing. This continuation adds an explicit native token-assembly API; it does not change or retroactively repair that historical full-page policy. Its results remain separate below at the registered 100,000-character retrieval boundary. Do not compare its latency as though it were the native excerpt route.

| Public historical full-page policy | Token cap | Evidence recall | Complete evidence | Mean context tokens |
|---|---:|---:|---:|---:|
| cl100k_base | 512 | 62.44% | 66.26% | 447.6 |
| cl100k_base | 1024 | 69.54% | 72.88% | 827.2 |
| cl100k_base | 2048 | 69.54% | 72.88% | 832.1 |
| o200k_base | 512 | 62.94% | 66.72% | 451.5 |
| o200k_base | 1024 | 69.54% | 72.88% | 809.2 |
| o200k_base | 2048 | 69.54% | 72.88% | 810.0 |

## Import and stored archive costs

| Cohort | Source sessions / source UTF-8 bytes | Old / new import ms | Old / new database bytes | Pages |
|---|---:|---:|---:|---:|
| development-synthetic61 | 112 / 1,578,382 | 1244.6 / 1903.6 | 20,508,672 / 20,508,672 | 1,912 |
| regression-synthetic211 | 112 / 1,578,520 | 4685.0 / 1356.2 | 20,496,384 / 20,496,384 | 1,912 |
| regression-synthetic509 | 112 / 1,578,474 | 1177.7 / 1181.6 | 20,496,384 / 20,496,384 | 1,912 |
| regression-synthetic883 | 112 / 1,578,625 | 1065.4 / 1061.4 | 20,475,904 / 20,475,904 | 1,912 |
| regression-synthetic1297 | 112 / 1,578,584 | 866.0 / 832.3 | 20,496,384 / 20,496,384 | 1,912 |
| regression-public1015 | 216 / 617,094 | 1470.7 / 1503.2 | 12,881,920 / 12,881,920 | 1,339 |
| regression-authored36 | 42 / 7,735 | 64.6 / 30.6 | 344,064 / 344,064 | 42 |
| external-hotpot128 | 1272 / 694,666 | 1982.8 / 2053.9 | 16,625,664 / 16,625,664 | 1,915 |

Database size is the engine's reported on-disk snapshot after ingestion, not peak RAM or total deployment size. Each import is one measured pass and can vary with filesystem and host scheduling. Peak memory, CPU energy and provider monetary bills were not measured. The preserved tokenizer-startup report measures a separate boundary; query timing here pre-initializes both encodings and is not tokenizer-cold latency.

## Recovery provenance and reproduction

The baseline source is 5abc85eef00097555366f8524fc81f8b5711ad7a; the native-token candidate is 407cda1c5f1dac0e67dfe527d3c23febdad5e818. Semantic recall and clause coverage are disabled. Every raw report, summary and Markdown file must match a completed checkpoint before aggregation. The three earlier completed cohorts remain unchanged. Freshly recovered jobs keep separate host/process identities and the same registered cohort, source, evaluator, budget and repetition settings. Baseline and candidate are sequential workers inside each cohort; timing samples are never pooled across jobs or earlier hosts.

Run the original full manifest with a new checkpoint after preparing its verified data and source worktrees. Alternatively, run each unchanged stage in its own manifest/job and supply all resulting checkpoint files plus the original completed-stage checkpoints to the summarizer:

```bash
export TIKTOKEN_CACHE_DIR="$PWD/.artifacts/tiktoken"
python -m benchmarks.resume --manifest benchmarks/native-completion-manifest.json \
  --checkpoint .artifacts/native-fresh-checkpoint.json
python scripts/summarize_native_completion.py \
  --checkpoints .artifacts/native-fresh-checkpoint.json
```
