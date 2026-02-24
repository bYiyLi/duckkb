from __future__ import annotations

from duckkb.infrastructure.persistence.duckdb.connection import connect


def execute_readonly(db_path: str, sql: str) -> tuple[list[str], list[list[object]]]:
    with connect(db_path, read_only=True) as conn:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
    return columns, rows
