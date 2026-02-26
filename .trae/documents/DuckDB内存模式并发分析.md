# DuckKB 并发问题分析与解决方案

## 1. 当前架构分析

### 1.1 数据库连接模式

当前 DuckKB 使用 **纯内存模式**：

```python
# src/duckkb/core/mixins/db.py
def _create_connection(self) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()  # 无参数 = 内存模式
    return conn
```

### 1.2 并发操作方式

所有数据库操作通过 `asyncio.to_thread()` 在线程池中执行：

```python
# 示例：search.py
rows = await asyncio.to_thread(self._execute_query, sql, fts_params)
```

### 1.3 当前并发风险

| 风险点 | 描述 |
|--------|------|
| 连接非线程安全 | DuckDB 连接对象本身不是线程安全的 |
| 无锁保护 | 多个协程可能同时调用 `self.conn` 执行操作 |
| 乐观并发冲突 | 同时更新相同行会触发 `Transaction conflict` 错误 |

---

## 2. DuckDB 并发限制（已验证）

### 2.1 核心限制

根据测试文件 `tests/test_duckdb_concurrency.py` 的验证：

| 场景 | 是否支持 | 测试用例 |
|------|----------|----------|
| 单一写连接 | ✅ | `test_single_write_connection` |
| 写连接关闭后打开只读连接 | ✅ | `test_readonly_connection_after_close` |
| 多个只读连接并发读取（写连接关闭后） | ✅ | `test_multiple_readonly_connections` |
| **读写连接同时存在** | ❌ | `test_read_write_cannot_coexist` |
| 多个写连接串行写入 | ✅ | `test_multiple_writers_sequential` |

### 2.2 关键结论

**DuckDB 文件模式不支持读写连接同时存在，但支持：**
- 写连接关闭后，多个只读连接并发读取
- 多个写连接串行写入（一次只有一个写连接）

---

## 3. 推荐方案：文件模式 + 公平读写锁

### 3.1 写饥饿问题

**问题**：如果使用普通读写锁，当读操作持续不断时，写操作可能永远无法获得锁。

```
时间线 →

读线程1: [读锁][查询][释放]                                   
读线程2:        [读锁][查询][释放]                            
读线程3:              [读锁][查询][释放]                      
读线程4:                    [读锁][查询][释放]                
读线程5:                          [读锁][查询][释放]          
写线程:  [等待................................................] 永远等待！
```

### 3.2 解决方案：公平读写锁（Fair RWLock）

**公平锁策略**：当有写请求在等待时，新的读请求必须排队等待写请求完成。

```
时间线 →

读线程1: [读锁][查询][释放]                                   
读线程2:        [读锁][查询][释放]                            
写线程:               [排队等待...] [写锁][写入][释放]
读线程3:                            [排队等待...][读锁][查询][释放]
读线程4:                                        [读锁][查询][释放]

特点：
- 写请求到达后，新的读请求必须等待
- 保证写操作最终能够执行
- 牺牲部分读并发性能，避免写饥饿
```

### 3.3 公平读写锁实现

```python
import threading
from contextlib import contextmanager
from typing import Generator


class FairReadWriteLock:
    """公平读写锁（避免写饥饿）。

    当有写请求在等待时，新的读请求必须排队。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._read_ready = threading.Condition(self._lock)
        self._reader_count = 0
        self._writer_waiting = 0
        self._writer_active = False

    @contextmanager
    def read_lock(self) -> Generator[None, None, None]:
        """获取读锁。

        如果有写请求在等待，新的读请求必须排队。
        """
        with self._lock:
            while self._writer_active or self._writer_waiting > 0:
                self._read_ready.wait()
            self._reader_count += 1
        try:
            yield
        finally:
            with self._lock:
                self._reader_count -= 1
                if self._reader_count == 0:
                    self._read_ready.notify_all()

    @contextmanager
    def write_lock(self) -> Generator[None, None, None]:
        """获取写锁（独占）。"""
        with self._lock:
            self._writer_waiting += 1
            while self._reader_count > 0 or self._writer_active:
                self._read_ready.wait()
            self._writer_waiting -= 1
            self._writer_active = True
        try:
            yield
        finally:
            with self._lock:
                self._writer_active = False
                self._read_ready.notify_all()
```

### 3.4 使用 `readerwriterlock` 库（推荐）

```bash
pip install readerwriterlock
```

```python
from readerwriterlock import rwlock

class DuckDBConnectionManager:
    """DuckDB 文件模式连接管理器。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._rw_lock = rwlock.RWLockFair()  # 公平读写锁，避免写饥饿

    def read(self, sql: str, params: list | None = None) -> list:
        """读操作（可并发，但有写等待时需排队）。"""
        with self._rw_lock.gen_rlock():
            conn = duckdb.connect(self._db_path, read_only=True)
            try:
                if params:
                    return conn.execute(sql, params).fetchall()
                return conn.execute(sql).fetchall()
            finally:
                conn.close()

    def write(self, sql: str, params: list | None = None) -> None:
        """写操作（独占）。"""
        with self._rw_lock.gen_wlock():
            conn = duckdb.connect(self._db_path, read_only=False)
            try:
                if params:
                    conn.execute(sql, params)
                else:
                    conn.execute(sql)
            finally:
                conn.close()
```

### 3.5 完整实现（异步友好）

```python
import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import duckdb

from duckkb.core.base import BaseEngine
from duckkb.logger import logger


class FairReadWriteLock:
    """公平读写锁（避免写饥饿）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._read_ready = threading.Condition(self._lock)
        self._reader_count = 0
        self._writer_waiting = 0
        self._writer_active = False

    @contextmanager
    def read_lock(self) -> Generator[None, None, None]:
        with self._lock:
            while self._writer_active or self._writer_waiting > 0:
                self._read_ready.wait()
            self._reader_count += 1
        try:
            yield
        finally:
            with self._lock:
                self._reader_count -= 1
                if self._reader_count == 0:
                    self._read_ready.notify_all()

    @contextmanager
    def write_lock(self) -> Generator[None, None, None]:
        with self._lock:
            self._writer_waiting += 1
            while self._reader_count > 0 or self._writer_active:
                self._read_ready.wait()
            self._writer_waiting -= 1
            self._writer_active = True
        try:
            yield
        finally:
            with self._lock:
                self._writer_active = False
                self._read_ready.notify_all()


class DBMixin(BaseEngine):
    """数据库连接管理 Mixin（文件模式 + 公平读写锁）。

    特性：
    - 多读可并发执行
    - 写操作独占，但保证不会饥饿
    - 有写请求等待时，新读请求需排队
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._db_path: Path | None = None
        self._rw_lock = FairReadWriteLock()

    @property
    def db_path(self) -> Path:
        """数据库文件路径。"""
        if self._db_path is None:
            self._db_path = self.kb_path / "data" / "kb.duckdb"
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return self._db_path

    def _create_read_connection(self) -> duckdb.DuckDBPyConnection:
        """创建只读连接。"""
        return duckdb.connect(str(self.db_path), read_only=True)

    def _create_write_connection(self) -> duckdb.DuckDBPyConnection:
        """创建写连接。"""
        return duckdb.connect(str(self.db_path), read_only=False)

    def execute_read(self, sql: str, params: list | None = None) -> list:
        """执行读操作（可并发）。"""
        with self._rw_lock.read_lock():
            conn = self._create_read_connection()
            try:
                if params:
                    return conn.execute(sql, params).fetchall()
                return conn.execute(sql).fetchall()
            finally:
                conn.close()

    def execute_write(self, sql: str, params: list | None = None) -> None:
        """执行写操作（独占）。"""
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
        """执行写操作并返回结果（独占）。"""
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
        """写事务上下文（独占）。"""
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

    def close(self) -> None:
        """关闭连接管理器。"""
        logger.debug("Database connection manager closed")
```

---

## 4. 并发行为对比

### 4.1 普通读写锁（有写饥饿风险）

```
读线程1: [读锁][查询][释放]                                   
读线程2:        [读锁][查询][释放]                            
读线程3:              [读锁][查询][释放]                      
读线程4:                    [读锁][查询][释放]                
写线程:  [等待................................................] 永远等待！
```

### 4.2 公平读写锁（无写饥饿）

```
读线程1: [读锁][查询][释放]                                   
读线程2:        [读锁][查询][释放]                            
写线程:               [排队...] [写锁][写入][释放]
读线程3:                          [排队...][读锁][查询][释放]
读线程4:                                      [读锁][查询][释放]
```

---

## 5. 方案对比

| 方案 | 多读并发 | 写饥饿风险 | 实现复杂度 | 推荐度 |
|------|----------|------------|------------|--------|
| 内存模式 + 简单锁 | ❌ 串行 | 无 | 低 | ⭐⭐⭐ |
| 文件模式 + 普通读写锁 | ✅ | **有** | 中 | ⭐⭐ |
| **文件模式 + 公平读写锁** | ✅ | **无** | 中 | ⭐⭐⭐⭐⭐ |

---

## 6. 结论

| 问题 | 答案 |
|------|------|
| 写饥饿问题存在吗？ | ✅ 普通读写锁存在此问题 |
| 如何解决？ | 使用**公平读写锁**（Fair RWLock） |
| 公平锁原理？ | 有写请求等待时，新读请求必须排队 |
| 性能影响？ | 牺牲部分读并发，但保证写操作能执行 |

**推荐方案**：文件模式 + 公平读写锁，既支持多读并发，又避免写饥饿。

---

## 7. 参考资料

- [DuckDB Concurrency](https://duckdb.org/docs/connect/concurrency)
- [readerwriterlock PyPI](https://pypi.org/project/readerwriterlock/)
- 测试文件：`tests/test_duckdb_concurrency.py`
