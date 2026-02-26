"""搜索测试。"""

import pytest


class TestSearch:
    """搜索测试。"""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, async_engine):
        """测试空查询。"""
        results = await async_engine.search("")
        assert results == []


class TestGetSourceRecord:
    """获取原始记录测试。"""

    @pytest.mark.asyncio
    async def test_get_source_record_not_exists(self, async_engine):
        """测试获取不存在的原始记录。"""
        record = await async_engine.get_source_record("characters", 999999999)
        assert record is None


class TestSearchHelpers:
    """搜索辅助方法测试。"""

    def test_format_vector_literal(self, engine):
        """测试向量字面量格式化。"""
        vector = [0.1, 0.2, 0.3]
        literal = engine._format_vector_literal(vector)
        assert literal == "[0.1, 0.2, 0.3]"

    def test_execute_query(self, engine):
        """测试执行查询。"""
        results = engine.execute_read("SELECT 1 as value")
        assert len(results) == 1
        assert results[0][0] == 1

    def test_process_results_empty(self, engine):
        """测试处理空结果。"""
        results = engine._process_results([])
        assert results == []


class TestQueryRawSql:
    """原始 SQL 查询测试。"""

    @pytest.mark.asyncio
    async def test_query_raw_sql_count(self, async_engine):
        """测试 COUNT 查询。"""
        results = async_engine.execute_read("SELECT 1 as count")
        assert len(results) == 1
