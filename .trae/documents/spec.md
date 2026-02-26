# DuckKB 并发安全改造规格说明

## 1. 背景

### 1.1 当前问题

当前 DuckKB 使用纯内存模式（`duckdb.connect()`），存在以下并发风险：

| 风险点     | 描述                                   |
| ------- | ------------------------------------ |
| 连接非线程安全 | DuckDB 连接对象本身不是线程安全的                 |
| 无锁保护    | 多个协程可能同时调用 `self.conn` 执行操作          |
| 乐观并发冲突  | 同时更新相同行会触发 `Transaction conflict` 错误 |

### 1.2 目标

实现**文件模式 + 公平读写锁**方案：

* 多读操作可并发执行

* 写操作独占执行，且不会饥饿

* 使用临时目录创建 db 文件，对用户透明

* 与内存模式使用方式一致

***

## 2. 设计方案

### 2.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      Engine (用户接口)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   execute_read()              execute_write()               │
│   ┌─────────────────┐         ┌─────────────────┐          │
│   │ 获取读锁         │         │ 获取写锁         │          │
│   │ 打开只读连接     │         │ 等待所有读完成   │          │
│   │ 执行查询         │         │ 打开写连接       │          │
│   │ 关闭连接         │         │ 执行写入         │          │
│   │ 释放读锁         │         │ 关闭连接         │          │
│   └─────────────────┘         │ 释放写锁         │          │
│         ↓ ↓ ↓                 └─────────────────┘          │
│    多个读可同时进行                  ↓                      │
│                                    独占                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              {temp_dir}/duckkb_{uuid}.duckdb                │
│                    (临时数据库文件)                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 临时文件策略

```python
# 文件路径格式
{system_temp_dir}/duckkb/{uuid}/kb.duckdb

# 示例
# Windows: C:\Users\xxx\AppData\Local\Temp\duckkb\a1b2c3d4\kb.duckdb
# Linux:   /tmp/duckkb/a1b2c3d4/kb.duckdb
```

**特点**：

* 每次程序启动生成新的 UUID 目录

* 程序退出时自动清理（可选保留用于调试）

* 多个 Engine 实例互不干扰

### 2.3 公平读写锁设计

```python
class FairReadWriteLock:
    """公平读写锁（避免写饥饿）。
    
    当有写请求在等待时，新的读请求必须排队。
    """
    
    # 状态变量
    _reader_count: int      # 当前活跃的读线程数
    _writer_waiting: int    # 等待中的写线程数
    _writer_active: bool    # 是否有写线程正在执行
```

**行为规则**：

| 条件        | 读请求    | 写请求    |
| --------- | ------ | ------ |
| 无写等待、无写执行 | ✅ 立即获取 | ✅ 立即获取 |
| 有写等待      | ❌ 排队等待 | ❌ 排队等待 |
| 有写执行      | ❌ 排队等待 | ❌ 排队等待 |
| 有读执行      | ✅ 共享获取 | ❌ 排队等待 |

***

## 3. 模块设计

### 3.1 文件结构

```
src/duckkb/
├── core/
│   ├── mixins/
│   │   ├── db.py              # 修改：文件模式 + 公平读写锁
│   │   ├── search.py          # 修改：使用 execute_read
│   │   ├── storage.py         # 修改：使用 execute_write
│   │   ├── index.py           # 修改：使用 execute_read/write
│   │   └── ...
│   └── ...
├── utils/
│   └── rwlock.py              # 新增：公平读写锁实现
└── ...
```

### 3.2 DBMixin 接口设计

```python
class DBMixin(BaseEngine):
    """数据库连接管理 Mixin（文件模式 + 公平读写锁）。"""

    # 属性
    @property
    def db_path(self) -> Path:
        """临时数据库文件路径。"""

    # 读操作（可并发）
    def execute_read(
        self, 
        sql: str, 
        params: list | None = None
    ) -> list:
        """执行读操作（可并发）。"""

    # 写操作（独占）
    def execute_write(
        self, 
        sql: str, 
        params: list | None = None
    ) -> None:
        """执行写操作（独占）。"""

    def execute_write_with_result(
        self, 
        sql: str, 
        params: list | None = None
    ) -> list:
        """执行写操作并返回结果（独占）。"""

    # 事务支持
    @contextmanager
    def write_transaction(
        self
    ) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """写事务上下文（独占）。"""

    # 生命周期
    def close(self) -> None:
        """关闭连接管理器，清理临时文件。"""
```

***

## 4. 调用方修改

### 4.1 SearchMixin

```python
# 修改前
rows = await asyncio.to_thread(self._execute_query, sql, params)

def _execute_query(self, sql: str, params: list | None = None) -> list:
    return self.conn.execute(sql, params).fetchall()

# 修改后
rows = await asyncio.to_thread(self.execute_read, sql, params)
```

### 4.2 StorageMixin

```python
# 修改前
def _execute_load() -> int:
    try:
        self.conn.begin()
        self.conn.execute(...)
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise

# 修改后
def _execute_load() -> int:
    with self.write_transaction() as conn:
        conn.execute(...)
```

### 4.3 IndexMixin

```python
# 修改前
self.conn.execute(sql, params)

# 修改后
self.execute_write(sql, params)
```

***

## 5. 配置选项

### 5.1 新增配置项

```yaml
# config.yaml
database:
  # 数据库模式：memory（内存）或 file（文件）
  mode: file
  
  # 临时文件目录（可选，默认使用系统临时目录）
  temp_dir: null
  
  # 退出时是否保留临时文件（用于调试）
  keep_temp_on_exit: false
```

### 5.2 配置模型

```python
# src/duckkb/core/config/models.py
class DatabaseConfig(BaseModel):
    """数据库配置。"""

    mode: Literal["memory", "file"] = "file"
    temp_dir: Path | None = None
    keep_temp_on_exit: bool = False
```

***

## 6. 测试策略

### 6.1 单元测试

| 测试项                                     | 描述          |
| --------------------------------------- | ----------- |
| `test_fair_rwlock_read_concurrent`      | 多个读操作可并发执行  |
| `test_fair_rwlock_write_exclusive`      | 写操作独占执行     |
| `test_fair_rwlock_no_writer_starvation` | 写操作不会饥饿     |
| `test_temp_db_creation`                 | 临时数据库文件正确创建 |
| `test_temp_db_cleanup`                  | 程序退出时正确清理   |

### 6.2 并发测试

```python
async def test_concurrent_reads():
    """测试并发读取。"""
    engine = Engine(kb_path)
    
    async def read_task():
        return await engine.search("test query")
    
    # 并发执行 10 个读操作
    results = await asyncio.gather(*[read_task() for _ in range(10)])
    assert len(results) == 10

async def test_concurrent_read_write():
    """测试并发读写。"""
    engine = Engine(kb_path)
    
    async def read_task():
        return await engine.search("test")
    
    async def write_task():
        return await engine.sync_node("Document")
    
    # 并发执行读写
    results = await asyncio.gather(
        *[read_task() for _ in range(5)],
        *[write_task() for _ in range(2)],
    )
    assert len(results) == 7
```

***

## 7. 风险与缓解

| 风险        | 影响     | 缓解措施                |
| --------- | ------ | ------------------- |
| 临时文件未清理   | 磁盘空间占用 | 使用 `atexit` 注册清理函数  |
| 文件 I/O 性能 | 查询延迟   | DuckDB 文件模式性能接近内存模式 |
| 锁竞争       | 并发性能   | 公平锁策略平衡读写需求         |

***

## 8. 参考资料

* [DuckDB Concurrency](https://duckdb.org/docs/connect/concurrency)

* [readerwriterlock PyPI](https://pypi.org/project/readerwriterlock/)

* 测试文件：`tests/test_duckdb_concurrency.py`

