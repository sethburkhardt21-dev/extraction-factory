from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmarks_ext.certify_cold_audit import build_entry, decide, risk_scopes
from benchmarks_ext.cold_audit_score import (
    CASE_SCHEMA,
    VERDICT_SCHEMA,
    build_cases,
    cold_case_semantic_sha256,
    mutation_options,
    score_verdicts,
)
from hermes_factory.models import SourceUnit
from benchmarks_ext.score_role import sha256_text


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


class ColdAuditRiskScopeTests(unittest.TestCase):
    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    def test_risk_scopes_partition_certificates_without_broadening_units(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_sha = "a" * 64
            text = "Routine statement 25 mmHg."
            table = "Row A | Value 25 mmHg"
            units = [
                SourceUnit(
                    source_unit_id="U-TEXT", source_id="S", source_version_id="SV", source_sha256=source_sha,
                    unit_type="PARAGRAPH", content_representation="TEXT", locator={"pdf_pages": [1]},
                    content_sha256=sha256_text(text), content=text,
                ),
                SourceUnit(
                    source_unit_id="U-TABLE", source_id="S", source_version_id="SV", source_sha256=source_sha,
                    unit_type="TABLE", content_representation="TABLE", locator={"pdf_pages": [2]},
                    content_sha256=sha256_text(table), content=table,
                ),
            ]
            source = root / "source_units.jsonl"
            self._write_jsonl(source, [u.to_dict() for u in units])
            raw = source.read_text(encoding="utf-8")
            manifest = {
                "source_pdf_sha256": source_sha,
                "source_units_sha256": sha256_text(raw),
                "source_unit_content_sha256": {u.source_unit_id: u.content_sha256 for u in units},
            }
            manifest_path = root / "GOLD_MANIFEST.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            scopes = risk_scopes(source, manifest_path)
            self.assertEqual(scopes[("W2", "S1")], ["U-TEXT"])
            self.assertEqual(scopes[("W3", "S3")], ["U-TABLE"])
            self.assertEqual(sorted(uid for rows in scopes.values() for uid in rows), ["U-TABLE", "U-TEXT"])

    def test_build_entry_uses_exact_risk_stratum_unit_scope(self):
        score = {
            "metrics": self.perfect_metrics(),
            "reference_sha256": "a" * 64,
            "gold_manifest_sha256": "b" * 64,
            "source_units_sha256": "c" * 64,
            "cold_benchmark_cases_sha256": "d" * 64,
            "cold_benchmark_verdicts_sha256": "e" * 64,
            "candidate_semantic_sha256": "f" * 64,
            "gold_label": "MECHANICALLY_CHECKED",
            "scored_identity": {
                "provider": "OLLAMA", "model_alias": "audit", "underlying_family": "DEEPSEEK",
                "empirical_semantic_model": True, "independence_group": "DEEPSEEK",
                "observed_version_policy": "OLLAMA_DIGEST", "observed_version": "sha256:" + "1" * 64,
                "version_binding_certifiable": True,
            },
            "primary_baseline_identity": None,
        }
        verification = {"recomputation_verified": True}
        entry = build_entry(score, "CERTIFIED_WITH_LIMITS", [], verification, units_in_scope=["U-TABLE"])
        self.assertEqual(entry["units_in_scope"], ["U-TABLE"])
        self.assertEqual(entry["candidate_file_sha256"], "d" * 64)
        self.assertTrue(entry["benchmark_inputs_verified"])

    @staticmethod
    def perfect_metrics() -> dict:
        return ColdAuditDecisionTests.perfect_metrics()


if __name__ == "__main__":
    unittest.main()
