from __future__ import annotations

import copy
import unittest

from benchmarks_ext.manage_certification_lifecycle import propose_transition
from hermes_factory.candidate_semantics import candidate_semantic_sha256
from hermes_factory.certification_authority import canonical_projection_sha256
from hermes_factory.certification_state import (
    MATCH_SEMANTIC,
    recertification_block_reason,
    semantic_evidence_sha256,
)

BENCH = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
PRIMARY_KEY = f"OLLAMA|model|PRIMARY|W2|S1|{BENCH}"
BLIND_KEY = f"OLLAMA|blind|BLIND_RECALL|W2|S1|{BENCH}"
VERSION_A = "sha256:" + "1" * 64
VERSION_B = "sha256:" + "2" * 64


def _candidate(*, cid: str = "C1", run_id: str = "RUN-A", proposition: str = "Agent is 1%.",
               evidence: str = "Agent is 1%.", version: str = VERSION_A, unit: str = "U1",
               metadata_value: str = "x") -> dict:
    return {
        "candidate_id": cid,
        "source_unit_id": unit,
        "source_sha256": "a" * 64,
        "evidence": evidence,
        "evidence_sha256": "ignored-by-semantic-projection",
        "proposition": proposition,
        "originating_run_id": run_id,
        "originating_capsule_id": "CAP-A",
        "parent_artifact_sha256": "p" * 64,
        "metadata": {"controller_only": metadata_value},
        "subject": "unused structured subject",
        "worker_identity": {
            "provider": "OLLAMA",
            "model_alias": "model",
            "underlying_family": "LOCAL",
            "observed_version": version,
        },
    }


def _identity(model: str = "model", version: str = VERSION_A) -> dict:
    return {
        "provider": "OLLAMA",
        "model_alias": model,
        "underlying_family": model.upper(),
        "empirical_semantic_model": True,
        "independence_group": model.upper(),
        "observed_version_policy": "OLLAMA_DIGEST",
        "observed_version": version,
        "version_binding_certifiable": True,
    }


def _entry(*, key_role: str = "PRIMARY", candidate_semantic: str = "d",
           primary_semantic: str | None = None, candidate_file: str = "e",
           primary_file: str | None = None, status: str = "CERTIFIED_WITH_LIMITS") -> dict:
    model = "blind" if key_role == "BLIND_RECALL" else "model"
    identity = _identity(model)
    projection = {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": copy.deepcopy(identity),
        "primary_baseline_identity": _identity("model") if key_role == "BLIND_RECALL" else None,
    }
    return {
        "status": status,
        "benchmark_inputs_verified": True,
        "source_units_sha256": "a" * 64,
        "units_in_scope": ["U1"],
        "scored_identity": identity,
        "registry_authority_projection": projection,
        "registry_authority_sha256": canonical_projection_sha256(projection),
        "gold_reference_sha256": "b" * 64,
        "gold_manifest_sha256": "c" * 64,
        "candidate_file_sha256": candidate_file * 64,
        "primary_candidate_file_sha256": primary_file * 64 if primary_file else None,
        "candidate_semantic_sha256": candidate_semantic * 64,
        "primary_candidate_semantic_sha256": primary_semantic * 64 if primary_semantic else None,
    }


class CandidateSemanticDigestTests(unittest.TestCase):
    def test_metadata_ids_lineage_and_order_do_not_manufacture_freshness(self):
        first = _candidate(cid="C1", run_id="RUN-A", metadata_value="one")
        second = _candidate(cid="C2", run_id="RUN-B", metadata_value="two")
        other = _candidate(cid="C3", proposition="Second fact.", evidence="Second fact.")
        h1 = candidate_semantic_sha256([first, other], units_in_scope=["U1"])
        h2 = candidate_semantic_sha256([copy.deepcopy(other), second], units_in_scope=["U1"])
        self.assertEqual(h1, h2)

    def test_proposition_change_is_new_semantic_evidence(self):
        first = _candidate(proposition="Agent is 1%.")
        second = _candidate(proposition="Agent is approximately 1%.")
        self.assertNotEqual(
            candidate_semantic_sha256([first], units_in_scope=["U1"]),
            candidate_semantic_sha256([second], units_in_scope=["U1"]),
        )

    def test_evidence_change_is_new_semantic_evidence(self):
        first = _candidate(evidence="Agent is 1%.")
        second = _candidate(evidence="Agent is exactly 1%.")
        self.assertNotEqual(
            candidate_semantic_sha256([first], units_in_scope=["U1"]),
            candidate_semantic_sha256([second], units_in_scope=["U1"]),
        )

    def test_observed_model_version_change_is_new_semantic_identity(self):
        first = _candidate(version=VERSION_A)
        second = _candidate(version=VERSION_B)
        self.assertNotEqual(
            candidate_semantic_sha256([first], units_in_scope=["U1"]),
            candidate_semantic_sha256([second], units_in_scope=["U1"]),
        )

    def test_out_of_scope_metadata_or_semantics_do_not_change_certified_scope_digest(self):
        base = _candidate(unit="U1")
        outside_a = _candidate(unit="U2", proposition="Outside A", evidence="Outside A")
        outside_b = _candidate(unit="U2", proposition="Outside B", evidence="Outside B")
        self.assertEqual(
            candidate_semantic_sha256([base, outside_a], units_in_scope=["U1"]),
            candidate_semantic_sha256([base, outside_b], units_in_scope=["U1"]),
        )


class SemanticLifecycleFreshnessTests(unittest.TestCase):
    def test_lifecycle_prefers_semantic_fingerprint(self):
        entry = _entry()
        registry = {
            "certifications": {PRIMARY_KEY: entry},
            "role_status": {"PRIMARY_W2": "CERTIFIED_WITH_LIMITS"},
            "certification_lifecycle_events": [],
            "invalidated_certification_evidence": [],
            "retired_certification_keys": [],
        }
        proposed, event = propose_transition(
            registry=registry, key=PRIMARY_KEY, target_status="SUSPENDED",
            reason="semantic regression", expected_status="CERTIFIED_WITH_LIMITS",
        )
        self.assertEqual(event["invalidated_evidence_match_mode"], MATCH_SEMANTIC)
        self.assertEqual(
            event["invalidated_evidence_sha256"],
            semantic_evidence_sha256(PRIMARY_KEY, entry),
        )
        self.assertEqual(proposed["invalidated_certification_evidence"][0]["match_mode"], MATCH_SEMANTIC)

    def test_metadata_only_file_hash_change_cannot_reactivate_same_semantics(self):
        entry = _entry(candidate_semantic="d", candidate_file="e")
        registry = {
            "certifications": {PRIMARY_KEY: entry},
            "role_status": {"PRIMARY_W2": "CERTIFIED_WITH_LIMITS"},
            "certification_lifecycle_events": [],
            "invalidated_certification_evidence": [],
            "retired_certification_keys": [],
        }
        suspended, _ = propose_transition(
            registry=registry, key=PRIMARY_KEY, target_status="SUSPENDED",
            reason="semantic regression", expected_status="CERTIFIED_WITH_LIMITS",
        )
        metadata_only_rewrite = _entry(candidate_semantic="d", candidate_file="f")
        reason = recertification_block_reason(suspended, PRIMARY_KEY, metadata_only_rewrite)
        self.assertIsNotNone(reason)
        self.assertIn("mode=SEMANTIC_FINGERPRINT", reason)

    def test_changed_semantic_digest_can_reactivate_nonretired_role(self):
        entry = _entry(candidate_semantic="d", candidate_file="e")
        registry = {
            "certifications": {PRIMARY_KEY: entry},
            "role_status": {"PRIMARY_W2": "CERTIFIED_WITH_LIMITS"},
            "certification_lifecycle_events": [],
            "invalidated_certification_evidence": [],
            "retired_certification_keys": [],
        }
        suspended, _ = propose_transition(
            registry=registry, key=PRIMARY_KEY, target_status="SUSPENDED",
            reason="semantic regression", expected_status="CERTIFIED_WITH_LIMITS",
        )
        changed = _entry(candidate_semantic="f", candidate_file="f")
        self.assertIsNone(recertification_block_reason(suspended, PRIMARY_KEY, changed))

    def test_blind_semantic_fingerprint_binds_primary_semantic_baseline(self):
        first = _entry(
            key_role="BLIND_RECALL", candidate_semantic="d", primary_semantic="e",
            candidate_file="f", primary_file="a",
        )
        second = _entry(
            key_role="BLIND_RECALL", candidate_semantic="d", primary_semantic="f",
            candidate_file="f", primary_file="b",
        )
        self.assertNotEqual(
            semantic_evidence_sha256(BLIND_KEY, first),
            semantic_evidence_sha256(BLIND_KEY, second),
        )


if __name__ == "__main__":
    unittest.main()
