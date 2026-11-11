"""Opt-in, current-user service management. Never needs a stored password.

Native supervisors own the process lifecycle: systemd --user, launchd user
agents, and Windows Task Scheduler with an interactive, limited principal.
All external commands use argv lists; generated files contain no shell hooks.
"""

from __future__ import annotations

import base64
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import data_dir

SERVICE_NAME = "ai-memory-book.service"
LAUNCH_LABEL = "com.ai-memory-book.agent"
TASK_NAME = "AI-Memory-Book"
MARKER = "Managed by AI-Memory-Book"


def _clean(value: str | Path) -> str:
    text = str(value)
    if any(ord(char) < 32 for char in text):
        raise ValueError("Service paths cannot contain control characters")
    return text


def _unit_quote(value: str, *, command: bool = True) -> str:
    escaped = _clean(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return '"' + (escaped.replace('$', '$$') if command else escaped) + '"'


def _ps_quote(value: str) -> str:
    return "'" + _clean(value).replace("'", "''") + "'"


def _powershell(script: str) -> list[str]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def service_path(*, platform: str | None = None, home: Path | None = None,
                 environ: dict | None = None) -> Path:
    target = sys.platform if platform is None else platform
    user_home = Path.home() if home is None else Path(home)
    env = os.environ if environ is None else environ
    if target == "darwin":
        return user_home / "Library" / "LaunchAgents" / f"{LAUNCH_LABEL}.plist"
    if target == "win32":
        return data_dir(home=user_home, platform=target, environ=env) / "service.json"
    if target.startswith("linux"):
        config_home = Path(env.get("XDG_CONFIG_HOME", str(user_home / ".config")))
        return config_home / "systemd" / "user" / SERVICE_NAME
    raise ValueError("User services support Linux, macOS, and Windows; run 'memory-book daemon' on this platform")


def render_service(config_path: Path | str, *, executable: str | None = None,
                   platform: str | None = None, home: Path | None = None,
                   environ: dict | None = None) -> dict:
    target = sys.platform if platform is None else platform
    config = Path(config_path).expanduser().absolute()
    python = _clean(executable or sys.executable)
    args = [python, "-m", "memory_book", "daemon", "--config", _clean(config)]
    path = service_path(platform=target, home=home, environ=environ)
    folder = config.parent
    if target.startswith("linux"):
        content = (
            f"# {MARKER}\n[Unit]\nDescription=AI Memory Book background capture and local reader\n"
            "\n[Service]\nType=simple\n"
            f"ExecStart={' '.join(_unit_quote(a) for a in args)}\n"
            f"WorkingDirectory={_unit_quote(str(folder), command=False)}\n"
            "Environment=PYTHONUNBUFFERED=1\nRestart=on-failure\nRestartSec=5\n"
            "TimeoutStopSec=30\n\n[Install]\nWantedBy=default.target\n"
        )
        manager = "systemd --user"
    elif target == "darwin":
        content = plistlib.dumps({
            "Label": LAUNCH_LABEL,
            "Comment": MARKER,
            "ProgramArguments": args,
            "WorkingDirectory": str(folder),
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 5,
            "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
            "StandardOutPath": str(folder / "service.stdout.log"),
            "StandardErrorPath": str(folder / "service.stderr.log"),
        }, sort_keys=False).decode("utf-8")
        manager = "launchd"
    elif target == "win32":
        # pythonw avoids a console window when Task Scheduler starts the worker.
        sibling = Path(python).with_name("pythonw.exe")
        if sibling.is_file():
            args[0] = str(sibling)
        content = json.dumps({"managed_by": MARKER, "task_name": TASK_NAME,
                              "arguments": args, "working_directory": str(folder)}, indent=2) + "\n"
        manager = "Windows Task Scheduler"
    else:
        raise ValueError("Unsupported service platform")
    return {"manager": manager, "path": str(path), "content": content,
            "arguments": args, "config": str(config), "platform": target}


def _write_managed(path: Path, content: str) -> bool:
    if path.is_symlink():
        raise ValueError("Refusing to replace a symbolic-link service file")
    if path.exists():
        previous = path.read_text(encoding="utf-8")
        if MARKER not in previous:
            raise ValueError(f"An unmanaged service file already exists: {path}")
        if previous == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=30, check=False)
    except FileNotFoundError:
        raise RuntimeError(f"{args[0]} is unavailable; run 'memory-book daemon --config <path>' under your process supervisor") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{args[0]} did not respond within 30 seconds") from None
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "No diagnostic output").strip()[:1200]
        raise RuntimeError(f"Service manager failed ({result.returncode}): {detail}")
    return result


def _windows_script(action: str, spec: dict) -> str:
    task = _ps_quote(TASK_NAME)
    # The description marker prevents overwriting a same-named unrelated task.
    common = (
        "$ErrorActionPreference = 'Stop'\n"
        f"$mbTask = Get-ScheduledTask -TaskName {task} -ErrorAction SilentlyContinue\n"
        f"if ($mbTask -and $mbTask.Description -ne {_ps_quote(MARKER)}) {{ throw 'Task name belongs to another application' }}\n"
    )
    if action == "install":
        argv = spec["arguments"]
        return common + (
            f"if ($mbTask) {{ Stop-ScheduledTask -TaskName {task}; $mbDeadline = (Get-Date).AddSeconds(10); while ((Get-ScheduledTask -TaskName {task}).State -eq 'Running') {{ if ((Get-Date) -gt $mbDeadline) {{ throw 'Previous worker did not stop' }}; Start-Sleep -Milliseconds 100 }} }}\n"
            "$mbUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name\n"
            f"$mbAction = New-ScheduledTaskAction -Execute {_ps_quote(argv[0])} -Argument {_ps_quote(subprocess.list2cmdline(argv[1:]))} -WorkingDirectory {_ps_quote(str(Path(spec['config']).parent))}\n"
            "$mbTrigger = New-ScheduledTaskTrigger -AtLogOn -User $mbUser\n"
            "$mbPrincipal = New-ScheduledTaskPrincipal -UserId $mbUser -LogonType Interactive -RunLevel Limited\n"
            "$mbSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries\n"
            f"Register-ScheduledTask -TaskName {task} -Action $mbAction -Trigger $mbTrigger -Principal $mbPrincipal -Settings $mbSettings -Description {_ps_quote(MARKER)} -Force | Out-Null\n"
            f"Start-ScheduledTask -TaskName {task}\n"
        )
    if action == "status":
        return common + "if ($mbTask) { $mbTask | Select-Object TaskName,State | ConvertTo-Json -Compress } else { Write-Output '{\"state\":\"not-installed\"}' }\n"
    if action == "uninstall":
        return common + f"if ($mbTask) {{ Stop-ScheduledTask -TaskName {task}; Unregister-ScheduledTask -TaskName {task} -Confirm:$false }}\n"
    command = "Start-ScheduledTask" if action == "start" else "Stop-ScheduledTask"
    return common + f"if (-not $mbTask) {{ throw 'Run memory-book service install first' }}\n{command} -TaskName {task}\n"


def manage_service(action: str, config_path: Path | str, *, dry_run: bool = False,
                   executable: str | None = None, platform: str | None = None,
                   home: Path | None = None, environ: dict | None = None) -> dict:
    if action not in {"install", "start", "stop", "status", "uninstall"}:
        raise ValueError("Unknown service action")
    spec = render_service(config_path, executable=executable, platform=platform, home=home, environ=environ)
    target = spec["platform"]
    path = Path(spec["path"])
    if dry_run:
        return {**spec, "action": action, "dry_run": True}
    if path.is_symlink():
        raise ValueError("Refusing a symbolic-link service file")
    managed = path.is_file() and MARKER in path.read_text(encoding="utf-8")
    if path.exists() and not managed:
        raise ValueError("The existing service file is not managed by AI-Memory-Book")
    if action == "install":
        if not Path(spec["config"]).is_file():
            raise ValueError("Background configuration is missing; run 'memory-book setup --client <name> --capture' first")
        # Validate configuration before creating an auto-start job.
        from .sync import load_config
        load_config(spec["config"])
        changed = _write_managed(path, spec["content"])
    else:
        changed = False
        if action in {"start", "stop", "uninstall"} and not managed:
            if action == "uninstall":
                return {"action": action, "installed": False, "changed": False, "path": str(path)}
            raise ValueError("Service is not installed; run 'memory-book service install'")
    commands = []
    if target.startswith("linux"):
        if action == "install":
            commands = [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", SERVICE_NAME], ["systemctl", "--user", "restart", SERVICE_NAME]]
        elif action == "uninstall":
            commands = [["systemctl", "--user", "disable", "--now", SERVICE_NAME]]
        elif action == "status":
            commands = [["systemctl", "--user", "show", SERVICE_NAME, "--property=LoadState,ActiveState,SubState,MainPID", "--no-pager"]]
        else:
            commands = [["systemctl", "--user", action, SERVICE_NAME]]
    elif target == "darwin":
        domain = f"gui/{os.getuid()}"
        label = domain + "/" + LAUNCH_LABEL
        if action == "install":
            _run(["launchctl", "bootout", domain, str(path)], check=False)
            commands = [["launchctl", "enable", label], ["launchctl", "bootstrap", domain, str(path)]]
        elif action == "start":
            # stop uses bootout so a deliberate stop survives KeepAlive.
            loaded = _run(["launchctl", "print", label], check=False)
            commands = [["launchctl", "kickstart", label]] if loaded.returncode == 0 else [["launchctl", "bootstrap", domain, str(path)]]
        elif action in {"stop", "uninstall"}:
            loaded = _run(["launchctl", "print", label], check=False)
            commands = [["launchctl", "bootout", domain, str(path)]] if loaded.returncode == 0 else []
        else:
            commands = [["launchctl", "print", label]]
    else:
        commands = [_powershell(_windows_script(action, spec))]
    results = [_run(command, check=action != "status") for command in commands]
    if action == "uninstall":
        path.unlink(missing_ok=True)
        if target.startswith("linux"):
            _run(["systemctl", "--user", "daemon-reload"])
        changed = True
    output = "\n".join(r.stdout.strip() for r in results if r.stdout.strip())
    return {"action": action, "manager": spec["manager"], "path": str(path),
            "installed": path.is_file(), "changed": changed, "ok": all(r.returncode == 0 for r in results),
            "details": output[:4000]}
