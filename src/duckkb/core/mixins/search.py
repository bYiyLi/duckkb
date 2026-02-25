"""检索能力 Mixin。"""

import asyncio
from typing import Any

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.exceptions import DatabaseError
from duckkb.logger import logger


class SearchMixin(BaseEngine):
    """检索能力 Mixin。

    提供 RRF 混合检索和纯向量/全文检索功能。

    Attributes:
        rrf_k: RRF 平滑常数。
    """

    def __init__(self, *args, rrf_k: int = 60, **kwargs) -> None:
        """初始化检索 Mixin。

        Args:
            rrf_k: RRF 常数，默认 60。较大的 k 值会使排名靠前的结果优势减弱，
                   较小的 k 值会使排名靠前的结果优势增强。
        """
        super().__init__(*args, **kwargs)
        self._rrf_k = rrf_k

    @property
    def rrf_k(self) -> int:
        """RRF 平滑常数。"""
        return self._rrf_k

    async def search(
        self,
        node_type: str,
        vector_column: str,
        query_vector: list[float],
        fts_columns: list[str],
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """执行 RRF 混合检索。

        使用 CTE 在数据库内完成：
        1. 向量检索：基于向量距离排序
        2. 全文检索：基于 BM25 排序
        3. RRF 融合：合并两种检索结果的排名

        Args:
            node_type: 节点类型名称。
            vector_column: 向量字段名。
            query_vector: 查询向量。
            fts_columns: 全文检索字段列表。
            query_text: 查询文本。
            limit: 返回结果数量，默认 10。

        Returns:
            排序后的结果列表，每个元素包含原始字段和 rrf_score。

        Raises:
            ValueError: 节点类型不存在时抛出。
            DatabaseError: 查询执行失败时抛出。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table
        validate_table_name(table_name)

        if not query_vector:
            logger.warning("Empty query vector provided")
            return []

        if not fts_columns:
            logger.warning("No FTS columns specified, falling back to vector search only")
            return await self.vector_search(node_type, vector_column, query_vector, limit)

        sql = self._build_rrf_query(
            table_name, vector_column, query_vector, fts_columns, query_text, limit
        )

        try:
            rows = await asyncio.to_thread(self._execute_query, sql)
            return self._process_results(rows)
        except Exception as e:
            logger.error(f"RRF search failed: {e}")
            raise DatabaseError(f"RRF search failed: {e}") from e

    async def vector_search(
        self,
        node_type: str,
        vector_column: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """执行纯向量检索。

        Args:
            node_type: 节点类型名称。
            vector_column: 向量字段名。
            query_vector: 查询向量。
            limit: 返回结果数量。

        Returns:
            排序后的结果列表。

        Raises:
            ValueError: 节点类型不存在时抛出。
            DatabaseError: 查询执行失败时抛出。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table
        validate_table_name(table_name)

        if not query_vector:
            logger.warning("Empty query vector provided")
            return []

        vector_dim = len(query_vector)
        vector_literal = self._format_vector_literal(query_vector)

        sql = f"""
        SELECT t.*, array_distance(t.{vector_column}, {vector_literal}::FLOAT[{vector_dim}]) as distance
        FROM {table_name} t
        WHERE t.{vector_column} IS NOT NULL
        ORDER BY distance
        LIMIT {limit}
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, sql)
            return self._process_results(rows)
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise DatabaseError(f"Vector search failed: {e}") from e

    async def fts_search(
        self,
        node_type: str,
        fts_columns: list[str],
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """执行纯全文检索。

        Args:
            node_type: 节点类型名称。
            fts_columns: 全文检索字段列表。
            query_text: 查询文本。
            limit: 返回结果数量。

        Returns:
            排序后的结果列表。

        Raises:
            ValueError: 节点类型不存在时抛出。
            DatabaseError: 查询执行失败时抛出。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table
        validate_table_name(table_name)

        if not fts_columns:
            raise ValueError("fts_columns cannot be empty")

        fts_columns_str = ", ".join(fts_columns)
        escaped_query = query_text.replace("'", "''")

        sql = f"""
        SELECT t.*, fts_score as score
        FROM {table_name} t
        WHERE fts_match(({fts_columns_str}), '{escaped_query}')
        ORDER BY score DESC
        LIMIT {limit}
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, sql)
            return self._process_results(rows)
        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            raise DatabaseError(f"FTS search failed: {e}") from e

    def _build_rrf_query(
        self,
        table_name: str,
        vector_column: str,
        query_vector: list[float],
        fts_columns: list[str],
        query_text: str,
        limit: int,
    ) -> str:
        """构建 RRF 混合检索 SQL 查询。

        Args:
            table_name: 表名。
            vector_column: 向量字段名。
            query_vector: 查询向量。
            fts_columns: 全文检索字段列表。
            query_text: 查询文本。
            limit: 返回结果数量。

        Returns:
            SQL 查询字符串。
        """
        prefetch_limit = limit * 3
        vector_dim = len(query_vector)
        vector_literal = self._format_vector_literal(query_vector)
        fts_columns_str = ", ".join(fts_columns)
        escaped_query = query_text.replace("'", "''")

        return f"""
        WITH
        vector_results AS (
            SELECT
                __id,
                array_distance({vector_column}, {vector_literal}::FLOAT[{vector_dim}]) as score,
                rank() OVER (ORDER BY array_distance({vector_column}, {vector_literal}::FLOAT[{vector_dim}])) as rnk
            FROM {table_name}
            WHERE {vector_column} IS NOT NULL
            ORDER BY score
            LIMIT {prefetch_limit}
        ),
        fts_results AS (
            SELECT
                __id,
                fts_score as score,
                rank() OVER (ORDER BY fts_score DESC) as rnk
            FROM {table_name}
            WHERE fts_match(({fts_columns_str}), '{escaped_query}')
            LIMIT {prefetch_limit}
        ),
        rrf_scores AS (
            SELECT
                COALESCE(v.__id, f.__id) as __id,
                COALESCE(1.0 / ({self._rrf_k} + v.rnk), 0.0) + COALESCE(1.0 / ({self._rrf_k} + f.rnk), 0.0) as rrf_score
            FROM vector_results v
            FULL OUTER JOIN fts_results f ON v.__id = f.__id
        )
        SELECT t.*, r.rrf_score
        FROM rrf_scores r
        JOIN {table_name} t ON r.__id = t.__id
        ORDER BY rrf_score DESC
        LIMIT {limit}
        """

    def _format_vector_literal(self, vector: list[float]) -> str:
        """格式化向量为 SQL 字面量。

        Args:
            vector: 向量列表。

        Returns:
            SQL 向量字面量字符串。
        """
        values = ", ".join(str(v) for v in vector)
        return f"[{values}]"

    def _execute_query(self, sql: str) -> list[Any]:
        """执行 SQL 查询。

        Args:
            sql: SQL 查询字符串。

        Returns:
            查询返回的行列表。
        """
        return self.conn.execute(sql).fetchall()

    def _process_results(self, rows: list[Any]) -> list[dict[str, Any]]:
        """处理原始数据库行为结构化结果。

        Args:
            rows: 数据库返回的原始行。

        Returns:
            包含处理结果的字典列表。
        """
        if not rows:
            return []

        cursor = self.conn.execute("SELECT * FROM (SELECT 1 LIMIT 0)")
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

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
