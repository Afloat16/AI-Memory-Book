"""Prospective authored accuracy diagnostics; no production data or holdout claim.

The older v012 workload stays unchanged. Labels are evaluator inputs only.
Each scenario is duplicated in two exact project namespaces with distinct
values, so namesake task/session IDs cannot silently borrow another project.
"""
from __future__ import annotations

import copy


def workload():
    scenarios = []
    projects = (("service", "service-copy"), ("cache", "cache/child"),
                ("MODEL", "model"), ("生产工程", "生产工程-实验"))

    def add(name, category, records, query, *, expected=None, quote=None,
            kind="answerable", status="comparable_declaration", occurrences=False,
            required=None):
        pair = projects[len(scenarios) % len(projects)]
        sessions, cases = [], []
        for side, project in enumerate(pair):
            values = {"old": str(30 + 100 * side), "new": str(12 + 100 * side),
                      "wrong": str(99 + 100 * side)}
            by_id = {}
            for sid, body, date in records:
                text = body.format(**values)
                by_id[sid] = text
                sessions.append({"project": project, "session_id": sid,
                    "task_id": "shared-task", "task_title": "Engineering configuration",
                    "title": "Configuration record", "created_at": date,
                    "messages": [{"role": "assistant", "content": text}]})
            evidence = ([{"session_id": sid, "quote": text.format(**values)}
                         for sid, text in required] if required else
                        [{"session_id": expected, "quote": (quote or by_id[expected]).format(**values)}]
                        if expected else [])
            cases.append({"id": name + ":" + str(side), "project": project,
                "query": query, "category": category, "kind": kind,
                "expected_first_session": expected if kind == "answerable" else None,
                "required": evidence, "expected_assessment": status,
                "expected_preserve_occurrences": occurrences})
        scenarios.append({"id": name, "sessions": sessions, "cases": cases})

    old = "2026-01-01T00:00:00Z"
    new = "2026-06-01T00:00:00Z"
    latest = "2026-10-01T00:00:00Z"
    zh_old = "生产环境重试次数是 {old}。"
    zh_query = "当前生产环境的重试次数是多少？"
    for name, newer in (
        ("zh-aspect-yi", "生产环境重试次数已调整为 {new}。"),
        ("zh-aspect-yijing", "生产环境重试次数已经调整为 {new}。"),
        ("zh-aspect-xianyi", "生产环境重试次数现已设置为 {new}。"),
    ):
        add(name, "chinese_parameter_revision", [("decision", zh_old, old),
            ("revision", newer, new)], zh_query, expected="revision")
    for name, subject in (("zh-max-retry-count", "生产环境最大重试次数"),
                          ("zh-retry-count-ceiling", "生产环境重试次数上限"),
                          ("zh-training-iterations", "训练迭代次数")):
        add(name, "chinese_parameter_revision", [
            ("decision", subject + "是 {old}。", old),
            ("revision", subject + "已调整为 {new}。", new)],
            "当前" + subject + "是多少？", expected="revision")

    # Neither aspect stripping nor a matching title may erase negation, a
    # proposal, a different environment, another field or a scope suffix.
    for name, newer in (
        ("zh-negative", "生产环境重试次数未调整为 {wrong}。"),
        ("zh-pending", "生产环境重试次数拟调整为 {wrong}，仍待审批。"),
        ("zh-condition", "如果批准，生产环境重试次数已调整为 {wrong}。"),
        ("zh-suffix-scope", "生产环境重试次数已调整为 {wrong}，仅用于测试环境。"),
        ("zh-other-environment", "测试环境重试次数已调整为 {wrong}。生产环境仍待审批。"),
        ("zh-other-field", "生产环境重试间隔已调整为 {wrong}。重试次数仍待讨论。"),
    ):
        add(name, "chinese_negative_scope", [("decision", zh_old + " 生产环境重试次数。" * 8, old),
            ("proposal", newer, latest)], zh_query, expected="decision", quote=zh_old)

    fact = "Production retry_limit={old}."
    agenda = ("Production retry_limit remains on the review agenda. No value was decided. "
              + "production retry_limit review. " * 12)
    add("high-relevance-agenda", "explicit_nondecision_priority", [("decision", fact, old),
        ("agenda", agenda, latest)], "current production retry_limit", expected="decision")
    add("high-relevance-pending", "explicit_nondecision_priority", [("decision", fact, old),
        ("pending", "Production retry_limit remains pending approval; no new value was selected. "
         + "production retry_limit review. " * 12, latest)],
        "current production retry_limit", expected="decision")
    add("agenda-does-not-borrow-staging", "explicit_nondecision_scope", [
        ("decision", fact, old), ("agenda", agenda, latest),
        ("staging", "Staging retry_limit={wrong}. Production review is pending.", new)],
        "current production retry_limit", expected="decision", quote=fact)
    add("agenda-and-other-field", "missing_comparable_field", [
        ("agenda", "Production lease_duration remains on the agenda. No value was decided.", latest),
        ("different", "Production retry_limit={new}.", new)],
        "current production lease_duration", kind="missing", status="no_comparable_declaration")
    add("agenda-only", "missing_comparable_field", [("agenda", agenda, latest)],
        "current production retry_limit", kind="missing", status="no_comparable_declaration")
    add("missing-query", "no_matching_evidence", [("unrelated", "worker_pool_size={old}.", old)],
        "current distributed_all_reduce_bucket_bytes", kind="missing", status="no_matching_evidence")

    add("equal-time-distinct-values", "same_time_ambiguity", [("decision", fact, old),
        ("revision", "Production retry_limit={new}.", old)],
        "current production retry_limit", kind="conflict", status="potential_conflict",
        required=[("decision", fact), ("revision", "Production retry_limit={new}.")])
    add("equal-time-identical-values", "same_time_control", [("decision", fact, old),
        ("duplicate", fact, old)], "current production retry_limit", kind="control")
    add("ordered-revision", "same_time_control", [("decision", fact, old),
        ("revision", "Production retry_limit={new}.", new)],
        "current production retry_limit", expected="revision")
    add("equal-time-different-environments", "same_time_scope_control", [
        ("decision", fact + " production retry_limit. " * 8, old),
        ("staging", "Staging retry_limit={wrong}.", old)],
        "current production retry_limit", expected="decision", quote=fact)
    add("equal-time-different-fields", "same_time_scope_control", [
        ("decision", fact, old), ("unrelated", "Production lease_duration={wrong}.", old)],
        "current production retry_limit", expected="decision", quote=fact)
    add("equal-time-pending-value", "same_time_scope_control", [
        ("decision", fact + " production retry_limit. " * 8, old),
        ("pending", "Production retry_limit={wrong} if approved; approval is pending.", old)],
        "current production retry_limit", expected="decision", quote=fact)

    add("explicit-chinese-occurrences", "occurrence_control", [
        ("one", zh_old, old), ("two", zh_old, new), ("three", zh_old, latest)],
        "当前生产环境重试次数的出现次数", kind="control", status="not_assessed",
        occurrences=True, required=[("one", zh_old), ("two", zh_old), ("three", zh_old)])
    add("explicit-chinese-timeline", "occurrence_control", [
        ("decision", zh_old, old), ("revision", "生产环境重试次数已调整为 {new}。", new)],
        "当前生产环境重试次数的变更时间线", kind="control", status="not_assessed",
        occurrences=True)
    add("historical-parameter", "historical_control", [
        ("decision", zh_old + " 生产环境重试次数。" * 8, old),
        ("revision", "生产环境重试次数已调整为 {new}。", new)],
        "最初生产环境重试次数是多少？", kind="control", status="not_assessed")

    occurrence = next(s for s in scenarios if s["id"] == "explicit-chinese-occurrences")
    original_cases = list(occurrence["cases"])
    for label, query in (("how-many-retries", "当前生产环境重试发生了多少次？"),
                         ("count-retries", "统计生产环境重试次数"),
                         ("each-retry", "当前生产环境每次重试")):
        for index, source in enumerate(original_cases):
            case = copy.deepcopy(source)
            case.update(id=label + ":" + str(index), query=query)
            occurrence["cases"].append(case)

    for scenario in scenarios[:2]:
        case = copy.deepcopy(scenario["cases"][0])
        case.update(id=scenario["id"] + ":unknown-project", project="absent-project",
                    category="unknown_project", kind="empty_scope", expected_first_session=None,
                    required=[], expected_assessment="no_matching_evidence")
        scenario["cases"].append(case)
    return scenarios
