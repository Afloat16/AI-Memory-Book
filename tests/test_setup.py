from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.cli import main
from memory_book.integration import capture_source, get_config, setup_clients
from memory_book.paths import data_dir, default_database
from memory_book.service import MARKER, _windows_script, manage_service, render_service
from memory_book.sync import SyncConfig, WatchSource, load_config, save_config


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "user"
        self.home.mkdir()
        self.config = self.root / "app" / "config.json"
        self.db = self.root / "app" / "memory.db"

    def tearDown(self):
        self.temporary.cleanup()

    def setup_client(self, **kwargs):
        return setup_clients(["claude-code"], config_path=self.config, database=self.db,
                             home=self.home, environ={}, **kwargs)

    def test_dry_run_does_not_create_client_config_or_capture_state(self):
        result = self.setup_client(capture=True, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["capture_sources"][0]["path"], str(self.home / ".claude" / "projects"))
        self.assertFalse((self.home / ".claude.json").exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.db.exists())

    def test_setup_preserves_other_settings_and_reuses_capture_source(self):
        original = {"theme": "dark", "mcpServers": {"other": {"command": "other-tool"}}}
        client_config = self.home / ".claude.json"
        client_config.write_text(json.dumps(original), encoding="utf-8")
        with patch("memory_book.integration.importlib.util.find_spec", return_value=object()):
            first = self.setup_client(capture=True)
            second = self.setup_client(capture=True, workspace=str(self.root / "one-project"))
        parsed = json.loads(client_config.read_text())
        self.assertEqual(parsed["theme"], "dark")
        self.assertEqual(parsed["mcpServers"]["other"], original["mcpServers"]["other"])
        self.assertEqual(len(load_config(self.config).sources), 1)
        self.assertEqual(load_config(self.config).sources[0].workspace, str(self.root / "one-project"))
        self.assertFalse(second["clients"][0]["applied"])
        self.assertTrue(Path(first["clients"][0]["backup_path"]).is_file())

    def test_aliases_do_not_create_duplicate_plans_or_watchers(self):
        with patch("memory_book.integration.importlib.util.find_spec", return_value=object()):
            result = setup_clients(["claude", "claude-code"], config_path=self.config, database=self.db,
                                   home=self.home, environ={}, capture=True)
        self.assertEqual(len(result["clients"]), 1)
        self.assertEqual(len(load_config(self.config).sources), 1)

    def test_unsupported_capture_fails_before_any_client_edit(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            setup_clients(["claude-code", "cursor"], config_path=self.config, database=self.db,
                          home=self.home, environ={}, capture=True)
        self.assertFalse((self.home / ".claude.json").exists())
        self.assertFalse(self.config.exists())

    def test_client_config_cannot_overwrite_background_config_or_state(self):
        for target in (self.config, self.config.parent / "sync-state.json", self.config.parent / "sync.log.jsonl"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "must be separate"):
                setup_clients(["claude-code"], config_path=self.config, client_config_path=target,
                              database=self.db, home=self.home, environ={})
            self.assertFalse(target.exists())

    def test_container_binding_is_explicit_and_retains_local_host_policy(self):
        from memory_book.web import make_server
        with self.assertRaises(ValueError):
            make_server(self.db, host="0.0.0.0", port=0)
        server = make_server(self.db, host="0.0.0.0", port=0, container_bind=True)
        try:
            self.assertTrue(server.reader_url.startswith("http://127.0.0.1:"))
            self.assertFalse(any(host.startswith("0.0.0.0:") for host in server.allowed_hosts))
            self.assertFalse(any(host.startswith("example.com:") for host in server.allowed_hosts))
        finally:
            server.server_close()

    def test_all_mode_marks_unsupported_capture_as_mcp_only(self):
        with patch("memory_book.integration.importlib.util.find_spec", return_value=object()):
            result = setup_clients(["claude-code", "cursor"], config_path=self.config, database=self.db,
                                   home=self.home, environ={}, capture=True, capture_supported_only=True)
        self.assertEqual(len(load_config(self.config).sources), 1)
        self.assertTrue(any("MCP only" in note for note in result["notes"]))

    def test_background_failure_reports_saved_configuration(self):
        with patch("memory_book.integration.importlib.util.find_spec", return_value=object()), \
                patch("memory_book.service.manage_service", side_effect=RuntimeError("No user service manager")):
            result = self.setup_client(capture=True, background=True)
        self.assertFalse(result["ok"])
        self.assertTrue((self.home / ".claude.json").exists())
        self.assertTrue(self.config.exists())
        self.assertIn("No user service manager", result["service"]["error"])

    def test_central_database_is_independent_of_working_directory(self):
        with patch.dict(os.environ, {"MEMORY_BOOK_HOME": str(self.root / "shared")}, clear=True):
            self.assertEqual(default_database(), self.root / "shared" / "memory.db")
        self.assertEqual(data_dir(home=self.home, platform="darwin", environ={}), self.home / "Library" / "Application Support" / "AI-Memory-Book")
        self.assertEqual(data_dir(home=self.home, platform="win32", environ={}), self.home / "AppData" / "Local" / "AI-Memory-Book")
        self.assertEqual(data_dir(home=self.home, platform="linux", environ={"XDG_DATA_HOME": str(self.root / "xdg")}), self.root / "xdg" / "ai-memory-book")

    def test_explicit_database_and_service_diagnostics_ignore_broken_capture_config(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text("not valid JSON")
        with patch.dict(os.environ, {"MEMORY_BOOK_CONFIG": str(self.config)}, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--db", str(self.db), "projects"]), 0)
                self.assertEqual(main(["service", "status", "--dry-run"]), 0)

    def test_watch_cli_add_list_remove_and_import_once(self):
        source = self.root / "exports"
        source.mkdir()
        (source / "conversation.json").write_text(json.dumps({
            "session_id": "alpha", "messages": [{"role": "user", "content": "Launch code?"},
                                                   {"role": "assistant", "content": "The code is comet-771."}]
        }), encoding="utf-8")
        with patch.dict(os.environ, {"MEMORY_BOOK_HOME": str(self.root / "app")}, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["watch", "add", str(source), "--id", "export", "--project", "example", "--config", str(self.config)]), 0)
                self.assertEqual(main(["sync", "--once", "--config", str(self.config)]), 0)
                self.assertEqual(main(["watch", "remove", "export", "--config", str(self.config)]), 0)
        with MemoryBook(self.db) as book:
            self.assertIn("comet-771", book.recall("Launch code", project="example")["context"])
        self.assertEqual(load_config(self.config).sources, ())

    def test_foreground_workers_receive_explicit_database_override(self):
        save_config(SyncConfig(self.root / "configured.db", self.root / "state.json"), self.config)
        for command in ("daemon", "sync"):
            with self.subTest(command=command), patch("memory_book.integration.run_daemon") as run:
                self.assertEqual(main(["--db", str(self.db), command, "--config", str(self.config)]), 0)
                self.assertEqual(Path(run.call_args.kwargs["database"]), self.db)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "space $ percent%" / "config.json"
        save_config(SyncConfig(self.root / "memory.db", self.root / "state.json"), self.config)

    def tearDown(self):
        self.temporary.cleanup()

    def test_linux_quotes_paths_without_shell_expansion(self):
        plan = render_service(self.config, executable="/path with spaces/python", platform="linux", home=self.root, environ={})
        text = plan["content"]
        self.assertIn('ExecStart="/path with spaces/python"', text)
        self.assertIn("space $$ percent%%", text)
        self.assertIn('WorkingDirectory="' + str(self.config.parent).replace('%', '%%') + '"', text)
        self.assertNotIn("/bin/sh", text)

    def test_macos_plist_preserves_exact_argument_boundaries(self):
        plan = render_service(self.config, executable="/app path/python", platform="darwin", home=self.root, environ={})
        value = plistlib.loads(plan["content"].encode())
        self.assertEqual(value["ProgramArguments"][-1], str(self.config))
        self.assertEqual(value["ProgramArguments"][0], "/app path/python")
        self.assertTrue(value["RunAtLoad"])
        self.assertEqual(value["KeepAlive"], {"SuccessfulExit": False})

    def test_windows_task_uses_current_limited_interactive_user(self):
        plan = render_service(self.config, executable=str(self.root / "python.exe"), platform="win32", home=self.root, environ={})
        script = _windows_script("install", plan)
        self.assertIn("-LogonType Interactive -RunLevel Limited", script)
        self.assertIn("-ExecutionTimeLimit ([TimeSpan]::Zero)", script)
        self.assertIn("-MultipleInstances IgnoreNew", script)
        self.assertNotIn("-Password", script)
        self.assertNotIn("-RunLevel Highest", script)

    def test_dry_run_has_no_files_or_subprocesses(self):
        with patch("memory_book.service._run") as run:
            plan = manage_service("install", self.config, dry_run=True, platform="linux", home=self.root, environ={})
        run.assert_not_called()
        self.assertFalse(Path(plan["path"]).exists())

    def test_install_and_uninstall_manage_only_owned_unit(self):
        finished = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch("memory_book.service._run", return_value=finished) as run:
            result = manage_service("install", self.config, platform="linux", home=self.root, environ={})
            self.assertIn(["systemctl", "--user", "restart", "ai-memory-book.service"], [call.args[0] for call in run.call_args_list])
            path = Path(result["path"])
            self.assertIn(MARKER, path.read_text())
            manage_service("uninstall", self.config, platform="linux", home=self.root, environ={})
            self.assertFalse(path.exists())
            self.assertTrue(self.config.exists())

    def test_unmanaged_unit_is_never_replaced(self):
        plan = render_service(self.config, platform="linux", home=self.root, environ={})
        path = Path(plan["path"])
        path.parent.mkdir(parents=True)
        path.write_text("[Service]\nExecStart=/another/app\n")
        with patch("memory_book.service._run") as run, self.assertRaisesRegex(ValueError, "not managed"):
            manage_service("install", self.config, platform="linux", home=self.root, environ={})
        run.assert_not_called()
        self.assertIn("/another/app", path.read_text())


class DaemonProcessTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX signal shutdown; Windows task generation is covered separately")
    def test_real_worker_imports_and_stops_on_sigterm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "transcripts"
            source.mkdir()
            (source / "conversation.json").write_text(json.dumps({"project": "smoke", "session_id": "one",
                "messages": [{"role": "user", "content": "What is the memory marker?"},
                             {"role": "assistant", "content": "The marker is nebula-218."}]}), encoding="utf-8")
            database = root / "requested.db"
            config = SyncConfig(root / "configured.db", root / "state.json", poll_interval=0.05,
                                sources=(WatchSource("test", source, "canonical", project="smoke"),),
                                reader_enabled=False)
            path = root / "config.json"
            save_config(config, path)
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(sys.path)
            process = subprocess.Popen([sys.executable, "-m", "memory_book", "--db", str(database), "daemon", "--config", str(path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail(process.communicate()[1].decode())
                    if config.state_path.exists():
                        with MemoryBook(database) as book:
                            if book.stats()["sessions"] == 1:
                                self.assertIn("nebula-218", book.recall("memory marker", project="smoke")["context"])
                                break
                    time.sleep(0.05)
                else:
                    self.fail("Background import did not complete")
                save_config(replace(config, sources=()), path)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    state = json.loads(config.state_path.read_text())
                    if state["files"] and all(row.get("inactive") for row in state["files"].values()):
                        break
                    time.sleep(0.05)
                else:
                    self.fail("Running worker did not reload a removed capture source")
                (source / "second.json").write_text(json.dumps({"project": "smoke", "session_id": "two",
                    "messages": [{"role": "user", "content": "Do not capture this after removal"}]}))
                previous_cycle = state["last_cycle"]["finished_at"]
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if json.loads(config.state_path.read_text())["last_cycle"]["finished_at"] != previous_cycle:
                        break
                    time.sleep(0.05)
                with MemoryBook(database) as book:
                    self.assertEqual(book.stats()["sessions"], 1)
                self.assertFalse(config.database.exists(), "Explicit --db must survive daemon configuration reload")
                process.terminate()
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr.decode())
                self.assertNotIn(b"nebula-218", stdout + stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
