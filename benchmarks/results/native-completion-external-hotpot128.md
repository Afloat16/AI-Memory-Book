# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 69.93% | 39.84% | 450.9 | 8.068 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 74.51% | 48.44% | 717.4 | 8.260 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 74.51% | 48.44% | 717.4 | 8.337 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 69.93% | 39.84% | 450.5 | 8.782 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 74.51% | 48.44% | 711.0 | 8.981 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 74.51% | 48.44% | 711.0 | 8.787 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 51.96% | 21.88% | 431.0 | 11.516 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 56.21% | 27.34% | 667.5 | 11.438 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 56.21% | 27.34% | 667.5 | 11.433 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 51.96% | 21.88% | 429.3 | 11.677 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 56.21% | 27.34% | 668.5 | 11.820 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 56.21% | 27.34% | 668.5 | 11.920 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 66.34% | 34.38% | 451.4 | 7.873 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 74.51% | 48.44% | 802.3 | 8.052 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 74.51% | 48.44% | 805.8 | 8.219 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 66.34% | 34.38% | 451.6 | 8.306 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 74.51% | 48.44% | 801.1 | 8.709 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 74.51% | 48.44% | 804.6 | 8.767 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 52.29% | 21.88% | 486.0 | 12.819 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 56.21% | 27.34% | 667.5 | 11.726 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 56.21% | 27.34% | 667.5 | 11.793 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 52.61% | 21.88% | 488.9 | 13.628 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 56.21% | 27.34% | 668.5 | 12.381 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 56.21% | 27.34% | 668.5 | 12.528 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 66.99% | 35.16% | 479.4 | 9.188 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 74.51% | 48.44% | 804.0 | 8.221 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 74.51% | 48.44% | 805.8 | 8.343 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 66.99% | 35.16% | 479.0 | 10.380 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 74.51% | 48.44% | 802.9 | 9.046 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 74.51% | 48.44% | 804.6 | 8.898 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | cl100k_base | 512 | 1 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 512 | 2 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 512 | 2 | 0 | 1 | 0 | 0 |
| 8000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 512 | 2 | 0 | 1 | 0 | 0 |
| 8000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
