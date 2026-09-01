from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict


def open_readonly_sqlite(path: Path, *, immutable: bool = True) -> sqlite3.Connection:
    """Open a SQLite database through a fail-closed read-only URI.

    09D release databases are sealed artifacts. ``immutable=1`` prevents SQLite
    from attempting journal/WAL interaction and makes accidental write intent
    even less useful. Callers can disable it only for synthetic tests or an
    explicitly non-sealed inspection target.
    """
    path = Path(path).resolve()
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    uri = f"file:{path.as_posix()}{suffix}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    """Measure Motion-1/Motion-2 carrier partition without mutating 09D.

    This is also a cycle-safety primitive for comparison. New extraction runs
    should compare against the inherited Motion-1 authority lane by default,
    not against prior Motion-2 extraction rows that could recursively validate
    later model output.
    """
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
        required = {"source_assertion_candidate", "ingest_source_locator"}
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
