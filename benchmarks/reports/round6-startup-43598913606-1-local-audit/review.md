# Independent startup review: v0.3.4 candidate A

**Recommendation: accept the disclosed startup resource tradeoff.** The original numeric gates pass. The saved automatic result remains `accepted=false`, and the workflow remains `failure`, because one resource mean increased by more than 10%. No measurement, threshold, source, or original report was changed.

This is a startup and atomic-initialization release judgment. The original recall 10% / 15% / 10% gates remain unchanged, unpassed, and formally unrun. Candidate B is excluded. Final fresh-comparison, CI, package and public-install checks remain separate requirements.

## Verified evidence

- Unique startup run: [43598913606](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43598913606), first attempt, trigger `c3ffaa4d5b158148471516fe72f7253ef7b89f9c`.
- Original result commit: `ffcc0a6f01b3b4acdf755ecd4c01b1e564d279b6`. All eight original Git blobs, lengths and completion SHA-256 entries verified before reading measurements.
- Frozen evaluator: `2981df099893708b062934770905f07f47b34d98`; binding SHA-256 `c968ab50f2f5e153954983046e0cbcdadf122515d8736832acdb8687121a4c88`.
- Baseline v0.3.3: `796cedfd1f5368144037a1fb72292b8d13884b8c`; candidate A: `df35007c29e4af61dd96146232fe4651cfc74391`, runtime `f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242`.
- The frozen independent auditor recomputed all 480 observations, 960 events, timers, statistics, resources, gates and adverse cells from saved records. Source/evaluator/plan/binding Git identity, help/version, empty archive state and actual official-SDK metadata passed. Its local output is byte-identical to the remote audit (SHA-256 `e6b28455e3fb8f770ff1353ecaadcbd174cff102bfe319012114a0f40e9938c9`).
- No new product process, server, benchmark timing or rerun was used for this review.

Primary evidence: [original report](../round6-startup-43598913606-1/report.json.gz), [original ledger](../round6-startup-43598913606-1/attempts.jsonl.gz), [original completion](../round6-startup-43598913606-1/completion.json), [local verification](verification.json), [recomputed audit](independent-audit.json), and [full review data](review.json).

## Six startup boundaries

Forty observations per source and boundary, in the registered four rounds (AB, BA, BA, AB); no samples excluded. All times below are milliseconds. Change is candidate minus baseline, so negative values are improvements.

| Boundary | Baseline median | Candidate median | Median change | Baseline p95 | Candidate p95 | p95 change |
|---|---:|---:|---:|---:|---:|---:|
| `cli-help` | 102.902619 | 48.749533 | -52.625567% | 104.103962 | 49.546675 | -52.406542% |
| `cli-version` | 101.345546 | 47.478763 | -53.151604% | 103.116280 | 48.259182 | -53.199260% |
| `api-import` | 33.506216 | 33.920427 | +1.236220% | 33.821928 | 34.432927 | +1.806515% |
| `api-new` | 24.517632 | 4.163528 | -83.018227% | 27.373841 | 6.358100 | -76.773082% |
| `api-existing` | 0.640361 | 0.632477 | -1.231181% | 0.667592 | 0.665576 | -0.302078% |
| `mcp-initialize` | 627.601162 | 620.104423 | -1.194507% | 632.233029 | 624.837497 | -1.169748% |

New-archive median decreases by 20.354104 ms; CLI help by 54.153086 ms; CLI version by 53.866784 ms. Each passes its registered median, p95 and absolute-reduction target. The complete API import is slightly slower: median +0.414211 ms and p95 +0.610998 ms. All six secondary median/p95 guards pass without changing their rules.

CLI measurements are real `python -m memory_book --help/--version` process wall times. API import includes `from memory_book import MemoryBook`; the cheap package-only lazy import is not substituted. Constructor timers exclude helper verification. MCP timing uses a fresh official SDK connection through successful initialization.

## The resource flag and its cause assessment

The sole pooled resource flag is `api-existing / process.system_cpu_s`: **18.646175 → 21.120575 ms**, an increase of **2.474400 ms (+13.270282%)**. All four round means increase, including both source orders; treating this as a discarded outlier or established random noise would be unsupported.

| Round | Order | Baseline system CPU (ms) | Candidate system CPU (ms) | Increase (ms) | Increase |
|---|---|---:|---:|---:|---:|
| 1 | AB | 18.386800 | 20.899600 | 2.512800 | 13.666326% |
| 2 | BA | 17.201200 | 19.589000 | 2.387800 | 13.881590% |
| 3 | BA | 18.310600 | 20.989700 | 2.679100 | 14.631416% |
| 4 | AB | 20.686100 | 23.004000 | 2.317900 | 11.205109% |

The recorded resource interval covers the complete helper child: interpreter and imports, archive snapshot reads, constructor, stats/close, JSON evidence serialization and exit. The constructor itself improves slightly (median 0.640361 → 0.632477 ms; p95 0.667592 → 0.665576 ms). Whole-helper wall time increases 138.762209 → 139.995957 ms (+1.233748 ms, +0.889110%). User CPU decreases by 1.246025 ms, leaving total user-plus-system CPU +1.228375 ms. These intervals must not be presented as interchangeable.

Static source inspection limits the attribution. In frozen A, the new atomic initialization branch is entered for a new/older schema or a missing stem guard. Every saved existing-archive sample starts from the same intact schema-3 template, so that new-schema transaction path is not executed. The schema-3 initialization SQL and schema contents remain unchanged. Request-local recall metadata reuse is not exercised in this startup matrix. The full API import path does change through lazy class resolution, and additional source is parsed with bytecode writes disabled; that establishes changed import work, not its quantitative contribution to system CPU. See the [baseline-to-A source comparison](https://github.com/Afloat16/AI-Memory-Book/compare/796cedfd1f5368144037a1fb72292b8d13884b8c...df35007c29e4af61dd96146232fe4651cfc74391) and frozen `child()` / `measured_process()` in `scripts/round6_startup.py`.

No syscall profile, fault accounting or isolated compilation experiment was recorded. There is no defensible quantitative causal decomposition of this system-CPU increase. The acceptance judgment retains that uncertainty and the measured cost. It accepts an approximately 1.23 ms whole-helper wall increase and 2.47 ms additional system CPU for existing-archive startup alongside the much larger confirmed CLI and fresh-archive improvements, with unchanged protocol outputs and archive state. It does not establish any latency or memory advantage for arbitrary applications.

## Every pooled adverse result

The complete machine-readable review retains **6 pooled timing cells, 26 round timing cells, 9 pooled resource cells, and 27 round resource cells**. These are all increases, including those below review thresholds. Counts represent metric cells, not failed samples.

| Boundary | Timing metric | Absolute increase (ms) | Increase |
|---|---|---:|---:|
| `api-import` | `mean_ms` | 0.495365 | 1.478490% |
| `api-import` | `median_ms` | 0.414211 | 1.236220% |
| `api-import` | `p95_ms` | 0.610998 | 1.806515% |
| `api-import` | `min_ms` | 0.436291 | 1.319243% |
| `api-import` | `max_ms` | 1.447914 | 4.238045% |
| `api-existing` | `max_ms` | 0.031711 | 4.718829% |

| Boundary | Pooled resource metric | Baseline → candidate | Absolute increase | Increase |
|---|---|---:|---:|---:|
| `api-import` | `process.system_cpu_s` | 18.726550 → 19.575675 ms | 0.849125 ms | 4.534338% |
| `api-import` | `process.max_rss_bytes` | 50402713.600000 → 50425651.200000 bytes | 22937.600000 bytes | 0.045509% |
| `api-new` | `process.user_cpu_s` | 120.769850 → 121.287875 ms | 0.518025 ms | 0.428936% |
| `api-new` | `process.max_rss_bytes` | 50647142.400000 → 50684211.200000 bytes | 37068.800000 bytes | 0.073190% |
| `api-existing` | `process.wall_ms` | 138.762209 → 139.995957 ms | 1.233748 ms | 0.889110% |
| `api-existing` | `process.system_cpu_s` | 18.646175 → 21.120575 ms | 2.474400 ms | 13.270282% |
| `api-existing` | `process.max_rss_bytes` | 54265651.200000 → 54285209.600000 bytes | 19558.400000 bytes | 0.036042% |
| `mcp-initialize` | `process.system_cpu_s` | 101.166400 → 102.880175 ms | 1.713775 ms | 1.694016% |
| `mcp-initialize` | `details.server_sample.system_cpu_s` | 40.500000 → 42.750000 ms | 2.250000 ms | 5.555556% |

The complete per-round negative lists, including the API-import round-4 system-CPU +13.860602% and MCP sampled-server round-1 system-CPU +15%, remain in `review.json` and the original report. The original pooled resource rule is unchanged; those per-round values were not silently promoted into, or removed from, its threshold. API new/existing archive bytes are 159,744 for both sources.

## Practical limits

This is one fixed Linux/Python host and a descriptive acceptance study, not a statistical-significance or universal-performance claim. OS caches evolved naturally. The kernel `wait4` maximum-RSS records are not isolated post-exec product memory measurements: the CLI values are identical within each two-source round and rise across rounds. They remain intact, and do not support a claim of equal or reduced product memory. MCP server RSS/HWM and CPU are explicitly a live procfs sample after initialize; they are not unobserved whole-lifetime maxima or totals.

The saved automatic rejection is intentional evidence of the resource-review requirement. Independent acceptance of this disclosed cost permits the remaining release gates to proceed; it never changes the original startup or recall result fields.
