"""Command metadata remains usable without loading archive/client machinery."""
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LightweightCommandTests(unittest.TestCase):
    def isolated(self, code):
        prelude = "import sys\nsys.path.insert(0, " + repr(str(ROOT / "src")) + ")\n"
        result = subprocess.run([sys.executable, "-I", "-c", prelude + textwrap.dedent(code)],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_help_and_version_do_not_need_archive_or_transcript_modules(self):
        self.isolated('''
            import contextlib
            import importlib.abc
            import io
            blocked = {"sqlite3", "memory_book.store", "memory_book.importers",
                       "memory_book.integration", "memory_book.sync", "memory_book.clients"}
            class NoArchiveImports(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname in blocked:
                        raise AssertionError("Command metadata imported " + fullname)
            sys.meta_path.insert(0, NoArchiveImports())
            import memory_book
            from memory_book.cli import main
            for arguments in (["--version"], ["--help"], ["recall", "--help"], ["import", "--help"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    try:
                        main(arguments)
                    except SystemExit as error:
                        assert error.code == 0
                    else:
                        raise AssertionError("Metadata argument should exit through argparse")
                assert output.getvalue().strip()
                if arguments == ["--version"]:
                    assert output.getvalue().strip() == memory_book.__version__
            assert not (blocked & set(sys.modules))
        ''')

    def test_public_class_identity_star_import_and_type_hints_are_preserved(self):
        self.isolated('''
            import memory_book
            assert "memory_book.store" not in sys.modules
            assert "MemoryBook" in dir(memory_book)
            try:
                memory_book.missing_public_attribute
            except AttributeError:
                pass
            else:
                raise AssertionError("Unknown module attribute must fail")
            assert "memory_book.store" not in sys.modules
            from memory_book import MemoryBook
            from memory_book.store import MemoryBook as original
            from memory_book import cli
            from typing import get_type_hints
            assert MemoryBook is original is memory_book.MemoryBook is cli.MemoryBook
            assert get_type_hints(cli.export_book)["book"] is original
            namespace = {}
            exec("from memory_book import *", namespace)
            assert namespace["MemoryBook"] is original
            assert "MemoryBook" in dir(cli)
            with MemoryBook(":memory:") as book:
                assert book.stats()["pages"] == 0
        ''')

    def test_explicit_database_does_not_load_capture_or_importer_configuration(self):
        self.isolated('''
            import contextlib
            import importlib.abc
            import io
            import json
            import tempfile
            from pathlib import Path
            blocked = {"memory_book.integration", "memory_book.importers", "memory_book.sync"}
            class NoCaptureImports(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname in blocked:
                        raise AssertionError("Explicit archive command imported " + fullname)
            sys.meta_path.insert(0, NoCaptureImports())
            from memory_book.cli import main
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "book.db"
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    assert main(["--db", str(target), "init"]) == 0
                assert target.is_file()
                assert json.loads(output.getvalue())["pages"] == 0
            assert not (blocked & set(sys.modules))
        ''')

    def test_existing_cli_class_override_is_still_used(self):
        self.isolated('''
            import contextlib
            import io
            import json
            from memory_book import cli
            class Replacement:
                def __init__(self, database, **options):
                    assert database == ":memory:"
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def stats(self):
                    return {"replacement": True}
            cli.MemoryBook = Replacement
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                assert cli.main(["--db", ":memory:", "stats"]) == 0
            assert json.loads(output.getvalue()) == {"replacement": True}
        ''')


if __name__ == "__main__":
    unittest.main()
