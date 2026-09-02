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
    validate_gold_construction_disjointness,
)
from benchmarks_ext.cold_audit_challenge_dimensions import (
    DIM_NEGATION,
    DIM_NUMERIC,
    DIM_QUALIFIER,
    DIM_RELATIONSHIP_DIRECTION,
    DIM_SUPPORTED,
    DIM_UNSUPPORTED_ADDITION,
    applicable_dimensions,
    coverage_summary,
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


def _passing_results(challenges: list[dict]) -> list[dict]:
    return [
        {
            "challenge_id": c["challenge_id"],
            "source_unit_id": c["source_unit_id"],
            "mutation": c["mutation"],
            "dimension": c.get("dimension"),
            "expected_supported": c["expected_supported"],
            "actual_supported": c["expected_supported"],
            "correct": True,
            "request_sha256": "1" * 64,
            "verdict": {"supported": c["expected_supported"], "rationale": "bounded test"},
            "provider_receipt": {"duration_seconds": 1.0},
        }
        for c in challenges
    ]


def _coverage_metrics(challenges: list[dict], gold: list[dict], results: list[dict] | None = None) -> dict:
    rows = results or _passing_results(challenges)
    coverage = coverage_summary(challenges, rows, applicable_dimensions(gold))
    return score_results(rows, coverage)


class ColdAuditChallengeTests(unittest.TestCase):
    def test_numeric_row_exercises_support_atomicity_negation_and_numeric(self):
        unit = _unit("U1", "The pressure is 10 mmHg. This statement is source grounded.")
        gold = [{"source_unit_id": "U1", "proposition": "The pressure is 10 mmHg.", "evidence": "The pressure is 10 mmHg."}]
        rows = build_challenges(gold, {"U1": unit})
        dims = {r["dimension"] for r in rows}
        self.assertTrue({DIM_SUPPORTED, DIM_UNSUPPORTED_ADDITION, DIM_NEGATION, DIM_NUMERIC}.issubset(dims))
        numeric = next(r for r in rows if r["dimension"] == DIM_NUMERIC)
        self.assertEqual(numeric["mutation"], "NUMERIC_VALUE_CHANGED")
        self.assertEqual(numeric["evidence"], gold[0]["evidence"])
        self.assertNotIn(numeric["proposition"], unit.content)

    def test_non_numeric_row_still_exercises_atomicity_and_negation(self):
        unit = _unit("U1", "Volatile agents have characteristic properties.")
        gold = [{"source_unit_id": "U1", "proposition": "Volatile agents have characteristic properties.", "evidence": "Volatile agents have characteristic properties."}]
        rows = build_challenges(gold, {"U1": unit})
        dims = {r["dimension"] for r in rows}
        self.assertTrue({DIM_SUPPORTED, DIM_UNSUPPORTED_ADDITION, DIM_NEGATION}.issubset(dims))
        unsupported = next(r for r in rows if r["dimension"] == DIM_UNSUPPORTED_ADDITION)
        self.assertEqual(unsupported["mutation"], "UNSUPPORTED_UNIVERSAL_ADDITION")
        self.assertNotIn(unsupported["proposition"], unit.content)

    def test_qualifier_and_relationship_dimensions_are_generated_when_applicable(self):
        unit = _unit("U1", "Pressure may increase during the maneuver.")
        gold = [{"source_unit_id": "U1", "proposition": "Pressure may increase during the maneuver.", "evidence": "Pressure may increase during the maneuver."}]
        rows = build_challenges(gold, {"U1": unit})
        dims = {r["dimension"] for r in rows}
        self.assertIn(DIM_QUALIFIER, dims)
        self.assertIn(DIM_RELATIONSHIP_DIRECTION, dims)
        self.assertIn(DIM_QUALIFIER, applicable_dimensions(gold))
        self.assertIn(DIM_RELATIONSHIP_DIRECTION, applicable_dimensions(gold))

    def test_missing_applicable_dimension_blocks_certification(self):
        gold = [{"source_unit_id": "U1", "proposition": "Pressure may increase.", "evidence": "Pressure may increase."}]
        challenges = [
            {"challenge_id": "p", "source_unit_id": "U1", "dimension": DIM_SUPPORTED, "expected_supported": True},
            {"challenge_id": "n", "source_unit_id": "U1", "dimension": DIM_UNSUPPORTED_ADDITION, "expected_supported": False},
            {"challenge_id": "g", "source_unit_id": "U1", "dimension": DIM_NEGATION, "expected_supported": False},
        ]
        results = _passing_results(challenges)
        coverage = coverage_summary(challenges, results, applicable_dimensions(gold))
        metrics = score_results(results, coverage)
        status, failures = decide(metrics, version_certifiable=True, version_authority_verified=True)
        self.assertEqual(status, "REJECTED")
        self.assertTrue(any("required_dimension_coverage_incomplete" in x for x in failures))

    def test_one_error_in_one_dimension_blocks_certification(self):
        unit = _unit("U1", "Pressure may increase to 10 mmHg.")
        gold = [{"source_unit_id": "U1", "proposition": "Pressure may increase to 10 mmHg.", "evidence": "Pressure may increase to 10 mmHg."}]
        challenges = build_challenges(gold, {"U1": unit})
        results = _passing_results(challenges)
        target = next(r for r in results if r["dimension"] == DIM_RELATIONSHIP_DIRECTION)
        target["actual_supported"] = True
        target["correct"] = False
        metrics = _coverage_metrics(challenges, gold, results)
        status, failures = decide(metrics, version_certifiable=True, version_authority_verified=True)
        self.assertEqual(status, "REJECTED")
        self.assertTrue(any("RELATIONSHIP_DIRECTION" in x for x in failures))

    def test_semantic_freshness_ignores_rationale_receipt_and_request_noise(self):
        unit = _unit("U1", "The pressure is 10 mmHg.")
        gold = [{"source_unit_id": "U1", "proposition": "The pressure is 10 mmHg.", "evidence": "The pressure is 10 mmHg."}]
        challenges = build_challenges(gold, {"U1": unit})
        results = _passing_results(challenges)
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


class ColdAuditGoldIndependenceTests(unittest.TestCase):
    def test_auditor_must_be_disjoint_from_all_gold_construction_groups(self):
        manifest = {"gold_construction_independence_groups": ["GOLD_A", "GOLD_B", "GOLD_C"]}
        identity = _ollama_identity()
        self.assertEqual(validate_gold_construction_disjointness(manifest, identity), ["GOLD_A", "GOLD_B", "GOLD_C"])
        contaminated = dict(identity); contaminated["independence_group"] = "GOLD_B"
        with self.assertRaisesRegex(ValueError, "gold_construction_contamination"):
            validate_gold_construction_disjointness(manifest, contaminated)

    def test_missing_or_non_distinct_gold_lineage_fails_closed(self):
        identity = _ollama_identity()
        with self.assertRaisesRegex(ValueError, "missing_or_incomplete"):
            validate_gold_construction_disjointness({}, identity)
        with self.assertRaisesRegex(ValueError, "not_distinct"):
            validate_gold_construction_disjointness({"gold_construction_independence_groups": ["A", "A", "B"]}, identity)


class ColdAuditProviderAuthorityTests(unittest.TestCase):
    def test_ollama_provider_uses_measured_digest_and_guarded_command(self):
        args = argparse.Namespace(provider_command=None, ollama_host="http://127.0.0.1:11434", timeout=30,
                                  observed_version=None, model="auditor:1", ollama_keep_alive="30m", ollama_think=None)
        with patch("benchmarks_ext.cold_audit_certifier.resolve_digest", return_value=DIGEST):
            provider, observed, verified = _build_provider(args, _ollama_identity())
        self.assertEqual(observed, DIGEST); self.assertTrue(verified)
        self.assertEqual(provider.identity().observed_version, DIGEST)
        joined = " ".join(provider.command)
        self.assertIn("ollama_digest_guard.py", joined); self.assertIn(DIGEST, joined)

    def test_ollama_operator_version_assertion_mismatch_fails(self):
        args = argparse.Namespace(provider_command=None, ollama_host="http://127.0.0.1:11434", timeout=30,
                                  observed_version="sha256:" + "b" * 64, model="auditor:1", ollama_keep_alive="30m", ollama_think=None)
        with patch("benchmarks_ext.cold_audit_certifier.resolve_digest", return_value=DIGEST):
            with self.assertRaisesRegex(ValueError, "assertion_mismatch"):
                _build_provider(args, _ollama_identity())

    def test_non_ollama_generic_command_remains_descriptive_not_certifiable(self):
        identity = dict(_ollama_identity())
        identity.update({"provider": "HOSTED", "model_alias": "hosted-model", "observed_version_policy": "EXPLICIT_IMMUTABLE_VERSION"})
        args = argparse.Namespace(provider_command=["python", "fake.py"], ollama_host="http://127.0.0.1:11434", timeout=30,
                                  observed_version="provider-version-1", model="hosted-model", ollama_keep_alive="30m", ollama_think=None)
        provider, observed, verified = _build_provider(args, identity)
        self.assertEqual(observed, "provider-version-1"); self.assertFalse(verified)
        self.assertEqual(provider.identity().observed_version, observed)


class ColdAuditRuntimeCertificationTests(unittest.TestCase):
    def _registry_and_entry(self):
        identity = _ollama_identity()
        coverage = {
            "required_dimensions": [DIM_SUPPORTED, DIM_UNSUPPORTED_ADDITION, DIM_NEGATION],
            "covered_dimensions": [DIM_SUPPORTED, DIM_UNSUPPORTED_ADDITION, DIM_NEGATION],
            "missing_required_dimensions": [],
            "all_required_dimensions_covered": True,
            "per_dimension": {
                DIM_SUPPORTED: {"challenge_count": 1, "correct_count": 1, "accuracy": 1.0},
                DIM_UNSUPPORTED_ADDITION: {"challenge_count": 1, "correct_count": 1, "accuracy": 1.0},
                DIM_NEGATION: {"challenge_count": 1, "correct_count": 1, "accuracy": 1.0},
            },
        }
        entries = build_entries(
            registry={}, identity=identity, observed_version=DIGEST,
            metrics={"all_challenges_correct": True, "dimension_coverage": coverage}, results_sha256="1" * 64,
            semantic_sha256="5" * 64, reference_sha256="2" * 64, gold_manifest_sha256="3" * 64,
            source_units_sha256="4" * 64, units_in_scope=["U1"], source_classes=["S1"],
            status="CERTIFIED_WITH_LIMITS", failures=[],
        )
        key = next(iter(entries))
        registry = {
            "model_identities": {"OLLAMA|auditor:1": {"underlying_family": "AUDITOR_FAMILY", "empirical_semantic_model": True,
                                                        "independence_group": "AUDITOR_GROUP", "observed_version_policy": "OLLAMA_DIGEST"}},
            "certifications": entries,
            "retired_certification_keys": [],
        }
        return registry, key

    def test_cold_audit_key_is_architectural_w4_even_if_source_risk_is_w2(self):
        key = certification_key("OLLAMA", "auditor:1", "COLD_AUDIT", "W2", "S1", "B1")
        self.assertEqual(key.split("|")[3], "W4")

    def test_generated_certificate_is_runtime_source_version_and_coverage_bound(self):
        registry, key = self._registry_and_entry()
        self.assertTrue(is_certified_for_source(registry, key, source_units_sha256="4" * 64, source_unit_id="U1",
                                                provider="OLLAMA", model_alias="auditor:1", observed_version=DIGEST))
        self.assertFalse(is_certified_for_source(registry, key, source_units_sha256="4" * 64, source_unit_id="U1",
                                                 provider="OLLAMA", model_alias="auditor:1", observed_version="sha256:" + "b" * 64))
        stale = copy.deepcopy(registry)
        del stale["certifications"][key]["cold_audit_dimension_coverage"]
        self.assertFalse(is_certified_for_source(stale, key, source_units_sha256="4" * 64, source_unit_id="U1",
                                                 provider="OLLAMA", model_alias="auditor:1", observed_version=DIGEST))

    def test_tampered_dimension_coverage_invalidates_runtime_authority(self):
        registry, key = self._registry_and_entry()
        tampered = copy.deepcopy(registry)
        tampered["certifications"][key]["cold_audit_dimension_coverage"]["per_dimension"][DIM_NEGATION]["accuracy"] = 0.0
        self.assertFalse(is_certified_for_source(tampered, key, source_units_sha256="4" * 64, source_unit_id="U1",
                                                 provider="OLLAMA", model_alias="auditor:1", observed_version=DIGEST))

    def test_certificate_carries_semantic_fingerprint_for_lifecycle_freshness(self):
        registry, key = self._registry_and_entry()
        self.assertEqual(registry["certifications"][key]["candidate_semantic_sha256"], "5" * 64)


if __name__ == "__main__":
    unittest.main()
