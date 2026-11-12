"""Small release-integrity fixtures; no GitHub calls or package installations."""
import copy
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import release


class ReleaseTests(unittest.TestCase):
    @unittest.skipIf(sys.version_info < (3, 11), "Release preparation uses Python 3.12 and tomllib")
    def test_v031_packaging_refuses_a_changed_but_committed_runtime(self):
        """A fresh commit/version alone must not silently replace measured code."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "ai-memory-book"\nversion = "0.3.1"\n',
                encoding="utf-8")
            sources = sorted((release.ROOT / "src/memory_book").rglob("*.py"))
            sources.append(release.ROOT / "src/memory_book/static/index.html")
            names = []
            for source in sources:
                relative = source.relative_to(release.ROOT).as_posix()
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                names.append(relative)

            def committed_snapshot(checkout, *args):
                self.assertEqual(checkout, root)
                if args == ("rev-parse", "HEAD"):
                    return b"a" * 40
                if args == ("status", "--porcelain", "--untracked-files=no"):
                    return b""
                if args == ("ls-tree", "-r", "--name-only", "a" * 40, "src/memory_book"):
                    return ("\n".join(names) + "\n").encode()
                if args == ("rev-parse", "HEAD^{tree}"):
                    return b"b" * 40
                if args == ("show", "-s", "--format=%ct", "a" * 40):
                    return b"1760000000"
                if len(args) == 2 and args[0] == "show":
                    head, path = args[1].split(":", 1)
                    self.assertEqual(head, "a" * 40)
                    return (root / path).read_bytes()
                self.fail("Unexpected Git read: " + repr(args))

            with patch.object(release, "git", side_effect=committed_snapshot):
                identity, _ = release.source_identity(root)
                self.assertEqual(identity["version"], "0.3.1")
                self.assertEqual(identity["runtime_sha256"],
                    "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46")
                path = root / "src/memory_book/store.py"
                path.write_bytes(path.read_bytes() + b"\n# Different committed runtime fixture.\n")
                with self.assertRaisesRegex(ValueError, "v0.3.1 runtime differs from the approved source"):
                    release.source_identity(root)

    def test_creation_uses_returned_id_without_a_listing_or_write_retry(self):
        draft = {"id": 17, "tag_name": "v0.3.1", "target_commitish": "a" * 40,
                 "draft": True, "prerelease": True}
        with patch.object(release, "api", return_value=draft) as api, \
                patch.object(release, "find_release", side_effect=AssertionError("must use returned ID")):
            self.assertEqual(release.create_draft("v0.3.1", "a" * 40, "notes\nwith lines"), draft)
            api.assert_called_once_with("releases", body={"tag_name": "v0.3.1", "target_commitish": "a" * 40,
                "name": "v0.3.1", "body": "notes\nwith lines", "draft": True, "prerelease": True, "make_latest": "false"})
        with patch.object(release, "api", side_effect=ValueError("write failed")) as api, \
                self.assertRaises(ValueError):
            release.create_draft("v0.3.1", "a" * 40, "notes")
        self.assertEqual(api.call_count, 1)

    def test_tag_visibility_poll_is_bounded_and_never_retries_writes(self):
        tag = {"object": {"sha": "a" * 40, "type": "commit"}}
        with patch.object(release, "api", side_effect=[None, tag]) as api, patch.object(release.time, "sleep") as sleep:
            self.assertEqual(release.visible_tag("v0.3.1", "a" * 40), tag)
            self.assertEqual(api.call_count, 2)
            self.assertTrue(all(call.kwargs == {"missing": True} for call in api.call_args_list))
            sleep.assert_called_once_with(1)
        with patch.object(release, "api", return_value=None) as api, patch.object(release.time, "sleep"), \
                self.assertRaisesRegex(ValueError, "no write was retried"):
            release.visible_tag("v0.3.1", "a" * 40)
        self.assertEqual(api.call_count, 4)
        with patch.object(release, "api", return_value=tag), patch.object(release.time, "sleep") as sleep, \
                self.assertRaises(ValueError):
            release.visible_tag("v0.3.1", "b" * 40)
        sleep.assert_not_called()

    def test_release_visibility_checks_identity_and_waits_only_for_expected_state(self):
        draft = {"id": 17, "tag_name": "v0.3.1", "target_commitish": "a" * 40,
                 "draft": True, "assets": []}
        complete = {**draft, "assets": [{"name": "one.whl", "state": "uploaded"}]}
        with patch.object(release, "api", side_effect=[None, draft, complete]) as api, \
                patch.object(release.time, "sleep") as sleep:
            self.assertEqual(release.visible_release(17, "v0.3.1", "a" * 40, draft=True,
                                                    asset_names={"one.whl"}), complete)
            self.assertEqual(api.call_count, 3)
            self.assertEqual([call.args for call in sleep.call_args_list], [(1,), (2,)])
            self.assertTrue(all("body" not in call.kwargs for call in api.call_args_list))
        for bad in ({**draft, "target_commitish": "b" * 40}, {**draft, "draft": False},
                    {**draft, "assets": [{"name": "unexpected", "state": "uploaded"}]}):
            with self.subTest(bad=bad), patch.object(release, "api", return_value=bad) as api, \
                    patch.object(release.time, "sleep") as sleep, self.assertRaises(ValueError):
                release.visible_release(17, "v0.3.1", "a" * 40, draft=True, asset_names={"one.whl"})
            api.assert_called_once()
            sleep.assert_not_called()
        published = {**complete, "draft": False}
        with patch.object(release, "api", side_effect=[complete, published]), patch.object(release.time, "sleep"):
            self.assertEqual(release.visible_release(17, "v0.3.1", "a" * 40, draft=False), published)

    def test_an_already_published_release_only_reconciles_without_any_remote_write(self):
        identity = {"version": "0.3.1", "tag": "v0.3.1", "commit": "a" * 40}
        names = ["asset-" + str(i) for i in range(7)]
        published = {"id": 17, "tag_name": identity["tag"], "target_commitish": identity["commit"],
                     "draft": False, "prerelease": True, "html_url": "https://github.com/example/release",
                     "assets": [{"name": name, "state": "uploaded"} for name in names]}
        def read_api(path, **kwargs):
            self.assertNotIn("body", kwargs)
            if path.startswith("git/ref/"):
                return {"object": {"sha": identity["commit"], "type": "commit"}}
            self.assertEqual(path, "releases/17")
            return published
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "assets"
            output.mkdir()
            for name in names:
                (output / name).write_bytes(b"fixture")
            notes = root / "docs/releases/v0.3.1.md"
            notes.parent.mkdir(parents=True)
            notes.write_text("Release fixture")
            job_output = root / "outputs"
            env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": release.REPOSITORY,
                   "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": identity["commit"],
                   "GITHUB_REF": "refs/heads/release/v0.3.1", "GITHUB_OUTPUT": str(job_output)}
            with patch.object(release, "ROOT", root), patch.dict(os.environ, env), \
                    patch.object(release.sys, "argv", ["release.py", "--output", str(output)]), \
                    patch.object(release, "source_identity", return_value=(identity, {})), \
                    patch.object(release, "command", return_value=subprocess.CompletedProcess([], 0, b"gh version 2.1.0", b"")) as command, \
                    patch.object(release, "api", side_effect=read_api), \
                    patch.object(release, "ci_gate", return_value={"html_url": "https://github.com/ci"}), \
                    patch.object(release, "find_release", return_value=published), \
                    patch.object(release, "prepare", return_value=identity), \
                    patch.object(release, "verify_remote_assets") as verify, \
                    patch.object(release, "create_draft", side_effect=AssertionError("must not create")), \
                    patch.object(release.sys, "stdout", new_callable=io.StringIO) as stdout:
                release.main()
                self.assertIn('"reconciled_read_only": true', stdout.getvalue())
            command.assert_called_once_with(["gh", "--version"], check=False)
            verify.assert_called_once_with(published, output, complete=True)
            self.assertEqual(job_output.read_text(), f"tag=v0.3.1\nversion=0.3.1\ncommit={identity['commit']}\n")

    def test_failure_diagnostic_contains_status_but_not_response_secrets(self):
        result = subprocess.CompletedProcess([], 1, b"", b"HTTP 403\nAuthorization: secret-token https://private.invalid/path")
        self.assertEqual(release.failure_summary(result, "GitHub API releases"),
                         "GitHub API releases failed (exit=1, http=403)")

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
