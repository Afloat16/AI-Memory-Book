"""Public evidence invariants across project-local optimizations and real writes.

These controls do not prescribe a derived table, query plan, cache layout, or
latency threshold. Foreign writes may change global BM25 statistics: compare
cached recall with fresh recall, not with an obsolete score snapshot. Historical
benchmark queries and gold are not imported or changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from memory_book import MemoryBook
from memory_book.maintenance import backup_database, check_database


V013_SOURCE = "4977ebc13e9da10a8fa4cb95f39e2c533aabe790"
V013_DOCUMENTATION_HEAD = "861b7f35ac2557024d89bc51d5b3017ca35cb9d0"
V013_RUNTIME_SHA256 = "a7492a74a94170b87a2fd54ada421866b9d737f46dce2ff3a3bc21d6debb9da1"
TARGET = "worker"
FOREIGN = "worker/related"
QUERY = "current production retry_limit"


def source(project=TARGET, value=12, *, identity="same-session", task="same-task",
           project_name="Similar worker", task_title="Retry configuration"):
    return {
        "project": project, "project_name": project_name, "session_id": identity,
        "task_id": task, "task_title": task_title, "title": "Retry configuration",
        "created_at": "2026-01-01T00:00:00Z",
        "messages": [{"role": "assistant", "content":
                      f"Production retry_limit={value}. 原文坐标保持一致：e\u0301 / 😀。"}],
    }


def stable_response(result):
    return {key: value for key, value in result.items()
            if key not in {"latency_ms", "cache_hit"}}


class ScopeConsistencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "memory.db"
        self.reader = MemoryBook(self.path, segmentation="turn")
        self.addCleanup(self.reader.close)
        self.writer = MemoryBook(self.path, segmentation="turn")
        self.addCleanup(self.writer.close)
        self.target = self.reader.ingest(source())
        self.foreign = self.reader.ingest(source(FOREIGN, 912))

    def assert_authenticated(self, result, project):
        """Check returned excerpts against API-visible original messages.

        This fixture has exactly one assistant message per source; reconstruct
        its labeled turn directly rather than using the runtime's tokenizer or
        source-reference construction helper as the expected value.
        """
        for hit in result["results"]:
            page = self.reader.read(hit["id"], project=project, limit=100000)
            self.assertEqual(hit["breadcrumb"][0]["id"], project)
            self.assertTrue(hit["source_refs"])
            for reference in hit["source_refs"]:
                self.assertEqual(reference["project"], project)
                self.assertEqual(reference["turn_index"], 0)
                original = self.reader.get_session(project, reference["session_id"])
                turn = "ASSISTANT: " + original["messages"][0]["content"]
                self.assertEqual(
                    page["content"][reference["start"]:reference["end"]],
                    turn[reference["turn_start"]:reference["turn_end"]],
                )
            for start, end in hit["excerpt_spans"]:
                self.assertIn(page["content"][start:end], hit["text"])
        assessment = result["temporal"]["evidence_assessment"]
        for conflict in assessment["conflicts"]:
            for identity in conflict["page_ids"]:
                self.assertEqual(self.reader.read(identity, project=project)["breadcrumb"][0]["id"],
                                 project)

    def assert_cached_matches_fresh(self, project=TARGET, **options):
        cached = self.reader.recall(QUERY, project=project, **options)
        fresh = self.reader.recall(QUERY, project=project, use_cache=False, **options)
        self.assertEqual(stable_response(cached), stable_response(fresh))
        self.assert_authenticated(cached, project)
        return cached

    def test_namesake_project_session_and_chapter_queries_never_share_evidence(self):
        for project, saved, expected in ((TARGET, self.target, "retry_limit=12"),
                                         (FOREIGN, self.foreign, "retry_limit=912")):
            for options in ({}, {"session": "same-session"},
                            {"chapter": saved["chapter_id"]},
                            {"session": "same-session", "chapter": saved["chapter_id"]}):
                with self.subTest(project=project, options=options):
                    first = self.assert_cached_matches_fresh(project, **options)
                    warm = self.assert_cached_matches_fresh(project, **options)
                    self.assertIn(expected, first["context"])
                    self.assertTrue(warm["cache_hit"])
        for options in ({"chapter": self.foreign["chapter_id"]},):
            self.assertEqual(self.reader.recall(QUERY, project=TARGET, **options)["results"], [])
        for absent in ("Worker", "worker ", "workers", "worker' OR 1=1--"):
            with self.subTest(absent=absent):
                self.assertEqual(self.reader.recall(QUERY, project=absent)["results"], [])

    def test_foreign_mutations_preserve_target_sources_without_freezing_global_scores(self):
        before = self.reader.recall(QUERY, project=TARGET)
        original = {hit["id"]: self.reader.read(hit["id"], project=TARGET)
                    for hit in before["results"]}
        for mutation in (
            lambda: self.writer.ingest(source(FOREIGN, 777)),
            lambda: self.writer.ingest(source(FOREIGN, 777, task_title="Renamed foreign chapter")),
            lambda: self.writer.link_session(FOREIGN, "same-session", "another-task", "Foreign move"),
            lambda: self.writer.delete_project(FOREIGN),
            lambda: self.writer.ingest(source(FOREIGN, 888)),
        ):
            mutation()
            result = self.assert_cached_matches_fresh()
            self.assertEqual({hit["id"] for hit in result["results"]}, set(original))
            for identity, page in original.items():
                self.assertEqual(self.reader.read(identity, project=TARGET), page)

    def test_replacement_rename_relink_delete_and_recreate_update_visible_evidence(self):
        old = self.reader.recall(QUERY, project=TARGET)
        old_ids = {hit["id"] for hit in old["results"]}
        foreign = self.reader.recall(QUERY, project=FOREIGN)
        foreign_pages = {hit["id"]: self.reader.read(hit["id"], project=FOREIGN)
                         for hit in foreign["results"]}
        self.writer.ingest(source(value=73))
        current = self.assert_cached_matches_fresh()
        self.assertIn("retry_limit=73", current["context"])
        self.assertNotIn("retry_limit=12", current["context"])
        for identity in old_ids:
            with self.assertRaises(KeyError):
                self.reader.read(identity, project=TARGET)
        self.writer.ingest(source(value=73, project_name="Renamed project",
                                  task_title="Renamed chapter"))
        renamed = self.assert_cached_matches_fresh()
        self.assertEqual(renamed["results"][0]["breadcrumb"][0]["title"], "Renamed project")
        self.assertEqual(renamed["results"][0]["breadcrumb"][1]["title"], "Renamed chapter")
        moved = self.writer.link_session(TARGET, "same-session", "new-task", "Moved chapter")
        self.assertEqual(self.assert_cached_matches_fresh()["results"][0]["breadcrumb"][1]["id"],
                         moved["chapter_id"])
        self.assertEqual(self.reader.recall(QUERY, project=TARGET,
                                          chapter=self.target["chapter_id"])["results"], [])
        self.assertTrue(self.writer.delete_session(TARGET, "same-session"))
        self.assertEqual(self.assert_cached_matches_fresh()["results"], [])
        self.writer.ingest(source(value=48))
        self.assertIn("retry_limit=48", self.assert_cached_matches_fresh()["context"])
        for identity, page in foreign_pages.items():
            self.assertEqual(self.reader.read(identity, project=FOREIGN), page)

    def test_equal_time_conflicts_remain_project_local_even_without_query_scope(self):
        self.writer.ingest(source(value=30, identity="second"))
        self.writer.ingest(source(FOREIGN, 930, identity="second"))
        scoped = self.assert_cached_matches_fresh()
        self.assertEqual(scoped["temporal"]["evidence_assessment"]["status"], "potential_conflict")
        combined = self.reader.recall(QUERY, limit=10)
        conflicts = combined["temporal"]["evidence_assessment"]["conflicts"]
        self.assertEqual(len(conflicts), 2)
        projects = []
        for conflict in conflicts:
            owners = {self.reader.read(identity)["breadcrumb"][0]["id"]
                      for identity in conflict["page_ids"]}
            self.assertEqual(len(owners), 1)
            self.assertEqual(len(set(conflict["page_ids"])), 2)
            projects.extend(owners)
        self.assertEqual(set(projects), {TARGET, FOREIGN})

    def test_failed_replacement_rolls_back_sources_navigation_and_cached_response(self):
        before = self.reader.recall(QUERY, project=TARGET)
        sources = self.reader.export()
        directory = self.reader.toc(TARGET)
        revision = self.reader.revision
        self.writer.db.execute("""CREATE TRIGGER v014_fail_replacement BEFORE INSERT ON pages
            WHEN instr(NEW.content, 'retry_limit=73') > 0
            BEGIN SELECT RAISE(ABORT, 'independent rollback control'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "independent rollback control"):
            self.writer.ingest(source(value=73, task_title="Should roll back"))
        self.assertFalse(self.writer.db.in_transaction)
        self.assertEqual(self.reader.revision, revision)
        self.assertEqual(self.reader.export(), sources)
        self.assertEqual(self.reader.toc(TARGET), directory)
        after = self.assert_cached_matches_fresh()
        self.assertEqual(stable_response(after), stable_response(before))
        self.assertTrue(after["cache_hit"])
        self.assertEqual(self.reader.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.reader.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_snapshot_result_cannot_be_published_as_a_new_revision_cache(self):
        expected = self.reader.recall(QUERY, project=TARGET, use_cache=False)
        old_revision = expected["revision"]
        state = {"fired": False, "errors": []}

        def write_before_read_commit(statement):
            # A commit boundary is a transaction contract, not a query plan.
            # The callback runs before COMMIT; the already-read snapshot stays
            # valid while a second WAL connection commits its replacement.
            if statement.strip().upper() == "COMMIT" and not state["fired"]:
                state["fired"] = True
                try:
                    self.writer.ingest(source(value=73))
                except BaseException as exc:
                    state["errors"].append(repr(exc))

        self.reader.db.set_trace_callback(write_before_read_commit)
        try:
            old_result = self.reader.recall(QUERY, project=TARGET)
        finally:
            self.reader.db.set_trace_callback(None)
        self.assertTrue(state["fired"])
        self.assertEqual(state["errors"], [])
        self.assertEqual(stable_response(old_result), stable_response(expected))
        self.assertEqual(old_result["revision"], old_revision)
        self.assertGreater(self.reader.revision, old_revision)
        current = self.assert_cached_matches_fresh()
        self.assertFalse(current["cache_hit"])
        self.assertIn("retry_limit=73", current["context"])
        self.assertNotIn("retry_limit=12", current["context"])
        self.assertTrue(self.reader.recall(QUERY, project=TARGET)["cache_hit"])

    def test_reopening_a_ready_archive_does_not_wait_for_an_uncommitted_writer(self):
        self.writer.db.execute("BEGIN IMMEDIATE")
        self.writer.db.execute("UPDATE projects SET name='Uncommitted' WHERE id=?", (TARGET,))
        completed = threading.Event()
        observations, errors = [], []

        def open_reader():
            try:
                with MemoryBook(self.path, segmentation="turn") as reopened:
                    observations.append(reopened.get_session(TARGET, "same-session"))
            except BaseException as exc:
                errors.append(repr(exc))
            finally:
                completed.set()

        thread = threading.Thread(target=open_reader)
        thread.start()
        try:
            completed_before_unlock = completed.wait(5)
        finally:
            self.writer.db.execute("ROLLBACK")
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertTrue(completed_before_unlock, "healthy opening waited for an unrelated write lock")
        self.assertEqual(errors, [])
        self.assertEqual(observations, [self.reader.get_session(TARGET, "same-session")])

    def test_online_backup_restore_keeps_a_separate_revision_and_project_history(self):
        snapshot = self.root / "restored.db"
        expected = self.reader.recall(QUERY, project=TARGET)
        expected_sources = self.reader.export()
        receipt = backup_database(self.path, snapshot)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["revision"], expected["revision"])
        self.writer.ingest(source(value=73))
        self.writer.delete_project(FOREIGN)
        with MemoryBook(snapshot, segmentation="turn") as restored:
            self.assertEqual(restored.export(), expected_sources)
            self.assertEqual(stable_response(restored.recall(QUERY, project=TARGET)),
                             stable_response(expected))
            restored.ingest(source(FOREIGN, 444))
            restored.ingest(source(value=35))
            current = restored.recall(QUERY, project=TARGET)
            fresh = restored.recall(QUERY, project=TARGET, use_cache=False)
            self.assertEqual(stable_response(current), stable_response(fresh))
            self.assertIn("retry_limit=35", current["context"])
            self.assertNotIn("retry_limit=444", current["context"])
        self.assertIn("retry_limit=73", self.assert_cached_matches_fresh()["context"])
        self.assertTrue(check_database(snapshot)["ok"])


class ReleasedWriterCompatibilityTests(unittest.TestCase):
    """A real pinned v0.13 Python writer, never the candidate with patched flags.

    A checkout without the old Git object reports this test as skipped. Local
    release acceptance must provide that object or a verified source directory
    and report the actual run rather than counting a skip as compatibility.
    The later documentation commit is allowed only with the exact published
    runtime digest, and is recorded as its actual HEAD, not as the release tag.
    """

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        override = os.environ.get("MEMORY_BOOK_V013_SOURCE_ROOT")
        repo = Path(__file__).resolve().parents[1]
        # A developer checkout may use a partial clone. Never start an implicit
        # network fetch from a unit test while looking for the old fixture.
        git_environment = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
        if override:
            checkout = Path(override).resolve()
            identity = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout,
                                      capture_output=True, text=True, check=True,
                                      env=git_environment, timeout=10).stdout.strip()
            if identity not in {V013_SOURCE, V013_DOCUMENTATION_HEAD}:
                raise AssertionError("old writer override must be a pinned v0.13 checkout")
            dirty = subprocess.run(["git", "status", "--porcelain", "--", "src/memory_book"],
                                   cwd=checkout, capture_output=True, text=True, check=True,
                                   env=git_environment, timeout=10).stdout
            if dirty:
                raise AssertionError("old writer runtime must be clean")
            hasher = hashlib.sha256()
            for path in sorted((checkout / "src/memory_book").rglob("*")):
                if path.is_file() and path.suffix in {".py", ".c", ".h", ".rs"}:
                    if path.is_symlink():
                        raise AssertionError("old writer runtime cannot contain source symlinks")
                    name = path.relative_to(checkout / "src/memory_book").as_posix()
                    hasher.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
            if hasher.hexdigest() != V013_RUNTIME_SHA256:
                raise AssertionError("old writer bytes differ from the published v0.13 runtime")
            cls.legacy_root = checkout / "src"
            sys.stderr.write(f"Legacy writer actual HEAD={identity}; runtime={hasher.hexdigest()}; backend=python\n")
        else:
            if shutil.which("git") is None:
                raise unittest.SkipTest("Git unavailable for pinned v0.13 writer extraction")
            try:
                listing = subprocess.run(["git", "ls-tree", "-r", V013_SOURCE, "--", "src/memory_book"],
                                         cwd=repo, capture_output=True, text=True,
                                         env=git_environment, timeout=10)
            except subprocess.TimeoutExpired:
                raise unittest.SkipTest("local v0.13 source lookup timed out; compatibility not assessed")
            if listing.returncode:
                raise unittest.SkipTest("exact v0.13 source object unavailable; compatibility not assessed")
            cls.legacy_root = cls.root / "legacy" / "src"
            count = 0
            for entry in listing.stdout.splitlines():
                metadata, name = entry.split("\t", 1)
                mode, kind, identity = metadata.split()
                relative = Path(name)
                if (kind != "blob" or mode != "100644" or relative.suffix != ".py"
                        or relative.parts[:2] != ("src", "memory_book")
                        or ".." in relative.parts):
                    continue
                try:
                    blob = subprocess.run(["git", "cat-file", "blob", identity], cwd=repo,
                                          capture_output=True, env=git_environment, timeout=10)
                except subprocess.TimeoutExpired:
                    raise unittest.SkipTest("local v0.13 blob lookup timed out; compatibility not assessed")
                if blob.returncode:
                    raise unittest.SkipTest("v0.13 Python blob unavailable locally; compatibility not assessed")
                destination = cls.root / "legacy" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob.stdout)
                count += 1
            if not count:
                raise unittest.SkipTest("v0.13 Python fixture empty; compatibility not assessed")

    def test_already_open_v013_writer_cannot_leave_candidate_results_stale(self):
        child = """
import json, pathlib, sys
from memory_book import MemoryBook
path, ready = sys.argv[1:]
with MemoryBook(path, segmentation='turn') as book:
    for item in json.loads(sys.stdin.readline()):
        book.ingest(item)
    pathlib.Path(ready).write_text('ready', encoding='ascii')
    command = json.loads(sys.stdin.readline())
    try:
        if command['action'] == 'delete':
            result = book.delete_session(command['project'], 'same-session')
        else:
            result = book.ingest(command['source'])
        print(json.dumps({'ok': True, 'result': result}), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'type': type(error).__name__, 'error': str(error)}), flush=True)
"""
        actions = (
            {"action": "replace", "source": source(value=73)},
            {"action": "rename", "source": source(task_title="Old writer rename")},
            {"action": "delete", "project": TARGET},
            {"action": "foreign", "source": source(FOREIGN, 777)},
        )
        for index, action in enumerate(actions):
            with self.subTest(action=action["action"]):
                path = self.root / f"old-writer-{index}.db"
                ready = self.root / f"ready-{index}"
                environment = {**os.environ, "PYTHONPATH": str(self.legacy_root),
                               "MEMORY_BOOK_TEXT_BACKEND": "python"}
                process = subprocess.Popen([sys.executable, "-c", child, str(path), str(ready)],
                                           cwd=self.root, env=environment, stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    process.stdin.write(json.dumps([source(), source(FOREIGN, 912)]) + "\n")
                    process.stdin.flush()
                    deadline = time.monotonic() + 10
                    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(ready.exists(), "old writer did not open its archive")
                    with MemoryBook(path, segmentation="turn") as candidate:
                        before = candidate.recall(QUERY, project=TARGET)
                        sources = candidate.export()
                        revision = candidate.revision
                        stdout, stderr = process.communicate(json.dumps(action) + "\n", timeout=15)
                        self.assertEqual(process.returncode, 0, stderr)
                        outcome = json.loads(stdout)
                        after = candidate.recall(QUERY, project=TARGET)
                        fresh = candidate.recall(QUERY, project=TARGET, use_cache=False)
                        self.assertEqual(stable_response(after), stable_response(fresh))
                        self.assertTrue(all(ref["project"] == TARGET for hit in after["results"]
                                            for ref in hit["source_refs"]))
                        if not outcome["ok"]:
                            # A format-changing candidate may explicitly reject
                            # an incompatible old writer, but only atomically.
                            self.assertEqual(outcome["type"], "IntegrityError")
                            self.assertIn("restart older writers", outcome["error"])
                            self.assertEqual(candidate.revision, revision)
                            self.assertEqual(candidate.export(), sources)
                            self.assertEqual(stable_response(after), stable_response(before))
                        elif action["action"] == "replace":
                            self.assertIn("retry_limit=73", after["context"])
                            self.assertNotIn("retry_limit=12", after["context"])
                        elif action["action"] == "rename":
                            self.assertEqual(after["results"][0]["breadcrumb"][1]["title"],
                                             "Old writer rename")
                        elif action["action"] == "delete":
                            self.assertEqual(after["results"], [])
                        else:
                            self.assertIn("retry_limit=12", after["context"])
                            self.assertIn("retry_limit=777", candidate.recall(QUERY, project=FOREIGN)["context"])
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream is not None:
                            stream.close()


if __name__ == "__main__":
    unittest.main()
