"""C4 namespace/provenance guards plus inherited unchanged failure fixtures.

These tests construct artificial records only; no recall or benchmark is run.
"""
import copy
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from scripts import round5_performance as original
from scripts import round5_c4_performance as bench
from tests import test_round5_performance as inherited


class C4AcceptanceTests(inherited.RoundFiveAcceptanceTests):
    def setUp(self):
        super().setUp()
        # Only the inherited artificial fixtures change their module under test.
        # The production C4 runner never monkeypatches its frozen predecessor.
        replacement = patch.object(inherited, 'bench', bench)
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_publication_is_limited_to_registered_first_attempt_and_result_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / bench.C4_BINDING_PATH
            binding.parent.mkdir(parents=True)
            binding.write_bytes(b'{}\n')
            args = SimpleNamespace(binding=binding, publish_branch='validation/v033-round5-c4-performance-123-1',
                output=root/'benchmarks/reports/round5-c4-performance-123-1/report.json.gz',
                state_dir=root/'.artifacts/round5-c4-performance-123-1')
            environment = {'GITHUB_RUN_ID':'123', 'GITHUB_RUN_ATTEMPT':'1',
                'GITHUB_REPOSITORY':'Afloat16/AI-Memory-Book', 'GITHUB_EVENT_NAME':'push',
                'GITHUB_REF':'refs/heads/ci/v033-round5-c4-performance'}
            with patch.object(bench, 'ROOT', root), patch.dict(bench.os.environ, environment):
                publication = bench.publication_identity(args)
                self.assertEqual(publication['claim_branch'],
                                 'validation/v033-round5-c4-claim-' + bench.sha(binding.read_bytes()))
                for altered in ({'GITHUB_RUN_ATTEMPT':'2'}, {'GITHUB_REF':'refs/heads/ci/v033-round5-performance'}):
                    with patch.dict(bench.os.environ, altered):
                        with self.assertRaisesRegex(ValueError, 'first-attempt'):
                            bench.publication_identity(args)
                args.publish_branch = 'validation/v033-round5-performance-123-1'
                with self.assertRaisesRegex(ValueError, 'validation branch'):
                    bench.publication_identity(args)
                args.publish_branch = publication['branch']
                args.output = root/'benchmarks/reports/round5-performance-123-1/report.json.gz'
                with self.assertRaisesRegex(ValueError, 'checkpoint directory'):
                    bench.publication_identity(args)
                args.output = root/'benchmarks/reports/round5-c4-performance-123-1/report.json.gz'
                args.state_dir = root/'.artifacts/round5-performance-123-1'
                with self.assertRaisesRegex(ValueError, 'C4 worker state'):
                    bench.publication_identity(args)

    def test_all_measurement_and_verification_functions_are_unchanged(self):
        allowed = {'bind', 'load_binding', 'publication_identity'}
        compared = []
        for name, function in vars(original).items():
            if inspect.isfunction(function) and function.__module__ == original.__name__ and name not in allowed:
                self.assertEqual(inspect.getsource(getattr(bench, name)), inspect.getsource(function), name)
                compared.append(name)
        self.assertIn('worker', compared)
        self.assertIn('controller', compared)
        self.assertIn('validation', compared)
        self.assertIn('audit', compared)
        self.assertIs(bench.previous.acceptance, original.previous.acceptance)
        self.assertIs(bench.previous.comparisons, original.previous.comparisons)
        self.assertEqual(bench.CONFIGURATIONS, original.CONFIGURATIONS)
        self.assertEqual(bench.PLAN, original.PLAN)
        self.assertEqual(bench.PACKAGES, original.PACKAGES)

    def test_tools_keep_every_frozen_c3_input_and_add_only_new_provenance(self):
        self.assertTrue(set(original.TOOLS).issubset(bench.TOOLS))
        for name in ('scripts/round5_c4_performance.py', 'tests/test_round5_c4_performance.py',
                     'tests/test_round5_candidate_c4.py', '.github/workflows/round5-c4-performance.yml',
                     bench.CONTINUATION_PATH, bench.C3_BINDING_PATH, bench.C3_SUMMARY_PATH):
            self.assertIn(name, bench.TOOLS)
        prior = json.loads((original.ROOT / bench.C3_BINDING_PATH).read_bytes())
        self.assertEqual(bench.sha((original.ROOT / bench.C3_BINDING_PATH).read_bytes()), bench.C3_BINDING_SHA256)
        for name, expected in prior['evaluator_files'].items():
            self.assertEqual(bench.sha((original.ROOT / name).read_bytes()), expected, name)

    def test_continuation_retains_complete_failed_c3_and_exact_preregistration(self):
        raw = (bench.ROOT / bench.CONTINUATION_PATH).read_bytes()
        with patch.object(bench, 'git', return_value=raw) as git:
            value = bench.continuation_registration()
            git.assert_called_once_with('show', bench.CONTINUATION_COMMIT + ':' + bench.CONTINUATION_PATH)
        self.assertEqual(value['document']['rejected_c3']['commit'], bench.C3_SOURCE['commit'])
        self.assertEqual(value['document']['formal_protocol']['thresholds_percent'],
                         original.load_plan()['thresholds_percent'])
        self.assertEqual(value['rejected_c3_summary_sha256'], bench.C3_SUMMARY_SHA256)
        with patch.object(bench, 'git', return_value=raw + b' '):
            with self.assertRaisesRegex(ValueError, 'preregistration bytes or commit'):
                bench.continuation_registration()

    def test_changed_c3_runtime_cannot_be_replayed_under_c4_label(self):
        args = SimpleNamespace(bind=bench.ROOT/bench.C4_BINDING_PATH,
                               baseline_src=Path('baseline/src'), candidate_src=Path('candidate/src'))
        for old_source in (bench.C3_SOURCE, bench.BASELINE):
            with patch.object(bench, 'continuation_registration', return_value={'fixture':True}), \
                    patch.object(bench, 'source_identity', side_effect=[bench.BASELINE, old_source]):
                with self.assertRaisesRegex(ValueError, 'materially changed source'):
                    bench.bind(args)
        args.bind = bench.ROOT/bench.C3_BINDING_PATH
        with self.assertRaisesRegex(ValueError, 'new C4 binding path'):
            bench.bind(args)
        with self.assertRaisesRegex(ValueError, 'separately committed C4 binding'):
            bench.load_binding(args.bind)

    def test_new_workflow_uses_separate_paths_and_fetches_registration_before_binding(self):
        workflow = (bench.ROOT/'.github/workflows/round5-c4-performance.yml').read_text()
        self.assertIn("branches: ['ci/v033-round5-c4-performance']", workflow)
        self.assertIn('scripts/round5_c4_performance.py', workflow)
        self.assertIn(bench.C4_BINDING_PATH, workflow)
        self.assertIn('round5-c4-performance-$GITHUB_RUN_ID-1', workflow)
        self.assertIn('validation/v033-round5-c4-performance-', workflow)
        self.assertIn('for provenance_commit in (evaluator, CONTINUATION_COMMIT):', workflow)
        self.assertLess(workflow.index('for provenance_commit in'), workflow.index('binding = load_binding('))
        self.assertNotIn('round5-performance-$GITHUB_RUN_ID', workflow)
        for name in ('tests.test_round5_c4_performance', 'tests.test_round5_candidate_c4'):
            self.assertIn(name, workflow)
