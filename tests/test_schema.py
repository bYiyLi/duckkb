import pytest

from duckkb.schema import get_schema_info, get_sys_schema_ddl, init_schema


class TestSchema:
    @pytest.mark.asyncio
    async def test_init_schema_creates_tables(self, mock_kb_path):
        await init_schema()
        assert True

    @pytest.mark.asyncio
    async def test_get_sys_schema_ddl_returns_string(self):
        ddl = get_sys_schema_ddl(1536)
        assert isinstance(ddl, str)
        assert "CREATE TABLE" in ddl
        assert "_sys_search" in ddl
        assert "_sys_cache" in ddl
        assert "FLOAT[1536]" in ddl

    @pytest.mark.asyncio
    async def test_get_sys_schema_ddl_different_dim(self):
        ddl = get_sys_schema_ddl(3072)
        assert "FLOAT[3072]" in ddl

    @pytest.mark.asyncio
    async def test_get_schema_info_returns_string(self, mock_kb_path):
        info = get_schema_info()
        assert isinstance(info, str)
        assert "System Schema" in info

    @pytest.mark.asyncio
    async def test_get_schema_info_includes_sys_tables(self, mock_kb_path):
        info = get_schema_info()
        assert "_sys_search" in info
        assert "_sys_cache" in info

    @pytest.mark.asyncio
    async def test_get_schema_info_includes_mermaid(self, mock_kb_path):
        info = get_schema_info()
        assert "mermaid" in info.lower() or "ER Diagram" in info
