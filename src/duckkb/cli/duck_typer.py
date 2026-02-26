"""DuckTyper - 将知识库引擎暴露为 CLI 命令。"""

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from duckkb import __version__
from duckkb.core.engine import Engine
from duckkb.mcp.duck_mcp import DuckMCP

DEFAULT_KB_PATH = Path(".duckkb/default")


def _run_async(coro: Any) -> Any:
    """在同步环境中运行异步协程。

    Args:
        coro: 异步协程对象。

    Returns:
        协程执行结果。
    """
    return asyncio.run(coro)


class DuckTyper(typer.Typer):
    """DuckKB CLI 工具类。

    继承 typer.Typer，通过组合使用 DuckMCP 和 Engine。

    职责：
    - CLI 命令注册与解析
    - 全局选项处理（kb_path）
    - 路由到正确的处理器

    自动注册的命令：
    - serve: 启动 MCP 服务器
    - version: 显示版本信息

    全局选项：
    - --kb-path, -k: 知识库目录路径

    Example:
        ```python
        # 入口文件
        from duckkb.cli import DuckTyper

        app = DuckTyper()

        if __name__ == "__main__":
            app()
        ```

        ```bash
        # 命令行使用
        duckkb --kb-path /path/to/kb serve
        duckkb -k /path/to/kb version
        duckkb version  # 使用默认路径
        ```
    """

    def __init__(self, **kwargs: Any) -> None:
        """初始化 DuckTyper。

        创建 typer.Typer 实例并注册命令。
        kb_path 通过 CLI 选项传入，不在构造函数中指定。

        Args:
            **kwargs: 传递给 typer.Typer 的参数。
        """
        super().__init__(**kwargs)
        self._kb_path: Path | None = None
        self._register_callback()
        self._register_commands()

    @property
    def kb_path(self) -> Path:
        """知识库根目录。

        Raises:
            RuntimeError: 如果 callback 尚未初始化 kb_path。
        """
        if self._kb_path is None:
            raise RuntimeError("kb_path not initialized, callback was not called")
        return self._kb_path

    def _register_callback(self) -> None:
        """注册全局回调（处理 kb_path 选项）。"""

        @self.callback()
        def main(
            kb_path: Path = typer.Option(
                DEFAULT_KB_PATH,
                "--kb-path",
                "-k",
                help="知识库目录路径",
            ),
        ) -> None:
            """DuckKB CLI 和 MCP 服务器入口。

            初始化应用上下文并配置日志。

            Args:
                kb_path: 知识库目录路径，默认为 ./knowledge-bases/default。
            """
            if not kb_path.exists():
                kb_path.mkdir(parents=True, exist_ok=True)
            self._kb_path = kb_path.resolve()

            from duckkb.config import AppContext
            from duckkb.logger import setup_logging

            ctx = AppContext.init(kb_path)
            setup_logging(ctx.kb_config.LOG_LEVEL)

    def _register_commands(self) -> None:
        """注册 CLI 命令。"""
        self._register_serve_command()
        self._register_version_command()
        self._register_info_command()
        self._register_import_command()
        self._register_search_commands()
        self._register_query_raw_sql_command()
        self._register_graph_commands()

    def _register_serve_command(self) -> None:
        """注册 serve 命令。"""

        @self.command()
        def serve() -> None:
            """启动 MCP 服务器。

            知识库初始化和关闭时的数据持久化由 FastMCP lifespan 管理。
            """
            mcp = DuckMCP(self.kb_path)
            mcp.run()

    def _register_version_command(self) -> None:
        """注册 version 命令。"""

        @self.command()
        def version() -> None:
            """显示版本信息。"""
            typer.echo(f"DuckKB v{__version__}")

    def _register_info_command(self) -> None:
        """注册 info 命令。"""

        @self.command("info")
        def info() -> None:
            """获取知识库信息。

            返回知识库的完整介绍文档（Markdown 格式），包含：
            - 使用说明
            - 导入数据格式
            - 表结构
            - 知识图谱关系
            """
            with Engine(self.kb_path) as engine:
                result = engine.get_info()
            typer.echo(result)

    def _register_import_command(self) -> None:
        """注册 import 命令。"""

        @self.command("import")
        def import_knowledge(
            temp_file_path: Path = typer.Argument(
                ...,
                help="YAML 文件路径",
            ),
        ) -> None:
            """导入知识数据。

            从 YAML 文件导入数据到知识库。文件格式为数组，每个元素包含：
            - type: 实体类型（节点类型或边类型名称）
            - action: 操作类型（upsert/delete），默认 upsert
            - 节点：identity 字段
            - 边：source 和 target 对象
            """

            async def _import() -> dict[str, Any]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.import_knowledge_bundle(str(temp_file_path))
                finally:
                    engine.close()

            result = _run_async(_import())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_search_commands(self) -> None:
        """注册搜索相关命令。"""
        self._register_search_command()
        self._register_vector_search_command()
        self._register_fts_search_command()
        self._register_get_source_record_command()

    def _register_search_command(self) -> None:
        """注册 search 命令。"""

        @self.command()
        def search(
            query: str = typer.Argument(..., help="搜索查询文本"),
            node_type: str | None = typer.Option(
                None,
                "--node-type",
                "-t",
                help="节点类型过滤器",
            ),
            limit: int = typer.Option(10, "--limit", "-l", help="返回结果数量"),
            alpha: float = typer.Option(
                0.5,
                "--alpha",
                "-a",
                help="向量搜索权重 (0.0-1.0)",
            ),
        ) -> None:
            """智能混合搜索（RRF 融合）。

            结合向量语义检索和全文关键词检索，使用 RRF 算法融合结果。
            """

            async def _search() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.search(
                        query,
                        node_type=node_type,
                        limit=limit,
                        alpha=alpha,
                    )
                finally:
                    engine.close()

            result = _run_async(_search())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_vector_search_command(self) -> None:
        """注册 vector-search 命令。"""

        @self.command("vector-search")
        def vector_search(
            query: str = typer.Argument(..., help="搜索查询文本"),
            node_type: str | None = typer.Option(
                None,
                "--node-type",
                "-t",
                help="节点类型过滤器",
            ),
            limit: int = typer.Option(10, "--limit", "-l", help="返回结果数量"),
        ) -> None:
            """纯向量语义检索。

            基于向量相似度进行语义检索，适合概念性、模糊性查询。
            """

            async def _search() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.vector_search(
                        query,
                        node_type=node_type,
                        limit=limit,
                    )
                finally:
                    engine.close()

            result = _run_async(_search())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_fts_search_command(self) -> None:
        """注册 fts-search 命令。"""

        @self.command("fts-search")
        def fts_search(
            query: str = typer.Argument(..., help="搜索查询文本"),
            node_type: str | None = typer.Option(
                None,
                "--node-type",
                "-t",
                help="节点类型过滤器",
            ),
            limit: int = typer.Option(10, "--limit", "-l", help="返回结果数量"),
        ) -> None:
            """纯全文关键词检索。

            基于全文索引进行关键词匹配，适合精确词汇查询。
            """

            async def _search() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.fts_search(
                        query,
                        node_type=node_type,
                        limit=limit,
                    )
                finally:
                    engine.close()

            result = _run_async(_search())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_get_source_record_command(self) -> None:
        """注册 get-source-record 命令。"""

        @self.command("get-source-record")
        def get_source_record(
            source_table: str = typer.Option(
                ...,
                "--source-table",
                "-t",
                help="源表名",
            ),
            source_id: int = typer.Option(..., "--source-id", "-i", help="源记录 ID"),
        ) -> None:
            """根据搜索结果回捞原始业务记录。

            从搜索结果中获取的 source_table 和 source_id，
            查询原始业务表中的完整记录。
            """

            async def _get() -> dict[str, Any] | None:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.get_source_record(
                        source_table=source_table,
                        source_id=source_id,
                    )
                finally:
                    engine.close()

            result = _run_async(_get())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_query_raw_sql_command(self) -> None:
        """注册 query-raw-sql 命令。"""

        @self.command("query-raw-sql")
        def query_raw_sql(
            sql: str = typer.Argument(..., help="要执行的 SQL 查询语句"),
        ) -> None:
            """执行只读 SQL 查询。

            安全地执行原始 SQL 查询语句，仅支持 SELECT 操作。
            系统会自动应用 LIMIT 限制，防止返回过多数据。
            """

            async def _query() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.query_raw_sql(sql)
                finally:
                    engine.close()

            result = _run_async(_query())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_graph_commands(self) -> None:
        """注册图谱检索相关命令。"""
        self._register_get_neighbors_command()
        self._register_graph_search_command()
        self._register_traverse_command()
        self._register_extract_subgraph_command()
        self._register_find_paths_command()

    def _register_get_neighbors_command(self) -> None:
        """注册 get-neighbors 命令。"""

        @self.command("get-neighbors")
        def get_neighbors(
            node_type: str = typer.Argument(..., help="节点类型名称"),
            node_id: str = typer.Argument(..., help="节点 ID 或 identity 字段值"),
            edge_types: str | None = typer.Option(
                None,
                "--edge-types",
                "-e",
                help="边类型过滤列表，逗号分隔",
            ),
            direction: str = typer.Option(
                "both",
                "--direction",
                "-d",
                help="遍历方向：out, in, both",
            ),
            limit: int = typer.Option(100, "--limit", "-l", help="返回数量限制"),
        ) -> None:
            """获取节点的邻居节点。

            查询指定节点的直接关联节点，支持按边类型和方向过滤。
            """
            parsed_node_id: int | str
            try:
                parsed_node_id = int(node_id)
            except ValueError:
                parsed_node_id = node_id

            async def _execute() -> dict[str, Any]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.get_neighbors(
                        node_type=node_type,
                        node_id=parsed_node_id,
                        edge_types=[e.strip() for e in edge_types.split(",")]
                        if edge_types
                        else None,
                        direction=direction,
                        limit=limit,
                    )
                finally:
                    engine.close()

            result = _run_async(_execute())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    def _register_graph_search_command(self) -> None:
        """注册 graph-search 命令。"""

        @self.command("graph-search")
        def graph_search(
            query: str = typer.Argument(..., help="查询文本"),
            node_type: str | None = typer.Option(
                None,
                "--node-type",
                "-t",
                help="种子节点类型过滤",
            ),
            edge_types: str | None = typer.Option(
                None,
                "--edge-types",
                "-e",
                help="遍历边类型过滤，逗号分隔",
            ),
            direction: str = typer.Option(
                "both",
                "--direction",
                "-d",
                help="图遍历方向：out, in, both",
            ),
            traverse_depth: int = typer.Option(
                1,
                "--traverse-depth",
                "--depth",
                help="图遍历深度",
            ),
            search_limit: int = typer.Option(
                5,
                "--search-limit",
                help="向量检索返回的种子节点数",
            ),
            neighbor_limit: int = typer.Option(
                10,
                "--neighbor-limit",
                help="每个种子节点的邻居数限制",
            ),
            alpha: float = typer.Option(
                0.5,
                "--alpha",
                "-a",
                help="向量搜索权重 (0.0-1.0)",
            ),
        ) -> None:
            """向量检索 + 图遍历融合检索。

            结合语义检索和图谱遍历，返回语义相关节点及其关联上下文。
            """

            async def _execute() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.graph_search(
                        query=query,
                        node_type=node_type,
                        edge_types=[e.strip() for e in edge_types.split(",")]
                        if edge_types
                        else None,
                        direction=direction,
                        traverse_depth=traverse_depth,
                        search_limit=search_limit,
                        neighbor_limit=neighbor_limit,
                        alpha=alpha,
                    )
                finally:
                    engine.close()

            result = _run_async(_execute())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    def _register_traverse_command(self) -> None:
        """注册 traverse 命令。"""

        @self.command()
        def traverse(
            node_type: str = typer.Argument(..., help="起始节点类型"),
            node_id: str = typer.Argument(..., help="起始节点 ID"),
            edge_types: str | None = typer.Option(
                None,
                "--edge-types",
                "-e",
                help="允许的边类型，逗号分隔",
            ),
            direction: str = typer.Option(
                "out",
                "--direction",
                "-d",
                help="遍历方向：out, in, both",
            ),
            max_depth: int = typer.Option(3, "--max-depth", help="最大遍历深度"),
            limit: int = typer.Option(1000, "--limit", "-l", help="返回结果限制"),
            no_paths: bool = typer.Option(
                False,
                "--no-paths",
                help="仅返回节点列表（不返回路径）",
            ),
        ) -> None:
            """多跳图遍历。

            沿指定边类型进行多跳遍历，返回所有可达节点及其路径信息。
            """
            parsed_node_id: int | str
            try:
                parsed_node_id = int(node_id)
            except ValueError:
                parsed_node_id = node_id

            async def _execute() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.traverse(
                        node_type=node_type,
                        node_id=parsed_node_id,
                        edge_types=[e.strip() for e in edge_types.split(",")]
                        if edge_types
                        else None,
                        direction=direction,
                        max_depth=max_depth,
                        limit=limit,
                        return_paths=not no_paths,
                    )
                finally:
                    engine.close()

            result = _run_async(_execute())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    def _register_extract_subgraph_command(self) -> None:
        """注册 extract-subgraph 命令。"""

        @self.command("extract-subgraph")
        def extract_subgraph(
            node_type: str = typer.Argument(..., help="中心节点类型"),
            node_id: str = typer.Argument(..., help="中心节点 ID"),
            edge_types: str | None = typer.Option(
                None,
                "--edge-types",
                "-e",
                help="包含的边类型，逗号分隔",
            ),
            max_depth: int = typer.Option(2, "--max-depth", help="扩展深度"),
            node_limit: int = typer.Option(100, "--node-limit", help="节点数量上限"),
            edge_limit: int = typer.Option(200, "--edge-limit", help="边数量上限"),
        ) -> None:
            """提取子图。

            以指定节点为中心，提取指定深度范围内的完整子图。
            """
            parsed_node_id: int | str
            try:
                parsed_node_id = int(node_id)
            except ValueError:
                parsed_node_id = node_id

            async def _execute() -> dict[str, Any]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.extract_subgraph(
                        node_type=node_type,
                        node_id=parsed_node_id,
                        edge_types=[e.strip() for e in edge_types.split(",")]
                        if edge_types
                        else None,
                        max_depth=max_depth,
                        node_limit=node_limit,
                        edge_limit=edge_limit,
                    )
                finally:
                    engine.close()

            result = _run_async(_execute())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    def _register_find_paths_command(self) -> None:
        """注册 find-paths 命令。"""

        @self.command("find-paths")
        def find_paths(
            from_type: str = typer.Argument(..., help="起始节点类型"),
            from_id: str = typer.Argument(..., help="起始节点 ID"),
            to_type: str = typer.Argument(..., help="目标节点类型"),
            to_id: str = typer.Argument(..., help="目标节点 ID"),
            edge_types: str | None = typer.Option(
                None,
                "--edge-types",
                "-e",
                help="允许的边类型，逗号分隔",
            ),
            max_depth: int = typer.Option(5, "--max-depth", help="最大路径长度"),
            limit: int = typer.Option(10, "--limit", "-l", help="返回路径数量"),
        ) -> None:
            """查找两节点间的路径。

            查找两个节点之间的所有路径（最短路径优先）。
            """
            parsed_from_id: int | str
            try:
                parsed_from_id = int(from_id)
            except ValueError:
                parsed_from_id = from_id

            parsed_to_id: int | str
            try:
                parsed_to_id = int(to_id)
            except ValueError:
                parsed_to_id = to_id

            async def _execute() -> list[dict[str, Any]]:
                engine = Engine(self.kb_path)
                try:
                    await engine.async_initialize()
                    return await engine.find_paths(
                        from_node=(from_type, parsed_from_id),
                        to_node=(to_type, parsed_to_id),
                        edge_types=[e.strip() for e in edge_types.split(",")]
                        if edge_types
                        else None,
                        max_depth=max_depth,
                        limit=limit,
                    )
                finally:
                    engine.close()

            result = _run_async(_execute())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    def create_mcp(self, **kwargs: Any) -> DuckMCP:
        """创建 MCP 服务实例。

        Args:
            **kwargs: 传递给 DuckMCP 的参数。

        Returns:
            DuckMCP 实例。
        """
        return DuckMCP(self.kb_path, **kwargs)
