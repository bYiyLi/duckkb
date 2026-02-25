# 嵌入向量管理与搜索功能增强详细设计

## 一、嵌入向量管理 (EmbeddingMixin)

### 1.1 设计目标

- 集成 OpenAI Embedding API
- 实现嵌入向量缓存，避免重复 API 调用
- 支持批量处理优化
- 支持中文分词预处理

### 1.2 数据模型

#### 缓存表结构

```sql
-- 嵌入向量缓存表
CREATE TABLE IF NOT EXISTS _sys_embedding_cache (
    content_hash VARCHAR PRIMARY KEY,  -- 文本内容哈希 (MD5)
    embedding FLOAT[],                 -- 嵌入向量
    last_used TIMESTAMP,               -- 最后使用时间
    created_at TIMESTAMP               -- 创建时间
);
```

### 1.3 EmbeddingMixin 实现

```python
# src/duckkb/core/mixins/embedding.py

"""嵌入向量管理 Mixin。"""

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from duckkb.core.base import BaseEngine
from duckkb.logger import logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI


class EmbeddingMixin(BaseEngine):
    """嵌入向量管理 Mixin。

    提供文本向量嵌入的获取与缓存功能，支持批量查询和自动缓存。
    通过缓存机制避免重复调用 OpenAI API，降低成本并提升性能。

    Attributes:
        embedding_model: 嵌入模型名称。
        embedding_dim: 嵌入向量维度。
    """

    def __init__(
        self,
        *args,
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536,
        **kwargs,
    ) -> None:
        """初始化嵌入向量 Mixin。

        Args:
            embedding_model: 嵌入模型名称。
            embedding_dim: 嵌入向量维度。
        """
        super().__init__(*args, **kwargs)
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._openai_client: AsyncOpenAI | None = None

    @property
    def embedding_model(self) -> str:
        """嵌入模型名称。"""
        return self._embedding_model

    @property
    def embedding_dim(self) -> int:
        """嵌入向量维度。"""
        return self._embedding_dim

    @property
    def openai_client(self) -> "AsyncOpenAI":
        """OpenAI 客户端（懒加载）。"""
        if self._openai_client is None:
            from openai import AsyncOpenAI
            from duckkb.config import get_global_config
            
            config = get_global_config()
            self._openai_client = AsyncOpenAI(
                api_key=config.OPENAI_API_KEY,
                base_url=config.OPENAI_BASE_URL,
            )
        return self._openai_client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本列表的向量嵌入，支持缓存和批量处理。

        流程：
        1. 计算文本哈希
        2. 批量查询缓存
        3. 对缓存未命中的文本调用 OpenAI API
        4. 将新嵌入存入缓存

        Args:
            texts: 待获取嵌入的文本列表。

        Returns:
            向量嵌入列表，每个元素是与输入文本对应的嵌入向量。
        """
        if not texts:
            return []

        hashes = [self._compute_hash(t) for t in texts]

        # 批量查询缓存
        cached_map = await asyncio.to_thread(
            self._get_cached_embeddings_batch, hashes
        )

        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        for i, h in enumerate(hashes):
            if h in cached_map:
                results[i] = cached_map[h]
            else:
                missing_indices.append(i)
                missing_texts.append(texts[i])

        # 对缓存未命中的文本调用 API
        if missing_texts:
            logger.debug(f"Embedding cache miss: {len(missing_texts)}/{len(texts)}")
            new_embeddings = await self._call_embedding_api(missing_texts)

            # 存入缓存
            missing_hashes = [hashes[i] for i in missing_indices]
            await asyncio.to_thread(
                self._cache_embeddings_batch, missing_hashes, new_embeddings
            )

            for idx, embedding in zip(missing_indices, new_embeddings, strict=True):
                results[idx] = embedding

        return [r if r is not None else [] for r in results]

    async def embed_single(self, text: str) -> list[float]:
        """获取单个文本的向量嵌入。

        Args:
            text: 待获取嵌入的文本。

        Returns:
            文本的向量嵌入列表。
        """
        res = await self.embed([text])
        return res[0] if res else []

    async def embed_node_field(
        self,
        node_type: str,
        field_name: str,
        batch_size: int = 100,
    ) -> int:
        """为节点类型的指定字段生成嵌入向量。

        批量处理节点表中指定字段的文本，生成嵌入向量并更新到表中。

        Args:
            node_type: 节点类型名称。
            field_name: 字段名。
            batch_size: 批处理大小。

        Returns:
            处理的记录数。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table
        vector_column = f"{field_name}_embedding"

        # 检查向量列是否存在，不存在则添加
        self._ensure_vector_column(table_name, vector_column)

        # 获取需要处理的记录
        def _fetch_records() -> list[tuple[int, str]]:
            return self.conn.execute(
                f"SELECT __id, {field_name} FROM {table_name} "
                f"WHERE {field_name} IS NOT NULL AND {vector_column} IS NULL"
            ).fetchall()

        records = await asyncio.to_thread(_fetch_records)
        processed = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            ids = [r[0] for r in batch]
            texts = [r[1] for r in batch]

            embeddings = await self.embed(texts)

            def _update_batch() -> None:
                for j, (record_id, embedding) in enumerate(zip(ids, embeddings)):
                    if embedding:
                        self.conn.execute(
                            f"UPDATE {table_name} SET {vector_column} = ? WHERE __id = ?",
                            [embedding, record_id],
                        )

            await asyncio.to_thread(_update_batch)
            processed += len(batch)

        logger.info(f"Embedded {processed} records for {node_type}.{field_name}")
        return processed

    async def clean_cache(self, expire_days: int = 30) -> int:
        """清理过期的嵌入缓存。

        Args:
            expire_days: 过期天数，默认 30 天。

        Returns:
            删除的缓存条目数。
        """
        def _execute_clean() -> int:
            result = self.conn.execute(
                f"DELETE FROM _sys_embedding_cache "
                f"WHERE last_used < current_timestamp - INTERVAL {expire_days} DAY"
            )
            return result.fetchone()[0] if result else 0

        deleted = await asyncio.to_thread(_execute_clean)
        logger.info(f"Cleaned {deleted} expired embedding cache entries")
        return deleted

    def _ensure_vector_column(self, table_name: str, column_name: str) -> None:
        """确保向量列存在。"""
        try:
            self.conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} FLOAT[{self._embedding_dim}]"
            )
        except Exception:
            pass  # 列已存在

    def _compute_hash(self, text: str) -> str:
        """计算文本哈希。"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _get_cached_embeddings_batch(
        self, hashes: list[str]
    ) -> dict[str, list[float]]:
        """批量查询缓存中的向量嵌入。"""
        if not hashes:
            return {}
        try:
            placeholders = ",".join("?" * len(hashes))
            rows = self.conn.execute(
                f"SELECT content_hash, embedding FROM _sys_embedding_cache "
                f"WHERE content_hash IN ({placeholders})",
                hashes,
            ).fetchall()

            # 更新 last_used
            now = datetime.now(UTC)
            for h, _ in rows:
                self.conn.execute(
                    "UPDATE _sys_embedding_cache SET last_used = ? WHERE content_hash = ?",
                    [now, h],
                )

            return {r[0]: r[1] for r in rows}
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            return {}

    def _cache_embeddings_batch(
        self, hashes: list[str], embeddings: list[list[float]]
    ) -> None:
        """批量存储向量嵌入到缓存。"""
        if not hashes:
            return
        try:
            now = datetime.now(UTC)
            data = [(h, emb, now, now) for h, emb in zip(hashes, embeddings, strict=True)]
            self.conn.executemany(
                "INSERT OR REPLACE INTO _sys_embedding_cache "
                "(content_hash, embedding, last_used, created_at) VALUES (?, ?, ?, ?)",
                data,
            )
        except Exception as e:
            logger.error(f"Failed to cache embeddings: {e}")

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI Embedding API。"""
        try:
            response = await self.openai_client.embeddings.create(
                input=texts, model=self._embedding_model
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            logger.error(f"Failed to call embedding API: {e}")
            raise

    def _init_cache_table(self) -> None:
        """初始化缓存表。"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _sys_embedding_cache (
                content_hash VARCHAR PRIMARY KEY,
                embedding FLOAT[],
                last_used TIMESTAMP,
                created_at TIMESTAMP
            )
        """)
```

### 1.4 使用示例

```python
# 获取嵌入向量
engine = Engine("/path/to/kb")
embeddings = await engine.embed(["文本1", "文本2"])

# 为节点字段生成嵌入
await engine.embed_node_field("document", "content")

# 清理缓存
await engine.clean_cache(expire_days=30)
```

---

## 二、搜索功能增强 (SearchMixin 扩展)

### 2.1 增强目标

- 支持自动嵌入生成（传入文本而非向量）
- 支持向量/全文权重配置
- 支持表过滤器
- 支持降级策略
- 支持结果限制

### 2.2 扩展 SearchMixin

```python
# src/duckkb/core/mixins/search.py (扩展)

class SearchMixin(BaseEngine):
    """检索能力 Mixin - 扩展版。"""

    # ... 现有代码保持不变 ...

    async def smart_search(
        self,
        query: str,
        *,
        node_type: str | None = None,
        vector_column: str = "embedding",
        fts_columns: list[str] | None = None,
        limit: int = 10,
        alpha: float = 0.5,
    ) -> list[dict[str, Any]]:
        """智能混合搜索（自动生成嵌入）。

        这是 search() 的高级封装，自动处理嵌入生成。

        Args:
            query: 搜索查询文本。
            node_type: 节点类型过滤器（可选）。
            vector_column: 向量字段名。
            fts_columns: 全文检索字段列表。
            limit: 返回结果数量。
            alpha: 向量搜索权重 (0.0-1.0)，1-alpha 为全文权重。

        Returns:
            排序后的结果列表。
        """
        # 自动生成查询向量
        query_vector = await self.embed_single(query)
        if not query_vector:
            logger.warning("Failed to generate query embedding")
            return []

        # 如果未指定全文检索字段，尝试从 ontology 获取
        if fts_columns is None and node_type:
            node_def = self.ontology.nodes.get(node_type)
            if node_def and node_def.json_schema:
                props = node_def.json_schema.get("properties", {})
                fts_columns = [k for k, v in props.items() 
                              if v.get("type") == "string" and k != vector_column]

        if node_type:
            return await self.weighted_search(
                node_type=node_type,
                vector_column=vector_column,
                query_vector=query_vector,
                fts_columns=fts_columns or [],
                query_text=query,
                limit=limit,
                vector_weight=alpha,
                text_weight=1.0 - alpha,
            )
        else:
            # 跨表搜索
            return await self.cross_table_search(
                query_vector=query_vector,
                query_text=query,
                vector_column=vector_column,
                limit=limit,
                alpha=alpha,
            )

    async def weighted_search(
        self,
        node_type: str,
        vector_column: str,
        query_vector: list[float],
        fts_columns: list[str],
        query_text: str,
        limit: int = 10,
        vector_weight: float = 0.5,
        text_weight: float = 0.5,
    ) -> list[dict[str, Any]]:
        """加权混合搜索。

        支持自定义向量/全文权重，替代固定 RRF 算法。

        Args:
            node_type: 节点类型名称。
            vector_column: 向量字段名。
            query_vector: 查询向量。
            fts_columns: 全文检索字段列表。
            query_text: 查询文本。
            limit: 返回结果数量。
            vector_weight: 向量搜索权重。
            text_weight: 全文搜索权重。

        Returns:
            排序后的结果列表。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        table_name = node_def.table
        validate_table_name(table_name)

        prefetch_limit = limit * 3
        vector_dim = len(query_vector)
        vector_literal = self._format_vector_literal(query_vector)
        fts_columns_str = ", ".join(fts_columns) if fts_columns else ""
        escaped_query = query_text.replace("'", "''")

        # 构建加权查询
        if fts_columns:
            sql = f"""
            WITH
            vector_search AS (
                SELECT 
                    __id,
                    array_cosine_similarity({vector_column}, {vector_literal}::FLOAT[{vector_dim}]) as score
                FROM {table_name}
                WHERE {vector_column} IS NOT NULL
                ORDER BY score DESC
                LIMIT {prefetch_limit}
            ),
            text_search AS (
                SELECT 
                    __id,
                    fts_score as score
                FROM {table_name}
                WHERE fts_match(({fts_columns_str}), '{escaped_query}')
                ORDER BY score DESC
                LIMIT {prefetch_limit}
            ),
            combined AS (
                SELECT __id, score * {vector_weight} as score FROM vector_search
                UNION ALL
                SELECT __id, score * {text_weight} as score FROM text_search
            )
            SELECT t.*, SUM(c.score) as final_score
            FROM combined c
            JOIN {table_name} t ON c.__id = t.__id
            GROUP BY t.rowid, t.*
            HAVING final_score > 0
            ORDER BY final_score DESC
            LIMIT {limit}
            """
        else:
            # 降级为纯向量搜索
            return await self.vector_search(node_type, vector_column, query_vector, limit)

        try:
            rows = await asyncio.to_thread(self._execute_query, sql)
            return self._process_results(rows)
        except Exception as e:
            logger.warning(f"Weighted search failed, falling back to vector search: {e}")
            return await self.vector_search(node_type, vector_column, query_vector, limit)

    async def cross_table_search(
        self,
        query_vector: list[float],
        query_text: str,
        vector_column: str = "embedding",
        limit: int = 10,
        alpha: float = 0.5,
    ) -> list[dict[str, Any]]:
        """跨表搜索。

        在所有节点表中搜索，合并结果。

        Args:
            query_vector: 查询向量。
            query_text: 查询文本。
            vector_column: 向量字段名。
            limit: 返回结果数量。
            alpha: 向量搜索权重。

        Returns:
            合并后的结果列表，包含 source_table 字段。
        """
        results: list[dict[str, Any]] = []

        for node_name, node_type in self.ontology.nodes.items():
            try:
                node_results = await self.weighted_search(
                    node_type=node_name,
                    vector_column=vector_column,
                    query_vector=query_vector,
                    fts_columns=[],  # 简化：跨表搜索暂不支持全文
                    query_text=query_text,
                    limit=limit,
                    vector_weight=alpha,
                    text_weight=1.0 - alpha,
                )
                for r in node_results:
                    r["_source_table"] = node_type.table
                    r["_node_type"] = node_name
                results.extend(node_results)
            except Exception as e:
                logger.warning(f"Search failed for node type {node_name}: {e}")

        # 按分数排序并截取
        results.sort(key=lambda x: x.get("final_score", x.get("rrf_score", 0)), reverse=True)
        return results[:limit]

    async def query_raw_sql(
        self,
        sql: str,
        default_limit: int = 1000,
        max_size_bytes: int = 2 * 1024 * 1024,
    ) -> list[dict[str, Any]]:
        """安全执行原始 SQL 查询。

        安全检查：
        1. 只允许 SELECT 查询
        2. 自动添加 LIMIT
        3. 结果大小限制

        Args:
            sql: 原始 SQL 查询字符串。
            default_limit: 默认 LIMIT 值。
            max_size_bytes: 结果最大字节数。

        Returns:
            查询结果字典列表。

        Raises:
            DatabaseError: SQL 包含禁止的操作。
        """
        import re
        import orjson

        sql_stripped = sql.strip()
        sql_upper = sql_stripped.upper()

        if not sql_upper.startswith("SELECT"):
            raise DatabaseError("Only SELECT queries are allowed.")

        # 检查禁止的关键字
        forbidden = [
            "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
            "TRUNCATE", "EXEC", "GRANT", "REVOKE", "ATTACH", "DETACH",
            "PRAGMA", "IMPORT", "EXPORT", "COPY", "LOAD", "INSTALL",
            "VACUUM", "BEGIN", "COMMIT", "ROLLBACK",
        ]
        forbidden_pattern = r"\b(" + "|".join(forbidden) + r")\b"
        if re.search(forbidden_pattern, sql_upper):
            raise DatabaseError("Forbidden keyword in SQL query.")

        # 添加 LIMIT
        if not re.search(r"\bLIMIT\s+\d+", sql_upper):
            sql = sql_stripped + f" LIMIT {default_limit}"

        def _execute() -> list[dict[str, Any]]:
            cursor = self.conn.execute(sql)
            if not cursor.description:
                return []
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            result = [dict(zip(columns, row, strict=True)) for row in rows]

            # 检查结果大小
            json_bytes = orjson.dumps(result)
            if len(json_bytes) > max_size_bytes:
                raise ValueError(
                    f"Result size exceeds {max_size_bytes // (1024 * 1024)}MB limit."
                )
            return result

        return await asyncio.to_thread(_execute)
```

### 2.3 使用示例

```python
engine = Engine("/path/to/kb")

# 智能搜索（自动生成嵌入）
results = await engine.smart_search(
    query="知识图谱技术",
    node_type="document",
    alpha=0.7,  # 向量权重 70%
)

# 加权搜索（自定义权重）
results = await engine.weighted_search(
    node_type="document",
    vector_column="content_embedding",
    query_vector=vector,
    fts_columns=["title", "content"],
    query_text="知识图谱",
    vector_weight=0.6,
    text_weight=0.4,
)

# 跨表搜索
results = await engine.cross_table_search(
    query_vector=vector,
    query_text="查询文本",
    limit=20,
)

# 安全 SQL 查询
results = await engine.query_raw_sql(
    "SELECT * FROM documents WHERE category = 'tech' LIMIT 100"
)
```

---

## 三、Engine 类更新

```python
# src/duckkb/core/engine.py

class Engine(
    ConfigMixin,
    DBMixin,
    OntologyMixin,
    StorageMixin,
    EmbeddingMixin,  # 新增
    SearchMixin,
):
    """知识库引擎 - 完整版。"""

    def __init__(
        self,
        kb_path: Path | str,
        *,
        config_path: Path | str | None = None,
        db_path: Path | str | None = None,
        rrf_k: int = 60,
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536,
    ) -> None:
        super().__init__(
            kb_path=kb_path,
            config_path=config_path,
            db_path=db_path,
            rrf_k=rrf_k,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )

    def initialize(self) -> Self:
        """初始化引擎。"""
        self.sync_schema()
        self._init_cache_table()  # 初始化嵌入缓存表
        return self
```

---

## 四、文件结构更新

```
src/duckkb/core/
├── __init__.py
├── base.py
├── engine.py
├── config/
│   └── models.py
└── mixins/
    ├── __init__.py
    ├── config.py
    ├── db.py
    ├── ontology.py
    ├── storage.py
    ├── embedding.py    # 新增
    └── search.py       # 扩展
```

---

## 五、依赖关系

```
EmbeddingMixin
    ├── 依赖: BaseEngine (conn, kb_config)
    └── 被依赖: SearchMixin (smart_search)

SearchMixin
    ├── 依赖: BaseEngine (conn, ontology)
    ├── 依赖: EmbeddingMixin (embed_single) - 可选
    └── 提供: search, vector_search, fts_search, smart_search, weighted_search, cross_table_search
```
