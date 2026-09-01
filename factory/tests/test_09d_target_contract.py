from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes_factory.bridge_09d import motion2_target_contract_readonly
from hermes_factory.hashing import sha256_text
from stages_ext.project_09d_motion2 import build_projection


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
            CREATE TABLE ingest_source_locator(
                ingest_locator_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                locator_json TEXT NOT NULL
            );
            CREATE INDEX ingest_source_locator_source_idx ON ingest_source_locator(source_id);

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
            CREATE INDEX source_assertion_candidate_subject_idx
                ON source_assertion_candidate(subject_entity_id);

            CREATE TABLE entity_name(
                canonical_id TEXT, name_text TEXT, normalized_name TEXT, is_searchable INTEGER
            );
        """)
        conn.commit()
    finally:
        conn.close()


def make_run(root: Path) -> Path:
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
    summary = {"carrier_scope": "MOTION1_AUTHORITY", "cycle_safe_authority_comparison": True}
    (run_dir / "SOURCE" / "source_units.jsonl").write_text(json.dumps(unit) + "\n", encoding="utf-8")
    (run_dir / "ASSERTIONS" / "union_candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    (run_dir / "09D" / "comparison_09d.jsonl").write_text(json.dumps(comparison) + "\n", encoding="utf-8")
    (run_dir / "09D" / "comparison_09d_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


class Motion2TargetContractTests(unittest.TestCase):
    def test_contract_is_stable_for_unchanged_target_schema(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "09d.sqlite"
            make_db(db)
            first = motion2_target_contract_readonly(db)
            second = motion2_target_contract_readonly(db)
            self.assertEqual(first["motion2_target_contract_sha256"], second["motion2_target_contract_sha256"])
            self.assertEqual(first["tables"], second["tables"])

    def test_unrelated_schema_change_does_not_change_motion2_contract(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "09d.sqlite"
            make_db(db)
            before = motion2_target_contract_readonly(db)
            conn = sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE unrelated_future_feature(id TEXT PRIMARY KEY, note TEXT)")
                conn.commit()
            finally:
                conn.close()
            after = motion2_target_contract_readonly(db)
            self.assertNotEqual(
                before["whole_database_schema_fingerprint_sha256"],
                after["whole_database_schema_fingerprint_sha256"],
            )
            self.assertEqual(
                before["motion2_target_contract_sha256"],
                after["motion2_target_contract_sha256"],
            )

    def test_relevant_target_schema_change_changes_motion2_contract(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "09d.sqlite"
            make_db(db)
            before = motion2_target_contract_readonly(db)
            conn = sqlite3.connect(db)
            try:
                conn.execute("ALTER TABLE ingest_source_locator ADD COLUMN locator_kind TEXT")
                conn.commit()
            finally:
                conn.close()
            after = motion2_target_contract_readonly(db)
            self.assertNotEqual(
                before["motion2_target_contract_sha256"],
                after["motion2_target_contract_sha256"],
            )

    def test_relevant_index_change_changes_motion2_contract(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "09d.sqlite"
            make_db(db)
            before = motion2_target_contract_readonly(db)
            conn = sqlite3.connect(db)
            try:
                conn.execute(
                    "CREATE INDEX source_assertion_candidate_predicate_idx "
                    "ON source_assertion_candidate(predicate_code)"
                )
                conn.commit()
            finally:
                conn.close()
            after = motion2_target_contract_readonly(db)
            self.assertNotEqual(
                before["motion2_target_contract_sha256"],
                after["motion2_target_contract_sha256"],
            )

    def test_projection_binds_every_row_to_same_target_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            make_db(db)
            run_dir = make_run(root)
            projection = build_projection(run_dir, db)
            contract_hash = projection["target_contract"]["motion2_target_contract_sha256"]
            self.assertEqual(projection["summary"]["motion2_target_contract_sha256"], contract_hash)
            self.assertEqual(projection["candidate_rows"][0]["09d_motion2_target_contract_sha256"], contract_hash)
            self.assertEqual(projection["locator_rows"][0]["09d_motion2_target_contract_sha256"], contract_hash)
            self.assertFalse(projection["target_contract"]["direct_insert_allowed"])
            self.assertFalse(projection["target_contract"]["automatic_schema_migration_allowed"])


if __name__ == "__main__":
    unittest.main()
