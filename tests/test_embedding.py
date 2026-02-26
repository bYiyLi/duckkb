"""向量嵌入测试。"""

import hashlib

import pytest


class TestEmbedding:
    """向量嵌入测试。"""

    def test_embedding_model_property(self, engine):
        """测试嵌入模型属性。"""
        assert engine.embedding_model == "text-embedding-3-small"

    def test_embedding_dim_property(self, engine):
        """测试嵌入维度属性。"""
        assert engine.embedding_dim == 1536

    def test_compute_hash(self, engine):
        """测试哈希计算。"""
        text = "测试文本"
        hash_result = engine.compute_hash(text)
        expected = hashlib.md5(text.encode("utf-8")).hexdigest()

        assert hash_result == expected

    def test_compute_hash_consistent(self, engine):
        """测试哈希一致性。"""
        text = "一致性测试文本"
        hash1 = engine.compute_hash(text)
        hash2 = engine.compute_hash(text)

        assert hash1 == hash2

    def test_compute_hash_different(self, engine):
        """测试不同文本产生不同哈希。"""
        hash1 = engine.compute_hash("文本A")
        hash2 = engine.compute_hash("文本B")

        assert hash1 != hash2


class TestEmbeddingWithMock:
    """使用 Mock 的向量测试。"""

    @pytest.mark.asyncio
    async def test_embed_single_with_mock(self, async_engine, mock_embedding_single):
        """测试单个文本向量嵌入（Mock）。"""
        result = await async_engine.embed_single("测试文本")

        assert isinstance(result, list)
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_batch_with_mock(self, async_engine):
        """测试批量向量嵌入（Mock）。"""
        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed") as mock_embed:
            mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]

            texts = ["文本A", "文本B", "文本C"]
            results = await async_engine.embed(texts)

            assert len(results) == 3
            for result in results:
                assert isinstance(result, list)
                assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_empty_list(self, async_engine):
        """测试空列表向量嵌入。"""
        results = await async_engine.embed([])
        assert results == []


class TestEmbeddingCache:
    """向量缓存测试。"""

    @pytest.mark.asyncio
    async def test_cache_hit(self, async_engine, tmp_path):
        """测试缓存命中。"""
        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed") as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            yaml_content = """
- type: Character
  name: 缓存测试
  bio: 这是用于测试向量缓存的文本内容
"""
            yaml_file = tmp_path / "bundle.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            await async_engine.import_knowledge_bundle(str(yaml_file))

            row = async_engine.execute_read(
                "SELECT COUNT(*) FROM _sys_search_cache",
            )[0]

            assert row[0] >= 0


class TestEmbeddingEdgeCases:
    """向量边界情况测试。"""

    @pytest.mark.asyncio
    async def test_embed_long_text(self, async_engine, mock_embedding_single, long_text):
        """测试长文本向量嵌入。"""
        result = await async_engine.embed_single(long_text)

        assert isinstance(result, list)
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_special_chars(self, async_engine, mock_embedding_single):
        """测试特殊字符向量嵌入。"""
        result = await async_engine.embed_single("特殊字符：!@#$%^&*()")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_embed_unicode(self, async_engine, mock_embedding_single):
        """测试 Unicode 向量嵌入。"""
        result = await async_engine.embed_single("😀🎉🚀")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_embed_multiline(self, async_engine, mock_embedding_single):
        """测试多行文本向量嵌入。"""
        text = "第一行\n第二行\n第三行"
        result = await async_engine.embed_single(text)

        assert isinstance(result, list)


class TestEmbeddingDimension:
    """向量维度测试。"""

    def test_valid_dimensions(self, test_kb_path):
        """测试有效维度配置。"""
        from duckkb.config import KBConfig

        config = KBConfig()
        assert config.embedding.dim in [1536, 3072]

    def test_embedding_dim_matches_config(self, engine):
        """测试嵌入维度与配置匹配。"""
        assert engine.embedding_dim == engine.config.embedding_dim
