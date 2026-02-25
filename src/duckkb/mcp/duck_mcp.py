"""DuckMCP - 将知识库引擎暴露为 MCP 工具。"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from duckkb.core.engine import Engine
from duckkb.logger import logger


@lifespan
async def engine_lifespan(server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
    """Engine 生命周期管理。

    在 MCP 服务启动时初始化引擎，关闭时清理资源。

    Args:
        server: DuckMCP 实例。

    Yields:
        包含 engine 实例的上下文字典。
    """
    duck_mcp = cast("DuckMCP", server)
    logger.info("Initializing knowledge base engine...")
    duck_mcp.initialize()
    logger.info("Knowledge base engine initialized.")
    try:
        yield {"engine": duck_mcp}
    finally:
        logger.info("Closing knowledge base engine...")
        duck_mcp.close()
        logger.info("Knowledge base engine closed.")


class DuckMCP(Engine, FastMCP):
    """DuckKB MCP 服务类。

    多重继承 Engine 和 FastMCP，将知识库能力暴露为 MCP 工具。

    通过继承 Engine 获得知识库操作能力：
    - 混合检索（向量 + 全文）
    - 索引构建与管理
    - 数据加载与导出
    - 本体管理
    - 知识导入

    通过继承 FastMCP 获得 MCP 服务能力：
    - 工具注册与暴露
    - 多种传输协议（stdio, http, sse）
    - 生命周期管理

    Attributes:
        kb_path: 知识库根目录（来自 Engine）。
        config: 配置对象（来自 Engine）。
        name: MCP 服务名称（来自 FastMCP）。

    Example:
        ```python
        # 开箱即用
        DuckMCP("/path/to/kb").run()

        # 自定义名称
        DuckMCP("/path/to/kb", name="MyKB").run()

        # HTTP 模式
        mcp = DuckMCP("/path/to/kb")
        mcp.run(transport="http", port=8000)
        ```
    """

    def __init__(
        self,
        kb_path: Path | str,
        *,
        name: str = "DuckKB",
        instructions: str | None = None,
        config_path: Path | str | None = None,
        rrf_k: int = 60,
        **kwargs,
    ) -> None:
        """初始化 DuckMCP。

        创建 Engine 实例、FastMCP 实例，并注册工具。

        Args:
            kb_path: 知识库根目录路径。
            name: MCP 服务名称，默认 "DuckKB"。
            instructions: MCP 服务说明。
            config_path: 配置文件路径，默认为 kb_path/config.yaml。
            rrf_k: RRF 常数，默认 60。
            **kwargs: 传递给 FastMCP 的其他参数。
        """
        Engine.__init__(
            self,
            kb_path=kb_path,
            config_path=config_path,
            rrf_k=rrf_k,
        )
        FastMCP.__init__(
            self,
            name=name,
            instructions=instructions,
            lifespan=engine_lifespan,
            **kwargs,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        """注册 MCP 工具。"""
        self._register_knowledge_schema_tool()
        self._register_import_knowledge_bundle_tool()

    def _register_knowledge_schema_tool(self) -> None:
        """注册 get_knowledge_schema 工具。"""
        @self.tool()
        def get_knowledge_schema() -> str:
            """获取知识库校验 Schema。

            返回当前知识库的完整校验规则（JSON Schema Draft 7），
            用于验证 import_knowledge_bundle 的输入数据。

            返回的 Schema 定义了 YAML 文件的合法结构：
            - 根节点为数组类型
            - 每个元素必须包含 type 字段指定实体类型
            - 节点类型需要提供 identity 字段
            - 边类型需要提供 source 和 target 对象

            Returns:
                JSON 格式的 Schema 定义，包含：
                - full_bundle_schema: 完整的 JSON Schema
                - example_yaml: YAML 示例
            """
            result = self.get_bundle_schema()
            return json.dumps(result, ensure_ascii=False, indent=2)

    def _register_import_knowledge_bundle_tool(self) -> None:
        """注册 import_knowledge_bundle 工具。"""
        @self.tool()
        async def import_knowledge_bundle(temp_file_path: str) -> str:
            """导入知识包。

            从 YAML 文件导入数据到知识库。文件格式为数组，每个元素包含：
            - type: 实体类型（节点类型或边类型名称）
            - action: 操作类型（upsert/delete），默认 upsert
            - 节点：identity 字段（根据 get_knowledge_schema 返回的 Schema）
            - 边：source 和 target 对象

            导入前会使用 get_knowledge_schema 返回的 Schema 进行完整校验。
            校验失败会返回精确的错误位置，便于修复。

            导入后自动触发：
            - 索引重建（受影响的节点类型）
            - 持久化导出（JSONL 文件）

            Args:
                temp_file_path: 临时 YAML 文件的绝对路径。

            Returns:
                JSON 格式的操作结果，包含：
                - status: 操作状态
                - nodes: 节点导入统计
                - edges: 边导入统计
                - indexed: 索引构建统计
                - dumped: 持久化导出统计

            Raises:
                ValueError: 校验失败时抛出，包含精确的错误位置。
                FileNotFoundError: 临时文件不存在时抛出。
            """
            result = await self.import_knowledge_bundle(temp_file_path)
            return json.dumps(result, ensure_ascii=False, indent=2)
