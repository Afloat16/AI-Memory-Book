# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 68.18% | 68.42% | 369.1 | 7.583 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 81.82% | 84.21% | 846.2 | 7.789 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 81.82% | 84.21% | 1145.5 | 7.900 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 73.86% | 75.00% | 383.3 | 7.683 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 81.82% | 84.21% | 821.7 | 8.496 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 81.82% | 84.21% | 1081.9 | 8.767 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 77.27% | 78.95% | 420.7 | 10.633 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 709.8 | 10.762 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 926.0 | 10.774 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 79.55% | 81.58% | 454.4 | 10.919 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 691.2 | 11.287 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 770.1 | 11.460 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 68.18% | 68.42% | 376.3 | 7.146 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 859.9 | 7.488 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1172.0 | 8.214 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 72.73% | 73.68% | 379.3 | 7.502 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 836.8 | 8.000 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1109.2 | 8.737 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 79.55% | 81.58% | 492.6 | 20.189 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 753.4 | 17.519 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 926.0 | 12.303 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 79.55% | 81.58% | 489.2 | 19.116 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 727.4 | 15.290 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 770.1 | 12.754 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 81.82% | 84.21% | 490.0 | 15.305 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 922.6 | 16.882 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1257.0 | 14.363 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 81.82% | 84.21% | 490.5 | 16.426 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 897.2 | 16.696 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1142.9 | 14.389 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | cl100k_base | 512 | 4 | 0 | 4 | 0 | 0 |
| 2000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 512 | 24 | 0 | 24 | 0 | 0 |
| 8000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 512 | 16 | 0 | 16 | 0 | 0 |
| 8000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
