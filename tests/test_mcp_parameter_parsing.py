"""测试 MCP 参数解析功能。"""

import pytest

from duckkb.mcp.duck_mcp import _parse_edge_types


class TestParseEdgeTypes:
    """测试 _parse_edge_types 函数。"""

    def test_single_edge_type(self) -> None:
        """测试单个边类型字符串解析。"""
        result = _parse_edge_types("knows")
        assert result == ["knows"]

    def test_multiple_edge_types(self) -> None:
        """测试多个边类型字符串解析。"""
        result = _parse_edge_types("knows,authored,mentions")
        assert result == ["knows", "authored", "mentions"]

    def test_with_whitespace(self) -> None:
        """测试带空格的字符串解析。"""
        result = _parse_edge_types("knows , authored , mentions")
        assert result == ["knows", "authored", "mentions"]

    def test_empty_string(self) -> None:
        """测试空字符串解析。"""
        result = _parse_edge_types("")
        assert result is None

    def test_none_value(self) -> None:
        """测试 None 值解析。"""
        result = _parse_edge_types(None)
        assert result is None

    def test_single_with_spaces(self) -> None:
        """测试单个带空格的边类型。"""
        result = _parse_edge_types(" knows ")
        assert result == ["knows"]

    def test_trailing_comma(self) -> None:
        """测试尾部逗号处理。"""
        result = _parse_edge_types("knows,authored,")
        assert result == ["knows", "authored"]

    def test_multiple_commas(self) -> None:
        """测试连续逗号处理。"""
        result = _parse_edge_types("knows,,authored")
        assert result == ["knows", "authored"]

    def test_only_commas(self) -> None:
        """测试仅逗号字符串。"""
        result = _parse_edge_types(",,")
        assert result is None

    def test_only_whitespace(self) -> None:
        """测试仅空白字符串。"""
        result = _parse_edge_types("   ")
        assert result is None
