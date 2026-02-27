# Tasks

- [x] Task 1: 修复混合搜索字段映射问题
  - [x] SubTask 1.1: 分析 `_execute_hybrid_search` SQL 查询返回的列顺序
  - [x] SubTask 1.2: 修复 `_process_results` 方法的字段名映射逻辑
  - [x] SubTask 1.3: 添加测试用例验证字段映射正确性

- [x] Task 2: 修复全文搜索返回空结果问题
  - [x] SubTask 2.1: 检查 FTS 索引创建和查询逻辑
  - [x] SubTask 2.2: 修复 `fts_search` 的 SQL 查询参数传递
  - [x] SubTask 2.3: 添加测试用例验证全文搜索功能

- [x] Task 3: 修复 datetime 序列化问题
  - [x] SubTask 3.1: 在 `get_source_record` 中添加 datetime 处理
  - [x] SubTask 3.2: 确保 JSON 序列化使用 `default=str` 或自定义序列化器
  - [x] SubTask 3.3: 添加测试用例验证 datetime 序列化

- [x] Task 4: 修复图遍历邻居节点字段名问题
  - [x] SubTask 4.1: 修复 `_query_direction` 方法的字段名获取逻辑
  - [x] SubTask 4.2: 使用 `_get_table_columns` 获取正确的列名
  - [x] SubTask 4.3: 添加测试用例验证字段名正确性

- [x] Task 5: 优化邻居节点去重逻辑
  - [x] SubTask 5.1: 在 `get_neighbors` 中添加邻居去重逻辑
  - [x] SubTask 5.2: 保留边的方向信息
  - [x] SubTask 5.3: 添加测试用例验证去重功能

- [x] Task 6: 完善子图提取边属性返回
  - [x] SubTask 6.1: 修改 `extract_subgraph` 获取完整边属性
  - [x] SubTask 6.2: 添加测试用例验证边属性完整性

- [x] Task 7: 完善 SQL 安全限制机制
  - [x] SubTask 7.1: 在 `query_raw_sql` 中添加 SQL 语句类型检测
  - [x] SubTask 7.2: 对非 SELECT 语句返回明确错误提示
  - [x] SubTask 7.3: 添加测试用例验证安全拦截

- [x] Task 8: 完善参数前置校验
  - [x] SubTask 8.1: 添加 limit 参数非负校验
  - [x] SubTask 8.2: 添加 max_depth 参数正整数校验
  - [x] SubTask 8.3: 优化错误提示信息

# Task Dependencies

- [Task 3] 可与 [Task 1], [Task 2], [Task 4] 并行执行
- [Task 5] 依赖 [Task 4] 完成
- [Task 6] 依赖 [Task 4] 完成
- [Task 7], [Task 8] 可与其他任务并行执行
