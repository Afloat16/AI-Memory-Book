# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 88.89% | 86.67% | 183.9 | 1.794 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 88.89% | 86.67% | 183.9 | 1.757 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 88.89% | 86.67% | 183.9 | 1.749 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 88.89% | 86.67% | 168.3 | 1.922 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 88.89% | 86.67% | 168.3 | 1.924 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 88.89% | 86.67% | 168.3 | 1.921 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 1.637 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 1.611 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 1.632 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 88.89% | 86.67% | 172.9 | 1.835 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 88.89% | 86.67% | 172.9 | 1.782 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 88.89% | 86.67% | 172.9 | 1.774 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 1.644 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 1.619 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 1.642 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 88.89% | 86.67% | 172.9 | 1.778 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 88.89% | 86.67% | 172.9 | 1.802 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 88.89% | 86.67% | 172.9 | 1.814 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 1.807 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 1.764 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 1.722 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 88.89% | 86.67% | 172.9 | 2.006 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 88.89% | 86.67% | 172.9 | 1.998 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 88.89% | 86.67% | 172.9 | 1.980 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 1.721 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 1.747 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 1.751 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 88.89% | 86.67% | 172.9 | 1.983 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 88.89% | 86.67% | 172.9 | 1.949 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 88.89% | 86.67% | 172.9 | 1.998 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | cl100k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
