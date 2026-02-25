# 实现任务清单 (Tasks)

## Phase 1: 核心架构与配置
- [x] **Task 1.1: 基础结构**
  - 创建 `src/duckkb/core/base.py` - BaseEngine 抽象基类
  - 创建 `src/duckkb/core/mixins/` 目录结构

- [x] **Task 1.2: 基础设施 Mixin**
  - 创建 `ConfigMixin` - 配置读取和解析
  - 创建 `DBMixin` - DuckDB 连接管理

## Phase 2: 业务能力 Mixin
- [x] **Task 2.1: OntologyMixin**
  - 本体定义加载
  - DDL 生成
  - sync_schema 同步

- [x] **Task 2.2: StorageMixin**
  - load_table 使用 read_json_auto
  - dump_table 使用 COPY ... PARTITION_BY
  - load_node/dump_node 便捷方法

- [x] **Task 2.3: SearchMixin**
  - RRF 混合检索
  - vector_search 纯向量检索
  - fts_search 纯全文检索

## Phase 3: 使用层
- [x] **Task 3.1: Engine 多继承类**
  - 聚合所有 Mixin
  - initialize/close 生命周期
  - 上下文管理器支持

- [x] **Task 3.2: 更新导出**
  - 更新 `__init__.py`
  - 清理旧文件

## Phase 4: 清理
- [x] 删除旧文件 (runtime.py, loader.py, persister.py, rrf.py, manager.py)
- [x] ruff 和 mypy 验证通过
