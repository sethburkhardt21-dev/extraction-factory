import json
import tempfile
import unittest
from pathlib import Path

from hermes_factory.blindness import build_blind_worker_request
from hermes_factory.hashing import sha256_text
from hermes_factory.models import AssertionCandidate, EvidenceFamily, Gate, SourceUnit
from hermes_factory.readiness import derive_readiness
from hermes_factory.specialists import qualifier_scope_check, relationship_direction_check, numeric_binding_check


def cand(evidence, proposition):
    return AssertionCandidate(candidate_id="C",source_unit_id="U",source_id="S",source_version_id="V",source_sha256="a",locator={},evidence=evidence,evidence_sha256=sha256_text(evidence),proposition=proposition,originating_capsule_id="CP",originating_run_id="R",parent_artifact_sha256="P")

def family():
    return EvidenceFamily(family_id="F",source_unit_id="U",member_candidate_ids=["C"],propositions=[],origins=["PRIMARY"],evidence_hashes=[],disagreement_types=[],specialist_requirements=[])


class SemanticMutationTests(unittest.TestCase):
    def test_dropped_negation_detected(self):
        c=cand("It is not affected by pressure.","It is affected by pressure.")
        r=qualifier_scope_check(family(),{"C":c})
        self.assertEqual(r.outcome,"AMBIGUOUS_DEFER")

    def test_dropped_may_detected(self):
        c=cand("Pressure may increase.","Pressure increases.")
        r=qualifier_scope_check(family(),{"C":c})
        self.assertEqual(r.outcome,"AMBIGUOUS_DEFER")

    def test_direction_cue_loss_detected(self):
        c=cand("Pressure increases with heat.","Pressure changes with heat.")
        r=relationship_direction_check(family(),{"C":c})
        self.assertEqual(r.outcome,"AMBIGUOUS_DEFER")

    def test_numeric_literal_loss_detected(self):
        c=cand("Pressure is 20 mmHg.","Pressure is elevated.")
        r=numeric_binding_check(family(),{"C":c})
        self.assertEqual(r.outcome,"AMBIGUOUS_DEFER")


class ReadinessMutationTests(unittest.TestCase):
    def test_unresolved_p0_blocks(self):
        r=derive_readiness([Gate("SOURCE_AUTHORITY","PASS"),Gate("P0_INTEGRITY","FAIL_BLOCKING")])
        self.assertFalse(r["frontier_review_ready"])

    def test_missing_receipt_not_run_blocks(self):
        r=derive_readiness([Gate("SOURCE_AUTHORITY","PASS"),Gate("SEMANTIC_RECEIPTS","NOT_RUN")])
        self.assertFalse(r["frontier_review_ready"])

    def test_authored_status_input_is_ignored_because_api_only_uses_gates(self):
        gates=[Gate("SOURCE","PASS"),Gate("BUILD","FAIL_BLOCKING")]
        r=derive_readiness(gates)
        self.assertEqual(r["status"],"NOT_READY")


class BlindInjectionTests(unittest.TestCase):
    def test_all_known_leakage_keys_removed(self):
        keys=["primary_assertions","peer_output","reference_answer","gold_value","canonical_answer","review_decision","expected_count","hidden_answer"]
        raw={"request_schema_version":"1","task_role":"BLIND_RECALL","work_class":"W2","source_class":"S1","capsule_id":"C","run_id":"R","source_unit":{"content":"x"},"boundary_context":{},"task_instructions":"x","output_schema":{},"provider_constraints":{}}
        raw.update({k:"SECRET" for k in keys})
        clean=build_blind_worker_request(raw)
        self.assertFalse(any(k in clean for k in keys))


if __name__ == "__main__": unittest.main()
