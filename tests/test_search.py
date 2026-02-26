"""搜索测试。"""

import pytest


class TestSearch:
    """搜索测试。"""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, async_engine):
        """测试空查询。"""
        results = await async_engine.search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_content(self, async_engine, tmp_path):
        """测试有内容时的搜索。"""
        yaml_content = """
- type: Character
  name: 搜索测试角色
  bio: 这是一个用于测试搜索功能的角色简介
"""
        yaml_file = tmp_path / "test_search.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import AsyncMock, patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.search("搜索测试", limit=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_node_type_filter(self, async_engine, tmp_path):
        """测试节点类型过滤。"""
        yaml_content = """
- type: Character
  name: 过滤测试角色
  bio: 测试节点类型过滤
"""
        yaml_file = tmp_path / "test_filter.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import AsyncMock, patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.search("测试", node_type="Character", limit=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_invalid_node_type(self, async_engine):
        """测试无效节点类型。"""
        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            with pytest.raises(ValueError, match="Unknown node type"):
                await async_engine.search("测试", node_type="InvalidType")

    @pytest.mark.asyncio
    async def test_search_with_alpha(self, async_engine, tmp_path):
        """测试 alpha 参数。"""
        yaml_content = """
- type: Character
  name: Alpha测试角色
  bio: 测试alpha权重参数
"""
        yaml_file = tmp_path / "test_alpha.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results1 = await async_engine.search("测试", alpha=0.0, limit=5)
            results2 = await async_engine.search("测试", alpha=1.0, limit=5)
            assert isinstance(results1, list)
            assert isinstance(results2, list)


class TestVectorSearch:
    """向量搜索测试。"""

    @pytest.mark.asyncio
    async def test_vector_search_empty_query(self, async_engine):
        """测试空查询向量搜索。"""
        results = await async_engine.vector_search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_vector_search_with_content(self, async_engine, tmp_path):
        """测试有内容时的向量搜索。"""
        yaml_content = """
- type: Character
  name: 向量搜索测试
  bio: 这是用于测试向量搜索的内容
"""
        yaml_file = tmp_path / "test_vector.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.vector_search("向量搜索", limit=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_vector_search_with_node_type_filter(self, async_engine, tmp_path):
        """测试向量搜索节点类型过滤。"""
        yaml_content = """
- type: Character
  name: 向量过滤测试
  bio: 测试向量搜索过滤
"""
        yaml_file = tmp_path / "test_vector_filter.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.vector_search("测试", node_type="Character", limit=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_vector_search_invalid_node_type(self, async_engine):
        """测试向量搜索无效节点类型。"""
        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            with pytest.raises(ValueError, match="Unknown node type"):
                await async_engine.vector_search("测试", node_type="InvalidType")


class TestFtsSearch:
    """全文搜索测试。"""

    @pytest.mark.asyncio
    async def test_fts_search_empty_query(self, async_engine):
        """测试空查询全文搜索。"""
        results = await async_engine.fts_search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_fts_search_with_content(self, async_engine, tmp_path):
        """测试有内容时的全文搜索。"""
        yaml_content = """
- type: Character
  name: 全文搜索测试
  bio: 这是用于测试全文搜索的内容
"""
        yaml_file = tmp_path / "test_fts.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        try:
            results = await async_engine.fts_search("全文搜索", limit=5)
            assert isinstance(results, list)
        except Exception as e:
            from duckkb.exceptions import FTSError

            if isinstance(e, FTSError):
                pytest.skip("FTS extension not available")
            raise

    @pytest.mark.asyncio
    async def test_fts_search_with_node_type_filter(self, async_engine, tmp_path):
        """测试全文搜索节点类型过滤。"""
        yaml_content = """
- type: Character
  name: 全文过滤测试
  bio: 测试全文搜索过滤
"""
        yaml_file = tmp_path / "test_fts_filter.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        try:
            results = await async_engine.fts_search("测试", node_type="Character", limit=5)
            assert isinstance(results, list)
        except Exception as e:
            from duckkb.exceptions import FTSError

            if isinstance(e, FTSError):
                pytest.skip("FTS extension not available")
            raise

    @pytest.mark.asyncio
    async def test_fts_search_invalid_node_type(self, async_engine):
        """测试全文搜索无效节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.fts_search("测试", node_type="InvalidType")


class TestGetSourceRecord:
    """获取原始记录测试。"""

    @pytest.mark.asyncio
    async def test_get_source_record_not_exists(self, async_engine):
        """测试获取不存在的原始记录。"""
        record = await async_engine.get_source_record("characters", 999999999)
        assert record is None

    @pytest.mark.asyncio
    async def test_get_source_record_exists(self, async_engine, tmp_path):
        """测试获取存在的原始记录。"""
        yaml_content = """
- type: Character
  name: 原始记录测试
  bio: 测试获取原始记录
"""
        yaml_file = tmp_path / "test_source.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["原始记录测试"]
        )
        if rows:
            record = await async_engine.get_source_record("characters", rows[0][0])
            assert record is not None
            assert record["name"] == "原始记录测试"

    @pytest.mark.asyncio
    async def test_get_source_record_invalid_table(self, async_engine):
        """测试无效表名。"""
        from duckkb.exceptions import InvalidTableNameError

        with pytest.raises(InvalidTableNameError):
            await async_engine.get_source_record("invalid-table-name", 1)


class TestQueryRawSql:
    """原始 SQL 查询测试。"""

    @pytest.mark.asyncio
    async def test_query_raw_sql_count(self, async_engine):
        """测试 COUNT 查询。"""
        results = async_engine.execute_read("SELECT 1 as count")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_raw_sql_auto_limit(self, async_engine):
        """测试自动添加 LIMIT。"""
        results = await async_engine.query_raw_sql("SELECT 1 as value")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_query_raw_sql_with_limit(self, async_engine):
        """测试带 LIMIT 的查询。"""
        results = await async_engine.query_raw_sql("SELECT 1 as value LIMIT 10")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_query_raw_sql_empty_result(self, async_engine):
        """测试空结果查询。"""
        results = await async_engine.query_raw_sql(
            "SELECT * FROM characters WHERE name = 'nonexistent'"
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_query_raw_sql_select_star(self, async_engine):
        """测试 SELECT * 查询。"""
        results = await async_engine.query_raw_sql("SELECT * FROM characters LIMIT 1")
        assert isinstance(results, list)


class TestSearchHelpers:
    """搜索辅助方法测试。"""

    def test_format_vector_literal(self, engine):
        """测试向量字面量格式化。"""
        vector = [0.1, 0.2, 0.3]
        literal = engine._format_vector_literal(vector)
        assert literal == "[0.1, 0.2, 0.3]"

    def test_format_vector_for_sql(self, engine):
        """测试 SQL 向量格式化。"""
        vector = [0.1, 0.2, 0.3]
        literal = engine._format_vector_for_sql(vector)
        assert "DOUBLE[3]" in literal

    def test_to_float32_array(self, engine):
        """测试转换为 float32 数组。"""
        vector = [0.1, 0.2, 0.3]
        result = engine._to_float32_array(vector)
        assert len(result) == 3

    def test_execute_query(self, engine):
        """测试执行查询。"""
        results = engine.execute_read("SELECT 1 as value")
        assert len(results) == 1
        assert results[0][0] == 1

    def test_process_results_empty(self, engine):
        """测试处理空结果。"""
        results = engine._process_results([])
        assert results == []

    def test_process_results_with_data(self, engine):
        """测试处理有数据的结果。"""
        rows = [("characters", 1, "bio", 0, "test content", 0.85)]
        results = engine._process_results(rows)

        assert len(results) == 1
        assert results[0]["source_table"] == "characters"
        assert results[0]["source_id"] == 1
        assert results[0]["score"] == 0.85

    def test_get_table_columns(self, engine):
        """测试获取表列名。"""
        columns = engine._get_table_columns("characters")
        assert "__id" in columns
        assert "name" in columns

    def test_extract_columns_from_sql(self, engine):
        """测试从 SQL 提取列名。"""
        sql = "SELECT name, bio FROM characters"
        columns = engine._extract_columns_from_sql(sql)
        assert "name" in columns
        assert "bio" in columns

    def test_extract_columns_from_sql_with_alias(self, engine):
        """测试从带别名的 SQL 提取列名。"""
        sql = "SELECT name AS n, bio AS b FROM characters"
        columns = engine._extract_columns_from_sql(sql)
        assert "n" in columns
        assert "b" in columns

    def test_extract_columns_from_sql_star(self, engine):
        """测试从 SELECT * 提取列名。"""
        sql = "SELECT * FROM characters"
        columns = engine._extract_columns_from_sql(sql)
        assert len(columns) > 0


class TestSearchEdgeCases:
    """搜索边界条件测试。"""

    @pytest.mark.asyncio
    async def test_search_with_special_characters(self, async_engine, tmp_path):
        """测试特殊字符搜索。"""
        yaml_content = """
- type: Character
  name: 特殊字符角色
  bio: 包含特殊字符：!@#$%^&*()
"""
        yaml_file = tmp_path / "test_special.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.search("特殊字符", limit=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_unicode(self, async_engine, tmp_path):
        """测试 Unicode 搜索。"""
        yaml_content = """
- type: Character
  name: Unicode角色
  bio: 包含表情符号：😀🎉🚀
"""
        yaml_file = tmp_path / "test_unicode.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.search("Unicode", limit=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_very_long_query(self, async_engine):
        """测试超长查询。"""
        long_query = "测试" * 1000
        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            results = await async_engine.search(long_query, limit=5)
            assert isinstance(results, list)
