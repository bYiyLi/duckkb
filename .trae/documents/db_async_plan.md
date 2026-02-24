# DuckKB 数据库层异步化分析与方案

## 一、现状分析

### 1. 当前数据库实现

[db.py](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/db.py) 中的实现：

```python
class DBManager:
    def get_connection(self, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path), read_only=read_only)

@contextmanager
def get_db(read_only: bool = True):
    conn = db_manager.get_connection(read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()
```

**特点**：同步实现，使用 `@contextmanager` 装饰器。

### 2. 调用位置统计

| 文件 | 函数 | 操作类型 | 当前处理方式 |
|------|------|---------|-------------|
| [indexer.py:61](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/indexer.py#L61) | `create_fts_index()` | DDL | `asyncio.to_thread` |
| [indexer.py:87](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/indexer.py#L87) | `clean_cache()` | DELETE | `asyncio.to_thread` |
| [indexer.py:184](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/indexer.py#L184) | `_process_file()` | 事务 | `asyncio.to_thread` |
| [searcher.py:153](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/searcher.py#L153) | `smart_search()` | SELECT | `asyncio.to_thread` |
| [searcher.py:234](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/searcher.py#L234) | `query_raw_sql()` | SELECT | `asyncio.to_thread` |
| [embedding.py:27](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/utils/embedding.py#L27) | `get_embeddings()` | SELECT | `asyncio.to_thread` |
| [embedding.py:47](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/utils/embedding.py#L47) | `get_embeddings()` | INSERT | `asyncio.to_thread` |
| [schema.py:30](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/schema.py#L30) | `init_schema()` | DDL | 同步调用 |

### 3. DuckDB 异步支持情况

**关键结论**：DuckDB Python 绑定**目前没有原生异步接口**。

- DuckDB 是嵌入式数据库，操作本质上是阻塞的
- 官方推荐做法：使用线程池执行阻塞操作
- Python 3.12 的 `asyncio.to_thread()` 是标准解决方案

### 4. 项目规范符合性

当前实现**符合**项目规范：

> 禁止同步代码：核心逻辑必须 async/await；阻塞 I/O 只能通过 asyncio.to_thread 封装

所有公开 API 都是 `async def`，数据库操作通过 `asyncio.to_thread` 封装。

---

## 二、问题识别

### 1. 不一致的地方

| 位置 | 问题 |
|------|------|
| [schema.py:30](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/schema.py#L30) | `init_schema()` 是同步函数，直接调用 `get_db()` |
| [db.py](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/db.py) | `get_db()` 是同步上下文管理器，无法直接用于 async with |

### 2. 架构层面的考虑

当前模式：
```
async def public_api():
    result = await asyncio.to_thread(_sync_db_operation)
```

这种模式的问题：
- 每个调用者都需要手动创建同步包装函数
- 代码重复（每个文件都有 `_sync_*` 辅助函数）

---

## 三、改进方案

### 方案：创建异步数据库上下文管理器

在 `db.py` 中添加异步版本的 `get_db()`，内部使用 `asyncio.to_thread`：

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_async_db(read_only: bool = True):
    """
    异步数据库连接上下文管理器。
    内部使用 asyncio.to_thread 将阻塞操作放入线程池。
    """
    conn = await asyncio.to_thread(db_manager.get_connection, read_only=read_only)
    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)
```

**优点**：
1. 符合项目规范（核心逻辑 async/await）
2. 调用者无需手动创建 `_sync_*` 包装函数
3. 统一的异步接口，代码更清晰

**注意**：
- 连接获取和关闭是异步的，但连接上的操作（execute/fetchall）仍是同步的
- 调用者仍需将耗时操作包装在 `asyncio.to_thread` 中

### 是否值得改？

**建议：暂不改动**

理由：
1. 当前实现已符合项目规范（阻塞 I/O 通过 `asyncio.to_thread` 封装）
2. DuckDB 没有原生异步接口，改动不会带来性能提升
3. 现有模式已稳定运行，改动风险 > 收益

如果需要改进，建议优先处理 `schema.py` 中的同步调用。

---

## 四、实施计划（如需改动）

### 任务列表

1. **修改 `db.py`**
   - 添加 `get_async_db()` 异步上下文管理器
   - 保留 `get_db()` 同步版本供内部使用

2. **修改 `schema.py`**
   - 将 `init_schema()` 改为 `async def init_schema()`
   - 使用 `get_async_db()` 或 `asyncio.to_thread`

3. **更新调用方（可选）**
   - 简化 indexer.py、searcher.py、embedding.py 中的代码
   - 移除部分 `_sync_*` 辅助函数

### 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 测试覆盖不足 | 中 | 确保所有测试通过 |
| 行为变化 | 低 | 保持接口兼容 |

---

## 五、结论

**当前实现已符合项目规范**，数据库操作通过 `asyncio.to_thread` 封装，核心 API 都是异步的。

唯一需要关注的是 `schema.py` 中的同步调用，如果 `init_schema()` 是在异步上下文中调用的，需要改为异步版本。

是否需要实施改动，请确认。
