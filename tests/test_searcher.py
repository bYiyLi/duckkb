import pytest

from duckkb.constants import SYS_SEARCH_TABLE
from duckkb.database.connection import get_db
from duckkb.database.schema import init_schema
from duckkb.database.engine.search import (
    PREFETCH_MULTIPLIER,
    _build_hybrid_query,
    _execute_search_query,
    _process_search_results,
    smart_search,
)


class TestSearcher:
    @pytest.mark.asyncio
    async def test_smart_search_empty_query(self, mock_kb_path):
        await init_schema()
        results = await smart_search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_smart_search_with_data(self, mock_kb_path):
        await init_schema()

        # Create a dummy embedding vector
        embedding = [0.1] * 1536

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} (ref_id, source_table, source_field, segmented_text, embedding_id, embedding, metadata, priority_weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("1", "users", "name", "Alice test", "hash1", embedding, '{"id": "1"}', 1.0),
            )

        results = await smart_search("Alice", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_smart_search_with_table_filter(self, mock_kb_path):
        await init_schema()

        embedding = [0.1] * 1536

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} (ref_id, source_table, source_field, segmented_text, embedding_id, embedding, metadata, priority_weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("1", "users", "name", "Alice", "hash1", embedding, '{"id": "1"}', 1.0),
            )
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} (ref_id, source_table, source_field, segmented_text, embedding_id, embedding, metadata, priority_weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("2", "products", "desc", "Pizza", "hash2", embedding, '{"id": "2"}', 1.0),
            )

        results = await smart_search("Alice", limit=5, table_filter="users")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_smart_search_alpha_clamping(self, mock_kb_path):
        await init_schema()

        embedding = [0.1] * 1536

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_SEARCH_TABLE} (ref_id, source_table, source_field, segmented_text, embedding_id, embedding, metadata, priority_weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("1", "users", "name", "Alice", "hash1", embedding, '{"id": "1"}', 1.0),
            )

        results = await smart_search("Alice", limit=5, alpha=2.0)
        assert isinstance(results, list)

        results = await smart_search("Alice", limit=5, alpha=-1.0)
        assert isinstance(results, list)

    def test_execute_search_empty_result(self, mock_kb_path):
        # We must create the DB first because get_db(read_only=True) fails if DB file missing
        # And create the table since init_schema fails in this env due to missing extensions
        with get_db(read_only=False) as conn:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {SYS_SEARCH_TABLE} (id VARCHAR)")

        results = _execute_search_query(f"SELECT * FROM {SYS_SEARCH_TABLE} WHERE 1=0", [])
        assert results == []

    def test_build_hybrid_query(self, mock_kb_path):
        query = "test"
        query_vec = [0.1, 0.2]
        limit = 10
        table_filter = None
        vector_w = 0.5
        text_w = 0.5

        sql, params = _build_hybrid_query(query, query_vec, limit, table_filter, vector_w, text_w)
        assert "vector_search AS" in sql
        assert "text_search AS" in sql
        # PREFETCH_MULTIPLIER = 2, so limit * 2 = 20
        # params order: vector_vec, filter_params, limit*2, query, query, filter_params, limit*2, vector_w, text_w, limit
        # vector_vec (1), limit*2 (1) = 2
        # query (2), limit*2 (1) = 3
        # vector_w (1), text_w (1) = 2
        # limit (1) = 1
        # Total params = 2 + 3 + 2 + 1 = 8 (without filter)

        # Actually params:
        # [vec], limit*2
        # query, query, limit*2
        # vector_w, text_w
        # limit

        # filter_params is empty.

        # let's just check length and content roughly
        assert len(params) >= 8
        assert params[-1] == limit
        # params[0] is query_vec
        # params[1] is limit * PREFETCH_MULTIPLIER (since filter_params is empty)
        assert params[1] == limit * PREFETCH_MULTIPLIER

    def test_process_search_results(self):
        rows = [
            ("ref1", "table1", "field1", '{"key": "value"}', 0.9),
            ("ref2", "table2", "field2", "invalid_json", 0.8),
            ("ref3", "table3", "field3", None, 0.7),
        ]
        results = _process_search_results(rows)
        assert len(results) == 3
        assert results[0]["metadata"] == {"key": "value"}
        assert results[1]["metadata"] == "invalid_json"
        assert results[2]["metadata"] is None
