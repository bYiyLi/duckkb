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
        rrf_k: RRF 平滑常数（从配置文件读取）。
        _auto_k: 是否启用自适应 k 值。
        _min_k: k 值下限。
        _max_k: k 值上限。
        _thresholds: 自适应阈值配置。
        _strategy: 自适应策略。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化检索 Mixin。

        从配置文件加载 RRF 相关参数：
        - auto_k: 是否启用自适应 k 值
        - k: 固定 k 值（auto_k=false 时使用）
        - min_k, max_k: k 值范围限制
        - strategy: 自适应策略
        - thresholds: 自适应阈值配置
        """
        super().__init__(*args, **kwargs)

        # 从配置加载所有 RRF 参数
        search_config = getattr(self, "config", None)
        if search_config and hasattr(search_config, "search"):
            rrf_config = search_config.search.rrf
            self._auto_k = rrf_config.auto_k
            self._min_k = rrf_config.min_k
            self._max_k = rrf_config.max_k
            self._thresholds = rrf_config.thresholds
            self._strategy = rrf_config.strategy
            self._config_k = rrf_config.k if not self._auto_k else None
        else:
            # 默认值（向后兼容）
            self._auto_k = True
            self._min_k = 5
            self._max_k = 60
            self._thresholds = []
            self._strategy = "document_count"
            self._config_k = None

        self._cached_k = None

        logger.info(
            f"SearchMixin initialized: auto_k={self._auto_k}, "
            f"k_range=[{self._min_k}, {self._max_k}], "
            f"strategy={self._strategy}"
        )

    @property
    def rrf_k(self) -> int:
        """RRF 平滑常数（可能是自适应计算的）。"""
        if self._cached_k is not None:
            return self._cached_k

        # 如果启用自适应，在异步上下文中计算
        if self._auto_k and self._strategy == "document_count":
            # 注意：这里不能直接调用异步方法，需要在异步上下文中使用
            # 默认返回一个合理的值，实际使用时会通过异步方法计算
            if self._thresholds:
                # 使用第一个阈值的 k 值作为默认值
                self._cached_k = self._thresholds[0].k
            else:
                self._cached_k = 10
        else:
            # 使用配置文件的固定值或默认值
            if self._config_k is not None:
                self._cached_k = self._config_k
            else:
                self._cached_k = 10

        return self._cached_k

    async def _calculate_optimal_k(self) -> int:
        """根据数据量和阈值配置计算最优 k 值。"""
        total_docs = await self._get_total_documents()

        # 使用配置的阈值
        if self._thresholds:
            for threshold in self._thresholds:
                if threshold.max_docs is None or total_docs <= threshold.max_docs:
                    k = threshold.k
                    break
            else:
                # 超出所有阈值，使用最大的 k
                k = self._thresholds[-1].k
        else:
            # 默认阈值（向后兼容）
            if total_docs < 10_000:
                k = 10
            elif total_docs < 100_000:
                k = 20
            elif total_docs < 1_000_000:
                k = 40
            else:
                k = 60

        # 应用范围限制
        k = max(self._min_k, min(self._max_k, k))

        logger.debug(f"Auto-calculated k={k} for {total_docs} documents")
        return k

    async def _get_total_documents(self) -> int:
        """获取搜索索引中的文档总数。"""

        def _count() -> int:
            rows = self.execute_read(
                f"SELECT COUNT(DISTINCT (source_table, source_id)) FROM {SEARCH_INDEX_TABLE}"
            )
            return rows[0][0] if rows else 0

        return await asyncio.to_thread(_count)

    async def refresh_k(self) -> int:
        """强制刷新 k 值。

        清除缓存的 k 值，下次搜索时重新计算。

        Returns:
            新计算的 k 值。
        """
        self._cached_k = None
        return self.rrf_k

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
            limit: 返回结果数量，必须 >= 0。
            alpha: 向量搜索权重 (0.0-1.0)。

        Returns:
            排序后的结果列表，包含原始字段和分数。

        Raises:
            ValueError: limit 参数为负数时抛出。
        """
        if limit < 0:
            raise ValueError(f"limit 必须 >= 0，当前值: {limit}")

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
        # 在执行搜索前，确保 k 值已被计算（如果是自适应模式）
        if self._auto_k and self._strategy == "document_count":
            # 重新计算 k 值，覆盖可能的同步访问结果
            optimal_k = await self._calculate_optimal_k()
            self._cached_k = optimal_k

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
                    (
                        COALESCE(1.0 / ({self.rrf_k} + v.rnk), 0.0) * {alpha} 
                        + COALESCE(1.0 / ({self.rrf_k} + f.rnk), 0.0) * {1 - alpha}
                    ) * ({self.rrf_k} + 1) as rrf_score
                FROM vector_search v
                FULL OUTER JOIN fts_search f 
                  ON v.id = f.id
            )
            SELECT 
                r.source_table,
                r.source_id,
                r.source_field,
                r.chunk_seq,
                i.content,
                r.rrf_score as score
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
            limit: 返回结果数量，必须 >= 0。

        Returns:
            排序后的结果列表。

        Raises:
            ValueError: limit 参数为负数时抛出。
        """
        if limit < 0:
            raise ValueError(f"limit 必须 >= 0，当前值: {limit}")

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
            limit: 返回结果数量，必须 >= 0。

        Returns:
            排序后的结果列表。

        Raises:
            ValueError: limit 参数为负数时抛出。
            DatabaseError: FTS 搜索失败时抛出。
        """
        if limit < 0:
            raise ValueError(f"limit 必须 >= 0，当前值: {limit}")

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
            ValueError: SQL 语句类型不允许或结果集大小超限。
            duckdb.Error: SQL 执行失败或包含写操作。
        """
        sql_stripped = sql.strip()
        self._validate_sql_type(sql_stripped)

        if not re.search(r"\bLIMIT\s+\d+", sql_stripped.upper()):
            sql = sql_stripped + f" LIMIT {QUERY_DEFAULT_LIMIT}"

        return await asyncio.to_thread(self._execute_raw_sql_readonly, sql)

    def _validate_sql_type(self, sql: str) -> None:
        """验证 SQL 语句类型，仅允许 SELECT 查询。

        Args:
            sql: SQL 查询字符串。

        Raises:
            ValueError: 当 SQL 不是 SELECT 语句时抛出。
        """
        forbidden_keywords = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "CREATE",
            "TRUNCATE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
            "CALL",
        ]

        sql_upper = sql.upper()
        for keyword in forbidden_keywords:
            if re.search(rf"\b{keyword}\b", sql_upper):
                raise ValueError(f"仅允许 SELECT 查询，检测到禁止的关键字: {keyword}")

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
        for i, row in enumerate(rows):
            row_dict = {}
            for j, value in enumerate(row):
                if j < len(columns):
                    row_dict[columns[j]] = value
                else:
                    row_dict[f"col_{j}"] = value

            # 增加元数据
            row_dict["_meta"] = {
                "rank": i + 1,
                "rrf_k": self.rrf_k,
                "auto_k": self._auto_k,
                "strategy": self._strategy,
            }

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
