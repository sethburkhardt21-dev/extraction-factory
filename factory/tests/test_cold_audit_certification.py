from __future__ import annotations

import unittest

from benchmarks_ext.certify_cold_audit import decide
from benchmarks_ext.cold_audit_score import (
    CASE_SCHEMA,
    VERDICT_SCHEMA,
    build_cases,
    cold_case_semantic_sha256,
    mutation_options,
    score_verdicts,
)


class ColdCaseConstructionTests(unittest.TestCase):
    @staticmethod
    def gold() -> list[dict]:
        rows = []
        propositions = [
            "Agent A may increase pressure to 25 mmHg.",
            "Agent B decreases flow by 2 percent.",
        ]
        for idx, prop in enumerate(propositions, 1):
            rows.append({
                "gold_id": f"G{idx}",
                "source_unit_id": f"U{idx}",
                "proposition": prop,
                "evidence": prop,
            })
        return rows

    def test_mutation_options_cover_high_value_error_classes(self):
        kinds = {kind for kind, _ in mutation_options("Agent may increase pressure to 25 mmHg.")}
        self.assertIn("NUMERIC_VALUE_CHANGED", kinds)
        self.assertIn("RELATIONSHIP_REVERSED", kinds)
        self.assertIn("QUALIFIER_DROPPED", kinds)
        self.assertIn("NEGATION_INJECTED", kinds)
        self.assertIn("UNSUPPORTED_ADDITION", kinds)

    def test_case_builder_covers_every_source_with_positive_and_negative(self):
        cases = build_cases(self.gold(), max_positive=2, max_negative=6)
        pos = {x["source_unit_id"] for x in cases if x["expected_supported"]}
        neg = {x["source_unit_id"] for x in cases if not x["expected_supported"]}
        self.assertEqual(pos, {"U1", "U2"})
        self.assertEqual(neg, {"U1", "U2"})
        self.assertEqual(len({x["case_id"] for x in cases}), len(cases))
        self.assertTrue(all(x["case_schema_version"] == CASE_SCHEMA for x in cases))

    def test_case_semantic_digest_ignores_row_order(self):
        cases = build_cases(self.gold(), max_positive=2, max_negative=4)
        self.assertEqual(cold_case_semantic_sha256(cases), cold_case_semantic_sha256(list(reversed(cases))))


class ColdAuditMetricTests(unittest.TestCase):
    @staticmethod
    def cases() -> list[dict]:
        return [
            {"case_id": "P", "source_unit_id": "U1", "expected_supported": True, "mutation_type": "SOURCE_FIRST_GOLD_SUPPORTED"},
            {"case_id": "N1", "source_unit_id": "U1", "expected_supported": False, "mutation_type": "NUMERIC_VALUE_CHANGED"},
            {"case_id": "N2", "source_unit_id": "U1", "expected_supported": False, "mutation_type": "RELATIONSHIP_REVERSED"},
            {"case_id": "N3", "source_unit_id": "U1", "expected_supported": False, "mutation_type": "QUALIFIER_DROPPED"},
        ]

    def test_perfect_verdicts_score_perfectly(self):
        verdicts = []
        for case in self.cases():
            verdicts.append({
                "verdict_schema_version": VERDICT_SCHEMA,
                "case_id": case["case_id"],
                "expected_supported": case["expected_supported"],
                "observed_supported": case["expected_supported"],
            })
        metrics = score_verdicts(self.cases(), verdicts)
        self.assertEqual(metrics["supported_case_recall"]["value"], 1.0)
        self.assertEqual(metrics["unsupported_case_rejection"]["value"], 1.0)
        self.assertEqual(metrics["provider_error_rate"]["value"], 0.0)

    def test_provider_error_counts_as_failure(self):
        verdicts = []
        for case in self.cases():
            row = {
                "verdict_schema_version": VERDICT_SCHEMA,
                "case_id": case["case_id"],
                "expected_supported": case["expected_supported"],
                "observed_supported": case["expected_supported"],
            }
            verdicts.append(row)
        verdicts[0].pop("observed_supported")
        verdicts[0]["error"] = "provider_failed"
        metrics = score_verdicts(self.cases(), verdicts)
        self.assertGreater(metrics["provider_error_rate"]["value"], 0.0)
        self.assertLess(metrics["supported_case_recall"]["value"], 1.0)


class ColdAuditDecisionTests(unittest.TestCase):
    @staticmethod
    def perfect_metrics() -> dict:
        return {
            "case_counts": {"supported": 8, "unsupported": 8, "total": 16},
            "supported_case_recall": {"value": 1.0},
            "unsupported_case_rejection": {"value": 1.0},
            "overall_accuracy": {"value": 1.0},
            "provider_error_rate": {"value": 0.0},
            "mutation_rejection": {
                "NUMERIC_VALUE_CHANGED": {"numerator": 3, "denominator": 3, "value": 1.0},
                "RELATIONSHIP_REVERSED": {"numerator": 3, "denominator": 3, "value": 1.0},
                "QUALIFIER_DROPPED": {"numerator": 2, "denominator": 2, "value": 1.0},
            },
        }

    def test_thresholds_make_cold_gate_reachable(self):
        status, failures = decide(self.perfect_metrics(), [f"U{i}" for i in range(8)])
        self.assertEqual(status, "CERTIFIED_WITH_LIMITS")
        self.assertEqual(failures, [])

    def test_detection_regression_is_rejected(self):
        metrics = self.perfect_metrics()
        metrics["unsupported_case_rejection"] = {"value": 0.80}
        status, failures = decide(metrics, [f"U{i}" for i in range(8)])
        self.assertEqual(status, "REJECTED")
        self.assertTrue(any("unsupported_rejection" in x for x in failures))


if __name__ == "__main__":
    unittest.main()
