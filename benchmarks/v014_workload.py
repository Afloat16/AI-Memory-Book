"""Independent v0.14 experiment matrix; v0.13 frozen inputs stay unchanged.

The legacy generator is deliberately reused to replay its known adversarial
sources, with a new fixed nuisance seed and explicit absent/partial questions.
Expected evidence never enters a retrieval call. This is synthetic development
data, not the separately frozen real-project holdout.
"""

from __future__ import annotations

from copy import deepcopy

from benchmarks import v013_workload as legacy
from benchmarks.v013_workload import (CORE_PAGES, FAMILIES, GROWING,
                                      PAGES_PER_SESSION, TARGETS, digest,
                                      encoded, source_turn)

VERSION = "v014-long-history-workload-1"
SEED = 1401729


def sessions(spec, *, seed=SEED):
    yield from legacy.sessions(spec, seed=seed)


def source_for(spec, project, sid, *, seed=SEED):
    return legacy.source_for(spec, project, sid, seed=seed)


def cases(revision=0):
    output = deepcopy(legacy.cases(revision))
    for row in output:
        row["answerability"] = "answerable" if row["required"] else "unanswerable"
        row["missing_identifiers"] = ([] if row["required"] else
                                      ["distributed_all_reduce_bucket_bytes"])
    for target in TARGETS:
        spec = FAMILIES[target["family"]]
        absent = target["family"] + ".distributed_all_reduce_bucket_bytes"
        current = next(row for row in output
                       if row["id"] == target["project"] + ":current")
        for kind, query, required, answerability, stale in (
            ("missing_identifier", f"What is the current approved `{absent}` value?",
             [], "unanswerable", []),
            ("partial_identifier",
             f"What is the current `{spec['key']}` implementation contract and the approved `{absent}` value?",
             current["required"], "partial", current["stale"]),
        ):
            output.append({"id": target["project"] + ":" + kind,
                           "project": target["project"], "lifecycle": target["lifecycle"],
                           "family": target["family"], "category": kind, "surface": "recall",
                           "query": query, "required": deepcopy(required), "stale": deepcopy(stale),
                           "answerability": answerability, "missing_identifiers": [absent]})
    return output


def checkpoints(profile="main"):
    if profile not in ("main", "expanded", "development"):
        raise ValueError("Unknown registered resource profile")
    points = [
        ("age-reference-1024", "age", 896, 0, 0, "clustered", 0, None),
        ("age-shift-3650-1024", "age", 896, 0, 3650, "clustered", 0, None),
        ("age-shift-7300-1024", "age", 896, 0, 7300, "clustered", 0, None),
        ("foreign-10016", "foreign", 9888, 0, 0, "clustered", 0, "age-reference-1024"),
        ("foreign-50016", "foreign", 49888, 0, 0, "clustered", 0, "foreign-10016"),
        ("foreign-100000", "foreign", 99872, 0, 0, "clustered", 0, "foreign-50016"),
        ("own-200000", "own", 99872, 100000, 0, "clustered", 0, "foreign-100000"),
        ("interleaved-200000", "layout", 99872, 100000, 0, "interleaved", 0, None),
        ("replacement-200000", "replacement", 99872, 100000, 0, "interleaved", 1, "interleaved-200000"),
    ]
    if profile == "expanded":
        points += [
            ("foreign-350016", "foreign_extension", 249888, 100000, 0,
             "interleaved", 1, "replacement-200000"),
            ("own-500000", "own_extension", 249888, 249984, 0,
             "interleaved", 1, "foreign-350016"),
        ]
    elif profile == "development":
        # Plumbing diagnostic only: the label is carried into every manifest.
        # It cannot satisfy any registered 200k formal claim.
        points = [("development-192", "development", 32, 32, 0,
                   "interleaved", 0, None)]
    return [{"id": name, "axis": axis, "foreign_pages": foreign, "own_pages": own,
             "total_pages": CORE_PAGES + foreign + own, "shift_days": age,
             "layout": layout, "revision": revision, "parent": parent,
             "development_only": profile == "development"}
            for name, axis, foreign, own, age, layout, revision, parent in points]
