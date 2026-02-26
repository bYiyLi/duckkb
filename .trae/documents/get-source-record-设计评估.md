# `get_source_record` 设计评估

## 当前实现

```python
async def get_source_record(
    self,
    source_table: str,
    source_id: int,
) -> dict[str, Any] | None:
    """根据搜索结果回捞原始业务记录。

    Args:
        source_table: 源表名。
        source_id: 源记录 ID。

    Returns:
        原始业务记录，不存在时返回 None。
    """
    validate_table_name(source_table)

    def _fetch() -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT * FROM {source_table} WHERE __id = ?",
            [source_id],
        ).fetchone()
        if not row:
            return None

        cursor = self.conn.execute(f"SELECT * FROM {source_table} LIMIT 0")
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return dict(zip(columns, row, strict=True))

    return await asyncio.to_thread(_fetch)
```

---

## 设计优点

### 1. 职责单一，接口简洁
- 功能明确：从搜索结果回捞原始记录
- 参数简单：只需要 `source_table` + `source_id`
- 返回值清晰：记录存在返回字典，不存在返回 `None`

### 2. 异步封装正确
- 使用 `asyncio.to_thread` 将同步 DuckDB 操作包装为异步
- 符合项目"核心逻辑必须 async/await"的规范

### 3. 安全性考虑
- 调用 `validate_table_name(source_table)` 防止 SQL 注入
- 使用参数化查询 `WHERE __id = ?` 避免 ID 注入

### 4. 一致性
- 在 MCP、CLI、核心层三层都有对应接口
- 命名和参数风格统一

---

## 潜在问题与改进建议

### 问题 1：列名获取方式效率低

**现状：**
```python
cursor = self.conn.execute(f"SELECT * FROM {source_table} LIMIT 0")
columns = [desc[0] for desc in cursor.description]
```

**问题：**
- 每次调用执行两次 SQL（一次查数据，一次获取列名）
- `LIMIT 0` 是一种 hacky 的方式

**建议：**
- 方案 A：使用 DuckDB 的 `PRAGMA table_info('{table}')` 获取列信息
- 方案 B：缓存表结构信息（Engine 层维护 `_table_columns: dict[str, list[str]]`）
- 方案 C：直接使用 `cursor.description`（当前查询已经返回了列信息）

**推荐方案 C** - 最简单的优化：
```python
def _fetch() -> dict[str, Any] | None:
    cursor = self.conn.execute(
        f"SELECT * FROM {source_table} WHERE __id = ?",
        [source_id],
    )
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    row = cursor.fetchone()
    if not row:
        return None
    return dict(zip(columns, row, strict=True))
```

### 问题 2：缺少批量查询能力

**现状：** 只能单条查询，用户需要多次调用获取多条记录

**建议：** 新增 `get_source_records` 批量接口
```python
async def get_source_records(
    self,
    source_table: str,
    source_ids: list[int],
) -> list[dict[str, Any]]:
    """批量获取原始业务记录。"""
```

### 问题 3：缺少字段选择能力

**现状：** 总是 `SELECT *`，返回所有字段

**问题：**
- 大字段（如长文本）可能不需要
- 浪费网络/内存资源

**建议：** 增加可选的 `fields` 参数
```python
async def get_source_record(
    self,
    source_table: str,
    source_id: int,
    fields: list[str] | None = None,  # 新增
) -> dict[str, Any] | None:
```

### 问题 4：错误处理不够友好

**现状：** 表不存在时抛出 DuckDB 原生异常

**建议：** 捕获并转换为更友好的业务异常
```python
try:
    cursor = self.conn.execute(...)
except duckdb.CatalogException:
    raise ValueError(f"表 '{source_table}' 不存在")
```

### 问题 5：缺少日志记录

**现状：** 没有任何日志

**建议：** 添加调试日志（可选，视性能要求）
```python
logger.debug(f"Fetching source record: {source_table}.{source_id}")
```

### 问题 6：与搜索结果的关联不够紧密

**现状：** 用户需要手动从搜索结果中提取 `source_table` 和 `source_id`

**建议：** 搜索结果可直接返回原始记录（可选功能）
```python
async def search(
    self,
    query: str,
    *,
    include_source: bool = False,  # 新增
) -> list[dict[str, Any]]:
    """搜索时可选返回原始记录。"""
```

---

## 架构层面评估

### 与整体设计的一致性

| 维度 | 评估 | 说明 |
|------|------|------|
| 异步规范 | ✅ 符合 | 使用 `asyncio.to_thread` |
| 类型标注 | ✅ 完整 | 参数和返回值都有标注 |
| 错误处理 | ⚠️ 可改进 | 缺少友好错误信息 |
| 日志规范 | ❌ 缺失 | 没有日志记录 |
| 安全性 | ✅ 符合 | 表名验证 + 参数化查询 |
| 文档 | ✅ 完整 | 有 Docstring |

### 与其他搜索接口的对比

| 接口 | 返回内容 | 是否返回原始记录 |
|------|----------|------------------|
| `search` | 分块内容 + 元数据 | ❌ |
| `vector_search` | 分块内容 + 元数据 | ❌ |
| `fts_search` | 分块内容 + 元数据 | ❌ |
| `get_source_record` | 原始完整记录 | ✅ |

**设计意图清晰：** 搜索返回分块粒度的匹配，`get_source_record` 返回完整记录。这种分离是合理的，因为：
1. 搜索结果可能来自同一记录的多个分块
2. 用户可能只需要匹配片段，不需要完整记录
3. 分离可以减少不必要的数据传输

---

## 总结

### 整体评价：**设计合理，有小幅优化空间**

当前设计在核心功能上是正确的，符合项目规范。主要改进方向：

1. **必须修复**：列名获取方式优化（减少一次 SQL 查询）
2. **建议增加**：批量查询接口
3. **可选增加**：字段选择参数
4. **可选增加**：更友好的错误信息

### 改进优先级

| 优先级 | 改进项 | 影响 |
|--------|--------|------|
| P0 | 列名获取优化 | 性能提升 50% |
| P1 | 批量查询接口 | 减少 MCP 调用次数 |
| P2 | 友好错误信息 | 用户体验 |
| P3 | 字段选择 | 灵活性 |
| P3 | 日志记录 | 可观测性 |

---

## 是否需要修改？

**建议：** 进行小幅优化即可，不需要大改

1. 修复列名获取方式（P0）
2. 考虑增加批量接口（P1）

如果需要实施改进，请确认优先级和具体方案。
