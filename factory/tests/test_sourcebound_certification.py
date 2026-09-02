from __future__ import annotations

import copy
import unittest

from hermes_factory.certification_authority import canonical_projection_sha256
from hermes_factory.model_registry import is_certified_for_source


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
VERSION = "sha256:" + "1" * 64
OTHER_VERSION = "sha256:" + "2" * 64
KEY = "OLLAMA|model|PRIMARY|W2|S1|BENCH"

IDENTITY = {
    "provider": "OLLAMA",
    "model_alias": "model",
    "underlying_family": "TEST_FAMILY",
    "empirical_semantic_model": True,
    "independence_group": "TEST_GROUP",
    "observed_version_policy": "OLLAMA_DIGEST",
    "observed_version": VERSION,
    "version_binding_certifiable": True,
}
REGISTRY_IDENTITY = {
    "underlying_family": "TEST_FAMILY",
    "empirical_semantic_model": True,
    "independence_group": "TEST_GROUP",
    "observed_version_policy": "OLLAMA_DIGEST",
}


def _projection(identity=None):
    return {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": copy.deepcopy(identity or IDENTITY),
        "primary_baseline_identity": None,
    }


def _registry(**overrides):
    projection = _projection()
    entry = {
        "status": "CERTIFIED_WITH_LIMITS",
        "benchmark_inputs_verified": True,
        "source_units_sha256": HASH_A,
        "units_in_scope": ["SU-1", "SU-2"],
        "scored_identity": copy.deepcopy(IDENTITY),
        "registry_authority_projection": projection,
        "registry_authority_sha256": canonical_projection_sha256(projection),
        "gold_reference_sha256": HASH_B,
        "gold_manifest_sha256": HASH_C,
        "candidate_file_sha256": HASH_D,
    }
    entry.update(overrides)
    return {
        "model_identities": {"OLLAMA|model": copy.deepcopy(REGISTRY_IDENTITY)},
        "certifications": {KEY: entry},
    }


class SourceBoundCertificationTests(unittest.TestCase):
    def _check(self, registry, observed_version: str = VERSION):
        return is_certified_for_source(
            registry, KEY,
            source_units_sha256=HASH_A,
            source_unit_id="SU-1",
            provider="OLLAMA",
            model_alias="model",
            observed_version=observed_version,
        )

    def test_exact_verified_source_scope_version_and_authority_pass(self):
        self.assertTrue(self._check(_registry()))

    def test_same_alias_new_model_digest_does_not_inherit_certification(self):
        self.assertFalse(self._check(_registry(), OTHER_VERSION))

    def test_missing_certified_model_version_fails(self):
        identity = copy.deepcopy(IDENTITY); identity.pop("observed_version")
        self.assertFalse(self._check(_registry(scored_identity=identity)))

    def test_placeholder_certified_model_version_fails(self):
        identity = copy.deepcopy(IDENTITY); identity["observed_version"] = "CLI_OBSERVED"
        self.assertFalse(self._check(_registry(scored_identity=identity)))

    def test_same_class_different_source_artifact_does_not_inherit_certification(self):
        self.assertFalse(is_certified_for_source(
            _registry(), KEY,
            source_units_sha256="e" * 64,
            source_unit_id="SU-1",
            provider="OLLAMA",
            model_alias="model",
            observed_version=VERSION,
        ))

    def test_unit_outside_certified_scope_fails(self):
        self.assertFalse(is_certified_for_source(
            _registry(), KEY,
            source_units_sha256=HASH_A,
            source_unit_id="SU-EXPANSION",
            provider="OLLAMA",
            model_alias="model",
            observed_version=VERSION,
        ))

    def test_unverified_benchmark_inputs_fail(self):
        self.assertFalse(self._check(_registry(benchmark_inputs_verified=False)))

    def test_scored_model_identity_mismatch_fails(self):
        identity = copy.deepcopy(IDENTITY); identity["model_alias"] = "other"
        self.assertFalse(self._check(_registry(scored_identity=identity)))

    def test_missing_evidence_chain_hash_fails(self):
        self.assertFalse(self._check(_registry(candidate_file_sha256=None)))

    def test_rejected_status_fails(self):
        self.assertFalse(self._check(_registry(status="REJECTED")))

    def test_missing_authority_projection_fails_closed(self):
        self.assertFalse(self._check(_registry(registry_authority_projection=None)))

    def test_tampered_authority_projection_hash_fails_closed(self):
        self.assertFalse(self._check(_registry(registry_authority_sha256="f" * 64)))

    def test_projection_identity_must_match_certificate_identity(self):
        projection = _projection(); projection["scored_identity"]["independence_group"] = "OTHER"
        self.assertFalse(self._check(_registry(
            registry_authority_projection=projection,
            registry_authority_sha256=canonical_projection_sha256(projection),
        )))

    def test_current_registry_identity_drift_invalidates_certificate(self):
        mutations = {
            "underlying_family": "OTHER_FAMILY",
            "empirical_semantic_model": False,
            "independence_group": "OTHER_GROUP",
            "observed_version_policy": "EXPLICIT_IMMUTABLE_VERSION",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                registry = _registry()
                registry["model_identities"]["OLLAMA|model"][field] = value
                self.assertFalse(self._check(registry))

    def test_unrelated_registry_certification_does_not_invalidate_certificate(self):
        registry = _registry()
        registry["certifications"]["OLLAMA|other|PRIMARY|W2|S1|BENCH"] = {"status": "REJECTED"}
        self.assertTrue(self._check(registry))

    def test_malformed_certifications_container_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "registry_certifications_not_object"):
            is_certified_for_source(
                {"certifications": []}, KEY,
                source_units_sha256=HASH_A,
                source_unit_id="SU-1",
                provider="OLLAMA",
                model_alias="model",
                observed_version=VERSION,
            )


if __name__ == "__main__":
    unittest.main()
