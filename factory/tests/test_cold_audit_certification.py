from __future__ import annotations

import unittest

from benchmarks_ext.certify_cold_audit import build_challenges, build_entries, decide, score_results
from hermes_factory.hashing import sha256_text
from hermes_factory.model_registry import certification_key, is_certified_for_source
from hermes_factory.models import SourceUnit


DIGEST = "sha256:" + "a" * 64


def _unit(uid: str, content: str, representation: str = "TEXT") -> SourceUnit:
    return SourceUnit(uid, "S", "V", "source-sha", "PARAGRAPH", representation,
                      {"pdf_pages": [1]}, sha256_text(content), content)


class ColdAuditChallengeTests(unittest.TestCase):
    def test_builds_one_supported_and_one_known_unsupported_challenge_per_gold_row(self):
        unit = _unit("U1", "The pressure is 10 mmHg. This statement is source grounded.")
        gold = [{"source_unit_id": "U1", "proposition": "The pressure is 10 mmHg.", "evidence": "The pressure is 10 mmHg."}]
        rows = build_challenges(gold, {"U1": unit})
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["expected_supported"] for r in rows], [True, False])
        self.assertEqual(rows[1]["mutation"], "NUMERIC_VALUE_CHANGED")
        self.assertNotIn("10 mmHg", rows[1]["proposition"])
        self.assertEqual(rows[1]["evidence"], gold[0]["evidence"])

    def test_non_numeric_negative_is_explicit_unsupported_addition(self):
        unit = _unit("U1", "Volatile agents have characteristic properties.")
        gold = [{"source_unit_id": "U1", "proposition": "Volatile agents have characteristic properties.", "evidence": "Volatile agents have characteristic properties."}]
        rows = build_challenges(gold, {"U1": unit})
        self.assertEqual(rows[1]["mutation"], "UNSUPPORTED_UNIVERSAL_ADDITION")
        self.assertNotIn(rows[1]["proposition"], unit.content)

    def test_decision_is_strict_all_cases_correct(self):
        passing = [
            {"expected_supported": True, "actual_supported": True, "correct": True},
            {"expected_supported": False, "actual_supported": False, "correct": True},
        ]
        metrics = score_results(passing)
        self.assertEqual(decide(metrics, version_certifiable=True), ("CERTIFIED_WITH_LIMITS", []))
        status, failures = decide(metrics, version_certifiable=False)
        self.assertEqual(status, "BLOCKED_EXTERNAL")
        self.assertTrue(failures)
        failing = list(passing)
        failing[1] = {"expected_supported": False, "actual_supported": True, "correct": False}
        status, failures = decide(score_results(failing), version_certifiable=True)
        self.assertEqual(status, "REJECTED")
        self.assertTrue(failures)


class ColdAuditRuntimeCertificationTests(unittest.TestCase):
    def _registry_and_entry(self):
        identity = {
            "provider": "OLLAMA",
            "model_alias": "auditor:1",
            "underlying_family": "AUDITOR_FAMILY",
            "empirical_semantic_model": True,
            "independence_group": "AUDITOR_GROUP",
            "observed_version_policy": "OLLAMA_DIGEST",
        }
        entries = build_entries(
            registry={}, identity=identity, observed_version=DIGEST,
            metrics={"all_challenges_correct": True}, results_sha256="1" * 64,
            reference_sha256="2" * 64, gold_manifest_sha256="3" * 64,
            source_units_sha256="4" * 64, units_in_scope=["U1"], source_classes=["S1"],
            status="CERTIFIED_WITH_LIMITS", failures=[],
        )
        key = next(iter(entries))
        registry = {
            "model_identities": {
                "OLLAMA|auditor:1": {
                    "underlying_family": "AUDITOR_FAMILY",
                    "empirical_semantic_model": True,
                    "independence_group": "AUDITOR_GROUP",
                    "observed_version_policy": "OLLAMA_DIGEST",
                }
            },
            "certifications": entries,
            "retired_certification_keys": [],
        }
        return registry, key

    def test_cold_audit_key_is_architectural_w4_even_if_source_risk_is_w2(self):
        key = certification_key("OLLAMA", "auditor:1", "COLD_AUDIT", "W2", "S1", "B1")
        self.assertEqual(key.split("|")[3], "W4")

    def test_generated_certificate_is_runtime_source_and_version_bound(self):
        registry, key = self._registry_and_entry()
        self.assertTrue(is_certified_for_source(
            registry, key, source_units_sha256="4" * 64, source_unit_id="U1",
            provider="OLLAMA", model_alias="auditor:1", observed_version=DIGEST,
        ))
        self.assertFalse(is_certified_for_source(
            registry, key, source_units_sha256="4" * 64, source_unit_id="U1",
            provider="OLLAMA", model_alias="auditor:1", observed_version="sha256:" + "b" * 64,
        ))


if __name__ == "__main__":
    unittest.main()
