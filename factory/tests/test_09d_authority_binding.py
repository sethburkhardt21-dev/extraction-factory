from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes_factory.bridge_09d import motion2_capability_readonly
from hermes_factory.hashing import sha256_file, sha256_text
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


def make_bound_run(root: Path, db: Path, *, target_match: bool = True) -> Path:
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

    capability = motion2_capability_readonly(db)
    db_hash = sha256_file(db)
    summary = {
        "stage": "READ_ONLY_09D_COMPARISON",
        "database_sha256_measured": db_hash,
        "database_matches_declared_target": target_match,
        "schema_fingerprint_sha256": capability["schema_fingerprint_sha256"],
        "motion2_capability": capability,
        "carrier_scope": "MOTION1_AUTHORITY",
        "cycle_safe_authority_comparison": True,
        "comparator_target": {
            "comparator_target_version": "SYNTHETIC_TEST_TARGET",
            "expected_db_sha256": db_hash,
        },
    }
    (run_dir / "SOURCE" / "source_units.jsonl").write_text(json.dumps(unit) + "\n", encoding="utf-8")
    (run_dir / "ASSERTIONS" / "union_candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    (run_dir / "09D" / "comparison_09d.jsonl").write_text(json.dumps(comparison) + "\n", encoding="utf-8")
    (run_dir / "09D" / "comparison_09d_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


class AuthorityBindingTests(unittest.TestCase):
    def test_strict_projection_accepts_verified_bound_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            make_db(db)
            run_dir = make_bound_run(root, db)
            projection = build_projection(run_dir, db, require_verified_target=True)
            self.assertTrue(projection["authority_binding"]["verified"])
            self.assertTrue(projection["summary"]["authority_binding_verified"])
            self.assertEqual(projection["summary"]["projection_error_count"], 0)
            row = projection["candidate_rows"][0]
            self.assertEqual(row["loader_disposition"], "READY_FOR_09D_ADJUDICATION")
            self.assertTrue(row["09d_authority_binding_verified"])
            self.assertEqual(row["09d_authority_context_id"], projection["summary"]["authority_context_id"])

    def test_strict_projection_rejects_unverified_database_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            make_db(db)
            run_dir = make_bound_run(root, db, target_match=False)
            projection = build_projection(run_dir, db, require_verified_target=True)
            self.assertFalse(projection["authority_binding"]["verified"])
            self.assertEqual(projection["summary"]["projection_status"], "PROJECTION_REVIEW_REQUIRED")
            codes = {e["code"] for e in projection["summary"]["projection_errors"]}
            self.assertIn("09D_COMPARISON_AUTHORITY_BINDING_FAILED", codes)
            row = projection["candidate_rows"][0]
            self.assertEqual(row["loader_disposition"], "REVIEW_REQUIRED")
            self.assertEqual(row["subject_identity_candidates"], [])
            self.assertEqual(row["predicate_identity_candidates"], [])

    def test_strict_projection_detects_target_schema_drift_after_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            make_db(db)
            run_dir = make_bound_run(root, db)
            conn = sqlite3.connect(db)
            try:
                conn.execute("ALTER TABLE ingest_source_locator ADD COLUMN locator_kind TEXT")
                conn.commit()
            finally:
                conn.close()
            projection = build_projection(run_dir, db, require_verified_target=True)
            self.assertFalse(projection["authority_binding"]["verified"])
            failed = set(projection["summary"]["projection_errors"][0].get("failed_checks", []))
            self.assertTrue({
                "schema_fingerprint_matches_current_target",
                "motion2_target_contract_matches_current_target",
            } & failed)
            self.assertEqual(projection["candidate_rows"][0]["loader_disposition"], "REVIEW_REQUIRED")

    def test_authority_context_changes_when_comparison_bytes_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "09d.sqlite"
            make_db(db)
            run_dir = make_bound_run(root, db)
            first = build_projection(run_dir, db, require_verified_target=True)
            comparison_path = run_dir / "09D" / "comparison_09d.jsonl"
            row = json.loads(comparison_path.read_text(encoding="utf-8"))
            row["comparison_confidence"] = "MEDIUM"
            comparison_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            second = build_projection(run_dir, db, require_verified_target=True)
            self.assertNotEqual(
                first["authority_binding"]["authority_context"]["comparison_jsonl_sha256"],
                second["authority_binding"]["authority_context"]["comparison_jsonl_sha256"],
            )
            self.assertNotEqual(first["summary"]["authority_context_id"], second["summary"]["authority_context_id"])


if __name__ == "__main__":
    unittest.main()
