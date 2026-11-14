"""Exercise checkpoint publication with local Git repositories and saved bytes.

No SDK, database, retrieval or performance measurement is executed.
"""
from __future__ import annotations
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import host_round5_c7_development as host


class HostedCheckpointTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".artifacts"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="c7-host-fixture-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / "working"
        self.root.mkdir()
        self.remote = base / "remote.git"
        self.git("init", "--bare", str(self.remote))
        self.git("init", "-b", "main")
        self.git("config", "user.name", "C7 fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "source.txt").write_text("unchanged evaluator and source\n")
        self.git("add", "source.txt")
        self.git("commit", "-m", "fixture source")
        self.git("remote", "add", "origin", str(self.remote))
        self.initial = self.git("rev-parse", "HEAD")
        self.state = self.root / ".artifacts" / "state"
        self.state.mkdir(parents=True)
        self.public = self.root / "benchmarks/reports/c7-saved-fixture"
        self.branch = "validation/c7-saved-fixture"
        self.addCleanup(patch.stopall)
        patch.object(host, "ROOT", self.root).start()
        patch.dict(os.environ, {"GITHUB_RUN_ID": "101", "PHASE_OUTCOME": "failure"}).start()

    def git(self, *arguments):
        result = subprocess.run(["git", *arguments], cwd=self.root,
            capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def remote_head(self):
        return self.git("ls-remote", "--heads", "origin", "refs/heads/" + self.branch).split()[0]

    def blob(self, commit, path):
        return subprocess.check_output(["git", "show", commit + ":" + path], cwd=self.root)

    def test_saved_failures_preserve_bytes_and_head_across_two_checkpoints(self):
        raw = b'{"status":"failed","workers":[],"error":"retained"}\n'
        (self.state / "native-manifest.json").write_bytes(raw)
        workers = self.state / "native-state"
        workers.mkdir()
        (workers / "public1015-0-baseline.json").write_bytes(raw)
        host.preserve("native", self.state, self.public, self.branch)
        first = self.remote_head()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.git("rev-parse", first + "^"), self.initial)
        relative = self.public.relative_to(self.root).as_posix()
        self.assertEqual(gzip.decompress(self.blob(first, relative + "/native-manifest.json.gz")), raw)
        self.assertEqual(gzip.decompress(self.blob(first, relative + "/native-state/public1015-0-baseline.json.gz")), raw)
        # An interrupted SDK ledger has only a start event. Preserve it exactly.
        mcp = self.state / "mcp-state/workers"
        mcp.mkdir(parents=True)
        ledger = b'{"event":"started","seq":0,"query_id":"first"}\n'
        (mcp / "r0-public1015-baseline.attempts.jsonl").write_bytes(ledger)
        # Full corpus databases are deliberately outside the exported evidence.
        database = self.state / "mcp-state/r0-public1015-baseline/memory.db"
        database.parent.mkdir()
        database.write_bytes(b"corpus remains local")
        claim = self.root / ".artifacts/round5-c7-mcp-development-fixture.execution.json"
        claim.write_text('{"claim":"original"}\n')
        host.preserve("mcp", self.state, self.public, self.branch)
        second = self.remote_head()
        self.assertEqual(self.git("rev-parse", second + "^"), first)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(gzip.decompress(self.blob(second, relative + "/mcp-state/workers/r0-public1015-baseline.attempts.jsonl.gz")), ledger)
        self.assertEqual(self.blob(second, relative + "/" + claim.name), claim.read_bytes())
        self.assertNotIn("memory.db", self.git("ls-tree", "-r", "--name-only", second))
        self.assertEqual((self.root / "source.txt").read_text(), "unchanged evaluator and source\n")

    def test_conflicting_remote_writer_blocks_another_checkpoint(self):
        host.preserve("prepared", self.state, self.public, self.branch)
        first = self.remote_head()
        environment = {**os.environ, "GIT_AUTHOR_NAME": "Other fixture", "GIT_AUTHOR_EMAIL": "other@example.invalid",
            "GIT_COMMITTER_NAME": "Other fixture", "GIT_COMMITTER_EMAIL": "other@example.invalid"}
        other = subprocess.check_output(["git", "commit-tree", self.git("rev-parse", first + "^{tree}"),
            "-p", first, "-m", "other writer"], cwd=self.root, env=environment, text=True).strip()
        self.git("push", "origin", other + ":refs/heads/" + self.branch)
        with self.assertRaisesRegex(ValueError, "Unexpected result branch writer"):
            host.preserve("native", self.state, self.public, self.branch)
        self.assertEqual(self.remote_head(), other)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertEqual(json.loads((self.state / "publication.json").read_bytes())["commit"], first)


if __name__ == "__main__":
    unittest.main()
