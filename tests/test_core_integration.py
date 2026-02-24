from unittest.mock import AsyncMock, patch

import pytest

from duckkb.constants import DATA_DIR_NAME, SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.engine.indexer import sync_knowledge_base, validate_and_import
from duckkb.engine.searcher import query_raw_sql, smart_search
from duckkb.schema import init_schema

# Mock embedding to return a fixed vector
MOCK_EMBEDDING = [0.1] * 1536


@pytest.fixture
def mock_embedding():
    # Mock the OpenAI client to allow caching logic to run
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_data = AsyncMock()
    mock_data.embedding = MOCK_EMBEDDING
    mock_response.data = [mock_data]
    mock_client.embeddings.create.return_value = mock_response
    
    with patch("duckkb.utils.embedding.get_openai_client", return_value=mock_client):
        yield


@pytest.mark.asyncio
async def test_full_flow(mock_kb_path, mock_embedding):
    """Verify core flow: Init -> Sync -> Search -> Import -> Sync Again."""

    # 1. Init Schema
    init_schema()

    # 2. Create initial data
    data_dir = mock_kb_path / DATA_DIR_NAME
    data_dir.mkdir(parents=True)

    jsonl_content = """{"id": "1", "name": "Alice", "bio": "Alice is a software engineer."}
{"id": "2", "name": "Bob", "bio": "Bob likes pizza."}"""
    (data_dir / "users.jsonl").write_text(jsonl_content, encoding="utf-8")

    # 3. Sync
    await sync_knowledge_base(mock_kb_path)

    # 4. Verify DB content
    with get_db() as conn:
        count = conn.execute(f"SELECT count(*) FROM {SYS_SEARCH_TABLE}").fetchone()[0]
        # 2 records * (name, bio) = 4 rows?
        # id is string, indexed.
        # "name" -> "Alice" -> embedding -> row
        # "bio" -> "Alice is..." -> embedding -> row
        # "id" -> "1" -> embedding -> row
        # So at least 6 rows.
        assert count > 0

    # 5. Search
    results = await smart_search("software", limit=5)
    assert len(results) > 0
    # Check structure
    assert "ref_id" in results[0]
    assert "score" in results[0]

    # 6. Query Raw SQL
    raw = await query_raw_sql(f"SELECT count(*) as c FROM {SYS_SEARCH_TABLE}")
    assert raw[0]["c"] == count

    # 7. Validate and Import (Append)
    temp_file = mock_kb_path / "temp_import.jsonl"
    temp_file.write_text('{"id": "3", "name": "Charlie"}', encoding="utf-8")

    res = await validate_and_import("users", temp_file)
    assert "imported 1 records" in res

    # Check if users.jsonl has 3 lines now
    final_content = (data_dir / "users.jsonl").read_text(encoding="utf-8")
    assert "Charlie" in final_content
    assert "Alice" in final_content

    # Check if DB updated (validate_and_import triggers sync)
    # Sync might take time or be instant? It awaits sync_knowledge_base so instant.
    raw_after = await query_raw_sql(f"SELECT count(*) as c FROM {SYS_SEARCH_TABLE}")
    assert raw_after[0]["c"] > count
