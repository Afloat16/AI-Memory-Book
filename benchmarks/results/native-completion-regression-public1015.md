# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 62.44% | 66.26% | 447.6 | 7.359 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 69.54% | 72.88% | 827.2 | 7.644 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 69.54% | 72.88% | 832.1 | 7.714 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 62.94% | 66.72% | 451.5 | 8.285 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 69.54% | 72.88% | 809.2 | 8.562 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 69.54% | 72.88% | 810.0 | 8.716 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 46.07% | 48.69% | 483.3 | 8.570 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 47.59% | 50.23% | 607.4 | 8.340 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 47.59% | 50.23% | 607.4 | 8.292 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 45.94% | 48.69% | 475.8 | 8.770 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 47.59% | 50.23% | 594.9 | 9.003 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 47.59% | 50.23% | 594.9 | 8.925 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 61.17% | 65.33% | 444.5 | 7.120 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 69.54% | 72.88% | 855.5 | 7.392 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 69.54% | 72.88% | 867.1 | 7.452 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 62.06% | 65.95% | 446.6 | 7.900 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 69.54% | 72.88% | 839.3 | 8.383 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 69.54% | 72.88% | 845.0 | 8.484 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 46.19% | 48.84% | 485.8 | 9.978 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 47.59% | 50.23% | 607.4 | 8.710 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 47.59% | 50.23% | 607.4 | 8.918 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 45.94% | 48.69% | 479.2 | 10.937 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 47.59% | 50.23% | 594.9 | 9.408 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 47.59% | 50.23% | 594.9 | 9.405 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 62.18% | 66.41% | 491.9 | 10.076 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 69.54% | 72.88% | 861.1 | 8.260 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 69.54% | 72.88% | 867.1 | 7.967 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 62.82% | 66.72% | 492.7 | 11.994 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 69.54% | 72.88% | 842.2 | 9.231 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 69.54% | 72.88% | 845.0 | 8.945 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | cl100k_base | 512 | 1 | 0 | 1 | 0 | 0 |
| 2000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 512 | 8 | 0 | 7 | 0 | 0 |
| 8000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 512 | 6 | 0 | 5 | 0 | 0 |
| 8000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
