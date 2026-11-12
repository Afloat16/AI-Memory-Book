# Exact-output token budget performance

The optimized token-budget assembler preserves all **2,016 complete response
payloads** in the registered development comparison. Across the four
**512-token** settings, observed p95 latency falls **7.73%–14.45%**.
The full matrix also retains three 2,048-token settings with p95 increases
of **0.50%–2.43%**; this is a targeted small-budget improvement, not a claim
that every configuration becomes faster.

Sources: [complete summary](../benchmarks/reports/native-prefix-bound-development-43183816029-1.summary.json),
[compressed raw report](../benchmarks/reports/native-prefix-bound-development-43183816029-1.json.gz),
[completion manifest](../benchmarks/reports/native-prefix-bound-completion-43183816029-1.json)
and [preregistered plan](../benchmarks/experiments/token-prefix-bound-performance-plan.json).

## What changed and why outputs remain identical

Only **src/memory_book/token_budget.py** changes among the 17 files under
src/; the other **16 source files are byte-identical** to the frozen baseline.

The ordinary token-count path uses tiktoken 0.12.0's encode_ordinary entry
point. Its [official implementation](https://github.com/openai/tiktoken/blob/0.12.0/tiktoken/core.py#L63-L77)
documents equivalence to encode(text, disallowed_special=()), including
literal special-token strings and the same surrogate repair.

The prepared prefix counter also exposes its certified stable-token count
as a conservative lower bound. Its existing exact calculation is
stable_count + count(tail + candidate). Since the second term is nonnegative,
a stable count already greater than the budget proves that all remaining
candidates on that page will fail. Both UTF-8-tail and byte-prefix fallbacks
expose a zero lower bound and retain full-context counting.

The first candidate still receives a full count. Prefix preparation still
occurs only at index 1 when there are more than three candidates; equality
with the budget does not prune. Ranking, the 96-candidate limit, character and
token caps, source coordinates, citations and preservation of already accepted
blocks remain unchanged.

## Measurement scope and validation

This is the synthetic **seed 61 development** cohort: 168 queries, two
character caps (2,000 and 8,000), two tokenizers and three token caps
(512, 1,024 and 2,048). That produces **12 configurations and 2,016 unique
query/configuration comparisons**. Each engine executes three repetitions,
or **6,048 timed recalls per engine**, with 504 samples in every timing row.

The unchanged [verification script](../scripts/verify_native_optimization.py)
runs the baseline and optimized engine in separate, sequential processes on
the **same independent GitHub Actions VM**, baseline first. It initializes
tokenizers before timed queries, disables result caching and retains the
original deterministic query shuffle. OS and SQLite caches warm naturally;
these are not cold-cache or production-concurrency measurements. Database
ingestion is recorded separately from recall timing.

The runner used Python 3.12.16, SQLite 3.45.1 and pinned tiktoken 0.12.0 on
Linux x86-64 (the workflow selects ubuntu-24.04). All complete payload hashes
match after excluding only latency_ms. Repeated payloads also match.
Both source trees remain unchanged during execution, have source_dirty=false,
and have commit_identifies_source=true.

[The dedicated workflow passed](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43183816029),
including the focused token tests, source-change guard, complete equivalence
matrix and saved-report audit. [Ordinary CI also passed](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43183816003).
Nine added tests cover encoding equivalence, Unicode joins, both conservative
fallbacks, lazy preparation, legacy preservation, strict-bound comparison
and the unchanged candidate limit.

## All 12 timing configurations

Values are baseline → optimized, in milliseconds. Negative p95 change means
lower observed latency. Every configuration and all three regressions are
included.

| Character cap | Tokenizer | Token cap | p50 ms, baseline → optimized | p95 ms, baseline → optimized | p95 change | Mean ms, baseline → optimized |
|---:|---|---:|---:|---:|---:|---:|
| 2,000 | cl100k_base | 512 | 11.295 → 10.538 | 34.035 → 29.259 | -14.03% | 14.370 → 12.857 |
| 2,000 | cl100k_base | 1,024 | 10.911 → 10.257 | 29.370 → 26.781 | -8.82% | 12.838 → 11.803 |
| 2,000 | cl100k_base | 2,048 | 8.484 → 8.291 | 20.129 → 19.393 | -3.65% | 10.114 → 9.831 |
| 2,000 | o200k_base | 512 | 11.746 → 11.213 | 32.642 → 27.924 | -14.45% | 14.796 → 13.167 |
| 2,000 | o200k_base | 1,024 | 10.267 → 10.233 | 25.585 → 24.854 | -2.86% | 11.972 → 11.706 |
| 2,000 | o200k_base | 2,048 | 8.905 → 9.123 | 20.367 → 20.862 | +2.43% | 10.493 → 10.717 |
| 8,000 | cl100k_base | 512 | 11.791 → 11.069 | 25.741 → 23.221 | -9.79% | 13.009 → 12.392 |
| 8,000 | cl100k_base | 1,024 | 9.860 → 9.513 | 27.733 → 24.438 | -11.88% | 11.732 → 10.755 |
| 8,000 | cl100k_base | 2,048 | 8.199 → 8.332 | 21.969 → 22.080 | +0.50% | 9.721 → 9.922 |
| 8,000 | o200k_base | 512 | 13.215 → 12.727 | 26.965 → 24.880 | -7.73% | 14.516 → 13.863 |
| 8,000 | o200k_base | 1,024 | 10.038 → 10.377 | 27.390 → 26.631 | -2.77% | 12.166 → 12.157 |
| 8,000 | o200k_base | 2,048 | 8.628 → 8.939 | 24.917 → 25.437 | +2.09% | 10.378 → 10.578 |

p95 and mean latency improve in **9 of 12** configurations; p50 improves in
8 of 12. At 512 tokens, p50, p95 and mean all improve in all four settings.
The three regressing 2,048-token rows have mean increases of 1.93%–2.13%.
The 8,000-character / o200k_base / 1,024-token row has a 3.38% higher p50,
despite its lower p95 and nearly unchanged mean.

Because every configuration has the same sample count, the mean across each
engine's 6,048 timed calls is **12.175 → 11.646 ms**, a **4.35% decrease**.
This is an overall mean, not an average presented as an overall percentile.

These are observations from one host with a fixed engine order and three
repetitions, without a confidence interval or a causal breakdown between the
two implementation changes. They support the measured development-set
small-budget improvement. They do not supply new latency results for public
LoCoMo, synthetic seed 883 or the external transfer cohorts.

## Source and report identity

| Item | Identity |
|---|---|
| Frozen runtime baseline | 407cda1c5f1dac0e67dfe527d3c23febdad5e818 |
| Measured optimized checkout | e8a878ec2d8c4b0930e9a5cff20ce954f7ac6818 |
| Saved result commit | [8bd93dab5522f45a30be1fcfdac8da21720dc317](https://github.com/Afloat16/AI-Memory-Book/commit/8bd93dab5522f45a30be1fcfdac8da21720dc317) |
| Baseline runtime SHA-256 | 63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625 |
| Optimized runtime SHA-256 | 6fdad7b9bf0eef50ec925ceeed3ca45fe84d2eb22973c753118df2d0f67f6ba2 |
| Dataset SHA-256 | 117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26 |
| Raw report, decompressed JSON SHA-256 | e68aba13a89ca3b8ce0c2d777690ceb1cf405e1a2a16432149c25bf44ac1e0c9 |
| Compressed report SHA-256 | d57dae3513fa6e216780b9729b995d1ab89013ed83caf79407c0799c51183a41 |
| Summary SHA-256 | cffd1dc82526d188003e2a08dc29aebf0be91d7ca2f6d7f2ffe42fb866310695 |

## Reproduce the registered comparison

Use a new pair of worktree paths and a new output label for every attempt.
The script refuses to overwrite an existing result. Run from a checkout of
this repository on an otherwise idle worker with Python 3.12:

~~~bash
git fetch origin 407cda1c5f1dac0e67dfe527d3c23febdad5e818 e8a878ec2d8c4b0930e9a5cff20ce954f7ac6818
mkdir -p .artifacts
git worktree add --detach .artifacts/prefix-bound-baseline 407cda1c5f1dac0e67dfe527d3c23febdad5e818
git worktree add --detach .artifacts/prefix-bound-candidate e8a878ec2d8c4b0930e9a5cff20ce954f7ac6818
python -m pip install -e ".artifacts/prefix-bound-candidate[benchmark]"

reproduction_id=local-check-1
python .artifacts/prefix-bound-candidate/scripts/verify_native_optimization.py \
  --baseline-src .artifacts/prefix-bound-baseline/src \
  --candidate-src .artifacts/prefix-bound-candidate/src \
  --repeats 3 \
  --output "benchmarks/reports/native-prefix-bound-reproduction-$reproduction_id.json.gz"
~~~

The output contains payload hashes and timing statistics, not source passages.
The same prefix also receives a summary JSON file. A passing equivalence gate
establishes matching measured outputs; retain every timing row even when a
repeat experiment shows no speed gain or a regression.
