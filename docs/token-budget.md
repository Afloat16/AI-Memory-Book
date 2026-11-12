# Exact context token budgets

The development source exposes an optional exact token limit in Python, CLI,
and MCP. It uses a named reference tokenizer and retains the existing character
limit. Both limits include citations and separators in the returned `context`.
The outer JSON, tool schema, other conversation messages and model output are
outside this context budget.

## Install and initialize

From a checkout of the development branch:

```bash
git clone --branch perf/recall-quality-budget https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients,tokens]"
```

On Windows, use `.venv\Scripts\Activate.ps1`. The `tokens` extra pins
`tiktoken==0.12.0`; the `benchmark` and `all` extras also include that version.
The project is not published to PyPI, so install from the source checkout.
The dependency-free character-budget path does not initialize a tokenizer.

On its first use of an encoding, tiktoken may download its public vocabulary
if the vocabulary is absent from its local cache. The download contains no
query text, source text, or credentials. Subsequent encoding calls use the
local vocabulary. Preload both encodings during deployment to separate this
initialization from measured request latency:

```bash
python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
```

For offline deployment, preload into a persistent `TIKTOKEN_CACHE_DIR` while
network access is available, and make the same cached files available to the
offline process under that environment variable. Missing dependencies or
unavailable vocabulary initialization raise an error; no estimated-token
fallback is used for an exact budget.

## Use the same limits through each interface

```python
from memory_book import MemoryBook

with MemoryBook("memory.db") as book:
    result = book.recall(
        "cache expiry and retry window",
        project="atlas",
        budget_chars=4000,
        budget_tokens=512,
        tokenizer="cl100k_base",
    )
    assert result["context_tokens"] <= 512
    assert result["context_chars"] <= 4000
```

```bash
memory-book recall "cache expiry and retry window" --project atlas \
  --budget 4000 --budget-tokens 512 --tokenizer cl100k_base --json
```

MCP `tools/call` arguments:

```json
{
  "name": "recall_memory",
  "arguments": {
    "query": "cache expiry and retry window",
    "project": "atlas",
    "budget_chars": 4000,
    "budget_tokens": 512,
    "tokenizer": "cl100k_base"
  }
}
```

`budget_tokens` accepts integers from 0 through 100,000. Python and MCP reject
booleans, strings and fractional-number inputs; a budget of zero returns empty
context. Supported encodings are `cl100k_base` and `o200k_base`. The default
encoding is `cl100k_base`; the caller must choose the encoding appropriate for
its evaluation or model. A reference count is not provider billing.

When enabled, both compact and detailed MCP responses, and the Python result,
include `budget_tokens`, `tokenizer`, `tokenizer_version` and `context_tokens`.
`estimated_tokens` remains the older character-based estimate where that field
is exposed. Omitting `budget_tokens` retains the existing character-only
behavior and does not add the exact-token fields.

## Assembly and preservation contract

The token path uses the same scoped, ranked top-`limit` pages as character
recall. It first builds the ordinary character-budget output, then applies a
rank-order first-fit pass to its intact returned blocks: a block that does not
fit is skipped so a smaller later block can still fit. Every accepted block,
including its citation, text and source metadata, is retained unchanged.

It then tries to fill unused capacity with complete original source units from
the remaining selected pages. Units include intact lines, sentence boundaries,
short adjacent utterance spans and closed fenced code blocks. Each addition is
checked against the exact token count of the entire proposed context, including
all citation headers and separators. There is at most one result per selected
page, and no extra retrieval or generated paraphrase is used by this assembler.

Supplemental units are parsed in original turns before being projected into
pages. A page boundary inside a sentence or a code fence therefore cannot make
its fragment look like a complete new unit. Fenced code is atomic for new
additions; unclosed fences are omitted from the supplement candidates. A line
such as `USER: ``` ` inside a fenced block cannot close it. Previously accepted
legacy excerpts are preserved under the contract above.

The preservation guarantee is relative to **this version's ordinary
character-budget output followed by the same whole-block token packer**. It
does not establish non-regression against every older ranker or against the
historical full-page common-context benchmark. Those are separate comparisons.

Every returned span points to original page and turn coordinates. This path
does not solve low-overlap semantic retrieval by itself, decide which historical
statement is authoritative, or guarantee that all required evidence fits a
given budget. Smaller candidate windows can still omit useful qualifications;
read the complete page when a decision needs more context.

## Validation and costs

`tests/test_token_budget.py` checks exact caps with both encodings, independent
old-block preservation, original-source reconstruction, page/project/session
limits, literal tokenizer-special strings, cache isolation and code fences.
`tests/test_token_budget_mcp.py` exercises the real stdio SDK path, including
strict numeric validation and compact/detailed parity.

Tokenization and supplemental source-unit selection add local CPU work. Report
initial vocabulary loading separately from first uncached recall and repeated
cached recall. Measure full MCP response tokens separately from `context_tokens`.
New evidence-delivery results do not imply generated-answer accuracy or an
end-to-end cost advantage.

## Completed measurements

The [eight-cohort validation](../benchmarks/RESULTS-native-token-budget.md)
contains 24,228 query/configuration pairs, 251 complete-evidence gains, zero
complete-evidence losses and zero losses of previously fitting baseline
blocks. This includes public regression and independently authored external
questions, with every original timing boundary retained.

The [latest counting optimization](token-prefix-performance.md) preserves all
2,016 complete development payloads. Its four 512-token settings have p95
reductions of 7.73%–14.45%; all 12 settings and larger-budget tradeoffs are
published. Only the exact counting/fit-check path changes, not ranking,
source units, citation rules or context budgets.

[Real generated-answer results](../benchmarks/RESULTS-local-answers.md) are
reported separately: more delivered evidence is not automatically a higher
answer score.
