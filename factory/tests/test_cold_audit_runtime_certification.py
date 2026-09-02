from __future__ import annotations

import copy
import unittest

from hermes_factory.certification_authority import canonical_projection_sha256
from hermes_factory.model_registry import certification_key, is_certified_for_source


VERSION = "sha256:" + "a" * 64
SOURCE_SHA = "b" * 64
GOLD_SHA = "c" * 64
MANIFEST_SHA = "d" * 64
RESULTS_SHA = "e" * 64
BENCHMARK = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
DIM_SCHEMA = "hermes-cold-audit-dimensions-1.0"


def _coverage() -> dict:
    required = ["NEGATION", "SUPPORTED", "UNSUPPORTED_ADDITION"]
    return {
        "required_dimensions": required,
        "covered_dimensions": required,
        "missing_required_dimensions": [],
        "all_required_dimensions_covered": True,
        "per_dimension": {
            dim: {"challenge_count": 2, "correct_count": 2, "accuracy": 1.0}
            for dim in required
        },
    }


def _registry() -> dict:
    scored = {
        "provider": "OLLAMA",
        "model_alias": "cold-model",
        "underlying_family": "COLD_FAMILY",
        "empirical_semantic_model": True,
        "independence_group": "COLD_GROUP",
        "observed_version_policy": "OLLAMA_DIGEST",
        "observed_version": VERSION,
        "version_binding_certifiable": True,
    }
    projection = {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": scored,
        "primary_baseline_identity": None,
    }
    coverage = _coverage()
    key = certification_key("OLLAMA", "cold-model", "COLD_AUDIT", "W4", "S1", BENCHMARK)
    return {
        "benchmark_version": BENCHMARK,
        "model_identities": {
            "OLLAMA|cold-model": {
                "underlying_family": "COLD_FAMILY",
                "empirical_semantic_model": True,
                "independence_group": "COLD_GROUP",
                "observed_version_policy": "OLLAMA_DIGEST",
            }
        },
        "certifications": {
            key: {
                "status": "CERTIFIED_WITH_LIMITS",
                "decision_rule": "CERT-COLD-AUDIT-W4-STRICT-CHALLENGE",
                "benchmark_inputs_verified": True,
                "source_units_sha256": SOURCE_SHA,
                "units_in_scope": ["U1"],
                "scored_identity": scored,
                "registry_authority_projection": projection,
                "registry_authority_sha256": canonical_projection_sha256(projection),
                "gold_reference_sha256": GOLD_SHA,
                "gold_manifest_sha256": MANIFEST_SHA,
                "candidate_file_sha256": RESULTS_SHA,
                "cold_audit_dimension_schema": DIM_SCHEMA,
                "cold_audit_dimension_coverage": coverage,
                "cold_audit_dimension_coverage_sha256": canonical_projection_sha256(coverage),
                "cold_audit_all_required_dimensions_covered": True,
                "cold_audit_all_required_dimensions_perfect": True,
            }
        },
    }


def _check(registry: dict, *, version: str = VERSION, key: str | None = None) -> bool:
    key = key or certification_key("OLLAMA", "cold-model", "COLD_AUDIT", "W4", "S1", BENCHMARK)
    return is_certified_for_source(
        registry,
        key,
        source_units_sha256=SOURCE_SHA,
        source_unit_id="U1",
        provider="OLLAMA",
        model_alias="cold-model",
        observed_version=version,
    )


class ColdAuditRuntimeCertificationTests(unittest.TestCase):
    def test_cold_audit_key_is_architectural_w4_even_if_caller_supplies_w2(self):
        key = certification_key("OLLAMA", "cold-model", "COLD_AUDIT", "W2", "S1", BENCHMARK)
        self.assertEqual(key.split("|")[3], "W4")

    def test_dimension_complete_w4_cold_certificate_is_valid(self):
        self.assertTrue(_check(_registry()))

    def test_literal_legacy_w2_key_cannot_substitute_for_w4(self):
        registry = _registry()
        wrong_key = f"OLLAMA|cold-model|COLD_AUDIT|W2|S1|{BENCHMARK}"
        self.assertFalse(_check(registry, key=wrong_key))

    def test_changed_digest_invalidates_w4_cold_certificate(self):
        self.assertFalse(_check(_registry(), version="sha256:" + "f" * 64))

    def test_legacy_single_dimension_cold_certificate_is_non_authoritative(self):
        registry = _registry()
        entry = next(iter(registry["certifications"].values()))
        for key in [
            "cold_audit_dimension_schema",
            "cold_audit_dimension_coverage",
            "cold_audit_dimension_coverage_sha256",
            "cold_audit_all_required_dimensions_covered",
            "cold_audit_all_required_dimensions_perfect",
        ]:
            entry.pop(key, None)
        self.assertFalse(_check(registry))

    def test_dimension_coverage_tamper_invalidates_certificate(self):
        registry = _registry()
        entry = next(iter(registry["certifications"].values()))
        entry["cold_audit_dimension_coverage"]["per_dimension"]["NEGATION"]["accuracy"] = 0.5
        self.assertFalse(_check(registry))

    def test_rehashed_imperfect_dimension_still_invalidates_certificate(self):
        registry = _registry()
        entry = next(iter(registry["certifications"].values()))
        coverage = entry["cold_audit_dimension_coverage"]
        coverage["per_dimension"]["NEGATION"]["accuracy"] = 0.5
        entry["cold_audit_dimension_coverage_sha256"] = canonical_projection_sha256(coverage)
        self.assertFalse(_check(registry))


if __name__ == "__main__":
    unittest.main()
