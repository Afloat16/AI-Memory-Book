# Find the correct book, then recover the original evidence

An engineer can maintain several similar services, training pipelines or
algorithm implementations. Their module names, task titles and session IDs may
be identical while their contracts differ. AI-Memory-Book organizes this work
by exact identity before applying query similarity.

| Level | Meaning | How it is selected |
|---|---|---|
| Project book | One explicit engineering namespace | Exact project ID, independent of its display name |
| Task chapter | Sessions deliberately grouped by a task | Returned chapter ID; `task_id` is local to its project |
| Question section | Related turns and their continuation pages | Returned section ID or scoped directory search |
| Evidence page | A bounded piece of normalized original text | Content-bound page ID plus source coordinates |
| Original turn | The complete normalized question/response group | Project, session ID and zero-based turn index |

Directory lookup is useful when the question, task or chapter is known. Direct
scoped recall remains useful when the needed terms occur only in the body.
Neither route requires loading the entire archive. Both return addresses that
let the caller inspect more source text when the initial context is incomplete.

## Choose identity before relevance

With v0.7.0, `recall` requires an exact project or known chapter when the archive
contains multiple books. An archive with one book can select its sole project;
an empty archive returns no evidence. A repeated external session ID or a
display name is not sufficient to choose among books. Explicit empty scope
values are errors, including through HTTP.

An unknown explicit project returns no evidence. A miss never triggers a
fallback to another book. If the task really calls for cross-project research,
enable `all_projects=True` in Python/MCP, `--all-projects` in the CLI, or
`all_projects=true` in HTTP. It cannot accompany an explicit project. The result
warns that this broader search was requested even if the limit leaves one hit.

This changes earlier unscoped multi-project calls. Update those callers to
carry their known project ID or explicitly request a global search. Existing
explicit project calls keep their ranking and budget behavior.

## Run the similar-project example

The [example archive](../examples/similar-projects.json) contains two books
both displayed as **Routing Kernel**. They reuse a session ID, task name and
code symbols, while intentionally recording different policies. These are
synthetic demonstration contracts, not configuration advice.

From a release checkout, choose a new database path:

```bash
memory-book --db ./similar-projects.db import examples/similar-projects.json --format canonical
memory-book --db ./similar-projects.db projects
memory-book --db ./similar-projects.db index "routing policy" --project routing-prod
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --project routing-prod
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --project routing-eval
```

The production book records `bellman_ford` and `128`; the evaluation book
records `reject_negative` and `32`. Use the exact IDs printed by `projects`.
Calling `recall` against this two-book archive without a project raises a
selection error. A deliberate comparison is available with:

```bash
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --all-projects
```

## Locate a question without copying every answer

`search_directory` searches the existing indexed page titles, questions and
task/session directory fields. It does not search the body field. Multiple
continuation pages from one section become one directory result before the
limit, so a long answer does not occupy every directory slot.

Each entry includes the project/chapter/section/page breadcrumb, a matched
page address, a bounded summary, page count and source references. Use
`next_offset` to continue the result list. An absent directory match does not
establish absent evidence: use scoped `recall` when terms may occur only inside
an answer. Directory metadata is not a substitute for reading source evidence.

```python
from memory_book import MemoryBook

with MemoryBook("./similar-projects.db") as book:
    directory = book.search_directory("routing policy", "routing-prod", limit=20)
    for entry in directory["entries"]:
        print(entry["title"], entry["page_count"], entry["breadcrumb"])
```

The project filter is applied inside the query before section grouping and
pagination. A directory response uses one SQLite read snapshot, including its
counts and addresses. Separate pagination requests can observe later archive
revisions; compare `revision` and restart a directory listing if it changes.

## Carry the selected book through every follow-up

An opaque page ID may be valid but belong to another open project. Pass the
expected project to `chapter`, `section` and `read` to catch that mistake.
Wrong-book IDs raise a not-found error and return no foreign content.

```python
with MemoryBook("./similar-projects.db") as book:
    index = book.search_directory("negative-edge", "routing-prod")
    entry = index["entries"][0]
    chapter = book.chapter(entry["chapter_id"], project="routing-prod")
    section = book.section(entry["section_id"], project="routing-prod")
    page = book.read(entry["matched_page_id"], project="routing-prod")
```

CLI equivalents add `--project routing-prod` to `chapter`, `section` and
`read`. MCP uses the optional `project` argument on `browse_chapter`,
`browse_section` and `read_page`; HTTP accepts it on the corresponding routes.
The reader keeps the selected project on follow-up requests and displays IDs
next to identical book names. Existing ID-only reads remain available; provide
the guard when the caller already knows the expected book.

## Read the complete original turn, including its tail

`read_page.next_offset` continues that one page. It does not mean the complete
original turn fits in that page. Follow a returned source reference into
`read_turn` to read the full normalized turn directly, regardless of how many
pages the archive created for it.

```python
with MemoryBook("./similar-projects.db") as book:
    index = book.search_directory("negative-edge", "routing-prod")
    page = book.read(index["entries"][0]["matched_page_id"], project="routing-prod")
    ref = page["source_refs"][0]
    offset = 0
    while offset is not None:
        chunk = book.read_turn(
            ref["project"], ref["session_id"], ref["turn_index"],
            offset=offset, limit=1200, source_hash=page["source_hash"],
        )
        print(chunk["content"], end="")
        offset = chunk["next_offset"]
```

The `source_hash` identifies the stored session version. Carry it from the
page into the first turn read and every continuation. If that session changes,
the call raises instead of joining text from two versions; obtain the new
source reference and restart at offset zero. The guard is optional for a fresh
read but necessary when the caller wants version-consistent continuation.

`limit` bounds returned `content` characters, not all JSON metadata. The
question preview is bounded to 240 characters. `source_ref.turn_start` and
`turn_end` locate the chunk inside the normalized original turn; its
`message_indices` identify the source messages. These are character offsets,
not byte positions in the vendor's transcript file. Role labels are retained.

CLI: `memory-book turn PROJECT SESSION TURN --offset 0 --limit 1200
--source-hash HASH`. MCP: `read_source_turn`. HTTP: `/api/turn` with
`project`, `session_id`, `turn_index`, optional offsets and `source_hash`.

## Keep capture and project assignment explicit

Supported metadata capture derives workspace identities from normalized full
workspace paths with a hash suffix, so equal directory basenames do not merge
by name alone. Canonical imports retain their explicit project IDs. Ambiguous
or missing workspace metadata is reported rather than guessed. An explicit
capture-project override assigns that source to the chosen book, so configure
it with the actual repository/workspace boundary; later retrieval cannot undo
incorrect project labels supplied at ingestion.

Project filtering and navigation guards prevent accidental mixing in one local
archive. They are not authentication or multi-user access control. The service
does not know which repository a caller intends unless that identity is supplied
or there is only one possible book. Archived text remains untrusted historical
evidence: inspect dates and provenance, reconcile conflicting decisions, and run
the target project's own tests before treating a remembered contract as current.
