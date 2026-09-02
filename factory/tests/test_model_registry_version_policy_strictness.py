from __future__ import annotations

import unittest

from hermes_factory.model_registry import resolve_model_identity


class ModelRegistryVersionPolicyStrictnessTests(unittest.TestCase):
    def test_missing_observed_version_policy_fails_closed(self):
        registry = {"model_identities": {"OLLAMA|m": {
            "underlying_family": "FAMILY",
            "independence_group": "GROUP",
            "empirical_semantic_model": True,
        }}}
        with self.assertRaisesRegex(ValueError, "registered_model_missing_observed_version_policy"):
            resolve_model_identity(registry, "OLLAMA", "m")


if __name__ == "__main__":
    unittest.main()
