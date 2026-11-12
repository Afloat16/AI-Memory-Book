"""Focused fake-record checks for the independent numeric audit."""
import copy
import unittest

from scripts import audit_round2_component_costs as audit


def example():
    bridges, reads = [1, 9, 100], [100, 9, 0]
    native_ids = [["p1", None], ["p2", "p3"], []]
    rows = []
    for i in range(3):
        mapped = [identity for identity in native_ids[i] if identity is not None]
        rows.append({"id": "fake-" + str(i), "repetition": 0, "status": "ok",
            "search_ms": bridges[i] / 2, "bridge_ms": bridges[i], "read_ms": reads[i],
            "read_calls": len(mapped), "native_hit_ids": native_ids[i], "hit_ids": mapped,
            "read_payload_sha256": ["fake-digest"] * len(mapped),
            "unmapped_native_hits": native_ids[i].count(None),
            "search_payload_tokens": {"cl100k_base": [10, 20, 0][i], "o200k_base": [8, 18, 0][i]},
            "search_content_tokens": {"cl100k_base": [7, 17, 0][i], "o200k_base": [6, 16, 0][i]},
            "read_payload_tokens": {"cl100k_base": [20, 40, 0][i], "o200k_base": [18, 38, 0][i]},
            "read_content_tokens": {"cl100k_base": [15, 35, 0][i], "o200k_base": [13, 33, 0][i]}})
    # A later repeated call is deliberately very different. It cannot alter
    # any first-pass cost, context or combined latency aggregate.
    repeated = copy.deepcopy(rows[0])
    repeated.update(repetition=1, bridge_ms=100000, read_ms=100000)
    report = {"stage": "ai-memory-hybrid", "timing_rows": [*rows, repeated],
        "native_costs": {"queries": 3, "unmapped_native_hits": 1, "queries_with_unmapped_native_hits": 1,
            "mean_read_calls": 1.0, "mean_read_ms": 109 / 3,
            "mean_search_payload_tokens": {"cl100k_base": 10.0, "o200k_base": 26 / 3},
            "mean_search_content_tokens": {"cl100k_base": 8.0, "o200k_base": 22 / 3},
            "mean_read_payload_tokens": {"cl100k_base": 20.0, "o200k_base": 56 / 3},
            "mean_read_content_tokens": {"cl100k_base": 50 / 3, "o200k_base": 46 / 3},
            "read_policy": "fake fixture policy", "native_metadata_policy": "fake fixture policy"},
        "first_pass_roundtrip_latency": {"samples": 3, "p50_ms": 9.0, "p95_ms": 90.89999999999999, "mean_ms": 110 / 3},
        "first_pass_search_plus_all_reads_latency": {
            "samples": 3, "p50_ms": 100.0, "p95_ms": 100.9, "mean_ms": 73.0},
        "configurations": []}
    for encoding in audit.ENCODINGS:
        for budget in (512, 1024, 2048):
            contexts = [{"id": row["id"], "context_tokens": {"cl100k_base": 11 + i, "o200k_base": 9 + i}}
                        for i, row in enumerate(rows)]
            report["configurations"].append({"tokenizer": encoding, "budget_tokens": budget,
                "query_results": contexts, "metrics": {"mean_context_tokens": {"cl100k_base": 12.0, "o200k_base": 10.0}}})
    return report


class IndependentComponentCostAuditTests(unittest.TestCase):
    def test_first_pass_means_and_per_query_latency_sums(self):
        result = audit.recompute(example())
        self.assertEqual(result["recomputed_native_costs"]["queries"], 3)
        self.assertEqual(result["recomputed_native_costs"]["mean_read_calls"], 1.0)
        combined = result["first_pass_search_plus_all_reads_latency"]
        self.assertEqual(combined["p95_ms"], 100.9)
        self.assertNotEqual(combined["p95_ms"], audit.percentile([1, 9, 100], .95)
                            + audit.percentile([100, 9, 0], .95))
        self.assertEqual(len(result["common_packed_context"]), 6)
        self.assertNotIn("fake-0", str(result))

    def test_missing_content_remains_none_without_zero_imputation(self):
        report = example()
        report["timing_rows"][0]["search_content_tokens"] = None
        report["native_costs"]["mean_search_content_tokens"] = None
        result = audit.recompute(report)
        self.assertIsNone(result["recomputed_native_costs"]["mean_search_content_tokens"])
        self.assertIsNone(result["additional_per_query_sum_means"]["search_plus_read_content_tokens"])
        self.assertEqual(result["native_content_availability"]["search_content_tokens"], {"available": 2, "missing": 1})

    def test_native_without_reads_retains_zero_and_unavailable_text(self):
        report = example()
        report["stage"] = "baseline-component"
        for row in report["timing_rows"]:
            row["native_hit_ids"] = row["hit_ids"]
            row.update(read_calls=0, read_ms=0, read_payload_sha256=[], unmapped_native_hits=0,
                       search_content_tokens=None)
            row["read_payload_tokens"] = row["read_content_tokens"] = {e: 0 for e in audit.ENCODINGS}
        costs = report["native_costs"]
        costs.update(mean_read_calls=0.0, mean_read_ms=0.0, unmapped_native_hits=0,
                     queries_with_unmapped_native_hits=0, mean_search_content_tokens=None,
                     mean_read_payload_tokens={e: 0.0 for e in audit.ENCODINGS},
                     mean_read_content_tokens={e: 0.0 for e in audit.ENCODINGS})
        report["first_pass_search_plus_all_reads_latency"] = copy.deepcopy(report["first_pass_roundtrip_latency"])
        result = audit.recompute(report)
        self.assertEqual(result["recomputed_native_costs"]["mean_read_ms"], 0.0)
        self.assertIsNone(result["recomputed_native_costs"]["mean_search_content_tokens"])

    def test_incorrect_published_cost_metadata_or_summed_percentiles_fail(self):
        for mutation in ("mean", "metadata", "percentile", "read_count", "context", "axis"):
            report = example()
            if mutation == "mean":
                report["native_costs"]["mean_search_payload_tokens"]["cl100k_base"] += 1
            elif mutation == "metadata":
                report["timing_rows"][0]["unmapped_native_hits"] = 0
            elif mutation == "percentile":
                report["first_pass_search_plus_all_reads_latency"]["p95_ms"] = 181.8
            elif mutation == "read_count":
                report["timing_rows"][0]["read_calls"] = 0
            elif mutation == "context":
                report["configurations"][0]["metrics"]["mean_context_tokens"]["cl100k_base"] = 0
            else:
                report["configurations"].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit.recompute(report)


if __name__ == "__main__":
    unittest.main()
