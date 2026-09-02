from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks_ext.manage_certification_lifecycle import main as lifecycle_main, propose_transition
from hermes_factory.certification_lifecycle import apply_downward_transition, validate_transition
from hermes_factory.model_registry import ALLOWED, CERTIFIED_STATUSES, is_certified, is_certified_for_source
from hermes_factory.certification_authority import canonical_projection_sha256

KEY = "OLLAMA|model|PRIMARY|W2|S1|BENCH"
VERSION = "sha256:" + "1" * 64
SOURCE_SHA = "a" * 64

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


def _entry(status: str = "CERTIFIED_WITH_LIMITS") -> dict:
    projection = {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": copy.deepcopy(IDENTITY),
        "primary_baseline_identity": None,
    }
    return {
        "status": status,
        "benchmark_inputs_verified": True,
        "source_units_sha256": SOURCE_SHA,
        "units_in_scope": ["SU-1"],
        "scored_identity": copy.deepcopy(IDENTITY),
        "registry_authority_projection": projection,
        "registry_authority_sha256": canonical_projection_sha256(projection),
        "gold_reference_sha256": "b" * 64,
        "gold_manifest_sha256": "c" * 64,
        "candidate_file_sha256": "d" * 64,
    }


def _registry(status: str = "CERTIFIED_WITH_LIMITS") -> dict:
    return {
        "model_identities": {"OLLAMA|model": copy.deepcopy(REGISTRY_IDENTITY)},
        "certifications": {KEY: _entry(status)},
        "role_status": {"PRIMARY_W2": status},
        "certification_lifecycle_events": [],
        "retired_certification_keys": [],
    }


def _runtime_check(registry: dict) -> bool:
    return is_certified_for_source(
        registry,
        KEY,
        source_units_sha256=SOURCE_SHA,
        source_unit_id="SU-1",
        provider="OLLAMA",
        model_alias="model",
        observed_version=VERSION,
    )


class LifecycleStateTests(unittest.TestCase):
    def test_architecture_lifecycle_states_are_representable(self):
        for state in ("PROVISIONAL", "SUSPENDED", "DEMOTED", "RETIRED"):
            self.assertIn(state, ALLOWED)

    def test_only_certified_states_confer_authority(self):
        self.assertEqual(CERTIFIED_STATUSES, {"CERTIFIED", "CERTIFIED_WITH_LIMITS"})
        for state in ("PROVISIONAL", "SUSPENDED", "DEMOTED", "EXPIRED", "RETIRED"):
            registry = _registry(state)
            self.assertFalse(is_certified(registry, KEY), state)
            self.assertFalse(_runtime_check(registry), state)

    def test_downward_transition_records_reason_and_history(self):
        updated, event = apply_downward_transition(
            _entry(), certification_key=KEY, target_status="SUSPENDED",
            reason="unexpected E4 canary failure", incident_ref="INC-42", now_epoch=100.0,
        )
        self.assertEqual(updated["status"], "SUSPENDED")
        self.assertEqual(event["from_status"], "CERTIFIED_WITH_LIMITS")
        self.assertEqual(event["to_status"], "SUSPENDED")
        self.assertEqual(event["incident_ref"], "INC-42")
        self.assertEqual(updated["lifecycle_history"][-1]["event_id"], event["event_id"])

    def test_promotions_are_not_available_through_lifecycle_policy(self):
        with self.assertRaisesRegex(ValueError, "lifecycle_target_not_downward"):
            validate_transition("SUSPENDED", "CERTIFIED_WITH_LIMITS")

    def test_retired_is_terminal(self):
        with self.assertRaisesRegex(ValueError, "lifecycle_transition_not_allowed"):
            validate_transition("RETIRED", "SUSPENDED")

    def test_reason_is_mandatory(self):
        with self.assertRaisesRegex(ValueError, "lifecycle_reason_required"):
            apply_downward_transition(
                _entry(), certification_key=KEY, target_status="SUSPENDED", reason=""
            )


class GovernedLifecycleMutationTests(unittest.TestCase):
    def test_proposal_appends_top_level_audit_event(self):
        proposed, event = propose_transition(
            registry=_registry(), key=KEY, target_status="SUSPENDED",
            reason="regression sample below threshold", expected_status="CERTIFIED_WITH_LIMITS", now_epoch=10.0,
        )
        self.assertEqual(proposed["certifications"][KEY]["status"], "SUSPENDED")
        self.assertEqual(proposed["certification_lifecycle_events"][-1]["event_id"], event["event_id"])
        self.assertEqual(proposed["role_status"]["PRIMARY_W2"], "SUSPENDED")
        self.assertFalse(event["runtime_authority_after_transition"])

    def test_compare_and_set_rejects_stale_operator_state(self):
        with self.assertRaisesRegex(ValueError, "lifecycle_compare_and_set_failed"):
            propose_transition(
                registry=_registry(), key=KEY, target_status="SUSPENDED",
                reason="stale command", expected_status="CERTIFIED",
            )

    def test_retirement_creates_terminal_tombstone(self):
        proposed, _ = propose_transition(
            registry=_registry(), key=KEY, target_status="RETIRED",
            reason="model/provider permanently retired", expected_status="CERTIFIED_WITH_LIMITS",
        )
        self.assertIn(KEY, proposed["retired_certification_keys"])
        self.assertFalse(_runtime_check(proposed))

        # Even a later accidental entry overwrite cannot resurrect runtime authority.
        proposed["certifications"][KEY] = _entry("CERTIFIED")
        self.assertFalse(is_certified(proposed, KEY))
        self.assertFalse(_runtime_check(proposed))

    def test_unrelated_certification_remains_active_after_one_is_suspended(self):
        other = "OLLAMA|other|PRIMARY|W2|S1|BENCH"
        registry = _registry()
        registry["certifications"][other] = {"status": "CERTIFIED"}
        proposed, _ = propose_transition(
            registry=registry, key=KEY, target_status="SUSPENDED",
            reason="model-specific incident", expected_status="CERTIFIED_WITH_LIMITS",
        )
        self.assertEqual(proposed["role_status"]["PRIMARY_W2"], "CERTIFIED")

    def test_apply_requires_expect_status(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            path.write_text(json.dumps(_registry()), encoding="utf-8")
            rc = lifecycle_main([
                "--registry", str(path), "--key", KEY, "--to", "SUSPENDED",
                "--reason", "test", "--apply",
            ])
            self.assertEqual(rc, 3)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["certifications"][KEY]["status"], "CERTIFIED_WITH_LIMITS")

    def test_dry_run_does_not_mutate_registry(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            original = _registry()
            path.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
            rc = lifecycle_main([
                "--registry", str(path), "--key", KEY, "--to", "SUSPENDED",
                "--reason", "dry-run test", "--expect-status", "CERTIFIED_WITH_LIMITS",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_apply_writes_audited_transition(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            path.write_text(json.dumps(_registry()), encoding="utf-8")
            rc = lifecycle_main([
                "--registry", str(path), "--key", KEY, "--to", "SUSPENDED",
                "--reason", "confirmed regression", "--incident-ref", "INC-9",
                "--expect-status", "CERTIFIED_WITH_LIMITS", "--apply",
            ])
            self.assertEqual(rc, 0)
            result = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["certifications"][KEY]["status"], "SUSPENDED")
            self.assertEqual(result["certification_lifecycle_events"][-1]["incident_ref"], "INC-9")
            self.assertFalse(_runtime_check(result))


if __name__ == "__main__":
    unittest.main()
