"""Cheap protocol checks; no MemoryBook or measured retrieval calls."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import v014_fixed_scope as fixed
from benchmarks import v014_fixed_scope_audit as audit
from benchmarks.v014_audit import expected_count
from benchmarks.v014_workload import TARGETS, cases, digest


class FixedScopePlanTests(unittest.TestCase):
    def test_registered_profiles_and_unchanged_queries(self):
        plan = fixed.settings()
        self.assertEqual([s["total_pages"] for s in fixed.checkpoints("main", plan)], [1024, 50016, 200032])
        for profile, count in (("smoke", 996), ("main", 3636)):
            specs = fixed.checkpoints(profile, plan)
            self.assertEqual(len({digest(cases(spec)) for spec in specs}), 1)
            self.assertTrue(all(s["own_pages"] == 0 and s["revision"] == 0 and
                not s["delete_config"] and s["shift_days"] == 0 and s["layout"] == "clustered" for s in specs))
            bound = {**plan["profiles"][profile], "required_fields_controls": False}
            self.assertEqual(sum(expected_count(bound, spec, arm, rnd) for spec in specs
                for arm in ("baseline", "candidate") for rnd in range(bound["rounds"])), count)
            self.assertEqual(fixed.expected_records(profile, plan), count)

    def test_partial_foreign_session_rejected(self):
        plan = fixed.settings()
        plan["profiles"]["main"]["total_pages"][-1] = 200020
        with self.assertRaisesRegex(ValueError, "whole foreign sessions"):
            fixed.checkpoints("main", plan)

    def test_nonmonotonic_history_rejected(self):
        plan = fixed.settings()
        plan["profiles"]["main"]["total_pages"] = [1024, 50016, 512]
        with self.assertRaisesRegex(ValueError, "monotonically"):
            fixed.checkpoints("main", plan)

    def test_uncommitted_protocol_rejected(self):
        with patch.object(fixed.scale.common, "git", return_value=b""):
            with self.assertRaisesRegex(ValueError, "must be committed"):
                fixed.protocol_identity()

    def test_dirty_protocol_rejected(self):
        with patch.object(fixed.scale.common, "git", side_effect=[
                "\n".join(fixed.FROZEN).encode(), b" M benchmarks/v014_fixed_scope.py\n"]):
            with self.assertRaisesRegex(ValueError, "protocol is dirty"):
                fixed.protocol_identity()

    def test_offline_protocol_byte_identity_requires_no_git(self):
        with patch.object(fixed.scale.common, "git", side_effect=AssertionError("No live Git needed")):
            identity = fixed.protocol_files_identity()
        self.assertEqual(set(identity["files"]), set(fixed.FROZEN))
        self.assertEqual(identity["protocol"], fixed.PROTOCOL)

    def test_complete_expected_observation_matrix_matches_worker_count(self):
        plan = fixed.settings()
        spec = fixed.checkpoints("main", plan)[0]
        bound = {**plan["profiles"]["main"], "required_fields_controls": False}
        for rnd in range(bound["rounds"]):
            wanted = audit.expected_observations(bound, spec, rnd)
            self.assertEqual(sum(wanted.values()), expected_count(bound, spec, "candidate", rnd))
            self.assertTrue(all(count == 1 for count in wanted.values()))
            quality = [key for key in wanted if key[1] == "quality"]
            self.assertEqual(len(quality), 108 if rnd == 0 else 0)

    def test_equal_count_duplicate_case_does_not_pass_matrix(self):
        plan = fixed.settings()
        spec = fixed.checkpoints("main", plan)[0]
        wanted = audit.expected_observations(plan["profiles"]["main"], spec, 0)
        tampered = wanted.copy()
        keys = [key for key in tampered if key[1] == "quality"]
        del tampered[keys[0]]
        tampered[keys[1]] += 1
        self.assertEqual(sum(tampered.values()), sum(wanted.values()))
        self.assertNotEqual(tampered, wanted)


class TargetFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "source.sqlite"
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE chapters(id TEXT PRIMARY KEY, project_id TEXT, title TEXT, updated_at TEXT);
                CREATE TABLE sessions(id TEXT PRIMARY KEY, project_id TEXT, external_id TEXT, created_at TEXT, raw_json TEXT, updated_at TEXT);
                CREATE TABLE turns(id TEXT PRIMARY KEY, session_pk TEXT, content TEXT);
                CREATE TABLE sections(id TEXT PRIMARY KEY, session_pk TEXT, title TEXT);
                CREATE TABLE pages(rid INTEGER PRIMARY KEY, id TEXT UNIQUE, project_id TEXT, session_pk TEXT, content TEXT, source_refs TEXT);
            """)
            for i, target in enumerate(TARGETS):
                project, session = target["project"], f"session-{i}"
                db.execute("INSERT INTO projects VALUES (?,?,?,?)", (project, "same-name", "host-a", "host-a"))
                db.execute("INSERT INTO chapters VALUES (?,?,?,?)", (f"chapter-{i}", project, "same-title", "host-a"))
                db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)", (session, project, "shared-session", "2001-01-01", '{"source": "complete"}', "host-a"))
                for j in range(16):
                    identifier = f"{i}-{j}"
                    db.execute("INSERT INTO turns VALUES (?,?,?)", (identifier, session, "original turn"))
                    db.execute("INSERT INTO sections VALUES (?,?,?)", (identifier, session, "original section"))
                    db.execute("INSERT INTO pages VALUES (?,?,?,?,?,?)", (i * 16 + j + 1, identifier, project, session, "original page", '[{"start":0,"end":13}]'))
        self.original = fixed.target_fingerprint(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_all_targets_verified_and_fingerprints_record_columns(self):
        fixed.verify_target_scope(self.original)
        self.assertEqual(len(self.original["target_layout"]), 12)
        self.assertEqual(self.original["source_tables"]["pages"]["rows"], 192)
        self.assertEqual(self.original["physical_target_pages"]["rows"], 192)
        self.assertIn("created_at", self.original["source_tables"]["sessions"]["columns"])
        self.assertNotIn("created_at", self.original["source_tables"]["projects"]["columns"])

    def test_foreign_growth_and_bookkeeping_only_are_ignored(self):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO projects VALUES ('foreign','same-name','host-b','host-b')")
            db.execute("INSERT INTO sessions VALUES ('foreign-s','foreign','shared-session','2001-01-01','{}','host-b')")
            db.execute("INSERT INTO pages VALUES (193,'foreign-p','foreign','foreign-s','different','[]')")
            db.execute("UPDATE projects SET created_at='host-b',updated_at='host-b'")
            db.execute("UPDATE chapters SET updated_at='host-b'")
            db.execute("UPDATE sessions SET updated_at='host-b'")
        current = fixed.target_fingerprint(self.path)
        self.assertEqual(current, self.original)
        fixed.verify_target_scope(current, self.original)

    def test_original_turn_change_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE turns SET content='altered original' WHERE id='0-0'")
        with self.assertRaisesRegex(ValueError, "sources"):
            fixed.verify_target_scope(fixed.target_fingerprint(self.path), self.original)

    def test_source_timestamp_change_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE sessions SET created_at='2030-01-01' WHERE id='session-0'")
        with self.assertRaisesRegex(ValueError, "sources"):
            fixed.verify_target_scope(fixed.target_fingerprint(self.path), self.original)

    def test_source_reference_change_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE pages SET source_refs='[]' WHERE id='0-0'")
        with self.assertRaisesRegex(ValueError, "sources"):
            fixed.verify_target_scope(fixed.target_fingerprint(self.path), self.original)

    def test_deleted_target_page_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM pages WHERE id='0-0'")
        with self.assertRaisesRegex(ValueError, "exactly 16"):
            fixed.verify_target_scope(fixed.target_fingerprint(self.path), self.original)

    def test_target_rowid_swap_inside_same_range_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE pages SET rid=999 WHERE rid=2")
            db.execute("UPDATE pages SET rid=2 WHERE rid=3")
            db.execute("UPDATE pages SET rid=3 WHERE rid=999")
        current = fixed.target_fingerprint(self.path)
        self.assertEqual(current["source_tables_sha256"], self.original["source_tables_sha256"])
        self.assertEqual(current["target_layout"], self.original["target_layout"])
        with self.assertRaisesRegex(ValueError, "physical placement"):
            fixed.verify_target_scope(current, self.original)


if __name__ == "__main__":
    unittest.main()
