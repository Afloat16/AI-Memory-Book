"""Check release download routing without touching a user's installation."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_installer", ROOT / "scripts/install.py")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerReleaseTests(unittest.TestCase):
    def test_pinned_wheel_and_legacy_source_routes(self):
        repository = "https://github.com/Afloat16/AI-Memory-Book"
        for version in ("v0.3.0", "0.3.0", "v0.3.1", "0.3.1", "v0.3.2", "0.3.2", "v0.3.3", "0.3.3", "v0.3.4", "0.3.4"):
            number = version.removeprefix("v")
            wheel = repository + f"/releases/download/v{number}/ai_memory_book-{number}-py3-none-any.whl"
            for extras in (True, False):
                with self.subTest(version=version, extras=extras):
                    name = "ai-memory-book[mcp,clients]" if extras else "ai-memory-book"
                    self.assertEqual(INSTALLER.package_spec(None, version, extras), f"{name} @ {wheel}")
        for version in ("v0.2.1", "v0.4.0"):
            with self.subTest(version=version):
                self.assertEqual(INSTALLER.package_spec(None, version, True),
                    f"ai-memory-book[mcp,clients] @ {repository}/archive/refs/tags/{version}.zip")
        commit = "ABCDEF0123456789" * 2 + "ABCDEF01"
        self.assertEqual(INSTALLER.package_spec(None, commit, False),
            f"ai-memory-book @ {repository}/archive/{commit.lower()}.zip")
        with tempfile.TemporaryDirectory(prefix="installer-routes-", dir=ROOT) as directory:
            source = Path(directory) / "local source 记忆"
            source.mkdir()
            (source / "pyproject.toml").write_text("[project]\nname = 'ai-memory-book'\n", encoding="utf-8")
            self.assertEqual(INSTALLER.package_spec(source, "v0.3.0", True),
                f"ai-memory-book[mcp,clients] @ {source.resolve().as_uri()}")
            local_wheel = source / "ai_memory_book-0.3.0-py3-none-any.whl"
            local_wheel.touch()
            self.assertEqual(INSTALLER.package_spec(local_wheel, "v0.3.0", False),
                f"ai-memory-book @ {local_wheel.resolve().as_uri()}")

    def test_release_defaults_match_package_and_wrappers(self):
        self.assertEqual(INSTALLER.DEFAULT_VERSION, "v0.3.4")
        self.assertIn('version = "0.3.4"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('installer_ref="v0.3.4"', (ROOT / "scripts/install.sh").read_text(encoding="utf-8"))
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$Version = 'v0.3.4'", powershell)
        self.assertIn("$InstallerRef = 'v0.3.4'", powershell)


if __name__ == "__main__":
    unittest.main()
