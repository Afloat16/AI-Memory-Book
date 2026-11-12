# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 68.18% | 68.42% | 368.3 | 236.413 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 81.82% | 84.21% | 845.3 | 444.015 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 81.82% | 84.21% | 1143.9 | 61.395 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 75.00% | 76.32% | 402.4 | 33.261 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 81.82% | 84.21% | 820.7 | 77.372 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 81.82% | 84.21% | 1080.3 | 60.440 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 77.27% | 78.95% | 416.1 | 92.052 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 719.2 | 98.283 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 927.1 | 193.013 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 79.55% | 81.58% | 451.8 | 36.396 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 691.1 | 29.308 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 770.5 | 19.357 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 68.18% | 68.42% | 374.7 | 13.195 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 861.9 | 12.698 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1170.3 | 18.826 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 72.73% | 73.68% | 380.3 | 16.078 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 836.4 | 22.794 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1107.1 | 19.040 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 79.55% | 81.58% | 493.4 | 50.525 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 760.9 | 61.649 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 927.1 | 31.834 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 79.55% | 81.58% | 489.0 | 34.418 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 729.0 | 39.208 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 770.5 | 27.144 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 81.82% | 84.21% | 489.6 | 53.650 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 927.8 | 51.080 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1256.8 | 43.081 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 81.82% | 84.21% | 489.7 | 52.293 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 896.7 | 42.110 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1141.1 | 25.575 |

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
