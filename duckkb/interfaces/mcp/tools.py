from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from duckkb.application.usecases.get_schema import get_schema_info as get_schema_usecase
from duckkb.application.usecases.query_sql import query_raw_sql as query_usecase
from duckkb.application.usecases.smart_search import (
    smart_search as smart_search_usecase,
)
from duckkb.application.usecases.sync_kb import sync_knowledge_base as sync_usecase
from duckkb.application.usecases.validate_and_import import (
    validate_and_import as validate_usecase,
)
from duckkb.domain.errors import DuckKBError
from duckkb.infrastructure.embedding.provider_hash import HashEmbeddingProvider
from duckkb.infrastructure.filesystem.import_repo import FilesystemImportRepo
from duckkb.infrastructure.filesystem.kb_env import resolve_kb_path
from duckkb.infrastructure.persistence.duckdb.query import execute_readonly
from duckkb.infrastructure.persistence.duckdb.repos import (
    DuckDBCacheRepo,
    DuckDBSearchIndexRepo,
)
from duckkb.infrastructure.persistence.duckdb.schema import DuckDBSchemaRepo
from duckkb.infrastructure.persistence.duckdb.sql_guard import guard_select_only
from duckkb.types import ErrorEnvelope, SearchItem, SearchResponse, SyncResult


def sync_knowledge_base(kb_path: str | None = None) -> dict[str, Any]:
    try:
        kb = _resolve_kb_path(kb_path)
        schema_repo = DuckDBSchemaRepo(_db_path(kb), kb.schema_file)
        schema_repo.ensure_schema()
        import_repo = FilesystemImportRepo(kb.root)
        index_repo = DuckDBSearchIndexRepo(_db_path(kb))
        cache_repo = DuckDBCacheRepo(_db_path(kb))
        provider = HashEmbeddingProvider()
        synced = sync_usecase(
            import_repo,
            index_repo,
            cache_repo,
            provider,
            manifest_path=str(Path(kb.build_dir) / "sync_manifest.json"),
        )
        return asdict(
            SyncResult(synced=synced, affected_tables=["_sys_search", "_sys_cache"])
        )
    except DuckKBError as exc:
        return asdict(_error_envelope(exc))


def get_schema_info(kb_path: str | None = None) -> dict[str, Any]:
    try:
        kb = _resolve_kb_path(kb_path)
        schema_repo = DuckDBSchemaRepo(_db_path(kb), kb.schema_file)
        info = get_schema_usecase(schema_repo)
        return asdict(info)
    except DuckKBError as exc:
        return asdict(_error_envelope(exc))


def smart_search(kb_path: str | None, query: str, limit: int = 10) -> dict[str, Any]:
    try:
        kb = _resolve_kb_path(kb_path)
        schema_repo = DuckDBSchemaRepo(_db_path(kb), kb.schema_file)
        schema_repo.ensure_schema()
        index_repo = DuckDBSearchIndexRepo(_db_path(kb))
        cache_repo = DuckDBCacheRepo(_db_path(kb))
        provider = HashEmbeddingProvider()
        hits = smart_search_usecase(
            index_repo, cache_repo, provider, query=query, limit=limit
        )
        response = SearchResponse(
            items=[_to_search_item(hit) for hit in hits], truncated=False
        )
        return asdict(response)
    except DuckKBError as exc:
        return asdict(_error_envelope(exc))


def query_raw_sql(kb_path: str | None, sql: str) -> dict[str, Any]:
    try:
        kb = _resolve_kb_path(kb_path)
        schema_repo = DuckDBSchemaRepo(_db_path(kb), kb.schema_file)
        schema_repo.ensure_schema()
        result = query_usecase(
            sql=sql,
            guard=lambda statement: guard_select_only(statement, default_limit=1000),
            executor=lambda statement: execute_readonly(_db_path(kb), statement),
            max_bytes=2_000_000,
        )
        return asdict(result)
    except DuckKBError as exc:
        return asdict(_error_envelope(exc))


def validate_and_import(
    kb_path: str | None, table_name: str, lines: list[str]
) -> dict[str, Any]:
    try:
        kb = _resolve_kb_path(kb_path)
        import_repo = FilesystemImportRepo(kb.root)
        result = validate_usecase(import_repo, table_name=table_name, lines=lines)
        return asdict(result)
    except DuckKBError as exc:
        return asdict(_error_envelope(exc))


def _resolve_kb_path(kb_path: str | None):
    root = kb_path or os.environ.get("DUCKKB_KB_PATH")
    if not root:
        raise DuckKBError(
            code="missing_kb_path", message="KB_PATH 不能为空", details={}
        )
    return resolve_kb_path(root)


def _db_path(kb) -> str:
    build_dir = Path(kb.build_dir)
    return str(build_dir / "knowledge.db")


def _error_envelope(exc: DuckKBError) -> ErrorEnvelope:
    return ErrorEnvelope(code=exc.code, message=exc.message, details=exc.details)


def _to_search_item(hit) -> SearchItem:
    return SearchItem(
        ref_id=hit.ref_id,
        source_table=hit.source_table,
        source_field=hit.source_field,
        segmented_text=hit.segmented_text,
        metadata=hit.metadata,
        priority_weight=hit.priority_weight,
        score=hit.score,
    )
