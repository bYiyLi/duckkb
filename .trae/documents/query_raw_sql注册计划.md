# query_raw_sql 分析与注册计划

## 问题分析

### 1. 当前实现存在的问题

`query_raw_sql` 当前实现在 [search.py:306-405](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/core/mixins/search.py#L306-L405) 使用**应用层 SQL 关键字检查**：

```python
forbidden = [
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "ATTACH",
    "DETACH", "PRAGMA", "IMPORT", "EXPORT", "COPY", "LOAD",
    "INSTALL", "VACUUM", "BEGIN", "COMMIT", "ROLLBACK",
]
```

**问题**：
1. **不完整**：可能遗漏某些危险操作（如通过函数调用、表达式注入等）
2. **绕过风险**：SQL 语法复杂，可能存在绕过方式
3. **维护负担**：需要持续更新关键字列表
4. **性能开销**：正则匹配有一定开销

### 2. 更好的方案：利用 DuckDB 原生只读能力

DuckDB 支持 `access_mode` 配置：
- `automatic`（默认）
- `read_only`
- `read_write`

**方案**：在执行 SQL 前，临时设置会话为只读模式，让数据库引擎自己拒绝写操作。

```python
async def query_raw_sql(self, sql: str) -> list[dict[str, Any]]:
    """安全执行原始 SQL 查询。"""
    # 保存当前模式
    current_mode = self.conn.execute(
        "SELECT current_setting('access_mode')"
    ).fetchone()[0]
    
    try:
        # 设置只读模式
        self.conn.execute("SET access_mode='read_only'")
        
        # 执行查询
        result = await asyncio.to_thread(self._execute_raw_sql, sql)
        return result
    finally:
        # 恢复原模式
        self.conn.execute(f"SET access_mode='{current_mode}'")
```

**优势**：
1. **更安全**：数据库引擎级别的保护，无法绕过
2. **更简洁**：无需维护关键字黑名单
3. **更可靠**：DuckDB 官方支持，不会有遗漏
4. **错误信息更清晰**：数据库返回标准错误

### 3. MCP 注册问题

**现状**：
- `_register_query_raw_sql_tool()` 方法已定义在 [duck_mcp.py:183-209](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/mcp/duck_mcp.py#L183-L209)
- **BUG**：`_register_tools()` 方法中**未调用** `_register_query_raw_sql_tool()`

### 4. CLI 注册问题

**现状**：
- `query_raw_sql` 命令**未在 CLI 中注册**

---

## 修复计划

### 任务 1：重构 query_raw_sql 使用 DuckDB 原生只读模式

**文件**：`src/duckkb/core/mixins/search.py`

**修改内容**：
1. 移除关键字黑名单检查
2. 使用 `SET access_mode='read_only'` 实现只读保护
3. 保留 LIMIT 自动添加和结果大小限制

```python
async def query_raw_sql(self, sql: str) -> list[dict[str, Any]]:
    """安全执行原始 SQL 查询。

    使用 DuckDB 原生只读模式保护，自动拒绝所有写操作。
    自动添加 LIMIT 限制，防止返回过多数据。

    Args:
        sql: 原始 SQL 查询字符串。

    Returns:
        查询结果字典列表。

    Raises:
        ValueError: 结果集大小超限或执行失败。
        duckdb.Error: SQL 包含写操作时由数据库引擎抛出。
    """
    sql_stripped = sql.strip()
    
    # 自动添加 LIMIT
    if not re.search(r"\bLIMIT\s+\d+", sql_stripped.upper()):
        sql = sql_stripped + f" LIMIT {QUERY_DEFAULT_LIMIT}"
    
    return await asyncio.to_thread(self._execute_raw_sql_readonly, sql)

def _execute_raw_sql_readonly(self, sql: str) -> list[dict[str, Any]]:
    """在只读模式下执行 SQL 查询。

    Args:
        sql: 要执行的 SQL 查询。

    Returns:
        字典列表，键为列名，值为行值。

    Raises:
        ValueError: 结果集大小超限。
        duckdb.Error: SQL 执行失败或包含写操作。
    """
    # 保存当前模式
    current_mode = self.conn.execute(
        "SELECT current_setting('access_mode')"
    ).fetchone()[0]
    
    try:
        # 设置只读模式
        self.conn.execute("SET access_mode='read_only'")
        
        cursor = self.conn.execute(sql)
        if not cursor.description:
            return []
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        result = [dict(zip(columns, row, strict=True)) for row in rows]
        
        # 结果大小检查
        json_bytes = orjson.dumps(result)
        if len(json_bytes) > QUERY_RESULT_SIZE_LIMIT:
            raise ValueError(
                f"Result set size exceeds {QUERY_RESULT_SIZE_LIMIT // (1024 * 1024)}MB limit."
            )
        
        return result
    finally:
        # 恢复原模式
        self.conn.execute(f"SET access_mode='{current_mode}'")
```

### 任务 2：修复 MCP 注册

**文件**：`src/duckkb/mcp/duck_mcp.py`

**修改**：在 `_register_tools()` 方法中添加调用

```python
def _register_tools(self) -> None:
    """注册 MCP 工具。"""
    self._register_knowledge_schema_tool()
    self._register_import_knowledge_bundle_tool()
    self._register_search_tool()
    self._register_vector_search_tool()
    self._register_fts_search_tool()
    self._register_get_source_record_tool()
    self._register_query_raw_sql_tool()  # 新增
```

### 任务 3：添加 CLI 命令

**文件**：`src/duckkb/cli/duck_typer.py`

**修改内容**：

1. 在 `_register_commands()` 方法中添加调用
2. 添加新方法 `_register_query_raw_sql_command()`

---

## 验证步骤

1. 运行 `ruff check` 确保代码格式正确
2. 运行 `ruff format` 格式化代码
3. 测试只读模式是否生效：
   - 执行 SELECT 查询应成功
   - 执行 INSERT/UPDATE/DELETE 应被拒绝
4. 手动测试 MCP 工具是否可用
5. 手动测试 CLI 命令是否可用

---

## 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/duckkb/core/mixins/search.py` | 重构 | 使用 DuckDB 原生只读模式替代关键字检查 |
| `src/duckkb/mcp/duck_mcp.py` | 修改 | 在 `_register_tools()` 中添加调用 |
| `src/duckkb/cli/duck_typer.py` | 修改 | 添加 `_register_query_raw_sql_command()` 方法 |
