"""Tamper tests for final evidence audit; never execute an experiment."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import audit_round3_completion as audit


class FinalAuditTests(unittest.TestCase):
    def test_edited_raw_is_rejected_even_with_unchanged_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "worker.json"
            original = b'{"calls":47320,"accepted":false}\n'
            path.write_bytes(original)
            expected = {"worker.json": audit.blob(original)}
            before = audit.snapshot(root, expected)
            self.assertEqual(before["worker.json"]["sha256"], audit.sha(original))
            path.write_bytes(original.replace(b"false", b"true"))
            with self.assertRaisesRegex(ValueError, "Working bytes differ"):
                audit.snapshot(root, expected)

    def test_committed_rewrite_cannot_replace_the_original_pin(self):
        original = {"report.json": audit.blob(b"original"),
                    "worker.json": audit.blob(b"original worker")}
        rewritten = {"report.json": audit.blob(b"rewritten consistent summary"),
                     "worker.json": audit.blob(b"rewritten worker")}
        with self.assertRaisesRegex(ValueError, "Historical artifact"):
            audit.verify_pin(rewritten, original, "formal")
        with self.assertRaisesRegex(ValueError, "Historical artifact"):
            audit.verify_pin({"report.json": original["report.json"]}, original, "formal")

    def test_missing_and_symlink_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "Missing or unsafe"):
                audit.snapshot(root, {"missing": audit.blob(b"")})
            (root / "original").write_bytes(b"original")
            (root / "alias").symlink_to(root / "original")
            with self.assertRaisesRegex(ValueError, "Missing or unsafe"):
                audit.snapshot(root, {"alias": audit.blob(b"original")})

    def test_original_quality_rejection_cannot_be_relabelled(self):
        value = json.loads((audit.ROOT / audit.QUALITY / "decision.json").read_bytes())
        audit.quality_decision(value)
        for changes in ({"qualified": True}, {"loss_checks": 0}, {"calls": 8081},
                        {"action": "eligible_for_independent_validation"}):
            changed = {**copy.deepcopy(value), **changes}
            with self.assertRaisesRegex(ValueError, "rejected quality"):
                audit.quality_decision(changed)

    def test_startup_review_does_not_override_original_rejection(self):
        value = json.loads((audit.ROOT / audit.DECISION).read_bytes())
        audit.startup_decision(value)
        for changes in ({"original_report_accepted": True},
                        {"original_resource_review_retained": False},
                        {"status": "unconditional-pass"}):
            with self.assertRaisesRegex(ValueError, "startup decision"):
                audit.startup_decision({**copy.deepcopy(value), **changes})

    def test_guard_allows_local_git_reads_and_blocks_measurement_paths(self):
        guard = audit.ReadOnlyGuard()
        guard.active = True
        guard("subprocess.Popen", ("git", ["git", "show", "HEAD:README.md"], None, None))
        guard("open", ("report.json", "r", 0))
        forbidden = [
            ("open", ("report.json", "w", 0)),
            ("subprocess.Popen", ("python", ["python", "worker.py"], None, None)),
            ("socket.connect", (None, ("example.invalid", 443))),
            ("import", ("memory_book", None, None, None, None)),
            ("import", ("onnxruntime", None, None, None, None)),
            ("os.remove", ("report.json", -1)),
        ]
        for event, args in forbidden:
            with self.subTest(event=event):
                with self.assertRaisesRegex(RuntimeError, "Read-only audit blocked"):
                    guard(event, args)
        self.assertEqual(len(guard.blocked_operations), len(forbidden))


if __name__ == "__main__":
    unittest.main()
