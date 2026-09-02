from __future__ import annotations

import unittest

from hermes_factory.models import SourceUnit, WorkerIdentity
from hermes_factory.router import route_families
from hermes_factory.semantic import build_primary_request, normalize_provider_output
from hermes_factory.union import build_evidence_families
from hermes_factory.hashing import sha256_text


WORKER = WorkerIdentity("OLLAMA", "model", "FAMILY", "sha256:" + "a" * 64, "PRIMARY")


def _unit(uid: str, unit_type: str, representation: str, content: str) -> SourceUnit:
    return SourceUnit(
        source_unit_id=uid,
        source_id="S",
        source_version_id="V",
        source_sha256="b" * 64,
        unit_type=unit_type,
        content_representation=representation,
        locator={"pdf_pages": [1]},
        content_sha256=sha256_text(content),
        content=content,
    )


def _candidate(unit: SourceUnit, proposition: str, evidence: str):
    rows = normalize_provider_output(
        {"assertions": [{"proposition": proposition, "evidence": evidence}]},
        unit,
        "CAP",
        "RUN",
        WORKER,
        "PRIMARY",
    )
    return rows[0]


class W3TierBRoutingTests(unittest.TestCase):
    def test_primary_request_remains_w2_candidate_generation_for_w3_equation_source(self):
        unit = _unit("EQ", "EQUATION", "TEXT", "Flow equals pressure divided by resistance.")
        request = build_primary_request(unit, "CAP", "RUN", source_class="S1")
        self.assertEqual(request["work_class"], "W2")
        candidate = _candidate(unit, "Flow equals pressure divided by resistance.", "Flow equals pressure divided by resistance.")
        self.assertEqual(candidate.metadata["source_risk_work_class"], "W3")
        self.assertEqual(candidate.metadata["source_risk_source_class"], "S1")

    def test_w3_equation_family_cannot_be_locally_closed_without_any_specialist_flags(self):
        unit = _unit("EQ", "EQUATION", "TEXT", "Flow equals pressure divided by resistance.")
        candidate = _candidate(unit, "Flow equals pressure divided by resistance.", "Flow equals pressure divided by resistance.")
        family = build_evidence_families([candidate])[0]
        route = route_families([family], [])[0]
        self.assertEqual(route["action"], "SPECIALIST_REVIEW_REQUIRED")
        self.assertEqual(route["priority"], "P1")
        self.assertIn("W3_TIER_B_REVIEW_REQUIRED", route["unresolved_codes"])
        self.assertEqual(route["source_risk_work_class"], "W3")

    def test_w2_text_family_can_still_be_locally_complete_when_no_other_flags_exist(self):
        unit = _unit("TXT", "PARAGRAPH", "TEXT", "The vaporizer contains agent.")
        candidate = _candidate(unit, "The vaporizer contains agent.", "The vaporizer contains agent.")
        family = build_evidence_families([candidate])[0]
        route = route_families([family], [])[0]
        self.assertEqual(candidate.metadata["source_risk_work_class"], "W2")
        self.assertEqual(route["action"], "LOCAL_PRECISION_COMPLETE")
        self.assertNotIn("W3_TIER_B_REVIEW_REQUIRED", route["unresolved_codes"])

    def test_conflicting_source_risk_metadata_is_p0(self):
        unit = _unit("TXT", "PARAGRAPH", "TEXT", "The vaporizer contains agent.")
        a = _candidate(unit, "The vaporizer contains agent.", "The vaporizer contains agent.")
        b = _candidate(unit, "The vaporizer contains agent.", "The vaporizer contains agent.")
        b.origin_pass = "BLIND_RECALL"
        b.candidate_id = "OTHER"
        b.metadata["source_risk_work_class"] = "W3"
        family = build_evidence_families([a, b])[0]
        route = route_families([family], [])[0]
        self.assertEqual(route["action"], "FAIL_BLOCKING")
        self.assertEqual(route["priority"], "P0")
        self.assertIn("SOURCE_RISK_METADATA_CONFLICT", route["unresolved_codes"])


if __name__ == "__main__":
    unittest.main()
