# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 512 | 75.00% | 72.37% | 350.6 | 11.975 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 90.91% | 89.47% | 824.2 | 12.701 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 93.18% | 92.11% | 1135.7 | 12.721 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 512 | 78.41% | 76.32% | 363.2 | 12.361 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 1024 | 93.18% | 92.11% | 783.3 | 13.024 |
| prior-default-5abc85e / historical_whole_page_pack | 100000 | o200k_base | 2048 | 93.18% | 92.11% | 1087.9 | 15.061 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 512 | 85.80% | 84.21% | 398.2 | 17.399 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 1024 | 93.18% | 92.11% | 703.6 | 18.262 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | cl100k_base | 2048 | 93.18% | 92.11% | 951.6 | 16.393 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 512 | 93.18% | 92.11% | 446.8 | 16.260 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 1024 | 93.18% | 92.11% | 683.1 | 17.897 |
| prior-default-5abc85e / native_excerpt_pack | 2000 | o200k_base | 2048 | 93.18% | 92.11% | 781.3 | 17.076 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 512 | 75.00% | 72.37% | 358.4 | 11.741 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 1024 | 90.91% | 89.47% | 835.8 | 13.049 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | cl100k_base | 2048 | 93.18% | 92.11% | 1162.1 | 13.936 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 512 | 77.27% | 75.00% | 358.8 | 116.573 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 1024 | 93.18% | 92.11% | 790.0 | 24.600 |
| prior-default-5abc85e / native_excerpt_pack | 8000 | o200k_base | 2048 | 93.18% | 92.11% | 1115.0 | 14.257 |
| native-token-e70bc3d / native_token_budget | 2000 | cl100k_base | 512 | 92.61% | 92.11% | 483.8 | 57.773 |
| native-token-e70bc3d / native_token_budget | 2000 | cl100k_base | 1024 | 93.18% | 92.11% | 745.9 | 50.000 |
| native-token-e70bc3d / native_token_budget | 2000 | cl100k_base | 2048 | 93.18% | 92.11% | 951.6 | 18.255 |
| native-token-e70bc3d / native_token_budget | 2000 | o200k_base | 512 | 93.18% | 92.11% | 481.3 | 61.884 |
| native-token-e70bc3d / native_token_budget | 2000 | o200k_base | 1024 | 93.18% | 92.11% | 721.5 | 51.402 |
| native-token-e70bc3d / native_token_budget | 2000 | o200k_base | 2048 | 93.18% | 92.11% | 781.3 | 18.822 |
| native-token-e70bc3d / native_token_budget | 8000 | cl100k_base | 512 | 86.36% | 85.53% | 476.8 | 78.271 |
| native-token-e70bc3d / native_token_budget | 8000 | cl100k_base | 1024 | 93.18% | 92.11% | 905.5 | 75.159 |
| native-token-e70bc3d / native_token_budget | 8000 | cl100k_base | 2048 | 93.18% | 92.11% | 1260.1 | 25.712 |
| native-token-e70bc3d / native_token_budget | 8000 | o200k_base | 512 | 90.91% | 90.79% | 479.8 | 58.502 |
| native-token-e70bc3d / native_token_budget | 8000 | o200k_base | 1024 | 93.18% | 92.11% | 877.8 | 56.374 |
| native-token-e70bc3d / native_token_budget | 8000 | o200k_base | 2048 | 93.18% | 92.11% | 1146.9 | 24.571 |

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
