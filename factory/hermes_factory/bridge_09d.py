from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict

from .contract_09d import R3_TARGET, open_immutable_readonly


FOCUSED_TABLES = tuple(R3_TARGET["required_tables"].keys())


def open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    """Compatibility alias for the immutable read-only 09D opener."""
    return open_immutable_readonly(path)


def _schema_sha256(sql: str | None) -> str | None:
    if sql is None:
        return None
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def inventory_schema_readonly(path: Path) -> Dict[str, Any]:
    """Return a compact schema-relevant inventory.

    ``focused_schema`` carries detailed metadata only for objects the bridge
    depends on. ``tables`` remains as a lightweight name/hash index for backward
    compatibility; it intentionally does not copy hundreds of full CREATE
    statements or column lists into every run artifact.
    """
    conn = open_readonly_sqlite(path)
    try:
        table_rows = list(conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"))
        table_index = {
            str(row[0]): {"schema_sha256": _schema_sha256(row[1])}
            for row in table_rows
        }
        object_counts = {
            kind: int(conn.execute("SELECT count(*) FROM sqlite_master WHERE type=?", (kind,)).fetchone()[0])
            for kind in ("table", "view", "index", "trigger")
        }
        focused: Dict[str, Any] = {}
        for table in FOCUSED_TABLES:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if row is None:
                focused[table] = {"present": False}
                continue
            safe = table.replace('"', '""')
            columns = [dict(r) for r in conn.execute(f'PRAGMA table_xinfo("{safe}")')]
            foreign_keys = [dict(r) for r in conn.execute(f'PRAGMA foreign_key_list("{safe}")')]
            indexes = [dict(r) for r in conn.execute(f'PRAGMA index_list("{safe}")')]
            focused[table] = {
                "present": True,
                "schema_sha256": _schema_sha256(row[0]),
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indexes": indexes,
            }
        return {
            "database": str(Path(path).resolve()),
            "mode": "READ_ONLY_IMMUTABLE",
            "query_only": int(conn.execute("PRAGMA query_only").fetchone()[0]),
            "sqlite_version": sqlite3.sqlite_version,
            "object_counts": object_counts,
            "tables": table_index,
            "focused_schema": focused,
            "claim_boundary": (
                "Focused structural inventory only. No mutation, promotion, canonicalization, "
                "selection, or release authority is implied."
            ),
        }
    finally:
        conn.close()


def assert_write_blocked(path: Path) -> bool:
    conn = open_readonly_sqlite(path)
    try:
        try:
            conn.execute("CREATE TABLE __hermes_forbidden_write(x INTEGER)")
        except sqlite3.Error:
            return True
        return False
    finally:
        conn.close()
