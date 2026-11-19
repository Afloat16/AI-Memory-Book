"""Evaluator integrity only; these tests do not execute holdout retrieval."""
import copy
import unittest

from benchmarks.v014_public_holdout import dataset, source_chunks, verify_response


class PublicSourceHoldoutIntegrityTests(unittest.TestCase):
    def test_captured_sources_and_gold_are_byte_verified_and_disjoint(self):
        sessions, cases = dataset()
        self.assertEqual(len(sessions), 16)
        self.assertEqual(len(cases), 48)
        self.assertEqual(sum(c["category"] == "missing" for c in cases), 8)
        self.assertEqual(len({c["id"] for c in cases}), 48)
        self.assertGreater(9 * sum(len(s["messages"]) for s in sessions), 4096)
        self.assertTrue(all(c["required"] for c in cases if c["category"] != "missing"))

    def test_chunking_retains_unicode_whitespace_and_whole_lines(self):
        source = "# 参数\n\n" + "    keepalive_expiry = 5.0\n" * 60
        self.assertEqual("".join(source_chunks(source)), source)
        self.assertTrue(all(chunk.endswith("\n") for chunk in source_chunks(source)))

    def fixture(self):
        original = "USER: max_connections = 10"
        stamp = "2024-01-02T03:04:05+00:00"
        ref = {"project": "p", "session_id": "file", "turn_index": 0,
               "message_indices": [0], "created_at": stamp,
               "start": 0, "end": len(original), "turn_start": 0, "turn_end": len(original)}
        page = {"id": "page", "content": original, "source_refs": [ref], "offset": 0,
                "next_offset": None, "total_chars": len(original), "breadcrumb": [{"id": "p"}], "created_at": stamp}
        hit = {"id": "page", "text": original, "source_refs": [dict(ref)], "page_chars": len(original),
               "excerpt_spans": [[0, len(original)]], "breadcrumb": [{"id": "p"}], "created_at": stamp}
        context = "[page] p / file | " + stamp + "\n" + original
        case = {"query": "max_connections", "project": "p", "category": "current", "required": [{"session_id": "file", "quote": "max_connections = 10"}]}
        response = {"query": case["query"], "strategy": "book", "cache_hit": False, "budget_chars": 1200,
                    "temporal": {"requested": "auto"}, "results": [hit], "context": context, "context_chars": len(context)}
        return case, response, {"page": page}, {("p", "file", 0): {"text": original, "created_at": stamp}}

    def test_score_requires_answer_quote_in_verified_returned_source(self):
        case, response, pages, originals = self.fixture()
        self.assertTrue(verify_response(case, response, pages, originals, 1200)["complete"])
        case["required"][0]["quote"] = "max_connections = 100"
        self.assertFalse(verify_response(case, response, pages, originals, 1200)["complete"])

    def test_fabricated_source_scope_offset_timestamp_or_context_fails(self):
        for corruption in ("scope", "offset", "timestamp", "context", "text", "message"):
            with self.subTest(corruption=corruption):
                case, response, pages, originals = copy.deepcopy(self.fixture())
                if corruption == "scope":
                    response["results"][0]["source_refs"][0]["project"] = "other"
                elif corruption == "offset":
                    response["results"][0]["source_refs"][0]["turn_end"] += 1
                elif corruption == "timestamp":
                    pages["page"]["created_at"] = "2030-01-01T00:00:00Z"
                elif corruption == "text":
                    response["results"][0]["text"] += " fabricated"
                elif corruption == "message":
                    response["results"][0]["source_refs"][0]["message_indices"] = [1]
                else:
                    response["context"] += " fabricated"
                    response["context_chars"] = len(response["context"])
                with self.assertRaises(ValueError):
                    verify_response(case, response, pages, originals, 1200)

    def test_nonempty_missing_context_is_not_an_answer_or_absence_proof(self):
        case, response, pages, originals = self.fixture()
        case.update(required=[], category="missing")
        response["evidence_coverage"] = {"status": "insufficient_evidence", "missing_identifiers": ["unknown_field"]}
        score = verify_response(case, response, pages, originals, 1200)
        self.assertTrue(score["missing"])
        self.assertTrue(score["returned_context"])
        self.assertFalse(score["complete"])
        self.assertEqual(score["coverage_status"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
