# 知识图谱检索功能检查清单

## 代码质量检查

### 模型定义
- [ ] `EdgeIndexConfig` 类继承 `BaseModel`
- [ ] `EdgeIndexConfig` 包含完整的类型标注
- [ ] `EdgeIndexConfig` 包含中文 Docstring
- [ ] `EdgeType.index` 字段正确设置为可选
- [ ] 模型通过 Pydantic 验证

### GraphMixin 实现
- [ ] `GraphMixin` 正确继承 `BaseEngine`
- [ ] 所有公共方法使用 `async def`
- [ ] 所有公共方法包含完整类型标注
- [ ] 所有公共方法包含中文 Docstring（Google Style）
- [ ] Docstring 包含 Args 和 Returns 部分
- [ ] 私有方法以 `_` 开头
- [ ] 使用 `asyncio.to_thread` 封装阻塞 I/O

### SQL 安全
- [ ] 所有表名通过 `validate_table_name` 校验
- [ ] 使用参数化查询防止 SQL 注入
- [ ] 递归 CTE 包含深度限制防止无限循环
- [ ] 查询结果包含 LIMIT 限制

### 错误处理
- [ ] 节点不存在时抛出 `NodeNotFoundError`
- [ ] 无效方向参数时抛出 `InvalidDirectionError`
- [ ] 所有异常继承自 `DuckKBError`
- [ ] 异常消息清晰明确

## 功能检查

### get_neighbors
- [ ] 支持通过 `__id` 查询
- [ ] 支持通过 identity 字段值查询
- [ ] `direction="out"` 仅返回出边邻居
- [ ] `direction="in"` 仅返回入边邻居
- [ ] `direction="both"` 返回双向邻居
- [ ] `edge_types` 参数正确过滤边类型
- [ ] `limit` 参数正确限制返回数量
- [ ] 返回结果包含节点完整属性
- [ ] 返回结果包含边属性
- [ ] 返回结果包含统计信息

### traverse
- [ ] 正确实现广度优先遍历
- [ ] `max_depth` 参数正确限制遍历深度
- [ ] 避免环路（不重复访问已访问节点）
- [ ] `return_paths=True` 返回完整路径
- [ ] `return_paths=False` 返回去重节点列表
- [ ] `limit` 参数正确限制返回数量

### find_paths
- [ ] 正确查找两节点间的路径
- [ ] 按路径长度排序（最短优先）
- [ ] `max_depth` 参数正确限制路径长度
- [ ] `limit` 参数正确限制返回数量
- [ ] 无路径时返回空列表

### extract_subgraph
- [ ] 正确提取子图
- [ ] `max_depth` 参数正确控制扩展深度
- [ ] `node_limit` 参数正确限制节点数量
- [ ] `edge_limit` 参数正确限制边数量
- [ ] 返回结果包含中心节点
- [ ] 返回结果包含所有节点
- [ ] 返回结果包含所有边
- [ ] 返回结果包含统计信息

### graph_search
- [ ] 正确调用 `search` 方法获取种子节点
- [ ] 正确调用 `get_neighbors` 获取邻居
- [ ] `traverse_depth > 1` 时正确递归遍历
- [ ] `search_limit` 参数正确限制种子节点数
- [ ] `neighbor_limit` 参数正确限制邻居数
- [ ] 返回结果包含种子节点信息
- [ ] 返回结果包含上下文信息

## 集成检查

### Engine 集成
- [ ] `Engine` 类正确继承 `GraphMixin`
- [ ] `GraphMixin` 在 `SearchMixin` 之后添加
- [ ] Engine 初始化无错误
- [ ] 所有方法可通过 Engine 实例调用

### MCP 工具
- [ ] `get_neighbors` 工具正确注册
- [ ] `traverse` 工具正确注册
- [ ] `find_paths` 工具正确注册
- [ ] `extract_subgraph` 工具正确注册
- [ ] `graph_search` 工具正确注册
- [ ] 所有工具包含完整的 Docstring
- [ ] 所有工具返回 JSON 字符串
- [ ] JSON 序列化正确处理特殊类型（datetime 等）

### 索引创建
- [ ] 边表 DDL 包含 `__from_id` 索引
- [ ] 边表 DDL 包含 `__to_id` 索引
- [ ] 索引使用 `IF NOT EXISTS` 避免重复创建

## 测试检查

### 单元测试
- [ ] `test_get_neighbors_out_edges` 通过
- [ ] `test_get_neighbors_in_edges` 通过
- [ ] `test_get_neighbors_both_directions` 通过
- [ ] `test_get_neighbors_edge_type_filter` 通过
- [ ] `test_traverse_max_depth` 通过
- [ ] `test_traverse_no_cycles` 通过
- [ ] `test_find_paths_no_path` 通过
- [ ] `test_find_paths_shortest_first` 通过
- [ ] `test_extract_subgraph_limits` 通过
- [ ] `test_graph_search_integration` 通过

### 集成测试
- [ ] 完整工作流测试通过
- [ ] MCP 工具调用测试通过

### 边界测试
- [ ] 节点不存在时的处理正确
- [ ] 空结果的处理正确
- [ ] 参数边界值的处理正确

## 文档检查

### 代码文档
- [ ] 所有公共 API 包含 Docstring
- [ ] Docstring 使用简体中文
- [ ] Docstring 遵循 Google Style

### 用户文档
- [ ] `get_info()` 返回的 Markdown 包含图谱检索说明
- [ ] 包含使用示例
- [ ] 包含参数说明

## 性能检查

### 查询性能
- [ ] 邻居查询在 1000 条边内响应时间 < 100ms
- [ ] 两跳遍历在 10000 条边内响应时间 < 500ms
- [ ] 图谱融合检索响应时间 < 1s

### 资源使用
- [ ] 无内存泄漏
- [ ] 连接正确释放

## 代码规范检查

### Ruff 检查
- [ ] `ruff check` 无错误
- [ ] `ruff format` 格式化通过

### 类型检查
- [ ] 所有公共方法包含完整类型标注
- [ ] 无 `Any` 类型滥用
