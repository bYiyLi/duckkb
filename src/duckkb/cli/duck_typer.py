"""DuckTyper - 将知识库引擎暴露为 CLI 命令。"""

from pathlib import Path
from typing import Any

import typer

from duckkb import __version__
from duckkb.mcp.duck_mcp import DuckMCP

DEFAULT_KB_PATH = Path("./knowledge-bases/default")


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

    def create_mcp(self, **kwargs: Any) -> DuckMCP:
        """创建 MCP 服务实例。

        Args:
            **kwargs: 传递给 DuckMCP 的参数。

        Returns:
            DuckMCP 实例。
        """
        return DuckMCP(self.kb_path, **kwargs)
