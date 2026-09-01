from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes_factory.bridge_09d import (
    assert_write_blocked,
    carrier_witness_partition_readonly,
    motion2_capability_readonly,
)
from hermes_factory.hashing import sha256_text
from stages_ext.compare_09d import build_index, classify, load_carrier
from stages_ext.project_09d_motion2 import build_projection


def _carrier(value_text: str = "MAC is 6.4%", subject: str = "DES", alias: str = "desflurane"):
    return [{
        "carrier_candidate_id": "R1",
        "subject_entity_id": subject,
        "predicate_code": "mac",
        "predicate_norm": "mac",
        "fact_family": "drug",
        "value_text": value_text,
        "subject_aliases": {alias},
        "subject_tokens": {alias},
        "predicate_tokens": {"mac"},
        "value_tokens": {"mac"},
        "tokens": {alias, "mac"},
        "numbers": {("6.4", "%")} if "6.4" in value_text else {("7.0", "%")},
        "context_qualifiers": set(),
        "negated": False,
        "witness_kind": "MOTION1_SOURCE_WITNESSED",
    }]


class ComparatorIdentityTests(unittest.TestCase):
    def test_exact_alias_and_predicate_can_support(self):
        carrier = _carrier()
        candidate = {
            "candidate_id": "C1", "source_unit_id": "U1", "origin_pass": "PRIMARY",
            "proposition": "Desflurane MAC is 6.4%.", "subject": "Desflurane",
            "predicate": "MAC", "polarity": "AFFIRMATIVE", "metadata": {"fact_family": "drug"},
        }
        result = classify(candidate, carrier, build_index(carrier))
        self.assertEqual(result["state"], "SUPPORT")
        self.assertEqual(result["subject_resolution"]["resolved_entity_ids"], ["DES"])
        self.assertFalse(result["subject_resolution"]["ambiguous"])
        self.assertEqual(result["predicate_resolution"]["mode"], "EXACT_CODE_OR_LABEL")

    def test_same_identity_same_unit_different_value_is_contradiction(self):
        carrier = _carrier("MAC is 7.0%")
        candidate = {
            "candidate_id": "C1", "source_unit_id": "U1", "origin_pass": "PRIMARY",
            "proposition": "Desflurane MAC is 6.4%.", "subject": "Desflurane",
            "predicate": "MAC", "polarity": "AFFIRMATIVE", "metadata": {"fact_family": "drug"},
        }
        result = classify(candidate, carrier, build_index(carrier))
        self.assertEqual(result["state"], "CONTRADICTION")
        self.assertEqual(result["comparison_confidence"], "HIGH")

    def test_context_difference_suppresses_numeric_contradiction(self):
        carrier = _carrier("MAC is 7.0%")
        candidate = {
            "candidate_id": "C1", "source_unit_id": "U1", "origin_pass": "PRIMARY",
            "proposition": "Desflurane MAC may be 6.4%.", "subject": "Desflurane",
            "predicate": "MAC", "polarity": "AFFIRMATIVE", "metadata": {"fact_family": "drug"},
        }
        result = classify(candidate, carrier, build_index(carrier))
        self.assertNotEqual(result["state"], "CONTRADICTION")
        self.assertEqual(result["state"], "CONTEXT_DIFFERENCE")

    def test_ambiguous_exact_alias_cannot_support_or_contradict(self):
        carrier = _carrier(subject="E1", alias="agent") + [{
            **_carrier(subject="E2", alias="agent")[0],
            "carrier_candidate_id": "R2",
            "subject_entity_id": "E2",
        }]
        candidate = {
            "candidate_id": "C", "source_unit_id": "U", "origin_pass": "PRIMARY",
            "proposition": "Agent MAC is 6.4%.", "subject": "Agent", "predicate": "MAC",
            "polarity": "AFFIRMATIVE", "metadata": {"fact_family": "drug"},
        }
        result = classify(candidate, carrier, build_index(carrier))
        self.assertEqual(result["state"], "IDENTITY_UNCERTAIN")
        self.assertTrue(result["subject_resolution"]["ambiguous"])
        self.assertEqual(set(result["subject_resolution"]["resolved_entity_ids"]), {"E1", "E2"})

    def test_structured_numeric_binding_beats_neighbor_number_capture(self):
        carrier = _carrier("MAC is 7.0% at 760 mmHg")
        carrier[0]["numbers"] = {("7.0", "%"), ("760", "mmhg")}
        candidate = {
            "candidate_id": "C", "source_unit_id": "U", "origin_pass": "PRIMARY",
            "proposition": "Desflurane MAC is 6.4% at 760 mmHg.", "subject": "Desflurane",
            "predicate": "MAC", "polarity": "AFFIRMATIVE", "metadata": {"fact_family": "drug"},
            "numeric_values": [{"value_literal": "6.4", "unit_literal": "%"}],
        }
        result = classify(candidate, carrier, build_index(carrier))
        self.assertEqual(result["numeric_comparison_basis"], "STRUCTURED_NUMERIC_VALUES")
        self.assertEqual(result["state"], "CONTRADICTION")


class Motion2ProjectionTests(unittest.TestCase):
    def _make_db(self, path: Path, *, add_rows: bool = False) -> None:
        conn = sqlite3.connect(path)
        try:
            conn.executescript("""
                CREATE TABLE ingest_source_locator(
                    ingest_locator_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    locator_json TEXT NOT NULL
                );
                CREATE TABLE source_assertion_candidate(
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
                    CONSTRAINT source_assertion_candidate_witness_by_kind CHECK(
                         (source_resource_id IS NOT NULL AND ingest_locator_id IS NULL)
                      OR (source_resource_id IS NULL AND ingest_locator_id IS NOT NULL
                          AND parent_assertion_id IS NULL AND source_locator_id IS NULL
                          AND raw_cell_id IS NULL AND carried_status IS NULL
                          AND carried_confidence_basis IS NULL AND carried_source_era IS NULL)
                    )
                );
                CREATE TABLE entity_name(
                    canonical_id TEXT, name_text TEXT, normalized_name TEXT, is_searchable INTEGER
                );
            """)
            if add_rows:
                conn.execute("INSERT INTO entity_name VALUES('DES','Desflurane','desflurane',1)")
                conn.execute(
                    "INSERT INTO source_assertion_candidate(candidate_id,subject_entity_id,predicate_code,value_text,fact_family,source_resource_id) "
                    "VALUES('M1','DES','mac','MAC is 6.4%','drug','SRC1')"
                )
                conn.execute("INSERT INTO ingest_source_locator VALUES('L2','S2','{}')")
                conn.execute(
                    "INSERT INTO source_assertion_candidate(candidate_id,subject_entity_id,predicate_code,value_text,fact_family,ingest_locator_id) "
                    "VALUES('M2','DES','mac','MAC is 7.0%','drug','L2')"
                )
            conn.commit()
        finally:
            conn.close()

    def _make_run(self, root: Path, *, cycle_safe: bool = True) -> Path:
        run_dir = root / "run"
        (run_dir / "ASSERTIONS").mkdir(parents=True)
        (run_dir / "SOURCE").mkdir(parents=True)
        (run_dir / "09D").mkdir(parents=True)
        content = "Desflurane MAC is 6.4%."
        unit = {
            "source_unit_id": "U1", "source_id": "S1", "source_version_id": "V1",
            "source_sha256": "sourcehash", "content_sha256": sha256_text(content),
            "unit_type": "PARAGRAPH", "content_representation": "TEXT",
            "locator": {"pdf_pages": [1]}, "content": content,
        }
        candidate = {
            "candidate_id": "C1", "source_unit_id": "U1", "source_id": "S1",
            "source_version_id": "V1", "source_sha256": "sourcehash",
            "locator": {"pdf_pages": [1]}, "evidence": content,
            "evidence_sha256": sha256_text(content), "proposition": content,
            "subject": "Desflurane", "predicate": "MAC", "numeric_values": [],
            "qualifiers": [], "polarity": "AFFIRMATIVE", "certainty": "ASSERTED",
            "review_state": "UNREVIEWED", "canonical_state": "NON_CANONICAL",
            "worker_identity": {"provider": "TEST"}, "origin_pass": "PRIMARY",
            "uncertainty_flags": [],
        }
        comparison = {
            "candidate_id": "C1", "state": "SUPPORT", "comparison_confidence": "HIGH",
            "subject_resolution": {"mode": "EXACT_ALIAS", "resolved_entity_ids": ["DES"], "ambiguous": False},
            "predicate_resolution": {"mode": "EXACT_CODE_OR_LABEL"},
            "top_matches": [{
                "subject_compatible": True, "predicate_compatible": True,
                "fact_family_compatible": True, "subject_entity_id": "DES",
                "predicate_code": "mac", "score": 0.99,
                "witness_kind": "MOTION1_SOURCE_WITNESSED",
            }],
        }
        summary = {
            "carrier_scope": "MOTION1_AUTHORITY" if cycle_safe else "ALL_CARRIER",
            "cycle_safe_authority_comparison": cycle_safe,
        }
        (run_dir / "SOURCE" / "source_units.jsonl").write_text(json.dumps(unit) + "\n", encoding="utf-8")
        (run_dir / "ASSERTIONS" / "union_candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
        (run_dir / "09D" / "comparison_09d.jsonl").write_text(json.dumps(comparison) + "\n", encoding="utf-8")
        (run_dir / "09D" / "comparison_09d_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return run_dir

    def test_carrier_partition_and_default_scope_exclude_motion2(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "09d.sqlite"
            self._make_db(db, add_rows=True)
            partition = carrier_witness_partition_readonly(db)
            self.assertEqual(partition["motion1_rows"], 1)
            self.assertEqual(partition["motion2_rows"], 1)
            self.assertEqual(partition["invalid_witness_rows"], 0)
            self.assertTrue(partition["partition_valid"])
            authority = load_carrier(db)
            all_rows = load_carrier(db, scope="ALL_CARRIER")
            self.assertEqual(len(authority), 1)
            self.assertEqual(authority[0]["carrier_candidate_id"], "M1")
            self.assertEqual(len(all_rows), 2)

    def test_schema_capability_and_projection_remain_non_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            self._make_db(db)
            self.assertTrue(assert_write_blocked(db))
            capability = motion2_capability_readonly(db)
            self.assertTrue(capability["required_tables_present"])
            self.assertTrue(capability["motion2_witness_constraint_present"])
            self.assertTrue(capability["carrier_partition_valid"])

            run_dir = self._make_run(root, cycle_safe=True)
            projection = build_projection(run_dir, db)
            self.assertEqual(projection["summary"]["projection_status"], "SCHEMA_COMPATIBLE_NEEDS_GOVERNED_09D_LOADER")
            self.assertEqual(projection["summary"]["projection_error_count"], 0)
            self.assertTrue(projection["summary"]["cycle_safe_authority_comparison"])
            row = projection["candidate_rows"][0]
            self.assertFalse(row["direct_insert_allowed"])
            self.assertFalse(row["automatic_identity_merge_allowed"])
            self.assertEqual(row["subject_identity_candidates"][0]["subject_entity_id"], "DES")
            self.assertFalse(row["subject_identity_candidates"][0]["selection_authorized"])
            self.assertEqual(row["loader_disposition"], "READY_FOR_09D_ADJUDICATION")

    def test_projection_rejects_all_carrier_comparison_as_cycle_unsafe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            self._make_db(db)
            run_dir = self._make_run(root, cycle_safe=False)
            projection = build_projection(run_dir, db)
            self.assertEqual(projection["summary"]["projection_status"], "PROJECTION_REVIEW_REQUIRED")
            codes = {e["code"] for e in projection["summary"]["projection_errors"]}
            self.assertIn("09D_COMPARISON_NOT_CYCLE_SAFE", codes)
            self.assertEqual(projection["candidate_rows"][0]["loader_disposition"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
