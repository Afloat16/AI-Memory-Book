"""New client/service commands retain the parent launcher's isolation contract."""

import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memory_book import integration, service
from memory_book.clients import SERVER_NAME


class GeneratedProcessIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "User 记忆"
        self.home.mkdir()
        self.config = self.root / "Configuration 记忆" / "config.json"
        self.database = self.root / "Memory 记忆" / "memory.db"

    def parent(self, isolated):
        return SimpleNamespace(executable=sys.executable, platform=sys.platform,
                               flags=SimpleNamespace(isolated=isolated))

    def test_mcp_export_preserves_isolated_and_legacy_argument_boundaries(self):
        for isolated in (0, 1):
            with self.subTest(isolated=isolated), patch.object(integration, "sys", self.parent(isolated)):
                result = integration.setup_clients(["generic-json"], config_path=self.config,
                    database=self.database, home=self.home, environ={}, dry_run=True,
                    mcp_project="isolated-project", writable=True)
            entry = result["clients"][0]["entry"]
            prefix = ["-I", "-X", "utf8"] if isolated else []
            self.assertEqual(entry["command"], sys.executable)
            self.assertEqual(entry["args"], [*prefix, "-m", "memory_book", "--db", str(self.database),
                                             "mcp", "--project=isolated-project", "--allow-write"])
        self.assertFalse(self.config.exists())

    def test_rerunning_isolated_setup_updates_owned_entry_and_preserves_scope(self):
        arguments = dict(config_path=self.config, database=self.database,
                         home=self.home, environ={}, writable=True)
        with patch("memory_book.integration.importlib.util.find_spec", return_value=object()):
            with patch.object(integration, "sys", self.parent(0)):
                integration.setup_clients(["claude-code"], mcp_project="existing-project", **arguments)
            with patch.object(integration, "sys", self.parent(1)):
                updated = integration.setup_clients(["claude-code"], **arguments)
                repeated = integration.setup_clients(["claude-code"], **arguments)
        entry = json.loads((self.home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][SERVER_NAME]
        self.assertEqual(entry["args"], ["-I", "-X", "utf8", "-m", "memory_book", "--db", str(self.database),
                                         "mcp", "--project=existing-project", "--allow-write"])
        self.assertTrue(updated["clients"][0]["applied"])
        self.assertFalse(repeated["clients"][0]["applied"])

    def test_service_platforms_keep_exact_isolated_and_legacy_arguments(self):
        for isolated in (0, 1):
            for platform in ("linux", "darwin", "win32"):
                with self.subTest(isolated=isolated, platform=platform), \
                        patch.object(service, "sys", self.parent(isolated)):
                    executable = str(self.root / "Python Space 记忆" / "python.exe")
                    plan = service.render_service(self.config, executable=executable,
                                                  platform=platform, home=self.home, environ={})
                prefix = ["-I", "-X", "utf8", "-u"] if isolated else []
                expected = [executable, *prefix, "-m", "memory_book", "daemon", "--config", str(self.config)]
                self.assertEqual(plan["arguments"], expected)
                if platform == "linux":
                    command = next(line[len("ExecStart="):] for line in plan["content"].splitlines()
                                   if line.startswith("ExecStart="))
                    self.assertEqual(shlex.split(command), expected)
                    self.assertIn("Environment=PYTHONUNBUFFERED=1", plan["content"])
                elif platform == "darwin":
                    payload = plistlib.loads(plan["content"].encode("utf-8"))
                    self.assertEqual(payload["ProgramArguments"], expected)
                    self.assertEqual(payload["EnvironmentVariables"]["PYTHONUNBUFFERED"], "1")
                else:
                    self.assertEqual(json.loads(plan["content"])["arguments"], expected)

    def test_windows_pythonw_retains_isolation_and_unbuffered_flags(self):
        python = self.root / "python.exe"
        pythonw = self.root / "pythonw.exe"
        pythonw.touch()
        with patch.object(service, "sys", self.parent(1)):
            plan = service.render_service(self.config, executable=str(python),
                                          platform="win32", home=self.home, environ={})
        self.assertEqual(plan["arguments"], [str(pythonw), "-I", "-X", "utf8", "-u", "-m",
                                             "memory_book", "daemon", "--config", str(self.config)])

    def test_isolated_service_flags_preserve_utf8_and_unbuffered_pipe_output(self):
        with patch.object(service, "sys", self.parent(1)):
            plan = service.render_service(self.config, platform="linux", home=self.home, environ={})
        prefix = plan["arguments"][:plan["arguments"].index("-m")]
        code = "import json,sys; print(json.dumps({'isolated':sys.flags.isolated,'utf8':sys.flags.utf8_mode,'unbuffered':sys.stdout.write_through,'text':'记忆'},ensure_ascii=False))"
        environment = {**os.environ, "PYTHONHOME": str(self.root / "not-python"),
                       "PYTHONPATH": str(self.root), "PYTHONUTF8": "0", "PYTHONUNBUFFERED": "0"}
        result = subprocess.run([*prefix, "-c", code], env=environment, cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(result.stdout), {"isolated": 1, "utf8": 1, "unbuffered": True, "text": "记忆"})


if __name__ == "__main__":
    unittest.main()
