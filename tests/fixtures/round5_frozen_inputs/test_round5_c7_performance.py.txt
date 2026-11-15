"""C7 registration/source guards with unchanged C6 measurement and failure fixtures.

These tests construct artificial records only; no recall or benchmark is run.
"""
import copy
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from scripts import round5_c6_performance as original
from scripts import round5_c7_performance as bench
from tests import test_round5_performance as inherited


def empty_snapshot():
    value = {name: 0 for name in bench.MEMO_FIELDS}
    value.update(available=True, entry_limit=2048, text_byte_limit=2097152)
    return value


def attach_memo_fixture(report):
    """Add artificial observation records, without calling a product API."""
    for worker in report['workers']:
        diagnostics = bench.memo_diagnostics()
        current = empty_snapshot() if worker['label'] == 'candidate' else dict(bench.MEMO_BASELINE)
        for config in worker['configurations']:
            if config['surface'] != 'native':
                continue
            before = copy.deepcopy(current)
            if worker['label'] == 'candidate' and config['id'] != 'native-char4000':
                current.update(allocated=1, entries=current['entries'] + 1,
                               text_bytes=current['text_bytes'] + 128, misses=current['misses'] + 1)
            first = copy.deepcopy(current)
            if worker['label'] == 'candidate' and config['id'] != 'native-char4000':
                current['hits'] += 1
            diagnostics['configurations'].append({'id': config['id'], 'before': before,
                'first_query_id': config['rows'][0]['query_id'],
                'after_first_call': first, 'after': copy.deepcopy(current)})
        worker['native_token_count_memo'] = diagnostics
    return report


class C7AcceptanceTests(inherited.RoundFiveAcceptanceTests):
    def setUp(self):
        super().setUp()
        replacement = patch.object(inherited, 'bench', bench)
        replacement.start()
        self.addCleanup(replacement.stop)
        original_fixture = inherited.fixture
        fixture_replacement = patch.object(inherited, 'fixture',
            side_effect=lambda *args, **kwargs: attach_memo_fixture(original_fixture(*args, **kwargs)))
        fixture_replacement.start()
        self.addCleanup(fixture_replacement.stop)

    def test_publication_is_limited_to_registered_first_attempt_and_result_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / bench.C7_BINDING_PATH
            binding.parent.mkdir(parents=True)
            binding.write_bytes(b'{}\n')
            args = SimpleNamespace(binding=binding, publish_branch='validation/v033-round5-c7-performance-123-1',
                output=root/'benchmarks/reports/round5-c7-performance-123-1/report.json.gz',
                state_dir=root/'.artifacts/round5-c7-performance-123-1')
            environment = {'GITHUB_RUN_ID':'123', 'GITHUB_RUN_ATTEMPT':'1',
                'GITHUB_REPOSITORY':'Afloat16/AI-Memory-Book', 'GITHUB_EVENT_NAME':'push',
                'GITHUB_REF':'refs/heads/ci/v033-round5-c7-performance'}
            with patch.object(bench, 'ROOT', root), patch.dict(bench.os.environ, environment):
                publication = bench.publication_identity(args)
                self.assertEqual(publication['claim_branch'],
                                 'validation/v033-round5-c7-claim-' + bench.sha(binding.read_bytes()))
                for altered in ({'GITHUB_RUN_ATTEMPT':'2'}, {'GITHUB_REF':'refs/heads/ci/v033-round5-c6-performance'}):
                    with patch.dict(bench.os.environ, altered):
                        with self.assertRaisesRegex(ValueError, 'first-attempt'):
                            bench.publication_identity(args)
                args.publish_branch = 'validation/v033-round5-c6-performance-123-1'
                with self.assertRaisesRegex(ValueError, 'validation branch'):
                    bench.publication_identity(args)
                args.publish_branch = publication['branch']
                args.output = root/'benchmarks/reports/round5-c6-performance-123-1/report.json.gz'
                with self.assertRaisesRegex(ValueError, 'checkpoint directory'):
                    bench.publication_identity(args)
                args.output = root/'benchmarks/reports/round5-c7-performance-123-1/report.json.gz'
                args.state_dir = root/'.artifacts/round5-c6-performance-123-1'
                with self.assertRaisesRegex(ValueError, 'C7 worker state'):
                    bench.publication_identity(args)

    def test_measurement_body_statistics_ledgers_and_actual_mcp_are_unchanged(self):
        allowed = {'require_registered_source', 'bind', 'load_binding', 'publication_identity',
                   'continuation_registration', 'worker', 'controller'}
        compared = []
        for name, function in vars(original).items():
            if inspect.isfunction(function) and function.__module__ == original.__name__ and name not in allowed:
                self.assertEqual(inspect.getsource(getattr(bench, name)), inspect.getsource(function), name)
                compared.append(name)
        for name in ('validation', 'audit', 'main', 'verify_native_memo', 'check_c6_registered_scope',
                     'rejected_c5_registration'):
            self.assertIn(name, compared)
        self.assertIs(bench.previous.acceptance, original.previous.acceptance)
        self.assertIs(bench.previous.comparisons, original.previous.comparisons)
        self.assertEqual(bench.CONFIGURATIONS, original.CONFIGURATIONS)
        self.assertEqual(bench.PLAN, original.PLAN)
        self.assertEqual(bench.PACKAGES, original.PACKAGES)
        self.assertIs(bench.mcp_configuration, original.mcp_configuration)
        expected = inspect.getsource(original.worker).replace('def worker(args, plan, binding):\n',
            'def worker(args, plan, binding):\n'
            '    require_registered_source()\n'
            '    require(binding.get("sources") == {"baseline": BASELINE, "candidate": C7_SOURCE},\n'
            '            "C7 worker must use the exact registered sources")\n', 1)
        self.assertEqual(inspect.getsource(bench.worker), expected)
        expected = inspect.getsource(original.controller).replace(
            '            "Formal timing requires a hosted binding claim and per-worker remote checkpoints")\n',
            '            "Formal timing requires a hosted binding claim and per-worker remote checkpoints")\n'
            '    require_registered_source()\n'
            '    require(binding.get("sources") == {"baseline": BASELINE, "candidate": C7_SOURCE},\n'
            '            "C7 controller must use the exact registered sources")\n', 1)
        self.assertEqual(inspect.getsource(bench.controller), expected)

    def test_development_only_adds_early_guards_and_new_source_identity(self):
        from scripts import round5_c6_development_pair as old_dev
        from scripts import round5_c7_development_pair as new_dev
        self.assertEqual(old_dev.CONFIGS, new_dev.CONFIGS)
        early = ('    sys.path.insert(0, str(ROOT))\n'
                 '    from scripts.round5_c7_performance import require_registered_source\n'
                 '    require_registered_source()\n')
        for name, function in vars(old_dev).items():
            if not inspect.isfunction(function) or function.__module__ != old_dev.__name__:
                continue
            expected = inspect.getsource(function).replace('from scripts.round5_c6_performance import',
                                                           'from scripts.round5_c7_performance import')
            if name == 'worker':
                expected = expected.replace('C6_SOURCE', 'C7_SOURCE').replace(
                    'def worker(args):\n', 'def worker(args):\n' + early, 1)
            elif name == 'main':
                changes = [
                    ('def main():\n', 'def main():\n' + early),
                    ('C5_SOURCE, C6_SOURCE, DEVELOPMENT_PLAN_PATH',
                     'C5_SOURCE, C6_SOURCE, C7_SOURCE, DEVELOPMENT_PLAN_PATH'),
                    ('if sources != {"baseline": BASELINE, "candidate": C6_SOURCE}:',
                     'if sources != {"baseline": BASELINE, "candidate": C7_SOURCE}:'),
                    ('(BASELINE, C3_SOURCE, C4_SOURCE, C5_SOURCE)}:',
                     '(BASELINE, C3_SOURCE, C4_SOURCE, C5_SOURCE, C6_SOURCE)}:'),
                    ('registered C6 source', 'registered C7 source'),
                    ('prior baseline/C3/C4/C5 runtime', 'prior baseline/C3/C4/C5/C6 runtime'),
                    ('Complete saved C6 development', 'Complete saved C7 development'),
                ]
                for before, after in changes:
                    self.assertEqual(expected.count(before), 1)
                    expected = expected.replace(before, after, 1)
            self.assertEqual(inspect.getsource(getattr(new_dev, name)), expected, name)

    def test_tools_preserve_exact_frozen_c6_inputs_plus_nine_new_inputs(self):
        prior = json.loads((bench.ROOT / bench.C6_BINDING_PATH).read_bytes())
        self.assertEqual(set(bench.C6_TOOLS), set(original.TOOLS))
        self.assertEqual(set(prior['evaluator_files']), set(bench.C6_TOOLS))
        additions = {'scripts/round5_c7_performance.py', 'scripts/round5_c7_development_pair.py',
            'tests/test_round5_c7_performance.py', 'tests/test_round5_candidate_c7.py',
            '.github/workflows/round5-c7-performance.yml', bench.DEVELOPMENT_PLAN_PATH,
            bench.CONTINUATION_PATH, bench.C6_BINDING_PATH, bench.C6_SUMMARY_PATH}
        self.assertEqual(set(bench.TOOLS) - set(bench.C6_TOOLS), additions)
        self.assertEqual(len(bench.TOOLS), len(bench.C6_TOOLS) + 9)
        self.assertEqual(len(set(bench.TOOLS)), len(bench.TOOLS))
        for name, expected in prior['evaluator_files'].items():
            self.assertEqual(bench.sha((bench.ROOT / name).read_bytes()), expected, name)

    def test_missing_registration_policy_or_source_blocks_all_direct_entrypoints(self):
        from scripts import round5_c7_development_pair as dev
        fields = ('CONTINUATION_COMMIT', 'CONTINUATION_SHA256', 'CONTINUATION_PROTOCOL',
                  'CONTINUATION_STATUS', 'DEVELOPMENT_PLAN_SHA256', 'C7_POLICY_KEY', 'C7_POLICY')
        for name in fields:
            self.assertIsNotNone(getattr(bench, name))
        self.assertEqual(bench.CONTINUATION_COMMIT, '718ce3bbe42e23774e616219bd8ae60d143fb76f')
        self.assertEqual(bench.CONTINUATION_SHA256, '7dc67e10049bf28ffc57060432442a0bdc371da2cc95506bf373e8381d50afeb')
        self.assertEqual(bench.C7_POLICY_KEY, 'mcp_stdout_policy')
        registered = json.loads((bench.ROOT/bench.CONTINUATION_PATH).read_bytes())
        self.assertEqual(bench.C7_POLICY, registered['mcp_stdout_policy'])
        for path, expected in ((bench.CONTINUATION_PATH, bench.CONTINUATION_SHA256),
                               (bench.DEVELOPMENT_PLAN_PATH, bench.DEVELOPMENT_PLAN_SHA256)):
            self.assertEqual(bench.sha((bench.ROOT/path).read_bytes()), expected)
        self.assertEqual(bench.C7_SOURCE, {'commit': 'd0c84cbfc9bad440ad447d41e211d070ef5b2cae',
            'runtime_sha256': '55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45'})
        valid = {'CONTINUATION_COMMIT': '1' * 40, 'CONTINUATION_SHA256': '2' * 64,
                 'CONTINUATION_PROTOCOL': 'artificial-unit-fixture', 'CONTINUATION_STATUS': 'artificial-unit-fixture',
                 'DEVELOPMENT_PLAN_SHA256': '3' * 64, 'C7_POLICY_KEY': 'fixture_policy',
                 'C7_POLICY': {'purpose': 'unit fixture only'},
                 'C7_SOURCE': {'commit': '4' * 40, 'runtime_sha256': '5' * 64}}
        cases = [{name: None} for name in fields]
        cases += [{'C7_SOURCE': {'commit': None, 'runtime_sha256': '5' * 64}},
                  {'C7_SOURCE': {'commit': '4' * 40, 'runtime_sha256': None}}]
        args = SimpleNamespace(bind=bench.ROOT/bench.C7_BINDING_PATH, publish_branch='fixture')
        calls = (bench.require_registered_source, bench.continuation_registration,
                 lambda: bench.bind(args), lambda: bench.load_binding(args.bind),
                 lambda: bench.main(['--bind', str(args.bind)]),
                 lambda: bench.main(['--binding', str(args.bind)]),
                 lambda: bench.main(['--worker', 'blocked', '--binding', str(args.bind)]),
                 lambda: bench.worker(SimpleNamespace(), {}, {}),
                 lambda: bench.controller(args, {}, {}), lambda: dev.worker(SimpleNamespace()), dev.main)
        for missing in cases:
            with self.subTest(missing=missing), patch.multiple(bench, **{**valid, **missing}), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('Blocked C7 must not read samples or measure')):
                for call in calls:
                    with self.assertRaisesRegex(ValueError, 'C7 is blocked'):
                        call()

    def test_unbound_transport_policy_cannot_be_guessed_or_relabel_c6(self):
        with patch.object(bench, 'C7_POLICY_KEY', None), patch.object(bench, 'C7_POLICY', None):
            with self.assertRaisesRegex(ValueError, 'C7 transport policy is blocked'):
                bench.check_c7_registered_scope({})
        # Only an in-memory artificial registration fixture; no C7 measured data is created.
        document = json.loads((bench.ROOT/'benchmarks/experiments/round5-c6-addendum.json').read_bytes())
        document['fixture_policy'] = {'purpose': 'unit fixture only'}
        document['rejected_c6'] = {**bench.C6_SOURCE, 'formal_run': '43557136276-1',
            'result_commit': bench.C6_RESULT_COMMIT, 'binding_sha256': bench.C6_BINDING_SHA256,
            'summary_sha256': bench.C6_SUMMARY_SHA256, 'aggregate_p95_gain_percent': 14.91917268891384,
            'public_native_best_gain_percent': 16.286785133390612,
            'public_mcp_token1024_gain_percent': 5.7989107559001996,
            'numeric_gate_passed': False, 'accepted': False,
            'decision': 'Preserve the complete valid C6 formal rejection. Do not rerun the same source to select a faster sample.'}
        with patch.object(bench, 'C7_POLICY_KEY', 'fixture_policy'), \
                patch.object(bench, 'C7_POLICY', {'purpose': 'unit fixture only'}):
            bench.check_c7_registered_scope(document)
            for section, key, value in (
                ('fixture_policy', 'purpose', 'changed'),
                ('source_work_policy', 'maximum_batch_pairs', 401),
                ('source_work_policy', 'maximum_batch_parameters', 801),
                ('cache_policy', 'continuation', 'additional persistent memo'),
                ('rejected_c6', 'binding_sha256', '0' * 64),
                ('rejected_c6', 'summary_sha256', '0' * 64),
                ('rejected_c6', 'public_mcp_token1024_gain_percent', 10),
                ('rejected_c6', 'numeric_gate_passed', True),
                ('rejected_c6', 'accepted', True),
            ):
                altered = copy.deepcopy(document)
                altered[section][key] = value
                with self.assertRaises(ValueError, msg=(section, key)):
                    bench.check_c7_registered_scope(altered)

    def test_complete_rejected_c6_and_every_original_input_remain_bound(self):
        raw = (bench.ROOT/bench.C6_SUMMARY_PATH).read_bytes()
        with patch.object(bench, 'git', return_value=raw) as git:
            result = bench.rejected_c6_registration()
            git.assert_called_once_with('show', bench.C6_RESULT_COMMIT + ':' + bench.C6_SUMMARY_PATH)
        self.assertEqual(result['rejected_c6_binding_sha256'], bench.C6_BINDING_SHA256)
        self.assertEqual(result['rejected_c6_summary_sha256'], bench.C6_SUMMARY_SHA256)
        self.assertEqual(result['rejected_c6_result_commit'], bench.C6_RESULT_COMMIT)
        self.assertEqual(set(result['frozen_c6_evaluator_files']), set(original.TOOLS))
        with patch.object(bench, 'git', return_value=raw + b' '):
            with self.assertRaisesRegex(ValueError, 'committed rejected summary bytes changed'):
                bench.rejected_c6_registration()

    def test_prior_runtime_cannot_be_replayed_under_c7_label(self):
        args = SimpleNamespace(bind=bench.ROOT/bench.C7_BINDING_PATH,
                               baseline_src=Path('baseline/src'), candidate_src=Path('candidate/src'))
        for old_source in (bench.BASELINE, bench.C3_SOURCE, bench.C4_SOURCE, bench.C5_SOURCE, bench.C6_SOURCE):
            with patch.object(bench, 'require_registered_source', return_value=None), \
                    patch.object(bench, 'continuation_registration', return_value={'fixture':True}), \
                    patch.object(bench, 'source_identity', side_effect=[bench.BASELINE, old_source]):
                with self.assertRaisesRegex(ValueError, 'materially changed source'):
                    bench.bind(args)
        for old_path in (bench.C3_BINDING_PATH, bench.C5_BINDING_PATH, bench.C6_BINDING_PATH):
            args.bind = bench.ROOT / old_path
            with self.assertRaisesRegex(ValueError, 'new C7 binding path'):
                bench.bind(args)
            with self.assertRaisesRegex(ValueError, 'separately committed C7 binding'):
                bench.load_binding(args.bind)

    def test_workflow_fetches_every_required_history_before_loading_new_binding(self):
        workflow = (bench.ROOT/'.github/workflows/round5-c7-performance.yml').read_text()
        self.assertIn("branches: ['ci/v033-round5-c7-performance']", workflow)
        self.assertIn('scripts/round5_c7_performance.py', workflow)
        self.assertIn(bench.C7_BINDING_PATH, workflow)
        self.assertIn('round5-c7-performance-$GITHUB_RUN_ID-1', workflow)
        self.assertIn('validation/v033-round5-c7-performance-', workflow)
        self.assertIn('for provenance_commit in (evaluator, CONTINUATION_COMMIT, C4_ARCHIVE_COMMIT, C5_RESULT_COMMIT, C6_RESULT_COMMIT):', workflow)
        self.assertLess(workflow.index('for provenance_commit in'), workflow.index('binding = load_binding('))
        self.assertNotIn('round5-c6-performance-$GITHUB_RUN_ID', workflow)
        for name in ('tests.test_round5_c6_performance', 'tests.test_round5_c7_performance',
                     'tests.test_round5_candidate_c6', 'tests.test_round5_candidate_c7'):
            self.assertIn(name, workflow)

    def test_native_diagnostics_retain_cold_start_continuity_and_first_query(self):
        report = inherited.fixture()
        for worker in report['workers']:
            bench.verify_native_memo(worker, worker['configurations'])
        candidate = next(w for w in report['workers'] if w['label'] == 'candidate')
        for edit in (
            lambda rows: rows[0]['before'].update(allocated=1),
            lambda rows: rows[0]['after'].update(allocated=1, hits=1),
            lambda rows: rows[2]['before'].update(hits=0),
            lambda rows: rows[1].update(first_query_id='different-query'),
            lambda rows: rows[1]['after'].update(entries=2049),
            lambda rows: rows[1]['after'].update(text_bytes=2097153),
        ):
            altered = copy.deepcopy(candidate)
            edit(altered['native_token_count_memo']['configurations'])
            with self.assertRaises(ValueError):
                bench.verify_native_memo(altered, altered['configurations'])
        del candidate['native_token_count_memo']
        with self.assertRaises(KeyError):
            bench.verify_native_memo(candidate, candidate['configurations'])


if __name__ == '__main__':
    unittest.main()
