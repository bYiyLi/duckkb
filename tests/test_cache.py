import pytest

from duckkb.constants import SYS_CACHE_TABLE
from duckkb.database.connection import get_db
from duckkb.database.schema import init_schema
from duckkb.database.engine.cache import _execute_gc, clean_cache


class TestCache:
    @pytest.mark.asyncio
    async def test_clean_cache_runs_without_error(self, mock_kb_path):
        await init_schema()
        await clean_cache()
        assert True

    @pytest.mark.asyncio
    async def test_execute_gc_removes_old_entries(self, mock_kb_path):
        await init_schema()

        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT INTO {SYS_CACHE_TABLE} (content_hash, embedding, last_used) VALUES (?, ?, current_timestamp - INTERVAL 60 DAY)",
                ["old_hash", [0.1] * 1536],
            )
            conn.execute(
                f"INSERT INTO {SYS_CACHE_TABLE} (content_hash, embedding, last_used) VALUES (?, ?, current_timestamp)",
                ["new_hash", [0.2] * 1536],
            )

        _execute_gc()

        with get_db() as conn:
            count = conn.execute(f"SELECT count(*) FROM {SYS_CACHE_TABLE}").fetchone()[0]
            assert count == 1
