import pytest

from duckkb.config import AppContext
from duckkb.constants import SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.engine.searcher import _execute_search, smart_search
from duckkb.schema import init_schema


class TestSearcher:
    @pytest.mark.asyncio
    async def test_smart_search_empty_query(self, mock_kb_path):
        await init_schema()
        results = await smart_search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_smart_search_with_data(self, mock_kb_path):
        await init_schema()

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("1", "users", "name", "Alice test", "hash1", '{"id": "1"}', 1.0),
            )

        results = await smart_search("Alice", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_smart_search_with_table_filter(self, mock_kb_path):
        await init_schema()

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("1", "users", "name", "Alice", "hash1", '{"id": "1"}', 1.0),
            )
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2", "products", "name", "Widget", "hash2", '{"id": "2"}', 1.0),
            )

        results = await smart_search("Alice", limit=5, table_filter="users")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_smart_search_alpha_clamping(self, mock_kb_path):
        await init_schema()

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("1", "users", "name", "Alice", "hash1", '{"id": "1"}', 1.0),
            )

        results = await smart_search("Alice", limit=5, alpha=2.0)
        assert isinstance(results, list)

        results = await smart_search("Alice", limit=5, alpha=-1.0)
        assert isinstance(results, list)

    def test_execute_search_empty_result(self, mock_kb_path):
        results = _execute_search(f"SELECT * FROM {SYS_SEARCH_TABLE} WHERE 1=0", [])
        assert results == []
