"""命令行入口模块。

本模块提供 DuckKB 的 CLI 命令和 MCP 服务启动功能。
"""

import asyncio
from pathlib import Path

import typer

from duckkb import __version__
from duckkb.config import AppContext
from duckkb.engine.sync import sync_knowledge_base
from duckkb.logger import logger, setup_logging
from duckkb.mcp.server import mcp
from duckkb.schema import init_schema
from duckkb.utils.text import init_jieba_async

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


async def _startup():
    """Startup initialization tasks."""
    logger.info("Starting up...")
    try:
        await init_schema()
        # Initialize jieba in parallel with schema init or just after
        await init_jieba_async()
        # Perform incremental sync from file to DB on startup
        await sync_knowledge_base(AppContext.get().kb_path)
    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        # We continue even if sync fails, so the server can still run (maybe with stale data)
    logger.info("Startup complete.")


@app.command()
def serve():
    """启动 MCP 服务器。

    初始化数据库模式并同步知识库后启动 MCP 服务。
    """
    asyncio.run(_startup())
    mcp.run()


@app.command()
def version():
    """显示版本信息。"""
    typer.echo(f"DuckKB v{__version__}")


if __name__ == "__main__":
    app()
