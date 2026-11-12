"""Recovery rejects truncated, corrupt or misrouted saved experiment bytes."""
import copy
import hashlib
import json
import unittest

from scripts import recover_round3_quality as recovery


class QualityRecoveryTests(unittest.TestCase):
    def test_registered_inventory_cannot_omit_or_duplicate_a_part(self):
        original = json.loads(recovery.MANIFEST.read_bytes())
        self.assertEqual(len(recovery.validate_manifest(original)), 56)
        for mutation in ("missing", "duplicate", "escape", "source"):
            changed = copy.deepcopy(original)
            if mutation == "missing":
                changed["aggregate_prefix"]["parts"].pop()
            elif mutation == "duplicate":
                changed["aggregate_prefix"]["parts"][-1] = changed["aggregate_prefix"]["parts"][0]
            elif mutation == "escape":
                changed["files"][0]["parts"][0]["path"] = "../../private"
            else:
                changed["files"][0]["parts"][0]["commit"] = "0" * 40
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                recovery.validate_manifest(changed)

    def test_byte_reconstruction_checks_order_hash_and_full_git_blob(self):
        first, second = b"original ", b"ledger\n"
        full = first + second
        parts = [{"commit": "commit", "path": "a"}, {"commit": "commit", "path": "b"}]
        entry = {"name": "ledger", "bytes": len(full), "sha256": hashlib.sha256(full).hexdigest(),
                 "git_blob_sha1": hashlib.sha1(f"blob {len(full)}\0".encode() + full).hexdigest(), "parts": parts}
        source = {("commit", "a"): first, ("commit", "b"): second}
        self.assertEqual(recovery.assemble(entry, source), full)
        for value in (second[:-1], b"Ledger\n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recovery.assemble(entry, {**source, ("commit", "b"): value})
        with self.assertRaises(ValueError):
            recovery.assemble({**entry, "parts": list(reversed(parts))}, source)
        with self.assertRaises(ValueError):
            recovery.assemble({**entry, "git_blob_sha1": "0" * 40}, source)

    def test_metadata_must_be_complete_before_partial_worker_array(self):
        fields = recovery.complete_prefix_fields(b'{"attempted_workers":[1],"screening":{"qualified":false},"workers":[{"partial":')
        self.assertEqual(fields, {"attempted_workers": [1], "screening": {"qualified": False}})
        for raw in (b'{"screening":{"quali', b'{"screening":1,"screening":2,"workers":[',
                    b'{"screening":1,"workers":{}'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, IndexError)):
                recovery.complete_prefix_fields(raw)


if __name__ == "__main__":
    unittest.main()
