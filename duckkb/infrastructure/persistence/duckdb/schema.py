from __future__ import annotations

import re
from pathlib import Path

from duckkb.domain.ports.repository import SchemaRepo
from duckkb.infrastructure.persistence.duckdb.connection import connect

SYS_SEARCH_DDL = """
CREATE TABLE IF NOT EXISTS _sys_search (
    ref_id VARCHAR,
    source_table VARCHAR,
    source_field VARCHAR,
    chunk_id INTEGER,
    segmented_text TEXT,
    content_hash VARCHAR,
    metadata JSON,
    priority_weight DOUBLE,
    PRIMARY KEY (ref_id, source_table, source_field, chunk_id)
);
"""

SYS_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS _sys_cache (
    content_hash VARCHAR PRIMARY KEY,
    embedding DOUBLE[],
    created_at TIMESTAMP,
    last_used TIMESTAMP
);
"""


class DuckDBSchemaRepo(SchemaRepo):
    def __init__(self, db_path: str, schema_file: str) -> None:
        self._db_path = db_path
        self._schema_file = schema_file

    def load_schema_sql(self) -> str:
        path = Path(self._schema_file)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def ensure_schema(self) -> None:
        with connect(self._db_path, read_only=False) as conn:
            schema_sql = self.load_schema_sql()
            if schema_sql.strip():
                for statement in _split_statements(schema_sql):
                    conn.execute(statement)
            conn.execute(SYS_SEARCH_DDL)
            conn.execute(SYS_CACHE_DDL)

    def get_er_mermaid(self) -> str:
        schema_sql = self.load_schema_sql()
        tables, relations = _parse_schema(schema_sql)
        lines = ["erDiagram"]
        for table in sorted(tables):
            lines.append(f"  {table} {{")
            lines.append("  }")
        lines.append("  _sys_search {")
        lines.append("  }")
        lines.append("  _sys_cache {")
        lines.append("  }")
        lines.append("  _sys_search ||--o{ _sys_cache : uses")
        for left, right, label in relations:
            lines.append(f"  {left} ||--o{{ {right} : {label}")
        return "\n".join(lines) + "\n"


def _parse_schema(schema_sql: str) -> tuple[set[str], list[tuple[str, str, str]]]:
    tables = set()
    relations: list[tuple[str, str, str]] = []
    if not schema_sql.strip():
        return tables, relations
    create_table = re.compile(r"create\s+table\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
    fk_ref = re.compile(
        r"foreign\s+key\s*\([^)]+\)\s*references\s+([a-zA-Z_][\w]*)",
        re.IGNORECASE,
    )
    for match in create_table.finditer(schema_sql):
        tables.add(match.group(1))
    for match in fk_ref.finditer(schema_sql):
        target = match.group(1)
        if target in tables:
            relations.append(("_sys_search", target, "references"))
    return tables, relations


def _split_statements(schema_sql: str) -> list[str]:
    statements: list[str] = []
    for chunk in schema_sql.split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements
