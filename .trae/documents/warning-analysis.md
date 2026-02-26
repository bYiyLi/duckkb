# DuckKB 启动 WARNING 分析

## 问题概述

启动 `duckkb serve` 时出现 6 个 WARNING，分为两类问题：

### 问题 1：Character 节点加载失败（需要修复）

```
WARNING  Failed to load node type Character: Binder Error: table characters has 10 columns but 11 values were supplied
```

**根本原因**：

1. `__date` 字段在表定义中是 `VIRTUAL` 虚拟列（自动从 `__updated_at` 派生）
2. 导出 JSONL 时，`COPY ... TO` 语句将虚拟列也导出了
3. 重新加载时，JSONL 文件包含 11 列（含 `__date`），但表实际只有 10 列（虚拟列不占存储）

**`__date`** **字段分析**：

`__date` 字段设计初衷是用于按日期分区存储，但实际代码中：

* 导出时：`_dump_partitioned_by_date` 直接使用 `strftime(__updated_at, '%Y%m%d')` 计算日期

* 查询时：没有任何地方使用 `__date` 字段

**结论**：`__date` 字段目前**没有被实际使用**，可以直接移除。

**代码位置**：

* 表定义：[ontology.py:135](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/core/mixins/ontology.py#L135) - `__date DATE GENERATED ALWAYS AS ... VIRTUAL`

* 边表定义：[ontology.py:173](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/core/mixins/ontology.py#L173)

**修复方案**：

移除 `__date` 虚拟列定义，因为：

1. 它没有被使用
2. 它导致了导出/导入的数据不一致问题
3. 如果将来需要按日期查询，可以直接用 `CAST(__updated_at AS DATE)`

### 问题 2：数据文件不存在（正常现象）

```
WARNING  Failed to load node type Document: IO Error: No files found that match the pattern
WARNING  Failed to load node type Product: IO Error: No files found that match the pattern
WARNING  Failed to load edge type knows: IO Error: No files found that match the pattern
WARNING  Failed to load edge type authored: IO Error: No files found that match the pattern
WARNING  Failed to load edge type mentions: IO Error: No files found that match the pattern
```

**原因**：这些节点/边类型的数据文件尚未创建，是正常的空数据状态。

**建议**：可以将此日志级别从 WARNING 降为 DEBUG，避免误导用户。

## 修复计划

### 必须修复

1. **修改** **`ontology.py`**：移除节点表和边表中的 `__date` 虚拟列定义

### 建议优化

1. **修改** **`engine.py`** **加载逻辑**：当文件不存在时使用 DEBUG 级别日志而非 WARNING

## 影响评估

* **问题 1**：会导致已有数据无法正确加载，**需要修复**

* **问题 2**：仅是日志噪音，不影响功能，**可选优化**

