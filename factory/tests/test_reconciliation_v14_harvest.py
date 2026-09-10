from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hermes_factory.cli import _lease_ttl
from hermes_factory.contract_09d import verify_09d_contract
from hermes_factory.controller import _write_json, run_factory
from hermes_factory.hashing import sha256_file, sha256_text
from hermes_factory.models import AssertionCandidate, SourceUnit, WorkerIdentity
from hermes_factory.semantic import normalize_provider_output
from run_appliance import _appliance_status, _last_json_object


CARRIER_SQL = """
CREATE TABLE source_assertion_candidate (
  candidate_id TEXT PRIMARY KEY, subject_entity_id TEXT, predicate_code TEXT,
  value_text TEXT, fact_family TEXT, source_resource_id TEXT, ingest_locator_id TEXT,
  parent_assertion_id TEXT, source_locator_id TEXT, raw_cell_id TEXT,
  carried_status TEXT, carried_confidence_basis TEXT, carried_source_era TEXT,
  CONSTRAINT source_assertion_candidate_witness_by_kind CHECK (
    (source_resource_id IS NOT NULL AND ingest_locator_id IS NULL) OR
    (source_resource_id IS NULL AND ingest_locator_id IS NOT NULL
      AND parent_assertion_id IS NULL AND source_locator_id IS NULL AND raw_cell_id IS NULL
      AND carried_status IS NULL AND carried_confidence_basis IS NULL AND carried_source_era IS NULL)
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
  candidate_id TEXT PRIMARY KEY, domain TEXT NOT NULL, source_table TEXT NOT NULL,
  source_key TEXT NOT NULL, source_identity_sha256 TEXT NOT NULL UNIQUE,
  origin_package_id TEXT, state TEXT NOT NULL, legacy_entity_id TEXT,
  UNIQUE(source_table, source_key)
);
CREATE TABLE candidate_promotion_event(id TEXT);
""")
    con.commit()
    con.close()


class ContractTests(unittest.TestCase):
    def test_structural_contract_passes_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.sqlite"
            make_structural_09d(db)
            report = verify_09d_contract(db, verify_identity=False, strict_counts=False)
            self.assertTrue(report["ok"], report["errors"])
            self.assertTrue(report["read_only_comparison_allowed"])
            self.assertFalse(report["write_allowed"])
            self.assertFalse(report["automatic_promotion_allowed"])

    def test_missing_witness_constraint_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.sqlite"
            make_structural_09d(db)
            con = sqlite3.connect(db)
            con.execute("ALTER TABLE source_assertion_candidate RENAME TO old_carrier")
            con.execute("CREATE TABLE source_assertion_candidate(candidate_id TEXT PRIMARY KEY, subject_entity_id TEXT, predicate_code TEXT, value_text TEXT, fact_family TEXT, source_resource_id TEXT, ingest_locator_id TEXT, parent_assertion_id TEXT, source_locator_id TEXT, raw_cell_id TEXT, carried_status TEXT, carried_confidence_basis TEXT, carried_source_era TEXT)")
            con.commit()
            con.close()
            report = verify_09d_contract(db, verify_identity=False, strict_counts=False)
            self.assertFalse(report["ok"])
            self.assertIn("09d_motion2_witness_constraint_missing", report["errors"])


class IdentityTests(unittest.TestCase):
    def _unit(self):
        text = "Desflurane vapor pressure is 664 mmHg."
        return SourceUnit(
            "U", "S", "V", "a" * 64, "PARAGRAPH", "TEXT",
            {"pdf_pages": [1]}, sha256_text(text), text,
        )

    def test_stable_identity_survives_run_id_change(self):
        unit = self._unit()
        worker = WorkerIdentity("TEST", "m", "F", "1", "PRIMARY")
        output = {"assertions": [{
            "proposition": unit.content, "evidence": unit.content,
            "subject": "Desflurane", "predicate": "vapor pressure",
            "object_value": "664 mmHg",
        }]}
        a = normalize_provider_output(output, unit, "CAP", "RUN-A", worker, "PRIMARY")[0]
        b = normalize_provider_output(output, unit, "CAP", "RUN-B", worker, "PRIMARY")[0]
        self.assertNotEqual(a.candidate_id, b.candidate_id)
        self.assertEqual(a.stable_witness_sha256, b.stable_witness_sha256)
        self.assertEqual(a.stable_claim_sha256, b.stable_claim_sha256)

    def test_old_artifact_defaults_are_not_overwritten_with_none(self):
        old = {
            "candidate_id": "C", "source_unit_id": "U", "source_id": "S",
            "source_version_id": "V", "source_sha256": "a" * 64,
            "locator": {}, "evidence": "x", "evidence_sha256": "b" * 64,
            "proposition": "x", "originating_run_id": "R",
        }
        candidate = AssertionCandidate.from_dict(old)
        self.assertEqual(candidate.numeric_values, [])
        self.assertEqual(candidate.metadata, {})
        self.assertEqual(candidate.stable_witness_sha256, "")
        source = SourceUnit.from_dict({
            "source_unit_id": "U", "source_id": "S", "source_version_id": "V",
            "source_sha256": "a" * 64, "unit_type": "PARAGRAPH",
            "content_representation": "TEXT", "locator": {},
            "content_sha256": "b" * 64, "content": "x",
        })
        self.assertEqual(source.rights_metadata, {})
        self.assertEqual(source.process_metadata, {})


class SafetyTests(unittest.TestCase):
    def test_lease_ttl_outlives_provider_timeout(self):
        args = SimpleNamespace(provider_timeout=990, lease_ttl_seconds=None)
        self.assertEqual(_lease_ttl(args), 1290)
        with self.assertRaises(SystemExit):
            _lease_ttl(SimpleNamespace(provider_timeout=990, lease_ttl_seconds=990))

    def test_atomic_json_replaces_without_temp_residue(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.json"
            _write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual(list(Path(td).glob("*.tmp")), [])

    def test_atomic_json_retries_transient_windows_replace_lock(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.json"
            real_replace = os.replace
            calls = {"count": 0}

            def flaky_replace(src, dst):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise PermissionError(32, "transient sharing violation")
                return real_replace(src, dst)

            with patch("hermes_factory.controller.os.replace", side_effect=flaky_replace):
                _write_json(path, {"a": 2})
            self.assertEqual(calls["count"], 2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 2})

    def test_terminal_json_parser_ignores_prior_braces(self):
        value = _last_json_object('log {not json}\nmore\n{"run_id":"R","ok":true}\n')
        self.assertEqual(value["run_id"], "R")
        self.assertTrue(value["ok"])

    def test_requested_poststage_failure_downgrades_status(self):
        self.assertEqual(
            _appliance_status("FRONTIER_REVIEW_READY", [{"stage": "09D", "error": "boom"}]),
            "NOT_READY",
        )
        self.assertEqual(_appliance_status("READY_FOR_PROVIDER", []), "READY_FOR_PROVIDER")


if __name__ == "__main__":
    unittest.main()


class _NeverCalledProvider:
    def __init__(self, role: str):
        self.role = role
        self.calls = 0

    def identity(self):
        return WorkerIdentity("TEST", self.role.lower(), self.role, "v1", self.role)

    def capabilities(self):
        return {"network_required": False}

    def is_empirical_semantic_provider(self):
        return True

    def execute(self, request):
        self.calls += 1
        raise AssertionError("provider must not run before failed 09D contract")


class PredispatchTests(unittest.TestCase):
    def test_invalid_09d_contract_blocks_before_provider_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_pdf = root / "source.bin"
            source_pdf.write_bytes(b"source-bytes")
            source_sha = sha256_file(source_pdf)
            content = "Source-grounded statement."
            unit = SourceUnit("U", "S", "V", source_sha, "PARAGRAPH", "TEXT", {}, sha256_text(content), content)
            source_units = root / "source.jsonl"
            source_units.write_text(json.dumps(unit.to_dict()) + "\n", encoding="utf-8")
            bad_db = root / "bad.sqlite"
            sqlite3.connect(bad_db).close()
            primary = _NeverCalledProvider("PRIMARY")
            blind = _NeverCalledProvider("BLIND_RECALL")
            with patch("hermes_factory.controller.write_current_manifest", return_value={}), \
                 patch("hermes_factory.controller.verify_build", return_value={"result": "PASS", "errors": []}), \
                 patch("hermes_factory.controller.verify_runtime_lock", return_value={"result": "PASS", "errors": []}), \
                 patch("hermes_factory.controller.load_registry", return_value={}), \
                 patch("hermes_factory.controller.resolve_runtime_topology", return_value={
                     "PRIMARY": {"independence_group": "P"},
                     "BLIND_RECALL": {"independence_group": "B"},
                 }):
                with self.assertRaisesRegex(RuntimeError, "09D_SEALED_SCHEMA_CONTRACT"):
                    run_factory(
                        project_root=root,
                        source_units_path=source_units,
                        primary_provider=primary,
                        blind_provider=blind,
                        output_root=root / "out",
                        source_pdf=source_pdf,
                        source_expected_sha256=source_sha,
                        database_09d=bad_db,
                        mode="EXTERNAL_COMMAND",
                        execution_mode="HYBRID",
                    )
            self.assertEqual(primary.calls, 0)
            self.assertEqual(blind.calls, 0)
