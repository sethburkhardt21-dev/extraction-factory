from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Dict


def open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    path = Path(path).resolve()
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def inventory_schema_readonly(path: Path) -> Dict[str, Any]:
    conn = open_readonly_sqlite(path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        schema = {}
        for table in tables:
            safe = table.replace('"', '""')
            schema[table] = [dict(r) for r in conn.execute(f'PRAGMA table_info("{safe}")')]
        return {"database": str(Path(path)), "mode": "READ_ONLY", "tables": tables, "schema": schema}
    finally:
        conn.close()


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
