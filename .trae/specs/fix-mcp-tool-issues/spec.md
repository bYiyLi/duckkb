# DuckKB MCP 工具问题修复 Spec

## Why

测试报告显示 DuckKB MCP 工具存在多个严重问题，导致核心搜索功能和图遍历功能不可用。主要问题包括：混合搜索字段映射混乱、全文搜索返回空结果、datetime 序列化错误、图遍历结果字段名错误等。这些问题严重影响知识库的核心检索能力，需要优先修复。

## What Changes

- 修复混合搜索 `_process_results` 方法的字段映射逻辑，确保字段名与实际值正确对应
- 修复全文搜索 SQL 查询，确保 FTS 索引正确使用
- 修复 `get_source_record` 的 datetime 序列化问题
- 修复图遍历 `_query_direction` 方法的邻居节点字段名映射
- 优化邻居节点去重逻辑（direction="both" 时）
- 完善 SQL 安全限制机制，在解析阶段拦截危险语句
- 完善参数校验，提前拦截无效参数
- 优化错误提示信息

## Impact

- Affected specs: 搜索功能、图遍历功能、SQL 查询功能、原始记录获取
- Affected code:
  - `src/duckkb/core/mixins/search.py` - 搜索相关修复
  - `src/duckkb/core/mixins/graph.py` - 图遍历相关修复
  - `src/duckkb/mcp/duck_mcp.py` - JSON 序列化修复

## ADDED Requirements

### Requirement: 混合搜索结果字段映射

系统 SHALL 确保混合搜索返回的结果字段名与实际值正确对应。

#### Scenario: 混合搜索返回正确字段映射
- **WHEN** 用户调用 `search` 工具进行混合搜索
- **THEN** 返回结果中的 `source_table` 应为表名字符串
- **AND** `source_id` 应为整数 ID
- **AND** `source_field` 应为字段名字符串
- **AND** `chunk_seq` 应为整数序号
- **AND** `content` 应为文本内容字符串

### Requirement: 全文搜索功能

系统 SHALL 确保全文搜索能够正确返回匹配结果。

#### Scenario: 全文搜索返回匹配结果
- **WHEN** 用户调用 `fts_search` 工具搜索已索引的关键词
- **THEN** 应返回包含匹配内容的搜索结果列表
- **AND** 结果不为空数组（当存在匹配数据时）

### Requirement: datetime 序列化

系统 SHALL 正确处理包含 datetime 字段的记录序列化。

#### Scenario: 获取包含 datetime 的原始记录
- **WHEN** 用户调用 `get_source_record` 获取包含时间戳字段的记录
- **THEN** 应返回正确序列化的 JSON 数据
- **AND** datetime 字段应转换为 ISO 格式字符串

### Requirement: 图遍历邻居节点字段名

系统 SHALL 在图遍历结果中返回正确的字段名。

#### Scenario: 获取邻居节点返回正确字段名
- **WHEN** 用户调用 `get_neighbors` 获取邻居节点
- **THEN** 返回的邻居节点数据应包含正确的字段名（如 `__id`, `__created_at`, `name`, `age` 等）
- **AND** 不应出现 `col_2`, `col_3` 等数字形式字段名

### Requirement: SQL 安全限制

系统 SHALL 在 SQL 解析阶段直接拦截危险语句。

#### Scenario: 拦截 UPDATE 语句
- **WHEN** 用户尝试执行 UPDATE 语句
- **THEN** 应返回明确的错误提示"仅允许 SELECT 查询"
- **AND** 不应尝试执行添加 LIMIT 后的错误语法

### Requirement: 参数前置校验

系统 SHALL 在参数校验阶段拦截无效参数。

#### Scenario: 拦截负数 limit 参数
- **WHEN** 用户传入负数的 limit 参数
- **THEN** 应在参数校验阶段返回明确的错误提示
- **AND** 不应将负数传递到 SQL 层

## MODIFIED Requirements

### Requirement: 邻居节点去重

当 `direction="both"` 时，系统 SHALL 合并重复的邻居节点，避免同一条边被返回两次。

#### Scenario: 双向遍历去重
- **WHEN** 用户调用 `get_neighbors` 并设置 `direction="both"`
- **THEN** 每个邻居节点应只返回一次
- **AND** 应包含边的方向信息

### Requirement: 边属性返回

系统 SHALL 在子图提取等操作中返回完整的边属性。

#### Scenario: 子图提取返回完整边信息
- **WHEN** 用户调用 `extract_subgraph` 提取子图
- **THEN** 返回的边信息应包含所有属性字段（如 `since`, `closeness`, `role` 等）
- **AND** 不仅是 `__id`, `__from_id`, `__to_id`

## REMOVED Requirements

无移除的需求。
