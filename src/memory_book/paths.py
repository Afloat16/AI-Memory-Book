"""Stable per-user paths shared by CLI, MCP clients, and background services."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from collections.abc import Mapping


def data_dir(*, home: Path | str | None = None, platform: str | None = None,
             environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    target = sys.platform if platform is None else platform
    if env.get("MEMORY_BOOK_HOME"):
        return Path(env["MEMORY_BOOK_HOME"]).expanduser().absolute()
    if target == "win32":
        base = Path(env.get("LOCALAPPDATA", str(user_home / "AppData" / "Local")))
        return base / "AI-Memory-Book"
    if target == "darwin":
        return user_home / "Library" / "Application Support" / "AI-Memory-Book"
    return Path(env.get("XDG_DATA_HOME", str(user_home / ".local" / "share"))) / "ai-memory-book"


def default_database() -> Path:
    override = os.environ.get("MEMORY_BOOK_DB")
    return Path(override).expanduser().absolute() if override else data_dir() / "memory.db"


def default_config() -> Path:
    override = os.environ.get("MEMORY_BOOK_CONFIG")
    return Path(override).expanduser().absolute() if override else data_dir() / "config.json"
