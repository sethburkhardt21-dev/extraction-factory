from __future__ import annotations

import unittest

from hermes_factory.model_registry import is_certified_for_source


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
KEY = "OLLAMA|model|PRIMARY|W2|S1|BENCH"


def _registry(**overrides):
    entry = {
        "status": "CERTIFIED_WITH_LIMITS",
        "benchmark_inputs_verified": True,
        "source_units_sha256": HASH_A,
        "units_in_scope": ["SU-1", "SU-2"],
        "scored_identity": {"provider": "OLLAMA", "model_alias": "model"},
        "gold_reference_sha256": HASH_B,
        "gold_manifest_sha256": HASH_C,
        "candidate_file_sha256": HASH_D,
    }
    entry.update(overrides)
    return {"certifications": {KEY: entry}}


class SourceBoundCertificationTests(unittest.TestCase):
    def _check(self, registry):
        return is_certified_for_source(
            registry, KEY,
            source_units_sha256=HASH_A,
            source_unit_id="SU-1",
            provider="OLLAMA",
            model_alias="model",
        )

    def test_exact_verified_source_scope_passes(self):
        self.assertTrue(self._check(_registry()))

    def test_same_class_different_source_artifact_does_not_inherit_certification(self):
        self.assertFalse(is_certified_for_source(
            _registry(), KEY,
            source_units_sha256="e" * 64,
            source_unit_id="SU-1",
            provider="OLLAMA",
            model_alias="model",
        ))

    def test_unit_outside_certified_scope_fails(self):
        self.assertFalse(is_certified_for_source(
            _registry(), KEY,
            source_units_sha256=HASH_A,
            source_unit_id="SU-EXPANSION",
            provider="OLLAMA",
            model_alias="model",
        ))

    def test_unverified_benchmark_inputs_fail(self):
        self.assertFalse(self._check(_registry(benchmark_inputs_verified=False)))

    def test_scored_model_identity_mismatch_fails(self):
        self.assertFalse(self._check(_registry(
            scored_identity={"provider": "OLLAMA", "model_alias": "other"}
        )))

    def test_missing_evidence_chain_hash_fails(self):
        self.assertFalse(self._check(_registry(candidate_file_sha256=None)))

    def test_rejected_status_fails(self):
        self.assertFalse(self._check(_registry(status="REJECTED")))

    def test_malformed_certifications_container_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "registry_certifications_not_object"):
            is_certified_for_source(
                {"certifications": []}, KEY,
                source_units_sha256=HASH_A,
                source_unit_id="SU-1",
                provider="OLLAMA",
                model_alias="model",
            )


if __name__ == "__main__":
    unittest.main()
