# 实现任务清单 (Tasks)

## Phase 1: 核心架构与配置
- [ ] **Task 1.1: 基础结构**
  - 创建 `src/duckkb/core` 目录。
  - 定义 `KBConfig` 等模型。

- [ ] **Task 1.2: Ontology SQL 生成**
  - 实现 `OntologyManager`。
  - 生成建表语句，确保包含 `__id` 和用于分区的日期字段（如从 `__updated_at` 派生）。

## Phase 2: SQL 驱动的存储层
- [ ] **Task 2.1: SQL Loader**
  - 实现 `src/duckkb/core/storage/loader.py`。
  - 使用 `read_json_auto` 加载数据到临时表。
  - 使用 SQL `INSERT OR REPLACE` 或 `MERGE` 同步到主表。
  - 使用 SQL 生成缺失的 `__id`。

- [ ] **Task 2.2: SQL Persister**
  - 实现 `src/duckkb/core/storage/persister.py`。
  - 使用 `COPY ... TO ... (FORMAT JSON, PARTITION_BY (...))` 实现自动分片导出。
  - 验证导出的目录结构是否符合预期。

## Phase 3: 检索引擎
- [ ] **Task 3.1: RRF 搜索**
  - 实现 `RRFStrategy`。
  - 编写包含 `RANK()` 和 `CTE` 的复杂 SQL。

## Phase 4: 集成
- [ ] **Task 4.1: Runtime 集成**
  - 替换旧的 Python I/O 逻辑。
  - 验证全流程。
