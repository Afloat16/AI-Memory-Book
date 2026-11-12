"""Small release-integrity fixtures; no GitHub calls or package installations."""
import copy
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import release


class ReleaseTests(unittest.TestCase):
    def test_draft_lookup_paginates_and_rejects_duplicate_tags(self):
        first = [{"id": i + 1, "tag_name": "other-" + str(i)} for i in range(100)]
        draft = {"id": 101, "tag_name": "v0.3.0", "draft": True, "target_commitish": "a" * 40}
        with patch.object(release, "api", side_effect=[first, [draft]]) as api:
            self.assertEqual(release.find_release("v0.3.0"), draft)
            self.assertEqual([call.args[0] for call in api.call_args_list],
                             ["releases?per_page=100&page=1", "releases?per_page=100&page=2"])
        first[0] = {**draft, "id": 1}
        with patch.object(release, "api", side_effect=[first, [draft]]), self.assertRaises(ValueError):
            release.find_release("v0.3.0")
        with patch.object(release, "api", return_value=draft):
            self.assertEqual(release.release_by_id(101, "v0.3.0", "a" * 40, draft=True), draft)
            with self.assertRaises(ValueError):
                release.release_by_id(101, "v0.3.0", "a" * 40, draft=False)

    def test_exact_commit_push_ci_and_all_nine_successful_jobs_required(self):
        head = "a" * 40
        run = {"id": 7, "head_sha": head, "event": "push", "status": "completed",
               "conclusion": "success", "head_repository": {"full_name": release.REPOSITORY}}
        self.assertEqual(release.successful_ci([run], head), run)
        for field, value in (("head_sha", "b" * 40), ("event", "pull_request"), ("status", "in_progress"),
                             ("conclusion", "failure"), ("head_repository", {"full_name": "elsewhere/fork"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                release.successful_ci([{**run, field: value}], head)
        with self.assertRaises(ValueError):
            release.successful_ci([run, {**run, "id": 8, "conclusion": "failure"}], head)
        jobs = [{"name": name, "status": "completed", "conclusion": "success", "run_id": 7, "head_sha": head}
                for name in sorted(release.EXPECTED_JOBS)]
        release.verify_jobs(jobs, 7, head)
        for altered in (jobs[:-1], [*jobs, jobs[0]], [{**jobs[0], "conclusion": "skipped"}, *jobs[1:]],
                        [{**jobs[0], "head_sha": "b" * 40}, *jobs[1:]]):
            with self.assertRaises(ValueError):
                release.verify_jobs(altered, 7, head)

    def test_archive_normalization_preserves_runtime_and_record_and_is_repeatable(self):
        identity = {"version": "0.3.0", "epoch": 1760000000}
        sources = {"memory_book/__init__.py": b'__version__ = "0.3.0"\n',
                   "memory_book/static/index.html": b"<h1>fixture</h1>"}
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "ai_memory_book-0.3.0-py3-none-any.whl"
            record_path = "ai_memory_book-0.3.0.dist-info/RECORD"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name, value in sources.items():
                    archive.writestr(name, value)
                archive.writestr(record_path, b"unchanged-record-fixture\n")
            sdist = Path(directory) / "ai_memory_book-0.3.0.tar.gz"
            with tarfile.open(sdist, "w:gz") as archive:
                for name, value in sources.items():
                    info = tarfile.TarInfo("ai_memory_book-0.3.0/src/" + name)
                    info.size = len(value)
                    archive.addfile(info, io.BytesIO(value))
            for path in (wheel, sdist):
                release.canonicalize_and_check(path, identity, sources)
                first = path.read_bytes()
                release.canonicalize_and_check(path, identity, sources)
                self.assertEqual(path.read_bytes(), first)
            with zipfile.ZipFile(wheel) as archive:
                self.assertEqual(archive.read(record_path), b"unchanged-record-fixture\n")
            with self.assertRaises(ValueError):
                release.canonicalize_and_check(wheel, identity, {**sources, "memory_book/missing.py": b"required"})
        for name in ("../escape", "/absolute", "benchmarks/results/raw.json.gz", "memory_book/user.db",
                     "memory_book/model.onnx", "memory_book/cache.sqlite3"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.safe_member(name)

    def test_resume_downloads_and_hashes_existing_assets_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assets"
            output.mkdir()
            (output / "one.whl").write_bytes(b"expected")
            draft = {"tag_name": "v0.3.0", "assets": [{"name": "one.whl", "state": "uploaded", "size": 8}]}
            def download(argv, **_):
                destination = Path(argv[argv.index("--dir") + 1]) / argv[argv.index("--pattern") + 1]
                destination.write_bytes(b"expected")
            with patch.object(release, "command", side_effect=download):
                release.verify_remote_assets(draft, output, complete=False)
            altered = copy.deepcopy(draft)
            altered["assets"][0]["size"] = 7
            with self.assertRaises(ValueError):
                release.verify_remote_assets(altered, output, complete=False)
            altered["assets"][0].update(name="unexpected", size=8)
            with self.assertRaises(ValueError):
                release.verify_remote_assets(altered, output, complete=False)
            def wrong_download(argv, **_):
                destination = Path(argv[argv.index("--dir") + 1]) / "one.whl"
                destination.write_bytes(b"different")
            with patch.object(release, "command", side_effect=wrong_download), self.assertRaises(ValueError):
                release.verify_remote_assets(draft, output, complete=False)
            self.assertEqual((output / "one.whl").read_bytes(), b"expected")


if __name__ == "__main__":
    unittest.main()
