from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


def connect(database_path: str, read_only: bool) -> duckdb.DuckDBPyConnection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path), read_only=read_only)
    _apply_defaults(conn)
    return conn


def _apply_defaults(conn: duckdb.DuckDBPyConnection) -> None:
    settings: dict[str, Any] = {
        "threads": 4,
        "memory_limit": "1GB",
    }
    for key, value in settings.items():
        conn.execute(f"PRAGMA {key}='{value}'")
