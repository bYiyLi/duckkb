"""命令行入口模块。

本模块提供 DuckKB 的 CLI 命令和 MCP 服务启动功能。
"""

from pathlib import Path

import typer

from duckkb import __version__
from duckkb.config import AppContext
from duckkb.logger import setup_logging

DEFAULT_KB_PATH = Path("./knowledge-bases/default")

app = typer.Typer()


@app.callback()
def main(
    kb_path: Path = typer.Option(
        DEFAULT_KB_PATH,
        "--kb-path",
        "-k",
        help="Path to knowledge base directory",
    ),
):
    """DuckKB CLI 和 MCP 服务器入口。

    初始化应用上下文并配置日志。

    Args:
        kb_path: 知识库目录路径，默认为 ./knowledge-bases/default。
    """
    if not kb_path.exists():
        kb_path.mkdir(parents=True, exist_ok=True)
    ctx = AppContext.init(kb_path)
    setup_logging(ctx.kb_config.LOG_LEVEL)


@app.command()
def serve():
    """启动 MCP 服务器。

    知识库初始化和关闭时的数据持久化由 FastMCP lifespan 管理。
    """
    from duckkb.mcp.server import mcp

    mcp.run()


@app.command()
def version():
    """显示版本信息。"""
    typer.echo(f"DuckKB v{__version__}")


if __name__ == "__main__":
    app()
