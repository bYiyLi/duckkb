# 计划：将 query\_raw\_sql 迁移到新知识库引擎

## 背景

旧的 `query_raw_sql` 实现位于 `database/engine/search.py`，需要迁移到新的知识库引擎架构（`core/mixins/search.py`），并在 `DuckMCP` 中暴露为 MCP 工具。

## 现有实现分析

### 旧实现 (`database/engine/search.py:225-326`)

安全机制：

1. 只允许 SELECT 查询（白名单模式）
2. 禁止危险关键字（INSERT, UPDATE, DELETE, DROP, CREATE, ALTER 等 22 个关键字）
3. 移除 SQL 注释后检查
4. 自动添加 LIMIT（默认 1000）
5. 结果大小限制（2MB）
6. 使用只读数据库连接

### 新架构

* `Engine` 类通过 Mixin 组合能力

* `SearchMixin` 已有 `search`、`vector_search`、`fts_search` 方法

* `DBMixin` 提供 `self.conn` 数据库连接

* `DuckMCP` 继承 `Engine` 和 `FastMCP`

## 实现方案

### 1. 在 `SearchMixin` 中添加 `query_raw_sql` 方法

文件：`src/duckkb/core/mixins/search.py`

```python
async def query_raw_sql(self, sql: str) -> list[dict[str, Any]]:
    """安全执行原始 SQL 查询。
    
    安全检查：
    1. 只允许 SELECT 查询
    2. 禁止危险关键字
    3. 自动添加 LIMIT
    4. 结果大小限制
    
    Args:
        sql: 原始 SQL 查询字符串。
        
    Returns:
        查询结果字典列表。
        
    Raises:
        DatabaseError: SQL 包含禁止的关键字或不是 SELECT 查询。
        ValueError: 结果集大小超限或执行失败。
    """
```

需要从 `constants` 导入：

* `QUERY_RESULT_SIZE_LIMIT`

* `QUERY_DEFAULT_LIMIT`

需要从 `exceptions` 导入：

* `DatabaseError`

### 2. 在 `DuckMCP` 中注册 `query_raw_sql` 工具

文件：`src/duckkb/mcp/duck_mcp.py`

在 `_register_tools()` 中添加 `_register_query_raw_sql_tool()` 方法：

```python
def _register_query_raw_sql_tool(self) -> None:
    """注册 query_raw_sql 工具。"""
    @self.tool()
    async def query_raw_sql(sql: str) -> str:
        """执行只读 SQL 查询。
        
        安全地执行原始 SQL 查询语句，仅支持 SELECT 操作。
        系统会自动应用 LIMIT 限制，防止返回过多数据。
        
        Args:
            sql: 要执行的 SQL 查询语句，必须是 SELECT 语句。
            
        Returns:
            JSON 格式的查询结果列表。
        """
        results = await self.query_raw_sql(sql)
        return json.dumps(results, ensure_ascii=False, default=str)
```

## 任务清单

1. **修改** **`SearchMixin`**

   * 添加必要的导入（`re`, `orjson`, `DatabaseError`, 常量）

   * 实现 `query_raw_sql` 方法

   * 实现 `_execute_raw_sql` 辅助方法

2. **修改** **`DuckMCP`**

   * 在 `_register_tools()` 中调用 `_register_query_raw_sql_tool()`

   * 实现 `_register_query_raw_sql_tool()` 方法

## 注意事项

* 保持与旧实现完全相同的安全检查逻辑

* 使用 `asyncio.to_thread` 包装同步数据库操作

* 使用 `self.conn` 而非旧的 `get_db()` 函数

* 返回格式保持一致（字典列表）

