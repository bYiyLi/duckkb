import asyncio
import re
from typing import Any

import orjson

from duckkb.config import settings
from duckkb.db import get_db
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

    # Clamp alpha
    alpha = max(0.0, min(1.0, alpha))
    vector_w = alpha
    text_w = 1.0 - alpha

    # Generate query embedding
    try:
        query_vec = await get_embedding(query)
        if not query_vec:
            return []
    except Exception as e:
        logger.error(f"Search failed during embedding generation: {e}")
        return []

    # Hybrid Search Logic
    try:
        # Prepare filter
        filter_clause = ""
        filter_params = []
        if table_filter:
            filter_clause = "AND s.source_table = ?"
            filter_params = [table_filter]

        # 1. Vector Search CTE
        # Note: We need to filter here to reduce candidates
        vector_cte = f"""
        vector_search AS (
            SELECT 
                s.rowid, 
                array_cosine_similarity(c.embedding, ?::FLOAT[{settings.EMBEDDING_DIM}]) as score
            FROM _sys_search s
            JOIN _sys_cache c ON s.embedding_id = c.content_hash
            WHERE 1=1 {filter_clause}
            ORDER BY score DESC LIMIT ?
        )"""

        # 2. Text Search CTE
        # Using FTS macro fts_main__sys_search.match_bm25(key, query)
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

        # Combined SQL
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

        # Parameters construction
        params = []
        # Vector params
        params.append(query_vec)
        params.extend(filter_params)
        params.append(limit * 2)

        # Text params
        params.append(query)
        params.append(query)
        params.extend(filter_params)
        params.append(limit * 2)

        # Weight params
        params.append(vector_w)
        params.append(text_w)

        # Final params
        params.append(limit)

        return await asyncio.to_thread(_execute_search, sql, params)

    except Exception as e:
        logger.warning(f"Hybrid search failed, falling back to vector search: {e}")
        # Fallback to pure vector search
        sql = f"""
        SELECT 
            s.ref_id, 
            s.source_table, 
            s.source_field, 
            s.metadata,
            array_cosine_similarity(c.embedding, ?::FLOAT[{settings.EMBEDDING_DIM}]) as similarity
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


def _execute_search(sql: str, params: list) -> list[dict[str, Any]]:
    try:
        with get_db(read_only=True) as conn:
            rows = conn.execute(sql, params).fetchall()

            # Map to dict
            results = []
            for r in rows:
                metadata = r[3]
                # If metadata is returned as string/bytes, parse it
                if isinstance(metadata, str):
                    try:
                        metadata = orjson.loads(metadata)
                    except:
                        pass

                # Check for large result set (simple check)
                # But search usually has LIMIT 10-20, so it's fine.
                # The 2MB limit is mostly for raw SQL query.

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
    # 1. Pre-check
    sql_upper = sql.upper()

    # Forbidden keywords
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
        raise ValueError("Forbidden keyword in SQL query.")

    # Enforce LIMIT
    if "SELECT" in sql_upper and not re.search(r"\bLIMIT\s+\d+", sql_upper):
        sql += " LIMIT 1000"

    return await asyncio.to_thread(_execute_raw, sql)


def _execute_raw(sql: str) -> list[dict[str, Any]]:
    try:
        with get_db(read_only=True) as conn:
            cursor = conn.execute(sql)
            if not cursor.description:
                return []
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]

            # Check result size (approximate via JSON serialization)
            try:
                json_bytes = orjson.dumps(result)
                if len(json_bytes) > 2 * 1024 * 1024:  # 2MB
                    # Truncate or error?
                    # Design doc says: "Query rate limiting: strictly control result set size within 2MB".
                    # It implies we should probably error or truncate.
                    # Let's try to truncate to be friendly.
                    # But we already fetched all.
                    # Let's just return error to force user to use LIMIT.
                    raise ValueError(
                        "Result set size exceeds 2MB limit. Please add LIMIT or refine your query."
                    )
            except ValueError as ve:
                raise ve
            except Exception:
                # If serialization fails, ignore (likely not JSON serializable, but that's another issue)
                pass

            return result
    except Exception as e:
        # Return detailed error as struct
        logger.error(f"SQL execution failed: {e}")
        # Design says: "Return structured JSON with error"
        # Since we return List[Dict], we can raise or return a special dict?
        # Better to raise and let MCP handler catch it or return error dict.
        raise ValueError(str(e))
