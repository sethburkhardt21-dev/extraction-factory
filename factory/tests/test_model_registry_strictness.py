from __future__ import annotations

import unittest

from hermes_factory.model_registry import resolve_model_identity


class ModelRegistryStrictnessTests(unittest.TestCase):
    def _resolve(self, row):
        return resolve_model_identity({"model_identities": {"OLLAMA|m": row}}, "OLLAMA", "m")

    def test_complete_identity_resolves(self):
        resolved = self._resolve({
            "underlying_family": "FAMILY",
            "independence_group": "GROUP",
            "empirical_semantic_model": True,
            "observed_version_policy": "CLI_OBSERVED",
        })
        self.assertEqual(resolved["underlying_family"], "FAMILY")
        self.assertEqual(resolved["independence_group"], "GROUP")
        self.assertTrue(resolved["empirical_semantic_model"])

    def test_missing_empirical_status_does_not_default_true(self):
        with self.assertRaisesRegex(ValueError, "registered_model_missing_empirical_status"):
            self._resolve({"underlying_family": "FAMILY", "independence_group": "GROUP"})

    def test_non_boolean_empirical_status_is_rejected(self):
        for value in (1, 0, "true", "false", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "registered_model_empirical_status_not_boolean"):
                    self._resolve({
                        "underlying_family": "FAMILY",
                        "independence_group": "GROUP",
                        "empirical_semantic_model": value,
                    })

    def test_missing_independence_group_does_not_fallback_to_family(self):
        with self.assertRaisesRegex(ValueError, "registered_model_missing_independence_group"):
            self._resolve({"underlying_family": "FAMILY", "empirical_semantic_model": True})

    def test_blank_independence_group_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "registered_model_missing_independence_group"):
            self._resolve({
                "underlying_family": "FAMILY",
                "independence_group": "   ",
                "empirical_semantic_model": True,
            })

    def test_registry_identity_container_must_be_object(self):
        with self.assertRaisesRegex(ValueError, "registry_model_identities_not_object"):
            resolve_model_identity({"model_identities": []}, "OLLAMA", "m")

    def test_observed_version_policy_cannot_be_blank(self):
        with self.assertRaisesRegex(ValueError, "registered_model_observed_version_policy_invalid"):
            self._resolve({
                "underlying_family": "FAMILY",
                "independence_group": "GROUP",
                "empirical_semantic_model": True,
                "observed_version_policy": "",
            })


if __name__ == "__main__":
    unittest.main()
