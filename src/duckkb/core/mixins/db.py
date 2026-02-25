"""数据库连接管理 Mixin。"""

from pathlib import Path

import duckdb

from duckkb.core.base import BaseEngine
from duckkb.logger import logger


class DBMixin(BaseEngine):
    """数据库连接管理 Mixin。

    负责 DuckDB 连接的创建、管理和关闭。

    Attributes:
        db_path: 数据库文件路径。
        conn: 数据库连接。
    """

    def __init__(self, *args, db_path: Path | str | None = None, **kwargs) -> None:
        """初始化数据库 Mixin。

        Args:
            db_path: 数据库文件路径，默认从 config.storage.data_dir 派生。
        """
        super().__init__(*args, **kwargs)
        self._db_path = Path(db_path) if db_path else None
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def db_path(self) -> Path:
        """数据库文件路径。"""
        if self._db_path is None:
            return self.config.storage.data_dir / "knowledge.db"
        return self._db_path

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """数据库连接（懒加载）。"""
        if self._conn is None:
            self._conn = self._create_connection()
        return self._conn

    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        """创建数据库连接。

        Returns:
            DuckDB 连接实例。
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.db_path))
        logger.debug(f"Database connection established: {self.db_path}")
        return conn

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")
