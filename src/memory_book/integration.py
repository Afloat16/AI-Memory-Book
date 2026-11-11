"""Installation-time wiring and diagnostics; no client is modified on import."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import signal
import sqlite3
import sys
import threading
from dataclasses import replace
from pathlib import Path

from . import __version__
from .paths import default_config, default_database


def absolute_workspace(value: str | None) -> str | None:
    if value is None:
        return None
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"):
        return value
    return str(Path(value).expanduser().absolute())


def get_config(path: Path | str, database: str | Path | None = None):
    from .sync import SyncConfig, load_config
    config_path = Path(path).expanduser().absolute()
    if config_path.exists():
        config = load_config(config_path)
        return replace(config, database=Path(database).expanduser().absolute()) if database else config
    return SyncConfig(
        database=Path(database).expanduser().absolute() if database else default_database(),
        state_path=config_path.parent / "sync-state.json",
        log_path=config_path.parent / "sync.log.jsonl",
    )


def capture_source(client: str, *, source_path: str | Path | None = None,
                   project: str | None = None, workspace: str | None = None,
                   home: Path | None = None, environ: dict | None = None):
    """Create an opt-in source specification; does not read transcript files."""
    from .sync import WatchSource
    user_home = Path.home() if home is None else Path(home)
    env = os.environ if environ is None else environ
    if client == "claude-code":
        path = Path(env.get("CLAUDE_CONFIG_DIR", str(user_home / ".claude"))) / "projects"
        format_name, project_mode = "claude-code", "metadata"
    elif client == "codex":
        path = Path(env.get("CODEX_HOME", str(user_home / ".codex"))) / "sessions"
        format_name, project_mode = "codex", "metadata"
    elif client == "gemini":
        path = user_home / ".gemini" / "tmp"
        format_name, project_mode = "gemini", "subdirectory"
    elif client == "kimi-legacy":
        path = Path(env.get("KIMI_SHARE_DIR", str(user_home / ".kimi"))) / "sessions"
        format_name, project_mode = "kimi-legacy", "subdirectory"
    else:
        raise ValueError(f"Automatic transcript capture is not available for {client}. MCP recall still works; use explicit import or a verified watch source.")
    if source_path:
        path = Path(source_path).expanduser().absolute()
    if workspace and project_mode == "subdirectory":
        raise ValueError(f"{client} transcripts do not reliably record a workspace path. Select that workspace's transcript directory with --source and name it with --project instead.")
    # Re-running setup with a narrower path/workspace replaces that client's
    # previous capture scope. It must not leave a broader source running.
    source_id = client + "-capture"
    return WatchSource(id=source_id, path=path.expanduser().absolute(), format=format_name,
                       project=project, project_mode="explicit" if project else project_mode,
                       project_prefix=None, workspace=absolute_workspace(workspace))


def setup_clients(names: list[str], *, config_path: str | Path | None = None,
                  client_config_path: str | Path | None = None,
                  database: str | Path | None = None, writable: bool = False,
                  capture: bool = False, source_path: str | None = None,
                  workspace: str | None = None, project: str | None = None,
                  background: bool = False, dry_run: bool = False,
                  replace_existing: bool = False, home: Path | None = None,
                  platform: str | None = None, environ: dict | None = None,
                  capture_supported_only: bool = False) -> dict:
    from .clients import CLIENT_CAPTURE, apply_plan, plan_client
    from .sync import save_config
    if not names:
        raise ValueError("Choose a client with --client <name>; use 'memory-book clients' to list supported profiles")
    names = list(dict.fromkeys(names))
    if (client_config_path or source_path) and len(names) != 1:
        raise ValueError("--client-config and --source each require exactly one client")
    if (source_path or workspace or project) and not capture:
        raise ValueError("--source, --workspace and --project require --capture")
    if background and not capture:
        # Existing watch sources can still be started without adding duplicates.
        existing = get_config(config_path or default_config(), database)
        if not existing.sources:
            raise ValueError("Use --capture with --background, or add watch sources first")
    config_file = Path(config_path or default_config()).expanduser().absolute()
    if config_file.is_symlink():
        raise ValueError("Select the real background config path instead of a symlink")
    config = get_config(config_file, database)
    if config_file in {config.database, config.state_path, config.log_path}:
        raise ValueError("The background config must be separate from database, state, and log files")
    # Resolve every plan and source before applying any client configuration.
    plans = [plan_client(name, config.database, sys.executable,
                         argument_prefix=("-m", "memory_book"), config_path=client_config_path,
                         writable=writable, replace=replace_existing, home=home,
                         platform=platform, environ=environ) for name in names]
    plans = list({plan.profile: plan for plan in plans}.values())
    protected_paths = {path.resolve() for path in (config_file, config.database, config.state_path, config.log_path) if path is not None}
    protected_paths.update(Path(str(config.database) + suffix).resolve() for suffix in ("-wal", "-shm", "-journal"))
    if any(plan.config_path is not None and plan.config_path.resolve() in protected_paths for plan in plans):
        raise ValueError("Client configuration must be separate from the memory database and background config/state/log files")
    capture_names = [plan.profile for plan in plans]
    skipped_capture = []
    if capture and capture_supported_only:
        skipped_capture = [name for name in capture_names if name not in CLIENT_CAPTURE]
        capture_names = [name for name in capture_names if name in CLIENT_CAPTURE]
    added = [capture_source(name, source_path=source_path, project=project, workspace=workspace,
                            home=home, environ=environ) for name in capture_names] if capture else []
    sources = {source.id: source for source in config.sources}
    sources.update({source.id: source for source in added})
    config = replace(config, sources=tuple(sources.values()))
    result = {"version": __version__, "ok": True, "database": str(config.database),
              "background_config": str(config_file), "dry_run": dry_run,
              "reader_enabled": config.reader_enabled,
              "clients": [plan.as_dict() for plan in plans],
              "capture_sources": [{"id": s.id, "path": str(s.path), "format": s.format,
                                   "project": s.project, "project_mode": s.project_mode,
                                   "workspace": s.workspace, "exists": s.path.exists()} for s in added],
              "notes": ["Restart the selected client or refresh its MCP servers.",
                        "Client trust/permission prompts remain controlled by that client."]}
    if capture:
        result["notes"].append("Capture reads existing and future supported text transcripts in the displayed paths. Files stay local; your model receives evidence when its client calls a memory tool.")
    if skipped_capture:
        result["notes"].append("MCP only; no verified automatic capture adapter: " + ", ".join(skipped_capture))
    if dry_run:
        return result
    if importlib.util.find_spec("mcp") is None:
        raise RuntimeError("Client integration requires the MCP extra. Re-run the installer, or install '.[mcp,clients]' from this checkout.")
    result["clients"] = [apply_plan(plan) for plan in plans]
    save_config(config, config_file)
    if background:
        from .service import manage_service
        try:
            result["service"] = manage_service("install", config_file)
        except (ValueError, OSError, RuntimeError) as exc:
            result["ok"] = False
            result["service"] = {"ok": False, "error": str(exc)}
            result["notes"].append("Client configuration was saved; the background service did not start. Run 'memory-book daemon --config <displayed config>' under your process supervisor.")
    elif capture:
        result["notes"].append("Capture is configured. Run 'memory-book service install' for background collection, or 'memory-book sync --once' for one pass.")
    return result


def doctor(config_path: str | Path | None = None, *, database: str | Path | None = None) -> dict:
    from .clients import discover_clients
    from .sync import sync_status
    config_file = Path(config_path or default_config()).expanduser().absolute()
    config = get_config(config_file, database)
    fts_error = None
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE diagnostic USING fts5(text)")
    except sqlite3.Error as exc:
        fts_error = type(exc).__name__
    finally:
        connection.close()
    candidate = config.database.parent
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    writable = os.access(candidate, os.W_OK)
    legacy = Path.cwd() / ".memory-book" / "memory.db"
    warnings = []
    if legacy.is_file() and legacy.absolute() != config.database.absolute():
        warnings.append(f"A v0.1 local database exists at {legacy}. It was not moved. Use --db with that exact path, or export/import it into the shared database.")
    if importlib.util.find_spec("mcp") is None:
        warnings.append("MCP optional dependency is not installed; the core CLI and reader still work.")
    return {"version": __version__, "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
            "fts5": fts_error is None, "database": str(config.database), "database_exists": config.database.is_file(),
            "database_parent_writable": writable, "config": str(config_file), "config_exists": config_file.is_file(),
            "mcp_installed": importlib.util.find_spec("mcp") is not None,
            "tomlkit_installed": importlib.util.find_spec("tomlkit") is not None,
            "capture": sync_status(config), "clients": discover_clients(),
            "warnings": warnings, "ok": fts_error is None and writable}


def run_daemon(config_path: str | Path, *, container_bind: bool = False,
               reader_enabled: bool | None = None,
               database: str | Path | None = None) -> None:
    from .store import MemoryBook
    from .sync import load_config, watch
    from .web import make_server
    path = Path(config_path).expanduser().absolute()
    stop = threading.Event()
    cycle = {"stop": threading.Event()}

    def stop_all(*_):
        stop.set()
        cycle["stop"].set()

    def signature():
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, getattr(stat, "st_ino", 0)

    old_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, stop_all)
    try:
        while not stop.is_set():
            original_signature = signature()
            config = load_config(path)
            if database is not None:
                config = replace(config, database=Path(database).expanduser().absolute())
            with MemoryBook(config.database):
                pass
            cycle_stop = threading.Event()
            cycle["stop"] = cycle_stop
            changed = threading.Event()
            server = None
            reader_thread = None

            def monitor_config():
                # Reload scope changes even with a long configured polling
                # interval. Invalid/deleted config stops the old capture too.
                while not cycle_stop.wait(0.25):
                    if stop.is_set():
                        cycle_stop.set()
                        return
                    try:
                        current = signature()
                    except OSError:
                        current = None
                    if current != original_signature:
                        changed.set()
                        cycle_stop.set()
                        return

            monitor = threading.Thread(target=monitor_config, name="memory-book-config", daemon=True)
            monitor.start()
            try:
                if (config.reader_enabled if reader_enabled is None else reader_enabled):
                    server = make_server(config.database, host=config.reader_host, port=config.reader_port,
                                         container_bind=container_bind)
                    reader_thread = threading.Thread(target=server.serve_forever, name="memory-book-reader", daemon=True)
                    reader_thread.start()
                    if sys.stderr is not None:
                        print(f"AI-Memory-Book reader: {server.reader_url}", file=sys.stderr)
                watch(config, stop_event=cycle_stop)
            finally:
                cycle_stop.set()
                monitor.join(timeout=2)
                if server:
                    server.shutdown()
                    server.server_close()
                if reader_thread:
                    reader_thread.join(timeout=5)
            if not changed.is_set():
                break
    finally:
        stop_all()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
