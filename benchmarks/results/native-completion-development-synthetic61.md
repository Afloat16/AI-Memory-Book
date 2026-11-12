# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 75.00% | 72.37% | 350.6 | 18.892 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 90.91% | 89.47% | 824.2 | 23.215 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 93.18% | 92.11% | 1135.7 | 17.710 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 78.41% | 76.32% | 363.2 | 24.414 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 93.18% | 92.11% | 783.3 | 25.630 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 93.18% | 92.11% | 1087.9 | 39.850 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 85.80% | 84.21% | 398.2 | 27.510 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 93.18% | 92.11% | 703.6 | 25.999 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 93.18% | 92.11% | 951.6 | 24.959 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 93.18% | 92.11% | 446.8 | 17.452 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 93.18% | 92.11% | 683.1 | 27.014 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 93.18% | 92.11% | 781.3 | 17.250 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 75.00% | 72.37% | 358.4 | 13.442 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 90.91% | 89.47% | 835.8 | 34.846 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 93.18% | 92.11% | 1162.1 | 33.715 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 77.27% | 75.00% | 358.8 | 24.025 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 93.18% | 92.11% | 790.0 | 27.875 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 93.18% | 92.11% | 1115.0 | 27.266 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 92.61% | 92.11% | 483.8 | 97.668 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 93.18% | 92.11% | 745.9 | 172.323 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 93.18% | 92.11% | 951.6 | 59.866 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 93.18% | 92.11% | 481.3 | 81.182 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 93.18% | 92.11% | 721.5 | 57.618 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 93.18% | 92.11% | 781.3 | 34.574 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 86.36% | 85.53% | 476.8 | 45.684 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 93.18% | 92.11% | 905.5 | 56.538 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 93.18% | 92.11% | 1260.1 | 29.659 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 90.91% | 90.79% | 479.8 | 56.750 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 93.18% | 92.11% | 877.8 | 47.445 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 93.18% | 92.11% | 1146.9 | 39.729 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | cl100k_base | 512 | 12 | 0 | 12 | 0 | 0 |
| 2000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 512 | 20 | 0 | 20 | 0 | 0 |
| 8000 | cl100k_base | 1024 | 4 | 0 | 4 | 0 | 0 |
| 8000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 512 | 24 | 0 | 24 | 0 | 0 |
| 8000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
