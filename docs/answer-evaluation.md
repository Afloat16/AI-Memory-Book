# Paired answer evaluation with a real model

The registered local evaluation is complete: **768 actual Qwen2.5-0.5B
answer attempts**, across 128 LoCoMo and 128 HotpotQA questions with three
retrieval modes. Model/archive/runtime identity, process ownership, prepared
inputs, request/response hashes, usage and failure accounting are verified.

[Completed answer scores and costs](../benchmarks/RESULTS-local-answers.md) ·
[Separate native capture/consolidation/answer workflow](../benchmarks/RESULTS-full-workflow.md) ·
[Completion audit](continuation-status.md).

`benchmarks.answer_eval` freezes the evidence delivered by each source tree,
keeps scoring labels out of the model input, and calls an explicitly configured
real endpoint. The guide below documents that reusable process. The old
128-question readiness fixture contains no model calls and is retained only
as historical preparation evidence.

HTTP fixtures in `tests/test_answer_eval.py` verify transport and accounting;
they are separate from the actual model results. Lexical EM/F1, unsupported
exact abstention, source-evidence completeness and complete-workflow cost
have distinct definitions and reports.

## What it measures

| Stage | Recorded measurement | Boundary |
| --- | --- | --- |
| Canonical history import | One timed ingest event per session, input hash, database statistics | Book's local import; no native competitor observer |
| Retrieval | One uncached recall per question, context, original source references, source hash | Python in-process call; no MCP transport |
| Evidence packing | Exact reference-token count and packing time | Same whole-block packer and cap for every version |
| Answer generation | Answer text, model name reported by server, request/response hashes, endpoint roundtrip time | One non-streaming HTTP call; includes network and inference |
| Provider token usage | Reported input/output/total counts and supported numeric usage-detail fields | Unknown fields stay `null`; reference counts do not replace billing counts |
| Answer scoring | Normalized exact match, lexical token F1, explicit unsupported-question abstention | String-based diagnostic; no semantic judge |

Import and retrieval occur once during preparation. Repeating answer generation
does not repeat or charge those preparation events again. The runner does not
sum separately measured spans into an end-to-end wall-clock claim. Capture from
client logs, native competitor observers/consolidation, adaptive tool selection,
follow-up reads and provider billing are not measured. `full_workflow_cost` is
therefore `null`, and `full_workflow_measured` remains `false`.

## 1. Prepare a frozen pair

Install the optional benchmark dependency and prepare the reference-tokenizer
cache before going offline:

```bash
python -m pip install -e '.[benchmark]'
```

`tiktoken==0.12.0` is required. Its first tokenizer load may download the
encoding assets; use an already populated `TIKTOKEN_CACHE_DIR` for offline
preparation. No generative endpoint is called by `prepare`.

Create a separate baseline checkout, using the exact prior continuation head:

```bash
git worktree add --detach ../answer-baseline 605d74e1b76fd471def8274c2a04e96e2d095075
```

Supply an independently authored canonical file with separate source history
and expected answers. This example is only a format demonstration, not a
generalization benchmark:

```json
{
  "sessions": [
    {
      "project": "demo",
      "session_id": "cache-review",
      "created_at": "2026-01-01T12:00:00Z",
      "messages": [
        {"role": "user", "content": "What cache TTL did the review approve?"},
        {"role": "assistant", "content": "The approved cache TTL is 45 seconds."}
      ]
    }
  ],
  "queries": [
    {
      "id": "ttl",
      "query": "How long does the cache remain valid?",
      "project": "demo",
      "answerable": true,
      "answers": ["45 seconds", "45 s"]
    },
    {
      "id": "owner",
      "query": "Who is responsible for the cache?",
      "project": "demo",
      "answerable": false,
      "answers": []
    }
  ]
}
```

`answers` contains alternative acceptable **complete answers**, not fragments
of a multi-part answer. An unsupported question must explicitly set
`answerable: false` and `answers: []`. Only `sessions` are ingested: questions,
expected answers and answerability labels never enter the memory index or the
model prompt as scoring information.

After saving the cases to `.artifacts/answer-cases.json`:

```bash
python -m benchmarks.answer_eval prepare \
  --cases .artifacts/answer-cases.json \
  --source baseline=../answer-baseline/src \
  --source candidate=src \
  --tokenizer cl100k_base --budget-tokens 1024 --budget-chars 8000 \
  --cohort-label 'independently authored evaluation; describe authorship and prior exposure' \
  --output .artifacts/answer-eval/prepared.json
```

Each engine runs in an independent subprocess with the same canonical data,
query order, scope, page settings and top-five limit. The shared packer receives
only actual retrieved evidence, preserves whole source blocks and caps the
final context. Labels are not used to select evidence. Source hashes before
and after preparation must match. Dirty source trees are identified by their
actual bytes rather than attributed to a clean commit.

The evaluator, corpus loader, shared packer and scorer source files are also
hash-pinned in the prepared artifact. `run` rejects a changed harness or changed
question/answer/context bytes. After a code change, prepare a new pair and
identify it as a new experiment rather than reusing old prepared inputs.

The pinned LoCoMo adapter is also available:

```bash
python -m benchmarks.answer_eval prepare \
  --locomo-path .artifacts/data/locomo10.json \
  --split development --max-queries 128 \
  --source baseline=../answer-baseline/src --source candidate=src \
  --cohort-label 'public development regression' \
  --output .artifacts/answer-eval/locomo-prepared.json
```

This reuses the [text-evidence loader](../benchmarks/public_data.py) and its
hash-pinned file, conversation split, image exclusions and question selection.
The question's scalar `answer` supplies the scoring target; unsupported
category-5 questions require the explicit abstention marker. Non-scalar
answers are rejected rather than silently treated as alternative answers.
The existing LoCoMo questions have already been observed: a split named
`heldout` does not make them unseen again. This runner's lexical scores are
not the original LoCoMo evaluation procedure. Source data remains subject to
its [separate license](../benchmarks/locomo_split.json).

## 2. Run a real answering model

Start or select an actual served model first. The runner neither downloads nor
launches a generative model and does not assume that an embedding service can
answer questions. For a keyless local server:

```bash
python -m benchmarks.answer_eval run \
  --prepared .artifacts/answer-eval/prepared.json \
  --base-url http://127.0.0.1:1234/v1 \
  --model ACTUAL_SERVED_MODEL \
  --max-output-tokens 256 --temperature 0 \
  --output .artifacts/answer-eval/local-model-run
```

Replace `ACTUAL_SERVED_MODEL` with the server's real model identifier. For a
hosted compatible endpoint, supply an explicit HTTPS base URL, model and the
**name** of the environment variable containing its key:

```bash
python -m benchmarks.answer_eval run \
  --prepared .artifacts/answer-eval/prepared.json \
  --base-url "$ANSWER_BASE_URL" --model "$ANSWER_MODEL" \
  --api-key-env ANSWER_API_KEY \
  --output .artifacts/answer-eval/hosted-model-run
```

`run` sends the prepared questions and evidence to that endpoint. There is no
default remote host or implicit use of a provider key. Plain HTTP is accepted
only on loopback, URLs cannot embed credentials, and HTTP redirects are not
followed. Request headers and API keys are never written into the run trace.

The transport follows the standard non-streaming
[Chat Completions contract](https://developers.openai.com/api/reference/resources/chat):
`POST <base-url>/chat/completions`, `messages`, a model identifier and one textual
assistant choice. Local servers with the older output-limit field can use
`--output-token-field max_tokens`. For models that reject temperature, use
`--omit-temperature` explicitly; the resulting provider default is then not
controlled. There is no silent parameter fallback or automatic retry.

The prompt, request parameters, requested model and tokenizer remain fixed for
the whole pair. Every successful response must report the exact requested
model identifier. A different or absent identifier is a recorded error with
zero quality credit; its actual response hash and reported usage are retained.
If a provider resolves aliases to snapshot names, request the exact served
snapshot name for this evaluation.
Query-major execution rotates the engine order between questions and
repetitions to reduce a fixed first-engine ordering effect. Temperature zero
does not guarantee bitwise reproducibility. `--repeats 3` records three actual
answer attempts per question/version and their full costs. Summaries distinguish
attempt counts from unique questions; repetitions do not multiply the number
of independent questions.

## 3. Inspect the ledger and scores

The command writes a `.jsonl` trace and a `.summary.json` report. Defaults are
inside ignored `.artifacts/answer-eval`; new files use owner-only permissions
on systems that support them. Prepared contexts and raw model replies can
contain source text. They are private working artifacts, not files to commit
or redistribute automatically.

Every request writes a durable `request_started` row before HTTP and a
`request_finished` row afterward. Successful rows retain the answer text,
reported model/fingerprint, finish reason, numeric usage fields and a hash of
the complete response. Arbitrary provider diagnostics are omitted. If a
response echoes the explicit API key, the attempt is recorded as an error
without response text; numeric usage and the response hash remain. Errors and timeouts retain
their attempt, timing and unknown cost; they receive zero accuracy scores and
stay in the denominator. Error bodies are omitted to avoid recording arbitrary
server diagnostics. An interrupted request can leave a started row without a
finished row: its outcome and charge are unknown. Ordinary re-running refuses
an existing output. To continue after an interruption, repeat the identical
`run` command and output prefix with **`--resume`**. The evaluator verifies the
prepared inputs, model, endpoint, prompt, parameters and prior ledger before
making any call. Completed attempts are retained. An intent without an outcome
is recorded as `interrupted`, receives zero quality credit and keeps unknown
usage; it is never retried. Only requests without a previous intent are sent.
This preserves attempt counts and prevents a silent duplicate model charge.
A completed summary cannot be overwritten. A partial or corrupt ledger line
fails closed and must be preserved for explicit recovery.

For each usage field, the summary distinguishes the count of calls with
reported values, their **known subtotal**, and a complete total only when
every attempted call reported that field. A missing field is never zero.
Reference-token counts cover context, message text and answer text; message
text counts omit chat framing, hidden reasoning and provider-specific rules.
They are not provider usage or billed dollars. Returned model names and system
fingerprints are checked across the pair. Differing IDs mark model comparability
`incomparable`; absent identities, missing fingerprints or failed attempts mark
it `unverified`. Stable model/fingerprint reports produce `same_reported_identity`,
which still does not establish deterministic inference. Scores remain visible in every case, but a
changing or unverified backend prevents attributing their differences solely
to retrieval.

The lexical scorer applies Unicode NFKC normalization and case folding, uses
punctuation/symbol boundaries, and tokenizes Han characters individually while
keeping other letter/number runs. It does not delete English articles or
understand synonyms, morphology, fact entailment or complete reasoning. Exact
match compares the normalized token sequence; F1 measures token overlap with
the best accepted answer. For Chinese this is a character-based overlap
diagnostic, not word segmentation or a semantic score. Japanese, Thai and
other scripts are not language-specialized. Unsupported-question success
requires exactly `INSUFFICIENT_EVIDENCE` after surrounding whitespace is
trimmed; other uncertainty wording is deliberately not inferred as abstention.

Answerable exact/F1 and unsupported abstention rates are reported separately.
A low F1 can reflect alternate valid phrasing, and a high overlap score can
still describe a wrong answer. A defensible answer-quality claim additionally
needs blinded human assessment or a separately validated semantic judge and
confidence intervals. Broader cost claims still need genuine native capture,
observer/consolidation and follow-up-read traces for each compared product,
as specified in the [comparison protocol](comparison-protocol.md).

## 4. Run the registered local model with verified process ownership

The separately frozen [local answer plan](../benchmarks/experiments/local-answer-plan.json)
uses Qwen2.5-0.5B-Instruct Q4_K_M through llama.cpp b12110. Download and verify
the artifacts, prepare the registered cohorts, and use the owned launcher:

```bash
python scripts/prepare_local_answer_model.py
python -m benchmarks.local_answer_eval prepare --cohort locomo
python -m benchmarks.local_answer_eval run --cohort locomo \
  --run-prefix .artifacts/local-answer-evaluation/locomo/answers
python -m benchmarks.local_answer_eval export --cohort locomo \
  --run-prefix .artifacts/local-answer-evaluation/locomo/answers \
  --output benchmarks/results/local-answer-locomo128
```

Repeat with `--cohort hotpotqa` and distinct run/output prefixes for the other
128-question cohort. Preparation requires the pinned external source data,
baseline checkout and semantic model documented in the
[native evaluation protocol](native-budget-evaluation.md).

`local_answer_eval run` starts only the verified local binary with the exact
registered 4,096-token context, four inference threads, one slot, fixed seed,
and disabled prompt caching. It verifies the model, archive, every extracted
runtime file and library symlink, then records the actual process arguments,
startup time, log hash and exit status. It stops only the process it owns.
The `.server.json` proof binds the actual answer ledger and summary hashes to
these artifacts and settings; export rejects a missing proof, changed runtime,
edited result or unverified external endpoint. Downloaded model files alone
are insufficient evidence that an endpoint used those files.

Use the same owned `run` command with `--resume` after an interruption; existing
completed answers are never replayed. An inherited process lock prevents a
new run from overlapping a still-running orphan server. This experiment's
server settings remain separate from the 16,384-token native consolidation
workflow. Protocol fixture tests do not provide any generated-answer scores.

If interruption occurs after the final answer summary is saved but before
the server proof is finalized, keep that ledger and summary as retained
diagnostic evidence. The launcher refuses to replay completed answers, and
export refuses to invent a completed process proof. This narrow recovery case
requires an explicitly documented audit of the retained process artifacts;
it is not silently marked complete or rerun under the old output prefix.
