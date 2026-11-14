# C4 pre-implementation diagnosis

These C3-only profiles and an upper-bound simulation preceded C4 implementation. They retain all 1,015 old public questions and complete payload comparisons. Profiling and SQL instrumentation add overhead; no values are accepted performance measurements.

The metadata path reads 104,728 candidate directory records but references only 27,480 unique chapter/session pairs. A conservative title-boost bound retains 46,501 candidates for metadata expansion/scoring, while preserving every observed original top-K and selected page. This is a work-count diagnostic, not a speed guarantee or new quality result. The separate C3 formal run failed two fixed speed gates and remains rejected.

The compressed files retain exact original diagnostic JSON bytes. The scripts record their original .artifacts execution locations; input data and runtime remain bound in those results. The reusable continuation and unchanged formal gates are in [the C4 addendum](../../../experiments/round5-c4-addendum.json).
