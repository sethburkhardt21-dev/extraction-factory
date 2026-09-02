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
                "benchmark_inputs_verified": True,
                "source_units_sha256": SOURCE_SHA,
                "units_in_scope": ["U1"],
                "scored_identity": scored,
                "registry_authority_projection": projection,
                "registry_authority_sha256": canonical_projection_sha256(projection),
                "gold_reference_sha256": GOLD_SHA,
                "gold_manifest_sha256": MANIFEST_SHA,
                "candidate_file_sha256": RESULTS_SHA,
            }
        },
    }


class ColdAuditRuntimeCertificationTests(unittest.TestCase):
    def test_w4_cold_certificate_is_valid_for_exact_source_and_model_version(self):
        registry = _registry()
        key = certification_key("OLLAMA", "cold-model", "COLD_AUDIT", "W4", "S1", BENCHMARK)
        self.assertTrue(is_certified_for_source(
            registry,
            key,
            source_units_sha256=SOURCE_SHA,
            source_unit_id="U1",
            provider="OLLAMA",
            model_alias="cold-model",
            observed_version=VERSION,
        ))

    def test_w2_lookup_cannot_substitute_for_w4_cold_certificate(self):
        registry = _registry()
        wrong_key = certification_key("OLLAMA", "cold-model", "COLD_AUDIT", "W2", "S1", BENCHMARK)
        self.assertFalse(is_certified_for_source(
            registry,
            wrong_key,
            source_units_sha256=SOURCE_SHA,
            source_unit_id="U1",
            provider="OLLAMA",
            model_alias="cold-model",
            observed_version=VERSION,
        ))

    def test_changed_digest_invalidates_w4_cold_certificate(self):
        registry = _registry()
        key = certification_key("OLLAMA", "cold-model", "COLD_AUDIT", "W4", "S1", BENCHMARK)
        self.assertFalse(is_certified_for_source(
            registry,
            key,
            source_units_sha256=SOURCE_SHA,
            source_unit_id="U1",
            provider="OLLAMA",
            model_alias="cold-model",
            observed_version="sha256:" + "f" * 64,
        ))


if __name__ == "__main__":
    unittest.main()
