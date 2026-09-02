from __future__ import annotations

import argparse
import copy
import unittest
from unittest.mock import patch

from benchmarks_ext.certify_cold_audit import (
    _build_provider,
    build_challenges,
    build_entries,
    challenge_semantic_sha256,
    decide,
    score_results,
)
from hermes_factory.hashing import sha256_text
from hermes_factory.model_registry import certification_key, is_certified_for_source
from hermes_factory.models import SourceUnit


DIGEST = "sha256:" + "a" * 64


def _unit(uid: str, content: str, representation: str = "TEXT") -> SourceUnit:
    return SourceUnit(uid, "S", "V", "source-sha", "PARAGRAPH", representation,
                      {"pdf_pages": [1]}, sha256_text(content), content)


def _ollama_identity():
    return {
        "provider": "OLLAMA",
        "model_alias": "auditor:1",
        "underlying_family": "AUDITOR_FAMILY",
        "empirical_semantic_model": True,
        "independence_group": "AUDITOR_GROUP",
        "observed_version_policy": "OLLAMA_DIGEST",
    }


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

    def test_decision_is_strict_all_cases_correct_and_provider_verified(self):
        passing = [
            {"expected_supported": True, "actual_supported": True, "correct": True},
            {"expected_supported": False, "actual_supported": False, "correct": True},
        ]
        metrics = score_results(passing)
        self.assertEqual(
            decide(metrics, version_certifiable=True, version_authority_verified=True),
            ("CERTIFIED_WITH_LIMITS", []),
        )
        status, failures = decide(metrics, version_certifiable=False, version_authority_verified=True)
        self.assertEqual(status, "BLOCKED_EXTERNAL")
        self.assertTrue(failures)
        status, failures = decide(metrics, version_certifiable=True, version_authority_verified=False)
        self.assertEqual(status, "BLOCKED_EXTERNAL")
        self.assertTrue(failures)
        failing = list(passing)
        failing[1] = {"expected_supported": False, "actual_supported": True, "correct": False}
        status, failures = decide(score_results(failing), version_certifiable=True, version_authority_verified=True)
        self.assertEqual(status, "REJECTED")
        self.assertTrue(failures)

    def test_semantic_freshness_ignores_rationale_receipt_and_request_noise(self):
        unit = _unit("U1", "The pressure is 10 mmHg.")
        challenges = build_challenges(
            [{"source_unit_id": "U1", "proposition": "The pressure is 10 mmHg.", "evidence": "The pressure is 10 mmHg."}],
            {"U1": unit},
        )
        results = [
            {"challenge_id": challenges[0]["challenge_id"], "source_unit_id": "U1", "mutation": challenges[0]["mutation"],
             "expected_supported": True, "actual_supported": True, "correct": True,
             "request_sha256": "1" * 64, "verdict": {"supported": True, "rationale": "first wording"},
             "provider_receipt": {"duration_seconds": 1.0}},
            {"challenge_id": challenges[1]["challenge_id"], "source_unit_id": "U1", "mutation": challenges[1]["mutation"],
             "expected_supported": False, "actual_supported": False, "correct": True,
             "request_sha256": "2" * 64, "verdict": {"supported": False, "rationale": "caught mutation"},
             "provider_receipt": {"duration_seconds": 2.0}},
        ]
        changed_noise = copy.deepcopy(results)
        changed_noise[0]["request_sha256"] = "9" * 64
        changed_noise[0]["verdict"]["rationale"] = "completely different wording"
        changed_noise[0]["provider_receipt"]["duration_seconds"] = 99.0
        self.assertEqual(
            challenge_semantic_sha256(challenges, results),
            challenge_semantic_sha256(challenges, changed_noise),
        )
        changed_decision = copy.deepcopy(results)
        changed_decision[1]["actual_supported"] = True
        changed_decision[1]["correct"] = False
        self.assertNotEqual(
            challenge_semantic_sha256(challenges, results),
            challenge_semantic_sha256(challenges, changed_decision),
        )


class ColdAuditProviderAuthorityTests(unittest.TestCase):
    def test_ollama_provider_uses_measured_digest_and_guarded_command(self):
        args = argparse.Namespace(
            provider_command=None,
            ollama_host="http://127.0.0.1:11434",
            timeout=30,
            observed_version=None,
            model="auditor:1",
            ollama_keep_alive="30m",
            ollama_think=None,
        )
        with patch("benchmarks_ext.certify_cold_audit.resolve_digest", return_value=DIGEST):
            provider, observed, verified = _build_provider(args, _ollama_identity())
        self.assertEqual(observed, DIGEST)
        self.assertTrue(verified)
        self.assertEqual(provider.identity().observed_version, DIGEST)
        joined = " ".join(provider.command)
        self.assertIn("ollama_digest_guard.py", joined)
        self.assertIn(DIGEST, joined)
        self.assertIn("http://127.0.0.1:11434", joined)

    def test_ollama_operator_version_is_assertion_only_and_mismatch_fails(self):
        args = argparse.Namespace(
            provider_command=None,
            ollama_host="http://127.0.0.1:11434",
            timeout=30,
            observed_version="sha256:" + "b" * 64,
            model="auditor:1",
            ollama_keep_alive="30m",
            ollama_think=None,
        )
        with patch("benchmarks_ext.certify_cold_audit.resolve_digest", return_value=DIGEST):
            with self.assertRaisesRegex(ValueError, "assertion_mismatch"):
                _build_provider(args, _ollama_identity())

    def test_non_ollama_generic_command_remains_descriptive_not_certifiable(self):
        identity = dict(_ollama_identity())
        identity.update({
            "provider": "HOSTED",
            "model_alias": "hosted-model",
            "observed_version_policy": "EXPLICIT_IMMUTABLE_VERSION",
        })
        args = argparse.Namespace(
            provider_command=["python", "fake.py"],
            ollama_host="http://127.0.0.1:11434",
            timeout=30,
            observed_version="provider-version-1",
            model="hosted-model",
            ollama_keep_alive="30m",
            ollama_think=None,
        )
        provider, observed, verified = _build_provider(args, identity)
        self.assertEqual(observed, "provider-version-1")
        self.assertFalse(verified)
        self.assertEqual(provider.identity().observed_version, observed)


class ColdAuditRuntimeCertificationTests(unittest.TestCase):
    def _registry_and_entry(self):
        identity = _ollama_identity()
        entries = build_entries(
            registry={}, identity=identity, observed_version=DIGEST,
            metrics={"all_challenges_correct": True}, results_sha256="1" * 64,
            semantic_sha256="5" * 64,
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

    def test_certificate_carries_semantic_fingerprint_for_lifecycle_freshness(self):
        registry, key = self._registry_and_entry()
        self.assertEqual(registry["certifications"][key]["candidate_semantic_sha256"], "5" * 64)


if __name__ == "__main__":
    unittest.main()
