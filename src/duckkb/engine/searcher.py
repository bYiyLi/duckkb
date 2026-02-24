import asyncio
import re
from typing import Any

import orjson

from duckkb.config import get_kb_config
from duckkb.constants import QUERY_DEFAULT_LIMIT, QUERY_RESULT_SIZE_LIMIT
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
    """
    Perform a hybrid search (Vector Search + Metadata).

    Args:
        query: The search query string.
        limit: Max results to return.
        table_filter: Optional filter for source_table.
        alpha: Weight for vector search (0.0 to 1.0). Default 0.5.
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
        filter_clause = ""
        filter_params = []
        if table_filter:
            filter_clause = "AND s.source_table = ?"
            filter_params = [table_filter]

        embedding_dim = get_kb_config().EMBEDDING_DIM
        vector_cte = f"""
        vector_search AS (
            SELECT 
                s.rowid, 
                array_cosine_similarity(c.embedding, ?::FLOAT[{embedding_dim}]) as score
            FROM _sys_search s
            JOIN _sys_cache c ON s.embedding_id = c.content_hash
            WHERE 1=1 {filter_clause}
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
        params.append(limit * 2)

        params.append(query)
        params.append(query)
        params.extend(filter_params)
        params.append(limit * 2)

        params.append(vector_w)
        params.append(text_w)

        params.append(limit)

        return await asyncio.to_thread(_execute_search, sql, params)

    except Exception as e:
        logger.warning(f"Hybrid search failed, falling back to vector search: {e}")
        embedding_dim = get_kb_config().EMBEDDING_DIM
        sql = f"""
        SELECT 
            s.ref_id, 
            s.source_table, 
            s.source_field, 
            s.metadata,
            array_cosine_similarity(c.embedding, ?::FLOAT[{embedding_dim}]) as similarity
        FROM _sys_search s
        JOIN _sys_cache c ON s.embedding_id = c.content_hash
        WHERE 1=1
        """
        params = [query_vec]

        if table_filter:
            sql += " AND s.source_table = ?"
            params.append(table_filter)

        sql += " ORDER BY similarity DESC LIMIT ?"
        params.append(limit)

        return await asyncio.to_thread(_execute_search, sql, params)


def _execute_search(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    try:
        with get_db(read_only=True) as conn:
            rows = conn.execute(sql, params).fetchall()

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
    except Exception as e:
        logger.error(f"Search execution failed: {e}")
        return []


async def query_raw_sql(sql: str) -> list[dict[str, Any]]:
    """
    Execute raw SQL safely.

    Safety checks:
    1. Read-only connection.
    2. Auto-limit.
    3. Result size limit (2MB).
    4. Forbidden keywords.
    """
    sql_upper = sql.upper()

    forbidden = [
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "IMPORT",
        "EXPORT",
        "COPY",
        "LOAD",
        "INSTALL",
        "VACUUM",
        "DELETE",
        "UPDATE",
        "DROP",
        "INSERT",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
    ]
    forbidden_pattern = r"\b(" + "|".join(forbidden) + r")\b"
    if re.search(forbidden_pattern, sql_upper):
        raise DatabaseError("Forbidden keyword in SQL query.")

    if "SELECT" in sql_upper and not re.search(r"\bLIMIT\s+\d+", sql_upper):
        sql += f" LIMIT {QUERY_DEFAULT_LIMIT}"

    return await asyncio.to_thread(_execute_raw, sql)


def _execute_raw(sql: str) -> list[dict[str, Any]]:
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
