import inspect
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks import round2_anchor_eval as evaluation
from benchmarks.data import QueryCase


class AnchorEvaluationTests(unittest.TestCase):
    def test_both_frozen_reference_bodies_and_constants_are_checked(self):
        rrf = 'RRF_K = 60\n' + inspect.getsource(evaluation.legacy_rrf).replace('def legacy_rrf(', 'def fuse_candidates(')
        q1 = 'RRF_K = 60\nLEXICAL_WEIGHT = .75\n' + inspect.getsource(evaluation.q1_score_fusion).replace('def q1_score_fusion(', 'def fuse_candidates(')
        response = lambda text: SimpleNamespace(returncode=0, stdout=text)
        with patch.object(evaluation.subprocess, 'run', side_effect=[response(rrf), response(q1)]):
            self.assertEqual(evaluation.verify_reference()['q1_commit'], evaluation.Q1_REFERENCE)
        with patch.object(evaluation.subprocess, 'run', side_effect=[response(rrf), response(q1.replace('LEXICAL_WEIGHT = .75', 'LEXICAL_WEIGHT = .5'))]):
            with self.assertRaisesRegex(ValueError, 'Q1 reference constants'):
                evaluation.verify_reference()

    def test_q1_control_and_q2_runtime_are_distinct_and_restored(self):
        import memory_book.semantic as semantic
        book = SimpleNamespace(_semantic_model=SimpleNamespace(encode_query=lambda text: []))
        original = semantic.fuse_candidates
        for mode, expected in ((evaluation.MODES[1], evaluation.legacy_rrf),
                               (evaluation.MODES[2], evaluation.q1_score_fusion),
                               (evaluation.MODES[3], original)):
            with evaluation.fusion_mode(book, mode) as calls:
                self.assertIs(semantic.fuse_candidates, expected)
                self.assertEqual(calls[0], 0)
            self.assertIs(semantic.fuse_candidates, original)

    def test_four_mode_matrix_cannot_be_completed_by_only_three_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = evaluation.Progress(Path(directory) / 'state.db', {})
            config = {'budget_tokens': 512}
            try:
                for mode in evaluation.MODES[:3]:
                    for repeat in range(3):
                        seq = progress.start(evaluation.digest(config), repeat, 'q', mode)
                        progress.finish(seq, 1, {})
                with self.assertRaisesRegex(ValueError, 'four-mode'):
                    evaluation.build_report(progress, SimpleNamespace(queries=[QueryCase('q','fixture','fixture','p')]),
                                            [config], SimpleNamespace(repeats=3), '', {}, '')
            finally:
                progress.close()


if __name__ == '__main__':
    unittest.main()
