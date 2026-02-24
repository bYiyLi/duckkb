# MCP 启动逻辑实现计划

根据设计文档 `设计文档.md`，我们将完善 DuckKB 的 MCP Server 启动逻辑与工具接口实现。

## 目标
实现 `src/duckkb/main.py` 启动的 MCP Server，使其包含设计文档中定义的以下核心能力：
1.  **环境管理**: 同步知识库 (`sync_knowledge_base`)、获取 Schema 信息 (`get_schema_info`)。
2.  **知识检索**: 混合搜索 (`smart_search`)、安全 SQL 查询 (`query_raw_sql`)。
3.  **事实维护**: 数据校验与导入 (`validate_and_import`)。

## 步骤

### 1. 定义 Engine 接口
在 `src/duckkb/engine/` 模块中定义核心业务逻辑的接口签名。

-   **`src/duckkb/engine/indexer.py`**:
    -   更新 `sync_knowledge_base()`
    -   添加 `get_schema_info()`
    -   添加 `validate_and_import(table_name, temp_file_path)`
-   **`src/duckkb/engine/searcher.py`**:
    -   更新 `smart_search(query, limit, table_filter)`
    -   添加 `query_raw_sql(sql)`

### 2. 实现 MCP 工具注册
在 `src/duckkb/mcp/tools.py` 中使用 `fastmcp` 装饰器注册工具，并调用 Engine 层接口。

-   引入 `duckkb.mcp.server.mcp` 对象。
-   实现 5 个核心工具的包装函数。

### 3. 集成 Server 启动
确保 `src/duckkb/mcp/server.py` 和 `src/duckkb/main.py` 正确加载工具。

-   修改 `src/duckkb/mcp/server.py`: 显式导入 `duckkb.mcp.tools`，确保工具在 Server 启动前被注册。
-   检查 `src/duckkb/main.py`: 确认 `serve` 命令调用 `mcp.run()` 的正确性。

## 验证
-   检查代码静态结构，确保所有设计文档要求的接口均已定义且可被 MCP Server 加载。
