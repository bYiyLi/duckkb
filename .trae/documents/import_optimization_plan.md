# DuckKB 导入功能优化实施计划

## 概述

根据 `import_features_summary.md` 和原子同步协议 (Shadow Copy) 要求，对 `import_.py` 进行重构。

## 原子同步协议要求

```
流程：
  DB 事务写入 → 分词与切片 → 影子导出 → 原子替换 → 提交

详细步骤：
1. DB 事务写入: 在事务中更新业务表和 search_index
2. 分词与切片: 对变更内容执行 Chunking -> 分词处理 -> 向量查询（优先读缓存）
3. 影子导出:
   - 业务数据: 强制按 identity 排序，COPY ... TO ... (FORMAT JSONL)
   - 缓存数据: COPY ... TO ... (FORMAT PARQUET)
4. 原子替换: 在操作系统层面通过 rename 瞬间替换旧的 data/ 目录
5. 提交: 完成 COMMIT
```

## 当前实现问题

| 协议要求                         | 当前实现                         | 状态    |
| ---------------------------- | ---------------------------- | ----- |
| DB 事务写入（业务表 + search\_index） | 业务表写入有事务，但索引重建在事务外           | ❌     |
| 分词与切片在事务内                    | 索引重建在事务外执行                   | ❌     |
| 影子导出（先写临时文件）                 | `dump_table` 有临时文件，但不是影子目录模式 | ⚠️ 部分 |
| 缓存数据导出 Parquet               | 导入时未导出缓存                     | ❌     |
| 原子替换 data/ 目录                | 无此逻辑                         | ❌     |
| 最后 COMMIT                    | 索引和导出在事务外                    | ❌     |

***

## Phase 1: 单一事务框架重构

### 目标

* 使用单一事务包装所有数据库操作（业务表写入 + 索引构建）

* 支持同批次先创建节点再创建边

* 边引用完整性验证失败时自动回滚

### 实施步骤

1. **添加** **`_node_exists_in_transaction`** **方法**

   * 在事务内检查节点是否存在（包括未提交的数据）

2. **添加** **`_validate_edge_references`** **方法**

   * 验证边的 source/target 节点是否存在

3. **添加同步导入方法**

   * `_import_nodes_sync`: 同步导入节点

   * `_import_edges_sync`: 同步导入边

   * `_upsert_nodes_sync`: 同步 upsert 节点

   * `_delete_nodes_sync`: 同步删除节点

   * `_upsert_edges_sync`: 同步 upsert 边

   * `_delete_edges_sync`: 同步删除边

4. **添加** **`_build_index_for_ids_sync`** **方法**

   * 在事务内为指定 ID 的记录构建索引

5. **添加** **`_execute_import_in_transaction`** **方法**

   * 使用单一事务包装所有数据库操作

   * 流程：开启事务 → 导入节点 → 导入边 → 验证边引用 → 构建索引 → 提交/回滚

6. **重构** **`import_knowledge_bundle`** **主方法**

   * 使用新的单一事务流程

***

## Phase 2: 影子导出机制

### 目标

* 实现影子目录导出，确保导出失败不影响原有数据

* 支持原子替换 data/ 目录

### 实施步骤

1. **添加** **`_dump_to_shadow_dir`** **方法**

   * 创建影子目录 `{data_dir}_shadow/`

   * 导出业务数据到影子目录

   * 导出缓存数据到影子目录

2. **添加** **`_atomic_replace_data_dir`** **方法**

   * 使用 `os.rename` 原子替换目录

3. **修改** **`import_knowledge_bundle`**

   * 事务提交后执行影子导出

   * 导出成功后执行原子替换

***

## Phase 3: 缓存持久化

### 目标

* 导入完成后将 search\_cache 导出为 Parquet

### 实施步骤

1. **添加** **`_dump_cache_to_parquet`** **方法**

   * 将 `_sys_search_cache` 导出到 `cache/search_cache.parquet`

2. **修改影子导出流程**

   * 包含缓存数据导出

***

## Phase 4: 批量操作优化

### 目标

* 使用 `executemany` 替代逐条执行，减少数据库交互次数

### 实施步骤

1. **重构** **`_upsert_nodes_sync`** **方法**

   * 使用 `executemany` 批量插入

2. **重构** **`_delete_nodes_sync`** **方法**

   * 使用批量删除

3. **重构** **`_upsert_edges_sync`** **方法**

   * 使用 `executemany` 批量插入

4. **重构** **`_delete_edges_sync`** **方法**

   * 使用批量删除

***

## 最终流程

```
import_knowledge_bundle:
1. 读取 YAML 文件
2. Schema 校验
3. 开启事务
   3.1 导入节点（业务表）
   3.2 导入边（业务表）
   3.3 验证边引用完整性
   3.4 构建索引（search_index）
   3.5 提交事务（失败则回滚）
4. 影子导出
   4.1 创建影子目录 {data_dir}_shadow/
   4.2 导出业务数据（JSONL，按 identity 排序）
   4.3 导出缓存数据（PARQUET）
5. 原子替换
   5.1 rename {data_dir}_shadow/ -> {data_dir}/
6. 删除临时文件
7. 返回结果
```

***

## 文件变更

| 文件                                  | 变更类型      |
| ----------------------------------- | --------- |
| `src/duckkb/core/mixins/import_.py` | 重构 + 新增方法 |

## 风险与注意事项

1. **事务边界变化**：原实现每个节点类型独立事务，新实现使用单一事务，需确保 DuckDB 事务行为正确
2. **目录替换**：原子替换需要确保目标目录不存在或为空
3. **并发安全**：导入过程中应阻止其他写入操作
4. **向后兼容**：确保返回值结构保持兼容

## 验证方法

1. 运行现有测试确保不破坏已有功能
2. 添加测试验证边引用完整性检查
3. 添加测试验证事务回滚行为
4. 添加测试验证影子导出和原子替换

