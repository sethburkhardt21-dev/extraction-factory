from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

MOTION2_TARGET_TABLES = ("ingest_source_locator", "source_assertion_candidate")


def open_readonly_sqlite(path: Path, *, immutable: bool = True) -> sqlite3.Connection:
    """Open a SQLite database through a fail-closed read-only URI."""
    path = Path(path).resolve()
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    uri = f"file:{path.as_posix()}{suffix}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def table_columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    safe = _quote_identifier(table)
    return [dict(r) for r in conn.execute(f"PRAGMA table_info({safe})")]


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    """Stable hash of user-visible schema objects, independent of row content."""
    rows = [
        tuple(r)
        for r in conn.execute(
            "SELECT type, name, tbl_name, COALESCE(sql,'') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
    ]
    return _stable_sha256(rows)


def _table_contract(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """Return a focused, deterministic contract for one 09D target table."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None
    if not exists:
        return {"table": table, "present": False}

    table_row = conn.execute(
        "SELECT COALESCE(sql,'') AS sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    columns = table_columns(conn, table)
    safe = _quote_identifier(table)
    foreign_keys = [dict(r) for r in conn.execute(f"PRAGMA foreign_key_list({safe})")]

    indexes = []
    for row in conn.execute(f"PRAGMA index_list({safe})"):
        item = dict(row)
        index_name = str(item.get("name") or "")
        if index_name:
            quoted_index = _quote_identifier(index_name)
            item["columns"] = [dict(x) for x in conn.execute(f"PRAGMA index_info({quoted_index})")]
            sql_row = conn.execute(
                "SELECT COALESCE(sql,'') AS sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
            ).fetchone()
            item["sql"] = str(sql_row["sql"] if sql_row else "")
        indexes.append(item)

    triggers = [
        {"name": str(r["name"]), "sql": str(r["sql"] or "")}
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name", (table,)
        )
    ]
    base = {
        "table": table,
        "present": True,
        "create_sql": str(table_row["sql"] if table_row else ""),
        "columns": columns,
        "foreign_keys": foreign_keys,
        "indexes": indexes,
        "triggers": triggers,
    }
    base["table_contract_sha256"] = _stable_sha256(base)
    return base


def motion2_target_contract_readonly(path: Path) -> Dict[str, Any]:
    """Fingerprint only the 09D structures the future Motion-2 loader targets.

    This is intentionally separate from the whole-database schema fingerprint.
    A future 09D release may change unrelated tables while preserving the exact
    Motion-2 intake contract, or may alter this contract while the rest of the
    database remains mostly unchanged. This receipt distinguishes those cases
    without weakening full database hash verification.
    """
    conn = open_readonly_sqlite(path)
    try:
        contracts = {table: _table_contract(conn, table) for table in MOTION2_TARGET_TABLES}
        whole_schema = schema_fingerprint(conn)
    finally:
        conn.close()

    core = {
        "contract_schema_version": "09d-motion2-target-contract-1.0",
        "mode": "READ_ONLY_IMMUTABLE",
        "target_tables": list(MOTION2_TARGET_TABLES),
        "tables": contracts,
    }
    return {
        **core,
        "motion2_target_contract_sha256": _stable_sha256(core),
        "whole_database_schema_fingerprint_sha256": whole_schema,
        "direct_insert_allowed": False,
        "automatic_schema_migration_allowed": False,
    }


def inventory_schema_readonly(path: Path) -> Dict[str, Any]:
    conn = open_readonly_sqlite(path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
        schema = {table: table_columns(conn, table) for table in tables}
        return {
            "database": str(Path(path)),
            "mode": "READ_ONLY_IMMUTABLE",
            "tables": tables,
            "views": views,
            "schema": schema,
            "schema_fingerprint_sha256": schema_fingerprint(conn),
        }
    finally:
        conn.close()


def carrier_witness_partition_readonly(path: Path) -> Dict[str, Any]:
    """Measure Motion-1/Motion-2 carrier partition without mutating 09D."""
    conn = open_readonly_sqlite(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "source_assertion_candidate" not in tables:
            return {
                "available": False,
                "reason": "source_assertion_candidate_missing",
                "carrier_rows": None,
                "motion1_rows": None,
                "motion2_rows": None,
                "invalid_witness_rows": None,
                "partition_valid": False,
            }
        columns = {r["name"] for r in table_columns(conn, "source_assertion_candidate")}
        needed = {"source_resource_id", "ingest_locator_id"}
        if not needed.issubset(columns):
            return {
                "available": False,
                "reason": "witness_columns_missing",
                "missing_columns": sorted(needed - columns),
                "carrier_rows": None,
                "motion1_rows": None,
                "motion2_rows": None,
                "invalid_witness_rows": None,
                "partition_valid": False,
            }
        row = conn.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN source_resource_id IS NOT NULL AND ingest_locator_id IS NULL THEN 1 ELSE 0 END) AS motion1, "
            "SUM(CASE WHEN source_resource_id IS NULL AND ingest_locator_id IS NOT NULL THEN 1 ELSE 0 END) AS motion2, "
            "SUM(CASE WHEN NOT ((source_resource_id IS NOT NULL AND ingest_locator_id IS NULL) "
            "OR (source_resource_id IS NULL AND ingest_locator_id IS NOT NULL)) THEN 1 ELSE 0 END) AS invalid "
            "FROM source_assertion_candidate"
        ).fetchone()
        total = int(row["total"] or 0)
        motion1 = int(row["motion1"] or 0)
        motion2 = int(row["motion2"] or 0)
        invalid = int(row["invalid"] or 0)
        return {
            "available": True,
            "carrier_rows": total,
            "motion1_rows": motion1,
            "motion2_rows": motion2,
            "invalid_witness_rows": invalid,
            "partition_valid": invalid == 0 and motion1 + motion2 == total,
            "comparison_authority_default": "MOTION1_AUTHORITY",
            "cycle_safety_reason": (
                "Motion-1 is inherited/source-witnessed authority; Motion-2 rows are extraction intake and are excluded "
                "from default comparison to prevent recursive model-output support."
            ),
        }
    finally:
        conn.close()


def motion2_capability_readonly(path: Path) -> Dict[str, Any]:
    """Inspect the 09D Motion-2 intake surface without mutating it."""
    conn = open_readonly_sqlite(path)
    try:
        table_names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = set(MOTION2_TARGET_TABLES)
        missing = sorted(required - table_names)
        carrier_sql = ""
        if "source_assertion_candidate" in table_names:
            row = conn.execute(
                "SELECT COALESCE(sql,'') FROM sqlite_master WHERE type='table' AND name='source_assertion_candidate'"
            ).fetchone()
            carrier_sql = str(row[0] if row else "")
        carrier_columns = (
            {r["name"] for r in table_columns(conn, "source_assertion_candidate")}
            if "source_assertion_candidate" in table_names else set()
        )
        locator_columns = (
            {r["name"] for r in table_columns(conn, "ingest_source_locator")}
            if "ingest_source_locator" in table_names else set()
        )
        motion2_witness_columns = {
            "ingest_locator_id", "source_resource_id", "parent_assertion_id",
            "source_locator_id", "raw_cell_id",
        }
        witness_columns_present = motion2_witness_columns.issubset(carrier_columns)
        witness_constraint_present = (
            "source_assertion_candidate_witness_by_kind" in carrier_sql
            and "ingest_locator_id IS NOT NULL" in carrier_sql
        )
        locator_rows = None
        if "ingest_source_locator" in table_names:
            locator_rows = int(conn.execute("SELECT COUNT(*) FROM ingest_source_locator").fetchone()[0])
        fingerprint = schema_fingerprint(conn)
    finally:
        conn.close()

    partition = carrier_witness_partition_readonly(path)
    target_contract = motion2_target_contract_readonly(path)
    return {
        "mode": "READ_ONLY_IMMUTABLE",
        "required_tables_present": not missing,
        "missing_required_tables": missing,
        "carrier_columns": sorted(carrier_columns),
        "locator_columns": sorted(locator_columns),
        "motion2_witness_columns_present": witness_columns_present,
        "motion2_witness_constraint_present": witness_constraint_present,
        "carrier_rows": partition.get("carrier_rows"),
        "motion1_carrier_rows": partition.get("motion1_rows"),
        "motion2_carrier_rows": partition.get("motion2_rows"),
        "carrier_invalid_witness_rows": partition.get("invalid_witness_rows"),
        "carrier_partition_valid": partition.get("partition_valid"),
        "ingest_source_locator_rows": locator_rows,
        "schema_fingerprint_sha256": fingerprint,
        "motion2_target_contract_sha256": target_contract.get("motion2_target_contract_sha256"),
        "comparison_authority_default": "MOTION1_AUTHORITY",
        "direct_insert_allowed": False,
        "automatic_identity_merge_allowed": False,
    }


def assert_write_blocked(path: Path) -> bool:
    conn = open_readonly_sqlite(path)
    try:
        try:
            conn.execute("CREATE TABLE __hermes_forbidden_write(x INTEGER)")
        except sqlite3.OperationalError:
            return True
        return False
    finally:
        conn.close()
