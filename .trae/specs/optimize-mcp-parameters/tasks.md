# Tasks

- [x] Task 1: 修改 MCP 工具的 edge_types 参数为字符串格式
  - [x] SubTask 1.1: 修改 `get_neighbors` 工具的参数签名和解析逻辑
  - [x] SubTask 1.2: 修改 `graph_search` 工具的参数签名和解析逻辑
  - [x] SubTask 1.3: 修改 `traverse` 工具的参数签名和解析逻辑
  - [x] SubTask 1.4: 修改 `extract_subgraph` 工具的参数签名和解析逻辑
  - [x] SubTask 1.5: 修改 `find_paths` 工具的参数签名和解析逻辑

- [x] Task 2: 添加参数解析辅助函数
  - [x] SubTask 2.1: 创建 `_parse_edge_types` 静态方法
  - [x] SubTask 2.2: 处理空字符串和 None 值
  - [x] SubTask 2.3: 处理逗号分隔的多个值

- [x] Task 3: 更新工具文档说明
  - [x] SubTask 3.1: 更新所有 affected 工具的 docstring
  - [x] SubTask 3.2: 添加参数格式示例

- [x] Task 4: 测试验证
  - [x] SubTask 4.1: 创建测试用例验证字符串参数解析
  - [x] SubTask 4.2: 测试单个边类型
  - [x] SubTask 4.3: 测试多个边类型
  - [x] SubTask 4.4: 测试空值处理

# Task Dependencies

- [Task 2] 应该在 [Task 1] 之前或同时进行
- [Task 3] 可以与 [Task 1], [Task 2] 并行
- [Task 4] 依赖 [Task 1], [Task 2] 完成
