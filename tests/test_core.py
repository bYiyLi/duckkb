from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from duckkb.application.usecases.query_sql import query_raw_sql
from duckkb.application.usecases.smart_search import smart_search
from duckkb.application.usecases.sync_kb import sync_knowledge_base
from duckkb.application.usecases.validate_and_import import validate_and_import
from duckkb.domain.errors import DomainError
from duckkb.infrastructure.embedding.provider_hash import HashEmbeddingProvider
from duckkb.infrastructure.filesystem.fs_atomic import (
    read_jsonl_lines,
    write_jsonl_atomic,
)
from duckkb.infrastructure.filesystem.import_repo import FilesystemImportRepo
from duckkb.infrastructure.filesystem.kb_env import resolve_kb_path, safe_join
from duckkb.infrastructure.persistence.duckdb.repos import (
    DuckDBCacheRepo,
    DuckDBSearchIndexRepo,
)
from duckkb.infrastructure.persistence.duckdb.schema import DuckDBSchemaRepo
from duckkb.infrastructure.persistence.duckdb.sql_guard import guard_select_only


class CoreTests(unittest.TestCase):
    def test_kb_env_safe_join(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = resolve_kb_path(temp_dir)
            safe_path = safe_join(root.root, "data")
            self.assertTrue(str(safe_path).startswith(root.root))
            with self.assertRaises(DomainError):
                safe_join(root.root, "..", "escape")

    def test_fs_atomic_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "data.jsonl"
            lines = ['{"id":"1","content":"hello"}', '{"id":"2","content":"world"}']
            write_jsonl_atomic(str(file_path), lines)
            loaded = read_jsonl_lines(str(file_path))
            self.assertEqual(lines, loaded)

    def test_sql_guard_limit(self) -> None:
        sql = "SELECT * FROM _sys_search"
        guarded = guard_select_only(sql, default_limit=1000)
        self.assertIn("LIMIT 1000", guarded.upper())

    def test_validate_and_import_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            kb = resolve_kb_path(temp_dir)
            repo = FilesystemImportRepo(kb.root)
            result = validate_and_import(repo, "items", ['{"id": 1}'])
            self.assertEqual(0, result.accepted)
            self.assertTrue(result.errors)
            self.assertEqual("missing_id", result.errors[0].code)

    def test_sync_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            kb = resolve_kb_path(temp_dir)
            schema_repo = DuckDBSchemaRepo(
                str(Path(kb.build_dir) / "knowledge.db"), kb.schema_file
            )
            schema_repo.ensure_schema()
            repo = FilesystemImportRepo(kb.root)
            payload = {"id": "a1", "content": "hello duck", "priority_weight": 1.0}
            repo.write_table_jsonl("items", [json.dumps(payload, ensure_ascii=False)])
            index_repo = DuckDBSearchIndexRepo(str(Path(kb.build_dir) / "knowledge.db"))
            cache_repo = DuckDBCacheRepo(str(Path(kb.build_dir) / "knowledge.db"))
            sync_knowledge_base(
                repo,
                index_repo,
                cache_repo,
                HashEmbeddingProvider(),
                manifest_path=str(Path(kb.build_dir) / "sync_manifest.json"),
            )
            hits = smart_search(
                index_repo, cache_repo, HashEmbeddingProvider(), query="duck", limit=5
            )
            self.assertTrue(hits)
            second = sync_knowledge_base(
                repo,
                index_repo,
                cache_repo,
                HashEmbeddingProvider(),
                manifest_path=str(Path(kb.build_dir) / "sync_manifest.json"),
            )
            self.assertEqual(0, second)

    def test_query_usecase_truncation(self) -> None:
        def executor(statement: str):
            return ["a"], [[i] for i in range(10)]

        def guard(statement: str) -> str:
            return statement

        result = query_raw_sql("select 1", guard=guard, executor=executor, max_bytes=10)
        self.assertTrue(result.truncated)

    def test_schema_mermaid_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            kb = resolve_kb_path(temp_dir)
            schema_path = Path(kb.schema_file)
            schema_path.write_text(
                "CREATE TABLE items(id VARCHAR PRIMARY KEY);",
                encoding="utf-8",
            )
            repo = DuckDBSchemaRepo(
                str(Path(kb.build_dir) / "knowledge.db"), kb.schema_file
            )
            mermaid = repo.get_er_mermaid()
            self.assertIn("items", mermaid)


if __name__ == "__main__":
    unittest.main()
