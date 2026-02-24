"""数据库管理模块。

本模块提供 DuckDB 数据库连接管理功能，包括：
- 数据库连接管理器
- 同步/异步数据库连接上下文
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import duckdb

from duckkb.config import AppContext
from duckkb.constants import BUILD_DIR_NAME, DB_FILE_NAME
from duckkb.logger import logger


class DBManager:
    """数据库管理器类。

    负责管理 DuckDB 数据库文件的路径和连接创建。

    Attributes:
        db_path: 数据库文件的完整路径。
    """

    def __init__(self, kb_path: Path) -> None:
        """初始化数据库管理器。

        Args:
            kb_path: 知识库目录路径。
        """
        self.db_path = kb_path / BUILD_DIR_NAME / DB_FILE_NAME

    def get_connection(self, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        """创建 DuckDB 数据库连接。

        Args:
            read_only: 是否以只读模式打开数据库。

        Returns:
            DuckDB 连接对象。
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.db_path), read_only=read_only)

        # Initialize extensions and settings
        try:
            conn.execute("INSTALL vss; LOAD vss;")
            conn.execute("SET hnsw_enable_experimental_persistence=true;")
        except Exception as e:
            # Might fail if read-only or extension issues, but we try best effort
            logger.warning(f"Failed to load vss extension: {e}")

        return conn


def get_db_manager() -> DBManager:
    """获取数据库管理器实例。

    Returns:
        基于当前应用上下文的 DBManager 实例。
    """
    ctx = AppContext.get()
    return DBManager(ctx.kb_path)


@contextmanager
def get_db(read_only: bool = True) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """获取同步数据库连接的上下文管理器。

    Args:
        read_only: 是否以只读模式打开数据库。

    Yields:
        DuckDB 连接对象，退出上下文时自动关闭。
    """
    manager = get_db_manager()
    conn = manager.get_connection(read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def get_async_db(read_only: bool = True) -> AsyncGenerator[duckdb.DuckDBPyConnection, None]:
    """获取异步数据库连接的上下文管理器。

    通过 asyncio.to_thread 封装同步数据库操作，避免阻塞事件循环。

    Args:
        read_only: 是否以只读模式打开数据库。

    Yields:
        DuckDB 连接对象，退出上下文时自动关闭。
    """
    manager = get_db_manager()
    conn = await asyncio.to_thread(manager.get_connection, read_only=read_only)
    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)
