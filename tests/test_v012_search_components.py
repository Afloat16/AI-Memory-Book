"""Reject falsified source mappings, scope, request labels and matrix membership."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from benchmarks import engineering_workflow as workflow
from benchmarks.v012_search_components import (
    SOURCE_FILES, audit_inventory, audit_summaries, fresh_output, validate_native,
)
from benchmarks.competitors.v012_search_components import result_identity


class SearchComponentEvidenceTests(unittest.TestCase):
    def fixture(self, backend):
        doc = {'id': 'page', 'project': "alpha' OR 1=1 --", 'title': 'Marker',
               'text': 'USER: marker\n\nASSISTANT: 保留值=17.',
               'created_at': '2026-01-01T09:00:00+00:00'}
        if backend == 'lancedb_fts':
            payload = {'rows': [{**doc, '_score': 2.0}]}
        else:
            payload = {'hits': [{'fields': dict(doc), 'docnum': 3, 'score': 2.0}],
                       'parsed_query': 'text:marker', 'scored_length': 1}
        native = {'hit_ids': ['page'], 'records': [{key: doc[key] for key in ('id', 'project', 'text')}],
                  'scores': [2.0], 'native_payload': payload,
                  'request': {'query': 'marker', 'project': doc['project'], 'limit': 5},
                  'network_attempts': 0}
        return doc, native

    def test_complete_native_fields_bind_source_and_request(self):
        for backend in ('lancedb_fts', 'whoosh_bm25f_or'):
            doc, native = self.fixture(backend)
            with self.subTest(backend=backend):
                self.assertEqual(validate_native(backend, native, {'page': doc}, doc['project'], 'marker'), ['page'])
            for key, replacement in (('text', 'truncated'), ('title', 'foreign title'),
                                     ('created_at', '2030-01-01T00:00:00Z'), ('project', 'alpha')):
                changed = copy.deepcopy(native)
                row = (changed['native_payload']['rows'][0] if backend == 'lancedb_fts'
                       else changed['native_payload']['hits'][0]['fields'])
                row[key] = replacement
                with self.subTest(backend=backend, field=key), self.assertRaises(ValueError):
                    validate_native(backend, changed, {'page': doc}, doc['project'], 'marker')
            for key, value in (('query', 'rewritten marker'), ('project', 'alpha'), ('limit', 6)):
                changed = copy.deepcopy(native)
                changed['request'][key] = value
                with self.subTest(backend=backend, request=key), self.assertRaises(ValueError):
                    validate_native(backend, changed, {'page': doc}, doc['project'], 'marker')

    def test_scope_prefix_and_full_mapping_cannot_launder_foreign_page(self):
        for backend in ('lancedb_fts', 'whoosh_bm25f_or'):
            doc, native = self.fixture(backend)
            with self.subTest(backend=backend), self.assertRaises(ValueError):
                validate_native(backend, native, {'page': doc}, 'alpha', 'marker')
            changed = copy.deepcopy(native)
            changed['hit_ids'] *= 2
            changed['records'] *= 2
            changed['scores'] *= 2
            with self.subTest(backend=backend), self.assertRaises(ValueError):
                validate_native(backend, changed, {'page': doc}, doc['project'], 'marker')

    def test_native_scores_and_empty_outputs_are_preserved(self):
        for backend in ('lancedb_fts', 'whoosh_bm25f_or'):
            doc, native = self.fixture(backend)
            changed = copy.deepcopy(native)
            changed['scores'][0] = 99
            with self.subTest(backend=backend), self.assertRaises(ValueError):
                validate_native(backend, changed, {'page': doc}, doc['project'], 'marker')
            empty = {**native, 'hit_ids': [], 'records': [], 'scores': [],
                     'native_payload': {'rows': []} if backend == 'lancedb_fts'
                     else {'hits': [], 'parsed_query': 'text:marker', 'scored_length': 0}}
            self.assertEqual(validate_native(backend, empty, {'page': doc}, doc['project'], 'marker'), [])

    def test_stability_covers_complete_payload_and_request_but_excludes_timing(self):
        _, native = self.fixture('whoosh_bm25f_or')
        self.assertEqual(result_identity(native), result_identity({**native, 'search_ms': 9.0}))
        for field in ('request', 'native_payload', 'scores'):
            changed = copy.deepcopy(native)
            if field == 'request': changed[field]['query'] = 'rewrite'
            elif field == 'native_payload': changed[field]['hits'][0]['fields']['title'] = 'changed'
            else: changed[field] = [2.1]
            self.assertNotEqual(result_identity(native), result_identity(changed))

    def inventory(self):
        case = {'id': 'case', 'query': 'marker', 'project': 'alpha', 'checkpoint': 1,
                'category': 'scope', 'required': [], 'stale': [], 'consumer_family': None}
        settings = {'backends': ['lancedb_fts', 'whoosh_bm25f_or'],
                    'budgets_chars': [1200, 2400], 'repeats': 3, 'top_k': 5}
        native, rows = [], []
        for backend in settings['backends']:
            native.append({'backend': backend, 'case_id': 'case', 'query': 'marker', 'project': 'alpha',
                           'checkpoint': 1, 'samples': [{'repetition': index, 'adapter_call_ms': index + .5}
                                                     for index in range(3)]})
            for budget in settings['budgets_chars']:
                rows.append({'backend': backend, 'case_id': 'case', 'query': 'marker', 'project': 'alpha',
                             'checkpoint': 1, 'category': 'scope', 'budget_chars': budget,
                             'latency_ms': [.5, 1.5, 2.5], 'repeat_outputs_equal': True,
                             'score': workflow.score(case, {'context': '', 'results': []}, {}, budget)})
        return [{'checkpoint': 1, 'cases': [case]}], settings, native, rows

    def test_full_matrix_rejects_omissions_duplicates_and_extra_cases(self):
        steps, settings, native, rows = self.inventory()
        audit_inventory(steps, settings, native, rows)
        variants = ((native[:-1], rows), (native, rows[:-1]), (native + native[:1], rows),
                    (native, rows + rows[:1]), (native + [{**native[0], 'case_id': 'undeclared'}], rows))
        for altered_native, altered_rows in variants:
            with self.subTest(), self.assertRaises(ValueError):
                audit_inventory(steps, settings, altered_native, altered_rows)

    def test_matrix_rejects_query_scope_checkpoint_category_and_repetition_drift(self):
        steps, settings, native, rows = self.inventory()
        for key, value in (('query', 'rewritten'), ('project', 'foreign'), ('checkpoint', 2)):
            changed = copy.deepcopy(native)
            changed[0][key] = value
            with self.subTest(native=key), self.assertRaises(ValueError):
                audit_inventory(steps, settings, changed, rows)
        for key, value in (('query', 'rewritten'), ('project', 'foreign'), ('checkpoint', 2),
                           ('category', 'other'), ('latency_ms', [0, 0, 0])):
            changed = copy.deepcopy(rows)
            changed[0][key] = value
            with self.subTest(packed=key), self.assertRaises(ValueError):
                audit_inventory(steps, settings, native, changed)
        changed = copy.deepcopy(native)
        changed[0]['samples'].reverse()
        with self.assertRaises(ValueError):
            audit_inventory(steps, settings, changed, rows)

    def test_category_summary_is_independently_recomputed(self):
        _, _, _, rows = self.inventory()
        report = {'summary': workflow.summarize(rows), 'by_category': {'scope': workflow.summarize(rows)}}
        audit_summaries(report, rows)
        changed = copy.deepcopy(report)
        changed['by_category']['scope'][0]['cases'] += 1
        with self.assertRaises(ValueError):
            audit_summaries(changed, rows)

    def test_evaluator_binds_current_adapter_harness_protocol_and_lock(self):
        self.assertTrue({'benchmarks/v012_search_components.py',
                         'benchmarks/competitors/v012_search_components.py',
                         'benchmarks/competitors/v012_search_components.lock.json',
                         'benchmarks/competitors/v012_search_components.protocol.md'} <= set(SOURCE_FILES))

    def test_existing_failure_attempt_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = fresh_output(Path(temporary) / 'attempt')
            (output / 'failure.txt').write_text('original failure')
            with self.assertRaises(ValueError): fresh_output(output)
            self.assertEqual((output / 'failure.txt').read_text(), 'original failure')


if __name__ == '__main__':
    unittest.main()
