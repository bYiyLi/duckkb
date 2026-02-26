"""分词测试。"""

import pytest


class TestTokenizer:
    """分词测试。"""

    @pytest.mark.asyncio
    async def test_segment_chinese(self, async_engine):
        """测试中文分词。"""
        text = "这是一个中文分词测试"
        result = await async_engine.segment(text)

        assert isinstance(result, str)
        assert len(result) > 0
        assert " " in result

    @pytest.mark.asyncio
    async def test_segment_empty(self, async_engine):
        """测试空文本分词。"""
        result = await async_engine.segment("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_segment_english(self, async_engine):
        """测试英文分词。"""
        text = "This is an English sentence"
        result = await async_engine.segment(text)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_segment_mixed(self, async_engine):
        """测试中英混合分词。"""
        text = "这是中文 mixed with English"
        result = await async_engine.segment(text)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_segment_batch(self, async_engine):
        """测试批量分词。"""
        texts = ["第一段文本", "第二段文本", "第三段文本"]
        results = await async_engine.segment_batch(texts)

        assert len(results) == 3
        for result in results:
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_segment_batch_empty(self, async_engine):
        """测试空列表批量分词。"""
        results = await async_engine.segment_batch([])
        assert results == []


class TestTokenizerInit:
    """分词器初始化测试。"""

    def test_init_tokenizer(self, engine):
        """测试初始化分词器。"""
        engine.init_tokenizer()
        assert engine._jieba_initialized is True

    def test_init_tokenizer_idempotent(self, engine):
        """测试分词器初始化幂等性。"""
        engine.init_tokenizer()
        engine.init_tokenizer()
        assert engine._jieba_initialized is True

    def test_tokenizer_property(self, engine):
        """测试分词器属性。"""
        assert engine.tokenizer == "jieba"


class TestTokenizerWithUserDict:
    """自定义词典测试。"""

    @pytest.mark.asyncio
    async def test_segment_with_user_dict(self, default_kb_path):
        """测试使用自定义词典分词。"""
        from duckkb.core.engine import Engine

        engine = Engine(default_kb_path)
        await engine.async_initialize()

        try:
            text = "DuckKB是一个向量数据库"
            result = await engine.segment(text)

            assert "DuckKB" in result or "向量数据库" in result
        finally:
            engine.close()


class TestSegmentEdgeCases:
    """分词边界情况测试。"""

    @pytest.mark.asyncio
    async def test_segment_numbers(self, async_engine):
        """测试数字分词。"""
        text = "价格是123.45元"
        result = await async_engine.segment(text)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_segment_punctuation(self, async_engine):
        """测试标点符号分词。"""
        text = "你好，世界！这是测试。"
        result = await async_engine.segment(text)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_segment_special_chars(self, async_engine):
        """测试特殊字符分词。"""
        text = "email@example.com @user #hashtag"
        result = await async_engine.segment(text)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_segment_long_text(self, async_engine, long_text):
        """测试长文本分词。"""
        result = await async_engine.segment(long_text)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_segment_single_char(self, async_engine):
        """测试单字符分词。"""
        result = await async_engine.segment("中")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_segment_whitespace_only(self, async_engine):
        """测试纯空白字符。"""
        result = await async_engine.segment("   ")
        assert isinstance(result, str)
