# Native token-budget comparison

Validation: **PASS**.

Three delivery policies are separate. Evidence scores do not measure generated answers or complete competitor workflows.

| Engine / policy | Character cap | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Total p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|
| prior-default / historical_whole_page_pack | 100000 | cl100k_base | 512 | 72.90% | 75.90% | 451.2 | 4.529 |
| prior-default / historical_whole_page_pack | 100000 | cl100k_base | 1024 | 77.57% | 79.52% | 807.6 | 4.549 |
| prior-default / historical_whole_page_pack | 100000 | cl100k_base | 2048 | 77.57% | 79.52% | 811.1 | 4.859 |
| prior-default / historical_whole_page_pack | 100000 | o200k_base | 512 | 72.90% | 75.90% | 451.4 | 5.316 |
| prior-default / historical_whole_page_pack | 100000 | o200k_base | 1024 | 77.57% | 79.52% | 788.6 | 5.340 |
| prior-default / historical_whole_page_pack | 100000 | o200k_base | 2048 | 77.57% | 79.52% | 792.1 | 5.369 |
| prior-default / native_excerpt_pack | 2000 | cl100k_base | 512 | 50.47% | 51.81% | 485.3 | 5.137 |
| prior-default / native_excerpt_pack | 2000 | cl100k_base | 1024 | 52.34% | 54.22% | 606.7 | 4.971 |
| prior-default / native_excerpt_pack | 2000 | cl100k_base | 2048 | 52.34% | 54.22% | 606.7 | 5.332 |
| prior-default / native_excerpt_pack | 2000 | o200k_base | 512 | 50.47% | 51.81% | 476.3 | 6.108 |
| prior-default / native_excerpt_pack | 2000 | o200k_base | 1024 | 52.34% | 54.22% | 595.3 | 6.308 |
| prior-default / native_excerpt_pack | 2000 | o200k_base | 2048 | 52.34% | 54.22% | 595.3 | 5.604 |
| prior-default / native_excerpt_pack | 8000 | cl100k_base | 512 | 69.16% | 71.08% | 434.9 | 4.690 |
| prior-default / native_excerpt_pack | 8000 | cl100k_base | 1024 | 77.57% | 79.52% | 840.6 | 4.407 |
| prior-default / native_excerpt_pack | 8000 | cl100k_base | 2048 | 77.57% | 79.52% | 845.9 | 4.562 |
| prior-default / native_excerpt_pack | 8000 | o200k_base | 512 | 69.16% | 71.08% | 441.4 | 4.728 |
| prior-default / native_excerpt_pack | 8000 | o200k_base | 1024 | 77.57% | 79.52% | 821.7 | 9.568 |
| prior-default / native_excerpt_pack | 8000 | o200k_base | 2048 | 77.57% | 79.52% | 826.8 | 6.557 |
| native-token / native_token_budget | 2000 | cl100k_base | 512 | 50.47% | 51.81% | 486.3 | 9.576 |
| native-token / native_token_budget | 2000 | cl100k_base | 1024 | 52.34% | 54.22% | 606.7 | 6.356 |
| native-token / native_token_budget | 2000 | cl100k_base | 2048 | 52.34% | 54.22% | 606.7 | 5.662 |
| native-token / native_token_budget | 2000 | o200k_base | 512 | 50.47% | 51.81% | 478.6 | 12.149 |
| native-token / native_token_budget | 2000 | o200k_base | 1024 | 52.34% | 54.22% | 595.3 | 6.057 |
| native-token / native_token_budget | 2000 | o200k_base | 2048 | 52.34% | 54.22% | 595.3 | 5.843 |
| native-token / native_token_budget | 8000 | cl100k_base | 512 | 71.03% | 73.49% | 491.1 | 11.460 |
| native-token / native_token_budget | 8000 | cl100k_base | 1024 | 77.57% | 79.52% | 843.4 | 5.117 |
| native-token / native_token_budget | 8000 | cl100k_base | 2048 | 77.57% | 79.52% | 845.9 | 5.305 |
| native-token / native_token_budget | 8000 | o200k_base | 512 | 71.03% | 73.49% | 492.7 | 17.230 |
| native-token / native_token_budget | 8000 | o200k_base | 1024 | 77.57% | 79.52% | 824.4 | 6.157 |
| native-token / native_token_budget | 8000 | o200k_base | 2048 | 77.57% | 79.52% | 826.8 | 6.318 |

## Per-query changes against native excerpt packing

| Characters | Tokenizer | Tokens | Annotation gains | Annotation losses | Complete gains | Complete losses | Missing old blocks |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | cl100k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 512 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 2000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 512 | 2 | 0 | 2 | 0 | 0 |
| 8000 | cl100k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | cl100k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 512 | 2 | 0 | 2 | 0 | 0 |
| 8000 | o200k_base | 1024 | 0 | 0 | 0 | 0 | 0 |
| 8000 | o200k_base | 2048 | 0 | 0 | 0 | 0 | 0 |
