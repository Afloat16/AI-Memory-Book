"""Public artifact downloads; callers must verify the pinned digest."""
from __future__ import annotations

import time
import urllib.error
import urllib.request


def fetch_bytes(url: str, *, timeout: float = 60) -> bytes:
    """Retry transient public-host failures, never digest failures or 404s."""
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "AI-Memory-Book-benchmark/1"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if attempt == 2 or error.code not in {408, 429, 500, 502, 503, 504}:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)
    raise AssertionError("unreachable")
