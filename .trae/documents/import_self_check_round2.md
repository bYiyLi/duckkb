# 导入逻辑第二轮自检报告

## 已修复的问题 ✅

| 问题 | 状态 |
|------|------|
| 影子导出导致数据丢失 | ✅ 已修复 |
| 索引构建逻辑错误 | ✅ 已修复 |
| 删除节点时未处理相关边 | ✅ 已修复 |
| 向量嵌入无法计算 | ✅ 已修复 |
| 异常处理和清理 | ✅ 已修复 |
| 空数据处理 | ✅ 已修复 |

---

## 新发现的问题

### 1. 🔴 严重：DuckDB DELETE 不返回删除行数

**位置**: `_delete_edges_for_nodes` (第 500-508 行), `_delete_index_for_ids` (第 525-531 行)

**问题**: DuckDB 的 `DELETE` 语句执行后 `fetchone()` 不会返回删除的行数。这会导致 `total_deleted` 始终为 0。

```python
result = self.conn.execute(f"DELETE FROM {table_name} WHERE ...")
row = result.fetchone()
if row:
    total_deleted += row[0] if isinstance(row[0], int) else 0  # row 永远是 None
```

**修复方案**: 使用 DuckDB 的 `changes()` 函数或先查询再删除。

---

### 2. 🔴 严重：COPY TO FORMAT 不匹配

**位置**: `_dump_table_to_dir` (第 1077-1082 行)

**问题**: 使用 `FORMAT JSON` 输出 JSON 数组格式，但文件扩展名是 `.jsonl`。应该使用 `FORMAT JSONL`。

```python
self.conn.execute(
    f"COPY (...) TO '{temp_file}' (FORMAT JSON)"  # 输出 JSON 数组
)
# 但文件名是 part_0.jsonl，应该是 JSON Lines 格式
```

**修复方案**: 改为 `FORMAT JSONL` 或将文件扩展名改为 `.json`。

---

### 3. 🟡 中等：原子替换目录的竞态条件

**位置**: `_atomic_replace_data_dir` (第 1123-1132 行)

**问题**: 如果 backup_dir 已存在，先删除它再重命名 data_dir。如果在这两步之间发生崩溃，可能导致数据丢失。

```python
def _replace() -> None:
    if data_dir.exists():
        if backup_dir.exists():
            shutil.rmtree(backup_dir)  # 步骤 1: 删除 backup
        os.rename(str(data_dir), str(backup_dir))  # 步骤 2: 重命名 data -> backup
        # 如果这里崩溃，data_dir 就丢失了！
    os.rename(str(shadow_dir), str(data_dir))  # 步骤 3
```

**修复方案**: 使用时间戳命名 backup_dir，避免删除操作。

---

### 4. 🟡 中等：deleted_ids 参数未使用

**位置**: `_build_index_for_ids_sync` (第 646-736 行)

**问题**: 方法接收 `deleted_ids` 参数但从未使用。索引删除是在 `_delete_nodes_sync` 中完成的，这个参数是多余的。

```python
def _build_index_for_ids_sync(
    self,
    upserted_ids: dict[str, list[int]],
    deleted_ids: dict[str, list[int]],  # 未使用
) -> dict[str, int]:
```

**修复方案**: 移除未使用的参数，或在方法中处理删除索引（保持职责单一）。

---

### 5. 🟡 中等：向量保存缺少事务保护

**位置**: `_save_vector_to_cache` (第 961-991 行)

**问题**: 先插入缓存，再更新索引。如果更新索引失败，缓存中有数据但索引中没有。

```python
def _save_vector_to_cache(...) -> None:
    self.conn.execute(f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} ...")  # 步骤 1
    self.conn.execute(f"UPDATE {SEARCH_INDEX_TABLE} ...")  # 步骤 2，可能失败
```

**修复方案**: 应该在同一事务中执行，或先更新索引再插入缓存。

---

### 6. 🟢 轻微：边表存在性检查缺失

**位置**: `_delete_edges_for_nodes` (第 497-508 行)

**问题**: 假设所有边表都存在。如果某个边表不存在，会抛出异常。

```python
for edge_name in self.ontology.edges.keys():
    table_name = f"edge_{edge_name}"
    # 如果表不存在，execute 会抛出异常
    result = self.conn.execute(f"DELETE FROM {table_name} ...")
```

**修复方案**: 添加表存在性检查或 try-except。

---

### 7. 🟢 轻微：向量计算失败只记录日志

**位置**: `_compute_vectors_async` (第 916-917 行)

**问题**: 向量计算失败时只记录日志，不抛出异常。这可能导致部分记录没有向量，影响搜索质量，但用户不知道。

```python
except Exception as e:
    logger.error(f"Failed to compute vector: {e}")  # 只记录日志，继续执行
```

**修复方案**: 考虑在返回结果中标记失败的记录，或提供重试机制。

---

### 8. 🟢 轻微：缺少并发控制

**位置**: 整个导入流程

**问题**: 没有锁机制防止多个导入操作同时执行，可能导致数据竞争。

**修复方案**: 添加分布式锁或文件锁。

---

## 修复优先级

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | DuckDB DELETE 不返回删除行数 | 统计数据不准确 |
| P0 | COPY TO FORMAT 不匹配 | 文件格式错误 |
| P1 | 原子替换目录竞态条件 | 极端情况下数据丢失 |
| P1 | deleted_ids 参数未使用 | 代码冗余 |
| P1 | 向量保存缺少事务保护 | 数据不一致 |
| P2 | 边表存在性检查缺失 | 边缘情况异常 |
| P2 | 向量计算失败只记录日志 | 搜索质量下降 |
| P3 | 缺少并发控制 | 数据竞争 |

---

## 建议的修复计划

### Phase 1: 修复严重问题
1. 修复 DELETE 返回值问题 - 移除对返回值的依赖
2. 修复 COPY TO FORMAT - 改为 FORMAT JSONL

### Phase 2: 修复中等问题
3. 改进原子替换逻辑 - 使用时间戳命名 backup
4. 移除未使用的 deleted_ids 参数
5. 为向量保存添加事务保护

### Phase 3: 改进健壮性
6. 添加边表存在性检查
7. 改进向量计算失败处理
8. 添加并发控制（可选）
