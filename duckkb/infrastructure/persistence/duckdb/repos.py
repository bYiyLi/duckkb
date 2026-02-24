from __future__ import annotations

import json
from typing import Iterable

from duckkb.domain.models import Chunk
from duckkb.domain.ports.repository import CacheRepo, SearchIndexRepo
from duckkb.infrastructure.persistence.duckdb.connection import connect


class DuckDBSearchIndexRepo(SearchIndexRepo):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def clear_index(self) -> None:
        with connect(self._db_path, read_only=False) as conn:
            conn.execute("DELETE FROM _sys_search")

    def insert_chunks(self, chunks: Iterable[Chunk]) -> int:
        rows = [
            (
                chunk.ref_id,
                chunk.source_table,
                chunk.source_field,
                chunk.chunk_id,
                chunk.segmented_text,
                chunk.content_hash,
                json.dumps(chunk.metadata, ensure_ascii=False),
                chunk.priority_weight,
            )
            for chunk in chunks
        ]
        if not rows:
            return 0
        with connect(self._db_path, read_only=False) as conn:
            conn.executemany(
                """
                INSERT INTO _sys_search (
                    ref_id, source_table, source_field, chunk_id,
                    segmented_text, content_hash, metadata, priority_weight
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def search_by_tokens(self, tokens: list[str], limit: int) -> list[Chunk]:
        if limit <= 0:
            return []
        if not tokens:
            sql = "SELECT ref_id, source_table, source_field, chunk_id, segmented_text, content_hash, metadata, priority_weight FROM _sys_search LIMIT ?"
            params = [limit]
        else:
            clauses = " AND ".join(["segmented_text LIKE ?"] * len(tokens))
            sql = (
                "SELECT ref_id, source_table, source_field, chunk_id, segmented_text, content_hash, metadata, priority_weight "
                f"FROM _sys_search WHERE {clauses} LIMIT {limit}"
            )
            params = [f"%{token}%" for token in tokens]
        with connect(self._db_path, read_only=True) as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[Chunk] = []
        for row in rows:
            metadata = row[6]
            if isinstance(metadata, str):
                metadata_value = json.loads(metadata)
            else:
                metadata_value = metadata
            result.append(
                Chunk(
                    ref_id=row[0],
                    source_table=row[1],
                    source_field=row[2],
                    chunk_id=row[3],
                    segmented_text=row[4],
                    content_hash=row[5],
                    metadata=metadata_value or {},
                    priority_weight=float(row[7]),
                )
            )
        return result


class DuckDBCacheRepo(CacheRepo):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get_embedding(self, content_hash: str) -> list[float] | None:
        with connect(self._db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT embedding FROM _sys_cache WHERE content_hash = ?",
                [content_hash],
            ).fetchone()
        if row is None:
            return None
        return row[0]

    def put_embedding(self, content_hash: str, vector: list[float]) -> None:
        with connect(self._db_path, read_only=False) as conn:
            conn.execute(
                """
                INSERT INTO _sys_cache (content_hash, embedding, created_at, last_used)
                VALUES (?, ?, now(), now())
                ON CONFLICT (content_hash) DO UPDATE SET
                    embedding = excluded.embedding,
                    last_used = excluded.last_used
                """,
                [content_hash, vector],
            )

    def touch(self, content_hash: str) -> None:
        with connect(self._db_path, read_only=False) as conn:
            conn.execute(
                "UPDATE _sys_cache SET last_used = now() WHERE content_hash = ?",
                [content_hash],
            )

    def gc(self, max_days: int) -> int:
        with connect(self._db_path, read_only=False) as conn:
            days = int(max_days)
            cursor = conn.execute(
                f"DELETE FROM _sys_cache WHERE last_used < (now() - INTERVAL '{days} days')"
            )
            return cursor.rowcount
