from __future__ import annotations

from duckkb.domain.ports.repository import SchemaRepo
from duckkb.types import SchemaInfo


def get_schema_info(schema_repo: SchemaRepo) -> SchemaInfo:
    schema_sql = schema_repo.load_schema_sql()
    er_mermaid = schema_repo.get_er_mermaid()
    return SchemaInfo(schema_sql=schema_sql, er_mermaid=er_mermaid)
