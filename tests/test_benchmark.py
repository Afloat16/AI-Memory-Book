"""Test benchmark correctness, not a desired ranking outcome."""

import unittest
from dataclasses import asdict
import copy
import importlib.util

from benchmarks.data import Dataset, Evidence, QueryCase, generate_dataset
from benchmarks.run import aggregate, evaluate_response, percentile
from benchmarks.public_data import convert_locomo
from benchmarks.token_compare import TokenCounter, evidence_blocks, pack_whole_blocks, score_row
from benchmarks.component_eval import evidence_attainability, shared_response


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


class WholeBlockPackingTests(unittest.TestCase):
    class CharacterCounter:
        name = "test-character-counter"

        def count(self, text):
            return len(text)

    def response(self, entries):
        results = [{"id": page, "text": text, "source_refs": refs}
                   for page, text, refs in entries]
        context = "\n\n".join(f"[{item['id']}]\n{item['text']}" for item in results)
        return {"results": results, "context": context, "context_chars": len(context),
                "budget_chars": 10000}

    def test_whole_blocks_skip_oversized_and_preserve_source_spans(self):
        refs = [{"project": "p", "session_id": "s", "turn_index": 1,
                 "start": 0, "end": 8, "turn_start": 101, "turn_end": 109}]
        response = self.response([("large", "x" * 100, refs), ("small", "evidence", refs)])
        original = copy.deepcopy(response)
        packed = pack_whole_blocks(response, 16, self.CharacterCounter())
        self.assertEqual(packed["context"], "[small]\nevidence")
        self.assertLessEqual(len(packed["context"]), 16)
        self.assertEqual(packed["results"][0]["source_refs"], refs)
        self.assertEqual(response, original)
        packed["results"][0]["source_refs"][0]["turn_start"] = 0
        self.assertEqual(response, original)

    def test_context_metadata_disagreement_fails_closed(self):
        response = self.response([("one", "present evidence", [])])
        response["context"] = "[one]\ndifferent evidence"
        with self.assertRaises(ValueError):
            evidence_blocks(response)
        response["context"] = "[one]\npresent evidence\nundocumented tail"
        with self.assertRaises(ValueError):
            evidence_blocks(response)

    def test_lost_source_not_credited_for_duplicate_text_elsewhere(self):
        fact = "The chosen value is 45 seconds."
        original = "USER: " + fact
        valid = [{"project": "p", "session_id": "correct", "turn_index": 0,
                  "turn_start": 0, "turn_end": len(original)}]
        wrong = [{**valid[0], "session_id": "wrong"}]
        response = self.response([("first", fact + " extra" * 40, valid),
                                  ("second", fact, wrong)])
        case = QueryCase("q", "Which value?", "lookup", "p", (Evidence("correct", 0, fact),))
        packed = pack_whole_blocks(response, 50, self.CharacterCounter())
        self.assertIn(fact, packed["context"])
        row = evaluate_response(case, packed, 10000, {("p", "correct", 0): original})
        self.assertEqual(row["matched_evidence"], 0)

    def test_zero_budget_and_join_separator_count(self):
        response = self.response([("a", "one", []), ("b", "two", [])])
        self.assertEqual(pack_whole_blocks(response, 0, self.CharacterCounter())["context"], "")
        packed = pack_whole_blocks(response, len("[a]\none") * 2, self.CharacterCounter())
        self.assertEqual(len(packed["results"]), 1)

    def test_public_score_has_no_query_or_evidence_text(self):
        fact = "A synthetic test sentence."
        response = self.response([("one", fact, [])])
        case = QueryCase("q", "Private dataset question?", "lookup", "p", (Evidence("s", 0, fact),))
        row = score_row(case, response, {}, {"fake": self.CharacterCounter()}, public=True)
        self.assertNotIn("query", row)
        self.assertNotIn(fact, str(row))
        self.assertNotIn(case.query, str(row))

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "optional benchmark tokenizer is not installed")
    def test_real_tokenizers_enforce_final_unicode_context_budget(self):
        import tiktoken
        entries = [
            ("oversized", "大型背景说明🧠 " * 200, [{"session_id": "large", "turn_index": 0, "turn_start": 0, "turn_end": 1400}]),
            ("second", "缓存有效期为45秒。 café e\u0301 🧠 <|endoftext|>", [{"session_id": "s", "turn_index": 1, "turn_start": 10, "turn_end": 55}]),
            ("third", "原始来源与标点必须保留：日本語、中文。", [{"session_id": "s", "turn_index": 2, "turn_start": 70, "turn_end": 91}]),
        ]
        response = self.response(entries)
        original = copy.deepcopy(response)
        expected = f"[second]\n{entries[1][1]}\n\n[third]\n{entries[2][1]}"
        for name in ("cl100k_base", "o200k_base"):
            with self.subTest(encoding=name):
                encoding = tiktoken.get_encoding(name)
                # Derive the boundary from the real assembled Unicode text;
                # there are no brittle expected-token-count constants.
                budget = len(encoding.encode(expected, disallowed_special=()))
                packed = pack_whole_blocks(response, budget, TokenCounter(name))
                self.assertEqual(packed["context"], expected)
                self.assertLessEqual(len(encoding.encode(packed["context"], disallowed_special=())), budget)
                self.assertEqual([item["source_refs"] for item in packed["results"]], [entries[1][2], entries[2][2]])
                narrower = pack_whole_blocks(response, budget - 1, TokenCounter(name))
                self.assertEqual([item["id"] for item in narrower["results"]], ["second"])
                self.assertLessEqual(len(encoding.encode(narrower["context"], disallowed_special=())), budget - 1)
                self.assertEqual(response, original)


class PublicDatasetTests(unittest.TestCase):
    def fixture(self):
        return [{"sample_id": "sample-one", "conversation": {
            "speaker_a": "A", "speaker_b": "B",
            "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_1": [
                {"speaker": "A", "dia_id": "D1:1", "text": "I chose a blue notebook."},
                {"speaker": "B", "dia_id": "D1:2", "text": "Here is a picture.", "img_url": "test://image"},
                {"speaker": "A", "dia_id": "D1:3", "text": "The notebook has 80 pages."}]},
            "qa": [
                {"question": "What color?", "answer": "blue", "evidence": ["D1:1"], "category": 4},
                {"question": "Describe the picture?", "answer": "irrelevant", "evidence": ["D1:2"], "category": 4},
                {"question": "Which missing reference?", "answer": "irrelevant", "evidence": ["D9:9"], "category": 1},
                {"question": "What cannot be known?", "adversarial_answer": "wrong", "evidence": [], "category": 5},
                {"question": "Color and pages?", "answer": "blue and 80", "evidence": ["D1:1", "D1:3"], "category": 1}]}]

    def test_text_evidence_mapping_and_exclusions(self):
        data = convert_locomo(self.fixture(), sample_ids=["sample-one"], split="development")
        self.assertEqual(len(data.queries), 3)
        self.assertEqual(data.provenance["excluded_qa"], {"image_bearing_evidence": 1, "invalid_evidence_id": 1})
        multiple = next(case for case in data.queries if case.category == "locomo_category_1")
        self.assertEqual([item.turn_index for item in multiple.required], [0, 2])
        self.assertEqual(multiple.required[0].session_id, "sample-one-session_1")
        self.assertEqual(data.sessions[0]["messages"][0]["content"], "A: I chose a blue notebook.")
        self.assertEqual(data.sessions[0]["created_at"], "2023-05-08T13:56:00+00:00")
        self.assertEqual(data.description()["kind"], "public")
        self.assertFalse(next(case for case in data.queries if case.category == "locomo_category_5").answerable)

    def test_bounded_selection_is_stable_and_ignores_question_phrasing(self):
        items = self.fixture()
        first = convert_locomo(items, sample_ids=["sample-one"], split="heldout", max_queries=2)
        for qa in items[0]["qa"]:
            qa["question"] = "Entirely different query text"
        second = convert_locomo(items, sample_ids=["sample-one"], split="heldout", max_queries=2)
        self.assertEqual([case.id for case in first.queries], [case.id for case in second.queries])
        self.assertNotEqual(first.fingerprint, second.fingerprint)


class SharedComponentTests(unittest.TestCase):
    def test_whole_source_page_requires_known_unique_identifiers(self):
        doc = {"id": "a", "title": "A", "text": "USER: synthetic evidence",
               "project": "p", "created_at": "2025-01-01T00:00:00Z",
               "source_refs": [{"project": "p", "session_id": "s", "turn_index": 0,
                                "turn_start": 0, "turn_end": 24}], "breadcrumb": []}
        response = shared_response(["a"], {"a": doc})
        self.assertEqual(response["results"][0]["text"], doc["text"])
        self.assertEqual(evidence_blocks(response)[0][1]["source_refs"], doc["source_refs"])
        with self.assertRaises(ValueError):
            shared_response(["missing"], {"a": doc})
        with self.assertRaises(ValueError):
            shared_response(["a", "a"], {"a": doc})

    def test_preflight_flags_cross_page_annotation_without_dropping_it(self):
        text = "A long annotation that continues across two pages."
        original = "USER: " + text
        middle = 27
        dataset = Dataset(seed=1, split="development",
                          sessions=[{"project": "p", "session_id": "s", "messages": [{"role": "user", "content": text}]}],
                          queries=[QueryCase("q", "Question?", "lookup", "p", (Evidence("s", 0, text),))])
        documents = [{"id": str(index), "project": "p", "text": original[start:end],
                      "source_refs": [{"session_id": "s", "turn_index": 0,
                                       "turn_start": start, "turn_end": end}]}
                     for index, (start, end) in enumerate(((0, middle), (middle, len(original))))]
        result = evidence_attainability(dataset, documents)
        self.assertEqual(result["evidence_labels_checked"], 1)
        self.assertEqual(result["unattainable_single_page_labels"][0]["query_id"], "q")
        documents.append({"id": "whole", "project": "p", "text": original,
                          "source_refs": [{"session_id": "s", "turn_index": 0,
                                           "turn_start": 0, "turn_end": len(original)}]})
        self.assertEqual(evidence_attainability(dataset, documents)["unattainable_single_page_labels"], [])


if __name__ == "__main__":
    unittest.main()
