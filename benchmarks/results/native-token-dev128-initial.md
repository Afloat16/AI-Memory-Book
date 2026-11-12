# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default / historical_whole_page_pack | 100000 | cl100k_base | 512 | 72.90% | 75.90% | 451.2 | 4.519 |
| prior-default / native_excerpt_pack | 8000 | cl100k_base | 512 | 69.16% | 71.08% | 434.9 | 4.979 |
| native-token / native_token_budget | 8000 | cl100k_base | 512 | 71.03% | 73.49% | 491.1 | 12.827 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 8000 | cl100k_base | 512 | 2 | 0 | 2 | 0 | 0 |
