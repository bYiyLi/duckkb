"""DuckDB 并发读写能力验证测试。

验证 DuckDB 文件模式的并发限制和可行的解决方案。

结论：
- DuckDB Python 绑定不支持同一数据库文件的读写连接同时存在
- 解决方案：单一连接 + 线程安全封装（所有操作通过线程锁串行化）
"""

import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import duckdb
import pytest


class TestDuckDBConcurrency:
    """验证 DuckDB 文件模式的并发能力。"""

    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        """创建临时数据库路径。

        Args:
            tmp_path: pytest 提供的临时目录。

        Returns:
            数据库文件路径。
        """
        return tmp_path / "test.db"

    def test_single_write_connection(self, db_path: Path) -> None:
        """测试单一写连接的基本功能。"""
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
        conn.execute("INSERT INTO test VALUES (1, 'Alice')")
        result = conn.execute("SELECT * FROM test").fetchall()
        assert result == [(1, "Alice")]
        conn.close()

    def test_readonly_connection_after_close(self, db_path: Path) -> None:
        """测试写连接关闭后可以打开只读连接。"""
        writer = duckdb.connect(str(db_path))
        writer.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
        writer.execute("INSERT INTO test VALUES (1, 'Alice')")
        writer.close()

        reader = duckdb.connect(str(db_path), read_only=True)
        result = reader.execute("SELECT * FROM test").fetchall()
        assert result == [(1, "Alice")]
        reader.close()

    def test_multiple_readonly_connections(self, db_path: Path) -> None:
        """测试多个只读连接并发读取（写连接关闭后）。"""
        writer = duckdb.connect(str(db_path))
        writer.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
        writer.execute("INSERT INTO test VALUES (1, 'Alice')")
        writer.close()

        readers = [duckdb.connect(str(db_path), read_only=True) for _ in range(5)]

        for reader in readers:
            result = reader.execute("SELECT * FROM test").fetchall()
            assert result == [(1, "Alice")]

        for reader in readers:
            reader.close()

    def test_read_write_cannot_coexist(self, db_path: Path) -> None:
        """测试读写连接不能同时存在（关键限制）。"""
        writer = duckdb.connect(str(db_path))
        writer.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
        writer.execute("INSERT INTO test VALUES (1, 'Alice')")

        with pytest.raises(duckdb.ConnectionException) as exc_info:
            duckdb.connect(str(db_path), read_only=True)

        assert "different configuration" in str(exc_info.value)
        writer.close()

    def test_multiple_writers_sequential(self, db_path: Path) -> None:
        """测试多个写连接串行写入。"""
        writer1 = duckdb.connect(str(db_path))
        writer1.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
        writer1.execute("INSERT INTO test VALUES (1, 'Alice')")
        writer1.close()

        writer2 = duckdb.connect(str(db_path))
        writer2.execute("INSERT INTO test VALUES (2, 'Bob')")
        result = writer2.execute("SELECT * FROM test ORDER BY id").fetchall()
        assert result == [(1, "Alice"), (2, "Bob")]
        writer2.close()


class TestThreadSafeConnection:
    """测试线程安全连接封装方案。"""

    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        """创建临时数据库路径。"""
        return tmp_path / "test.db"

    def test_thread_safe_wrapper_basic(self, db_path: Path) -> None:
        """测试线程安全封装的基本功能。"""

        class ThreadSafeConnection:
            """线程安全的 DuckDB 连接封装。"""

            def __init__(self, db_path: str) -> None:
                self._conn = duckdb.connect(db_path)
                self._lock = threading.Lock()

            def execute(self, sql: str, params: list | None = None) -> list:
                with self._lock:
                    if params:
                        return self._conn.execute(sql, params).fetchall()
                    return self._conn.execute(sql).fetchall()

            def execute_write(self, sql: str, params: list | None = None) -> None:
                with self._lock:
                    if params:
                        self._conn.execute(sql, params)
                    else:
                        self._conn.execute(sql)

            def begin(self) -> None:
                with self._lock:
                    self._conn.begin()

            def commit(self) -> None:
                with self._lock:
                    self._conn.commit()

            def rollback(self) -> None:
                with self._lock:
                    self._conn.rollback()

            def close(self) -> None:
                with self._lock:
                    self._conn.close()

        conn = ThreadSafeConnection(str(db_path))
        conn.execute_write("CREATE TABLE test (id INTEGER, name VARCHAR)")
        conn.execute_write("INSERT INTO test VALUES (1, 'Alice')")

        result = conn.execute("SELECT * FROM test")
        assert result == [(1, "Alice")]

        conn.close()

    def test_concurrent_reads_with_lock(self, db_path: Path) -> None:
        """测试线程安全封装下的并发读取。"""

        class ThreadSafeConnection:
            def __init__(self, db_path: str) -> None:
                self._conn = duckdb.connect(db_path)
                self._lock = threading.Lock()

            def execute(self, sql: str, params: list | None = None) -> list:
                with self._lock:
                    if params:
                        return self._conn.execute(sql, params).fetchall()
                    return self._conn.execute(sql).fetchall()

            def execute_write(self, sql: str, params: list | None = None) -> None:
                with self._lock:
                    if params:
                        self._conn.execute(sql, params)
                    else:
                        self._conn.execute(sql)

            def close(self) -> None:
                with self._lock:
                    self._conn.close()

        conn = ThreadSafeConnection(str(db_path))
        conn.execute_write("CREATE TABLE test (id INTEGER, name VARCHAR)")
        conn.execute_write("INSERT INTO test VALUES (1, 'Alice')")

        results: list[int] = []
        errors: list[Exception] = []

        def read_task() -> None:
            try:
                for _ in range(10):
                    result = conn.execute("SELECT COUNT(*) FROM test")
                    results.append(result[0][0])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_task) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"读操作出错: {errors}"
        assert len(results) == 50

        conn.close()

    def test_concurrent_read_write_with_lock(self, db_path: Path) -> None:
        """测试线程安全封装下的并发读写。"""

        class ThreadSafeConnection:
            def __init__(self, db_path: str) -> None:
                self._conn = duckdb.connect(db_path)
                self._lock = threading.Lock()

            def execute(self, sql: str, params: list | None = None) -> list:
                with self._lock:
                    if params:
                        return self._conn.execute(sql, params).fetchall()
                    return self._conn.execute(sql).fetchall()

            def execute_write(self, sql: str, params: list | None = None) -> None:
                with self._lock:
                    if params:
                        self._conn.execute(sql, params)
                    else:
                        self._conn.execute(sql)

            def close(self) -> None:
                with self._lock:
                    self._conn.close()

        conn = ThreadSafeConnection(str(db_path))
        conn.execute_write("CREATE TABLE test (id INTEGER, name VARCHAR)")
        conn.execute_write("INSERT INTO test VALUES (1, 'Alice')")

        read_results: list[int] = []
        write_count: list[int] = []
        errors: list[Exception] = []

        def read_task() -> None:
            try:
                for _ in range(10):
                    result = conn.execute("SELECT COUNT(*) FROM test")
                    read_results.append(result[0][0])
            except Exception as e:
                errors.append(e)

        def write_task() -> None:
            try:
                for i in range(2, 12):
                    conn.execute_write(f"INSERT INTO test VALUES ({i}, 'User{i}')")
                    write_count.append(1)
            except Exception as e:
                errors.append(e)

        threads = [
            *([threading.Thread(target=read_task) for _ in range(3)]),
            threading.Thread(target=write_task),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"操作出错: {errors}"
        assert len(read_results) == 30
        assert len(write_count) == 10

        final_count = conn.execute("SELECT COUNT(*) FROM test")[0][0]
        assert final_count == 11

        conn.close()

    @pytest.mark.asyncio
    async def test_async_with_thread_safe_connection(self, db_path: Path) -> None:
        """测试异步环境下的线程安全连接。"""

        class ThreadSafeConnection:
            def __init__(self, db_path: str) -> None:
                self._conn = duckdb.connect(db_path)
                self._lock = threading.Lock()

            def execute(self, sql: str, params: list | None = None) -> list:
                with self._lock:
                    if params:
                        return self._conn.execute(sql, params).fetchall()
                    return self._conn.execute(sql).fetchall()

            def execute_write(self, sql: str, params: list | None = None) -> None:
                with self._lock:
                    if params:
                        self._conn.execute(sql, params)
                    else:
                        self._conn.execute(sql)

            def close(self) -> None:
                with self._lock:
                    self._conn.close()

        conn = ThreadSafeConnection(str(db_path))

        def init_db() -> None:
            conn.execute_write("CREATE TABLE test (id INTEGER, name VARCHAR)")
            conn.execute_write("INSERT INTO test VALUES (1, 'Alice')")

        await asyncio.to_thread(init_db)

        async def read_data() -> int:
            def _read() -> int:
                result = conn.execute("SELECT COUNT(*) FROM test")
                return result[0][0]

            return await asyncio.to_thread(_read)

        async def write_data() -> None:
            def _write() -> None:
                for i in range(2, 12):
                    conn.execute_write(f"INSERT INTO test VALUES ({i}, 'User{i}')")

            await asyncio.to_thread(_write)

        write_task = asyncio.create_task(write_data())
        read_tasks = [asyncio.create_task(read_data()) for _ in range(5)]

        await write_task
        read_results = await asyncio.gather(*read_tasks)

        assert all(r >= 1 for r in read_results)

        final_count = await asyncio.to_thread(lambda: conn.execute("SELECT COUNT(*) FROM test")[0][0])
        assert final_count == 11

        conn.close()


class TestSingleConnectionWithLock:
    """测试单一连接 + 线程锁方案（推荐方案）。"""

    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        """创建临时数据库路径。"""
        return tmp_path / "test.db"

    def test_transaction_with_lock(self, db_path: Path) -> None:
        """测试事务在锁保护下正确执行。"""

        class SafeConnection:
            def __init__(self, db_path: str) -> None:
                self._conn = duckdb.connect(db_path)
                self._lock = threading.Lock()

            @contextmanager
            def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
                with self._lock:
                    try:
                        self._conn.begin()
                        yield self._conn
                        self._conn.commit()
                    except Exception:
                        self._conn.rollback()
                        raise

            def execute(self, sql: str, params: list | None = None) -> list:
                with self._lock:
                    if params:
                        return self._conn.execute(sql, params).fetchall()
                    return self._conn.execute(sql).fetchall()

            def close(self) -> None:
                with self._lock:
                    self._conn.close()

        conn = SafeConnection(str(db_path))

        with conn.transaction() as c:
            c.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
            c.execute("INSERT INTO test VALUES (1, 'Alice')")

        result = conn.execute("SELECT * FROM test")
        assert result == [(1, "Alice")]

        conn.close()

    def test_transaction_rollback(self, db_path: Path) -> None:
        """测试事务回滚。"""

        class SafeConnection:
            def __init__(self, db_path: str) -> None:
                self._conn = duckdb.connect(db_path)
                self._lock = threading.Lock()

            @contextmanager
            def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
                with self._lock:
                    try:
                        self._conn.begin()
                        yield self._conn
                        self._conn.commit()
                    except Exception:
                        self._conn.rollback()
                        raise

            def execute(self, sql: str, params: list | None = None) -> list:
                with self._lock:
                    if params:
                        return self._conn.execute(sql, params).fetchall()
                    return self._conn.execute(sql).fetchall()

            def close(self) -> None:
                with self._lock:
                    self._conn.close()

        conn = SafeConnection(str(db_path))

        with conn.transaction() as c:
            c.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
            c.execute("INSERT INTO test VALUES (1, 'Alice')")

        with pytest.raises(ValueError):
            with conn.transaction() as c:
                c.execute("INSERT INTO test VALUES (2, 'Bob')")
                raise ValueError("Test rollback")

        result = conn.execute("SELECT * FROM test")
        assert result == [(1, "Alice")]

        conn.close()
