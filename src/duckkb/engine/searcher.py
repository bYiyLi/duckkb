import asyncio
import orjson
from typing import List, Dict, Any, Optional
from duckkb.db import get_db
from duckkb.logger import logger
from duckkb.utils.embedding import get_embedding
from duckkb.config import settings

async def smart_search(query: str, limit: int = 10, table_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Perform a hybrid search (Vector Search + Metadata).
    
    Args:
        query: The search query string.
        limit: Max results to return.
        table_filter: Optional filter for source_table.
    """
    if not query:
        return []
        
    # Generate query embedding
    try:
        query_vec = await get_embedding(query)
        if not query_vec:
            return []
    except Exception as e:
        logger.error(f"Search failed during embedding generation: {e}")
        return []
        
    # Prepare SQL
    # Note: We cast parameter to FLOAT[N] to ensure type matching with column
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
    
    # Execute
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
    """
    # 1. Pre-check
    sql_upper = sql.upper()

    # Basic protection against some non-selects (though read_only DB handles most)
    # But user might run PRAGMA etc.
    # Design says: "If no LIMIT and SELECT, append LIMIT 1000"

    if "LIMIT" not in sql_upper and "SELECT" in sql_upper:
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
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        # Return detailed error as struct
        logger.error(f"SQL execution failed: {e}")
        # Design says: "Return structured JSON with error"
        # Since we return List[Dict], we can raise or return a special dict?
        # Better to raise and let MCP handler catch it or return error dict.
        raise ValueError(str(e))
