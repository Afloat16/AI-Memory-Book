"""Prospective authored development cases, not an independent holdout.

Gold/session labels are consumed only by the evaluator, never by retrieval.
The legacy engineering workload and its common whole-block packer are unchanged.
"""
from __future__ import annotations

import copy


def workload():
    """Return separate small archives and fixed questions with explicit evidence."""
    scenarios = []
    pairs = (("workers", "workers-copy"), ("cache", "cache/child"),
             ("service", "SERVICE"), ("模型", "模型-实验"))

    def add(name, category, old, later, query, *, expected="revision", quote=None,
            repeats=1, other=(), missing=False, conflict=False):
        pair = pairs[len(scenarios) % len(pairs)]
        sessions, cases = [], []
        for side, project in enumerate(pair):
            # The same identifiers/task names occur in both projects, but the
            # recorded values differ. No private conversation is used.
            values = {"old": str(30 + side * 100), "new": str(12 + side * 100),
                      "wrong": str(99 + side * 100)}
            records = [("decision" if i == 0 else f"decision-{i}", old.format(**values), "01")
                       for i in range(repeats)]
            if later is not None:
                records.append(("revision", later.format(**values), "06"))
            records.extend((sid, text.format(**values), month) for sid, text, month in other)
            for sid, text, month in records:
                sessions.append({"project": project, "session_id": sid, "task_id": "shared-task",
                                 "task_title": "Engineering configuration", "title": "Configuration record",
                                 "created_at": f"2026-{month}-01T00:00:00Z",
                                 "messages": [{"role": "assistant", "content": text}]})
            required = [] if missing else [{"session_id": expected,
                "quote": (quote or (later if expected == "revision" else old)).format(**values)}]
            if conflict:
                required = [{"session_id": "decision", "quote": old.format(**values)},
                            {"session_id": "revision", "quote": later.format(**values)}]
            cases.append({"id": name + ":" + str(side), "project": project,
                          "query": query, "category": category,
                          "kind": "missing" if missing else "conflict" if conflict else "answerable",
                          "expected_first_session": None if missing or conflict else expected,
                          "required": required})
        scenarios.append({"id": name, "sessions": sessions, "cases": cases})

    add("numeric-revision", "declared_revision", "lease_duration={old}.", "lease_duration={new}.",
        "current lease_duration")
    add("snake-policy", "declared_revision", "split_policy=row_modulo.",
        "Approved replacement: split_policy=group_stratified.",
        "What is the current split_policy?", quote="split_policy=group_stratified")
    add("natural-prose", "natural_language", "Production retry limit is {old}.",
        "Production retry limit is now {new}.", "current production retry limit")
    add("qualified-revision", "declared_revision", "Production buffer_capacity={old}.",
        "Production buffer_capacity={new}.", "current production buffer_capacity")
    add("camel-identifier", "code_identifier", "workerRetryLimit={old}.",
        "workerRetryLimit={new}.", "current workerRetryLimit")
    add("dotted-identifier", "code_identifier", "worker.retry_limit={old}.",
        "worker.retry_limit={new}.", "current worker.retry_limit")
    add("bilingual-identifier", "bilingual", "retry_limit={old}。", "retry_limit={new}。",
        "当前 retry_limit 是多少？")
    add("chinese-prose", "bilingual", "生产环境重试次数是 {old}。",
        "生产环境重试次数已调整为 {new}。", "当前生产环境的重试次数是多少？")
    add("agenda", "unclassified_agenda", "Retry limit is {old}. " + "retry limit. " * 8,
        "The retry limit will be discussed at the upcoming meeting; no value was decided. "
        + "Administrative scheduling follows. " * 24,
        "current retry limit", expected="decision", quote="Retry limit is {old}.")
    add("example", "unsupported_declaration", "retry_limit={old}. " + "retry_limit. " * 8,
        "Example: retry_limit={wrong}. " + "Administrative scheduling follows. " * 24,
        "current retry_limit", expected="decision", quote="retry_limit={old}")
    add("code-example", "unsupported_declaration", "retry_limit={old}. " + "retry_limit. " * 8,
        "An example, not a chosen configuration:\n```python\nretry_limit={wrong}\n```\n"
        + "Administrative scheduling follows. " * 24,
        "current retry_limit", expected="decision", quote="retry_limit={old}")
    add("cross-sentence-facet", "facet_association", "Production lease_duration={old}. "
        + "production lease_duration. " * 8,
        "Staging lease_duration={wrong}. The production review remains open. "
        + "Administrative scheduling follows. " * 24,
        "current production lease_duration", expected="decision", quote="Production lease_duration={old}.")
    add("per-field-facet", "facet_association",
        "Production lease_duration={old}. Production max_connections={old}. "
        + "production lease_duration max_connections. " * 8,
        "Production max_connections={new}. Staging lease_duration={wrong}. "
        + "Administrative scheduling follows. " * 24,
        "current production lease_duration max_connections", expected="decision",
        quote="Production lease_duration={old}. Production max_connections={old}.")
    add("suffix-facet", "facet_association", "Production batch_size={old}. "
        + "production batch_size. " * 8,
        "Production batch_size={wrong} for staging. " + "Administrative scheduling follows. " * 24,
        "current production batch_size", expected="decision", quote="Production batch_size={old}.")
    add("crowded-revision", "crowded_revision", "flush_interval={old}. " + "flush_interval. " * 12,
        "flush_interval={new}.", "current flush_interval", repeats=104)
    add("crowded-facet", "crowded_revision", "Production flush_interval={old}. "
        + "production flush_interval. " * 12, "Production flush_interval={new}.",
        "current production flush_interval", repeats=104,
        other=(("staging", "Staging flush_interval={wrong}. Production meeting pending.", "10"),))
    add("missing-value", "missing_evidence", "worker_pool_size={old}. No cluster byte limit was approved.",
        None, "current approved distributed_all_reduce_bucket_bytes", missing=True)
    add("same-time-conflict", "conflicting_records", "Production queue_depth={old}.",
        "Production queue_depth={new}.", "current production queue_depth", conflict=True)
    for source in scenarios[-1]["sessions"]:
        source["created_at"] = "2026-01-01T00:00:00Z"
    # Unknown project IDs must not silently fall back to another book.
    for scenario in scenarios[:2]:
        case = copy.deepcopy(scenario["cases"][0])
        case.update(id=scenario["id"] + ":unknown-project", project="absent-project",
                    category="unknown_project", kind="empty_scope", expected_first_session=None, required=[])
        scenario["cases"].append(case)
    return scenarios


def original_sources(scenario):
    return {(s["project"], s["session_id"], 0): "ASSISTANT: " + s["messages"][0]["content"]
            for s in scenario["sessions"]}
