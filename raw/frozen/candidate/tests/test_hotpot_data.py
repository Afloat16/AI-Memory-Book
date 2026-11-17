import copy
import unittest

from benchmarks.hotpot_data import convert_hotpot, selected_ids


class HotpotDataTests(unittest.TestCase):
    def fixture(self):
        return [{"_id": "sample", "question": "PRIVATE_QUESTION", "answer": "PRIVATE_ANSWER",
                 "type": "bridge", "context": [["Alpha", ["Alpha sentence. ", "Second fact."]],
                                                  ["Beta", ["Beta fact."]]],
                 "supporting_facts": [["Alpha", 1], ["Beta", 0]]}]

    def test_all_source_paragraphs_are_indexed_and_labels_stay_out(self):
        data = convert_hotpot(self.fixture(), ["sample"])
        self.assertEqual(len(data.sessions), 2)
        indexed = str(data.sessions)
        self.assertNotIn("PRIVATE_QUESTION", indexed)
        self.assertNotIn("PRIVATE_ANSWER", indexed)
        self.assertNotIn("supporting_facts", indexed)
        self.assertEqual(data.queries[0].required[0].needle, "Second fact.")
        self.assertEqual(data.queries[0].required[0].turn_index, 1)
        self.assertEqual(data.sessions[0]["messages"], [
            {"role": "user", "content": "Alpha sentence. "},
            {"role": "user", "content": "Second fact."}])
        self.assertEqual(data.sessions[1]["messages"], [{"role": "user", "content": "Beta fact."}])
        self.assertEqual(data.queries[0].required[1].session_id, "sample-article-1")
        self.assertNotEqual(data.sessions[0]["task_id"], data.sessions[1]["task_id"])
        self.assertEqual(data.queries[0].project, data.sessions[0]["project"])

    def test_canonical_history_does_not_depend_on_supporting_labels(self):
        items = self.fixture()
        changed = copy.deepcopy(items)
        changed[0]["supporting_facts"] = [["Alpha", 0]]
        self.assertEqual(convert_hotpot(items, ["sample"]).sessions,
                         convert_hotpot(changed, ["sample"]).sessions)

    def test_frozen_selection_depends_on_id_only(self):
        items = self.fixture()
        changed = copy.deepcopy(items)
        changed[0]["question"] = "different question"
        changed[0]["answer"] = "different answer"
        self.assertEqual(selected_ids(items, 1), selected_ids(changed, 1))
        with self.assertRaises(ValueError):
            selected_ids(items + items, 1)

    def test_invalid_supporting_fact_is_never_silently_removed(self):
        for support in ([["missing", 0]], [["Alpha", 99]], [["Alpha", True]], []):
            items = self.fixture()
            items[0]["supporting_facts"] = support
            with self.subTest(support=support), self.assertRaises(ValueError):
                convert_hotpot(items, ["sample"])
