"""Historical input isolation must preserve the actual production hash gates."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import round5_c4_performance as c4
from scripts import round5_c5_performance as c5
from scripts import round5_c6_performance as c6
from scripts import round5_c7_performance as c7
from tests import round5_historical_fixture as fixture


class HistoricalRoundFiveInputsTests(unittest.TestCase):
    def test_snapshot_preserves_registered_bytes_and_restores_paths_after_error(self):
        original_root, original_plan = c7.ROOT, c7.PLAN
        live_covering = (original_root / "tests/test_round5_covering_index.py").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "leave fixture"):
            with fixture.historical_round5_inputs(c7) as root:
                self.assertNotEqual(root, original_root)
                self.assertEqual(c7.ROOT, root)
                self.assertEqual(c7.PLAN, root / fixture._PLAN_PATH)
                prior = json.loads((root / c7.C6_BINDING_PATH).read_bytes())
                for name, expected in prior["evaluator_files"].items():
                    self.assertEqual(c7.sha((root / name).read_bytes()), expected, name)
                raise RuntimeError("leave fixture")
        self.assertEqual(c7.ROOT, original_root)
        self.assertEqual(c7.PLAN, original_plan)
        self.assertFalse(root.exists())
        self.assertEqual((original_root / "tests/test_round5_covering_index.py").read_bytes(),
                         live_covering)

    def test_changed_saved_fixture_is_rejected_before_it_can_be_used(self):
        original_root, original_plan = c7.ROOT, c7.PLAN
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "saved-inputs"
            shutil.copytree(fixture._ARCHIVED_ROOT, archive)
            changed = archive / "test_round5_covering_index.py.txt"
            changed.write_bytes(changed.read_bytes() + b"\n# changed saved input\n")
            with patch.object(fixture, "_ARCHIVED_ROOT", archive):
                with self.assertRaisesRegex(ValueError,
                        "Frozen round-five fixture bytes changed: tests/test_round5_covering_index.py"):
                    with fixture.historical_round5_inputs(c7):
                        self.fail("An altered archive must not become a historical fixture")
        self.assertEqual(c7.ROOT, original_root)
        self.assertEqual(c7.PLAN, original_plan)

    def test_production_registration_gates_reject_changed_historical_inputs(self):
        covering = "tests/test_round5_covering_index.py"
        c4_test = "tests/test_round5_c4_performance.py"
        c5_test = "tests/test_round5_c5_performance.py"
        c6_test = "tests/test_round5_c6_performance.py"
        cases = (
            (c4, c4.continuation_registration, (covering,), {
                c4.CONTINUATION_COMMIT: (c4.CONTINUATION_PATH,),
            }),
            (c5, c5.continuation_registration, (covering, c4_test), {
                c5.CONTINUATION_COMMIT: (c5.CONTINUATION_PATH, c5.DEVELOPMENT_PLAN_PATH),
                c5.C4_ARCHIVE_COMMIT: (*c5.C4_TOOLS, c5.C4_SUMMARY_PATH),
            }),
            (c6, c6.rejected_c5_registration, (covering, c4_test, c5_test), {
                c6.C5_RESULT_COMMIT: (c6.C5_SUMMARY_PATH,),
            }),
            (c7, c7.rejected_c6_registration, (covering, c4_test, c5_test, c6_test), {
                c7.C6_RESULT_COMMIT: (c7.C6_SUMMARY_PATH,),
            }),
        )
        for evaluator, check, changed_names, revisions in cases:
            with self.subTest(evaluator=evaluator.VERSION):
                with fixture.historical_round5_inputs(evaluator) as root:
                    # Capture the verified original Git-object bytes before any
                    # mutation. The mock cannot reflect a subsequently changed
                    # working fixture back as if it were a committed object.
                    objects = {commit + ":" + name: (root / name).read_bytes()
                               for commit, names in revisions.items() for name in names}

                    def committed(command, object_name):
                        self.assertEqual(command, "show")
                        return objects[object_name]

                    with patch.object(evaluator, "git", side_effect=committed):
                        check()
                        for name in (*changed_names, "scripts/round5_performance.py"):
                            with self.subTest(changed=name):
                                path = root / name
                                raw = path.read_bytes()
                                path.write_bytes(raw + b"\n# altered historical input\n")
                                try:
                                    with self.assertRaisesRegex(ValueError,
                                            "(frozen C[356]|retained C4) evaluator file changed"):
                                        check()
                                finally:
                                    path.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()
