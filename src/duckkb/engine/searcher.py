"""智能搜索模块。

提供向量搜索和全文搜索的混合搜索功能，支持元数据过滤和结果排序。
"""

import asyncio
import re
from typing import Any

import orjson

from duckkb.config import get_kb_config
from duckkb.constants import (
    PREFETCH_MULTIPLIER,
    QUERY_DEFAULT_LIMIT,
    QUERY_RESULT_SIZE_LIMIT,
)
from duckkb.db import get_db
from duckkb.exceptions import DatabaseError
from duckkb.logger import logger
from duckkb.utils.embedding import get_embedding


async def smart_search(
    query: str,
    limit: int = 10,
    table_filter: str | None = None,
    alpha: float = 0.5,
) -> list[dict[str, Any]]:
    """执行混合搜索（向量搜索 + 元数据搜索）。

    Args:
        query: 搜索查询字符串。
        limit: 返回结果的最大数量。
        table_filter: 可选的源表过滤器。
        alpha: 向量搜索的权重系数（0.0 到 1.0），默认为 0.5。

    Returns:
        包含搜索结果的字典列表，每个字典包含：
        ref_id, source_table, source_field, metadata, score。
    """
    if not query:
        return []

    alpha = max(0.0, min(1.0, alpha))
    vector_w = alpha
    text_w = 1.0 - alpha

    try:
        query_vec = await get_embedding(query)
        if not query_vec:
            return []
    except Exception as e:
        logger.error(f"Search failed during embedding generation: {e}")
        return []

    try:
        sql, params = _build_hybrid_query(query, query_vec, limit, table_filter, vector_w, text_w)
        rows = await asyncio.to_thread(_execute_search_query, sql, params)
        return _process_search_results(rows)

    except Exception as e:
        logger.warning(f"Hybrid search failed, falling back to vector search: {e}")
        try:
            embedding_dim = get_kb_config().EMBEDDING_DIM
            sql = f"""
            SELECT 
                ref_id, 
                source_table, 
                source_field, 
                metadata,
                array_cosine_similarity(embedding, ?::FLOAT[{embedding_dim}]) as similarity
            FROM _sys_search
            WHERE embedding IS NOT NULL
            """
            params = [query_vec]

            if table_filter:
                sql += " AND source_table = ?"
                params.append(table_filter)

            sql += " ORDER BY similarity DESC LIMIT ?"
            params.append(limit)

            rows = await asyncio.to_thread(_execute_search_query, sql, params)
            return _process_search_results(rows)
        except Exception as e:
            logger.error(f"Vector search fallback failed: {e}")
            return []


def _build_hybrid_query(
    query: str,
    query_vec: list[float],
    limit: int,
    table_filter: str | None,
    vector_w: float,
    text_w: float,
) -> tuple[str, list[Any]]:
    """构建混合搜索的 SQL 查询和参数。

    Args:
        query: 搜索查询字符串。
        query_vec: 查询向量。
        limit: 返回结果的最大数量。
        table_filter: 可选的源表过滤器。
        vector_w: 向量搜索权重。
        text_w: 文本搜索权重。

    Returns:
        包含 SQL 字符串和参数列表的元组。
    """
    filter_clause = ""
    filter_params = []
    if table_filter:
        filter_clause = "AND s.source_table = ?"
        filter_params = [table_filter]

    embedding_dim = get_kb_config().EMBEDDING_DIM
    vector_cte = f"""
    vector_search AS (
        SELECT 
            rowid, 
            array_cosine_similarity(embedding, ?::FLOAT[{embedding_dim}]) as score
        FROM _sys_search
        WHERE embedding IS NOT NULL {filter_clause}
        ORDER BY score DESC LIMIT ?
    )"""

    text_cte = f"""
    text_search AS (
        SELECT 
            rowid, 
            fts_main__sys_search.match_bm25(rowid, ?) as score
        FROM _sys_search s
        WHERE fts_main__sys_search.match_bm25(rowid, ?) IS NOT NULL
        {filter_clause}
        ORDER BY score DESC LIMIT ?
    )"""

    sql = f"""
    WITH {vector_cte},
    {text_cte},
    combined AS (
        SELECT rowid, score * ? as score FROM vector_search
        UNION ALL
        SELECT rowid, score * ? as score FROM text_search
    )
    SELECT 
        s.ref_id, 
        s.source_table, 
        s.source_field, 
        s.metadata,
        SUM(c.score) * s.priority_weight as final_score
    FROM combined c
    JOIN _sys_search s ON c.rowid = s.rowid
    GROUP BY s.rowid, s.ref_id, s.source_table, s.source_field, s.metadata, s.priority_weight
    HAVING final_score > 0
    ORDER BY final_score DESC
    LIMIT ?
    """

    params = []
    params.append(query_vec)
    params.extend(filter_params)
    params.append(limit * PREFETCH_MULTIPLIER)

    params.append(query)
    params.append(query)
    params.extend(filter_params)
    params.append(limit * PREFETCH_MULTIPLIER)

    params.append(vector_w)
    params.append(text_w)

    params.append(limit)

    return sql, params


def _execute_search_query(sql: str, params: list[Any]) -> list[Any]:
    """执行搜索查询。

    Args:
        sql: SQL 查询字符串。
        params: 查询参数列表。

    Returns:
        查询返回的行列表。
    """
    with get_db(read_only=True) as conn:
        return conn.execute(sql, params).fetchall()


def _process_search_results(rows: list[Any]) -> list[dict[str, Any]]:
    """处理原始数据库行为结构化结果。

    Args:
        rows: 数据库返回的原始行。

    Returns:
        包含处理结果的字典列表。
    """
    results = []
    for r in rows:
        metadata = r[3]
        if isinstance(metadata, str):
            try:
                metadata = orjson.loads(metadata)
            except orjson.JSONDecodeError:
                pass

        results.append(
            {
                "ref_id": r[0],
                "source_table": r[1],
                "source_field": r[2],
                "metadata": metadata,
                "score": r[4],
            }
        )
    return results


async def query_raw_sql(sql: str) -> list[dict[str, Any]]:
    """安全执行原始 SQL 查询。

    安全检查：
    1. 只允许 SELECT 查询（白名单模式）。
    2. 只读连接。
    3. 自动添加 LIMIT。
    4. 结果大小限制（2MB）。
    5. 禁止子查询中的危险操作。

    Args:
        sql: 原始 SQL 查询字符串。

    Returns:
        表示查询结果的字典列表。

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

    return await asyncio.to_thread(_execute_raw, sql)


def _execute_raw(sql: str) -> list[dict[str, Any]]:
    """执行原始 SQL 查询并返回字典列表形式的结果。

    Args:
        sql: 要执行的 SQL 查询。

    Returns:
        字典列表，键为列名，值为行值。

    Raises:
        ValueError: 结果集大小超限或执行失败。
    """
    try:
        with get_db(read_only=True) as conn:
            cursor = conn.execute(sql)
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
