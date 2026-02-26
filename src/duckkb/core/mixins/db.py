"""数据库连接管理 Mixin。"""

import atexit
import shutil
import tempfile
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from duckkb.core.base import BaseEngine
from duckkb.exceptions import DatabaseError
from duckkb.logger import logger
from duckkb.utils.rwlock import FairReadWriteLock


class DBMixin(BaseEngine):
    """数据库连接管理 Mixin（文件模式 + 公平读写锁）。

    支持多读并发，写入独占，避免写饥饿。
    使用临时目录创建数据库文件，对用户透明。

    Attributes:
        db_path: 临时数据库文件路径。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化数据库 Mixin。"""
        super().__init__(*args, **kwargs)
        self._db_path: Path | None = None
        self._rw_lock = FairReadWriteLock()
        self._cleaned_up = False
        atexit.register(self._cleanup_on_exit)

    @property
    def db_path(self) -> Path:
        """临时数据库文件路径（懒加载）。"""
        if self._db_path is None:
            self._db_path = self._create_temp_db_path()
        return self._db_path

    def _create_temp_db_path(self) -> Path:
        """创建临时数据库文件路径。

        Returns:
            临时数据库文件路径。
        """
        db_config = self.config.database

        if db_config.temp_dir:
            base_dir = db_config.temp_dir
        else:
            base_dir = Path(tempfile.gettempdir()) / "duckkb"

        instance_dir = base_dir / str(uuid.uuid4())[:8]
        instance_dir.mkdir(parents=True, exist_ok=True)

        db_path = instance_dir / "kb.duckdb"
        logger.debug(f"Temp database path created: {db_path}")
        return db_path

    def _ensure_fts_installed(self) -> None:
        """确保 FTS 扩展已安装。

        通过临时写连接安装 FTS 扩展。
        如果扩展已安装，此操作是幂等的（不会重复下载）。

        Raises:
            DatabaseError: FTS 扩展安装失败时抛出。
        """
        conn = duckdb.connect(str(self.db_path), read_only=False)
        try:
            conn.execute("INSTALL fts")
            logger.debug("FTS extension installed successfully")
        except Exception as e:
            logger.error(f"Failed to install FTS extension: {e}")
            raise DatabaseError(f"Failed to install FTS extension: {e}") from e
        finally:
            conn.close()

    def _create_read_connection(self) -> duckdb.DuckDBPyConnection:
        """创建只读连接。

        Returns:
            只读 DuckDB 连接实例。
        """
        conn = duckdb.connect(str(self.db_path), read_only=True)
        try:
            conn.execute("LOAD fts")
        except Exception as e:
            logger.debug(f"Failed to load FTS extension in read-only connection: {e}")
        return conn

    def _create_write_connection(self) -> duckdb.DuckDBPyConnection:
        """创建写连接。

        Returns:
            读写 DuckDB 连接实例。
        """
        conn = duckdb.connect(str(self.db_path), read_only=False)
        conn.execute("INSTALL fts")
        conn.execute("LOAD fts")
        return conn

    def execute_read(self, sql: str, params: list | None = None) -> list:
        """执行读操作（可并发）。

        Args:
            sql: SQL 查询语句。
            params: 查询参数。

        Returns:
            查询结果列表。
        """
        with self._rw_lock.read_lock():
            conn = self._create_read_connection()
            try:
                if params:
                    return conn.execute(sql, params).fetchall()
                return conn.execute(sql).fetchall()
            finally:
                conn.close()

    def execute_write(self, sql: str, params: list | None = None) -> None:
        """执行写操作（独占）。

        Args:
            sql: SQL 语句。
            params: 语句参数。
        """
        with self._rw_lock.write_lock():
            conn = self._create_write_connection()
            try:
                if params:
                    conn.execute(sql, params)
                else:
                    conn.execute(sql)
            finally:
                conn.close()

    def execute_write_with_result(self, sql: str, params: list | None = None) -> list:
        """执行写操作并返回结果（独占）。

        Args:
            sql: SQL 语句。
            params: 语句参数。

        Returns:
            执行结果列表。
        """
        with self._rw_lock.write_lock():
            conn = self._create_write_connection()
            try:
                if params:
                    return conn.execute(sql, params).fetchall()
                return conn.execute(sql).fetchall()
            finally:
                conn.close()

    @contextmanager
    def write_transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """写事务上下文（独占）。

        Yields:
            写连接实例。

        Raises:
            Exception: 事务执行失败时回滚并抛出异常。
        """
        with self._rw_lock.write_lock():
            conn = self._create_write_connection()
            try:
                conn.begin()
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _cleanup_on_exit(self) -> None:
        """程序退出时清理临时文件。"""
        if self._cleaned_up:
            return
        self._cleanup_temp_files()
        self._cleaned_up = True

    def _cleanup_temp_files(self) -> None:
        """清理临时文件。"""
        if self._db_path is None:
            return

        db_config = self.config.database
        if db_config.keep_temp_on_exit:
            logger.debug(f"Keeping temp database: {self._db_path}")
            return

        temp_dir = self._db_path.parent
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")

    def close(self) -> None:
        """关闭连接管理器，清理临时文件。"""
        self._cleanup_temp_files()
        atexit.unregister(self._cleanup_on_exit)
        logger.debug("Database connection manager closed")

    def _table_exists(self, table_name: str) -> bool:
        """检查表是否存在。

        Args:
            table_name: 表名。

        Returns:
            表是否存在。
        """
        sql = """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
        """
        result = self.execute_read(sql, [table_name])
        return result[0][0] > 0

    def _get_table_count(self, table_name: str) -> int:
        """获取表记录数。

        Args:
            table_name: 表名。

        Returns:
            表中记录数。
        """
        if not self._table_exists(table_name):
            return 0
        result = self.execute_read(f'SELECT COUNT(*) FROM "{table_name}"')
        return result[0][0]

    def _get_table_columns(self, table_name: str) -> list[str]:
        """获取表的列名列表。

        Args:
            table_name: 表名。

        Returns:
            列名列表。
        """
        sql = """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'main' AND table_name = ?
            ORDER BY ordinal_position
        """
        result = self.execute_read(sql, [table_name])
        return [row[0] for row in result]
