# DuckKB MCP 工具分析报告

本报告对 `src/duckkb/mcp/server.py` 中定义的 Model Context Protocol (MCP) 工具进行了详细分析。

## 1. 概述

当前 MCP 服务提供了 **10 个** 工具，涵盖了知识库的健康检查、数据同步、查询、数据操作（导入/删除）以及备份恢复功能。所有工具均通过 `@mcp.tool()` 注册，并使用 `fastmcp` 框架。

## 2. 工具详细分析

### 2.1 基础管理类

#### `check_health`
*   **功能**: 检查服务健康状态，返回知识库路径、数据库存在性及数据文件统计。
*   **输入**: 无
*   **输出**: JSON 字符串 (包含 `status`, `kb_path`, `db_exists`, `data_files_count`, `data_files`)。
*   **实现**: 直接检查文件系统路径和文件存在性。
*   **依赖**: `AppContext`, `glob_files`, `file_exists`。

#### `get_schema_info`
*   **功能**: 获取数据库表结构定义和 ER 图信息，辅助用户理解数据模型。
*   **输入**: 无
*   **输出**: 字符串 (Schema 描述 + 可选的使用说明)。
*   **实现**: 调用底层 `_get_schema_info` 函数，并附加配置中的 `usage_instructions`。
*   **依赖**: `_get_schema_info`, `AppContext`。

### 2.2 数据同步与迁移类

#### `sync_knowledge_base`
*   **功能**: 同步知识库数据，支持通过 `ontology_yaml` 更新配置和迁移数据。
*   **输入**:
    *   `ontology_yaml` (str | None): 新的 ontology 配置 YAML 字符串。
    *   `force` (bool): 是否强制全量同步/迁移。
*   **输出**: JSON 字符串 (操作结果)。
*   **实现**:
    *   若提供 `ontology_yaml`，使用 `MigrationManager` 处理配置校验和迁移。
    *   否则，执行标准同步流程 `_sync` 并持久化表数据 `persist_all_tables`。
*   **风险**: `force=True` 操作可能涉及大量数据重写，需谨慎使用。

### 2.3 查询检索类

#### `smart_search`
*   **功能**: 执行混合搜索（向量相似度 + 元数据匹配）。
*   **输入**:
    *   `query` (str): 搜索关键词。
    *   `limit` (int, default=10): 结果数量限制。
    *   `table_filter` (str | None): 指定搜索表。
    *   `alpha` (float, default=0.5): 向量/元数据权重系数。
*   **输出**: JSON 字符串 (搜索结果列表)。
*   **实现**: 代理调用 `duckkb.engine.searcher.smart_search`。

#### `query_raw_sql`
*   **功能**: 执行只读 SQL 查询 (SELECT)。
*   **输入**: `sql` (str)
*   **输出**: JSON 字符串 (查询结果)。
*   **实现**: 代理调用 `duckkb.engine.searcher.query_raw_sql`。
*   **安全**: 文档声明仅支持 SELECT，底层应有相应校验机制防止 SQL 注入或写操作。

### 2.4 数据操作类

#### `validate_and_import`
*   **功能**: 验证 JSONL 文件并导入数据 (Upsert 模式)。
*   **输入**:
    *   `table_name` (str): 目标表名。
    *   `temp_file_path` (str): 临时文件路径。
*   **输出**: JSON 字符串 (导入结果统计)。
*   **实现**:
    1.  检查文件是否存在。
    2.  读取全部内容 (`read_file`) 并按行解析 JSON。
    3.  校验每行是否为 JSON 对象且包含 `id` 字段。
    4.  收集错误并统一抛出 (最多显示 `MAX_ERROR_FEEDBACK` 条)。
    5.  调用 `add_documents` 执行导入。
    6.  删除临时文件。
*   **潜在问题**: `read_file` 一次性读取整个文件内容，对于超大文件可能导致内存溢出 (OOM)。建议改为流式读取。

#### `delete_records`
*   **功能**: 删除指定记录。
*   **输入**:
    *   `table_name` (str): 表名。
    *   `record_ids` (list[str]): 待删除 ID 列表。
*   **输出**: JSON 字符串 (删除结果)。
*   **实现**: 代理调用 `delete_documents`。

### 2.5 备份恢复类

#### `list_backups`
*   **功能**: 列出所有备份。
*   **输入**: 无
*   **输出**: JSON 字符串 (备份列表)。
*   **实现**: 使用 `BackupManager.list_backups`。

#### `create_backup`
*   **功能**: 创建当前知识库备份。
*   **输入**: `prefix` (str, default=""): 备份名前缀。
*   **输出**: JSON 字符串 (备份路径信息)。
*   **实现**: 使用 `BackupManager.create_backup`。
*   **注意**: 模块顶部的 docstring 列表中遗漏了此工具的说明。

#### `restore_backup`
*   **功能**: 从指定备份恢复知识库。
*   **输入**: `backup_name` (str)。
*   **输出**: JSON 字符串 (恢复状态)。
*   **实现**: 使用 `BackupManager.restore_backup`。
*   **风险**: 恢复操作是破坏性的 (覆盖当前数据)，应在文档中强调风险。

## 3. 改进建议

1.  **性能优化**:
    *   `validate_and_import`: 建议修改文件读取逻辑，使用流式读取 (逐行处理) 替代一次性读取，以支持大文件导入并降低内存占用。

2.  **文档完善**:
    *   在模块顶部的 docstring 中补充 `create_backup` 工具的说明。
    *   `restore_backup` 的文档应更醒目地提示数据覆盖风险。

3.  **安全性**:
    *   确认 `query_raw_sql` 底层是否严格限制了非 SELECT 语句，防止 SQL 注入或意外的数据修改。

4.  **错误处理**:
    *   大部分工具直接抛出异常，建议在 MCP 层统一捕获常见异常并返回更友好的错误信息 JSON，而不是让客户端处理原始异常堆栈。
