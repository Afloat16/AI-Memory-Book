import importlib.util
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks.full_workflow_eval import (hook_events, inputs, native_recall,
                                          active_source_root, main, operation_succeeded, pack_native, run,
                                          usage_summary, wall_summary)
from benchmarks.resume import _lock
from benchmarks.token_compare import TokenCounter


class NativeWorkflowProtocolTests(unittest.TestCase):
    def test_frozen_cohort_includes_every_question_and_native_capture_keeps_sources(self):
        _, sessions, cases = inputs()
        self.assertEqual((len(sessions), len(cases), sum(c['answerable'] for c in cases)), (42, 36, 30))
        self.assertEqual(len({s['project'] for s in sessions}), 6)
        for session in sessions:
            events = hook_events(session)
            self.assertEqual(len(events), 4)
            self.assertEqual(events[1]['body']['prompt'], session['messages'][0]['content'])
            self.assertEqual(events[2]['body']['_ai_memory_assistant']['excerpt'], session['messages'][1]['content'])
            self.assertIn('capture_assistant=1', events[2]['url'])
            self.assertNotIn('answers', repr(events))

    @unittest.skipUnless(importlib.util.find_spec('tiktoken'), 'optional benchmark tokenizer not installed')
    def test_native_packing_preserves_complete_source_slices_and_exact_cap(self):
        counter = TokenCounter('cl100k_base')
        text = 'Short first fact. ' + ('An indivisible very long sentence ' * 100) + '. 最后一句。再一条事实。'
        result = pack_native([('project/source', text)], counter, budget=50)
        self.assertLessEqual(counter.count(result['context']), 50)
        self.assertIn('Short first fact.', result['context'])
        self.assertNotIn('indivisible', result['context'])
        for ref in result['sources']:
            self.assertIn(text[ref['start']:ref['end']], result['context'])
        self.assertTrue(result['context'].endswith(('。', '.')))

    @unittest.skipUnless(importlib.util.find_spec('tiktoken'), 'optional benchmark tokenizer not installed')
    def test_native_raw_observations_are_read_and_never_replaced_by_gold(self):
        class Native:
            def __init__(self):
                self.calls = []
            def call(self, name, args):
                self.calls.append((name, args))
                if name == 'memory_query':
                    data = {'hits': [{'path': 'sessions/one.md'}], 'raw_hits': [{'session_id': 'raw-one'}]}
                elif name == 'memory_read_page':
                    data = {'body': 'The original native page says amber.'}
                else:
                    data = {'total': 1, 'observations': [{'id': 'ob1', 'body': 'The captured observation says violet.'}]}
                return {'ok': True, 'decoded': data, 'native_text': str(data), 'elapsed_ms': 1}
        native = Native()
        result = native_recall(native, {'project': 'p', 'query': 'Which colors?', 'answers': ['NEVER USE GOLD']},
                               TokenCounter('cl100k_base'))
        self.assertEqual([name for name, _ in native.calls],
                         ['memory_query', 'memory_read_page', 'memory_read_session_observations'])
        self.assertIn('amber', result['context'])
        self.assertIn('violet', result['context'])
        self.assertNotIn('GOLD', result['context'])
        self.assertEqual(result['read_calls'], 2)

    def test_unknown_usage_does_not_become_zero_cost(self):
        result = usage_summary([{'usage': {'prompt_tokens': 10}}, {'usage': {}}], 'usage')
        self.assertEqual(result['prompt_tokens']['known_subtotal'], 10)
        self.assertIsNone(result['prompt_tokens']['total_if_complete'])
        self.assertEqual(result['completion_tokens']['reported_calls'], 0)
        self.assertIsNone(result['completion_tokens']['total_if_complete'])

    def test_concurrent_resume_is_rejected_before_native_or_model_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _lock(root / 'checkpoint.json'), patch('benchmarks.full_workflow_eval.run_locked') as work:
                with self.assertRaisesRegex(RuntimeError, 'active runner'):
                    run(SimpleNamespace(output=root))
                work.assert_not_called()

    def test_interrupted_phase_duration_is_unknown_and_dry_run_is_not_a_summary(self):
        durations = wall_summary([{'elapsed_ms': 12.0}, {'status': 'interrupted_unknown_outcome'}])
        self.assertEqual(durations['known_subtotal_ms'], 12.0)
        self.assertEqual(durations['reported_operations'], 1)
        self.assertIsNone(durations['total_if_complete_ms'])
        dry = {'status': 'completed', 'result': {'ok': True, 'decoded': {'dry_run': True, 'page_id': None}}}
        self.assertFalse(operation_succeeded('native-consolidate:test', dry))
        self.assertFalse(operation_succeeded('native-embed', {'status': 'completed', 'result': {'failed': 1}}))

    def test_shadow_installed_runtime_cannot_be_attributed_to_current_checkout(self):
        import memory_book
        expected = Path(__file__).resolve().parents[1] / 'src/memory_book'
        actual = Path(memory_book.__file__).resolve().parent
        self.assertEqual(active_source_root(), actual)
        with patch.object(memory_book, '__file__', '/unrelated/site-packages/memory_book/__init__.py'):
            with self.assertRaisesRegex(ValueError, 'Imported memory_book runtime'):
                active_source_root()
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / 'site-packages/memory_book'
            shutil.copytree(expected, installed, ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(memory_book, '__file__', str(installed / '__init__.py')), patch(
                    'benchmarks.full_workflow_eval.inspect.getfile', return_value=str(installed / 'store.py')):
                self.assertEqual(active_source_root(), installed)
                with (installed / 'store.py').open('a') as stream:
                    stream.write('\n# changed installed runtime\n')
                with self.assertRaisesRegex(ValueError, 'Imported memory_book runtime'):
                    active_source_root()

    def test_cli_fails_for_incomplete_or_failed_workflows(self):
        for status, expected in [('completed', 0), ('completed_with_failures', 2), ('incomplete', 2)]:
            with patch('sys.argv', ['full_workflow_eval']), patch(
                    'benchmarks.full_workflow_eval.run', return_value={'status': status}):
                self.assertEqual(main(), expected)


if __name__ == '__main__':
    unittest.main()
