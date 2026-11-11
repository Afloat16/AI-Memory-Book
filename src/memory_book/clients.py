"""Plan and install local MCP client configuration without reading chat history.

Only the named configuration file is read. JSON configuration is merged as strict
JSON; JSONC is deliberately left for the client's editor so comments are never
silently discarded. Codex's TOML uses the optional ``tomlkit`` package to preserve
comments. Plans expose only our new server entry, never the rest of a config
file, which may contain credentials.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVER_NAME = "memory-book"
MANAGED_ENV = "AI_MEMORY_BOOK_MANAGED"
MANAGED_VALUE = "ai-memory-book/v1"
MAX_CONFIG_BYTES = 4 * 1024 * 1024


class ConfigError(ValueError):
    """An unsafe or unsupported merge, with an optional safe manual snippet."""

    def __init__(self, message: str, *, snippet: str | None = None):
        super().__init__(message)
        self.snippet = snippet


@dataclass(frozen=True)
class _Profile:
    name: str
    label: str
    format: str
    container: tuple[str, ...]
    docs_url: str
    command: str | None = None
    notes: tuple[str, ...] = ()
    explicit_stdio: bool = False


_PROFILES = {
    item.name: item for item in (
        _Profile(
            "claude-code", "Claude Code", "json", ("mcpServers",),
            "https://code.claude.com/docs/en/mcp", "claude",
            ("User scope. A project .mcp.json can be selected with config_path.",),
            explicit_stdio=True,
        ),
        _Profile(
            "claude-desktop", "Claude Desktop", "json", ("mcpServers",),
            "https://modelcontextprotocol.io/docs/develop/connect-local-servers",
            notes=("Restart Claude Desktop after changing local MCP configuration.",),
        ),
        _Profile(
            "codex", "Codex CLI / desktop / IDE", "toml", ("mcp_servers",),
            "https://developers.openai.com/codex/mcp/", "codex",
            ("User scope. Project .codex/config.toml requires a trusted project.",),
        ),
        _Profile(
            "gemini", "Gemini CLI", "json", ("mcpServers",),
            "https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md", "gemini",
            ("Existing tool trust, allowlists, and exclusions remain in effect.",),
        ),
        _Profile(
            "kimi", "Kimi Code (current)", "json", ("mcpServers",),
            "https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp", "kimi",
            ("Current Node Kimi Code uses ~/.kimi-code; the legacy Python CLI uses kimi-legacy.",),
        ),
        _Profile(
            "kimi-legacy", "Kimi CLI (legacy Python)", "json", ("mcpServers",),
            "https://github.com/MoonshotAI/kimi-cli/blob/main/docs/en/customization/mcp.md", "kimi",
            ("Legacy Python CLI only; the current Kimi Code uses the kimi profile.",),
        ),
        _Profile(
            "cursor", "Cursor", "json", ("mcpServers",),
            "https://cursor.com/docs/mcp", "cursor",
            ("User scope. Project .cursor/mcp.json can be selected with config_path.",),
            explicit_stdio=True,
        ),
        _Profile(
            "opencode", "OpenCode v2", "json", ("mcp", "servers"),
            "https://opencode.ai/docs/mcp-servers/", "opencode",
            ("Current v2 schema uses mcp.servers. JSONC requires a manual merge.",
             "DeepSeek can be used through this MCP-capable host; the model API is not an MCP host."),
        ),
        _Profile(
            "copilot-cli", "GitHub Copilot CLI", "json", ("mcpServers",),
            "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers", "copilot",
            ("Copilot CLI uses type=local. This is separate from VS Code's MCP configuration.",),
        ),
        _Profile(
            "qwen-code", "Qwen Code", "json", ("mcpServers",),
            "https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/", "qwen",
            ("Existing MCP tool trust, allowlists, and exclusions remain in effect.",),
        ),
        _Profile(
            "lm-studio", "LM Studio", "json", ("mcpServers",),
            "https://lmstudio.ai/docs/app/mcp", "lms",
            ("Select a tool-capable model and enable the server in LM Studio's integrations UI.",),
        ),
        _Profile(
            "generic-json", "Generic MCP JSON snippet", "json", ("mcpServers",),
            "https://modelcontextprotocol.io/docs/develop/connect-local-servers",
            notes=("Export only. Adapt this snippet to your host's documented configuration.",
                   "For DeepSeek, select the MCP host you use. No standalone DeepSeek config path is assumed."),
        ),
    )
}
_ALIASES = {
    "claude": "claude-code", "gemini-cli": "gemini", "kimi-code": "kimi", "generic": "generic-json",
    "copilot": "copilot-cli", "qwen": "qwen-code", "lmstudio": "lm-studio",
}

# Locations are suggestions for an explicitly selected source, not an instruction
# to scan a user's whole history. Current Kimi Code has no verified transcript
# schema here; its session_index.jsonl is metadata and must not be imported.
CLIENT_CAPTURE = {
    "claude-code": {
        "format": "claude-code", "root_path": "~/.claude/projects", "patterns": ["*.jsonl"],
        "docs_url": "https://code.claude.com/docs/en/sessions",
        "note": "Select one project's directory. The native transcript schema is internal and version dependent.",
    },
    "codex": {
        "format": "codex", "root_path": "~/.codex/sessions", "patterns": ["rollout-*.jsonl"],
        "docs_url": "https://learn.chatgpt.com/docs/reference/troubleshooting",
        "note": "Choose an explicit source and project mapping; the date folders may contain multiple projects.",
    },
    "gemini": {
        "format": "gemini", "root_path": "~/.gemini/tmp", "patterns": ["session-*.json", "session-*.jsonl"],
        "docs_url": "https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/session-management.md",
        "note": "Select the project's chats directory; current JSONL requires replaying patches and rewinds.",
    },
    "kimi-legacy": {
        "format": "kimi-legacy", "root_path": "~/.kimi/sessions", "patterns": ["context.jsonl"],
        "docs_url": "https://github.com/MoonshotAI/kimi-cli/blob/main/CHANGELOG.md",
        "note": "Legacy Python CLI only. Select one working-directory bucket; rotated files are not active transcripts.",
    },
}


@dataclass(frozen=True)
class ClientPlan:
    """A read-only plan. Use ``as_dict`` when showing it to a user.

    Private fields retain the exact planned bytes for compare-before-write. Do
    not serialize this object with dataclasses.asdict: a complete client config
    can contain credentials. ``as_dict`` deliberately omits those fields.
    """

    profile: str
    config_path: Path | None
    action: str
    changed: bool
    entry: dict[str, Any] | None
    snippet: str
    notes: tuple[str, ...]
    docs_url: str
    _expected_hash: str | None = field(repr=False)
    _new_bytes: bytes | None = field(repr=False)
    _expected_mode: int | None = field(repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "config_path": str(self.config_path) if self.config_path is not None else None,
            "action": self.action,
            "changed": self.changed,
            "server_name": SERVER_NAME,
            "entry": copy.deepcopy(self.entry),
            "snippet": self.snippet,
            "notes": list(self.notes),
            "docs_url": self.docs_url,
        }


def profiles() -> list[dict[str, Any]]:
    """List supported schemas without examining any files or processes."""
    return [
        {"name": p.name, "label": p.label, "format": p.format,
         "export_only": p.name == "generic-json", "docs_url": p.docs_url,
         "notes": list(p.notes), "capture": copy.deepcopy(CLIENT_CAPTURE.get(p.name))}
        for p in _PROFILES.values()
    ]


def _profile(name: str) -> _Profile:
    name = _ALIASES.get(name, name)
    if name == "deepseek":
        raise ConfigError("DeepSeek is a model/provider choice here. Select its MCP host (for example opencode, codex, or claude-code), or generic-json for a manual snippet.")
    try:
        return _PROFILES[name]
    except KeyError:
        raise ConfigError(f"Unknown client profile {name!r}. Supported: {', '.join(_PROFILES)}") from None


def _absolute_path(value: str | os.PathLike[str], home: Path, label: str) -> Path:
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ConfigError(f"{label} must be a nonempty filesystem path")
    if raw == "~":
        path = home
    elif raw.startswith("~/") or raw.startswith("~\\"):
        path = home / raw[2:]
    elif raw.startswith("~"):
        raise ConfigError(f"{label}: named-user home expansion is not supported; use an absolute path")
    else:
        path = Path(raw)
    # Do not resolve symlinks here: the caller must see a symlink and decline an
    # automatic edit, instead of replacing a dotfile manager's link unnoticed.
    return Path(os.path.abspath(path))


def _settings(home: str | os.PathLike[str] | None, platform: str | None,
              environ: Mapping[str, str] | None) -> tuple[Path, str, Mapping[str, str]]:
    base = Path(home) if home is not None else Path.home()
    base = Path(os.path.abspath(base))
    return base, (platform or sys.platform).lower(), os.environ if environ is None else environ


def _config_path(p: _Profile, custom: str | os.PathLike[str] | None,
                 home: Path, platform: str, env: Mapping[str, str]) -> Path | None:
    if p.name == "generic-json":
        if custom is not None:
            raise ConfigError("generic-json exports a snippet only; use a named client profile with config_path to merge a file")
        return None
    if custom is not None:
        return _absolute_path(custom, home, "config_path")
    if p.name == "claude-code":
        return (_absolute_path(env["CLAUDE_CONFIG_DIR"], home, "CLAUDE_CONFIG_DIR") / ".claude.json"
                if env.get("CLAUDE_CONFIG_DIR") else home / ".claude.json")
    if p.name == "claude-desktop":
        if platform.startswith("win"):
            base = _absolute_path(env["APPDATA"], home, "APPDATA") if env.get("APPDATA") else home / "AppData" / "Roaming"
            return base / "Claude" / "claude_desktop_config.json"
        if platform in {"darwin", "macos"}:
            return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        return home / ".config" / "Claude" / "claude_desktop_config.json"
    if p.name == "codex":
        base = _absolute_path(env["CODEX_HOME"], home, "CODEX_HOME") if env.get("CODEX_HOME") else home / ".codex"
        return base / "config.toml"
    if p.name == "gemini":
        return home / ".gemini" / "settings.json"
    if p.name == "kimi":
        base = _absolute_path(env["KIMI_CODE_HOME"], home, "KIMI_CODE_HOME") if env.get("KIMI_CODE_HOME") else home / ".kimi-code"
        return base / "mcp.json"
    if p.name == "kimi-legacy":
        return home / ".kimi" / "mcp.json"
    if p.name == "cursor":
        return home / ".cursor" / "mcp.json"
    if p.name == "copilot-cli":
        base = _absolute_path(env["COPILOT_HOME"], home, "COPILOT_HOME") if env.get("COPILOT_HOME") else home / ".copilot"
        return base / "mcp-config.json"
    if p.name == "qwen-code":
        return home / ".qwen" / "settings.json"
    if p.name == "lm-studio":
        return home / ".lmstudio" / "mcp.json"
    if p.name == "opencode":
        base = _absolute_path(env["XDG_CONFIG_HOME"], home, "XDG_CONFIG_HOME") if env.get("XDG_CONFIG_HOME") else home / ".config"
        candidates = [base / "opencode" / "opencode.json", base / "opencode" / "opencode.jsonc"]
        existing = [path for path in candidates if path.exists() or path.is_symlink()]
        if len(existing) > 1:
            raise ConfigError("Both opencode.json and opencode.jsonc exist; specify config_path so the intended file is explicit")
        return existing[0] if existing else candidates[0]
    raise AssertionError(p.name)


def discover_clients(*, home: str | os.PathLike[str] | None = None,
                     platform: str | None = None,
                     environ: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Report known config paths and CLI availability; never read their contents.

    A present config or executable is only a discovery hint, not evidence that
    a particular client version is installed or that the host accepted MCP.
    """
    base, system, env = _settings(home, platform, environ)
    found = []
    for p in _PROFILES.values():
        error = None
        try:
            path = _config_path(p, None, base, system, env)
        except ConfigError as exc:
            path, error = None, str(exc)
        executable = shutil.which(p.command, path=env.get("PATH", "")) if p.command else None
        item = {
            "id": p.name, "profile": p.name, "label": p.label,
            "config_path": str(path) if path is not None else None,
            "config_exists": bool(path is not None and (path.exists() or path.is_symlink())),
            "executable": executable, "docs_url": p.docs_url,
            "export_only": p.name == "generic-json", "notes": list(p.notes),
        }
        # A shared `kimi` executable cannot identify the legacy Python edition.
        item["detected"] = item["config_exists"] or bool(executable and p.name != "kimi-legacy")
        capture = copy.deepcopy(CLIENT_CAPTURE.get(p.name))
        if capture is not None:
            if p.name == "claude-code" and env.get("CLAUDE_CONFIG_DIR"):
                capture_root = _absolute_path(env["CLAUDE_CONFIG_DIR"], base, "CLAUDE_CONFIG_DIR") / "projects"
            elif p.name == "codex" and env.get("CODEX_HOME"):
                capture_root = _absolute_path(env["CODEX_HOME"], base, "CODEX_HOME") / "sessions"
            else:
                capture_root = _absolute_path(capture["root_path"], base, "capture path")
            capture["root_path"] = str(capture_root)
        item["capture"] = capture
        if error:
            item["error"] = error
        found.append(item)
    return found


def _read_config(path: Path) -> tuple[bytes | None, int | None]:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ConfigError(f"Refusing to replace a symlink: {path}. Select its real target with config_path instead.")
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError(f"Client config must be a regular file: {path}")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ConfigError(f"Client config must be a regular file: {path}")
            raw = source.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                raise ConfigError(f"Client config exceeds {MAX_CONFIG_BYTES} bytes; merge the snippet manually")
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        raise ConfigError(f"Cannot read client config {path}: {exc.strerror}") from None
    return raw, stat.S_IMODE(info.st_mode)


def _hash(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("Duplicate JSON keys cannot be merged safely; correct the file or merge the snippet manually")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ConfigError(f"Nonstandard JSON constant {value} cannot be merged safely")


def _tomlkit() -> Any:
    try:
        import tomlkit
    except ImportError:
        raise ConfigError('Codex configuration needs the clients extra: install AI-Memory-Book with "[mcp,clients]" (or install tomlkit).') from None
    return tomlkit


def _parse(raw: bytes | None, p: _Profile, snippet: str) -> Any:
    try:
        text = raw.decode("utf-8-sig") if raw is not None else ""
    except UnicodeDecodeError:
        raise ConfigError("Client configuration must be UTF-8; merge the snippet with the client's editor", snippet=snippet) from None
    if p.format == "toml":
        tomlkit = _tomlkit()
        try:
            return tomlkit.parse(text)
        except Exception:
            # Parser messages can echo credential-bearing source lines.
            raise ConfigError("Invalid TOML configuration; correct it before installing MCP", snippet=snippet) from None
    try:
        parsed = json.loads(text, object_pairs_hook=_json_object, parse_constant=_invalid_constant) if raw is not None else {}
    except (ValueError, ConfigError) as exc:
        if isinstance(exc, ConfigError):
            raise ConfigError(str(exc), snippet=snippet) from None
        raise ConfigError("Configuration is not strict JSON. JSONC comments/trailing commas and malformed JSON are not auto-edited; merge the provided snippet in the client's configuration editor.", snippet=snippet) from None
    if not isinstance(parsed, dict):
        raise ConfigError("Client configuration must be a JSON object", snippet=snippet)
    return parsed


def _container(document: Any, p: _Profile, *, create: bool) -> Any | None:
    if p.name == "opencode" and isinstance(document.get("mcp"), Mapping):
        for key, value in document["mcp"].items():
            if key != "servers" and isinstance(value, Mapping) and value.get("type") in {"local", "remote"} and ("command" in value or "url" in value):
                raise ConfigError("This configuration uses the OpenCode v1 MCP layout. The opencode profile targets v2 (mcp.servers); migrate with OpenCode's official guide before automatic setup.")
    current = document
    for key in p.container:
        if key not in current:
            if not create:
                return None
            current[key] = _tomlkit().table() if p.format == "toml" else {}
        child = current[key]
        if not isinstance(child, Mapping):
            raise ConfigError(f"The {'.'.join(p.container)} configuration container must be an object/table")
        current = child
    return current


def _entry(p: _Profile, command: str, args: list[str]) -> dict[str, Any]:
    if p.name == "opencode":
        return {"type": "local", "command": [command, *args], "environment": {MANAGED_ENV: MANAGED_VALUE}}
    result: dict[str, Any] = {"command": command, "args": args, "env": {MANAGED_ENV: MANAGED_VALUE}}
    if p.name == "copilot-cli":
        result = {"type": "local", **result, "tools": ["*"]}
    if p.explicit_stdio:
        result = {"type": "stdio", **result}
    return result


def _snippet(p: _Profile, entry: dict[str, Any]) -> str:
    if p.format == "toml":
        # All generated values are JSON strings or arrays of strings, whose
        # escaping is also valid TOML. This export does not need tomlkit.
        return (f"[mcp_servers.{SERVER_NAME}]\n"
                f"command = {json.dumps(entry['command'], ensure_ascii=False)}\n"
                f"args = {json.dumps(entry['args'], ensure_ascii=False)}\n\n"
                f"[mcp_servers.{SERVER_NAME}.env]\n"
                f"{MANAGED_ENV} = {json.dumps(MANAGED_VALUE)}\n")
    wrapped: Any = {SERVER_NAME: entry}
    for key in reversed(p.container):
        wrapped = {key: wrapped}
    return json.dumps(wrapped, ensure_ascii=False, indent=2) + "\n"


def _owned(entry: Any, p: _Profile) -> bool:
    if not isinstance(entry, Mapping) or "url" in entry:
        return False
    environment = entry.get("environment" if p.name == "opencode" else "env")
    if not isinstance(environment, Mapping) or environment.get(MANAGED_ENV) != MANAGED_VALUE:
        return False
    if p.name == "opencode":
        command = entry.get("command")
        if entry.get("type") != "local" or not isinstance(command, Sequence) or isinstance(command, (str, bytes)) or not command:
            return False
        executable, args = command[0], list(command[1:])
    else:
        expected_type = "local" if p.name == "copilot-cli" else "stdio"
        if entry.get("type", expected_type) != expected_type:
            return False
        executable, args = entry.get("command"), entry.get("args")
        if not isinstance(args, Sequence) or isinstance(args, (str, bytes)):
            return False
        args = list(args)
    if not isinstance(executable, str) or not executable or not all(isinstance(arg, str) for arg in args):
        return False
    if args and args[-1] == "--allow-write":
        args.pop()
    return (len(args) >= 3 and args[-3] == "--db" and args[-1] == "mcp"
            and Path(args[-2]).is_absolute())


def _merge_owned(existing: Any, desired: dict[str, Any], p: _Profile) -> Any:
    result = copy.deepcopy(existing)
    env_key = "environment" if p.name == "opencode" else "env"
    for key, value in desired.items():
        if key == "tools" and key in result:
            # Copilot's tool exposure is a user's policy, not our launch args.
            continue
        if key == env_key:
            for name, setting in value.items():
                result[key][name] = setting
        elif result.get(key) != value:
            result[key] = value
    return result


def _dump(document: Any, p: _Profile, raw: bytes | None) -> bytes:
    text = _tomlkit().dumps(document) if p.format == "toml" else json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if raw is not None and b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""):
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    encoded = text.encode("utf-8")
    return b"\xef\xbb\xbf" + encoded if raw is not None and raw.startswith(b"\xef\xbb\xbf") else encoded


def plan_client(profile: str, db_path: str | os.PathLike[str], executable: str | os.PathLike[str], *,
                argument_prefix: Sequence[str] = (), config_path: str | os.PathLike[str] | None = None,
                writable: bool = False, replace: bool = False, home: str | os.PathLike[str] | None = None,
                platform: str | None = None, environ: Mapping[str, str] | None = None) -> ClientPlan:
    """Plan one install/update without changing any files.

    ``executable`` must name an absolute executable path. This avoids depending
    on a GUI client's PATH and never constructs a shell command. The common
    invocation is ``sys.executable`` with ``argument_prefix=['-m','memory_book']``.
    """
    p = _profile(profile)
    base, system, env = _settings(home, platform, environ)
    raw_executable = os.fspath(executable)
    if not isinstance(raw_executable, str) or not Path(raw_executable).is_absolute() or "\x00" in raw_executable:
        raise ConfigError("executable must be an absolute path (for example sys.executable)")
    if not isinstance(argument_prefix, Sequence) or isinstance(argument_prefix, (str, bytes)) or not all(isinstance(arg, str) and "\x00" not in arg for arg in argument_prefix):
        raise ConfigError("argument_prefix must be a sequence of strings")
    database = _absolute_path(db_path, base, "db_path")
    if os.fspath(db_path) == ":memory:":
        raise ConfigError("MCP requires a persistent database file, not :memory:")
    args = [*argument_prefix, "--db", str(database), "mcp"]
    if writable:
        args.append("--allow-write")
    entry = _entry(p, raw_executable, args)
    snippet = _snippet(p, entry)
    path = _config_path(p, config_path, base, system, env)
    if path is None:
        return ClientPlan(p.name, None, "export", False, entry, snippet, p.notes, p.docs_url, None, None, None)
    if path == database or path.resolve() == database.resolve():
        raise ConfigError("The MCP client configuration and memory database must be different files")
    raw, mode = _read_config(path)
    document = _parse(raw, p, snippet)
    container = _container(document, p, create=True)
    existing = container.get(SERVER_NAME)
    if existing == entry:
        changed = False
    elif SERVER_NAME in container:
        if _owned(existing, p):
            merged = _merge_owned(existing, entry, p)
            changed = existing != merged
            if changed:
                container[SERVER_NAME] = merged
        elif replace:
            container[SERVER_NAME] = entry
            changed = True
        else:
            raise ConfigError(f"An unmanaged {SERVER_NAME!r} server already exists; choose another configuration file or explicitly replace that entry", snippet=snippet)
    else:
        container[SERVER_NAME] = entry
        changed = True
    return ClientPlan(p.name, path, "install", changed, entry, snippet, p.notes, p.docs_url,
                      _hash(raw), _dump(document, p, raw) if changed else raw, mode)


def plan_remove(profile: str, *, config_path: str | os.PathLike[str] | None = None,
                home: str | os.PathLike[str] | None = None, platform: str | None = None,
                environ: Mapping[str, str] | None = None) -> ClientPlan:
    """Remove only a server bearing our marker and a valid memory-book command."""
    p = _profile(profile)
    base, system, env = _settings(home, platform, environ)
    path = _config_path(p, config_path, base, system, env)
    if path is None:
        raise ConfigError("generic-json is export only and has no managed configuration to remove")
    raw, mode = _read_config(path)
    changed = False
    new_bytes = raw
    if raw is not None:
        document = _parse(raw, p, "")
        container = _container(document, p, create=False)
        if container is not None and SERVER_NAME in container:
            if not _owned(container[SERVER_NAME], p):
                raise ConfigError(f"Refusing to remove {SERVER_NAME!r}: this entry is not marked as managed by AI-Memory-Book")
            del container[SERVER_NAME]
            changed = True
            new_bytes = _dump(document, p, raw)
    return ClientPlan(p.name, path, "remove", changed, None, "", p.notes, p.docs_url,
                      _hash(raw), new_bytes, mode)


def apply_plan(plan: ClientPlan) -> dict[str, Any]:
    """Apply an unchanged plan with a backup and atomic file replacement.

    A per-file lock prevents concurrent Memory Book installers. The hash check
    rejects a config edited after planning; no client process is terminated.
    """
    if plan.action == "export":
        return {**plan.as_dict(), "applied": False, "backup_path": None}
    if plan.action not in {"install", "remove"} or plan.config_path is None:
        raise ConfigError("Invalid client configuration plan")
    path = plan.config_path
    raw, mode = _read_config(path)
    if _hash(raw) != plan._expected_hash or mode != plan._expected_mode:
        raise ConfigError("Client configuration changed after planning; build a fresh plan before applying it")
    if not plan.changed:
        return {**plan.as_dict(), "applied": False, "backup_path": None}
    if plan._new_bytes is None:
        raise ConfigError("Invalid plan: new configuration is missing")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".memory-book.lock")
    try:
        lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ConfigError(f"Another setup may be editing this configuration: {lock_path}. If no setup process is running, remove that stale lock and retry.") from None
    temporary: str | None = None
    backup_path: Path | None = None
    try:
        os.close(lock_fd)
        raw, mode = _read_config(path)
        if _hash(raw) != plan._expected_hash or mode != plan._expected_mode:
            raise ConfigError("Client configuration changed after planning; build a fresh plan before applying it")
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".memory-book-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as target:
            if hasattr(os, "fchmod"):
                os.fchmod(target.fileno(), mode if mode is not None else 0o600)
            target.write(plan._new_bytes)
            target.flush()
            os.fsync(target.fileno())
        if raw is not None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            backup_path = path.with_name(f"{path.name}.memory-book.{stamp}.{uuid.uuid4().hex[:8]}.bak")
            backup_fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode if mode is not None else 0o600)
            with os.fdopen(backup_fd, "wb") as backup:
                backup.write(raw)
                backup.flush()
                os.fsync(backup.fileno())
        current, current_mode = _read_config(path)
        if _hash(current) != plan._expected_hash or current_mode != plan._expected_mode:
            raise ConfigError("Client configuration changed while applying; original configuration was preserved. Build a fresh plan.")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
    return {**plan.as_dict(), "applied": True,
            "backup_path": str(backup_path) if backup_path is not None else None}
