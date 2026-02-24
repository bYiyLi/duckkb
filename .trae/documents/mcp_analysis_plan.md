# MCP 工具分析计划

## 目标
全面分析项目中的所有 MCP (Model Context Protocol) 工具，理解其功能、输入输出、实现逻辑及潜在改进点。

## 范围
主要关注 `src/duckkb/mcp/server.py` 文件中定义的工具，以及它们依赖的底层逻辑（如 `DuckDBClient`, `StorageManager` 等）。

## 步骤

1.  **工具清单确认**
    *   确认所有使用 `@mcp.tool()` 注册的函数。
    *   目前已识别：`check_health`, `sync_knowledge_base`, `get_schema_info`, `smart_search`, `query_raw_sql`, `validate_and_import`, `delete_records`, `list_backups`, `restore_backup`, `create_backup`。

2.  **详细分析**
    对每个工具进行以下维度的分析：
    *   **功能描述**: 该工具的作用是什么？
    *   **参数 (Inputs)**: 接受哪些参数？类型和约束是什么？
    *   **返回值 (Outputs)**: 返回什么数据？格式如何？
    *   **实现逻辑**: 核心代码流程，涉及哪些模块（如 DB, Storage）。
    *   **错误处理**: 如何处理异常情况？
    *   **依赖关系**: 依赖哪些外部组件或配置。

3.  **代码质量与规范检查**
    *   检查是否符合项目规范（类型标注、文档字符串、错误处理等）。
    *   检查是否存在潜在的安全风险（如 SQL 注入）。

4.  **生成分析报告**
    *   汇总上述分析结果，生成一份详细的 Markdown 报告。
    *   提出改进建议（如有）。

## 交付物
*   MCP 工具分析报告 (Markdown 格式)
