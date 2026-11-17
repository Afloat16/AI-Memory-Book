"""Artificial protocol failures; importing/running these never measures recall."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round5_performance as bench
from tests.test_round4_performance import fixture as old_fixture, ledger_bytes, save_worker


def fixture(factor=.80):
    report = old_fixture(factor)
    report['evaluator'] = bench.VERSION
    report['run']['evaluator'] = bench.VERSION
    report['run']['binding']['sources']['baseline'] = dict(bench.BASELINE)
    report['run']['binding']['evaluator_files'] = report['run']['evaluator_files']
    report['run']['plan_sha256'] = bench.sha(bench.PLAN.read_bytes())
    for worker in report['workers']:
        source = report['run']['binding']['sources'][worker['label']]
        worker['source'] = worker['source_after'] = source
        worker['run_identity_sha256'] = bench.digest(report['run'])
        for config in worker['configurations']:
            for row in config['rows']:
                row['engine_source_sha256'] = source['runtime_sha256']
        worker['ledger_sha256'] = bench.sha(ledger_bytes(worker))
    report['validation'] = bench.validation(report)
    report['comparisons'] = bench.previous.comparisons(report)
    report['acceptance'] = bench.previous.acceptance(report, report['comparisons'])
    return report


class RoundFiveAcceptanceTests(unittest.TestCase):
    def test_formal_timing_requires_remote_checkpoint_publication(self):
        with self.assertRaisesRegex(ValueError, 'remote checkpoints'):
            bench.controller(SimpleNamespace(publish_branch=None), {}, {})

    def test_publication_is_limited_to_registered_first_attempt_and_result_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root/'binding.json'
            binding.write_bytes(b'{}\n')
            args = SimpleNamespace(binding=binding, publish_branch='validation/v033-round5-performance-123-1',
                output=root/'benchmarks/reports/round5-performance-123-1/report.json.gz',
                state_dir=root/'.artifacts/state')
            environment = {'GITHUB_RUN_ID':'123', 'GITHUB_RUN_ATTEMPT':'1',
                'GITHUB_REPOSITORY':'Afloat16/AI-Memory-Book', 'GITHUB_EVENT_NAME':'push',
                'GITHUB_REF':'refs/heads/ci/v033-round5-performance'}
            with patch.object(bench, 'ROOT', root), patch.dict(bench.os.environ, environment):
                publication = bench.publication_identity(args)
                self.assertTrue(publication['claim_branch'].endswith(bench.sha(binding.read_bytes())))
                with patch.dict(bench.os.environ, {'GITHUB_RUN_ATTEMPT':'2'}):
                    with self.assertRaisesRegex(ValueError, 'first-attempt'):
                        bench.publication_identity(args)
                args.publish_branch = 'main'
                with self.assertRaisesRegex(ValueError, 'validation branch'):
                    bench.publication_identity(args)

    def test_plan_locks_published_baseline_matrix_and_existing_gates(self):
        plan = bench.load_plan()
        self.assertEqual(plan['baseline']['release'], 'v0.3.2')
        self.assertEqual(plan['baseline']['commit'], '692fb959ddf8934c5f516ba3d74ceb4385a2fa82')
        self.assertEqual(len(bench.schedule(plan)), 16)
        self.assertEqual(plan['performance_candidate']['formal']['calls'], 56784)
        self.assertEqual(len(plan['performance_candidate']['formal']['configs']), 6)
        for field, value in (('calls', 1), ('rounds', 2)):
            altered = copy.deepcopy(plan)
            altered['performance_candidate']['formal'][field] = value
            with patch.object(Path, 'read_bytes', return_value=bench.json_bytes(altered)):
                with self.assertRaisesRegex(ValueError, 'matrix changed'):
                    bench.load_plan()

    def test_equal_outputs_with_improvement_pass_original_numeric_gates(self):
        report = fixture()
        self.assertTrue(report['validation']['passed'], report['validation'])
        self.assertTrue(report['acceptance']['accepted'], report['acceptance'])
        self.assertAlmostEqual(report['acceptance']['geometric_mean_p95_improvement_percent'], 20)
        self.assertFalse(fixture(.95)['acceptance']['accepted'])

    def test_envelope_or_full_native_mismatch_rejects(self):
        for field in ('payload_sha256', 'native_payload_sha256', 'envelope_sha256'):
            report = fixture()
            config = report['workers'][-1]['configurations'][1]
            config['rows'][0][field] = '0' * 64
            validation = bench.validation(report)
            self.assertFalse(validation['passed'], field)

    def test_missing_worker_row_or_failed_invariant_rejects(self):
        report = fixture()
        report['workers'].pop()
        self.assertFalse(bench.validation(report)['passed'])
        report = fixture()
        report['workers'][0]['configurations'][0]['rows'].pop()
        self.assertFalse(bench.validation(report)['passed'])
        report = fixture()
        report['workers'][0]['configurations'][0]['rows'][0]['invariants']['source_span_errors'] = 1
        self.assertFalse(bench.validation(report)['passed'])

    def test_resource_review_cannot_be_silently_accepted(self):
        report = fixture()
        for worker in report['workers']:
            if worker['label'] == 'candidate':
                worker['fresh_ingestion_ms'] *= 1.11
        accepted = bench.previous.acceptance(report, bench.previous.comparisons(report))
        self.assertTrue(accepted['numeric_gate_passed'])
        self.assertFalse(accepted['accepted'])
        self.assertTrue(accepted['resource_review'])

    def test_execution_claim_is_exclusive_even_with_different_state_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / 'binding.json'
            binding.write_bytes(b'{}\n')
            args = SimpleNamespace(binding=binding, state_dir=root/'one', output=root/'report.json.gz')
            run = {'host': {'boot': 'same'}}
            claim = bench.claim_execution(args, run)
            self.assertEqual(claim['binding_sha256'], bench.sha(binding.read_bytes()))
            original = bench.execution_claim_path(binding).read_bytes()
            args.state_dir = root / 'two'
            with self.assertRaises(FileExistsError):
                bench.claim_execution(args, run)
            self.assertEqual(bench.execution_claim_path(binding).read_bytes(), original)

    def test_saved_row_audit_recomputes_arithmetic_and_rejects_corruption(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, output = root/'state', root/'report.json.gz'
            bench.exclusive(state/'run.json', report['run'])
            for worker in report['workers']:
                save_worker(state, worker, report['run'])
            raw = bench.atomic(output, report, compressed=True)
            summary = output.with_name('report.summary.json')
            bench.atomic(summary, bench.previous.summary(report, output.read_bytes(), raw))
            with patch.object(bench, 'load_plan', return_value=report['plan']), \
                    patch.object(bench, 'file_hashes', return_value=report['run']['evaluator_files']):
                checked = bench.audit(output, state)
                self.assertTrue(checked['audit_passed'])
                self.assertEqual(checked['retrieval_calls_during_audit'], 0)
                altered = copy.deepcopy(report)
                altered['acceptance']['geometric_mean_p95_improvement_percent'] = 99
                bench.atomic(output, altered, compressed=True)
                with self.assertRaisesRegex(ValueError, 'arithmetic'):
                    bench.audit(output, state)
                output.write_bytes(gzip.compress(raw, mtime=0))
                ledger = state/'workers'/f"{report['workers'][0]['key']}.attempts.jsonl.gz"
                ledger.write_bytes(gzip.compress(b'{}\n', mtime=0))
                with self.assertRaisesRegex(ValueError, 'ledgers differ'):
                    bench.audit(output, state)

    def test_exported_gzip_only_state_is_auditable_and_immutable(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, public = root/'state', root/'public'
            binding = root/'binding.json'
            binding.write_bytes(b'{}\n')
            args = SimpleNamespace(binding=binding, state_dir=state, output=public/'report.json.gz')
            bench.exclusive(state/'run.json', report['run'])
            for worker in report['workers']:
                save_worker(state, worker, report['run'])
            bench.export_checkpoint(args)
            self.assertFalse(list((public/'workers').glob('*.attempts.jsonl')))
            self.assertEqual(len(list((public/'workers').glob('*.attempts.jsonl.gz'))), len(report['workers']))
            for item in report['run']['schedule']:
                bench.load_completed(public, item, report['run'], report['plan'])
            bench.export_checkpoint(args)  # Reexport unchanged artifacts is idempotent.
            (public/'run.json').write_bytes(b'{}\n')
            with self.assertRaisesRegex(ValueError, 'immutable'):
                bench.export_checkpoint(args)


if __name__ == '__main__':
    unittest.main()
