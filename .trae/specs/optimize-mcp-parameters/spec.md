# MCP 参数序列化优化 Spec

## Why

测试报告发现 `edge_types` 等列表类型参数在 MCP 工具调用时被序列化为字符串（如 `'["knows"]'`），导致 Pydantic 校验失败。这影响了 `get_neighbors`、`graph_search`、`traverse`、`extract_subgraph`、`find_paths` 等多个核心图遍历工具的使用。

## What Changes

- 修改所有使用 `edge_types: list[str] | None` 参数的 MCP 工具，改为接收字符串格式（逗号分隔）
- 在工具内部将逗号分隔的字符串转换为列表
- 保持底层引擎方法的列表类型签名不变
- 添加参数说明文档，指导用户正确传参

## Impact

- Affected specs: MCP 工具接口、图遍历功能
- Affected code:
  - `src/duckkb/mcp/duck_mcp.py` - MCP 工具参数处理
  - `src/duckkb/core/mixins/graph.py` - 底层引擎方法（保持不变）

## ADDED Requirements

### Requirement: edge_types 参数字符串化

系统 SHALL 支持通过逗号分隔的字符串传递边类型列表参数。

#### Scenario: 传递单个边类型
- **WHEN** 用户传入 `edge_types="knows"`
- **THEN** 系统应正确解析为 `["knows"]`

#### Scenario: 传递多个边类型
- **WHEN** 用户传入 `edge_types="knows,authored,mentions"`
- **THEN** 系统应正确解析为 `["knows", "authored", "mentions"]`

#### Scenario: 传递空值
- **WHEN** 用户传入 `edge_types=""` 或 `null`
- **THEN** 系统应解析为 `None`（不过滤边类型）

### Requirement: 参数校验与错误提示

系统 SHALL 提供清晰的参数说明和错误提示。

#### Scenario: 工具描述更新
- **WHEN** 用户查看工具描述
- **THEN** 应看到 `edge_types` 参数的格式说明（逗号分隔的字符串）

## MODIFIED Requirements

### Requirement: MCP 工具参数格式

所有包含 `edge_types` 参数的 MCP 工具 SHALL 修改为接收字符串格式：
- `get_neighbors`
- `graph_search`
- `traverse`
- `extract_subgraph`
- `find_paths`

## REMOVED Requirements

无移除的需求。
