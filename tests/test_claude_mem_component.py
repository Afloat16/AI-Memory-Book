"""No network/runtime fixtures: guards against crediting altered native source."""
import copy
import unittest

from benchmarks.competitors.claude_mem import validate_native_rows


class NativeSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.documents = {"page-a": {"title": "Decision", "text": "Keep all original text.",
                                     "project": "alpha"}}
        self.response = {"hit_ids": ["page-a"], "native_payload": [
            {"id": 7, "title": "Decision", "text": "Keep all original text.", "project": "alpha"}]}

    def test_exact_native_source_is_accepted(self):
        self.assertEqual(validate_native_rows(self.response, self.documents, "alpha", 5), ["page-a"])

    def test_truncated_or_rewritten_native_source_cannot_earn_credit(self):
        for field, changed in (("text", "Keep all"), ("title", "Summary"), ("project", "beta")):
            with self.subTest(field=field):
                value = copy.deepcopy(self.response)
                value["native_payload"][0][field] = changed
                with self.assertRaises(ValueError):
                    validate_native_rows(value, self.documents, "alpha", 5)

    def test_scope_unknown_mapping_and_duplicate_ids_fail(self):
        with self.assertRaises(ValueError):
            validate_native_rows(self.response, self.documents, "beta", 5)
        value = copy.deepcopy(self.response)
        value["hit_ids"] = ["unknown"]
        with self.assertRaises(ValueError):
            validate_native_rows(value, self.documents, "alpha", 5)
        value = copy.deepcopy(self.response)
        value["hit_ids"] *= 2
        value["native_payload"] *= 2
        with self.assertRaises(ValueError):
            validate_native_rows(value, self.documents, "alpha", 5)

    def test_more_than_limit_is_not_silently_truncated(self):
        with self.assertRaises(ValueError):
            validate_native_rows(self.response, self.documents, "alpha", 0)


if __name__ == "__main__":
    unittest.main()
