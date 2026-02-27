"""搜索索引管理 Mixin。"""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.exceptions import FTSError
from duckkb.logger import logger

SEARCH_INDEX_TABLE = "_sys_search_index"
SEARCH_CACHE_TABLE = "_sys_search_cache"


class IndexMixin(BaseEngine):
    """搜索索引管理 Mixin。

    负责管理 search_index 和 search_cache 表，提供索引构建和缓存管理功能。
    chunk_size 从 config.yaml 的 global.chunk_size 读取。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化索引 Mixin。"""
        super().__init__(*args, **kwargs)

    @property
    def chunk_size(self) -> int:
        """文本切片大小，从全局配置读取。"""
        return self.config.global_config.chunk_size

    def create_index_tables(self) -> None:
        """创建搜索索引表和缓存表。"""
        self._create_search_index_table()
        self._create_search_cache_table()

    def _create_search_index_table(self) -> None:
        """创建搜索索引表。"""
        self.execute_write(f"CREATE SEQUENCE IF NOT EXISTS {SEARCH_INDEX_TABLE}_id_seq START 1")
        self.execute_write(f"""
            CREATE TABLE IF NOT EXISTS {SEARCH_INDEX_TABLE} (
                id BIGINT PRIMARY KEY DEFAULT nextval('{SEARCH_INDEX_TABLE}_id_seq'),
                source_table VARCHAR NOT NULL,
                source_id BIGINT NOT NULL,
                source_field VARCHAR NOT NULL,
                chunk_seq INTEGER NOT NULL DEFAULT 0,
                content VARCHAR,
                fts_content VARCHAR,
                vector FLOAT[],
                content_hash VARCHAR,
                created_at TIMESTAMP,
                UNIQUE (source_table, source_id, source_field, chunk_seq)
            )
        """)
        logger.debug(f"Created table: {SEARCH_INDEX_TABLE}")

    def _create_search_cache_table(self) -> None:
        """创建搜索缓存表。"""
        self.execute_write(f"""
            CREATE TABLE IF NOT EXISTS {SEARCH_CACHE_TABLE} (
                content_hash VARCHAR PRIMARY KEY,
                fts_content VARCHAR,
                vector FLOAT[],
                last_used TIMESTAMP,
                created_at TIMESTAMP
            )
        """)
        logger.debug(f"Created table: {SEARCH_CACHE_TABLE}")

    def _create_fts_index(self) -> None:
        """为搜索索引表创建 FTS 索引。

        使用 fts_content（分词后的内容）建立全文索引。
        DuckDB FTS 按空格分词，中文需要先分词才能正确搜索。
        """
        try:
            self.execute_write(f"PRAGMA drop_fts_index('{SEARCH_INDEX_TABLE}')")
        except Exception:
            pass

        self.execute_write(f"PRAGMA create_fts_index('{SEARCH_INDEX_TABLE}', 'id', 'fts_content')")
        logger.info("FTS index created successfully")

    def rebuild_fts_index(self) -> None:
        """重建 FTS 索引。

        在数据导入后调用，确保 FTS 索引与数据同步。
        """
        self._create_fts_index()

    def _try_create_fts_index(self) -> None:
        """尝试创建 FTS 索引。

        检查 _sys_search_index 表是否有分词内容，如果有则创建 FTS 索引。
        """
        try:
            result = self.execute_read(
                f"SELECT COUNT(*) FROM {SEARCH_INDEX_TABLE} WHERE fts_content IS NOT NULL"
            )
            count = result[0][0] if result else 0
            if count > 0:
                self._create_fts_index()
                logger.info(f"FTS index created for {count} documents")
            else:
                logger.debug("No fts_content in search index, skipping FTS index creation")
        except Exception as e:
            raise FTSError(f"Failed to create FTS index: {e}") from e

    async def build_index(
        self,
        node_type: str | None = None,
        batch_size: int = 100,
    ) -> int:
        """构建搜索索引。

        为指定节点类型（或所有节点）构建搜索索引，包括：
        1. 扫描需要索引的字段
        2. 文本切片
        3. 分词处理
        4. 向量化
        5. 写入 search_index 表

        Args:
            node_type: 节点类型名称，None 表示所有节点。
            batch_size: 批处理大小。

        Returns:
            构建的索引条目数。
        """
        self.create_index_tables()

        total_indexed = 0

        if node_type:
            node_types = [node_type]
        else:
            node_types = list(self.ontology.nodes.keys())

        for nt in node_types:
            indexed = await self._build_node_index(nt, batch_size)
            total_indexed += indexed

        logger.info(f"Built search index: {total_indexed} entries")
        return total_indexed

    async def _build_node_index(self, node_type: str, batch_size: int) -> int:
        """为单个节点类型构建索引。"""
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table
        validate_table_name(table_name)

        search_config = getattr(node_def, "search", None)
        if not search_config:
            logger.warning(f"No search config for node type: {node_type}")
            return 0

        fts_fields: list[str] = getattr(search_config, "full_text", []) or []
        vector_fields: list[str] = getattr(search_config, "vectors", []) or []

        if not fts_fields and not vector_fields:
            logger.warning(f"No searchable fields for node type: {node_type}")
            return 0

        all_fields: set[str] = set(fts_fields) | set(vector_fields)

        def _fetch_records() -> list[tuple]:
            fields_str = ", ".join(all_fields)
            return self.execute_read(f"SELECT __id, {fields_str} FROM {table_name}")

        records = await asyncio.to_thread(_fetch_records)
        indexed = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            batch_entries = await self._process_batch(
                batch, table_name, all_fields, set(fts_fields), set(vector_fields)
            )

            if batch_entries:
                await asyncio.to_thread(self._insert_index_entries, batch_entries)
                indexed += len(batch_entries)

        logger.info(f"Indexed {indexed} entries for {node_type}")
        return indexed

    async def _process_batch(
        self,
        records: list[tuple],
        table_name: str,
        all_fields: set[str],
        fts_fields: set[str],
        vector_fields: set[str],
    ) -> list[tuple]:
        """处理一批记录，生成索引条目。"""
        entries = []
        field_list = list(all_fields)

        for record in records:
            source_id = record[0]
            field_values = record[1:]

            for field_idx, field_name in enumerate(field_list):
                content = field_values[field_idx]
                if not content or not isinstance(content, str):
                    continue

                chunks = self._chunk_text(content)

                for chunk_seq, chunk in enumerate(chunks):
                    content_hash = self._compute_hash(chunk)

                    fts_content = None
                    if field_name in fts_fields:
                        fts_content = await self._get_or_compute_fts(chunk, content_hash)

                    vector = None
                    if field_name in vector_fields:
                        vector = await self._get_or_compute_vector(chunk, content_hash)

                    entries.append(
                        (
                            table_name,
                            source_id,
                            field_name,
                            chunk_seq,
                            chunk,
                            fts_content,
                            vector,
                            content_hash,
                            datetime.now(UTC),
                        )
                    )

        return entries

    def _chunk_text(self, text: str) -> list[str]:
        """将文本切分为多个片段。

        委托给 ChunkingMixin.chunk_text 方法。

        Args:
            text: 待切分的文本。

        Returns:
            文本片段列表。

        Raises:
            RuntimeError: ChunkingMixin 未被正确继承时抛出。
        """
        if not hasattr(self, "chunk_text"):
            raise RuntimeError("ChunkingMixin not available, check Engine MRO")
        return self.chunk_text(text)

    def _compute_hash(self, text: str) -> str:
        """计算文本哈希。"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    async def _get_or_compute_fts(self, text: str, content_hash: str) -> str:
        """获取或计算分词结果。

        优先从缓存获取，缓存未命中则计算并存入缓存。

        Args:
            text: 待分词文本。
            content_hash: 文本哈希。

        Returns:
            分词结果（空格分隔）。
        """

        def _get_cached() -> str | None:
            rows = self.execute_read(
                f"SELECT fts_content FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
                [content_hash],
            )
            return rows[0][0] if rows else None

        cached = await asyncio.to_thread(_get_cached)
        if cached:
            return cached

        fts_content = await self._segment_text(text)

        def _cache_it() -> None:
            now = datetime.now(UTC)
            self.execute_write(
                f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
                "(content_hash, fts_content, last_used, created_at) VALUES (?, ?, ?, ?)",
                [content_hash, fts_content, now, now],
            )

        await asyncio.to_thread(_cache_it)
        return fts_content

    async def _get_or_compute_vector(
        self, text: str, content_hash: str, max_retries: int = 3, retry_delay: float = 1.0
    ) -> list[float] | None:
        """获取或计算向量嵌入。

        优先从缓存获取，缓存未命中则计算并存入缓存。
        支持重试机制以提高容错性。

        Args:
            text: 待向量化文本。
            content_hash: 文本哈希。
            max_retries: 最大重试次数，默认 3 次。
            retry_delay: 重试间隔秒数，默认 1.0 秒。

        Returns:
            向量嵌入。
        """

        def _get_cached() -> list[float] | None:
            rows = self.execute_read(
                f"SELECT vector FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
                [content_hash],
            )
            return rows[0][0] if rows else None

        cached = await asyncio.to_thread(_get_cached)
        if cached:
            return cached

        for attempt in range(max_retries):
            try:
                vector = await self._compute_embedding(text)

                def _cache_it(v: list[float] = vector) -> None:
                    now = datetime.now(UTC)
                    self.execute_write(
                        f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
                        "(content_hash, vector, last_used, created_at) VALUES (?, ?, ?, ?)",
                        [content_hash, v, now, now],
                    )

                await asyncio.to_thread(_cache_it)
                return vector
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Failed to compute embedding (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Failed to compute embedding after {max_retries} attempts: {e}")

        return None

    async def _segment_text(self, text: str) -> str:
        """分词处理（由 TokenizerMixin 提供）。"""
        if hasattr(self, "segment"):
            return await self.segment(text)
        return text

    async def _compute_embedding(self, text: str) -> list[float]:
        """计算向量嵌入（由 EmbeddingMixin 提供）。"""
        if hasattr(self, "embed_single"):
            return await self.embed_single(text)
        raise NotImplementedError("EmbeddingMixin not available")

    def _insert_index_entries(self, entries: list[tuple]) -> None:
        """插入索引条目。

        使用 UPSERT 语义：如果复合键冲突则更新，否则插入。
        ID 列自动生成，不需要手动指定。
        """
        with self.write_transaction() as conn:
            conn.executemany(
                f"INSERT INTO {SEARCH_INDEX_TABLE} "
                "(source_table, source_id, source_field, chunk_seq, content, "
                "fts_content, vector, content_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (source_table, source_id, source_field, chunk_seq) "
                "DO UPDATE SET content = excluded.content, "
                "fts_content = excluded.fts_content, "
                "vector = excluded.vector, "
                "content_hash = excluded.content_hash, "
                "created_at = excluded.created_at",
                entries,
            )

    async def rebuild_index(self, node_type: str) -> int:
        """重建指定节点类型的索引。

        Args:
            node_type: 节点类型名称。

        Returns:
            重建的索引条目数。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table

        def _delete_old() -> None:
            self.execute_write(
                f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE source_table = ?",
                [table_name],
            )

        await asyncio.to_thread(_delete_old)
        return await self._build_node_index(node_type, batch_size=100)

    async def load_cache_from_parquet(self, path: Path) -> int:
        """从 Parquet 文件加载搜索缓存。

        Args:
            path: Parquet 文件路径。

        Returns:
            加载的缓存条目数。
        """
        if not path.exists():
            logger.warning(f"Cache file not found: {path}")
            return 0

        def _load() -> int:
            self.execute_write(
                f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
                f"SELECT content_hash, fts_content, vector, last_used, created_at "
                f"FROM read_parquet('{path}')"
            )
            rows = self.execute_read(f"SELECT COUNT(*) FROM {SEARCH_CACHE_TABLE}")
            return rows[0][0] if rows else 0

        count = await asyncio.to_thread(_load)
        logger.info(f"Loaded {count} cache entries from {path}")
        return count

    async def save_cache_to_parquet(self, path: Path) -> int:
        """保存搜索缓存到 Parquet 文件。

        Args:
            path: Parquet 文件路径。

        Returns:
            保存的缓存条目数。
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        def _save() -> int:
            rows = self.execute_read(f"SELECT COUNT(*) FROM {SEARCH_CACHE_TABLE}")
            count = rows[0][0] if rows else 0

            self.execute_write(f"COPY {SEARCH_CACHE_TABLE} TO '{path}' (FORMAT PARQUET)")
            return count

        count = await asyncio.to_thread(_save)
        logger.info(f"Saved {count} cache entries to {path}")
        return count

    async def clean_cache(self, expire_days: int = 30) -> int:
        """清理过期的缓存条目。

        Args:
            expire_days: 过期天数。

        Returns:
            删除的条目数。
        """

        def _clean() -> int:
            rows = self.execute_write_with_result(
                f"DELETE FROM {SEARCH_CACHE_TABLE} "
                f"WHERE last_used < current_timestamp - INTERVAL {expire_days} DAY"
            )
            return len(rows) if rows else 0

        deleted = await asyncio.to_thread(_clean)
        logger.info(f"Cleaned {deleted} expired cache entries")
        return deleted

    async def _rebuild_index_from_cache(self) -> None:
        """从缓存重建搜索索引。

        扫描所有节点数据，使用缓存中的向量和分词结果重建索引。
        采用批量查询缓存的方式优化性能。
        """
        for node_type, node_def in self.ontology.nodes.items():
            search_config = getattr(node_def, "search", None)
            if not search_config:
                continue

            fts_fields: list[str] = getattr(search_config, "full_text", []) or []
            vector_fields: list[str] = getattr(search_config, "vectors", []) or []
            all_fields: set[str] = set(fts_fields) | set(vector_fields)

            if not all_fields:
                continue

            table_name = node_def.table
            validate_table_name(table_name)
            fields_str = ", ".join(all_fields)

            def _fetch_records() -> list[tuple]:
                return self.execute_read(f"SELECT __id, {fields_str} FROM {table_name}")

            records = await asyncio.to_thread(_fetch_records)
            if not records:
                continue

            entries = []
            content_hashes = set()

            for record in records:
                source_id = record[0]
                field_values = record[1:]
                field_list = list(all_fields)

                for field_idx, field_name in enumerate(field_list):
                    content = field_values[field_idx]
                    if not content or not isinstance(content, str):
                        continue

                    chunks = self._chunk_text(content)

                    for chunk_seq, chunk in enumerate(chunks):
                        content_hash = self._compute_hash(chunk)
                        content_hashes.add(content_hash)

                        entries.append(
                            {
                                "table_name": table_name,
                                "source_id": source_id,
                                "field_name": field_name,
                                "chunk_seq": chunk_seq,
                                "chunk": chunk,
                                "content_hash": content_hash,
                                "fts_field": field_name in fts_fields,
                                "vector_field": field_name in vector_fields,
                            }
                        )

            if not entries:
                continue

            def _batch_fetch_cache() -> dict[str, tuple[str | None, list[float] | None]]:
                placeholders = ", ".join(["?" for _ in content_hashes])
                rows = self.execute_read(
                    f"SELECT content_hash, fts_content, vector FROM {SEARCH_CACHE_TABLE} "
                    f"WHERE content_hash IN ({placeholders})",
                    list(content_hashes),
                )
                return {row[0]: (row[1], row[2]) for row in rows}

            cache_map = await asyncio.to_thread(_batch_fetch_cache)

            index_entries = []
            for entry in entries:
                fts_content = None
                vector = None
                cached = cache_map.get(entry["content_hash"])

                if cached:
                    if entry["fts_field"]:
                        fts_content = cached[0]
                    if entry["vector_field"]:
                        vector = cached[1]

                index_entries.append(
                    (
                        entry["table_name"],
                        entry["source_id"],
                        entry["field_name"],
                        entry["chunk_seq"],
                        entry["chunk"],
                        fts_content,
                        vector,
                        entry["content_hash"],
                        datetime.now(UTC),
                    )
                )

            def _insert() -> None:
                with self.write_transaction() as conn:
                    conn.executemany(
                        f"INSERT INTO {SEARCH_INDEX_TABLE} "
                        "(source_table, source_id, source_field, chunk_seq, content, "
                        "fts_content, vector, content_hash, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT (source_table, source_id, source_field, chunk_seq) "
                        "DO UPDATE SET content = excluded.content, "
                        "fts_content = excluded.fts_content, "
                        "vector = excluded.vector, "
                        "content_hash = excluded.content_hash, "
                        "created_at = excluded.created_at",
                        index_entries,
                    )

            await asyncio.to_thread(_insert)
            logger.info(f"Rebuilt index for {node_type}: {len(index_entries)} entries")
