"""Project-bound client setup preserves explicit choices across refreshes."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book.cli import parser
from memory_book.clients import ConfigError, SERVER_NAME, apply_plan, plan_client, plan_remove
from memory_book.integration import setup_clients
from memory_book.sync import load_config


HAS_TOMLKIT = importlib.util.find_spec("tomlkit") is not None


class ProjectScopeSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "user"
        self.home.mkdir()
        self.database = self.root / "app" / "memory.db"
        self.config = self.root / "app" / "config.json"
        self.python = str(Path(sys.executable).absolute())

    def plan(self, profile="claude-code", **options):
        return plan_client(profile, self.database, self.python,
                           argument_prefix=("-m", "memory_book"), home=self.home,
                           environ={}, **options)

    def setup_client(self, names=None, **options):
        # Setup config generation does not invoke MCP. Core-only installations
        # can still verify its writes without importing the optional protocol.
        with patch("memory_book.integration.importlib.util.find_spec", return_value=object()):
            return setup_clients(names or ["claude-code"], config_path=self.config,
                                 database=self.database, home=self.home, environ={}, **options)

    @staticmethod
    def launch_args(plan):
        return plan.entry["command"][1:] if plan.profile == "opencode" else plan.entry["args"]

    def test_json_and_opencode_bindings_round_trip_as_single_literal_arguments(self):
        for profile in ("claude-code", "opencode", "copilot-cli", "generic-json"):
            for project in ("algorithm-alpha", "--allow-write", "-engine-'\"; $(literal) 参数"):
                with self.subTest(profile=profile, project=project):
                    plan = self.plan(profile, project=project, writable=True)
                    args = self.launch_args(plan)
                    self.assertEqual(args[-2:], ["--project=" + project, "--allow-write"])
                    parsed = parser().parse_args(args[2:])
                    self.assertEqual(parsed.project, project)
                    self.assertTrue(parsed.allow_write)
                    self.assertEqual(plan.as_dict()["mcp_project"], project)
                    snippet = json.loads(plan.snippet)
                    server = (snippet["mcp"]["servers"][SERVER_NAME] if profile == "opencode"
                              else snippet["mcpServers"][SERVER_NAME])
                    self.assertEqual(server, plan.entry)
                    self.assertFalse(self.database.exists())

    def test_repeat_setup_and_dry_run_preserve_existing_binding(self):
        first = self.setup_client(mcp_project="algorithm-alpha")
        path = Path(first["clients"][0]["config_path"])
        original = path.read_bytes()
        preview = self.setup_client(dry_run=True)
        self.assertEqual(preview["clients"][0]["mcp_project"], "algorithm-alpha")
        self.assertFalse(preview["clients"][0]["changed"])
        self.assertEqual(path.read_bytes(), original)
        repeated = self.setup_client()
        self.assertFalse(repeated["clients"][0]["applied"])
        self.assertIsNone(repeated["clients"][0]["backup_path"])
        self.assertEqual(repeated["clients"][0]["mcp_project"], "algorithm-alpha")
        self.assertEqual(path.read_bytes(), original)

    def test_change_clear_and_disconnect_preserve_other_settings_and_make_backups(self):
        path = self.home / ".claude.json"
        original = {"theme": "dark", "mcpServers": {"other": {"command": "other-tool"}}}
        path.write_text(json.dumps(original), encoding="utf-8")
        self.setup_client(mcp_project="algorithm-alpha")
        document = json.loads(path.read_text())
        entry = document["mcpServers"][SERVER_NAME]
        entry["env"]["EXTRA_KEY"] = "private-setting"
        entry["timeout"] = 45
        path.write_text(json.dumps(document), encoding="utf-8")
        before_change = path.read_bytes()
        changed = self.setup_client(mcp_project="algorithm-beta", writable=True)
        self.assertEqual(Path(changed["clients"][0]["backup_path"]).read_bytes(), before_change)
        self.assertNotIn("private-setting", json.dumps(changed))
        saved = json.loads(path.read_text())
        self.assertEqual(saved["theme"], "dark")
        self.assertEqual(saved["mcpServers"]["other"], original["mcpServers"]["other"])
        self.assertEqual(saved["mcpServers"][SERVER_NAME]["env"]["EXTRA_KEY"], "private-setting")
        self.assertEqual(saved["mcpServers"][SERVER_NAME]["timeout"], 45)
        self.assertEqual(saved["mcpServers"][SERVER_NAME]["args"][-2:],
                         ["--project=algorithm-beta", "--allow-write"])
        before_clear = path.read_bytes()
        cleared = self.setup_client(clear_mcp_project=True, writable=True)
        self.assertIsNone(cleared["clients"][0]["mcp_project"])
        self.assertEqual(Path(cleared["clients"][0]["backup_path"]).read_bytes(), before_clear)
        self.assertFalse(any(arg.startswith("--project=") for arg in
                             json.loads(path.read_text())["mcpServers"][SERVER_NAME]["args"]))
        self.setup_client(mcp_project="algorithm-alpha")
        before_remove = path.read_bytes()
        removed = apply_plan(plan_remove("claude-code", home=self.home, environ={}))
        self.assertEqual(Path(removed["backup_path"]).read_bytes(), before_remove)
        self.assertEqual(json.loads(path.read_text()), original)

    def test_each_client_retains_its_own_binding_when_setup_omits_a_new_one(self):
        self.setup_client(["claude-code"], mcp_project="algorithm-alpha")
        self.setup_client(["cursor"], mcp_project="algorithm-beta")
        preview = self.setup_client(["claude-code", "cursor"], dry_run=True)
        self.assertEqual({item["profile"]: item["mcp_project"] for item in preview["clients"]},
                         {"claude-code": "algorithm-alpha", "cursor": "algorithm-beta"})
        self.assertTrue(all(not item["changed"] for item in preview["clients"]))

    def test_bound_opencode_entry_still_supports_refresh_and_disconnect(self):
        first = self.plan("opencode", project="algorithm-alpha", writable=True)
        apply_plan(first)
        self.assertFalse(self.plan("opencode", writable=True).changed)
        changed = self.plan("opencode", project="algorithm-beta", writable=True)
        self.assertEqual(changed.entry["command"][-2:],
                         ["--project=algorithm-beta", "--allow-write"])
        apply_plan(changed)
        removed = apply_plan(plan_remove("opencode", home=self.home, environ={}))
        self.assertTrue(removed["applied"])
        self.assertNotIn(SERVER_NAME, json.loads(first.config_path.read_text())["mcp"]["servers"])

    def test_mcp_binding_and_capture_assignment_remain_independent(self):
        no_capture = self.setup_client(mcp_project="read-project", dry_run=True)
        self.assertEqual(no_capture["capture_sources"], [])
        automatic = self.setup_client(mcp_project="read-project", capture=True)
        self.assertEqual(automatic["capture_sources"][0]["project_mode"], "metadata")
        self.assertIsNone(load_config(self.config).sources[0].project)
        explicit = self.setup_client(mcp_project="read-project", project="capture-project",
                                     source_path=str(self.root / "chosen-transcripts"), capture=True)
        self.assertEqual(explicit["clients"][0]["mcp_project"], "read-project")
        source = load_config(self.config).sources[0]
        self.assertEqual(source.project, "capture-project")
        self.assertEqual(source.project_mode, "explicit")
        self.assertEqual(source.path, self.root / "chosen-transcripts")
        cleared = self.setup_client(clear_mcp_project=True)
        self.assertIsNone(cleared["clients"][0]["mcp_project"])
        self.assertEqual(load_config(self.config).sources[0], source)

    def test_capture_project_does_not_implicitly_bind_mcp_and_still_requires_capture(self):
        result = self.setup_client(project="capture-project", capture=True, dry_run=True)
        self.assertIsNone(result["clients"][0]["mcp_project"])
        self.assertEqual(result["capture_sources"][0]["project"], "capture-project")
        with self.assertRaisesRegex(ValueError, "require --capture"):
            self.setup_client(project="capture-project", mcp_project="read-project")
        self.assertFalse((self.home / ".claude.json").exists())
        self.assertFalse(self.config.exists())

    def test_invalid_scope_and_conflicting_options_fail_before_any_config_write(self):
        options = [{"mcp_project": value} for value in
                   ("", " outer", "outer ", "x" * 201, "bad\x00project", "bad\ud800project", 1)]
        options += [{"mcp_project": "alpha", "clear_mcp_project": True},
                    {"clear_mcp_project": 1}]
        for option in options:
            with self.subTest(option=repr(option)), self.assertRaises(ValueError):
                self.setup_client(["claude-code", "cursor"], **option)
            self.assertFalse((self.home / ".claude.json").exists())
            self.assertFalse((self.home / ".cursor" / "mcp.json").exists())
            self.assertFalse(self.config.exists())
        with self.assertRaises(ConfigError):
            self.plan(project="alpha", clear_project=True)
        with self.assertRaises(ConfigError):
            self.plan(clear_project="yes")

    def test_later_invalid_client_or_capture_prevents_earlier_scope_update(self):
        first = self.setup_client(mcp_project="algorithm-alpha")
        path = Path(first["clients"][0]["config_path"])
        before_client, before_config = path.read_bytes(), self.config.read_bytes()
        bad = self.home / ".cursor" / "mcp.json"
        bad.parent.mkdir()
        bad.write_text("not valid JSON", encoding="utf-8")
        with self.assertRaises(ConfigError):
            self.setup_client(["claude-code", "cursor"], mcp_project="algorithm-beta")
        self.assertEqual(path.read_bytes(), before_client)
        self.assertEqual(self.config.read_bytes(), before_config)
        bad.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not available"):
            self.setup_client(["claude-code", "cursor"], mcp_project="algorithm-beta", capture=True)
        self.assertEqual(path.read_bytes(), before_client)
        self.assertEqual(self.config.read_bytes(), before_config)
        self.assertEqual(bad.read_text(), "{}")

    def test_malformed_managed_binding_is_not_silently_cleared(self):
        applied = apply_plan(self.plan(project="algorithm-alpha"))
        path = Path(applied["config_path"])
        document = json.loads(path.read_text())
        document["mcpServers"][SERVER_NAME]["args"][-1] = "--project= invalid"
        path.write_text(json.dumps(document), encoding="utf-8")
        original = path.read_bytes()
        with self.assertRaises(ConfigError):
            self.plan()
        with self.assertRaises(ConfigError):
            plan_remove("claude-code", home=self.home, environ={})
        self.assertEqual(path.read_bytes(), original)

    @unittest.skipUnless(HAS_TOMLKIT, "Install .[clients] for comment-preserving TOML setup")
    def test_toml_binding_refresh_clear_and_disconnect_keep_comments(self):
        import tomlkit
        path = self.home / ".codex" / "config.toml"
        path.parent.mkdir()
        original = '# Retain model preference\nmodel = "example" # Keep this\n\n[mcp_servers.other]\ncommand = "other-tool"\n'
        path.write_text(original, encoding="utf-8")
        project = "-algorithm-'\"-参数"
        applied = apply_plan(self.plan("codex", project=project))
        self.assertEqual(Path(applied["backup_path"]).read_text(), original)
        self.assertFalse(self.plan("codex").changed)
        self.assertEqual(self.plan("codex").as_dict()["mcp_project"], project)
        changed = self.plan("codex", project="algorithm-beta", writable=True)
        apply_plan(changed)
        saved = tomlkit.parse(path.read_text())
        self.assertEqual(saved["mcp_servers"][SERVER_NAME]["args"][-2:],
                         ["--project=algorithm-beta", "--allow-write"])
        self.assertEqual(saved["mcp_servers"]["other"]["command"], "other-tool")
        cleared = self.plan("codex", clear_project=True, writable=True)
        apply_plan(cleared)
        self.assertIsNone(self.plan("codex", writable=True).as_dict()["mcp_project"])
        apply_plan(self.plan("codex", project=project))
        apply_plan(plan_remove("codex", home=self.home, environ={}))
        final = path.read_text()
        self.assertIn('# Retain model preference', final)
        self.assertIn('# Keep this', final)
        self.assertNotIn(SERVER_NAME, tomlkit.parse(final)["mcp_servers"])


if __name__ == "__main__":
    unittest.main()
