"""文本切片测试。"""


class TestChunking:
    """文本切片测试。"""

    def test_chunk_text_short(self, engine):
        """测试短文本切片。"""
        text = "这是一段短文本"
        chunks = engine.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_empty(self, engine):
        """测试空文本切片。"""
        chunks = engine.chunk_text("")
        assert chunks == []

    def test_chunk_text_exact_size(self, engine):
        """测试恰好等于切片大小的文本。"""
        text = "a" * engine.chunk_size
        chunks = engine.chunk_text(text)

        assert len(chunks) == 1
        assert len(chunks[0]) == engine.chunk_size

    def test_chunk_text_long(self, engine, long_text):
        """测试长文本切片。"""
        chunks = engine.chunk_text(long_text)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk) <= engine.chunk_size * 2

    def test_chunk_text_overlap(self, engine):
        """测试切片重叠。"""
        text = "a" * (engine.chunk_size * 2)
        chunks = engine.chunk_text(text)

        assert len(chunks) > 1

    def test_chunk_size_property(self, engine):
        """测试切片大小属性。"""
        assert engine.chunk_size == 800

    def test_chunk_overlap_property(self, engine):
        """测试切片重叠属性。"""
        assert engine.chunk_overlap == 100


class TestChunkBySentence:
    """按句子切片测试。"""

    def test_chunk_by_sentence_short(self, engine):
        """测试短文本按句子切片。"""
        text = "这是第一句。这是第二句。"
        chunks = engine.chunk_by_sentence(text)

        assert len(chunks) >= 1

    def test_chunk_by_sentence_empty(self, engine):
        """测试空文本按句子切片。"""
        chunks = engine.chunk_by_sentence("")
        assert chunks == []

    def test_chunk_by_sentence_with_custom_size(self, engine):
        """测试自定义大小的句子切片。"""
        text = "这是第一句。这是第二句。这是第三句。"
        chunks = engine.chunk_by_sentence(text, max_size=20)

        for chunk in chunks:
            assert len(chunk) <= 20

    def test_chunk_by_sentence_chinese(self, engine):
        """测试中文句子切片。"""
        text = "这是第一句话。这是第二句话。这是第三句话。"
        chunks = engine.chunk_by_sentence(text)

        assert len(chunks) >= 1

    def test_chunk_by_sentence_mixed(self, engine):
        """测试中英混合句子切片。"""
        text = "This is English. 这是中文。Another English sentence."
        chunks = engine.chunk_by_sentence(text)

        assert len(chunks) >= 1


class TestChunkingEdgeCases:
    """切片边界情况测试。"""

    def test_chunk_text_single_char(self, engine):
        """测试单字符文本。"""
        chunks = engine.chunk_text("a")
        assert len(chunks) == 1
        assert chunks[0] == "a"

    def test_chunk_text_whitespace(self, engine):
        """测试空白文本。"""
        chunks = engine.chunk_text("   ")
        assert len(chunks) == 1

    def test_chunk_text_newlines(self, engine):
        """测试包含换行符的文本。"""
        text = "第一行\n第二行\n第三行"
        chunks = engine.chunk_text(text)

        assert len(chunks) >= 1

    def test_chunk_text_unicode(self, engine):
        """测试 Unicode 文本。"""
        text = "😀🎉🚀" * 100
        chunks = engine.chunk_text(text)

        for chunk in chunks:
            assert len(chunk) <= engine.chunk_size + engine.chunk_overlap

    def test_chunk_text_very_long(self, engine):
        """测试超长文本。"""
        text = "a" * 10000
        chunks = engine.chunk_text(text)

        assert len(chunks) > 10
