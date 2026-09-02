from __future__ import annotations

import copy
import unittest

from benchmarks_ext.manage_certification_lifecycle import propose_transition
from hermes_factory.certification_authority import canonical_projection_sha256
from hermes_factory.certification_state import (
    MATCH_FALLBACK,
    MATCH_FULL,
    aggregate_role_status,
    certification_evidence_sha256,
    recertification_block_reason,
)

BENCH = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
PRIMARY_KEY = f"OLLAMA|primary|PRIMARY|W2|S1|{BENCH}"
BLIND_KEY = f"OLLAMA|blind|BLIND_RECALL|W2|S1|{BENCH}"
VERSION = "sha256:" + "1" * 64


def _identity(model: str, group: str) -> dict:
    return {
        "provider": "OLLAMA",
        "model_alias": model,
        "underlying_family": group,
        "empirical_semantic_model": True,
        "independence_group": group,
        "observed_version_policy": "OLLAMA_DIGEST",
        "observed_version": VERSION,
        "version_binding_certifiable": True,
    }


def _entry(*, model: str = "primary", role: str = "PRIMARY", candidate: str = "d",
           primary_candidate: str | None = None, status: str = "CERTIFIED_WITH_LIMITS") -> dict:
    identity = _identity(model, model.upper())
    projection = {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": copy.deepcopy(identity),
        "primary_baseline_identity": _identity("primary", "PRIMARY") if role == "BLIND_RECALL" else None,
    }
    row = {
        "status": status,
        "benchmark_inputs_verified": True,
        "source_units_sha256": "a" * 64,
        "units_in_scope": ["SU-1", "SU-2"],
        "scored_identity": identity,
        "registry_authority_projection": projection,
        "registry_authority_sha256": canonical_projection_sha256(projection),
        "gold_reference_sha256": "b" * 64,
        "gold_manifest_sha256": "c" * 64,
        "candidate_file_sha256": candidate * 64,
        "primary_candidate_file_sha256": primary_candidate * 64 if primary_candidate else None,
    }
    return row


def _registry() -> dict:
    return {
        "certifications": {PRIMARY_KEY: _entry()},
        "role_status": {"PRIMARY_W2": "CERTIFIED_WITH_LIMITS"},
        "certification_lifecycle_events": [],
        "invalidated_certification_evidence": [],
        "retired_certification_keys": [],
    }


class EvidenceFingerprintTests(unittest.TestCase):
    def test_lifecycle_records_invalidated_evidence(self):
        registry = _registry()
        original_sha = certification_evidence_sha256(PRIMARY_KEY, registry["certifications"][PRIMARY_KEY])
        proposed, event = propose_transition(
            registry=registry,
            key=PRIMARY_KEY,
            target_status="SUSPENDED",
            reason="semantic regression",
            expected_status="CERTIFIED_WITH_LIMITS",
            now_epoch=10.0,
        )
        self.assertEqual(event["invalidated_evidence_sha256"], original_sha)
        self.assertEqual(event["invalidated_evidence_match_mode"], MATCH_FULL)
        self.assertEqual(proposed["invalidated_certification_evidence"][0]["evidence_sha256"], original_sha)
        self.assertEqual(proposed["invalidated_certification_evidence"][0]["match_mode"], MATCH_FULL)
        self.assertEqual(proposed["invalidated_certification_evidence"][0]["lifecycle_event_id"], event["event_id"])

    def test_exact_stale_evidence_cannot_restore_authority(self):
        proposed, _ = propose_transition(
            registry=_registry(),
            key=PRIMARY_KEY,
            target_status="SUSPENDED",
            reason="semantic regression",
            expected_status="CERTIFIED_WITH_LIMITS",
        )
        stale = _entry(status="CERTIFIED_WITH_LIMITS")
        reason = recertification_block_reason(proposed, PRIMARY_KEY, stale)
        self.assertIsNotNone(reason)
        self.assertIn("certification_evidence_previously_invalidated", reason)
        self.assertIn("mode=FULL_FINGERPRINT", reason)

    def test_new_candidate_evidence_can_reactivate_nonretired_role(self):
        proposed, _ = propose_transition(
            registry=_registry(),
            key=PRIMARY_KEY,
            target_status="SUSPENDED",
            reason="semantic regression",
            expected_status="CERTIFIED_WITH_LIMITS",
        )
        fresh = _entry(candidate="e", status="CERTIFIED_WITH_LIMITS")
        self.assertIsNone(recertification_block_reason(proposed, PRIMARY_KEY, fresh))

    def test_retired_key_blocks_even_fresh_evidence(self):
        proposed, _ = propose_transition(
            registry=_registry(),
            key=PRIMARY_KEY,
            target_status="RETIRED",
            reason="provider retired",
            expected_status="CERTIFIED_WITH_LIMITS",
        )
        fresh = _entry(candidate="e", status="CERTIFIED_WITH_LIMITS")
        self.assertEqual(
            recertification_block_reason(proposed, PRIMARY_KEY, fresh),
            "retired_certification_key_is_terminal",
        )

    def test_blind_fingerprint_binds_primary_baseline_candidate_file(self):
        first = _entry(model="blind", role="BLIND_RECALL", candidate="e", primary_candidate="d")
        second = _entry(model="blind", role="BLIND_RECALL", candidate="e", primary_candidate="f")
        self.assertNotEqual(
            certification_evidence_sha256(BLIND_KEY, first),
            certification_evidence_sha256(BLIND_KEY, second),
        )

    def test_legacy_blind_without_primary_baseline_uses_fallback_and_is_still_blocked(self):
        legacy = _entry(model="blind", role="BLIND_RECALL", candidate="e", primary_candidate="d")
        legacy.pop("primary_candidate_file_sha256")
        registry = {
            "certifications": {BLIND_KEY: legacy},
            "role_status": {"BLIND_RECALL_W2": "CERTIFIED_WITH_LIMITS"},
            "certification_lifecycle_events": [],
            "invalidated_certification_evidence": [],
            "retired_certification_keys": [],
        }
        suspended, event = propose_transition(
            registry=registry,
            key=BLIND_KEY,
            target_status="SUSPENDED",
            reason="legacy blind regression",
            expected_status="CERTIFIED_WITH_LIMITS",
        )
        self.assertEqual(event["invalidated_evidence_match_mode"], MATCH_FALLBACK)
        self.assertEqual(suspended["invalidated_certification_evidence"][0]["match_mode"], MATCH_FALLBACK)

        modern_same_scored_output = _entry(
            model="blind", role="BLIND_RECALL", candidate="e", primary_candidate="f",
            status="CERTIFIED_WITH_LIMITS",
        )
        reason = recertification_block_reason(suspended, BLIND_KEY, modern_same_scored_output)
        self.assertIsNotNone(reason)
        self.assertIn("mode=CANDIDATE_FILE_FALLBACK", reason)

        fresh_scored_output = _entry(
            model="blind", role="BLIND_RECALL", candidate="f", primary_candidate="f",
            status="CERTIFIED_WITH_LIMITS",
        )
        self.assertIsNone(recertification_block_reason(suspended, BLIND_KEY, fresh_scored_output))

    def test_invalidated_evidence_deduplicates_across_downward_transitions(self):
        suspended, _ = propose_transition(
            registry=_registry(), key=PRIMARY_KEY, target_status="SUSPENDED",
            reason="first action", expected_status="CERTIFIED_WITH_LIMITS",
        )
        demoted, event = propose_transition(
            registry=suspended, key=PRIMARY_KEY, target_status="DEMOTED",
            reason="confirmed regression", expected_status="SUSPENDED",
        )
        self.assertEqual(len(demoted["invalidated_certification_evidence"]), 1)
        self.assertIsNotNone(event["invalidated_evidence_sha256"])
        self.assertEqual(event["invalidated_evidence_match_mode"], MATCH_FULL)


class AggregateRoleStatusTests(unittest.TestCase):
    def test_other_active_certificate_keeps_role_aggregate_certified(self):
        certifications = {
            PRIMARY_KEY: _entry(status="SUSPENDED"),
            f"OLLAMA|other|PRIMARY|W2|S1|{BENCH}": _entry(model="other", status="CERTIFIED"),
        }
        self.assertEqual(
            aggregate_role_status(certifications, role="PRIMARY", work_class="W2", benchmark_version=BENCH),
            "CERTIFIED",
        )


if __name__ == "__main__":
    unittest.main()
