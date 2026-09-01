from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes_factory.contract_09d import verify_09d_contract
from hermes_factory.hashing import sha256_text
from hermes_factory.models import AssertionCandidate, SourceUnit, WorkerIdentity
from hermes_factory.semantic import normalize_provider_output
from stages_ext.compare_09d import build_index, classify, load_carrier
from stages_ext.project_09d_motion2 import build_projection


CARRIER_SQL = """
CREATE TABLE source_assertion_candidate (
  candidate_id TEXT PRIMARY KEY,
  subject_entity_id TEXT,
  predicate_code TEXT,
  value_text TEXT,
  fact_family TEXT,
  source_resource_id TEXT,
  ingest_locator_id TEXT,
  parent_assertion_id TEXT,
  source_locator_id TEXT,
  raw_cell_id TEXT,
  carried_status TEXT,
  carried_confidence_basis TEXT,
  carried_source_era TEXT,
  CONSTRAINT source_assertion_candidate_witness_by_kind CHECK (
    (source_resource_id IS NOT NULL AND ingest_locator_id IS NULL)
    OR
    (source_resource_id IS NULL AND ingest_locator_id IS NOT NULL
      AND parent_assertion_id IS NULL
      AND source_locator_id IS NULL
      AND raw_cell_id IS NULL
      AND carried_status IS NULL
      AND carried_confidence_basis IS NULL
      AND carried_source_era IS NULL)
  )
);
"""


def make_structural_09d(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(CARRIER_SQL + """
CREATE TABLE entity_name(canonical_id TEXT, name_text TEXT, normalized_name TEXT, is_searchable INTEGER);
CREATE TABLE ingest_source_locator(id TEXT);
CREATE TABLE assertion(id TEXT);
CREATE TABLE candidate_registry(
  candidate_id TEXT PRIMARY KEY,
  domain TEXT NOT NULL,
  source_table TEXT NOT NULL,
  source_key TEXT NOT NULL,
  source_identity_sha256 TEXT NOT NULL UNIQUE,
  origin_package_id TEXT,
  state TEXT NOT NULL,
  legacy_entity_id TEXT,
  UNIQUE(source_table, source_key)
);
CREATE TABLE candidate_promotion_event(id TEXT);
""")
    con.commit()
    con.close()


class ContractTests(unittest.TestCase):
    def test_structural_motion2_contract_passes_and_write_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.sqlite"
            make_structural_09d(db)
            report = verify_09d_contract(db, verify_identity=False, strict_counts=False)
            self.assertTrue(report["ok"], report["errors"])
            self.assertTrue(report["read_only_comparison_allowed"])
            self.assertFalse(report["write_allowed"])
            self.assertFalse(report["automatic_promotion_allowed"])

    def test_missing_named_motion2_constraint_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.sqlite"
            make_structural_09d(db)
            con = sqlite3.connect(db)
            # Rebuild the carrier without the named witness constraint.
            con.execute("ALTER TABLE source_assertion_candidate RENAME TO old_carrier")
            con.execute("CREATE TABLE source_assertion_candidate(candidate_id TEXT PRIMARY KEY, subject_entity_id TEXT, predicate_code TEXT, value_text TEXT, fact_family TEXT, source_resource_id TEXT, ingest_locator_id TEXT, parent_assertion_id TEXT, source_locator_id TEXT, raw_cell_id TEXT, carried_status TEXT, carried_confidence_basis TEXT, carried_source_era TEXT)")
            con.commit(); con.close()
            report = verify_09d_contract(db, verify_identity=False, strict_counts=False)
            self.assertFalse(report["ok"])
            self.assertIn("09d_motion2_witness_constraint_missing", report["errors"])

    def test_motion2_forbidden_legacy_payload_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.sqlite"
            make_structural_09d(db)
            con = sqlite3.connect(db)
            con.execute("PRAGMA ignore_check_constraints=ON")
            con.execute(
                "INSERT INTO source_assertion_candidate(candidate_id,ingest_locator_id,carried_status) VALUES('C','L','legacy')"
            )
            con.commit(); con.close()
            report = verify_09d_contract(db, verify_identity=False, strict_counts=False)
            self.assertFalse(report["ok"])
            self.assertTrue(any(x.startswith("09d_motion2_forbidden_payload_rows") for x in report["errors"]))


class StableIdentityTests(unittest.TestCase):
    def test_same_source_claim_has_same_stable_identity_across_runs(self):
        text = "Desflurane vapor pressure is 664 mmHg."
        unit = SourceUnit(
            "U", "S", "V", "a" * 64, "PARAGRAPH", "TEXT", {"pdf_pages": [1]},
            sha256_text(text), text,
        )
        worker = WorkerIdentity("TEST", "m", "F", "1", "PRIMARY")
        output = {"assertions": [{
            "proposition": text,
            "evidence": text,
            "subject": "Desflurane",
            "predicate": "vapor pressure",
            "object_value": "664 mmHg",
        }]}
        a = normalize_provider_output(output, unit, "CAP", "RUN-A", worker, "PRIMARY")[0]
        b = normalize_provider_output(output, unit, "CAP", "RUN-B", worker, "PRIMARY")[0]
        self.assertNotEqual(a.candidate_id, b.candidate_id)
        self.assertEqual(a.stable_witness_sha256, b.stable_witness_sha256)
        self.assertEqual(a.stable_claim_sha256, b.stable_claim_sha256)

    def test_from_dict_preserves_new_defaults_for_old_artifacts(self):
        old = {
            "candidate_id": "C", "source_unit_id": "U", "source_id": "S", "source_version_id": "V",
            "source_sha256": "a" * 64, "locator": {}, "evidence": "x", "evidence_sha256": "b" * 64,
            "proposition": "x", "originating_run_id": "R",
        }
        c = AssertionCandidate.from_dict(old)
        self.assertEqual(c.stable_witness_sha256, "")
        self.assertEqual(c.numeric_values, [])
        self.assertEqual(c.metadata, {})


class ProjectionTests(unittest.TestCase):
    def test_projection_deduplicates_stable_claim_and_never_becomes_insert_ready(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run"
            for d in ("ASSERTIONS", "FAMILIES", "REVIEW"):
                (run / d).mkdir(parents=True, exist_ok=True)
            base = {
                "source_unit_id": "U", "source_id": "S", "source_version_id": "V", "source_sha256": "a" * 64,
                "locator": {"pdf_pages": [1]}, "evidence_sha256": "b" * 64,
                "proposition": "Desflurane vapor pressure is 664 mmHg.", "subject": "Desflurane",
                "predicate": "vapor pressure", "object_value": "664 mmHg", "numeric_values": [],
                "qualifiers": [], "polarity": "AFFIRMATIVE", "certainty": "ASSERTED",
            }
            rows = [dict(base, candidate_id="C1", origin_pass="PRIMARY"), dict(base, candidate_id="C2", origin_pass="BLIND_RECALL")]
            with (run / "ASSERTIONS" / "union_candidates.jsonl").open("w", encoding="utf-8") as f:
                for row in rows: f.write(json.dumps(row) + "\n")
            (run / "FAMILIES" / "evidence_families.jsonl").write_text(json.dumps({
                "family_id": "F", "member_candidate_ids": ["C1", "C2"]
            }) + "\n", encoding="utf-8")
            (run / "REVIEW" / "routes.jsonl").write_text(json.dumps({
                "family_id": "F", "action": "LOCAL_PRECISION_COMPLETE", "unresolved_flags": []
            }) + "\n", encoding="utf-8")
            summary = build_projection(run)
            self.assertEqual(summary["stable_projected_candidate_count"], 1)
            projected = json.loads((run / "09D" / "motion2_candidate_envelope.jsonl").read_text().strip())
            self.assertTrue(projected["candidate_registry"]["candidate_id"].startswith("CAND:"))
            self.assertEqual(len(projected["candidate_registry"]["source_identity_sha256"]), 64)
            self.assertFalse(projected["09d_intake_readiness"]["insert_ready"])
            self.assertFalse(projected["09d_intake_readiness"]["automatic_promotion_allowed"])
            self.assertIsNone(projected["candidate_registry"]["origin_package_id"])
            self.assertIsNone(projected["source_assertion_candidate_motion2_template"]["ingest_locator_id"])


class ComparatorModelTests(unittest.TestCase):
    @staticmethod
    def carrier(value="669 mmHg"):
        return [{
            "carrier_candidate_id": "R1", "subject_entity_id": "DES",
            "predicate_code": "drug.vapor_pressure", "fact_family": "drug", "value_text": value,
            "subject_tokens": {"desflurane"}, "predicate_tokens": {"vapor", "pressure"},
            "value_tokens": {"669", "mmhg"}, "tokens": {"desflurane", "vapor", "pressure", "669", "mmhg"},
            "numbers": {("669", "mmhg")} if value else set(), "qualifier_cues": set(), "negated": False,
        }]

    @staticmethod
    def candidate(value="664"):
        return {
            "candidate_id": "C", "source_unit_id": "U", "origin_pass": "PRIMARY",
            "proposition": f"Desflurane vapor pressure is {value} mmHg.", "subject": "Desflurane",
            "predicate": "vapor pressure", "polarity": "AFFIRMATIVE", "metadata": {"fact_family": "drug"},
        }

    def test_true_conflict_requires_trusted_target_and_structured_compatibility(self):
        carrier = self.carrier()
        result = classify(self.candidate(), carrier, build_index(carrier), target_trusted=True)
        self.assertEqual(result["conflict_outcome"], "TRUE_CONFLICT")
        self.assertEqual(result["state"], "CONTRADICTION")
        self.assertFalse(result["selection_allowed"])
        diagnostic = classify(self.candidate(), carrier, build_index(carrier), target_trusted=False)
        self.assertNotEqual(diagnostic["conflict_outcome"], "TRUE_CONFLICT")
        self.assertNotEqual(diagnostic["state"], "CONTRADICTION")

    def test_equivalent_numeric_format_is_not_a_conflict(self):
        carrier = self.carrier("6.40 %")
        carrier[0]["numbers"] = {("6.4", "%")}
        carrier[0]["tokens"] = {"desflurane", "vapor", "pressure", "6", "40"}
        candidate = self.candidate("6.4")
        result = classify(candidate, carrier, build_index(carrier), target_trusted=True)
        self.assertNotEqual(result["conflict_outcome"], "TRUE_CONFLICT")

    def test_null_value_carrier_is_not_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "carrier.sqlite"
            con = sqlite3.connect(db)
            con.executescript(CARRIER_SQL + "CREATE TABLE entity_name(canonical_id TEXT,name_text TEXT,normalized_name TEXT,is_searchable INTEGER);")
            con.execute("INSERT INTO source_assertion_candidate(candidate_id,subject_entity_id,predicate_code,source_resource_id) VALUES('C','E','some.predicate','S')")
            con.execute("INSERT INTO entity_name VALUES('E','Some entity','some entity',1)")
            con.commit(); con.close()
            rows = load_carrier(db)
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["value_text"])


if __name__ == "__main__":
    unittest.main()
