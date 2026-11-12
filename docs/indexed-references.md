# Optional indexed source references

An operator can configure the MCP server to encode repeated source identities
in one response-wide session table. The default `objects` format retains the
existing tool schemas, initialization instructions and response serialization.
The indexed mode preserves the original context, page IDs, warnings and every
source-reference field. It does not change retrieval or the evidence budget.

## Enable the format explicitly

```sh
memory-book mcp --source-format indexed
```

For a manually configured MCP client, append the option to the existing `mcp`
arguments, for example:

```json
{
  "command": "memory-book",
  "args": ["--db", "/absolute/path/memory.db", "mcp", "--source-format", "indexed"]
}
```

Python operators can pass `source_format="indexed"` to
`memory_book.mcp_server.create_server()` or its `serve()` helper. The HTTP reader's
`serve` command and generated client configurations remain unchanged.

The choice is fixed for the server connection. There is no new `recall_memory`
tool argument. Indexed initialization instructions explain the representation
to the connected agent; object-mode clients receive the existing instructions.

## Decode a reference

An indexed recall response adds `"source_format": "indexed-v1"` and a
`source_sessions` table. Each table row is `[project, session_id]`. Each
`source_refs` entry contains a zero-based table index and the original turn
index; detailed references retain all other fields in a third object.

```json
{
  "source_format": "indexed-v1",
  "source_sessions": [["project-a", "session-7"]],
  "results": [
    {"id": "page-example", "source_refs": [[0, 3, {"start": 10, "end": 24, "turn_start": 30, "turn_end": 44}]]}
  ]
}
```

This example shows only the reference-related fields. Expanding its reference
produces `project="project-a"`, `session_id="session-7"`, `turn_index=3`, and all
four original offsets. Additional fields such as role, message indices and
timestamps remain in the third object when present. Compact references have two
array entries because the established compact projection contains only the
three identity fields. `details=true` retains the existing detailed projection
before encoding.

Project and session ID together identify a table row, so identical session names
in different projects stay separate. Reference order and detailed duplicates
are preserved. Empty responses still declare `indexed-v1` with an empty table.
`read_page` continues to return object references in either server mode.

## Cost boundary

Default clients incur no added schema or initialization-instruction cost.
Indexed clients receive extra decoding instructions, which must be included in
first-call cost accounting. Tool schemas and tool arguments are identical in
both modes. A response with few references, including an empty response, can
cost more after adding the table and version marker. The representation is an
explicit choice, not a guarantee of savings for every call.

The separate [per-call-argument prototype](../benchmarks/experiments/indexed-references-prototype-plan.json)
motivated the operator-only design; its schema and argument overhead does not
describe this final interface. The [operator evaluation protocol](../benchmarks/experiments/indexed-references-operator-plan.json)
requires actual SDK response and initialization counts, all per-query losses,
complete reversible projections, and paired latency measurements on old
regression corpora. No response-token percentage is presented as provider
billing or final-answer accuracy.
