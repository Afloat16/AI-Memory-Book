# Memory for algorithm and engineering development

Use AI-Memory-Book to recover the constraints, failed approaches and decision
changes that a coding task depends on. Keep the project scope explicit, inspect
the cited original text, then run the project's own tests against the recovered
contract. The archive supplies evidence; it does not execute experiments or
decide whether a recorded conclusion is correct.

The identifier improvements, token-only correction handling, `backup`, and
`check-database` described here are available from the **current main source**.
The published release installer is separate; use a source checkout to try these
changes:

```bash
git clone https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients,tokens]"
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. The `tokens` extra is
needed only for exact token budgets; lexical recall and database maintenance
use the standard library. Before opening an existing archive, follow the
[source-upgrade procedure](deployment.md#current-main-and-schema-4).

## Try a complete local workflow

The [example archive](../examples/engineering-workflow.json) contains five
synthetic sessions across four projects. It records illustrative project
policies, not measured model performance or recommended production settings.
Run these commands from the checkout with a new demo database:

```bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db projects
memory-book --db ./demo-memory.db recall "current shortest-path policy and failed approach" --project routing-demo
memory-book --db ./demo-memory.db recall "jsonl_reader input contract and split" --project training-demo
memory-book --db ./demo-memory.db recall "http_parser" --project gateway-demo
memory-book --db ./demo-memory.db recall "current kv_cache block_size" --project inference-demo
```

| Development task | Evidence to recover | Why it matters when continuing work |
|---|---|---|
| Algorithm implementation | The negative-edge input contract, the Bellman-Ford decision and why the visited-once prototype failed | An old implementation choice can become invalid when the input contract changes |
| Training data preparation | Required `JSONLReader` fields, sample isolation, chronological splitting and train-only normalization | Multiple constraints must survive together before changing a loader or evaluation script |
| API and service development | The `HTTPParser` rejection behavior and recorded boundary cases | Searching with a different naming convention should still lead to the original interface contract |
| Inference experiments | The current `KVCache` block size, superseded value and reason for the change | A bare parameter value loses the workload and memory assumptions that justified it |
| Parallel projects | `inference-demo` uses 32; a different `gateway-demo` test double uses 256 | Identical session names and symbols must remain scoped to the selected project |

The final inference query should contain the current value `32` and its recorded
reason. It may also contain `128` as explicitly superseded history when the full
page fits. It must not borrow the gateway project's value `256`.

Repeating the import with unchanged content skips the existing sessions. Keep
stable `project`, `session_id`, and `task_id` values in your own canonical input;
an updated session is replaced transactionally, and evidence from different
projects remains separate. Importing a list is a series of session transactions,
not one all-or-nothing transaction for the entire file.

## Query symbols, decisions and failures

The lexical index recognizes code naming variants such as `HTTPParser`,
`HttpParser`, `httpParser`, `http_parser`, and `HTTP_PARSER`. Acronyms and digit
boundaries also support names such as `XMLHttpRequest`, `parseHTTPResponse`,
`HTTP2Parser`, and their corresponding snake-case forms. Both ingestion and
queries use compatible aliases; the original source text and offsets are not
rewritten. Qualified-name or path separators are not concatenated across
components.

This is lexical normalization. It does not infer that unrelated names describe
the same function, translate Chinese into English, or resolve a repository's
complete symbol graph. Include a distinctive symbol and the concrete constraint
you need, for example `JSONLReader sample_id split`, and scope the query to its
project.

Use `current`, `latest`, `当前`, or `最新` when asking for a present decision.
Current-turn preference compares matching turns in the same source session and
authenticates an extract against the original turn before using it. A later
message from a different session is not automatically treated as an authoritative
replacement. For an earlier decision, ask an explicitly historical question:

```bash
memory-book --db ./demo-memory.db recall "historical initial KVCache block_size" --project inference-demo
memory-book --db ./demo-memory.db recall "shortest-path failed prototype negative edge" --project routing-demo
```

For your own experiments, record the dataset or revision, seed, split, metric,
units, configuration, result and reason for accepting or rejecting an approach.
Those details become searchable evidence only if they are actually present in
the imported conversation. Store large model outputs and datasets in their
normal artifact system and record their identifiers or paths in the discussion.

## Read the evidence before applying it

Default recall returns at most five results in a 2400-character `context`,
including citation headings and separators. Request JSON to inspect each
result's `id`, `source_refs`, `excerpt_spans`, and truncation status:

```bash
memory-book --db ./demo-memory.db recall "http_parser" --project gateway-demo --json
memory-book --db ./demo-memory.db source gateway-demo parser-contract
```

Pass an actual returned page ID to `memory-book --db ./demo-memory.db read PAGE_ID`.
`read` returns source references for the requested window; follow `next_offset`
when the page exceeds that window. `source` returns the normalized source
session. It preserves supported text, not every vendor's original multimodal
payload. Page addresses remain stable during this index migration; replacing
source content can create different page addresses.

The Python interface exposes the same evidence without a shell wrapper:

```python
from memory_book import MemoryBook

with MemoryBook("demo-memory.db") as book:
    result = book.recall("http_parser", project="gateway-demo")
    print(result["context"])
    for hit in result["results"]:
        page = book.read(hit["id"])
        for ref in hit["source_refs"]:
            source = book.get_session(ref["project"], ref["session_id"])
            print(page["id"], ref, source["session_id"])
```

An empty response can mean no lexical match or insufficient space for a complete
evidence unit. A nonempty response can still be missing a required constraint.
Check the source and the task's tests; neither outcome establishes correctness
by itself.

## Use exact tokens when the host needs them

Character and token caps apply to the same assembled context, including its
citations. The current-turn restriction also applies when a complete page fits
the character allowance but does not fit the token cap. Complete pages remain
unchanged when both caps fit; tight budgets can still return no suitable unit.

```bash
memory-book --db ./demo-memory.db recall "current KVCache block_size" --project inference-demo --budget 2400 --budget-tokens 160 --tokenizer cl100k_base --json
```

The JSON response reports the exact `context_tokens` count for the named
reference tokenizer. These limits exclude the outer JSON, tool schema, other
messages and generated answer. They are not a provider billing estimate.
Vocabulary initialization may need a one-time download; see
[offline tokenizer preparation and supported encodings](token-budget.md).

For client integration, run `memory-book --db ABSOLUTE_DATABASE_PATH setup
--client CLIENT_PROFILE` using the installed source environment. Add
`--capture --background` only when you want collection and the selected profile
supports it. The [integration guide](integrations.md) lists those capabilities.
Restart the client after configuration changes. The host and model decide when
to call MCP tools; connecting the server alone does not guarantee recall.

## Maintain and move the archive

```bash
memory-book --db ./demo-memory.db backup --output ./backups/demo-snapshot.db
memory-book --db ./backups/demo-snapshot.db check-database
memory-book --db ./backups/demo-snapshot.db backup --output ./recovery/demo-memory.db
memory-book --db ./recovery/demo-memory.db recall "current KVCache block_size" --project inference-demo
```

Choose new snapshot and recovery paths each time. Online backup includes
committed WAL data, verifies the resulting SQLite snapshot and refuses to
overwrite an existing output. A snapshot is independent of the running source;
future source writes are not added to it. Database checks do not migrate or
repair their input. Inspect the returned state and warnings as well as SQLite
integrity results. Normal recall on a recovery copy can migrate that copy.

Before switching your clients, verify known evidence in the new working copy,
then stop capture, update the configured database path and restart all clients.
Backups contain conversation text but exclude capture settings, client settings,
logs, original transcript files and optional model files. Project filtering is
a retrieval boundary, not authorization between mutually untrusted users.
See [backup and recovery details](deployment.md#back-up-and-check-the-archive).

## Validate changes to retrieval

Run the targeted regressions and the existing engineering replay from the
checkout. The replay needs no coding model:

```bash
python -m unittest tests.test_identifier_recall tests.test_current_token_recall tests.test_index_migration tests.test_maintenance -v
python -m benchmarks.engineering_workflow --output ./validation/workflow --repeats 3 --budget-chars 1200 2400
```

The [common-page component comparison](engineering-memory-evaluation.md) also
runs a pinned open-source search kernel and needs Node.js. Keep its whole-page
packing rules separate from native excerpts. Preserve all budgets, failures,
source-validation outcomes and missing-evidence cases. These synthetic
development checks exercise retrieval behavior; they do not measure LLM coding
accuracy, production throughput, or general superiority over another product.
