from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes_factory.bridge_09d import assert_write_blocked, motion2_capability_readonly
from hermes_factory.hashing import sha256_text
from stages_ext.compare_09d import build_index, classify
from stages_ext.project_09d_motion2 import build_projection


def _carrier(value_text: str = "MAC is 6.4%"):
    return [{
        "carrier_candidate_id": "R1",
        "subject_entity_id": "DES",
        "predicate_code": "mac",
        "predicate_norm": "mac",
        "fact_family": "drug",
        "value_text": value_text,
        "subject_aliases": {"desflurane"},
        "subject_tokens": {"desflurane"},
        "predicate_tokens": {"mac"},
        "value_tokens": {"mac"},
        "tokens": {"desflurane", "mac"},
        "numbers": {("6.4", "%")} if "6.4" in value_text else {("7.0", "%")},
        "context_qualifiers": set(),
        "negated": False,
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


class Motion2ProjectionTests(unittest.TestCase):
    def _make_db(self, path: Path) -> None:
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
            conn.commit()
        finally:
            conn.close()

    def test_schema_capability_and_projection_remain_non_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            self._make_db(db)
            self.assertTrue(assert_write_blocked(db))
            capability = motion2_capability_readonly(db)
            self.assertTrue(capability["required_tables_present"])
            self.assertTrue(capability["motion2_witness_constraint_present"])

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
                "subject_resolution": {"mode": "EXACT_ALIAS", "resolved_entity_ids": ["DES"]},
                "predicate_resolution": {"mode": "EXACT_CODE_OR_LABEL"},
                "top_matches": [{
                    "subject_compatible": True, "predicate_compatible": True,
                    "fact_family_compatible": True, "subject_entity_id": "DES",
                    "predicate_code": "mac", "score": 0.99,
                }],
            }
            (run_dir / "SOURCE" / "source_units.jsonl").write_text(json.dumps(unit) + "\n", encoding="utf-8")
            (run_dir / "ASSERTIONS" / "union_candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            (run_dir / "09D" / "comparison_09d.jsonl").write_text(json.dumps(comparison) + "\n", encoding="utf-8")

            projection = build_projection(run_dir, db)
            self.assertEqual(projection["summary"]["projection_status"], "SCHEMA_COMPATIBLE_NEEDS_GOVERNED_09D_LOADER")
            self.assertEqual(projection["summary"]["projection_error_count"], 0)
            row = projection["candidate_rows"][0]
            self.assertFalse(row["direct_insert_allowed"])
            self.assertFalse(row["automatic_identity_merge_allowed"])
            self.assertEqual(row["subject_identity_candidates"][0]["subject_entity_id"], "DES")
            self.assertFalse(row["subject_identity_candidates"][0]["selection_authorized"])


if __name__ == "__main__":
    unittest.main()
