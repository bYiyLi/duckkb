"""检索能力 Mixin。"""

import asyncio
import re
from typing import Any

import numpy as np
import orjson

from duckkb.constants import QUERY_DEFAULT_LIMIT, QUERY_RESULT_SIZE_LIMIT, validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.exceptions import DatabaseError, FTSError
from duckkb.logger import logger

SEARCH_INDEX_TABLE = "_sys_search_index"


class SearchMixin(BaseEngine):
    """检索能力 Mixin。

    提供 RRF 混合检索和纯向量/全文检索功能。
    使用 search_index 表作为唯一检索入口。

    Attributes:
        rrf_k: RRF 平滑常数。
    """

    def __init__(self, *args, rrf_k: int = 60, **kwargs) -> None:
        """初始化检索 Mixin。

        Args:
            rrf_k: RRF 常数，默认 60。
        """
        super().__init__(*args, **kwargs)
        self._rrf_k = rrf_k

    @property
    def rrf_k(self) -> int:
        """RRF 平滑常数。"""
        return self._rrf_k

    async def search(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 10,
        alpha: float = 0.5,
    ) -> list[dict[str, Any]]:
        """智能混合搜索。

        通过 search_index 表执行混合检索，支持：
        1. 向量检索：语义相似度
        2. 全文检索：关键词匹配
        3. RRF 融合：合并两种检索结果

        Args:
            query: 搜索查询文本。
            node_type: 节点类型过滤器（可选）。
            limit: 返回结果数量。
            alpha: 向量搜索权重 (0.0-1.0)。

        Returns:
            排序后的结果列表，包含原始字段和分数。
        """
        if not query:
            return []

        query_vector = await self._get_query_vector(query)
        if not query_vector:
            logger.warning("Failed to generate query embedding")
            return []

        return await self._execute_hybrid_search(
            query=query,
            query_vector=query_vector,
            node_type=node_type,
            limit=limit,
            alpha=alpha,
        )

    async def _get_query_vector(self, query: str) -> list[float] | None:
        """获取查询向量并校验维度。

        Returns:
            校验通过的查询向量，校验失败返回 None。
        """
        if hasattr(self, "embed_single"):
            try:
                vector = await self.embed_single(query)
                if hasattr(self, "embedding_dim"):
                    expected_dim = self.embedding_dim
                    actual_dim = len(vector)
                    if actual_dim != expected_dim:
                        logger.error(
                            f"Vector dimension mismatch: expected {expected_dim}, got {actual_dim}"
                        )
                        return None
                return vector
            except Exception as e:
                logger.error(f"Failed to embed query: {e}")
        return None

    async def _execute_hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        node_type: str | None,
        limit: int,
        alpha: float,
    ) -> list[dict[str, Any]]:
        """执行混合检索。"""
        table_filter = ""
        params: list[Any] = []

        if node_type:
            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                raise ValueError(f"Unknown node type: {node_type}")
            table_filter = "AND source_table = ?"
            params.append(node_def.table)

        vector_dim = len(query_vector)
        vector_literal = self._format_vector_for_sql(query_vector)
        prefetch_limit = limit * 3

        fts_params = params + [query, query, query] + params

        try:
            sql = f"""
            WITH
            vector_search AS (
                SELECT 
                    id,
                    source_table,
                    source_id,
                    source_field,
                    chunk_seq,
                    array_cosine_similarity(vector::DOUBLE[{vector_dim}], {vector_literal}) as score,
                    rank() OVER (ORDER BY array_cosine_similarity(vector::DOUBLE[{vector_dim}], {vector_literal}) DESC) as rnk
                FROM {SEARCH_INDEX_TABLE}
                WHERE vector IS NOT NULL {table_filter.replace("s.", "")}
                ORDER BY score DESC
                LIMIT {prefetch_limit}
            ),
            fts_search AS (
                SELECT 
                    id,
                    source_table,
                    source_id,
                    source_field,
                    chunk_seq,
                    fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) as score,
                    rank() OVER (ORDER BY fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) DESC) as rnk
                FROM {SEARCH_INDEX_TABLE}
                WHERE fts_content IS NOT NULL
                  AND fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) IS NOT NULL
                {table_filter.replace("s.", "")}
                ORDER BY score DESC
                LIMIT {prefetch_limit}
            ),
            rrf_scores AS (
                SELECT 
                    COALESCE(v.id, f.id) as id,
                    COALESCE(v.source_table, f.source_table) as source_table,
                    COALESCE(v.source_id, f.source_id) as source_id,
                    COALESCE(v.source_field, f.source_field) as source_field,
                    COALESCE(v.chunk_seq, f.chunk_seq) as chunk_seq,
                    COALESCE(1.0 / ({self._rrf_k} + v.rnk), 0.0) * {alpha} 
                    + COALESCE(1.0 / ({self._rrf_k} + f.rnk), 0.0) * {1 - alpha} as rrf_score
                FROM vector_search v
                FULL OUTER JOIN fts_search f 
                  ON v.id = f.id
            )
            SELECT r.*, i.content
            FROM rrf_scores r
            JOIN {SEARCH_INDEX_TABLE} i 
              ON r.id = i.id
            ORDER BY rrf_score DESC
            LIMIT {limit}
            """
            rows = await asyncio.to_thread(self.execute_read, sql, fts_params)
            return self._process_results(rows)
        except Exception as e:
            if "match_bm25" in str(e).lower() or "fts" in str(e).lower():
                raise FTSError(
                    "FTS index not available. Please ensure FTS extension is installed and index is created."
                ) from e
            logger.error(f"Hybrid search failed: {e}")
            raise DatabaseError(f"Hybrid search failed: {e}") from e

    async def vector_search(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """纯向量检索。

        Args:
            query: 搜索查询文本。
            node_type: 节点类型过滤器。
            limit: 返回结果数量。

        Returns:
            排序后的结果列表。
        """
        query_vector = await self._get_query_vector(query)
        if not query_vector:
            return []

        table_filter = ""
        params: list[Any] = []

        if node_type:
            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                raise ValueError(f"Unknown node type: {node_type}")
            table_filter = "AND source_table = ?"
            params.append(node_def.table)

        vector_dim = len(query_vector)
        vector_literal = self._format_vector_for_sql(query_vector)

        sql = f"""
        SELECT source_table, source_id, source_field, chunk_seq, content,
               array_cosine_similarity(vector::DOUBLE[{vector_dim}], {vector_literal}) as score
        FROM {SEARCH_INDEX_TABLE}
        WHERE vector IS NOT NULL {table_filter}
        ORDER BY score DESC
        LIMIT {limit}
        """

        try:
            rows = await asyncio.to_thread(self.execute_read, sql, params)
            return self._process_results(rows)
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise DatabaseError(f"Vector search failed: {e}") from e

    async def fts_search(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """全文检索（使用 DuckDB FTS 扩展）。

        Args:
            query: 搜索查询文本。
            node_type: 节点类型过滤器。
            limit: 返回结果数量。

        Returns:
            排序后的结果列表。

        Raises:
            DatabaseError: FTS 搜索失败时抛出。
        """
        if not query:
            return []

        table_filter = ""
        params: list[Any] = [query, query]

        if node_type:
            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                raise ValueError(f"Unknown node type: {node_type}")
            table_filter = "AND source_table = ?"
            params.append(node_def.table)

        sql = f"""
        SELECT 
            source_table, source_id, source_field, chunk_seq, content,
            fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) as score
        FROM {SEARCH_INDEX_TABLE}
        WHERE fts_content IS NOT NULL
          AND fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) IS NOT NULL
        {table_filter}
        ORDER BY score DESC
        LIMIT ?
        """
        params.append(limit)

        try:
            rows = await asyncio.to_thread(self.execute_read, sql, params)
            return self._process_results(rows)
        except Exception as e:
            if "match_bm25" in str(e).lower() or "fts" in str(e).lower():
                raise FTSError(
                    "FTS index not available. Please ensure FTS extension is installed and index is created."
                ) from e
            logger.error(f"FTS search failed: {e}")
            raise DatabaseError(f"FTS search failed: {e}") from e

    async def get_source_record(
        self,
        source_table: str,
        source_id: int,
    ) -> dict[str, Any] | None:
        """根据搜索结果回捞原始业务记录。

        Args:
            source_table: 源表名。
            source_id: 源记录 ID。

        Returns:
            原始业务记录，不存在时返回 None。
        """
        validate_table_name(source_table)

        def _fetch() -> dict[str, Any] | None:
            rows = self.execute_read(f"SELECT * FROM {source_table} WHERE __id = ?", [source_id])
            if not rows:
                return None
            row = rows[0]
            columns = self._get_table_columns(source_table)
            return dict(zip(columns, row, strict=True))

        return await asyncio.to_thread(_fetch)

    async def query_raw_sql(self, sql: str) -> list[dict[str, Any]]:
        """安全执行原始 SQL 查询。

        使用只读连接执行，自动拒绝所有写操作。
        自动添加 LIMIT 限制，防止返回过多数据。

        Args:
            sql: 原始 SQL 查询字符串。

        Returns:
            查询结果字典列表。

        Raises:
            ValueError: 结果集大小超限。
            duckdb.Error: SQL 执行失败或包含写操作。
        """
        sql_stripped = sql.strip()

        if not re.search(r"\bLIMIT\s+\d+", sql_stripped.upper()):
            sql = sql_stripped + f" LIMIT {QUERY_DEFAULT_LIMIT}"

        return await asyncio.to_thread(self._execute_raw_sql_readonly, sql)

    def _execute_raw_sql_readonly(self, sql: str) -> list[dict[str, Any]]:
        """在只读模式下执行 SQL 查询。

        Args:
            sql: 要执行的 SQL 查询。

        Returns:
            字典列表，键为列名，值为行值。

        Raises:
            ValueError: 结果集大小超限。
            duckdb.Error: SQL 执行失败或包含写操作。
        """
        rows = self.execute_read(sql)
        if not rows:
            return []

        columns = self._extract_columns_from_sql(sql)
        actual_col_count = len(rows[0])
        if len(columns) != actual_col_count:
            columns = columns[:actual_col_count]
            if len(columns) < actual_col_count:
                columns.extend([f"col_{i}" for i in range(len(columns), actual_col_count)])
        result = [dict(zip(columns, row, strict=True)) for row in rows]

        json_bytes = orjson.dumps(result)
        if len(json_bytes) > QUERY_RESULT_SIZE_LIMIT:
            raise ValueError(
                f"Result set size exceeds {QUERY_RESULT_SIZE_LIMIT // (1024 * 1024)}MB limit."
            )

        return result

    def _format_vector_literal(self, vector: list[float]) -> str:
        """格式化向量为 SQL 字面量。"""
        values = ", ".join(str(v) for v in vector)
        return f"[{values}]"

    def _to_float32_array(self, vector: list[float]) -> list[float]:
        """确保向量为 float32 格式。

        Args:
            vector: 浮点数列表。

        Returns:
            float32 值列表。
        """
        return [float(np.float32(v)) for v in vector]

    def _format_vector_for_sql(self, vector: list[float]) -> str:
        """格式化向量为 SQL 字面量，使用固定大小 DOUBLE 数组。

        Args:
            vector: 浮点数列表。

        Returns:
            SQL DOUBLE 数组字面量字符串。
        """
        dim = len(vector)
        values = ", ".join(str(float(np.float32(v))) for v in vector)
        return f"[{values}]::DOUBLE[{dim}]"

    def _process_results(self, rows: list[Any]) -> list[dict[str, Any]]:
        """处理原始数据库行为结构化结果。"""
        if not rows:
            return []

        columns = ["source_table", "source_id", "source_field", "chunk_seq", "content", "score"]

        results = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(columns):
                    row_dict[columns[i]] = value
                else:
                    row_dict[f"col_{i}"] = value
            results.append(row_dict)

        return results

    def _get_table_columns(self, table_name: str) -> list[str]:
        """获取表的列名列表。

        Args:
            table_name: 表名。

        Returns:
            列名列表。
        """
        rows = self.execute_read(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position"
        )
        return [row[0] for row in rows]

    def _extract_columns_from_sql(self, sql: str) -> list[str]:
        """从 SQL 中提取列名。

        Args:
            sql: SQL 查询语句。

        Returns:
            列名列表。
        """
        sql_upper = sql.upper()
        select_idx = sql_upper.find("SELECT")
        from_idx = sql_upper.find("FROM")

        if select_idx == -1 or from_idx == -1:
            return [f"col_{i}" for i in range(100)]

        select_part = sql[select_idx + 6 : from_idx].strip()

        if select_part == "*":
            return [f"col_{i}" for i in range(100)]

        columns = []
        for col in select_part.split(","):
            col = col.strip()
            if " AS " in col.upper():
                col = col.split()[-1]
            elif "." in col:
                col = col.split(".")[-1]
            columns.append(col)

        return columns
