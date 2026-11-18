"""Independent controls for fixes motivated by the retained scale failures."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from memory_book import MemoryBook
import memory_book.store as store


def record(identity, text, *, project='engine', newer=False):
    return {'project': project, 'task_id': 'configuration', 'task_title': 'Configuration',
            'session_id': identity, 'created_at': '2026-06-01T00:00:00Z' if newer else '2026-01-01T00:00:00Z',
            'messages': [{'role': 'assistant', 'content': text}]}


def first(result):
    return result['results'][0]['source_refs'][0]['session_id']


class MultiSourceDeclarationRegressions(unittest.TestCase):
    def test_repeated_literal_declarations_with_the_same_scope_remain_comparable(self):
        for repeated in ('Approved contract: execution_mode=parallel. Approved contract: execution_mode=parallel.',
                         'Approved current contract: execution_mode=parallel. 中文复核记录：当前生效约定为 execution_mode=parallel。'):
            with self.subTest(repeated=repeated), MemoryBook(':memory:', segmentation='turn') as book:
                book.ingest(record('old', 'Original approved contract: execution_mode=serial. ' + 'execution_mode record. ' * 12))
                book.ingest(record('new', repeated, newer=True))
                result = book.recall('current execution_mode', project='engine', limit=1)
                self.assertEqual(first(result), 'new')
                self.assertIn('execution_mode=parallel', result['context'])
                self.assertEqual(result['temporal']['evidence_assessment']['status'], 'comparable_declaration')

    def test_repeated_literals_do_not_merge_different_scopes_or_ineligible_references(self):
        cases = (
            'Production access_limit=12. Staging access_limit=12.',
            'Production access_limit=12. Proposed production access_limit=12.',
            'Production access_limit=12. Production access_limit=13.',
            'Production access_limit=12. Production access_limit=12. Example: access_limit=12.',
            'Production access_limit=12. Production access_limit=12. access_limit!=12.',
            'Production access_limit=12. Production access_limit=12. Example: "Production access_limit is 99."',
            'Production access_limit=12. Production access_limit=12. If approved, Production access_limit is 99.',
            'Production access_limit=12. Production access_limit=12. Production access_limit is not 12.',
            'Production access_limit=true. Production access_limit=True.',
            'Production access_limit=1 ms. Production access_limit=1 s.',
        )
        for text in cases:
            with self.subTest(text=text), MemoryBook(':memory:', segmentation='turn') as book:
                book.ingest(record('old', 'Production access_limit=30. ' + 'production access_limit record. ' * 16))
                book.ingest(record('uncertain', text, newer=True))
                result = book.recall('current production access_limit', project='engine', limit=1)
                self.assertEqual(first(result), 'old')

    def test_reporting_description_is_not_an_environment_or_a_code_identifier(self):
        with MemoryBook(':memory:', segmentation='turn') as book:
            book.ingest(record('old', 'The implementation contract is "contract-v1". ' + 'implementation contract. ' * 12))
            book.ingest(record('new', 'The implementation contract is "contract-v2".', newer=True))
            self.assertEqual(first(book.recall('current implementation contract', project='engine', limit=1)), 'new')
        with MemoryBook(':memory:', segmentation='turn') as book:
            book.ingest(record('old', 'Approved contract: execution_mode=serial. ' + 'execution_mode implementation contract. ' * 12))
            book.ingest(record('new', 'Approved contract: execution_mode=parallel.', newer=True))
            result = book.recall('current execution_mode implementation contract', project='engine', limit=1)
            self.assertEqual(first(result), 'new')
        with MemoryBook(':memory:', segmentation='turn') as book:
            book.ingest(record('field', 'Production implementation_contract=12.'))
            book.ingest(record('other', 'Staging contract=99. ' + 'implementation contract. ' * 12, newer=True))
            result = book.recall('current production implementation_contract', project='engine', limit=1)
            self.assertEqual(first(result), 'field')
        with MemoryBook(':memory:', segmentation='turn') as book:
            book.ingest(record('old', 'Implementation contract deadline=30. ' + 'implementation contract deadline. ' * 12))
            book.ingest(record('new', 'Implementation contract deadline=12.', newer=True))
            query = 'current "implementation contract" deadline'
            relevant = book.recall(query, project='engine', temporal='relevance', limit=1)
            current = book.recall(query, project='engine', limit=1)
            self.assertEqual(first(current), first(relevant))

    def test_reference_only_records_with_explicit_no_change_have_independent_wording(self):
        notes = (
            'We inspected the logs for task_limit. No new value was selected.',
            'We checked task_limit during the review. The configuration remains unchanged.',
            'The review examined task_limit records. This discussion proposes no approved parameter change.',
            'We inspected task_limit and jobs.task_scale logs. No new value was selected.',
        )
        for note in notes:
            with self.subTest(note=note), MemoryBook(':memory:', segmentation='turn') as book:
                book.ingest(record('decision', 'Approved configuration: task_limit=12.'))
                book.ingest(record('review', note + ' task_limit records. ' * 12, newer=True))
                result = book.recall('current task_limit', project='engine', limit=1)
                self.assertEqual(first(result), 'decision')
                self.assertIn('nondecision_priority', result['temporal'])

    def test_unparsed_unicode_quotes_do_not_gain_new_frame_qualification(self):
        for left, right in (('“', '”'), ('「', '」'), ('＂', '＂'), ('〝', '〞'),
                            ('❝', '❞'), ('｢', '｣'), ('＇', '＇')):
            for frame in ('当前生效约定为', '当前配置:', 'The 当前配置:'):
                with self.subTest(left=left, frame=frame), MemoryBook(':memory:', segmentation='turn') as book:
                    book.ingest(record('old', 'Approved configuration: access_limit=30. ' + 'access_limit record. ' * 12))
                    book.ingest(record('quoted', 'The log quotes another task: ' + left
                                       + 'First note. ' + frame + ' access_limit=12。' + right, newer=True))
                    self.assertEqual(first(book.recall('current access_limit', project='engine', limit=1)), 'old')
            with MemoryBook(':memory:', segmentation='turn') as book:
                book.ingest(record('old', 'Implementation contract deadline=30. ' + 'implementation contract deadline. ' * 12))
                book.ingest(record('new', 'Implementation contract deadline=12.', newer=True))
                self.assertEqual(first(book.recall('current ' + left + 'implementation contract' + right + ' deadline',
                                                  project='engine', limit=1)), 'old')

    def test_reference_records_preserve_negation_revocation_quotes_and_unknown_scope(self):
        notes = (
            'We did not inspect task_limit logs. No new value was selected.',
            'We inspected task_limit logs. No new value was selected. The previous value has been revoked.',
            'We inspected task_limit logs. No new value was selected. 旧值已被撤销。',
            'We inspected task_limit logs. No new value was selected. Do not use the previous setting.',
            'We inspected task_limit logs. No new value was selected. 旧配置不再适用。',
            'Staging staff inspected task_limit logs. No new value was selected.',
            'Earlier notes said "We inspected task_limit logs. No new value was selected."',
            'We inspected another_limit logs. No new value was selected.',
        )
        for note in notes:
            with self.subTest(note=note), MemoryBook(':memory:', segmentation='turn') as book:
                book.ingest(record('decision', 'Approved configuration: task_limit=12.'))
                book.ingest(record('review', note + ' task_limit records. ' * 12, newer=True))
                result = book.recall('current task_limit', project='engine', limit=1)
                self.assertEqual(first(result), 'review')
                self.assertNotIn('nondecision_priority', result['temporal'])

    def test_history_occurrences_and_exact_projects_keep_their_boundaries(self):
        with MemoryBook(':memory:', segmentation='turn') as book:
            for project, value in (('engine', 12), ('engine-copy', 99)):
                book.ingest(record('decision', f'Approved configuration: task_limit={value}.', project=project))
                book.ingest(record('review', 'We inspected task_limit logs. No new value was selected. '
                                   + 'task_limit records. ' * 12, project=project, newer=True))
            for query, temporal in (('current task_limit', 'relevance'), ('original task_limit', 'auto'),
                                    ('current task_limit occurrence count', 'auto')):
                result = book.recall(query, project='engine', temporal=temporal, limit=5)
                self.assertNotIn('nondecision_priority', result['temporal'])
                self.assertTrue(all(ref['project'] == 'engine' for hit in result['results'] for ref in hit['source_refs']))
            self.assertEqual(book.recall('current task_limit', project='ENGINE')['results'], [])

    def test_user_review_heading_must_match_real_navigation_metadata(self):
        for heading, expected in (('Engine regression review 12', 'decision'),
                                  ('Staging regression review 12', 'review'),
                                  ('Do not use the previous setting.', 'review')):
            with self.subTest(heading=heading), MemoryBook(':memory:', segmentation='turn') as book:
                decision = record('decision', 'Approved configuration: task_limit=12.')
                review = record('review', 'We inspected task_limit logs. No new value was selected. '
                                + 'task_limit records. ' * 12, newer=True)
                for source in (decision, review):
                    source['task_title'] = 'Engine parameter configuration'
                review['messages'].insert(0, {'role': 'user', 'content': heading})
                book.ingest(decision)
                book.ingest(review)
                self.assertEqual(first(book.recall('current task_limit', project='engine', limit=1)), expected)

    def test_no_change_report_preserves_separately_requested_current_check_result(self):
        with MemoryBook(':memory:', segmentation='turn') as book:
            decision = record('decision', 'Approved configuration: task_limit=12. The deployment checklist failed.')
            review = record('review', 'We inspected task_limit logs. No new value was selected. '
                            'The deployment checklist passed. ' + 'task_limit records. ' * 12, newer=True)
            for source in (decision, review):
                source['task_title'] = 'Deployment checklist'
                book.ingest(source)
            result = book.recall('What is the current task_limit and the result of the deployment checklist?',
                                 project='engine', limit=1)
            self.assertEqual(first(result), 'review')
            self.assertNotIn('nondecision_priority', result['temporal'])
            self.assertIn('checklist passed', result['context'])
            self.assertEqual(first(book.recall('current task_limit', project='engine', limit=1)), 'decision')

    def test_prior_recall_versions_are_invalidated(self):
        for old_version in (24, 25):
            with self.subTest(old_version=old_version), MemoryBook(':memory:', segmentation='turn') as book:
                book.ingest(record('decision', 'Approved configuration: task_limit=12.'))
                with patch.object(store, 'RECALL_VERSION', old_version):
                    book.recall('current task_limit', project='engine')
                self.assertFalse(book.recall('current task_limit', project='engine')['cache_hit'])


if __name__ == '__main__':
    unittest.main()
