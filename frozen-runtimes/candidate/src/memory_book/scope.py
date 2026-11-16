"""Exact project identifiers for optional client-side scope assertions."""

from __future__ import annotations


def validate_project(project: str) -> str:
    """Validate an already stored ID without changing its spelling or case."""
    if not isinstance(project, str) or not project or project != project.strip():
        raise ValueError("project must be a nonempty exact ID without surrounding whitespace")
    if len(project) > 200 or "\x00" in project:
        raise ValueError("project must be at most 200 characters and contain no NUL")
    try:
        project.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("project must be valid UTF-8 text without unpaired surrogates") from exc
    return project
