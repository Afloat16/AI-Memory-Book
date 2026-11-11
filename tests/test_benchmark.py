"""Test benchmark correctness, not a desired ranking outcome."""

import unittest
from dataclasses import asdict

from benchmarks.data import Evidence, QueryCase, generate_dataset
from benchmarks.run import aggregate, evaluate_response, percentile


class DatasetTests(unittest.TestCase):
    def test_deterministic_and_split_specific(self):
        first = generate_dataset(11, "development", 2)
        second = generate_dataset(11, "development", 2)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.sessions, second.sessions)
        self.assertEqual(first.queries, second.queries)
        heldout = generate_dataset(11, "heldout", 2)
        self.assertNotEqual(first.fingerprint, heldout.fingerprint)
        self.assertNotEqual({case.query for case in first.queries},
                            {case.query for case in heldout.queries})

    def test_evidence_labels_resolve_to_original_turns(self):
        dataset = generate_dataset(11, "development", 2)
        indexed = {}
        for session in dataset.sessions:
            turn = -1
            for message in session["messages"]:
                if message["role"] == "user":
                    turn += 1
                indexed.setdefault((session["session_id"], turn), [])
                indexed[(session["session_id"], turn)].append(message["content"])
        for case in dataset.queries:
            self.assertEqual(case.answerable, bool(case.required), case.id)
            for evidence in case.required + case.stale:
                self.assertIn(evidence.needle,
                              "\n".join(indexed[(evidence.session_id, evidence.turn_index)]),
                              (case.id, asdict(evidence)))

    def test_required_categories_and_bilingual_data(self):
        dataset = generate_dataset(11, "development", 2)
        categories = {case.category for case in dataset.queries}
        self.assertTrue({"cross_session", "long_answer_middle", "short_followup",
                         "cross_project_name", "low_overlap_paraphrase", "latest_decision",
                         "unanswerable_unrelated", "unanswerable_related"} <= categories)
        self.assertEqual(len(dataset.sessions), 28)
        self.assertTrue(any("刷新令牌" in message["content"]
                            for session in dataset.sessions for message in session["messages"]))
        self.assertTrue(any("Refresh tokens" in message["content"]
                            for session in dataset.sessions for message in session["messages"]))
        # At least one fact is genuinely far into a long answer, rather than
        # a long page whose relevant information is always in the prefix.
        long_cases = [case for case in dataset.queries if case.category == "long_answer_middle"]
        for case in long_cases:
            evidence = case.required[0]
            session = next(item for item in dataset.sessions
                           if item["session_id"] == evidence.session_id)
            text = session["messages"][1]["content"]
            self.assertGreater(text.index(evidence.needle), 1000)
            self.assertGreater(len(text) - text.index(evidence.needle), 1000)

    def test_long_corpus_contains_real_scale_and_separated_evidence(self):
        dataset = generate_dataset(11, "development", 8)
        self.assertGreaterEqual(dataset.source_characters, 500_000)
        journals = [session for session in dataset.sessions
                    if session["task_id"] == "engineering-journal"]
        self.assertEqual(len(journals), 16)
        self.assertTrue(all(sum(message["role"] == "user" for message in session["messages"]) == 64
                            for session in journals))
        multi = [case for case in dataset.queries if case.category == "multi_section"]
        self.assertEqual(len(multi), 16)
        self.assertTrue(all(case.required[0].session_id == case.required[1].session_id
                            and abs(case.required[0].turn_index - case.required[1].turn_index) > 40
                            for case in multi))
        short = generate_dataset(11, "development", 8, include_long_sessions=False)
        self.assertEqual(short.description()["version"], "1.0")
        self.assertEqual(short.fingerprint, "7c4bff5efb192ea2ac5a7e42603d6df1f7b0f97fbe8931cb025320fbaac8adeb")


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evidence = Evidence("s-1", 0, "The chosen value is 45 seconds.")
        self.case = QueryCase("q-1", "Which value?", "lookup", "p", (self.evidence,))

    def response(self, text=None, refs=None, context=None):
        text = self.evidence.needle if text is None else text
        refs = [{"session_id": "s-1", "turn_index": 0, "start": 0,
                 "end": len(text)}] if refs is None else refs
        context = text if context is None else context
        return {"results": [{"id": "page-1", "text": text, "source_refs": refs}],
                "context": context, "context_chars": len(context)}

    def test_requires_correct_source(self):
        report = evaluate_response(self.case, self.response(), 4000)
        self.assertEqual(report["matched_evidence"], 1)
        wrong = self.response(refs=[{"session_id": "other", "turn_index": 0}])
        self.assertEqual(evaluate_response(self.case, wrong, 4000)["matched_evidence"], 0)
        wrong_project = self.response(refs=[{"project": "other", "session_id": "s-1", "turn_index": 0}])
        self.assertEqual(evaluate_response(self.case, wrong_project, 4000)["matched_evidence"], 0)

    def test_original_source_span_must_contain_evidence(self):
        original = "USER: Question\n\nASSISTANT: " + self.evidence.needle
        sources = {("p", "s-1", 0): original}
        response = self.response(refs=[{"project": "p", "session_id": "s-1", "turn_index": 0,
                                       "turn_start": 0, "turn_end": 5}])
        self.assertEqual(evaluate_response(self.case, response, 4000, sources)["matched_evidence"], 0)
        response["results"][0]["source_refs"][0]["turn_end"] = len(original)
        self.assertEqual(evaluate_response(self.case, response, 4000, sources)["matched_evidence"], 1)

    def test_lost_to_budget_is_not_a_hit(self):
        report = evaluate_response(self.case, self.response(context="truncated before answer"), 4000)
        self.assertFalse(report["complete"])
        self.assertEqual(report["matched_evidence"], 0)

    def test_cross_session_requires_all_evidence(self):
        case = QueryCase("q-2", "Which value and why?", "cross_session", "p",
                         (self.evidence, Evidence("s-2", 1, "Because prices change frequently.")))
        row = evaluate_response(case, self.response(), 4000)
        self.assertEqual(row["required_evidence"], 2)
        self.assertEqual(row["matched_evidence"], 1)
        self.assertFalse(row["complete"])
        summary = aggregate([row])
        self.assertEqual(summary["evidence_recall"], .5)
        self.assertEqual(summary["complete_evidence_rate"], 0)

    def test_budget_and_reported_size_are_checked(self):
        response = self.response()
        response["context_chars"] = 1
        row = evaluate_response(self.case, response, 5)
        self.assertTrue(row["budget_violation"])
        self.assertFalse(row["context_size_consistent"])

    def test_unanswerable_not_vacuously_complete(self):
        case = QueryCase("q-none", "Unknown?", "unanswerable_related", "p", answerable=False)
        row = evaluate_response(case, self.response(), 4000)
        self.assertFalse(row["complete"])
        summary = aggregate([row])
        self.assertIsNone(summary["evidence_recall"])
        self.assertEqual(summary["unanswerable_nonempty_rate"], 1)

    def test_latest_stale_diagnostics(self):
        stale = Evidence("s-old", 0, "The old value was 90 seconds.")
        case = QueryCase("q-latest", "Current?", "latest_decision", "p", (self.evidence,), (stale,))
        response = self.response(stale.needle, [{"session_id": "s-old", "turn_index": 0}])
        row = evaluate_response(case, response, 4000)
        self.assertTrue(row["stale_only"])
        self.assertFalse(row["stale_before_current"])

    def test_percentiles_handle_small_samples(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([3], .95), 3)
        self.assertEqual(percentile([1, 3], .5), 2)
        self.assertAlmostEqual(percentile([1, 3], .95), 2.9)

    def test_overlap_uses_original_turn_coordinates(self):
        response = self.response()
        response["results"][0]["source_refs"] = [
            {"session_id": "s-1", "turn_index": 0, "start": 0, "end": 30,
             "turn_start": 0, "turn_end": 30}]
        response["results"].append({"id": "page-2", "text": "a continuation",
                                    "source_refs": [{"session_id": "s-1", "turn_index": 0,
                                                     "start": 0, "end": 30,
                                                     "turn_start": 30, "turn_end": 60}]})
        self.assertEqual(evaluate_response(self.case, response, 4000)["duplicate_source_characters"], 0)
        response["results"][1]["source_refs"][0]["turn_start"] = 20
        self.assertEqual(evaluate_response(self.case, response, 4000)["duplicate_source_characters"], 10)

    def test_source_overlap_is_scoped_by_project(self):
        response = self.response()
        response["results"][0]["breadcrumb"] = [{"id": "one", "kind": "project"}]
        response["results"].append({"id": "page-2", "text": "different project",
                                    "source_refs": [{"session_id": "s-1", "turn_index": 0,
                                                     "start": 0, "end": 30}],
                                    "breadcrumb": [{"id": "two", "kind": "project"}]})
        self.assertEqual(evaluate_response(self.case, response, 4000)["duplicate_source_characters"], 0)


if __name__ == "__main__":
    unittest.main()
