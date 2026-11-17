import tempfile
import unittest

from scripts import summarize_round2_quality as summary


class QualitySummaryTests(unittest.TestCase):
    def test_incomplete_matrix_cannot_be_called_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "all four"):
                summary.collect(directory)
            partial = summary.collect(directory, allow_partial=True)
            self.assertEqual(partial["status"], "partial")
            self.assertEqual(len(partial["missing_cohorts"]), 4)
            self.assertIn("**partial**", summary.markdown(partial))

    def test_other_run_attempt_source_or_failed_marker_cannot_supply_scores(self):
        record = {"stage": "fixture", "status": "completed", "run_id": summary.RUN_ID,
                  "run_attempt": "1", "source_commit": summary.SOURCE_COMMIT}
        summary.validate_marker(record, "fixture")
        for key, value in (("run_id", "1"), ("run_attempt", "2"), ("source_commit", "b" * 40),
                           ("status", "failed"), ("stage", "another")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "fixed successful"):
                summary.validate_marker({**record, key: value}, "fixture")


if __name__ == "__main__":
    unittest.main()
