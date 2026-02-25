"""数据库连接管理 Mixin。"""

import duckdb

from duckkb.core.base import BaseEngine
from duckkb.logger import logger


class DBMixin(BaseEngine):
    """数据库连接管理 Mixin。

    负责 DuckDB 连接的创建、管理和关闭。
    采用内存模式，不产生持久化 .db 文件。

    Attributes:
        conn: 数据库连接。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化数据库 Mixin。"""
        super().__init__(*args, **kwargs)
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """数据库连接（懒加载，内存模式）。"""
        if self._conn is None:
            self._conn = self._create_connection()
        return self._conn

    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        """创建数据库连接（内存模式）。

        DuckDB 仅作为高性能运行时计算层，不产生持久化 .db 文件。
        所有数据从 JSONL 文件加载，真理源于文件。

        Returns:
            DuckDB 连接实例。
        """
        conn = duckdb.connect()
        logger.debug("Database connection established (in-memory mode)")
        return conn

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")
