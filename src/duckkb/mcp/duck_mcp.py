"""DuckMCP - 将知识库引擎暴露为 MCP 工具。"""

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

    yield {"engine": duck_mcp}

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
        """注册 MCP 工具。

        TODO: 实现完整的工具注册。
        """
        pass
