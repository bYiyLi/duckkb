# DuckKB 核心引擎重构规范 (Core Engine Refactor Spec)

## 1. 目标与愿景 (Why)
现有代码结构存在耦合度高、扩展性差的问题，且大量使用了低效的 Python 循环处理 I/O，未充分利用 DuckDB 的高性能特性。
本规范旨在基于设计文档，**从零构建**一个全新的核心引擎 (`src/duckkb/core`)，核心原则是**“能用 SQL 解决的绝不写 Python 循环”**。

## 2. 架构设计 (Architecture)

### 2.1 模块结构
```
src/duckkb/core/
├── config/           # 配置定义 (Pydantic Models)
├── ontology/         # 本体管理 (Schema生成, DDL同步)
├── storage/          # 存储层 (SQL-driven IO)
├── search/           # 检索引擎 (RRF Strategy)
└── runtime.py        # 运行时入口
```

### 2.2 关键设计模式
*   **Repository Pattern**: 封装 DuckDB SQL 操作。
*   **Strategy Pattern**: 检索策略 (Vector/FTS/Hybrid)。
*   **ELT (Extract-Load-Transform)**: 替代传统的 ETL。先把 JSONL Load 进 DuckDB 临时表，再通过 SQL Transform/Merge 到主表。

## 3. 核心特性实现 (Features)

### 3.1 Ontology 驱动 (Ontology Engine)
*   **Schema Sync**:
    *   启动时根据 Config 生成 DDL。
    *   Node 表: `CREATE TABLE IF NOT EXISTS {table} (__id BIGINT PRIMARY KEY, __date DATE, ...)`。
    *   Edge 表: `CREATE TABLE IF NOT EXISTS {table} (__id BIGINT PRIMARY KEY, __from_id BIGINT, __to_id BIGINT, __date DATE, ...)`。
    *   注意：增加 `__date` 虚拟列（Generated Column 或 View），用于分区导出。

### 3.2 存储层 (Storage Layer) - SQL Driven
*   **Loader (SQL-Based)**:
    1.  **Staging**: `CREATE TEMP TABLE staging AS SELECT * FROM read_json_auto('data/nodes/{table}/**/*.jsonl', union_by_name=true)`.
    2.  **Merge**: 使用 `INSERT OR REPLACE INTO {table} SELECT * FROM staging` (或 `DELETE` + `INSERT`) 实现全量/增量同步。
    3.  **ID Generation**: `UPDATE {table} SET __id = hash(identity) WHERE __id IS NULL`.
*   **Persister (SQL-Based)**:
    *   使用 DuckDB 的 **Partitioned Write** 特性。
    *   `COPY (SELECT *, strftime(__updated_at, '%Y%m%d') as part_date FROM {table} ORDER BY __id) TO 'data/nodes/{table}' (FORMAT JSON, PARTITION_BY (part_date), OVERWRITE_OR_IGNORE)`.
    *   这样会自动生成 `data/nodes/{table}/part_date={YYYYMMDD}/data_0.json` 结构。

### 3.3 检索引擎 (Search Engine)
*   **RRF Strategy**:
    *   利用 DuckDB 的 `rank()` 窗口函数在数据库内完成计算。
    *   避免将大量数据拉取到 Python 层处理。

## 4. 详细变更 (What Changes)

### Phase 1: Core Skeleton
- 创建 `src/duckkb/core` 目录。

### Phase 2: Ontology & Storage
- **OntologyManager**: 生成带分区支持的 DDL。
- **DuckDBLoader**:
    - `load_table(table_name, path_pattern)`: 执行 `read_json_auto` 和 `MERGE` SQL。
- **DuckDBPersister**:
    - `dump_table(table_name, output_dir)`: 执行 `COPY ... PARTITION_BY` SQL。

### Phase 3: Search
- **RRFStrategy**: 生成高效的混合检索 SQL。

## 5. 影响范围 (Impact)
*   **Performance**: I/O 性能将有数量级提升（Python Loop -> C++ Vectorized Execution）。
*   **Code Complexity**: Python 代码量大幅减少，SQL 复杂度增加。
