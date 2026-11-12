# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 68.18% | 68.42% | 365.9 | 12.557 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 81.82% | 84.21% | 845.0 | 13.652 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 81.82% | 84.21% | 1144.0 | 13.876 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 73.86% | 75.00% | 392.1 | 13.450 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 81.82% | 84.21% | 820.6 | 14.454 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 81.82% | 84.21% | 1080.7 | 15.615 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 77.27% | 78.95% | 415.2 | 19.145 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 713.8 | 18.989 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 932.6 | 19.287 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 79.55% | 81.58% | 450.8 | 19.320 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 692.3 | 20.279 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 774.9 | 20.002 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 68.18% | 68.42% | 373.9 | 12.550 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 855.2 | 13.413 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1171.9 | 13.987 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 72.73% | 73.68% | 379.6 | 13.015 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 825.3 | 14.232 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1109.2 | 15.629 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 79.55% | 81.58% | 492.8 | 33.755 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 757.1 | 29.104 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 932.6 | 21.288 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 79.55% | 81.58% | 489.9 | 33.548 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 731.3 | 26.011 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 774.9 | 21.996 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 81.82% | 84.21% | 489.4 | 26.448 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 925.0 | 28.901 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1258.7 | 24.545 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 81.82% | 84.21% | 491.1 | 27.737 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 897.9 | 29.150 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1144.6 | 25.258 |

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
