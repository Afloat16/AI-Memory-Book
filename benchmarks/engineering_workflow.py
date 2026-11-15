"""Synthetic, chronological engineering-memory development diagnostic.

This is an authored regression workload, not a real-user study, an LLM coding
benchmark, or an evaluation of any external memory product. Its small fixed
consumer only selects a policy from retrieved configuration statements; the
consumer's executable checks must never be reported as generated-code accuracy.

Run with a chosen runtime on PYTHONPATH::

    PYTHONPATH=src python -m benchmarks.engineering_workflow \
        --output .artifacts/engineering-development --budget-chars 1200 2400

The same evaluator can use an unmodified baseline runtime from another checkout.
The report hashes the *imported* runtime, the complete workload and this evaluator.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import sys
import tempfile
import time

VERSION = "engineering-development-v1"
BACKENDS = ("no_memory", "recent_history", "flat", "book")

# These schemas belong to the fixed consumer, not the retriever. They describe
# project contracts written in source conversations, not hidden answer labels.
POLICIES = {
    "routing": ("edge_policy", ("reject_negative", "bellman_ford")),
    "ranking": ("tie_policy", ("stable_input", "id_ascending")),
    "splitting": ("split_policy", ("row_modulo", "whole_group", "chronological")),
    "attention": ("all_masked_policy", ("uniform", "zeros")),
}
PROJECTS = (
    ("routing-online", "routing", "reject_negative", "bellman_ford"),
    ("routing-batch", "routing", "bellman_ford", "reject_negative"),
    ("ranking-online", "ranking", "stable_input", "id_ascending"),
    ("ranking-batch", "ranking", "id_ascending", "stable_input"),
    ("training-online", "splitting", "row_modulo", "whole_group"),
    ("training-batch", "splitting", "whole_group", "chronological"),
    ("attention-online", "attention", "uniform", "zeros"),
    ("attention-batch", "attention", "zeros", "uniform"),
)
FAILURES = {
    "routing": "A visited-once Dijkstra prototype returned distance 2 instead of -1 for s->a=2, s->b=3, b->a=-4.",
    "ranking": "Sorting a set of tied candidates changed the winner when the input order changed.",
    "splitting": "Splitting individual rows leaked the same patient's repeated records across training and validation.",
    "attention": "Subtracting a masked maximum of negative infinity produced NaN for a completely masked row.",
}
BOUNDARIES = {
    "routing": "Unreachable vertices keep an infinite distance; a negative cycle must raise ValueError.",
    "ranking": "A request with k=0 returns an empty list; equal scores follow the chosen tie policy.",
    "splitting": "The split is deterministic; no record may appear twice in the output partition.",
    "attention": "Masked positions are zero when an unmasked position exists; subtract the maximum before exponentiation.",
}
SYMBOLS = {
    "routing": "routing.relaxation_limit",
    "ranking": "ranking.stable_topk_buffer",
    "splitting": "training.group_split_seed",
    "attention": "attention.mask_tile_size",
}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def original_turn(session):
    """Fixture sessions contain exactly one user turn; no runtime helper used."""
    return "\n\n".join(f"{message['role'].upper()}: {message['content']}" for message in session["messages"])


def workload(noise_per_step=2):
    """Six chronological checkpoints, paired namespaces, and source replacement.

    The explicit gold remains in query records. Retrieval receives only the
    query string and project ID, and cannot access future checkpoint sessions.
    """
    if not isinstance(noise_per_step, int) or not 0 <= noise_per_step <= 100:
        raise ValueError("noise_per_step must be an integer from 0 through 100")
    steps = []
    for month in range(1, 7):
        sessions, cases = [], []
        for index, (project, family, old, new) in enumerate(PROJECTS):
            key = POLICIES[family][0]
            current = old if month < 3 else new
            old_fact, new_fact = f"{key}={old}", f"{key}={new}"
            symbol = SYMBOLS[family]
            config_value = 64 + index if month < 5 else 128 + index

            def session(identity, question, answer, day=1):
                return {"project": project, "session_id": identity,
                        "title": question, "task_id": family + "-kernel",
                        "task_title": family + " numerical kernel",
                        "created_at": f"2026-{month:02d}-{day:02d}T09:00:00+00:00",
                        "messages": [{"role": "user", "content": question},
                                     {"role": "assistant", "content": answer}]}

            def case(name, query, category, evidence=(), stale=(), consumer=False, expected=None):
                return {"id": f"m{month}:{project}:{name}", "project": project,
                        "query": query, "category": category, "checkpoint": month,
                        "required": [{"session_id": sid, "quote": quote} for sid, quote in evidence],
                        "stale": [{"session_id": sid, "quote": quote} for sid, quote in stale],
                        "consumer_family": family if consumer else None,
                        "consumer_expected_policy": expected if consumer else None}

            if month == 1:
                sessions.append(session("initial-design", f"Choose {family} kernel policy",
                    f"Initial project decision: {old_fact}. This is the active contract until an explicit replacement is recorded."))
                cases.append(case("initial", f"What is the current {key} for this {family} kernel?",
                    "initial_decision", [("initial-design", old_fact)], consumer=True, expected=old))
            elif month == 2:
                sessions.append(session("failed-prototype", f"Why did the {family} prototype fail?", FAILURES[family]))
                sessions.append(session("active-config", f"Configure {symbol}", f"Measured configuration: {symbol}={config_value}. This value is scoped to this project."))
                cases.append(case("failure", f"Which {family} prototype failure should we avoid repeating?",
                    "failed_attempt", [("failed-prototype", FAILURES[family])]))
                cases.append(case("config", f"What is the value of `{symbol}`?", "code_identifier",
                    [("active-config", f"{symbol}={config_value}")]))
            elif month == 3:
                sessions.append(session("replacement-design", f"Replace the {family} policy after review",
                    f"Approved replacement for the initial contract: {new_fact}. The original design remains useful history but is no longer the current implementation requirement."))
                cases.append(case("replacement", f"What is the current {key} for this {family} kernel?",
                    "updated_decision", [("replacement-design", new_fact)], [("initial-design", old_fact)], True, new))
            elif month == 4:
                sessions.append(session("boundary-review", f"Review {family} kernel boundary cases", BOUNDARIES[family]))
                cases.append(case("constraints", f"What is the current {key} and which {family} boundary cases must pass?",
                    "multiple_constraints", [("replacement-design", new_fact), ("boundary-review", BOUNDARIES[family])],
                    [("initial-design", old_fact)], True, new))
                cases.append(case("chinese", f"当前 {key} 的配置是什么？请找出原始工程决策。",
                    "bilingual_query", [("replacement-design", new_fact)], [("initial-design", old_fact)], True, new))
            elif month == 5:
                # Replace the same source atomically, rather than adding a
                # different ID and accidentally measuring only append behavior.
                sessions.append(session("active-config", f"Configure {symbol}", f"Measured configuration: {symbol}={config_value}. This value is scoped to this project."))
                cases.append(case("config-replaced", f"What is the value of `{symbol}`?", "source_replacement",
                    [("active-config", f"{symbol}={config_value}")]))
                cases.append(case("missing", "Which approved distributed_all_reduce_bucket_bytes value should the cluster use?",
                    "missing_evidence"))
            else:
                sessions.append(session("handoff", f"Continue the {family} kernel after a long interruption",
                    "Resume from the recorded implementation decisions and failure evidence. The project has no new policy decision in this handoff."))
                cases.append(case("long-gap", f"What is the current {key} for this {family} kernel?",
                    "long_gap", [("replacement-design", new_fact)], [("initial-design", old_fact)], True, new))
                cases.append(case("historical", f"What was the original {key} for this {family} kernel?",
                    "historical_decision", [("initial-design", old_fact)], consumer=True, expected=old))
            for noise in range(noise_per_step):
                sessions.append(session(f"maintenance-{month}-{noise}", f"{family} implementation maintenance {noise}",
                    f"Reviewed the {family} kernel benchmark, deployment cache and worker scheduling. "
                    f"The {key} and {symbol} names appear in logging, but this maintenance note records no chosen values. "
                    "The build passed a smoke check; this is not evidence for numerical correctness or a replacement decision.",
                    day=10 + noise % 18))
        steps.append({"checkpoint": month, "sessions": sessions, "cases": cases})
    return steps


def visible_sources(sessions):
    return {(s["project"], s["session_id"], 0): original_turn(s) for s in sessions.values()}


def source_errors(response, sources, project):
    """Verify returned source slices against original visible transcript text.

    Uncovered text may contain only whitespace or the excerpt ellipsis. This
    catches fabricated additions even when one valid citation is attached.
    Page IDs are never gold, and missing future/deleted sources fail validation.
    """
    errors = []
    for number, hit in enumerate(response["results"]):
        text = hit["text"]
        covered = [False] * len(text)
        if text not in response["context"]:
            errors.append(f"hit {number}: snippet absent from context")
        if not hit.get("source_refs"):
            errors.append(f"hit {number}: missing source references")
        for ref in hit.get("source_refs", []):
            identity = (ref.get("project"), ref.get("session_id"), ref.get("turn_index"))
            original = sources.get(identity)
            lo, hi = ref.get("turn_start"), ref.get("turn_end")
            if identity[0] != project:
                errors.append(f"hit {number}: cross-project source")
            if (original is None or type(lo) is not int or type(hi) is not int
                    or not 0 <= lo < hi <= len(original)):
                errors.append(f"hit {number}: invalid original source span")
                continue
            fragment = original[lo:hi]
            start = text.find(fragment)
            if start < 0 or ref.get("end", 0) - ref.get("start", 0) != hi - lo:
                errors.append(f"hit {number}: source slice does not match snippet")
                continue
            for position in range(start, start + len(fragment)):
                covered[position] = True
        if any(not seen and not character.isspace() and character != "…" for seen, character in zip(covered, text)):
            errors.append(f"hit {number}: unsupported snippet characters")
    return errors


def evidence_rank(evidence, response, sources, project):
    quote = evidence["quote"]
    if quote not in response["context"]:
        return None
    for rank, hit in enumerate(response["results"], 1):
        if quote not in hit["text"]:
            continue
        for ref in hit.get("source_refs", []):
            if (ref.get("project"), ref.get("session_id")) != (project, evidence["session_id"]):
                continue
            original = sources.get((project, evidence["session_id"], ref.get("turn_index")), "")
            lo, hi = ref.get("turn_start", 0), ref.get("turn_end", 0)
            if isinstance(lo, int) and isinstance(hi, int) and quote in original[lo:hi]:
                return rank
    return None


def recent_history(sessions, project, budget):
    """Strong simple baseline: newest project history, with a shared hard cap.

    This has no query ranking; its separate source storage is already in memory.
    Its latency is not an external memory product latency comparison.
    """
    hits, blocks, used = [], [], 0
    ordered = sorted((s for s in sessions.values() if s["project"] == project),
                     key=lambda s: (s["created_at"], s["session_id"]), reverse=True)
    for session in ordered:
        header = f"[{session['session_id']}] {project} | {session['created_at']}\n"
        remaining = budget - used - len(header) - (2 if blocks else 0)
        if remaining < 1:
            break
        original = original_turn(session)
        text = original[:remaining]
        block = header + text
        used += len(block) + (2 if blocks else 0)
        blocks.append(block)
        hits.append({"text": text, "created_at": session["created_at"], "source_refs": [{
            "project": project, "session_id": session["session_id"], "turn_index": 0,
            "start": 0, "end": len(text), "turn_start": 0, "turn_end": len(text)}]})
    return {"context": "\n\n".join(blocks), "results": hits}


def retrieve(book, backend, query, project, budget, sessions):
    # This function deliberately has no case/gold parameter.
    if backend == "no_memory":
        return {"context": "", "results": []}
    if backend == "recent_history":
        return recent_history(sessions, project, budget)
    return book.recall(query, project=project, budget_chars=budget, limit=5,
                       strategy=backend, use_cache=False)


def select_policy(family, query, response):
    """Fixed, deliberately limited consumer of returned evidence, never gold."""
    key, allowed = POLICIES[family]
    pattern = re.compile(r"\b" + re.escape(key) + r"\s*=\s*(" + "|".join(allowed) + r")\b")
    choices = []
    for rank, hit in enumerate(response["results"]):
        # Only evidence actually supplied to the consumer is eligible.
        if hit["text"] not in response["context"]:
            continue
        for match in pattern.finditer(hit["text"]):
            choices.append((hit.get("created_at", ""), -rank, match.group(1)))
    if not choices:
        return None
    if re.search(r"\boriginal\b|最初", query, re.IGNORECASE):
        return min(choices)[2]
    return max(choices)[2]


def configured_algorithm(family, policy, data):
    """Handwritten algorithm variants; retrieved text is never executed."""
    if family == "routing":
        vertices, edges, source = data
        if policy == "reject_negative" and any(weight < 0 for _, _, weight in edges):
            raise ValueError("negative edge")
        distances = {vertex: math.inf for vertex in vertices}
        distances[source] = 0
        for _ in range(len(vertices) - 1):
            changed = False
            for left, right, weight in edges:
                if distances[left] + weight < distances[right]:
                    distances[right] = distances[left] + weight
                    changed = True
            if not changed:
                break
        if any(distances[left] + weight < distances[right] for left, right, weight in edges):
            raise ValueError("negative cycle")
        return distances
    if family == "ranking":
        records, k = data
        return sorted(records, key=(lambda item: (-item[1], item[0])) if policy == "id_ascending"
                      else (lambda item: -item[1]))[:max(0, k)]
    if family == "splitting":
        rows = data  # (identity, patient/group, timestamp), in input order
        if policy == "chronological":
            ordered = sorted(rows, key=lambda item: item[2])
            return [row[0] for row in ordered[:-2]], [row[0] for row in ordered[-2:]]
        if policy == "whole_group":
            return ([row[0] for row in rows if row[1] != "patient-b"],
                    [row[0] for row in rows if row[1] == "patient-b"])
        return ([row[0] for index, row in enumerate(rows) if index % 2 == 0],
                [row[0] for index, row in enumerate(rows) if index % 2])
    values, mask = data
    if not any(mask):
        return [1 / len(values)] * len(values) if policy == "uniform" and values else [0.0] * len(values)
    largest = max(value for value, active in zip(values, mask) if active)
    exps = [math.exp(value - largest) if active else 0.0 for value, active in zip(values, mask)]
    total = sum(exps)
    return [value / total for value in exps]


def executable_checks(family, selected, expected):
    """Evaluate policy application, not autonomous implementation quality."""
    if selected is None:
        return {"selected_policy": None, "checks": 0, "passed": 0, "all_passed": False, "abstained": True}
    if family == "routing":
        vectors = [((['s', 'a', 'b', 'isolated'], [('s', 'a', 2), ('s', 'b', 3), ('b', 'a', -4)], 's'),
                    "ValueError" if expected == "reject_negative" else {'s': 0, 'a': -1, 'b': 3, 'isolated': math.inf}),
                   ((['s', 'a'], [('s', 'a', 2)], 's'), {'s': 0, 'a': 2}),
                   ((['s', 'a'], [('s', 'a', -1), ('a', 's', -1)], 's'), "ValueError")]
    elif family == "ranking":
        records = [('b', 0.8), ('a', 0.8), ('c', 0.4)]
        vectors = [((records, 1), [('a', 0.8)] if expected == "id_ascending" else [('b', 0.8)]),
                   ((records, 0), []), (([], 4), [])]
    elif family == "splitting":
        rows = [('r0', 'patient-a', 4), ('r1', 'patient-b', 1), ('r2', 'patient-b', 3), ('r3', 'patient-a', 2)]
        wanted = {"row_modulo": (['r0', 'r2'], ['r1', 'r3']),
                  "whole_group": (['r0', 'r3'], ['r1', 'r2']),
                  "chronological": (['r1', 'r3'], ['r2', 'r0'])}[expected]
        vectors = [(rows, wanted), ([], ([], []))]
    else:
        wanted = [0.5, 0.5] if expected == "uniform" else [0.0, 0.0]
        vectors = [(([3.0, -7.0], [False, False]), wanted),
                   (([1000.0, 1001.0], [True, False]), [1.0, 0.0]),
                   (([1000.0, 1000.0], [True, True]), [0.5, 0.5])]
    observations = []
    for data, wanted in vectors:
        try:
            got = configured_algorithm(family, selected, data)
        except ValueError:
            got = "ValueError"
        observations.append(got == wanted)
    return {"selected_policy": selected, "checks": len(vectors), "passed": sum(observations),
            "all_passed": all(observations), "abstained": False, "per_check_passed": observations}


def score(case, response, sources, budget):
    ranks = [evidence_rank(e, response, sources, case["project"]) for e in case["required"]]
    stale = [evidence_rank(e, response, sources, case["project"]) for e in case["stale"]]
    errors = source_errors(response, sources, case["project"])
    answerable = bool(ranks)
    matched = sum(rank is not None for rank in ranks)
    result = {"answerable": answerable, "required_evidence": len(ranks), "matched_evidence": matched,
              "complete_evidence": answerable and matched == len(ranks), "evidence_ranks": ranks,
              "stale_evidence_ranks": stale, "stale_only": any(rank is not None for rank in stale) and not matched,
              "missing_evidence_nonempty_context": not answerable and bool(response["context"]),
              "context_chars": len(response["context"]), "within_budget": len(response["context"]) <= budget,
              "source_errors": errors, "returned_blocks": len(response["results"])}
    if case["consumer_family"]:
        selected = select_policy(case["consumer_family"], case["query"], response)
        result["fixed_consumer"] = executable_checks(case["consumer_family"], selected, case["consumer_expected_policy"])
    return result


def quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["backend"], row["budget_chars"])].append(row)
    result = []
    for (backend, budget), entries in groups.items():
        quality = [entry["score"] for entry in entries]
        answerable = [value for value in quality if value["answerable"]]
        consumers = [value["fixed_consumer"] for value in quality if "fixed_consumer" in value]
        latencies = [sample for entry in entries for sample in entry["latency_ms"]]
        required = sum(value["required_evidence"] for value in quality)
        result.append({"backend": backend, "budget_chars": budget, "cases": len(entries),
            "answerable_cases": len(answerable), "evidence_recall": sum(value["matched_evidence"] for value in quality) / required if required else None,
            "complete_evidence_rate": sum(value["complete_evidence"] for value in answerable) / len(answerable) if answerable else None,
            "fixed_consumer_cases": len(consumers),
            "fixed_consumer_all_checks_pass_rate": sum(value["all_passed"] for value in consumers) / len(consumers) if consumers else None,
            "stale_only_cases": sum(value["stale_only"] for value in quality),
            "missing_evidence_nonempty_cases": sum(value["missing_evidence_nonempty_context"] for value in quality),
            "budget_violations": sum(not value["within_budget"] for value in quality),
            "source_validation_failures": sum(bool(value["source_errors"]) for value in quality),
            "mean_context_chars": statistics.mean(value["context_chars"] for value in quality),
            "retrieval_p50_ms": statistics.median(latencies), "retrieval_p95_ms": quantile(latencies, .95),
            "retrieval_samples": len(latencies), "repeat_output_changes": sum(not entry["repeat_outputs_equal"] for entry in entries)})
    return sorted(result, key=lambda item: (item["budget_chars"], item["backend"]))


def runtime_identity(memory_book):
    root = Path(inspect.getfile(memory_book)).resolve().parent
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob("*.py"))}
    return {"imported_runtime_root": str(root), "files": files, "sha256": sha(files)}


def markdown_report(report):
    lines = ["# Chronological engineering-memory development diagnostic", "",
        "**Synthetic authored regression data. No language model, real user workflow, or external memory product was evaluated.**", "",
        "The fixed consumer selects a configuration policy from returned source text and runs handwritten algorithm variants. Its pass rate is not generated-code accuracy.", "",
        f"Workload SHA-256: `{report['dataset_sha256']}`. Imported runtime SHA-256: `{report['runtime']['sha256']}`.", "",
        "All backends see the same chronological prefix and project scope. Character caps include citation text; they are not token caps. Result caching is disabled. Reported latency surrounds only local retrieval/context construction, excluding ingestion, scoring, executable checks and model generation. Repetitions are timing samples, not independent quality cases.", "",
        "| Backend | Character cap | Evidence recall | Complete evidence | Fixed consumer passes | Stale-only | p50 / p95 ms | Mean chars |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cell in report["summary"]:
        lines.append(f"| {cell['backend']} | {cell['budget_chars']} | {cell['evidence_recall']:.1%} | {cell['complete_evidence_rate']:.1%} | {cell['fixed_consumer_all_checks_pass_rate']:.1%} | {cell['stale_only_cases']} | {cell['retrieval_p50_ms']:.3f} / {cell['retrieval_p95_ms']:.3f} | {cell['mean_context_chars']:.1f} |")
    lines += ["", "## Interpretation limits", "",
        "- These fixtures are development data from their first use. They do not establish generalization, significance, real coding productivity, hallucination rates or superiority over another open-source product.",
        "- `flat` is this repository's scoped exact FTS route with the same source index and packer; it is not an implementation of another product. `recent_history` uses already resident transcript text and different storage work.",
        "- A nonempty context for a missing-answer query is a retrieval diagnostic, not evidence of an incorrect generated answer. Stale and current evidence can coexist legitimately; stale-only and executable policy checks are reported separately.",
        "- Gold quotes must survive into the returned context and the cited original source slice. Private history, credentials, model calls and network downloads are not required.",
        "- The raw JSONL retains each case, context, source references, repeated latency samples and output digests. The dataset JSON retains chronology, labels and source replacements.", ""]
    return "\n".join(lines)


def run(output, *, budgets=(1200, 2400), repeats=3, noise_per_step=2):
    import memory_book
    from memory_book import MemoryBook
    if not budgets or any(type(b) is not int or not 0 < b <= 100_000 for b in budgets):
        raise ValueError("budgets must contain positive integer caps up to 100000")
    if type(repeats) is not int or not 1 <= repeats <= 30:
        raise ValueError("repeats must be between 1 and 30")
    if len(set(budgets)) != len(budgets):
        raise ValueError("duplicate budgets are not independent cells")
    runtime_before = runtime_identity(memory_book)
    evaluator_before = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    steps = workload(noise_per_step)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("report.json", "raw.jsonl", "dataset.json")):
        raise ValueError("output already contains an experiment; choose a fresh directory")
    (output / "dataset.json").write_text(json.dumps(steps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows, ingestion, visible = [], [], {}
    ordinal = 0
    with tempfile.TemporaryDirectory(prefix="engineering-memory-") as directory, \
            MemoryBook(Path(directory) / "memory.db", cache_size=0) as book, \
            (output / "raw.jsonl").open("w", encoding="utf-8") as trace:
        for step in steps:
            started = time.perf_counter_ns()
            for session in step["sessions"]:
                book.ingest(session)
                visible[(session["project"], session["session_id"])] = session
            ingestion.append({"checkpoint": step["checkpoint"], "events": len(step["sessions"]),
                              "visible_sessions": len(visible), "elapsed_ms": (time.perf_counter_ns() - started) / 1e6})
            sources = visible_sources(visible)
            for case in step["cases"]:
                for budget in budgets:
                    measurements = {backend: {"times": [], "digests": [], "response": None} for backend in BACKENDS}
                    for repetition in range(repeats):
                        rotation = (ordinal + repetition) % len(BACKENDS)
                        order = BACKENDS[rotation:] + BACKENDS[:rotation]
                        if repetition % 2:
                            order = tuple(reversed(order))
                        for backend in order:
                            start = time.perf_counter_ns()
                            response = retrieve(book, backend, case["query"], case["project"], budget, visible)
                            elapsed = (time.perf_counter_ns() - start) / 1e6
                            stable = {key: value for key, value in response.items() if key != "latency_ms"}
                            sample = measurements[backend]
                            sample["times"].append(elapsed)
                            sample["digests"].append(sha(stable))
                            if sample["response"] is None:
                                sample["response"] = response
                    for backend, sample in measurements.items():
                        response = sample["response"]
                        row = {"case_id": case["id"], "category": case["category"], "checkpoint": case["checkpoint"],
                               "query": case["query"], "project": case["project"], "backend": backend,
                               "budget_chars": budget, "latency_ms": sample["times"], "output_sha256": sample["digests"],
                               "repeat_outputs_equal": len(set(sample["digests"])) == 1,
                               "visible_sessions": len(visible), "response": response,
                               "score": score(case, response, sources, budget)}
                        rows.append(row)
                        trace.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                        trace.flush()
                    ordinal += 1
        storage_bytes = sum(path.stat().st_size for path in Path(directory).glob("memory.db*") if path.is_file())
    runtime_after = runtime_identity(memory_book)
    evaluator_after = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report = {"version": VERSION, "status": "completed", "evidence_level": "synthetic_development_proxy",
              "created_at": datetime.now(timezone.utc).isoformat(), "dataset_sha256": sha(steps),
              "evaluator_sha256": evaluator_before, "evaluator_unchanged": evaluator_before == evaluator_after,
              "runtime": runtime_before, "runtime_unchanged": runtime_before == runtime_after,
              "runtime_final_sha256": runtime_after["sha256"],
              "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
              "settings": {"budgets_chars": list(budgets), "repeats": repeats, "noise_per_step": noise_per_step, "result_cache": False, "segmentation": "adaptive", "limit": 5},
              "projects": len(PROJECTS), "checkpoints": len(steps), "case_count": sum(len(step["cases"]) for step in steps),
              "ingestion": ingestion, "final_database_bytes_including_wal_shm": storage_bytes,
              "summary": summarize(rows), "by_category": {category: summarize([row for row in rows if row["category"] == category])
                  for category in sorted({row["category"] for row in rows})}}
    if (not report["runtime_unchanged"] or not report["evaluator_unchanged"]
            or any(cell["budget_violations"] or cell["source_validation_failures"] or cell["repeat_output_changes"] for cell in report["summary"])):
        report["status"] = "completed_with_integrity_failures"
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-chars", nargs="+", type=int, default=[1200, 2400])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--noise-per-step", type=int, default=2)
    args = parser.parse_args()
    report = run(args.output, budgets=args.budget_chars, repeats=args.repeats, noise_per_step=args.noise_per_step)
    print(json.dumps({"status": report["status"], "cases": report["case_count"], "output": str(args.output), "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
