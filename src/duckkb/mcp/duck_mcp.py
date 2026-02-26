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

    在 MCP 服务启动时初始化引擎并加载已有数据，关闭时清理资源。

    Args:
        server: DuckMCP 实例。

    Yields:
        包含 engine 实例的上下文字典。
    """
    duck_mcp = cast("DuckMCP", server)
    logger.info("Initializing knowledge base engine...")
    await duck_mcp.async_initialize()
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
        self._register_knowledge_intro_tool()
        self._register_import_tool()
        self._register_search_tool()
        self._register_vector_search_tool()
        self._register_fts_search_tool()
        self._register_get_source_record_tool()
        self._register_query_raw_sql_tool()

    def _register_knowledge_intro_tool(self) -> None:
        """注册 get_knowledge_intro 工具。"""

        @self.tool()
        def get_knowledge_intro() -> str:
            """获取知识库介绍。

            返回知识库的完整介绍文档（Markdown 格式），包含：
            - 使用说明：知识库的用途和操作指南
            - 导入数据格式：JSON Schema 和 YAML 示例
            - 表结构：节点表、边表和系统表的 DDL
            - 知识图谱关系：关系详情表格和 Mermaid 图

            Returns:
                Markdown 格式的知识库介绍文档。
            """
            return self.get_knowledge_intro()

    def _register_import_tool(self) -> None:
        """注册 import 工具。"""

        @self.tool(name="import")
        async def import_knowledge(temp_file_path: str) -> str:
            """导入知识数据。

            从 YAML 文件导入数据到知识库。文件格式为数组，每个元素包含：
            - type: 实体类型（节点类型或边类型名称）
            - action: 操作类型（upsert/delete），默认 upsert
            - 节点：identity 字段（根据 get_knowledge_intro 返回的 Schema）
            - 边：source 和 target 对象

            导入前会使用 get_knowledge_intro 返回的 Schema 进行完整校验。
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

    def _register_query_raw_sql_tool(self) -> None:
        """注册 query_raw_sql 工具。"""

        @self.tool()
        async def query_raw_sql(sql: str) -> str:
            """执行只读 SQL 查询。

            安全地执行原始 SQL 查询语句，仅支持 SELECT 操作。
            系统会自动应用 LIMIT 限制，防止返回过多数据。

            安全检查：
            - 只允许 SELECT 查询
            - 禁止危险关键字（INSERT, UPDATE, DELETE 等）
            - 自动添加 LIMIT（默认 1000）
            - 结果大小限制（2MB）

            Args:
                sql: 要执行的 SQL 查询语句，必须是 SELECT 语句。

            Returns:
                JSON 格式的查询结果列表。

            Raises:
                ValueError: SQL 语句不是只读查询时抛出。
            """
            results = await self.query_raw_sql(sql)
            return json.dumps(results, ensure_ascii=False, default=str)

    def _register_search_tool(self) -> None:
        """注册 search 工具。"""

        @self.tool()
        async def search(
            query: str,
            node_type: str | None = None,
            limit: int = 10,
            alpha: float = 0.5,
        ) -> str:
            """智能混合搜索（RRF 融合）。

            结合向量语义检索和全文关键词检索，使用 RRF 算法融合结果。
            向量检索基于语义相似性，全文检索基于关键词匹配。

            Args:
                query: 搜索查询文本。
                node_type: 节点类型过滤器（可选），限定搜索范围到指定节点类型。
                limit: 返回结果数量，默认 10。
                alpha: 向量搜索权重 (0.0-1.0)，默认 0.5。
                    0.0 表示仅使用全文检索，1.0 表示仅使用向量检索。

            Returns:
                JSON 格式的搜索结果列表，每个结果包含：
                - source_table: 源表名
                - source_id: 源记录 ID
                - source_field: 源字段名
                - chunk_seq: 分块序号
                - content: 匹配的文本内容
                - score: 相关性分数
            """
            result = await self.search(
                query,
                node_type=node_type,
                limit=limit,
                alpha=alpha,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

    def _register_vector_search_tool(self) -> None:
        """注册 vector_search 工具。"""

        @self.tool()
        async def vector_search(
            query: str,
            node_type: str | None = None,
            limit: int = 10,
        ) -> str:
            """纯向量语义检索。

            基于向量相似度进行语义检索，适合概念性、模糊性查询。

            Args:
                query: 搜索查询文本。
                node_type: 节点类型过滤器（可选）。
                limit: 返回结果数量，默认 10。

            Returns:
                JSON 格式的搜索结果列表。
            """
            result = await self.vector_search(
                query,
                node_type=node_type,
                limit=limit,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

    def _register_fts_search_tool(self) -> None:
        """注册 fts_search 工具。"""

        @self.tool()
        async def fts_search(
            query: str,
            node_type: str | None = None,
            limit: int = 10,
        ) -> str:
            """纯全文关键词检索。

            基于全文索引进行关键词匹配，适合精确词汇查询。

            Args:
                query: 搜索查询文本。
                node_type: 节点类型过滤器（可选）。
                limit: 返回结果数量，默认 10。

            Returns:
                JSON 格式的搜索结果列表。
            """
            result = await self.fts_search(
                query,
                node_type=node_type,
                limit=limit,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

    def _register_get_source_record_tool(self) -> None:
        """注册 get_source_record 工具。"""

        @self.tool()
        async def get_source_record(
            source_table: str,
            source_id: int,
        ) -> str:
            """根据搜索结果回捞原始业务记录。

            从搜索结果中获取的 source_table 和 source_id，
            查询原始业务表中的完整记录。

            Args:
                source_table: 源表名（来自搜索结果的 source_table 字段）。
                source_id: 源记录 ID（来自搜索结果的 source_id 字段）。

            Returns:
                JSON 格式的原始业务记录，不存在时返回 null。
            """
            result = await self.get_source_record(
                source_table=source_table,
                source_id=source_id,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)
