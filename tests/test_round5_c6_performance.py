"""Blocked C6 namespace/provenance guards with unchanged C5 measurement fixtures plus inherited unchanged failure fixtures.

These tests construct artificial records only; no recall or benchmark is run.
"""
import copy
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from scripts import round5_c5_performance as original
from scripts import round5_c6_performance as bench
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


class C6AcceptanceTests(inherited.RoundFiveAcceptanceTests):
    def setUp(self):
        super().setUp()
        # Only the inherited artificial fixtures change their module under test.
        # The production C6 runner never monkeypatches its frozen predecessor.
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
            binding = root / bench.C6_BINDING_PATH
            binding.parent.mkdir(parents=True)
            binding.write_bytes(b'{}\n')
            args = SimpleNamespace(binding=binding, publish_branch='validation/v033-round5-c6-performance-123-1',
                output=root/'benchmarks/reports/round5-c6-performance-123-1/report.json.gz',
                state_dir=root/'.artifacts/round5-c6-performance-123-1')
            environment = {'GITHUB_RUN_ID':'123', 'GITHUB_RUN_ATTEMPT':'1',
                'GITHUB_REPOSITORY':'Afloat16/AI-Memory-Book', 'GITHUB_EVENT_NAME':'push',
                'GITHUB_REF':'refs/heads/ci/v033-round5-c6-performance'}
            with patch.object(bench, 'ROOT', root), patch.dict(bench.os.environ, environment):
                publication = bench.publication_identity(args)
                self.assertEqual(publication['claim_branch'],
                                 'validation/v033-round5-c6-claim-' + bench.sha(binding.read_bytes()))
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
                args.output = root/'benchmarks/reports/round5-c6-performance-123-1/report.json.gz'
                args.state_dir = root/'.artifacts/round5-performance-123-1'
                with self.assertRaisesRegex(ValueError, 'C6 worker state'):
                    bench.publication_identity(args)

    def test_all_measurement_and_verification_functions_are_unchanged(self):
        allowed = {'bind', 'load_binding', 'publication_identity', 'continuation_registration', 'main'}
        compared = []
        for name, function in vars(original).items():
            if inspect.isfunction(function) and function.__module__ == original.__name__ and name not in allowed:
                self.assertEqual(inspect.getsource(getattr(bench, name)), inspect.getsource(function), name)
                compared.append(name)
        self.assertIn('validation', compared)
        self.assertIn('audit', compared)
        self.assertIs(bench.previous.acceptance, original.previous.acceptance)
        self.assertIs(bench.previous.comparisons, original.previous.comparisons)
        self.assertEqual(bench.CONFIGURATIONS, original.CONFIGURATIONS)
        self.assertEqual(bench.PLAN, original.PLAN)
        self.assertEqual(bench.PACKAGES, original.PACKAGES)
        self.assertIs(bench.mcp_configuration, original.mcp_configuration)
        old_worker, new_worker = inspect.getsource(original.worker), inspect.getsource(bench.worker)
        start = 'seq = ledger.start(config["id"], identity)'
        stop = 'response.pop("latency_ms")'
        self.assertEqual(old_worker[old_worker.index(start):old_worker.index(stop)],
                         new_worker[new_worker.index(start):new_worker.index(stop)])
        from scripts import round5_c4_development_pair as old_dev
        from scripts import round5_c5_development_pair as new_dev
        self.assertEqual(old_dev.CONFIGS, new_dev.CONFIGS)
        old_worker, new_worker = inspect.getsource(old_dev.worker), inspect.getsource(new_dev.worker)
        start, stop = 'start = time.perf_counter_ns()', 'response.pop("latency_ms")'
        self.assertEqual(old_worker[old_worker.index(start):old_worker.index(stop)],
                         new_worker[new_worker.index(start):new_worker.index(stop)])

    def test_development_only_changes_imports_source_guards_and_error_label(self):
        from scripts import round5_c5_development_pair as old_dev
        from scripts import round5_c6_development_pair as new_dev
        self.assertEqual(old_dev.CONFIGS, new_dev.CONFIGS)
        replacements = {
            'worker': [(
                '    from scripts.round5_c5_performance import (memo_diagnostics, native_memo_snapshot,\n'
                '                                               verify_native_memo)\n',
                '    from scripts.round5_c6_performance import (BASELINE, C6_SOURCE, require_registered_source,\n'
                '        memo_diagnostics, native_memo_snapshot, verify_native_memo)\n'
                '    require_registered_source()\n'
                '    expected_source = {"baseline": BASELINE, "candidate": C6_SOURCE}.get(args.label)\n'
                '    if expected_source != {"commit": args.source_commit, "runtime_sha256": args.source_sha}:\n'
                '        raise ValueError("Development worker must use the exact registered source")\n',
            )],
            'main': [(
                '    from scripts.round5_c5_performance import (BASELINE, C3_SOURCE, C4_SOURCE, DEVELOPMENT_PLAN_PATH,\n',
                '    from scripts.round5_c6_performance import (BASELINE, C3_SOURCE, C4_SOURCE, C5_SOURCE, C6_SOURCE, DEVELOPMENT_PLAN_PATH,\n',
            ), (
                '    assert sources["baseline"] == BASELINE\n'
                '    assert sources["candidate"]["runtime_sha256"] not in {\n'
                '        source["runtime_sha256"] for source in (BASELINE, C3_SOURCE, C4_SOURCE)}\n',
                '    if sources != {"baseline": BASELINE, "candidate": C6_SOURCE}:\n'
                '        raise ValueError("Development source arguments must match the exact registered C6 source")\n'
                '    if sources["candidate"]["runtime_sha256"] in {\n'
                '            source["runtime_sha256"] for source in (BASELINE, C3_SOURCE, C4_SOURCE, C5_SOURCE)}:\n'
                '        raise ValueError("Development cannot replay a prior baseline/C3/C4/C5 runtime")\n',
            ), (
                '"Complete saved C5 development payload pair differs"',
                '"Complete saved C6 development payload pair differs"',
            )],
        }
        for name, function in vars(old_dev).items():
            if inspect.isfunction(function) and function.__module__ == old_dev.__name__:
                expected = inspect.getsource(function)
                for old, new in replacements.get(name, []):
                    self.assertEqual(expected.count(old), 1, name)
                    expected = expected.replace(old, new, 1)
                self.assertEqual(inspect.getsource(getattr(new_dev, name)), expected, name)

    def test_tools_keep_every_frozen_c3_input_and_add_only_new_provenance(self):
        self.assertTrue(set(original.TOOLS).issubset(bench.TOOLS))
        for name in ('scripts/round5_c6_performance.py', 'tests/test_round5_c6_performance.py',
                     'tests/test_round5_candidate_c6.py', '.github/workflows/round5-c6-performance.yml',
                     'scripts/round5_c5_development_pair.py', 'scripts/round5_c6_development_pair.py',
                     bench.DEVELOPMENT_PLAN_PATH,
                     bench.CONTINUATION_PATH, bench.C3_BINDING_PATH, bench.C3_SUMMARY_PATH, bench.C4_SUMMARY_PATH):
            self.assertIn(name, bench.TOOLS)
        prior = json.loads((original.ROOT / bench.C3_BINDING_PATH).read_bytes())
        self.assertEqual(bench.sha((original.ROOT / bench.C3_BINDING_PATH).read_bytes()), bench.C3_BINDING_SHA256)
        for name, expected in prior['evaluator_files'].items():
            self.assertEqual(bench.sha((original.ROOT / name).read_bytes()), expected, name)

    def test_registered_c6_without_frozen_source_cannot_read_binding_or_start_measurement(self):
        self.assertEqual(bench.CONTINUATION_COMMIT, '099cbaf427c28351d71f3995fd0ff42f9c881b38')
        self.assertEqual(bench.CONTINUATION_SHA256, '7ad88598c9ccb3492083be06448e92a76da7025501a1aa578a0e39d8bd94c9d5')
        self.assertEqual(bench.CONTINUATION_PROTOCOL, 'v033-c6-in-snapshot-source-work-continuation-v1')
        self.assertEqual(bench.CONTINUATION_STATUS, 'registered-before-c6-implementation-and-timing')
        self.assertEqual(bench.C6_SOURCE, {
            'commit': '1bd97221e31e8e975498ece00f4bbfb3e0426aac',
            'runtime_sha256': 'cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78'})
        self.assertEqual((bench.DEVELOPMENT_CALLS, bench.DEVELOPMENT_PAIRS, bench.DEVELOPMENT_ROUNDS,
                          bench.DEVELOPMENT_ORDER),
                         (18928, 9464, 2, [['baseline', 'candidate'], ['candidate', 'baseline']]))
        args = SimpleNamespace(bind=bench.ROOT/bench.C6_BINDING_PATH)
        with patch.object(bench, 'C6_SOURCE', {'commit': None, 'runtime_sha256': None}), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('Blocked C6 must not inspect files or measure')):
            for call in (bench.require_registered_source, bench.continuation_registration,
                         lambda: bench.bind(args),
                         lambda: bench.load_binding(bench.ROOT/bench.C6_BINDING_PATH),
                         lambda: bench.main(['--bind', str(args.bind)]),
                         lambda: bench.main(['--binding', str(args.bind)])):
                with self.assertRaisesRegex(ValueError, 'C6 is blocked'):
                    call()

    def test_registered_scope_and_committed_documents_reject_policy_or_c5_relabeling(self):
        for name, expected in ((bench.CONTINUATION_PATH, bench.CONTINUATION_SHA256),
                               (bench.DEVELOPMENT_PLAN_PATH, bench.DEVELOPMENT_PLAN_SHA256)):
            raw = (bench.ROOT/name).read_bytes()
            self.assertEqual(bench.sha(raw), expected)
        document = json.loads((bench.ROOT/bench.CONTINUATION_PATH).read_bytes())
        development = json.loads((bench.ROOT/bench.DEVELOPMENT_PLAN_PATH).read_bytes())
        self.assertEqual(development['engine_order'], bench.DEVELOPMENT_ORDER)
        bench.check_c6_registered_scope(document)
        for section, key, value in (
            ('source_work_policy', 'maximum_batch_pairs', 401),
            ('source_work_policy', 'maximum_batch_parameters', 801),
            ('source_work_policy', 'ownership', 'persistent across recalls'),
            ('source_work_policy', 'sqlite_statement_cache', 'enlarge to 256'),
            ('cache_policy', 'continuation', 'additional persistent source cache'),
            ('rejected_c5', 'binding_sha256', '0' * 64),
            ('rejected_c5', 'summary_sha256', '0' * 64),
            ('rejected_c5', 'result_commit', '0' * 40),
            ('rejected_c5', 'public_mcp_token1024_gain_percent', 10),
            ('rejected_c5', 'numeric_gate_passed', True),
            ('rejected_c5', 'accepted', True),
            ('rejected_c5', 'decision', 'accepted'),
        ):
            altered = copy.deepcopy(document)
            altered[section][key] = value
            with self.assertRaises(ValueError, msg=(section, key)):
                bench.check_c6_registered_scope(altered)

    def test_complete_rejected_c5_and_every_original_input_remain_bound(self):
        raw = (bench.ROOT/bench.C5_SUMMARY_PATH).read_bytes()
        with patch.object(bench, 'git', return_value=raw) as git:
            result = bench.rejected_c5_registration()
            git.assert_called_once_with('show', bench.C5_RESULT_COMMIT + ':' + bench.C5_SUMMARY_PATH)
        self.assertEqual(result['rejected_c5_binding_sha256'], bench.C5_BINDING_SHA256)
        self.assertEqual(result['rejected_c5_summary_sha256'], bench.C5_SUMMARY_SHA256)
        self.assertEqual(result['rejected_c5_result_commit'], bench.C5_RESULT_COMMIT)
        self.assertEqual(set(result['frozen_c5_evaluator_files']), set(original.TOOLS))
        self.assertEqual(set(bench.C5_TOOLS), set(original.TOOLS))
        with patch.object(bench, 'git', return_value=raw + b' '):
            with self.assertRaisesRegex(ValueError, 'committed rejected summary bytes changed'):
                bench.rejected_c5_registration()

    def test_prior_runtime_cannot_be_replayed_under_c6_label(self):
        args = SimpleNamespace(bind=bench.ROOT/bench.C6_BINDING_PATH,
                               baseline_src=Path('baseline/src'), candidate_src=Path('candidate/src'))
        for old_source in (bench.C3_SOURCE, bench.C4_SOURCE, bench.C5_SOURCE, bench.BASELINE):
            with patch.object(bench, 'require_registered_source', return_value=None), \
                    patch.object(bench, 'continuation_registration', return_value={'fixture':True}), \
                    patch.object(bench, 'source_identity', side_effect=[bench.BASELINE, old_source]):
                with self.assertRaisesRegex(ValueError, 'materially changed source'):
                    bench.bind(args)
        args.bind = bench.ROOT/bench.C3_BINDING_PATH
        with self.assertRaisesRegex(ValueError, 'new C6 binding path'):
            bench.bind(args)
        with self.assertRaisesRegex(ValueError, 'separately committed C6 binding'):
            bench.load_binding(args.bind)

    def test_new_workflow_uses_separate_paths_and_fetches_registration_before_binding(self):
        workflow = (bench.ROOT/'.github/workflows/round5-c6-performance.yml').read_text()
        self.assertIn("branches: ['ci/v033-round5-c6-performance']", workflow)
        self.assertIn('scripts/round5_c6_performance.py', workflow)
        self.assertIn(bench.C6_BINDING_PATH, workflow)
        self.assertIn('round5-c6-performance-$GITHUB_RUN_ID-1', workflow)
        self.assertIn('validation/v033-round5-c6-performance-', workflow)
        self.assertIn('for provenance_commit in (evaluator, CONTINUATION_COMMIT, C4_ARCHIVE_COMMIT, C5_RESULT_COMMIT):', workflow)
        self.assertLess(workflow.index('for provenance_commit in'), workflow.index('binding = load_binding('))
        self.assertNotIn('round5-performance-$GITHUB_RUN_ID', workflow)
        for name in ('tests.test_round5_c6_performance', 'tests.test_round5_candidate_c6'):
            self.assertIn(name, workflow)

    def test_native_diagnostics_require_empty_start_continuity_and_saved_first_query(self):
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

    def test_baseline_memo_is_explicitly_unavailable_and_candidate_snapshot_is_bounded(self):
        class UntouchedBaseline:
            def _token_memo_snapshot(self):
                raise AssertionError('Do not probe the baseline for a new candidate API')
        self.assertEqual(bench.native_memo_snapshot(UntouchedBaseline(), 'baseline'), bench.MEMO_BASELINE)
        with self.assertRaisesRegex(ValueError, 'read-only native memo'):
            bench.native_memo_snapshot(object(), 'candidate')
        baseline = {'label': 'baseline'}
        for value in ({'available': False}, empty_snapshot(), {'available': False, 'reason': 'unknown'}):
            with self.assertRaises(ValueError):
                bench.check_memo_snapshot(value, baseline['label'])
        valid = empty_snapshot()
        bench.check_memo_snapshot(valid, 'candidate')
        for field, value in (('entry_limit', 4096), ('text_byte_limit', 4194304), ('hits', True), ('misses', -1)):
            with self.assertRaises(ValueError):
                bench.check_memo_snapshot({**valid, field: value}, 'candidate')
