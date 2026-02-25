"""DuckTyper - 将知识库引擎暴露为 CLI 命令。"""

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from duckkb import __version__
from duckkb.core.engine import Engine
from duckkb.mcp.duck_mcp import DuckMCP

DEFAULT_KB_PATH = Path("./knowledge-bases/default")


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
        self._register_knowledge_schema_command()
        self._register_import_knowledge_bundle_command()
        self._register_search_commands()

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

    def _register_knowledge_schema_command(self) -> None:
        """注册 get-knowledge-schema 命令。"""

        @self.command("get-knowledge-schema")
        def get_knowledge_schema() -> None:
            """获取知识库校验 Schema。

            返回当前知识库的完整校验规则（JSON Schema Draft 7），
            用于验证 import-knowledge-bundle 的输入数据。
            """
            with Engine(self.kb_path) as engine:
                result = engine.get_bundle_schema()
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def _register_import_knowledge_bundle_command(self) -> None:
        """注册 import-knowledge-bundle 命令。"""

        @self.command("import-knowledge-bundle")
        def import_knowledge_bundle(
            temp_file_path: Path = typer.Argument(
                ...,
                help="YAML 文件路径",
            ),
        ) -> None:
            """导入知识包。

            从 YAML 文件导入数据到知识库。文件格式为数组，每个元素包含：
            - type: 实体类型（节点类型或边类型名称）
            - action: 操作类型（upsert/delete），默认 upsert
            - 节点：identity 字段
            - 边：source 和 target 对象
            """

            async def _import() -> dict[str, Any]:
                with Engine(self.kb_path) as engine:
                    return await engine.import_knowledge_bundle(str(temp_file_path))

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
                with Engine(self.kb_path) as engine:
                    return await engine.search(
                        query,
                        node_type=node_type,
                        limit=limit,
                        alpha=alpha,
                    )

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
                with Engine(self.kb_path) as engine:
                    return await engine.vector_search(
                        query,
                        node_type=node_type,
                        limit=limit,
                    )

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
                with Engine(self.kb_path) as engine:
                    return await engine.fts_search(
                        query,
                        node_type=node_type,
                        limit=limit,
                    )

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
                with Engine(self.kb_path) as engine:
                    return await engine.get_source_record(
                        source_table=source_table,
                        source_id=source_id,
                    )

            result = _run_async(_get())
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    def create_mcp(self, **kwargs: Any) -> DuckMCP:
        """创建 MCP 服务实例。

        Args:
            **kwargs: 传递给 DuckMCP 的参数。

        Returns:
            DuckMCP 实例。
        """
        return DuckMCP(self.kb_path, **kwargs)
