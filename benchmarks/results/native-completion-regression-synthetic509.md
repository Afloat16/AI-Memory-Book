# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 68.18% | 68.42% | 367.1 | 13.897 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 81.82% | 84.21% | 846.9 | 12.742 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 81.82% | 84.21% | 1146.0 | 17.412 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 73.30% | 74.34% | 379.4 | 12.591 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 81.82% | 84.21% | 816.5 | 15.067 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 81.82% | 84.21% | 1082.6 | 26.760 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 77.27% | 78.95% | 416.0 | 19.620 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 720.6 | 21.010 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 928.5 | 18.271 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 79.55% | 81.58% | 450.3 | 18.851 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 693.8 | 22.265 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 773.1 | 23.066 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 68.18% | 68.42% | 374.9 | 15.772 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 864.3 | 15.895 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1173.4 | 14.536 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 72.73% | 73.68% | 378.8 | 13.537 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 835.8 | 14.692 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1111.2 | 16.121 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 512 | 79.55% | 81.58% | 493.6 | 33.677 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 1024 | 79.55% | 81.58% | 762.6 | 35.434 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | cl100k_base | 2048 | 79.55% | 81.58% | 928.5 | 21.742 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 512 | 79.55% | 81.58% | 490.3 | 32.128 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 1024 | 79.55% | 81.58% | 731.1 | 31.085 |
| native-token-stable-prefix-v1 / native_token_budget | 2000 | o200k_base | 2048 | 79.55% | 81.58% | 773.1 | 25.109 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 512 | 81.82% | 84.21% | 489.9 | 44.004 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 1024 | 81.82% | 84.21% | 929.4 | 30.600 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | cl100k_base | 2048 | 81.82% | 84.21% | 1258.9 | 25.853 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 512 | 81.82% | 84.21% | 491.0 | 29.640 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 1024 | 81.82% | 84.21% | 899.9 | 32.925 |
| native-token-stable-prefix-v1 / native_token_budget | 8000 | o200k_base | 2048 | 81.82% | 84.21% | 1145.1 | 40.877 |

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
