# C6 preparation: observe unchanged C5 MCP work

C5 completed its sole formal run and remains rejected: aggregate p95 improved
15.220791%, best public native token p95 improved 15.422173%, and actual public
MCP token1024 improved 6.673181%, below the fixed 10% gate. This directory retains
a separately registered mechanism observation; it is not another C5 timing run.

The plan pins unchanged C5 source, the exact official SDK, the complete original
public round-0 MCP token1024 order, and every expected full payload/envelope hash.
Exactly 1,015 actual SDK calls are planned, without a second native retrieval.
Normal query-result cache reads/writes, source validation and all first calls
remain. A transparent diagnostic Connection subclass records original SQL
templates and order; Python profiling only counts JSON loads and input sizes.
No elapsed times or performance scores are recorded.

Offline replay considers all fixed statement-cache capacities 128, 256, 512 and
1,024. This models application template reuse; it does not observe actual SQLite
compilation, FTS-internal statements, busy prepared statements or schema-driven
invalidations. Any product change or capacity choice still needs a separate C6
registration before implementation and its own fixed formal acceptance.

`mcp-lifecycle.json` is a static review of the actual installed SDK, event-loop
context inheritance and current tests. It distinguishes code-derived connection
reuse expectations from the real-process evidence to be collected here.

## Reproduction and interruption boundary

The original prepared script directory is `.artifacts/round5-c6-diagnostic/`.
Copy `plan.json`, `diagnostic.py` and `sitecustomize.py` back to that path in a
checkout before reproducing; the script deliberately resolves the repository
from this directory. Materialize the exact pinned source and original database
copy, adjust only machine-specific absolute paths in a separately identified
reproduction plan, and retain its hash. The original attempt is exclusive and
never overwrites or retries `observation-01`. All input hashes and source identity
are checked before and after the planned observation.

At this checkpoint the files are prepared, not executed. Any observations,
failures and complete raw traces will be saved separately; no result is implied.


## Complete observation, including the negative result

The first prepared harness stopped before starting an SDK process or issuing a
retrieval because a frozen helper received a list instead of its dataset object.
All original bytes and the zero-call failure are retained in `observation-01/`.
The isolated repair and new output namespace were committed at
`df3eb6bdf33c49f5eb0eb289c50d0437f9332f13` before execution.

The repaired observation completed all **1,015** fixed actual-SDK calls, matching
every original compact MCP, envelope and full native payload hash, with all
source/index/revision/budget invariants preserved. There was **one connection
open and one close on the same thread**, confirming reuse in this actual run.

The trace contains **20,464 application SQL executions and 97 distinct original
templates**. Every modeled capacity (128 / 256 / 512 / 1,024) has exactly
20,367 hits, 97 compulsory misses and **zero repeated misses**. This negative
result provides no basis for enlarging the statement cache or reshaping IN lists.
No such product change is selected. The cache model remains distinct from real
SQLite compilation and FTS internal work.

The same source-reference JSON was parsed **5,073 times / 3,542,467 input bytes**
in the snapshot, then the same totals again in `_refs`. Original-turn reads
issued **4,289 SQL statements**. These are work counts, not latency savings.
A separately registered candidate may batch the same exact source-turn pairs
and reuse parsed references only within their original request/snapshot while
retaining full validation and custom/malformed fallbacks.

`observation-02/receipt.json` hashes every complete raw trace, call ledger and
all four capacity models; gzip preserves their original bytes. No duration or
new performance acceptance is collected by this diagnostic.
