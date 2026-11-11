# Contributing

Small, evidence-backed improvements are welcome. Please keep source provenance, project isolation, bounded context, and reproducible evaluation intact.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp]"
python -m unittest discover -s tests -v
python -m benchmarks.run --split development --seed 11 --budget-chars 2000 8000
```

The core remains standard-library only. MCP is optional. Do not commit private transcripts, databases, credentials, or user identifiers. Use small synthetic reproductions for bugs.

## Retrieval changes

Compare all three segmentation modes with the same tokenizer, ranking implementation, project scope, snippet packer, and character budget. Evidence must survive into the actual returned context and match its original source. Keep failures and no-answer cases in the report. Once a heldout seed informs tuning, label it development evidence and choose a new evaluation split.

Do not call local indexing latency end-to-end model latency. Claims about another product require actually running that product under a documented fair comparison.

## Pull requests

Explain the concrete problem, changed behavior, and meaningful validation. Add regression tests for data loss, source/offset correctness, isolation, or protocol bugs. Do not add tests that only repeat implementation details. If changing the storage format, include an explicit schema migration and a fixture that demonstrates compatibility.
