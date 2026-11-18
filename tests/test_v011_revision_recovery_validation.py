"""Independent rejection tests using the retained complete baseline response.

The original 36-call file is hash checked and never rewritten. Mutations are
made only to in-memory copies; no synthetic retrieval scores are introduced.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/reports/v0.11-development/freshness-baseline.json"
FIXTURE_SHA256 = "d5af073e351a6d186d5211b40d45bf517b7c774f38e3f8f1bc283ad3030c0659"
VERIFY = runpy.run_path(str(ROOT / "scripts/validate_v011_revision_recovery.py"))["verify_observations"]


class V011RevisionRecoveryValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
            raise AssertionError("The original complete baseline fixture changed")
        cls.original = json.loads(raw)

    def fixture(self):
        return copy.deepcopy(self.original)

    def test_original_full_fixture_has_the_exact_closed_observation_matrix(self):
        expected = set(itertools.product((4, 100, 1000), ("relevance", "current"), (1, 5), range(3)))
        rows = VERIFY(self.fixture())
        self.assertEqual(set(rows), expected)
        self.assertEqual(len(rows), 36)

    def test_order_does_not_change_the_closed_matrix(self):
        raw = self.fixture()
        raw["observations"].reverse()
        self.assertEqual(VERIFY(raw), VERIFY(self.fixture()))

    def test_changed_source_coordinates_are_rejected(self):
        for field in ("start", "end", "turn_start", "turn_end", "turn_index"):
            with self.subTest(field=field):
                raw = self.fixture()
                ref = raw["observations"][0]["result"]["results"][0]["source_refs"][0]
                ref[field] += 1
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_changed_message_and_excerpt_coordinates_are_rejected(self):
        for kind in ("message", "excerpt", "page_length"):
            with self.subTest(kind=kind):
                raw = self.fixture()
                item = raw["observations"][0]["result"]["results"][0]
                if kind == "message":
                    item["source_refs"][0]["message_indices"] = [1]
                elif kind == "excerpt":
                    item["excerpt_spans"][0][0] = 1
                else:
                    item["page_chars"] += 1
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_changed_body_is_rejected_even_with_consistent_local_lengths(self):
        raw = self.fixture()
        result = raw["observations"][0]["result"]
        item = result["results"][0]
        original = item["text"]
        changed = original.replace("retry_limit=3", "retry_limit=99", 1)
        self.assertNotEqual(original, changed)
        item["text"] = changed
        item["page_chars"] = len(changed)
        item["excerpt_spans"] = [[0, len(changed)]]
        item["source_refs"][0]["end"] = len(changed)
        item["source_refs"][0]["turn_end"] = len(changed)
        result["context"] = result["context"].replace(original, changed)
        result["context_chars"] = len(result["context"])
        with self.assertRaises(ValueError):
            VERIFY(raw)

    def test_wrong_project_and_unknown_source_session_are_rejected(self):
        for field, value in (("project", "workers-copy"), ("session_id", "old-4"),
                             ("session_id", "unknown")):
            with self.subTest(field=field, value=value):
                raw = self.fixture()
                item = raw["observations"][0]["result"]["results"][0]
                item["source_refs"][0][field] = value
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_both_false_positive_and_false_negative_recovery_claims_are_rejected(self):
        for actual in (False, True):
            with self.subTest(actual=actual):
                raw = self.fixture()
                row = next(row for row in raw["observations"] if row["new_present"] is actual)
                row["new_present"] = not actual
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_first_session_claim_cannot_override_selected_source(self):
        raw = self.fixture()
        raw["observations"][0]["first_session"] = "new"
        with self.assertRaises(ValueError):
            VERIFY(raw)

    def test_recovery_text_inserted_only_in_context_is_rejected(self):
        raw = self.fixture()
        row = raw["observations"][0]
        self.assertFalse(row["new_present"])
        row["result"]["context"] += "\nretry_limit=7"
        row["result"]["context_chars"] = len(row["result"]["context"])
        row["new_present"] = True
        with self.assertRaises(ValueError):
            VERIFY(raw)

    def test_context_cannot_omit_the_selected_original_body(self):
        raw = self.fixture()
        result = raw["observations"][0]["result"]
        result["context"] = result["context"].replace(result["results"][0]["text"], "Body omitted.")
        result["context_chars"] = len(result["context"])
        with self.assertRaises(ValueError):
            VERIFY(raw)

    def test_cell_mode_must_match_the_recorded_temporal_contract(self):
        for field, value in (("requested", "relevance"), ("resolved", "relevance"),
                             ("basis", "auto"), ("preserve_occurrences", True)):
            with self.subTest(field=field):
                raw = self.fixture()
                row = next(row for row in raw["observations"] if row["mode"] == "current")
                row["result"]["temporal"][field] = value
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_duplicate_observation_cells_are_rejected(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                raw = self.fixture()
                duplicate = copy.deepcopy(raw["observations"][0])
                if replace:
                    raw["observations"][-1] = duplicate
                else:
                    raw["observations"].append(duplicate)
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_missing_observation_cells_are_rejected(self):
        for index in (0, -1):
            with self.subTest(index=index):
                raw = self.fixture()
                raw["observations"].pop(index)
                with self.assertRaises(ValueError):
                    VERIFY(raw)

    def test_unknown_observation_cells_are_rejected(self):
        for field, value in (("old_count", 5), ("mode", "historical"),
                             ("limit", 2), ("repeat", 3)):
            with self.subTest(field=field, value=value):
                raw = self.fixture()
                raw["observations"][0][field] = value
                with self.assertRaises(ValueError):
                    VERIFY(raw)


if __name__ == "__main__":
    unittest.main()
