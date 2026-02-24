import pytest

from duckkb.config import AppContext
from duckkb.utils.text import segment_text


class TestTextSegment:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        AppContext.init(tmp_path)
        yield
        AppContext.reset()

    def test_basic_segmentation(self):
        result = segment_text("我爱编程")
        assert "我" in result
        assert "编程" in result

    def test_empty_string(self):
        result = segment_text("")
        assert result == ""

    def test_whitespace_string(self):
        result = segment_text("   ")
        assert result.strip() == ""

    def test_mixed_chinese_english(self):
        result = segment_text("Python编程很有趣")
        assert "Python" in result
        assert "编程" in result

    def test_search_mode(self):
        result = segment_text("机器学习")
        assert "机器" in result or "学习" in result or "机器学习" in result

    def test_returns_string(self):
        result = segment_text("测试文本")
        assert isinstance(result, str)

    def test_space_separated(self):
        result = segment_text("中文分词测试")
        words = result.split()
        assert len(words) > 0
