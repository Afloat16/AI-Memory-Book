# Optional indexed source references

An operator can configure the MCP server to encode repeated source identities
in one response-wide session table. The default `objects` format retains the
existing tool schemas, initialization instructions and response serialization.
The indexed mode preserves the original context, page IDs, warnings and every
source-reference field. It does not change retrieval or the evidence budget.

## Enable the format explicitly

```sh
memory-book mcp --source-format indexed
```

For a manually configured MCP client, append the option to the existing `mcp`
arguments, for example:

```json
{
  "command": "memory-book",
  "args": ["--db", "/absolute/path/memory.db", "mcp", "--source-format", "indexed"]
}
```

Python operators can pass `source_format="indexed"` to
`memory_book.mcp_server.create_server()` or its `serve()` helper. The HTTP reader's
`serve` command and generated client configurations remain unchanged.

The choice is fixed for the server connection. There is no new `recall_memory`
tool argument. Indexed initialization instructions explain the representation
to the connected agent; object-mode clients receive the existing instructions.

## Decode a reference

An indexed recall response adds `"source_format": "indexed-v1"` and a
`source_sessions` table. Each table row is `[project, session_id]`. Each
`source_refs` entry contains a zero-based table index and the original turn
index; detailed references retain all other fields in a third object.

```json
{
  "source_format": "indexed-v1",
  "source_sessions": [["project-a", "session-7"]],
  "results": [
    {"id": "page-example", "source_refs": [[0, 3, {"start": 10, "end": 24, "turn_start": 30, "turn_end": 44}]]}
  ]
}
```

This example shows only the reference-related fields. Expanding its reference
produces `project="project-a"`, `session_id="session-7"`, `turn_index=3`, and all
four original offsets. Additional fields such as role, message indices and
timestamps remain in the third object when present. Compact references have two
array entries because the established compact projection contains only the
three identity fields. `details=true` retains the existing detailed projection
before encoding.

Project and session ID together identify a table row, so identical session names
in different projects stay separate. Reference order and detailed duplicates
are preserved. Empty responses still declare `indexed-v1` with an empty table.
`read_page` continues to return object references in either server mode.

## Cost boundary

Default clients incur no added schema or initialization-instruction cost.
Indexed clients receive extra decoding instructions, which must be included in
first-call cost accounting. Tool schemas and tool arguments are identical in
both modes. A response with few references, including an empty response, can
cost more after adding the table and version marker. The representation is an
explicit choice, not a guarantee of savings for every call.

The [per-call-argument prototype](../benchmarks/experiments/indexed-references-prototype-plan.json) is a historical experiment that motivated the operator-only design. Its added tool-schema and per-call argument costs do not describe the final interface. The following formal evaluation uses the final startup option, actual SDK metadata and the frozen integrated runtime.

## Formal operator evaluation

The opt-in MCP connection format is a lossless transport choice. This measurement compares `objects` and `indexed` on the same frozen integrated runtime using actual official-SDK stdio calls. Default clients keep the previous tool schemas, instructions and compact response bytes. Indexed clients receive a session table and decoding instructions; no retrieval ranking, context, provenance field or budget is removed.

**Complete run:** 56,784 calls, 16 sequential workers, four balanced-order rounds, all 12 configurations, and 7,098 distinct query/budget/details payload pairs. Every original stored reference was also checked, including pages never returned by retrieval. The full matrix and the independent saved-report audit passed.

For public1015 at the default 4,000-character compact setting, `o200k_base`
response text falls from **1,464.844 to 1,177.237 tokens (19.63% fewer)**. Including
the complete measured metadata, arguments and the indexed-only decoding
instructions, the first-call text total falls from **2,620.986 to 2,407.379
(8.15% fewer)**. The SDK envelope falls from 1,546.255 to 1,252.777 tokens.
The corresponding p95 changes from **7.1257071 to 7.1311244 ms**, an increase of
0.0054173 ms (0.0760%); this setting is a token reduction with nearly unchanged
measured tail latency, not a latency improvement claim.

The smaller synthetic results have a weaker tradeoff. At 2,000 characters with
details, the mean first-call saving is only **4.095 text tokens / 2.482 envelope
tokens** under `o200k_base`, and **10.185 / 1.756** under `cl100k_base`. Many
individual synthetic questions cost more after adding the table and decoding
instructions. Across all 12 settings, pooled p95 changes range from **−0.8830%
to +0.9594%**. All individual losses and all four rounds are retained below.

## Source and evidence

- Runtime: [`cbf626037b42f11f8bc5b6d46f56caac771e54ba`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba); Python source SHA-256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`.
- Format implementation: [`2797562`](https://github.com/Afloat16/AI-Memory-Book/commit/27975628863c2b95a0bb33e2147fec35416e2ebe). The integrated `cli.py` and `mcp_server.py` are byte-identical to that tested implementation. Optional semantic changes present in the integration are disabled in every call here.
- Evaluator: [`b7a62c0`](https://github.com/Afloat16/AI-Memory-Book/commit/b7a62c0c4cf923365bc59dbde392ee9ae2dd8076); [registered protocol](../benchmarks/experiments/indexed-references-operator-plan.json) and [premeasurement source binding](../benchmarks/experiments/indexed-references-operator-binding.json).
- [Actual measurement and independent audit](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43203389371); [ordinary CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43203389215).
- [Full original rows](../benchmarks/reports/indexed-references-operator-43203389371-1.json.gz), [complete summary](../benchmarks/reports/indexed-references-operator-43203389371-1.summary.json), [attempt status](../benchmarks/reports/indexed-references-operator-43203389371-1.completion.json); result commit [`01191a1439b9cdadd72ee31a2443ddb3bba2d9e9`](https://github.com/Afloat16/AI-Memory-Book/commit/01191a1439b9cdadd72ee31a2443ddb3bba2d9e9).
- Decompressed report SHA-256: `a2b50a5201356d5ce3cbd4bbe7583985713d7cb1f4fa0cf9726abc23d1e2693d`; gzip SHA-256: `c9172ec8f57ad52dc56745a169bdfc3a10db15865fd0dd2f4049441bc6cebac3`.

The data are the previously used synthetic seed 61 development cohort (168 questions) and public1015 regression cohort (1,015 questions). The public set is not a fresh holdout here. Character budgets are 2,000, 4,000 and 8,000; `limit=5`; compact and `details=true` outputs are both included. No new blinded Hotpot questions, model generation or semantic retrieval participate.

## Complete compatibility and provenance checks

The evaluator compares the default compact response text and official SDK envelope with the previously audited actual responses, for every old query and budget. Indexed compact results decode to those same bytes. All 7,098 compact/detailed complete JSON values match across both modes and all four rounds after excluding only the pre-existing `latency_ms` diagnostic from the equality hash. Actual token counts still include that diagnostic and every other returned byte. Therefore small detailed-mode token differences between repeated calls can include variation in its printed timing value.

| Cohort | Stored pages audited | Original source reference records | Original and decoded reference SHA-256 |
| --- | --- | --- | --- |
| synthetic61 | 1912 | 2184 | afe05e37aa1b82c4492e52c158bde5a964def37f1741c9d3a6a988f0818e1aa4 |
| public1015 | 1339 | 4684 | c083796bed0008686ca49f394d726e9cecad1777d662dd9afbf79849a90bae15 |

The archive check uses every `pages.source_refs` record before retrieval selection. It preserves extras, offsets, message indices, roles, timestamps, duplicate references and project/session identity. The usual compact projection still performs its established identity deduplication before indexing; the new format adds no additional deduplication. Stored index digests match the earlier audited corpus and remain unchanged after calls. The option affects only MCP transport projection; `read_page` retains object references.

These checks prove that a decoder can recover the original data. They do not measure how reliably a particular language model follows the table instructions or emits correct citations in indexed mode. Existing generated-answer results from the default object format are not relabeled as indexed-format results.

## What the token totals include

A first-call total is one complete `list_tools` JSON, the actual `initialize.instructions` string, compact tool-argument JSON, and either the actual response text or the actual SDK result envelope. These are two alternative response surfaces and are never added to each other. Counts use pinned `tiktoken==0.12.0`; SDK 1.30.0 and Pydantic 2.14.3 are fixed. Provider-specific prompt wrappers, billing, cached-input discounts and final answer generation are outside this measurement.

The raw `later_call_*` fields describe incremental message/response token cost: arguments plus the new response, with initialization metadata excluded from that accounting boundary. They are not the token count or bill for a complete later LLM request. Clients can resend initialization instructions, schemas and historical prefixes; caching or reuse does not imply those input tokens are free. If metadata is present in a request, its costs still apply under that provider’s accounting. There is no per-call `source_format` argument; selection happens once at MCP server startup.

| Tokenizer | Objects schema | Indexed schema | Objects instructions | Indexed instructions | Indexed instruction overhead | Added tool-argument tokens |
| --- | --- | --- | --- | --- | --- | --- |
| cl100k_base | 912 | 912 | 168 | 241 | 73 | 0 |
| o200k_base | 954 | 954 | 167 | 241 | 74 | 0 |

Default `objects` users pay zero added schema or instruction tokens. Indexed instruction overhead includes the explicit zero-based coordinate explanation. The response totals include the version marker, session table and every reference extra. No metadata is subtracted from the measured response.

### cl100k_base — all response and first-call means

| Cohort | Chars | Details | Response text objects → indexed | SDK envelope objects → indexed | First-call text total objects → indexed | First-call envelope total objects → indexed | First-call net text / envelope |
| --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 1347.40 → 1254.77 | 1429.68 → 1337.63 | 2464.96 → 2445.33 | 2547.25 → 2528.20 | 19.63 / 19.05 |
| synthetic61 | 2000 | yes | 1878.77 → 1795.58 | 1986.52 → 1911.76 | 3000.33 → 2990.15 | 3108.08 → 3106.33 | 10.18 / 1.76 |
| synthetic61 | 4000 | no | 1841.03 → 1741.22 | 1943.88 → 1843.71 | 2958.60 → 2931.79 | 3061.45 → 3034.27 | 26.81 / 27.17 |
| synthetic61 | 4000 | yes | 2405.07 → 2315.19 | 2533.89 → 2452.44 | 3526.63 → 3509.76 | 3655.46 → 3647.01 | 16.88 / 8.45 |
| synthetic61 | 8000 | no | 1929.98 → 1830.17 | 2037.74 → 1937.21 | 3047.55 → 3020.74 | 3155.30 → 3127.78 | 26.81 / 27.52 |
| synthetic61 | 8000 | yes | 2502.44 → 2412.56 | 2635.82 → 2554.36 | 3624.01 → 3607.12 | 3757.38 → 3748.93 | 16.88 / 8.45 |
| public1015 | 2000 | no | 1129.64 → 934.38 | 1198.44 → 1001.98 | 2244.93 → 2122.68 | 2313.74 → 2190.27 | 122.25 / 123.46 |
| public1015 | 2000 | yes | 1808.17 → 1626.49 | 1911.04 → 1739.81 | 2927.46 → 2818.78 | 3030.33 → 2932.10 | 108.68 / 98.23 |
| public1015 | 4000 | no | 1480.64 → 1194.80 | 1567.39 → 1274.91 | 2595.93 → 2383.10 | 2682.68 → 2463.20 | 212.83 / 219.48 |
| public1015 | 4000 | yes | 2376.96 → 2109.23 | 2505.92 → 2248.64 | 3496.25 → 3301.52 | 3625.22 → 3440.93 | 194.73 / 184.28 |
| public1015 | 8000 | no | 1480.87 → 1195.02 | 1567.65 → 1275.15 | 2596.17 → 2383.31 | 2682.94 → 2463.44 | 212.85 / 219.50 |
| public1015 | 8000 | yes | 2377.48 → 2109.73 | 2506.47 → 2249.17 | 3496.77 → 3302.02 | 3625.77 → 3441.46 | 194.75 / 184.30 |

Positive net means fewer tokens with indexed references; negative net means an increase. Means use every query in every round, including empty and small-reference responses.

| Cohort | Chars | Details | Paired calls | First text saves / equal / adds | First envelope saves / equal / adds | Incremental text saves / equal / adds | Incremental envelope saves / equal / adds | Worst first-call net text / envelope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 672 | 312 / 4 / 356 | 300 / 12 / 360 | 656 / 0 / 16 | 656 / 0 / 16 | -84 / -89 |
| synthetic61 | 2000 | yes | 672 | 296 / 0 / 376 | 268 / 0 / 404 | 656 / 0 / 16 | 656 / 0 / 16 | -84 / -89 |
| synthetic61 | 4000 | no | 672 | 328 / 4 / 340 | 304 / 24 / 344 | 656 / 0 / 16 | 656 / 0 / 16 | -84 / -89 |
| synthetic61 | 4000 | yes | 672 | 299 / 1 / 372 | 268 / 0 / 404 | 656 / 0 / 16 | 656 / 0 / 16 | -84 / -89 |
| synthetic61 | 8000 | no | 672 | 328 / 4 / 340 | 328 / 0 / 344 | 656 / 0 / 16 | 656 / 0 / 16 | -84 / -89 |
| synthetic61 | 8000 | yes | 672 | 300 / 0 / 372 | 268 / 0 / 404 | 656 / 0 / 16 | 656 / 0 / 16 | -84 / -89 |
| public1015 | 2000 | no | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -10 / -13 |
| public1015 | 2000 | yes | 4060 | 4056 / 0 / 4 | 4044 / 0 / 16 | 4060 / 0 / 0 | 4060 / 0 / 0 | -16 / -24 |
| public1015 | 4000 | no | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -10 / -13 |
| public1015 | 4000 | yes | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -16 / -24 |
| public1015 | 8000 | no | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -10 / -13 |
| public1015 | 8000 | yes | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -16 / -24 |

### o200k_base — all response and first-call means

| Cohort | Chars | Details | Response text objects → indexed | SDK envelope objects → indexed | First-call text total objects → indexed | First-call envelope total objects → indexed | First-call net text / envelope |
| --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 1185.43 → 1088.26 | 1263.31 → 1168.55 | 2340.09 → 2316.91 | 2417.96 → 2397.21 | 23.18 / 20.76 |
| synthetic61 | 2000 | yes | 1712.58 → 1634.49 | 1815.14 → 1738.65 | 2871.24 → 2867.14 | 2973.79 → 2971.31 | 4.10 / 2.48 |
| synthetic61 | 4000 | no | 1584.85 → 1480.49 | 1683.46 → 1580.58 | 2739.50 → 2709.14 | 2838.11 → 2809.24 | 30.36 / 28.88 |
| synthetic61 | 4000 | yes | 2144.66 → 2060.36 | 2268.46 → 2185.29 | 3303.32 → 3293.01 | 3427.12 → 3417.94 | 10.31 / 9.18 |
| synthetic61 | 8000 | no | 1653.88 → 1549.52 | 1757.39 → 1654.17 | 2808.53 → 2778.17 | 2912.05 → 2882.82 | 30.36 / 29.23 |
| synthetic61 | 8000 | yes | 2222.11 → 2137.80 | 2350.46 → 2267.28 | 3380.77 → 3370.46 | 3509.12 → 3499.94 | 10.31 / 9.18 |
| public1015 | 2000 | no | 1123.43 → 926.41 | 1187.10 → 989.63 | 2279.57 → 2156.55 | 2343.24 → 2219.78 | 123.03 / 123.46 |
| public1015 | 2000 | yes | 1801.81 → 1631.93 | 1898.55 → 1727.32 | 2961.96 → 2866.07 | 3058.69 → 2961.46 | 95.88 / 97.23 |
| public1015 | 4000 | no | 1464.84 → 1177.24 | 1546.26 → 1252.78 | 2620.99 → 2407.38 | 2702.40 → 2482.92 | 213.61 / 219.48 |
| public1015 | 4000 | yes | 2361.01 → 2109.61 | 2483.65 → 2226.36 | 3521.16 → 3343.75 | 3643.79 → 3460.50 | 177.41 / 183.28 |
| public1015 | 8000 | no | 1465.07 → 1177.44 | 1546.51 → 1253.01 | 2621.21 → 2407.59 | 2702.65 → 2483.15 | 213.63 / 219.50 |
| public1015 | 8000 | yes | 2361.53 → 2110.10 | 2484.18 → 2226.88 | 3521.67 → 3344.24 | 3644.33 → 3461.02 | 177.42 / 183.30 |

Positive net means fewer tokens with indexed references; negative net means an increase. Means use every query in every round, including empty and small-reference responses.

| Cohort | Chars | Details | Paired calls | First text saves / equal / adds | First envelope saves / equal / adds | Incremental text saves / equal / adds | Incremental envelope saves / equal / adds | Worst first-call net text / envelope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 672 | 316 / 12 / 344 | 304 / 8 / 360 | 656 / 0 / 16 | 656 / 0 / 16 | -85 / -88 |
| synthetic61 | 2000 | yes | 672 | 264 / 12 / 396 | 264 / 0 / 408 | 656 / 0 / 16 | 656 / 0 / 16 | -85 / -88 |
| synthetic61 | 4000 | no | 672 | 332 / 12 / 328 | 316 / 12 / 344 | 656 / 0 / 16 | 656 / 0 / 16 | -85 / -88 |
| synthetic61 | 4000 | yes | 672 | 264 / 12 / 396 | 264 / 0 / 408 | 656 / 0 / 16 | 656 / 0 / 16 | -85 / -88 |
| synthetic61 | 8000 | no | 672 | 332 / 12 / 328 | 328 / 0 / 344 | 656 / 0 / 16 | 656 / 0 / 16 | -85 / -88 |
| synthetic61 | 8000 | yes | 672 | 264 / 12 / 396 | 264 / 0 / 408 | 656 / 0 / 16 | 656 / 0 / 16 | -85 / -88 |
| public1015 | 2000 | no | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -10 / -13 |
| public1015 | 2000 | yes | 4060 | 4056 / 0 / 4 | 4044 / 0 / 16 | 4060 / 0 / 0 | 4060 / 0 / 0 | -22 / -25 |
| public1015 | 4000 | no | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -10 / -13 |
| public1015 | 4000 | yes | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -22 / -25 |
| public1015 | 8000 | no | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -10 / -13 |
| public1015 | 8000 | yes | 4060 | 4056 / 0 / 4 | 4056 / 0 / 4 | 4060 / 0 / 0 | 4060 / 0 / 0 | -22 / -25 |

Each outcome count is over repeated paired calls: 672 per synthetic configuration and 4,060 per public configuration, not that many distinct questions. These tables retain all small-reference and detailed-mode losses; the format is optional and no per-question automatic format selection is performed.

### Distinct questions with a first-call increase

The following counts were recomputed from the original paired rows. Each loss set contains the same question IDs in every round; the four repetitions do not inflate these question counts. A positive mean saving can coexist with many individual losses.

| Cohort | Chars | Details | Questions | cl100k text / envelope losses | o200k text / envelope losses |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 168 | 89 / 90 | 86 / 90 |
| synthetic61 | 2000 | yes | 168 | 94 / 101 | 99 / 102 |
| synthetic61 | 4000 | no | 168 | 85 / 86 | 82 / 86 |
| synthetic61 | 4000 | yes | 168 | 93 / 101 | 99 / 102 |
| synthetic61 | 8000 | no | 168 | 85 / 86 | 82 / 86 |
| synthetic61 | 8000 | yes | 168 | 93 / 101 | 99 / 102 |
| public1015 | 2000 | no | 1015 | 1 / 1 | 1 / 1 |
| public1015 | 2000 | yes | 1015 | 1 / 4 | 1 / 4 |
| public1015 | 4000 | no | 1015 | 1 / 1 | 1 / 1 |
| public1015 | 4000 | yes | 1015 | 1 / 1 | 1 / 1 |
| public1015 | 8000 | no | 1015 | 1 / 1 | 1 / 1 |
| public1015 | 8000 | yes | 1015 | 1 / 1 | 1 / 1 |

For public1015 / 4,000 characters / compact output, 1,014 of 1,015 questions save first-call tokens and one adds 10 text tokens or 13 envelope tokens, under either encoding. At public1015 / 2,000 characters / detailed output, four questions add envelope tokens. The worst synthetic first-call increase is 84 text / 89 envelope tokens under `cl100k_base` and 85 / 88 under `o200k_base`. These are response-format tradeoffs, not missing evidence.

### Unchanged context and tool arguments

| Cohort | Chars | Details | Context cl100k / o200k | Arguments cl100k / o200k |
| --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 951.59 / 781.35 | 37.57 / 33.65 |
| synthetic61 | 2000 | yes | 951.59 / 781.35 | 41.57 / 37.65 |
| synthetic61 | 4000 | no | 1426.76 / 1162.43 | 37.57 / 33.65 |
| synthetic61 | 4000 | yes | 1426.76 / 1162.43 | 41.57 / 37.65 |
| synthetic61 | 8000 | no | 1520.19 / 1235.95 | 37.57 / 33.65 |
| synthetic61 | 8000 | yes | 1520.19 / 1235.95 | 41.57 / 37.65 |
| public1015 | 2000 | no | 607.36 / 594.88 | 35.29 / 35.14 |
| public1015 | 2000 | yes | 607.36 / 594.88 | 39.29 / 39.14 |
| public1015 | 4000 | no | 866.60 / 844.52 | 35.29 / 35.14 |
| public1015 | 4000 | yes | 866.60 / 844.52 | 39.29 / 39.14 |
| public1015 | 8000 | no | 867.07 / 844.99 | 35.29 / 35.14 |
| public1015 | 8000 | yes | 867.07 / 844.99 | 39.29 / 39.14 |

Context bytes and tokens, tool-argument bytes and tokens, page order, page IDs and complete source fields are equal between formats. First-call differences come from response encoding and the indexed-only instructions.

## Actual MCP latency — every configuration

One isolated hosted VM executes sequential workers. Mode order is objects/indexed in even rounds and indexed/objects in odd rounds. Both see the same shuffled query order. A committed SQLite result-cache clear precedes every timed call; the clear is excluded, while normal server cache lookup and write remain included. Hashing, token counting, validation, startup and ingestion are outside the call timer. OS and SQLite caches are warm; these results do not claim cold-system latency.

| Cohort | Chars | Details | Objects p50 / p95 / mean ms | Indexed p50 / p95 / mean ms | Indexed p95 change | Mean paired indexed−objects ms |
| --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 7.286 / 16.860 / 8.964 | 7.234 / 16.775 / 8.947 | -0.50% | -0.018 |
| synthetic61 | 2000 | yes | 7.131 / 16.581 / 8.809 | 7.158 / 16.593 / 8.847 | 0.08% | 0.038 |
| synthetic61 | 4000 | no | 6.529 / 16.065 / 7.991 | 6.539 / 15.923 / 8.007 | -0.88% | 0.017 |
| synthetic61 | 4000 | yes | 6.562 / 16.017 / 8.022 | 6.611 / 16.054 / 8.082 | 0.23% | 0.059 |
| synthetic61 | 8000 | no | 6.256 / 11.746 / 7.196 | 6.369 / 11.766 / 7.272 | 0.17% | 0.076 |
| synthetic61 | 8000 | yes | 6.193 / 11.749 / 7.086 | 6.313 / 11.808 / 7.164 | 0.50% | 0.079 |
| public1015 | 2000 | no | 6.379 / 8.514 / 6.559 | 6.368 / 8.490 / 6.560 | -0.28% | 0.000 |
| public1015 | 2000 | yes | 6.461 / 8.550 / 6.623 | 6.421 / 8.507 / 6.591 | -0.50% | -0.032 |
| public1015 | 4000 | no | 5.503 / 7.126 / 5.634 | 5.466 / 7.131 / 5.601 | 0.08% | -0.033 |
| public1015 | 4000 | yes | 5.473 / 7.096 / 5.603 | 5.543 / 7.164 / 5.675 | 0.96% | 0.072 |
| public1015 | 8000 | no | 5.470 / 7.088 / 5.603 | 5.491 / 7.128 / 5.629 | 0.57% | 0.026 |
| public1015 | 8000 | yes | 5.479 / 7.116 / 5.607 | 5.491 / 7.126 / 5.631 | 0.15% | 0.024 |

A positive latency change is a regression. All four rounds are pooled above; no fastest-round selection or cross-host speed ratio is used. Paired latency differences include the whole SDK call, not an isolated codec microbenchmark.

The largest pooled p95 regression is public1015 / 4,000 characters /
`details=true`: 7.09620865 → 7.16429 ms, or +0.06808135 ms (+0.9594%). The largest
single-round p95 regression is the same configuration in round 1:
7.0777599 → 7.2158086 ms (+1.9505%). These increases are retained in the full
matrix and are not removed by selecting a better round.

### All four rounds retained

| Cohort | Chars | Details | Round 0 objects p50/p95/mean; indexed p50/p95/mean | Round 1 same order of values | Round 2 same order of values | Round 3 same order of values |
| --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | 2000 | no | 7.264 / 16.877 / 8.919 / 7.212 / 16.791 / 8.887 | 7.277 / 16.510 / 8.894 / 7.265 / 16.638 / 8.935 | 7.294 / 17.009 / 9.054 / 7.351 / 16.923 / 9.049 | 7.342 / 16.839 / 8.991 / 7.182 / 16.613 / 8.917 |
| synthetic61 | 2000 | yes | 7.059 / 16.348 / 8.710 / 7.080 / 16.549 / 8.829 | 7.085 / 16.502 / 8.797 / 7.124 / 16.479 / 8.770 | 7.141 / 16.733 / 8.833 / 7.365 / 16.807 / 9.004 | 7.178 / 16.763 / 8.897 / 7.055 / 16.482 / 8.785 |
| synthetic61 | 4000 | no | 6.512 / 15.794 / 7.926 / 6.501 / 15.936 / 8.037 | 6.400 / 15.619 / 7.946 / 6.547 / 15.775 / 8.020 | 6.562 / 16.065 / 7.982 / 6.590 / 16.214 / 8.051 | 6.588 / 16.097 / 8.109 / 6.440 / 15.667 / 7.921 |
| synthetic61 | 4000 | yes | 6.727 / 16.066 / 8.091 / 6.556 / 15.839 / 8.000 | 6.530 / 15.931 / 7.984 / 6.561 / 15.972 / 8.082 | 6.485 / 15.937 / 7.951 / 6.675 / 15.987 / 8.124 | 6.563 / 15.921 / 8.063 / 6.653 / 16.134 / 8.121 |
| synthetic61 | 8000 | no | 6.265 / 11.727 / 7.219 / 6.468 / 11.821 / 7.335 | 6.254 / 11.715 / 7.197 / 6.321 / 11.701 / 7.244 | 6.171 / 11.697 / 7.126 / 6.406 / 11.802 / 7.318 | 6.291 / 11.791 / 7.242 / 6.232 / 11.671 / 7.189 |
| synthetic61 | 8000 | yes | 6.172 / 11.748 / 7.072 / 6.275 / 11.802 / 7.132 | 6.255 / 11.731 / 7.091 / 6.397 / 11.899 / 7.325 | 6.175 / 11.732 / 7.076 / 6.158 / 11.685 / 7.046 | 6.275 / 11.829 / 7.104 / 6.310 / 11.824 / 7.155 |
| public1015 | 2000 | no | 6.392 / 8.529 / 6.575 / 6.429 / 8.561 / 6.631 | 6.430 / 8.612 / 6.620 / 6.342 / 8.462 / 6.515 | 6.336 / 8.414 / 6.503 / 6.395 / 8.534 / 6.574 | 6.373 / 8.436 / 6.539 / 6.330 / 8.342 / 6.518 |
| public1015 | 2000 | yes | 6.414 / 8.473 / 6.586 / 6.397 / 8.420 / 6.555 | 6.522 / 8.677 / 6.705 / 6.425 / 8.591 / 6.626 | 6.421 / 8.538 / 6.583 / 6.429 / 8.488 / 6.601 | 6.467 / 8.543 / 6.619 / 6.426 / 8.461 / 6.581 |
| public1015 | 4000 | no | 5.516 / 7.121 / 5.647 / 5.444 / 7.071 / 5.569 | 5.498 / 7.115 / 5.635 / 5.451 / 7.122 / 5.592 | 5.497 / 7.127 / 5.624 / 5.468 / 7.134 / 5.620 | 5.506 / 7.143 / 5.629 / 5.495 / 7.157 / 5.623 |
| public1015 | 4000 | yes | 5.489 / 7.128 / 5.619 / 5.523 / 7.116 / 5.661 | 5.461 / 7.078 / 5.590 / 5.556 / 7.216 / 5.677 | 5.445 / 7.065 / 5.586 / 5.560 / 7.163 / 5.687 | 5.477 / 7.080 / 5.617 / 5.534 / 7.164 / 5.676 |
| public1015 | 8000 | no | 5.469 / 7.087 / 5.613 / 5.499 / 7.147 / 5.637 | 5.441 / 7.117 / 5.593 / 5.544 / 7.181 / 5.690 | 5.503 / 7.090 / 5.628 / 5.487 / 7.130 / 5.629 | 5.457 / 7.061 / 5.577 / 5.438 / 7.060 / 5.561 |
| public1015 | 8000 | yes | 5.447 / 7.056 / 5.578 / 5.480 / 7.149 / 5.642 | 5.499 / 7.171 / 5.638 / 5.525 / 7.099 / 5.644 | 5.476 / 7.119 / 5.600 / 5.488 / 7.156 / 5.637 | 5.490 / 7.116 / 5.613 / 5.466 / 7.076 / 5.601 |


## Startup, process memory and storage

| Cohort | Format | Startup ms rounds 0 / 1 / 2 / 3 | Live child median RSS MiB | Maximum child VmHWM MiB | Logical DB bytes after ingest |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | objects | 622.535 / 626.908 / 622.873 / 623.379 | 61.69 | 61.79 | 20508672 |
| synthetic61 | indexed | 627.312 / 625.459 / 628.901 / 624.306 | 61.79 | 61.87 | 20508672 |
| public1015 | objects | 626.923 / 625.571 / 621.118 / 626.742 | 61.92 | 62.00 | 12881920 |
| public1015 | indexed | 622.210 / 624.025 / 625.536 / 626.221 | 61.87 | 61.90 | 12881920 |

Memory is a Linux `/proc` snapshot of the live MCP child after calls, not total system memory or a codec allocation peak. Storage and original index digests are consistency checks; this experiment does not claim a new ingestion-speed improvement. Complete live DB/WAL/SHM snapshots and individual memory records remain in the summary.

## Reproduce and use

Use the [committed workflow](../.github/workflows/indexed-references-operator.yml) to obtain the exact old corpus, reference gzip, dependency versions and frozen source. After that preparation, the measured command is:

```sh
python scripts/benchmark_indexed_references.py \
  --runtime-src .artifacts/operator-source/src \
  --locomo-path .artifacts/operator-locomo10.json \
  --reference-report .artifacts/default-reference.json.gz \
  --output benchmarks/reports/indexed-references-operator-new-run.json.gz

python scripts/benchmark_indexed_references.py \
  --audit benchmarks/reports/indexed-references-operator-new-run.json.gz
```

Existing output paths are rejected. Each completed worker checkpoints original rows; the workflow always saves available files and an explicit complete/failed marker to a new results branch. The audit verifies compressed and decompressed hashes, the exact complete matrix, source/corpus identity, payload equality, initialization metadata counts, all outcome counts and every cost/latency aggregate.

Use the startup configuration and decoding rules shown above. The default remains `objects`. The indexed format requires an operator to start `memory-book mcp --source-format indexed`; existing generated client configurations do not change. These transport measurements make no claim about final generated answer quality, universal client billing or superiority over complete memory products.
