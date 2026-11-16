"""Select equivalent text-loop implementations once, outside request timing.

The environment switch is for reproducibility and portability. It never changes
retrieval policy. A forced native run must not silently measure Python instead.
"""

from __future__ import annotations

import os


REQUESTED_BACKEND = os.environ.get("MEMORY_BOOK_TEXT_BACKEND", "auto")
if REQUESTED_BACKEND not in {"auto", "python", "native"}:
    raise ValueError("MEMORY_BOOK_TEXT_BACKEND must be auto, python or native")

NATIVE = None
if REQUESTED_BACKEND != "python":
    try:
        from . import _native as NATIVE
    except (ImportError, OSError) as error:
        if REQUESTED_BACKEND == "native":
            raise RuntimeError(
                "The native text backend was requested but is unavailable. "
                "Install a compatible native wheel or build the extension; "
                "use MEMORY_BOOK_TEXT_BACKEND=python for the reference implementation."
            ) from error

BACKEND_NAME = "native" if NATIVE is not None else "python"
