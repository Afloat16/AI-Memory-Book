from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book.clients import (
    MANAGED_ENV, MANAGED_VALUE, SERVER_NAME, ConfigError, apply_plan,
    discover_clients, plan_client, plan_remove, profiles,
)


HAS_TOMLKIT = importlib.util.find_spec("tomlkit") is not None


class ClientConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.database = self.home / "data with spaces" / "memory.sqlite3"
        self.python = str(Path(sys.executable).absolute())

    def plan(self, profile="claude-code", **kwargs):
        return plan_client(
            profile, self.database, self.python, argument_prefix=["-m", "memory_book"],
            home=self.home, environ={}, **kwargs,
        )

    def remove(self, profile="claude-code", **kwargs):
        return plan_remove(profile, home=self.home, environ={}, **kwargs)

    def write_config(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_plan_does_not_create_files_and_command_is_argument_array(self):
        plan = self.plan()
        self.assertEqual(plan.config_path, self.home / ".claude.json")
        self.assertFalse(plan.config_path.exists())
        self.assertFalse(self.database.parent.exists())
        self.assertTrue(plan.changed)
        self.assertEqual(plan.entry["command"], self.python)
        self.assertEqual(plan.entry["args"], ["-m", "memory_book", "--db", str(self.database), "mcp"])
        self.assertNotIn("--allow-write", plan.snippet)
        self.assertEqual(plan.entry["env"][MANAGED_ENV], MANAGED_VALUE)
        self.assertIn("--allow-write", self.plan(writable=True).entry["args"])

    def test_existing_credentials_preserved_but_not_exposed(self):
        path = self.home / ".claude.json"
        original = '{"oauthAccount":{"token":"private-account-token"},"mcpServers":{"other":{"env":{"API_KEY":"private-other-key"},"command":"other"}},"theme":"dark"}\n'
        self.write_config(path, original)
        os.chmod(path, 0o640)
        plan = self.plan()
        self.assertNotIn("private-", json.dumps(plan.as_dict()))
        self.assertNotIn("private-", repr(plan))
        applied = apply_plan(plan)
        self.assertNotIn("private-", json.dumps(applied))
        self.assertTrue(applied["applied"])
        backup = Path(applied["backup_path"])
        self.assertEqual(backup.read_text(), original)
        saved = json.loads(path.read_text())
        self.assertEqual(saved["oauthAccount"]["token"], "private-account-token")
        self.assertEqual(saved["mcpServers"]["other"]["env"]["API_KEY"], "private-other-key")
        self.assertEqual(saved["theme"], "dark")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        self.assertEqual(saved["mcpServers"][SERVER_NAME], plan.entry)

    def test_idempotent_install_has_no_second_write_or_backup(self):
        first = apply_plan(self.plan())
        self.assertIsNone(first["backup_path"])
        path = Path(first["config_path"])
        original = path.read_bytes()
        before = path.stat().st_mtime_ns
        plan = self.plan()
        self.assertFalse(plan.changed)
        second = apply_plan(plan)
        self.assertFalse(second["applied"])
        self.assertIsNone(second["backup_path"])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual(list(path.parent.glob("*.bak")), [])

    def test_updating_managed_entry_preserves_its_extra_settings_and_secret_env(self):
        path = self.plan().config_path
        apply_plan(self.plan())
        document = json.loads(path.read_text())
        entry = document["mcpServers"][SERVER_NAME]
        entry["env"]["EXTRA_SECRET"] = "secret-existing-env"
        entry["timeout"] = 45
        entry["disabled"] = True
        path.write_text(json.dumps(document), encoding="utf-8")
        plan = self.plan(writable=True)
        self.assertNotIn("secret-existing-env", json.dumps(plan.as_dict()))
        apply_plan(plan)
        saved = json.loads(path.read_text())["mcpServers"][SERVER_NAME]
        self.assertEqual(saved["env"]["EXTRA_SECRET"], "secret-existing-env")
        self.assertEqual(saved["timeout"], 45)
        self.assertTrue(saved["disabled"])
        self.assertIn("--allow-write", saved["args"])
        self.assertFalse(self.plan(writable=True).changed)

    def test_unmanaged_name_conflicts_require_explicit_replace(self):
        path = self.home / ".claude.json"
        for entry in ({"command": "unrelated", "env": {"API_KEY": "private-value"}}, None):
            with self.subTest(entry=entry):
                original = json.dumps({"mcpServers": {SERVER_NAME: entry}, "other": True})
                self.write_config(path, original)
                with self.assertRaises(ConfigError) as caught:
                    self.plan()
                self.assertNotIn("private-value", str(caught.exception))
                self.assertEqual(path.read_text(), original)
                self.assertIsNotNone(caught.exception.snippet)
                apply_plan(self.plan(replace=True))
                self.assertTrue(json.loads(path.read_text())["other"])

    def test_changed_config_rejects_stale_install_and_noop(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                path = self.home / ".claude.json"
                if installed:
                    apply_plan(self.plan())
                plan = self.plan()
                self.write_config(path, '{"changed":true}')
                with self.assertRaisesRegex(ConfigError, "changed after planning"):
                    apply_plan(plan)
                self.assertEqual(path.read_text(), '{"changed":true}')

    def test_remove_requires_owned_marker_and_preserves_other_servers(self):
        path = self.home / ".claude.json"
        self.write_config(path, '{"mcpServers":{"other":{"command":"other"}},"theme":"dark"}')
        apply_plan(self.plan())
        removal = self.remove()
        self.assertIsNone(removal.entry)
        self.assertEqual(removal.snippet, "")
        result = apply_plan(removal)
        self.assertTrue(result["applied"])
        saved = json.loads(path.read_text())
        self.assertEqual(saved["mcpServers"], {"other": {"command": "other"}})
        self.assertEqual(saved["theme"], "dark")
        self.assertFalse(self.remove().changed)
        apply_plan(self.plan())
        document = json.loads(path.read_text())
        del document["mcpServers"][SERVER_NAME]["env"][MANAGED_ENV]
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ConfigError, "not marked as managed"):
            self.remove()

    def test_marker_alone_cannot_remove_unrelated_command(self):
        path = self.home / ".claude.json"
        malicious = {"command": "other", "args": ["serve"], "env": {MANAGED_ENV: MANAGED_VALUE}}
        self.write_config(path, json.dumps({"mcpServers": {SERVER_NAME: malicious}}))
        with self.assertRaises(ConfigError):
            self.remove()

    def test_jsonc_duplicate_keys_invalid_root_and_bad_containers_do_not_write(self):
        examples = [
            '{// private-comment\n"mcpServers":{}}',
            '{"mcpServers":{},}',
            '{"apiKey":"private-value",broken}',
            '{"mcpServers":{},"mcpServers":{}}',
            '[]', '{"mcpServers":[]}', '{"mcpServers":null}', '{"x":NaN}', '',
        ]
        path = self.home / "settings.jsonc"
        for body in examples:
            with self.subTest(body=body):
                self.write_config(path, body)
                with self.assertRaises(ConfigError) as caught:
                    self.plan(config_path=path)
                self.assertNotIn("private-value", str(caught.exception))
                self.assertEqual(path.read_text(), body)
        self.assertEqual(list(self.home.glob("*.bak")), [])

    def test_symlink_is_not_replaced_and_nonregular_file_is_rejected(self):
        target = self.write_config(self.home / "target.json", '{}')
        link = self.home / ".claude.json"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(ConfigError, "symlink"):
            self.plan()
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(), '{}')
        with self.assertRaisesRegex(ConfigError, "regular file"):
            self.plan(config_path=self.home)

    def test_lock_prevents_concurrent_installer_and_is_not_deleted(self):
        plan = self.plan()
        lock = plan.config_path.with_name(plan.config_path.name + ".memory-book.lock")
        lock.write_text("owned by another installer")
        with self.assertRaisesRegex(ConfigError, "Another setup"):
            apply_plan(plan)
        self.assertEqual(lock.read_text(), "owned by another installer")
        self.assertFalse(plan.config_path.exists())

    def test_export_has_no_side_effect_and_deepseek_requires_host(self):
        plan = self.plan("generic-json")
        self.assertEqual(plan.action, "export")
        self.assertIsNone(plan.config_path)
        self.assertFalse(apply_plan(plan)["applied"])
        self.assertEqual(json.loads(plan.snippet)["mcpServers"][SERVER_NAME], plan.entry)
        with self.assertRaisesRegex(ConfigError, "MCP host"):
            self.plan("deepseek")
        with self.assertRaises(ConfigError):
            self.plan("generic-json", config_path=self.home / "no.json")

    def test_profiles_use_verified_current_and_legacy_schemas(self):
        expected = {"claude-code", "claude-desktop", "codex", "gemini", "kimi", "kimi-legacy", "cursor", "opencode", "copilot-cli", "qwen-code", "lm-studio", "generic-json"}
        self.assertEqual({item["name"] for item in profiles()}, expected)
        self.assertEqual(self.plan("gemini").config_path, self.home / ".gemini" / "settings.json")
        self.assertEqual(self.plan("kimi").config_path, self.home / ".kimi-code" / "mcp.json")
        self.assertEqual(self.plan("kimi-legacy").config_path, self.home / ".kimi" / "mcp.json")
        self.assertEqual(self.plan("cursor").config_path, self.home / ".cursor" / "mcp.json")
        self.assertEqual(self.plan("cursor").entry["type"], "stdio")
        self.assertEqual(self.plan("copilot-cli").config_path, self.home / ".copilot" / "mcp-config.json")
        self.assertEqual(self.plan("qwen-code").config_path, self.home / ".qwen" / "settings.json")
        self.assertEqual(self.plan("lm-studio").config_path, self.home / ".lmstudio" / "mcp.json")
        self.assertIsNone(next(item for item in profiles() if item["name"] == "kimi")["capture"])

    def test_environment_path_overrides_and_desktop_platforms(self):
        overrides = {"CLAUDE_CONFIG_DIR": str(self.home / "claude-data"), "CODEX_HOME": str(self.home / "codex-data"), "KIMI_CODE_HOME": str(self.home / "kimi-data"), "XDG_CONFIG_HOME": str(self.home / "xdg")}
        found = {item["profile"]: item for item in discover_clients(home=self.home, environ=overrides)}
        self.assertEqual(found["claude-code"]["config_path"], str(self.home / "claude-data" / ".claude.json"))
        self.assertEqual(found["codex"]["config_path"], str(self.home / "codex-data" / "config.toml"))
        self.assertEqual(found["kimi"]["config_path"], str(self.home / "kimi-data" / "mcp.json"))
        self.assertEqual(found["opencode"]["config_path"], str(self.home / "xdg" / "opencode" / "opencode.json"))
        self.assertEqual(found["codex"]["capture"]["root_path"], str(self.home / "codex-data" / "sessions"))
        for platform, suffix in (("darwin", "Library/Application Support/Claude/claude_desktop_config.json"), ("win32", "AppData/Roaming/Claude/claude_desktop_config.json"), ("linux", ".config/Claude/claude_desktop_config.json")):
            self.assertEqual(self.plan("claude-desktop", platform=platform).config_path, self.home / suffix)

    def test_discovery_reads_no_config_contents(self):
        self.write_config(self.home / ".claude.json", 'private unparseable content')
        with patch("memory_book.clients._read_config", side_effect=AssertionError("Do not read configuration during discovery")):
            found = discover_clients(home=self.home, environ={})
        claude = next(item for item in found if item["profile"] == "claude-code")
        self.assertTrue(claude["config_exists"])
        self.assertNotIn("private", json.dumps(found))

    def test_opencode_v2_and_existing_jsonc_require_safe_behavior(self):
        plan = self.plan("opencode")
        snippet = json.loads(plan.snippet)
        entry = snippet["mcp"]["servers"][SERVER_NAME]
        self.assertEqual(entry["type"], "local")
        self.assertEqual(entry["command"], [self.python, "-m", "memory_book", "--db", str(self.database), "mcp"])
        self.assertEqual(entry["environment"][MANAGED_ENV], MANAGED_VALUE)
        path = self.home / ".config" / "opencode" / "opencode.jsonc"
        self.write_config(path, '{"mcp":{"timeout":15000,"servers":{"other":{"type":"local","command":["other"]}}}}')
        plan = self.plan("opencode")
        self.assertEqual(plan.config_path, path)
        apply_plan(plan)
        self.assertFalse(self.plan("opencode").changed)
        saved = json.loads(path.read_text())
        self.assertEqual(saved["mcp"]["timeout"], 15000)
        self.assertIn("other", saved["mcp"]["servers"])
        apply_plan(self.remove("opencode"))
        self.assertNotIn(SERVER_NAME, json.loads(path.read_text())["mcp"]["servers"])
        self.write_config(path, '{// Keep this comment\n"mcp":{}}')
        with self.assertRaisesRegex(ConfigError, "JSONC") as caught:
            self.plan("opencode")
        self.assertIn('"servers"', caught.exception.snippet)
        self.assertIn("Keep this comment", path.read_text())

    def test_opencode_two_config_files_require_explicit_selection(self):
        folder = self.home / ".config" / "opencode"
        self.write_config(folder / "opencode.json", '{}')
        self.write_config(folder / "opencode.jsonc", '{}')
        with self.assertRaisesRegex(ConfigError, "Both"):
            self.plan("opencode")
        self.assertTrue(self.plan("opencode", config_path=folder / "opencode.json").changed)

    def test_opencode_v1_is_not_silently_mixed_with_v2(self):
        path = self.home / ".config" / "opencode" / "opencode.json"
        original = '{"mcp":{"other":{"type":"local","command":["other"],"enabled":true}}}'
        self.write_config(path, original)
        with self.assertRaisesRegex(ConfigError, "OpenCode v1"):
            self.plan("opencode")
        self.assertEqual(path.read_text(), original)

    def test_paths_and_prefix_are_validated(self):
        for executable in ("python", "", "python -m memory_book"):
            with self.subTest(executable=executable), self.assertRaisesRegex(ConfigError, "absolute path"):
                plan_client("generic-json", self.database, executable, home=self.home, environ={})
        for prefix in ("-m memory_book", ["-m", None], ["bad\x00arg"]):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ConfigError, "sequence of strings"):
                plan_client("generic-json", self.database, self.python, argument_prefix=prefix, home=self.home, environ={})
        with self.assertRaisesRegex(ConfigError, "persistent database"):
            plan_client("generic-json", ":memory:", self.python, home=self.home, environ={})
        with self.assertRaisesRegex(ConfigError, "different files"):
            self.plan(config_path=self.database)

    def test_utf8_bom_and_crlf_are_retained(self):
        path = self.home / ".claude.json"
        original = b'\xef\xbb\xbf{\r\n  "theme": "dark"\r\n}\r\n'
        path.write_bytes(original)
        result = apply_plan(self.plan())
        saved = path.read_bytes()
        self.assertTrue(saved.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b"\n", saved.replace(b"\r\n", b""))
        self.assertEqual(Path(result["backup_path"]).read_bytes(), original)

    @unittest.skipUnless(HAS_TOMLKIT, "Install .[clients] to test comment-preserving TOML merges")
    def test_codex_preserves_toml_comments_settings_and_idempotence(self):
        import tomlkit
        path = self.home / ".codex" / "config.toml"
        original = '# My model preference\nmodel = "gpt-example" # Keep inline comment\n\n[mcp_servers.other]\ncommand = "other"\n\n[mcp_servers.other.env]\nAPI_KEY = "private-other-key"\n'
        self.write_config(path, original)
        plan = self.plan("codex")
        self.assertNotIn("private-other-key", json.dumps(plan.as_dict()))
        result = apply_plan(plan)
        self.assertEqual(Path(result["backup_path"]).read_text(), original)
        installed = path.read_text()
        self.assertIn('# My model preference', installed)
        self.assertIn('# Keep inline comment', installed)
        document = tomlkit.parse(installed)
        self.assertEqual(document["model"], "gpt-example")
        self.assertEqual(document["mcp_servers"]["other"]["env"]["API_KEY"], "private-other-key")
        self.assertEqual(document["mcp_servers"][SERVER_NAME]["args"], ["-m", "memory_book", "--db", str(self.database), "mcp"])
        self.assertFalse(self.plan("codex").changed)
        apply_plan(self.plan("codex", writable=True))
        self.assertFalse(self.plan("codex", writable=True).changed)
        apply_plan(self.remove("codex"))
        removed = path.read_text()
        self.assertIn('# Keep inline comment', removed)
        self.assertIn('private-other-key', removed)
        self.assertNotIn(SERVER_NAME, tomlkit.parse(removed)["mcp_servers"])

    def test_copilot_local_type_and_user_tool_filter_survive_update(self):
        plan = self.plan("copilot-cli")
        self.assertEqual(plan.entry["type"], "local")
        self.assertEqual(plan.entry["tools"], ["*"])
        apply_plan(plan)
        path = plan.config_path
        document = json.loads(path.read_text())
        document["mcpServers"][SERVER_NAME]["tools"] = ["recall_memory"]
        path.write_text(json.dumps(document))
        self.assertFalse(self.plan("copilot-cli").changed)
        apply_plan(self.plan("copilot-cli", writable=True))
        self.assertEqual(json.loads(path.read_text())["mcpServers"][SERVER_NAME]["tools"], ["recall_memory"])
        apply_plan(self.remove("copilot-cli"))
        self.assertNotIn(SERVER_NAME, json.loads(path.read_text())["mcpServers"])

    def test_legacy_kimi_is_not_detected_from_shared_executable_alone(self):
        with patch("memory_book.clients.shutil.which", return_value="/bin/kimi"):
            found = {item["id"]: item for item in discover_clients(home=self.home, environ={})}
        self.assertFalse(found["kimi-legacy"]["detected"])
        self.write_config(self.home / ".kimi" / "mcp.json", '{}')
        with patch("memory_book.clients.shutil.which", return_value="/bin/kimi"):
            found = {item["id"]: item for item in discover_clients(home=self.home, environ={})}
        self.assertTrue(found["kimi-legacy"]["detected"])


if __name__ == "__main__":
    unittest.main()
