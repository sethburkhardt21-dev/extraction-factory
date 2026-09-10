from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote

from .hashing import sha256_file, sha256_json


R3_TARGET: Dict[str, Any] = {
    "schema_version": "09d-r3-sealed-contract-1.0",
    "target_name": "Project_09D_Milestone_A_v2/r3/final_s03.sqlite",
    "expected_db_sha256": "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3",
    "expected_bytes": 1760145408,
    "expected_counts": {
        "source_assertion_candidate": 71824,
        "motion_1": 71824,
        "motion_2": 0,
        "ingest_source_locator": 0,
        "assertion": 71824,
        "candidate_registry": 2233,
        "candidate_promotion_event": 0,
    },
    "required_tables": {
        "source_assertion_candidate": {
            "candidate_id",
            "subject_entity_id",
            "predicate_code",
            "value_text",
            "fact_family",
            "source_resource_id",
            "ingest_locator_id",
            "parent_assertion_id",
            "source_locator_id",
            "raw_cell_id",
            "carried_status",
            "carried_confidence_basis",
            "carried_source_era",
        },
        "entity_name": {"canonical_id", "name_text", "normalized_name", "is_searchable"},
        "ingest_source_locator": set(),
        "assertion": set(),
        "candidate_registry": {
            "candidate_id",
            "domain",
            "source_table",
            "source_key",
            "source_identity_sha256",
            "origin_package_id",
            "state",
            "legacy_entity_id",
        },
        "candidate_promotion_event": set(),
    },
    "witness_constraint": "source_assertion_candidate_witness_by_kind",
    "motion_2_required_null_columns": [
        "parent_assertion_id",
        "source_locator_id",
        "raw_cell_id",
        "carried_status",
        "carried_confidence_basis",
        "carried_source_era",
    ],
    "claim_boundary": (
        "This contract identifies the sealed r3 comparator target and verifies the Motion-1/Motion-2 "
        "witness boundary. It authorizes read-only comparison only. It does not authorize insertion, "
        "candidate promotion, canonicalization, automatic selection, generation, or release."
    ),
}


def _json_safe_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(contract)
    out["required_tables"] = {name: sorted(columns) for name, columns in contract["required_tables"].items()}
    return out

def _sqlite_uri(path: Path) -> str:
    resolved = Path(path).resolve().as_posix()
    return f"file:{quote(resolved, safe='/:')}?mode=ro&immutable=1"


def open_immutable_readonly(path: Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(_sqlite_uri(path), uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _file_snapshot(path: Path) -> Dict[str, int]:
    st = os.stat(path)
    return {
        "st_dev": int(getattr(st, "st_dev", 0)),
        "st_ino": int(getattr(st, "st_ino", 0)),
        "st_size": int(st.st_size),
        "st_mtime_ns": int(st.st_mtime_ns),
    }


def _normalized_sql(sql: str | None) -> str:
    return re.sub(r"\s+", " ", sql or "").strip().lower()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    safe = table.replace('"', '""')
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_xinfo("{safe}")')}


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    safe = table.replace('"', '""')
    return int(conn.execute(f'SELECT count(*) FROM "{safe}"').fetchone()[0])


def _write_is_blocked(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE TABLE __factory_forbidden_09d_write(x INTEGER)")
    except sqlite3.Error:
        return True
    return False


def verify_09d_contract(
    path: Path,
    *,
    verify_identity: bool = True,
    strict_counts: bool = True,
    quick_check: bool = False,
    contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Verify the read-only 09D target before it can influence a factory run.

    ``verify_identity`` performs the expensive whole-file SHA-256 and byte-size pin.
    ``strict_counts`` closes the sealed-r3 role boundary, including Motion-2 == 0.
    Tests may disable those two target-specific checks while still exercising the
    structural/witness contract against a small synthetic database.
    """
    contract = contract or R3_TARGET
    path = Path(path).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    observed: Dict[str, Any] = {"database_path": str(path)}

    if not path.is_file():
        return {
            "ok": False,
            "result": "FAIL_BLOCKING",
            "errors": ["09d_database_missing"],
            "warnings": [],
            "observed": observed,
            "contract": _json_safe_contract(contract),
            "target_identity_verified": False,
        }

    before = _file_snapshot(path)
    observed["file_snapshot_before"] = before
    if verify_identity:
        measured = sha256_file(path)
        observed["database_sha256"] = measured
        observed["database_bytes"] = before["st_size"]
        if measured != contract["expected_db_sha256"]:
            errors.append("09d_database_sha256_mismatch")
        if before["st_size"] != int(contract["expected_bytes"]):
            errors.append("09d_database_size_mismatch")
    else:
        observed["database_sha256"] = "NOT_MEASURED"
        observed["database_bytes"] = before["st_size"]
        warnings.append("09d_target_identity_not_cryptographically_verified")

    conn = None
    try:
        conn = open_immutable_readonly(path)
        query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
        observed["query_only"] = query_only
        if query_only != 1:
            errors.append("09d_query_only_not_enforced")
        if not _write_is_blocked(conn):
            errors.append("09d_write_mutation_not_blocked")

        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        observed["required_table_presence"] = {}
        for table, required_columns in contract["required_tables"].items():
            present = table in tables
            observed["required_table_presence"][table] = present
            if not present:
                errors.append(f"09d_required_table_missing:{table}")
                continue
            columns = _table_columns(conn, table)
            missing = sorted(set(required_columns) - columns)
            if missing:
                errors.append(f"09d_required_columns_missing:{table}:{','.join(missing)}")

        carrier_sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_assertion_candidate'"
        ).fetchone()
        carrier_sql = _normalized_sql(carrier_sql_row[0] if carrier_sql_row else None)
        observed["carrier_schema_sha256"] = sha256_json({"sql": carrier_sql}) if carrier_sql else None
        constraint_name = str(contract["witness_constraint"]).lower()
        if constraint_name not in carrier_sql:
            errors.append("09d_motion2_witness_constraint_missing")

        required_constraint_fragments = [
            "source_resource_id is not null and ingest_locator_id is null",
            "source_resource_id is null",
            "ingest_locator_id is not null",
        ] + [f"{col} is null" for col in contract["motion_2_required_null_columns"]]
        for fragment in required_constraint_fragments:
            if fragment not in carrier_sql:
                errors.append(f"09d_motion2_witness_constraint_fragment_missing:{fragment}")

        if "source_assertion_candidate" in tables:
            total = _table_count(conn, "source_assertion_candidate")
            motion_1 = int(conn.execute(
                "SELECT count(*) FROM source_assertion_candidate "
                "WHERE source_resource_id IS NOT NULL AND ingest_locator_id IS NULL"
            ).fetchone()[0])
            null_terms = " AND ".join(f"{c} IS NULL" for c in contract["motion_2_required_null_columns"])
            motion_2 = int(conn.execute(
                "SELECT count(*) FROM source_assertion_candidate "
                f"WHERE source_resource_id IS NULL AND ingest_locator_id IS NOT NULL AND {null_terms}"
            ).fetchone()[0])
            invalid_witness = total - motion_1 - motion_2
            observed["carrier_counts"] = {
                "total": total,
                "motion_1": motion_1,
                "motion_2": motion_2,
                "invalid_or_other_witness": invalid_witness,
            }
            if invalid_witness != 0:
                errors.append(f"09d_carrier_witness_partition_invalid:{invalid_witness}")

            contaminated_motion_2 = int(conn.execute(
                "SELECT count(*) FROM source_assertion_candidate WHERE ingest_locator_id IS NOT NULL AND ("
                + " OR ".join(f"{c} IS NOT NULL" for c in contract["motion_2_required_null_columns"])
                + ")"
            ).fetchone()[0])
            observed["motion_2_forbidden_payload_rows"] = contaminated_motion_2
            if contaminated_motion_2:
                errors.append(f"09d_motion2_forbidden_payload_rows:{contaminated_motion_2}")

        counts: Dict[str, int] = {}
        for table in ("ingest_source_locator", "assertion", "candidate_registry", "candidate_promotion_event"):
            if table in tables:
                counts[table] = _table_count(conn, table)
        observed["selected_table_counts"] = counts

        if strict_counts:
            expected = contract["expected_counts"]
            carrier_counts = observed.get("carrier_counts", {})
            checks = {
                "source_assertion_candidate": carrier_counts.get("total"),
                "motion_1": carrier_counts.get("motion_1"),
                "motion_2": carrier_counts.get("motion_2"),
                "ingest_source_locator": counts.get("ingest_source_locator"),
                "assertion": counts.get("assertion"),
                "candidate_registry": counts.get("candidate_registry"),
                "candidate_promotion_event": counts.get("candidate_promotion_event"),
            }
            for name, expected_value in expected.items():
                actual_value = checks.get(name)
                if actual_value != expected_value:
                    errors.append(f"09d_sealed_count_mismatch:{name}:expected={expected_value}:actual={actual_value}")

        if quick_check:
            row = conn.execute("PRAGMA quick_check").fetchone()
            quick = str(row[0]) if row else "NO_RESULT"
            observed["quick_check"] = quick
            if quick.lower() != "ok":
                errors.append(f"09d_quick_check_failed:{quick}")
        else:
            observed["quick_check"] = "NOT_RUN"
    except sqlite3.Error as exc:
        errors.append(f"09d_sqlite_contract_error:{type(exc).__name__}:{exc}")
    finally:
        if conn is not None:
            conn.close()

    after = _file_snapshot(path)
    observed["file_snapshot_after"] = after
    if before != after:
        errors.append("09d_database_changed_during_verification")

    target_identity_verified = bool(
        verify_identity
        and observed.get("database_sha256") == contract["expected_db_sha256"]
        and observed.get("database_bytes") == contract["expected_bytes"]
    )
    result = "PASS" if not errors else "FAIL_BLOCKING"
    return {
        "ok": not errors,
        "result": result,
        "errors": errors,
        "warnings": warnings,
        "observed": observed,
        "contract": _json_safe_contract(contract),
        "target_identity_verified": target_identity_verified,
        "read_only_comparison_allowed": not errors,
        "write_allowed": False,
        "automatic_promotion_allowed": False,
        "automatic_canonicalization_allowed": False,
        "automatic_selection_allowed": False,
    }
