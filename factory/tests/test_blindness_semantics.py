import json
import tempfile
import unittest
from pathlib import Path

from hermes_factory.blindness import BLIND_REQUEST_ALLOWLIST, build_blind_worker_request, assert_blind_request
from hermes_factory.hashing import sha256_text
from hermes_factory.models import AssertionCandidate, SourceUnit
from hermes_factory.providers.fixture import DeterministicFixtureProvider
from hermes_factory.semantic import build_blind_request, execute_blind, execute_primary, normalize_provider_output
from hermes_factory.literal import numeric_inventory, qualifier_inventory, relationship_inventory
from hermes_factory.union import deterministic_union, build_evidence_families
from hermes_factory.specialists import run_deterministic_specialists
from hermes_factory.router import route_families


def unit(content="A value may increase from 10 to 20 mmHg when heated. It is not affected by ambient pressure.", rep="TEXT"):
    return SourceUnit(
        source_unit_id="SU-1", source_id="S", source_version_id="SV", source_sha256="a"*64,
        unit_type="PARAGRAPH", content_representation=rep, locator={"pdf_pages":[1]},
        content_sha256=sha256_text(content), content=content,
    )


class BlindnessTests(unittest.TestCase):
    def test_positive_allowlist_drops_eight_injections(self):
        u = unit()
        packet = {
            "request_schema_version":"1", "task_role":"BLIND_RECALL", "work_class":"W2", "source_class":"S1",
            "capsule_id":"C", "run_id":"R", "source_unit":u.to_dict(), "boundary_context":{},
            "task_instructions":"x", "output_schema":{}, "provider_constraints":{},
            "primary_assertions":[1], "peer_output":{}, "reference_answer":"x", "gold_value":4,
            "canonical_answer":"x", "review_decision":"PASS", "expected_count":9, "hidden_answer":"x",
        }
        clean = build_blind_worker_request(packet)
        self.assertEqual(set(clean), set(packet) & BLIND_REQUEST_ALLOWLIST)
        for k in ["primary_assertions","peer_output","reference_answer","gold_value","canonical_answer","review_decision","expected_count","hidden_answer"]:
            self.assertNotIn(k, clean)
        assert_blind_request(clean)

    def test_nested_forbidden_key_is_rejected(self):
        packet = {"source_unit":{"content":"x", "peer_output":{"x":1}}}
        with self.assertRaises(ValueError):
            build_blind_worker_request(packet)

    def test_build_blind_request_never_carries_contamination(self):
        req = build_blind_request(unit(), "C", "R", primary_assertions=[1], expected_count=5)
        self.assertNotIn("primary_assertions", req)
        self.assertNotIn("expected_count", req)


class SemanticTests(unittest.TestCase):
    def test_fixture_primary_and_blind_are_noncanonical(self):
        u = unit()
        p, pr = execute_primary(DeterministicFixtureProvider("PRIMARY"), u, "CP", "RP")
        b, br = execute_blind(DeterministicFixtureProvider("BLIND_RECALL"), u, "CB", "RB")
        self.assertTrue(p and b)
        self.assertTrue(all(x.canonical_state == "NON_CANONICAL" for x in p+b))
        self.assertFalse(pr["empirical_semantic_model"])
        self.assertFalse(br["empirical_semantic_model"])

    def test_non_source_evidence_rejected(self):
        u = unit("Source truth only.")
        provider = DeterministicFixtureProvider("PRIMARY")
        out = {"assertions":[{"proposition":"invented", "evidence":"fabricated"}]}
        with self.assertRaises(ValueError):
            normalize_provider_output(out, u, "C", "R", provider.identity(), "PRIMARY")

    def test_extractor_cannot_set_canonical(self):
        c = AssertionCandidate(
            candidate_id="c", source_unit_id="u", source_id="s", source_version_id="v", source_sha256="x",
            locator={}, evidence="e", evidence_sha256=sha256_text("e"), proposition="p", originating_run_id="r",
            canonical_state="CANONICAL"
        )
        self.assertIn("extractor_candidate_must_be_noncanonical", c.validate_invariants())


class LiteralTests(unittest.TestCase):
    def test_numeric_literal_preserves_unit_and_range(self):
        inv = numeric_inventory(unit())
        self.assertTrue(any("10 to 20" in x["value_literal"] and x["unit_literal"].lower().replace(" ","") == "mmhg" for x in inv))

    def test_qualifiers_detect_may_when_not(self):
        inv = qualifier_inventory(unit())
        kinds = {x["qualifier_type"] for x in inv}
        self.assertIn("MODAL_MAY", kinds)
        self.assertIn("CONDITIONAL", kinds)
        self.assertIn("NEGATION", kinds)

    def test_relationship_direction_inventory(self):
        inv = relationship_inventory(unit())
        kinds = {x["relationship_type"] for x in inv}
        self.assertIn("INCREASES", kinds)
        self.assertIn("UNAFFECTED_BY", kinds)


class UnionTests(unittest.TestCase):
    def test_union_preserves_distinct_candidate_origins(self):
        u = unit("Pressure increases.")
        p, _ = execute_primary(DeterministicFixtureProvider("PRIMARY"), u, "CP", "RP")
        b, _ = execute_blind(DeterministicFixtureProvider("BLIND_RECALL"), u, "CB", "RB")
        both = deterministic_union(p,b)
        self.assertEqual(len(both), len(p)+len(b))
        self.assertEqual({x.origin_pass for x in both}, {"PRIMARY","BLIND_RECALL"})

    def test_family_groups_exact_evidence_only(self):
        u = unit("Pressure increases.")
        p, _ = execute_primary(DeterministicFixtureProvider("PRIMARY"), u, "CP", "RP")
        b, _ = execute_blind(DeterministicFixtureProvider("BLIND_RECALL"), u, "CB", "RB")
        fam = build_evidence_families(deterministic_union(p,b))
        self.assertEqual(len(fam), 1)
        self.assertEqual(set(fam[0].origins), {"PRIMARY","BLIND_RECALL"})

    def test_table_is_routed_to_specialist_queue(self):
        u = unit("TABLE 1 Agent Value Halothane 243 torr.", rep="TABLE")
        p, _ = execute_primary(DeterministicFixtureProvider("PRIMARY"), u, "CP", "RP")
        fam = build_evidence_families(p)
        receipts = run_deterministic_specialists(fam, p, [u])
        routes = route_families(fam, receipts)
        self.assertTrue(any(r["action"] == "SPECIALIST_REVIEW_REQUIRED" for r in routes))
        self.assertTrue(any(any("TABLE_BINDING" in f for f in r["unresolved_flags"]) for r in routes))


if __name__ == "__main__":
    unittest.main()
