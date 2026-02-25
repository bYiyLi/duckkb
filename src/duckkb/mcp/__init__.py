"""MCP 服务模块。

提供基于 Model Context Protocol (MCP) 的服务实现，
允许 AI 助手通过标准化接口访问和操作知识库。
"""

from duckkb.mcp.duck_mcp import DuckMCP

__all__ = ["DuckMCP"]
