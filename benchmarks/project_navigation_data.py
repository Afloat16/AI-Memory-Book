"""Preregistered, authored same-topic project-isolation development workload.

Gold belongs to the evaluator. Retrieval sees only the original question and
exact project ID, and only the source prefix visible at that checkpoint.
"""
from __future__ import annotations

from benchmarks import engineering_workflow as engineering

VERSION = "same-topic-project-isolation-v1"
PROJECT_IDS = (
    "route-kernel", "route_kernel", "Route-Kernel", "route-kernel-v2",
    "route-kernel-tests", "route-kernel-prod", "route-kernel-eu", "route-kernel-us",
)
PROJECT_NAME = "Routing Kernel"
MAIN_TASK = "routing-kernel"
TASK_TITLE = "Routing numerical kernel"
SYMBOL = "routing.relaxation_limit"
NEIGHBOR_FIELDS = ("routing.cache_alignment_bytes", "routing.prefetch_window_entries")
MISSING_FIELD = "routing.approved_gpu_warp_width"
BOUNDARY = "Unreachable vertices keep an infinite distance; a negative cycle must raise ValueError."
FAILURE = "A visited-once Dijkstra prototype returned distance 2 instead of -1 for s->a=2, s->b=3, b->a=-4."


def workload():
    """80 cases, four checkpoints, eight exact but deliberately similar IDs."""
    steps = []
    for checkpoint in range(1, 5):
        sessions, cases = [], []
        for index, project in enumerate(PROJECT_IDS):
            old, new = (("reject_negative", "bellman_ford") if index % 2 == 0
                        else ("bellman_ford", "reject_negative"))
            old_fact, new_fact = f"edge_policy={old}", f"edge_policy={new}"

            def session(identity, title, answer, *, day=1, task_id=MAIN_TASK, task_title=TASK_TITLE):
                return {"project": project, "project_name": PROJECT_NAME,
                        "session_id": identity, "title": title,
                        "task_id": task_id, "task_title": task_title,
                        "created_at": f"2026-{checkpoint + 6:02d}-{day:02d}T09:00:00+00:00",
                        "messages": [{"role": "user", "content": title},
                                     {"role": "assistant", "content": answer}]}

            def case(name, query, category, required=(), stale=(), *, policy=None, neighbor=()):
                return {"id": f"p{checkpoint}:{project}:{name}", "checkpoint": checkpoint,
                        "project": project, "query": query, "category": category,
                        "required": [{"session_id": identity, "quote": quote} for identity, quote in required],
                        "stale": [{"session_id": identity, "quote": quote} for identity, quote in stale],
                        "consumer_family": "routing" if policy else None,
                        "consumer_expected_policy": policy,
                        "neighbor_evidence": list(neighbor)}

            if checkpoint == 1:
                sessions.extend([
                    session("initial-design", "Choose production routing policy",
                            f"Production routing kernel initial decision: {old_fact}. "
                            "This is the active contract until an explicit replacement is recorded."),
                    session("active-config", "Configure relaxationLimit",
                            f"Production routing configuration: {SYMBOL}={64 + index}. "
                            "This measured limit belongs to this project only.", day=2),
                    session("test-double", "Routing kernel simulation",
                            "The test double uses test_double.edge_policy=reject_negative and "
                            "test_double.relaxation_limit=4. These are simulation settings, "
                            "not a production routing decision.", day=3,
                            task_id="routing_kernel", task_title=TASK_TITLE),
                ])
                cases.extend([
                    case("initial", "What is the current edge_policy for the production routing kernel?",
                         "initial_decision", [("initial-design", old_fact)], policy=old),
                    case("identifier", "What is the value of `routing.relaxation_limit`?",
                         "code_identifier", [("active-config", f"{SYMBOL}={64 + index}")]),
                ])
            elif checkpoint == 2:
                sessions.extend([
                    session("replacement-design", "Replace production routing policy",
                            f"Approved replacement for the production routing contract: {new_fact}. "
                            "The initial decision remains history and is no longer the current requirement."),
                    session("active-config", "Configure relaxationLimit",
                            f"Production routing configuration: {SYMBOL}={128 + index}. "
                            "This measured limit belongs to this project only.", day=2),
                ])
                cases.extend([
                    case("replacement", "What is the current edge_policy for the production routing kernel?",
                         "updated_decision", [("replacement-design", new_fact)], [("initial-design", old_fact)],
                         policy=new),
                    case("historical", "What was the original edge_policy for the production routing kernel?",
                         "historical_decision", [("initial-design", old_fact)], policy=old),
                    case("config-replaced", "What is the value of `routing.relaxation_limit`?",
                         "source_replacement", [("active-config", f"{SYMBOL}={128 + index}")]),
                ])
            elif checkpoint == 3:
                sessions.extend([
                    session("boundary-review", "Review production routing boundary cases", BOUNDARY,
                            task_id="verification", task_title="Boundary checks"),
                    session("failed-prototype", "Explain the routing prototype failure", FAILURE, day=2,
                            task_id="diagnostics", task_title="Routing failure evidence"),
                ])
                cases.extend([
                    case("constraints", "What is the current edge_policy and which production routing boundary cases must pass?",
                         "multiple_constraints", [("replacement-design", new_fact), ("boundary-review", BOUNDARY)],
                         [("initial-design", old_fact)], policy=new),
                    case("failure", "Which routing prototype failure should we avoid repeating?",
                         "failed_attempt", [("failed-prototype", FAILURE)]),
                ])
            else:
                own_field = NEIGHBOR_FIELDS[index % 2]
                missing_field = NEIGHBOR_FIELDS[1 - index % 2]
                neighbor_index = index + 1 if index % 2 == 0 else index - 1
                sessions.extend([
                    session("handoff", "Resume production routing work",
                            "Resume from the recorded production decisions and failure evidence. "
                            "This handoff makes no new policy decision. "
                            f"bodyonlysentinel{index} appears only in this body."),
                    session("local-cache-setting", "Record the scoped cache setting",
                            f"Approved local setting: {own_field}={256 + index}. "
                            "This record is scoped to this project and cannot configure a neighboring project.",
                            day=2, task_id="deployment", task_title="Deployment checks"),
                ])
                cases.extend([
                    case("bilingual-gap", "当前 production routing 的 edge_policy 是什么？请找出原始工程决策。",
                         "bilingual_long_gap", [("replacement-design", new_fact)], [("initial-design", old_fact)],
                         policy=new),
                    case("missing-everywhere", f"Which approved {MISSING_FIELD} value should the production routing kernel use?",
                         "missing_evidence_global"),
                    case("missing-here", f"Which approved {missing_field} value should the production routing kernel use?",
                         "missing_evidence_neighbor", neighbor=[{
                             "project": PROJECT_IDS[neighbor_index], "session_id": "local-cache-setting",
                             "quote": f"{missing_field}={256 + neighbor_index}",
                         }]),
                ])
            for noise in range(2):
                sessions.append(session(
                    f"maintenance-{checkpoint}-{noise}", f"Routing kernel maintenance {checkpoint}-{noise}",
                    "Reviewed production routing builds, deployment caches and worker scheduling. "
                    "The edge_policy and routing.relaxation_limit names appear in logs, but this "
                    "maintenance note records no chosen values or replacement decision.", day=10 + noise,
                ))
        # Interleave projects instead of giving one book a contiguous row range.
        # This deterministic order is fixed independently of retrieval results.
        ordered = []
        per_project = {project: [s for s in sessions if s["project"] == project] for project in PROJECT_IDS}
        for ordinal in range(max(map(len, per_project.values()))):
            for project in PROJECT_IDS:
                if ordinal < len(per_project[project]):
                    ordered.append(per_project[project][ordinal])
        steps.append({"checkpoint": checkpoint, "sessions": ordered, "cases": cases})
    return steps


def validate_workload(steps=None):
    """Validate authored labels and temporal scope, without running retrieval."""
    steps = workload() if steps is None else steps
    visible, identities, counts = {}, set(), {"cases": 0, "answerable": 0, "evidence_spans": 0,
                                            "fixed_consumer": 0, "missing_global": 0, "missing_neighbor": 0}
    for step in steps:
        for source in step["sessions"]:
            assert source["project"] in PROJECT_IDS
            assert source["project_name"] == PROJECT_NAME
            assert len(source["messages"]) == 2
            assert len(engineering.original_turn(source).encode("utf-8")) <= 10000
            visible[(source["project"], source["session_id"])] = source
        originals = engineering.visible_sources(visible)
        for case in step["cases"]:
            assert case["id"] not in identities
            identities.add(case["id"])
            assert case["checkpoint"] == step["checkpoint"]
            counts["cases"] += 1
            counts["answerable"] += bool(case["required"])
            counts["evidence_spans"] += len(case["required"])
            counts["fixed_consumer"] += bool(case["consumer_family"])
            for field in ("required", "stale"):
                for evidence in case[field]:
                    assert evidence["quote"] in originals[(case["project"], evidence["session_id"], 0)]
            if case["category"] == "missing_evidence_global":
                counts["missing_global"] += 1
                assert all(MISSING_FIELD not in body for body in originals.values())
            if case["category"] == "missing_evidence_neighbor":
                counts["missing_neighbor"] += 1
                assert not case["required"] and len(case["neighbor_evidence"]) == 1
                foreign = case["neighbor_evidence"][0]
                assert foreign["project"] != case["project"]
                assert foreign["quote"] in originals[(foreign["project"], foreign["session_id"], 0)]
                field = foreign["quote"].split("=", 1)[0]
                assert all(field not in body for key, body in originals.items() if key[0] == case["project"])
    assert counts == {"cases": 80, "answerable": 64, "evidence_spans": 72,
                      "fixed_consumer": 40, "missing_global": 8, "missing_neighbor": 8}
    return counts


def directory_queries():
    """Only caller-visible metadata requests; no answer quotes enter routing."""
    return [{"id": f"directory:{project}:{kind}", "project": project, "kind": kind, "query": query}
            for index, project in enumerate(PROJECT_IDS)
            for kind, query in (("title", "Configure relaxationLimit"),
                                ("task", TASK_TITLE),
                                ("body_only", f"bodyonlysentinel{index}"),
                                ("missing", "metadataabsentqzx"))]
