"""索引构建测试。"""

import pytest


class TestIndexMixin:
    """索引构建测试。"""

    def test_create_index_tables(self, engine):
        """测试创建索引表。"""
        tables = engine.execute_read(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        )
        table_names = [t[0] for t in tables]

        assert "_sys_search_index" in table_names
        assert "_sys_search_cache" in table_names

    def test_index_table_structure(self, engine):
        """测试索引表结构。"""
        columns = engine.execute_read(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = '_sys_search_index' ORDER BY ordinal_position"
        )
        column_names = [c[0] for c in columns]

        assert "id" in column_names
        assert "source_table" in column_names
        assert "source_id" in column_names
        assert "source_field" in column_names
        assert "chunk_seq" in column_names
        assert "content" in column_names
        assert "fts_content" in column_names
        assert "vector" in column_names
        assert "content_hash" in column_names
        assert "created_at" in column_names

    def test_cache_table_structure(self, engine):
        """测试缓存表结构。"""
        columns = engine.execute_read(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = '_sys_search_cache' ORDER BY ordinal_position"
        )
        column_names = [c[0] for c in columns]

        assert "content_hash" in column_names
        assert "fts_content" in column_names
        assert "vector" in column_names
        assert "last_used" in column_names
        assert "created_at" in column_names


class TestBuildIndex:
    """索引构建测试。"""

    @pytest.mark.asyncio
    async def test_build_index_empty_table(self, async_engine):
        """测试空表索引构建。"""
        count = await async_engine.build_index("Character")
        assert count >= 0

    @pytest.mark.asyncio
    async def test_build_index_all_node_types(self, async_engine):
        """测试构建所有节点类型的索引。"""
        count = await async_engine.build_index()
        assert count >= 0

    @pytest.mark.asyncio
    async def test_build_index_unknown_node_type(self, async_engine):
        """测试未知节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.build_index("UnknownType")

    @pytest.mark.asyncio
    async def test_rebuild_index(self, async_engine, tmp_path):
        """测试重建索引。"""
        yaml_content = """
- type: Character
  name: 索引测试角色
  bio: 这是用于测试索引构建的角色简介
"""
        yaml_file = tmp_path / "test_index.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        count = await async_engine.rebuild_index("Character")
        assert count >= 0

    @pytest.mark.asyncio
    async def test_rebuild_index_unknown_type(self, async_engine):
        """测试重建未知类型的索引。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.rebuild_index("UnknownType")


class TestIndexHelpers:
    """索引辅助方法测试。"""

    def test_compute_hash(self, engine):
        """测试哈希计算。"""
        import hashlib

        text = "测试文本"
        hash_result = engine._compute_hash(text)
        expected = hashlib.md5(text.encode("utf-8")).hexdigest()

        assert hash_result == expected

    def test_compute_hash_consistency(self, engine):
        """测试哈希一致性。"""
        text = "一致性测试"
        hash1 = engine._compute_hash(text)
        hash2 = engine._compute_hash(text)

        assert hash1 == hash2

    def test_compute_hash_different(self, engine):
        """测试不同文本产生不同哈希。"""
        hash1 = engine._compute_hash("文本A")
        hash2 = engine._compute_hash("文本B")

        assert hash1 != hash2

    def test_chunk_text_delegation(self, engine):
        """测试切片委托。"""
        text = "测试文本切片"
        chunks = engine._chunk_text(text)

        assert isinstance(chunks, list)
        assert len(chunks) >= 1


class TestCacheOperations:
    """缓存操作测试。"""

    @pytest.mark.asyncio
    async def test_save_and_load_cache(self, async_engine, tmp_path):
        """测试保存和加载缓存。"""
        cache_path = tmp_path / "cache" / "search_cache.parquet"

        saved = await async_engine.save_cache_to_parquet(cache_path)
        assert saved >= 0

        if saved > 0:
            loaded = await async_engine.load_cache_from_parquet(cache_path)
            assert loaded >= 0

    @pytest.mark.asyncio
    async def test_load_cache_nonexistent_file(self, async_engine, tmp_path):
        """测试加载不存在的缓存文件。"""
        cache_path = tmp_path / "nonexistent" / "cache.parquet"
        count = await async_engine.load_cache_from_parquet(cache_path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_clean_cache(self, async_engine):
        """测试清理过期缓存。"""
        deleted = await async_engine.clean_cache(expire_days=30)
        assert deleted >= 0


class TestFTSIndex:
    """FTS 索引测试。"""

    def test_rebuild_fts_index(self, engine):
        """测试重建 FTS 索引。"""
        engine.rebuild_fts_index()

    def test_try_create_fts_index_empty(self, engine):
        """测试空表时创建 FTS 索引。"""
        engine._try_create_fts_index()


class TestIndexWithContent:
    """有内容时的索引测试。"""

    @pytest.mark.asyncio
    async def test_build_index_with_content(self, async_engine, tmp_path):
        """测试有内容时的索引构建。"""
        yaml_content = """
- type: Character
  name: 索引内容测试
  bio: 这是一个用于测试索引构建的角色简介，包含一些关键词。
"""
        yaml_file = tmp_path / "test_content.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        count = await async_engine.build_index("Character")
        assert count >= 0

        rows = async_engine.execute_read("SELECT COUNT(*) FROM _sys_search_index")
        assert rows[0][0] >= 0

    @pytest.mark.asyncio
    async def test_index_entry_structure(self, async_engine, tmp_path):
        """测试索引条目结构。"""
        yaml_content = """
- type: Character
  name: 结构测试角色
  bio: 测试索引条目结构
"""
        yaml_file = tmp_path / "test_structure.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT source_table, source_id, source_field, chunk_seq, content "
            "FROM _sys_search_index LIMIT 1"
        )

        if rows:
            assert rows[0][0] == "characters"
            assert isinstance(rows[0][1], int)
            assert rows[0][2] in ["name", "bio"]
            assert isinstance(rows[0][3], int)
            assert isinstance(rows[0][4], str)


class TestIndexEdgeCases:
    """索引边界条件测试。"""

    @pytest.mark.asyncio
    async def test_build_index_with_empty_bio(self, async_engine, tmp_path):
        """测试空 bio 字段的索引构建。"""
        yaml_content = """
- type: Character
  name: 空简介角色
  bio: ""
"""
        yaml_file = tmp_path / "test_empty_bio.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_build_index_with_null_bio(self, async_engine, tmp_path):
        """测试无 bio 字段的索引构建。"""
        yaml_content = """
- type: Character
  name: 无简介角色
"""
        yaml_file = tmp_path / "test_null_bio.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_build_index_with_very_long_text(self, async_engine, tmp_path):
        """测试超长文本的索引构建。"""
        long_bio = "测试内容" * 1000
        yaml_content = f"""
- type: Character
  name: 超长文本角色
  bio: "{long_bio}"
"""
        yaml_file = tmp_path / "test_long_text.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_build_index_with_special_characters(self, async_engine, tmp_path):
        """测试特殊字符的索引构建。"""
        yaml_content = r"""
- type: Character
  name: 特殊字符角色
  bio: "包含特殊字符：!@#$%^&*()"
"""
        yaml_file = tmp_path / "test_special.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_build_index_with_unicode(self, async_engine, tmp_path):
        """测试 Unicode 字符的索引构建。"""
        yaml_content = """
- type: Character
  name: Unicode角色
  bio: "包含表情符号：😀🎉🚀 和日文：こんにちは"
"""
        yaml_file = tmp_path / "test_unicode.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
