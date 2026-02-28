# Tasks

- [ ] Task 1: 读取并分析 search.py 文件，了解当前 RRF 实现
  - [ ] Subtask 1.1: 读取 search.py 完整内容
  - [ ] Subtask 1.2: 定位 RRF 相关代码（初始化、分数计算、结果处理）
  - [ ] Subtask 1.3: 记录需要修改的具体位置

- [ ] Task 2: 修改 RRF 常数默认值
  - [ ] Subtask 2.1: 将 `__init__` 方法中的 `rrf_k` 默认值从 60 改为 10
  - [ ] Subtask 2.2: 更新相关注释说明

- [ ] Task 3: 修改 RRF 分数计算逻辑
  - [ ] Subtask 3.1: 在 SQL 查询中增加分数缩放 `* ({self._rrf_k} + 1)`
  - [ ] Subtask 3.2: 确保缩放逻辑应用到所有相关查询

- [ ] Task 4: 增加搜索结果元数据
  - [ ] Subtask 4.1: 修改 `_process_results` 方法
  - [ ] Subtask 4.2: 为每个结果添加 `_meta` 字段（包含 rank 和 rrf_k）

- [ ] Task 5: 验证修改
  - [ ] Subtask 5.1: 运行现有测试用例
  - [ ] Subtask 5.2: 执行搜索功能测试，验证分数范围
  - [ ] Subtask 5.3: 检查元数据是否正确返回

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
- Task 4 依赖 Task 1
- Task 5 依赖 Task 2、Task 3、Task 4
