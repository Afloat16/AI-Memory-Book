# Additional upstream lexical component replay

Status: `completed`. Protocol: `engineering-extended-lexical-v1`.

Authored synthetic development data; 80 unchanged questions, including eight missing-evidence questions. This is a supplied-page ranking and common whole-block packing comparison, not a held-out test, generated answer accuracy, or complete memory product benchmark.

| Actual upstream mode | Chars | Evidence recall | Complete evidence | Fixed-policy pass | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|---:|
| bm25s | 1200 | 100.00% | 100.00% | 100.00% | 0 | 1045.2 |
| haystack_bm25 | 1200 | 92.50% | 91.67% | 87.50% | 0 | 969.9 |
| memvid_lex | 1200 | 0.00% | 0.00% | 0.00% | 0 | 0.0 |
| bm25s | 2400 | 100.00% | 100.00% | 100.00% | 0 | 1846.7 |
| haystack_bm25 | 2400 | 92.50% | 91.67% | 87.50% | 0 | 1884.7 |
| memvid_lex | 2400 | 0.00% | 0.00% | 0.00% | 0 | 0.0 |

Haystack is a retrieval framework component; BM25S is a lexical library; Memvid is tested only in explicit lexical mode. All three execute unmodified pinned upstream code. Each receives the same original page bodies and project scope. Indexed metadata and native tokenization remain backend-specific.

Memvid normalizes whitespace and adds known metadata framing in native hits. Every complete indexed body and frame identity is checked before the common packer restores the supplied original page. This is not a test of byte-exact Memvid native source reads.

Setup/indexing, in-worker search and process roundtrip durations are retained for diagnosis. No speed ranking or whole-product performance claim is made. Repetitions are not additional quality examples. Missing-evidence queries are reported without relabelling context as an answer.
