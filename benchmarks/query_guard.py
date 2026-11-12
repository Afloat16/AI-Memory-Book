"""Fail before measurement when an explicit cohort has the wrong size."""

from __future__ import annotations


def require_query_count(dataset, expected: int | None) -> None:
    if expected is None:
        return
    if type(expected) is not int or expected < 1:
        raise ValueError("expected_queries must be a positive integer")
    queries = getattr(dataset, "queries", dataset)
    actual = len(queries)
    if actual != expected:
        raise ValueError(f"Expected {expected} queries, selected {actual}; refusing to measure the wrong cohort")
    ids = [case["id"] if isinstance(case, dict) else case.id for case in queries]
    if len(ids) != len(set(ids)):
        raise ValueError("Query IDs must be unique, even when question text repeats")
