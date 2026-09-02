from __future__ import annotations

import copy
import unittest

from hermes_factory.certification_authority import canonical_projection_sha256
from hermes_factory.model_registry import is_certified_for_source


SOURCE_SHA = "a" * 64
GOLD_SHA = "b" * 64
MANIFEST_SHA = "c" * 64
CANDIDATE_SHA = "d" * 64
PRIMARY_VERSION = "sha256:" + "1" * 64
PRIMARY_OTHER_VERSION = "sha256:" + "2" * 64
BLIND_VERSION = "sha256:" + "3" * 64
BENCH = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
BLIND_KEY = f"OLLAMA|blind|BLIND_RECALL|W2|S1|{BENCH}"
PRIMARY_KEY = f"OLLAMA|primary|PRIMARY|W2|S1|{BENCH}"


def _identity(model: str, family: str, group: str, version: str) -> dict:
    return {
        "provider": "OLLAMA",
        "model_alias": model,
        "underlying_family": family,
        "empirical_semantic_model": True,
        "independence_group": group,
        "observed_version_policy": "OLLAMA_DIGEST",
        "observed_version": version,
        "version_binding_certifiable": True,
    }


PRIMARY_IDENTITY = _identity("primary", "PRIMARY_FAMILY", "PRIMARY_GROUP", PRIMARY_VERSION)
BLIND_IDENTITY = _identity("blind", "BLIND_FAMILY", "BLIND_GROUP", BLIND_VERSION)


def _entry(scored: dict, primary_baseline: dict | None) -> dict:
    projection = {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": copy.deepcopy(scored),
        "primary_baseline_identity": copy.deepcopy(primary_baseline),
    }
    return {
        "status": "CERTIFIED_WITH_LIMITS",
        "benchmark_inputs_verified": True,
        "source_units_sha256": SOURCE_SHA,
        "units_in_scope": ["SU-1"],
        "scored_identity": copy.deepcopy(scored),
        "registry_authority_projection": projection,
        "registry_authority_sha256": canonical_projection_sha256(projection),
        "gold_reference_sha256": GOLD_SHA,
        "gold_manifest_sha256": MANIFEST_SHA,
        "candidate_file_sha256": CANDIDATE_SHA,
    }


def _registry() -> dict:
    return {
        "model_identities": {
            "OLLAMA|primary": {
                "underlying_family": "PRIMARY_FAMILY",
                "empirical_semantic_model": True,
                "independence_group": "PRIMARY_GROUP",
                "observed_version_policy": "OLLAMA_DIGEST",
            },
            "OLLAMA|primary-alt": {
                "underlying_family": "ALT_FAMILY",
                "empirical_semantic_model": True,
                "independence_group": "ALT_GROUP",
                "observed_version_policy": "OLLAMA_DIGEST",
            },
            "OLLAMA|blind": {
                "underlying_family": "BLIND_FAMILY",
                "empirical_semantic_model": True,
                "independence_group": "BLIND_GROUP",
                "observed_version_policy": "OLLAMA_DIGEST",
            },
        },
        "certifications": {
            BLIND_KEY: _entry(BLIND_IDENTITY, PRIMARY_IDENTITY),
            PRIMARY_KEY: _entry(PRIMARY_IDENTITY, None),
        },
        "retired_certification_keys": [],
    }


def _blind_check(registry: dict, *, primary_model: str = "primary", primary_version: str = PRIMARY_VERSION) -> bool:
    return is_certified_for_source(
        registry,
        BLIND_KEY,
        source_units_sha256=SOURCE_SHA,
        source_unit_id="SU-1",
        provider="OLLAMA",
        model_alias="blind",
        observed_version=BLIND_VERSION,
        primary_provider="OLLAMA",
        primary_model_alias=primary_model,
        primary_observed_version=primary_version,
    )


class BlindPairCertificationTests(unittest.TestCase):
    def test_exact_scored_primary_pair_passes(self):
        self.assertTrue(_blind_check(_registry()))

    def test_blind_certificate_cannot_move_to_different_primary_alias(self):
        self.assertFalse(_blind_check(_registry(), primary_model="primary-alt"))

    def test_blind_certificate_cannot_move_to_changed_primary_weights(self):
        self.assertFalse(_blind_check(_registry(), primary_version=PRIMARY_OTHER_VERSION))

    def test_missing_runtime_primary_pair_context_fails_closed(self):
        registry = _registry()
        self.assertFalse(is_certified_for_source(
            registry,
            BLIND_KEY,
            source_units_sha256=SOURCE_SHA,
            source_unit_id="SU-1",
            provider="OLLAMA",
            model_alias="blind",
            observed_version=BLIND_VERSION,
        ))

    def test_mutated_primary_registry_authority_invalidates_blind_pair(self):
        registry = _registry()
        registry["model_identities"]["OLLAMA|primary"]["independence_group"] = "CHANGED_GROUP"
        self.assertFalse(_blind_check(registry))

    def test_noncertifiable_primary_baseline_version_invalidates_blind_pair(self):
        registry = _registry()
        projection = registry["certifications"][BLIND_KEY]["registry_authority_projection"]
        projection["primary_baseline_identity"]["version_binding_certifiable"] = False
        registry["certifications"][BLIND_KEY]["registry_authority_sha256"] = canonical_projection_sha256(projection)
        self.assertFalse(_blind_check(registry))

    def test_primary_certificate_does_not_require_blind_pair_context(self):
        registry = _registry()
        self.assertTrue(is_certified_for_source(
            registry,
            PRIMARY_KEY,
            source_units_sha256=SOURCE_SHA,
            source_unit_id="SU-1",
            provider="OLLAMA",
            model_alias="primary",
            observed_version=PRIMARY_VERSION,
        ))


if __name__ == "__main__":
    unittest.main()
