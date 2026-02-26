"""MCP 测试。"""

import json
from unittest.mock import patch

import pytest


class TestMCPInit:
    """MCP 初始化测试。"""

    def test_mcp_init(self, test_kb_path):
        """测试 MCP 初始化。"""
        from duckkb.mcp.duck_mcp import DuckMCP

        mcp = DuckMCP(test_kb_path)
        assert mcp is not None
        mcp.close()

    def test_mcp_with_name(self, test_kb_path):
        """测试带名称的 MCP 初始化。"""
        from duckkb.mcp.duck_mcp import DuckMCP

        mcp = DuckMCP(test_kb_path, name="TestMCP")
        assert mcp.name == "TestMCP"
        mcp.close()


class TestMCPTools:
    """MCP 工具测试。"""

    @pytest.mark.asyncio
    async def test_get_knowledge_intro_tool(self, test_kb_path):
        """测试获取知识库介绍工具。"""
        from duckkb.mcp.duck_mcp import DuckMCP

        mcp = DuckMCP(test_kb_path)
        await mcp.async_initialize()

        try:
            result = mcp.get_knowledge_intro()
            assert "# 知识库介绍" in result
            assert "## 使用说明" in result
            assert "## 导入数据格式" in result
            assert "## 表结构" in result
            assert "## 知识图谱关系" in result
        finally:
            mcp.close()

    @pytest.mark.asyncio
    async def test_import_tool(self, test_kb_path, tmp_path):
        """测试导入知识数据工具。"""
        from duckkb.mcp.duck_mcp import DuckMCP

        yaml_content = """
- type: Character
  name: MCP测试角色
  bio: 这是一个通过MCP工具导入的测试角色
"""
        yaml_file = tmp_path / "mcp_bundle.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        mcp = DuckMCP(test_kb_path)
        await mcp.async_initialize()

        try:
            result = await mcp.import_knowledge_bundle(str(yaml_file))
            assert result["status"] == "success"
        finally:
            mcp.close()


class TestMCPLifespan:
    """MCP 生命周期测试。"""

    @pytest.mark.asyncio
    async def test_lifespan_initialize(self, test_kb_path):
        """测试生命周期初始化。"""
        from duckkb.mcp.duck_mcp import DuckMCP

        mcp = DuckMCP(test_kb_path)
        await mcp.async_initialize()

        assert mcp._conn is not None

        mcp.close()

    @pytest.mark.asyncio
    async def test_lifespan_close(self, test_kb_path):
        """测试生命周期关闭。"""
        from duckkb.mcp.duck_mcp import DuckMCP

        mcp = DuckMCP(test_kb_path)
        await mcp.async_initialize()

        mcp.close()

        assert mcp._conn is None
