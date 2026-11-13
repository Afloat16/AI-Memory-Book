"""A vector receipt must identify the requested old compatibility cohort."""

import unittest
from types import SimpleNamespace

from scripts.round4_semantic_compatibility import validate_preparation


class PreparationIdentityTests(unittest.TestCase):
    def test_other_cohort_or_count_cannot_be_relabelled(self):
        data = SimpleNamespace(fingerprint="historical-128", queries=[object()] * 128)
        receipt = {"cohort": "hotpot128", "dataset_sha256": data.fingerprint, "queries": 128}
        validate_preparation(receipt, "hotpot128", data)
        for key, value in (("cohort", "authored36"), ("dataset_sha256", "historical-36"),
                           ("queries", 36)):
            with self.subTest(key=key):
                changed = {**receipt, key: value}
                with self.assertRaisesRegex(ValueError, "historical cohort"):
                    validate_preparation(changed, "hotpot128", data)
                omitted = {k: v for k, v in receipt.items() if k != key}
                with self.assertRaisesRegex(ValueError, "historical cohort"):
                    validate_preparation(omitted, "hotpot128", data)


if __name__ == "__main__":
    unittest.main()
