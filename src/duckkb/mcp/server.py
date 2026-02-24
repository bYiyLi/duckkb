import json
from pathlib import Path

from fastmcp import FastMCP

from duckkb.config import settings
from duckkb.engine.indexer import sync_knowledge_base as _sync
from duckkb.engine.indexer import validate_and_import as _validate
from duckkb.engine.searcher import query_raw_sql as _query
from duckkb.engine.searcher import smart_search as _search
from duckkb.logger import setup_logging
from duckkb.schema import get_schema_info as _get_schema_info
from duckkb.schema import init_schema

# Initialize logging
setup_logging()

# Initialize schema
try:
    init_schema()
except Exception as e:
    import logging

    logging.error(f"Failed to initialize schema: {e}")

# Initialize FastMCP server
mcp = FastMCP("DuckKB")


@mcp.tool()
async def check_health() -> str:
    """Check if the server is running."""
    return "DuckKB is running!"


@mcp.tool()
async def sync_knowledge_base() -> str:
    """Sync the knowledge base from JSONL files to DuckDB."""
    await _sync(settings.KB_PATH)
    return "Synchronization completed."


@mcp.tool()
def get_schema_info() -> str:
    """Return the schema definition and ER diagram info."""
    return _get_schema_info()


@mcp.tool()
async def smart_search(
    query: str, 
    limit: int = 10, 
    table_filter: str | None = None,
    alpha: float = 0.5
) -> str:
    """
    Perform a hybrid search (Vector + Metadata).
    Args:
        query: The search query string.
        limit: Max results to return.
        table_filter: Optional filter for source_table.
        alpha: Weight for vector search (0.0 to 1.0). Default 0.5.
    Returns JSON string of results.
    """
    results = await _search(query, limit, table_filter, alpha)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
async def query_raw_sql(sql: str) -> str:
    """
    Execute raw SQL safely. Returns JSON string.
    Read-only, auto-LIMIT applied.
    """
    results = await _query(sql)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
async def validate_and_import(table_name: str, temp_file_path: str) -> str:
    """
    Validate temp file and move to data dir.
    Args:
        table_name: The target table name (without .jsonl).
        temp_file_path: Absolute path to the temporary JSONL file.
    """
    return await _validate(table_name, Path(temp_file_path))
