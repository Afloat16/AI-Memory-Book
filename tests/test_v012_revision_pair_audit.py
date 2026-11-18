"""Reject misleading baseline/candidate identity combinations."""
import unittest
from unittest.mock import patch

from benchmarks import v012_revision_pair_audit as audit


class RevisionPairIdentityTests(unittest.TestCase):
    def test_same_baseline_cannot_be_presented_as_a_candidate(self):
        with self.assertRaisesRegex(ValueError, "second baseline"):
            audit.paired(None, None, audit.evaluation.BASELINE)

    def test_backend_interpreter_platform_and_evaluator_must_match(self):
        before = {"backend": "python", "python": "interpreter", "platform": "platform", "evaluator": {"sha": "fixture"}}
        for key, changed in (("backend", "native"), ("python", "another interpreter"),
                             ("platform", "another platform"), ("evaluator", {"sha": "another fixture"})):
            with self.subTest(key=key), patch.object(audit, "arm_identity", side_effect=[before, {**before, key: changed}]):
                with self.assertRaisesRegex(ValueError, "changes backend"):
                    audit.paired(None, None, "candidate")


if __name__ == "__main__":
    unittest.main()
