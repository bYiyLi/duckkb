"""检索能力 Mixin。"""

import asyncio
import re
from typing import Any

import orjson

from duckkb.constants import QUERY_DEFAULT_LIMIT, QUERY_RESULT_SIZE_LIMIT, validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.exceptions import DatabaseError
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
        """获取查询向量。"""
        if hasattr(self, "embed_single"):
            try:
                return await self.embed_single(query)
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
        vector_literal = self._format_vector_literal(query_vector)
        escaped_query = query.replace("'", "''")
        prefetch_limit = limit * 3

        sql = f"""
        WITH
        vector_search AS (
            SELECT 
                source_table,
                source_id,
                source_field,
                chunk_seq,
                array_cosine_similarity(vector, {vector_literal}::FLOAT[{vector_dim}]) as score,
                rank() OVER (ORDER BY array_cosine_similarity(vector, {vector_literal}::FLOAT[{vector_dim}]) DESC) as rnk
            FROM {SEARCH_INDEX_TABLE}
            WHERE vector IS NOT NULL {table_filter}
            ORDER BY score DESC
            LIMIT {prefetch_limit}
        ),
        fts_search AS (
            SELECT 
                source_table,
                source_id,
                source_field,
                chunk_seq,
                fts_score as score,
                rank() OVER (ORDER BY fts_score DESC) as rnk
            FROM {SEARCH_INDEX_TABLE}
            WHERE fts_content IS NOT NULL 
              AND fts_match(fts_content, '{escaped_query}') {table_filter}
            ORDER BY score DESC
            LIMIT {prefetch_limit}
        ),
        rrf_scores AS (
            SELECT 
                COALESCE(v.source_table, f.source_table) as source_table,
                COALESCE(v.source_id, f.source_id) as source_id,
                COALESCE(v.source_field, f.source_field) as source_field,
                COALESCE(v.chunk_seq, f.chunk_seq) as chunk_seq,
                COALESCE(1.0 / ({self._rrf_k} + v.rnk), 0.0) * {alpha} 
                + COALESCE(1.0 / ({self._rrf_k} + f.rnk), 0.0) * {1 - alpha} as rrf_score
            FROM vector_search v
            FULL OUTER JOIN fts_search f 
              ON v.source_table = f.source_table 
             AND v.source_id = f.source_id 
             AND v.source_field = f.source_field
             AND v.chunk_seq = f.chunk_seq
        )
        SELECT r.*, i.content
        FROM rrf_scores r
        JOIN {SEARCH_INDEX_TABLE} i 
          ON r.source_table = i.source_table 
         AND r.source_id = i.source_id 
         AND r.source_field = i.source_field 
         AND r.chunk_seq = i.chunk_seq
        ORDER BY rrf_score DESC
        LIMIT {limit}
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, sql, params)
            return self._process_results(rows)
        except Exception as e:
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
        vector_literal = self._format_vector_literal(query_vector)

        sql = f"""
        SELECT source_table, source_id, source_field, chunk_seq, content,
               array_cosine_similarity(vector, {vector_literal}::FLOAT[{vector_dim}]) as score
        FROM {SEARCH_INDEX_TABLE}
        WHERE vector IS NOT NULL {table_filter}
        ORDER BY score DESC
        LIMIT {limit}
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, sql, params)
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
        """纯全文检索。

        Args:
            query: 搜索查询文本。
            node_type: 节点类型过滤器。
            limit: 返回结果数量。

        Returns:
            排序后的结果列表。
        """
        if not query:
            return []

        table_filter = ""
        params: list[Any] = []

        if node_type:
            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                raise ValueError(f"Unknown node type: {node_type}")
            table_filter = "AND source_table = ?"
            params.append(node_def.table)

        escaped_query = query.replace("'", "''")

        sql = f"""
        SELECT source_table, source_id, source_field, chunk_seq, content,
               fts_score as score
        FROM {SEARCH_INDEX_TABLE}
        WHERE fts_content IS NOT NULL 
          AND fts_match(fts_content, '{escaped_query}') {table_filter}
        ORDER BY score DESC
        LIMIT {limit}
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, sql, params)
            return self._process_results(rows)
        except Exception as e:
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
            row = self.conn.execute(
                f"SELECT * FROM {source_table} WHERE __id = ?",
                [source_id],
            ).fetchone()
            if not row:
                return None

            cursor = self.conn.execute(f"SELECT * FROM {source_table} LIMIT 0")
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return dict(zip(columns, row, strict=True))

        return await asyncio.to_thread(_fetch)

    async def query_raw_sql(self, sql: str) -> list[dict[str, Any]]:
        """安全执行原始 SQL 查询。

        安全检查：
        1. 只允许 SELECT 查询（白名单模式）。
        2. 禁止危险关键字。
        3. 移除 SQL 注释后检查。
        4. 自动添加 LIMIT。
        5. 结果大小限制。

        Args:
            sql: 原始 SQL 查询字符串。

        Returns:
            查询结果字典列表。

        Raises:
            DatabaseError: SQL 包含禁止的关键字或不是 SELECT 查询。
            ValueError: 结果集大小超限或执行失败。
        """
        sql_stripped = sql.strip()
        sql_upper = sql_stripped.upper()

        if not sql_upper.startswith("SELECT"):
            raise DatabaseError("Only SELECT queries are allowed.")

        sql_no_comments = re.sub(r"--.*$", "", sql_stripped, flags=re.MULTILINE)
        sql_no_comments = re.sub(r"/\*.*?\*/", "", sql_no_comments, flags=re.DOTALL)
        sql_no_comments_upper = sql_no_comments.upper()

        forbidden = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "EXEC",
            "EXECUTE",
            "GRANT",
            "REVOKE",
            "ATTACH",
            "DETACH",
            "PRAGMA",
            "IMPORT",
            "EXPORT",
            "COPY",
            "LOAD",
            "INSTALL",
            "VACUUM",
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
        ]
        forbidden_pattern = r"\b(" + "|".join(forbidden) + r")\b"
        if re.search(forbidden_pattern, sql_no_comments_upper):
            raise DatabaseError("Forbidden keyword in SQL query.")

        if not re.search(r"\bLIMIT\s+\d+", sql_upper):
            sql = sql_stripped + f" LIMIT {QUERY_DEFAULT_LIMIT}"

        return await asyncio.to_thread(self._execute_raw_sql, sql)

    def _execute_raw_sql(self, sql: str) -> list[dict[str, Any]]:
        """执行原始 SQL 查询并返回字典列表形式的结果。

        Args:
            sql: 要执行的 SQL 查询。

        Returns:
            字典列表，键为列名，值为行值。

        Raises:
            ValueError: 结果集大小超限或执行失败。
        """
        try:
            cursor = self.conn.execute(sql)
            if not cursor.description:
                return []
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            result = [dict(zip(columns, row, strict=True)) for row in rows]

            try:
                json_bytes = orjson.dumps(result)
                if len(json_bytes) > QUERY_RESULT_SIZE_LIMIT:
                    raise ValueError(
                        f"Result set size exceeds {QUERY_RESULT_SIZE_LIMIT // (1024 * 1024)}MB limit. Please add LIMIT or refine your query."
                    )
            except ValueError:
                raise
            except (orjson.JSONEncodeError, TypeError):
                pass

            return result
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            raise ValueError(str(e)) from e

    def _format_vector_literal(self, vector: list[float]) -> str:
        """格式化向量为 SQL 字面量。"""
        values = ", ".join(str(v) for v in vector)
        return f"[{values}]"

    def _execute_query(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        """执行 SQL 查询。"""
        if params:
            return self.conn.execute(sql, params).fetchall()
        return self.conn.execute(sql).fetchall()

    def _process_results(self, rows: list[Any]) -> list[dict[str, Any]]:
        """处理原始数据库行为结构化结果。"""
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
