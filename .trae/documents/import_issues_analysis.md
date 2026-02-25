# 导入逻辑问题分析报告

基于对 `src/duckkb/core/mixins/import_.py` 的代码审查，以下是文档中列出问题的当前状态。

## 问题状态汇总

| # | 问题 | 严重程度 | 当前状态 |
|---|------|---------|---------|
| 1 | Upsert 操作覆盖 `__created_at` | 🔴 严重 | ❌ **未修复** |
| 2 | Upsert 时旧索引条目未删除 | 🔴 严重 | ✅ **已修复** |
| 3 | 边表可能不存在 | 🟡 中等 | ❌ **未修复** |
| 4 | 空内容返回非空列表 | 🟡 中等 | ❌ **未修复** |
| 5 | 缓存表可能不存在 | 🟡 中等 | ❌ **未修复** |
| 6 | 索引表可能不存在 | 🟢 轻微 | ❌ **未修复** |
| 7 | 缺少导入锁 | 🟢 轻微 | ✅ **已修复** |

---

## 详细分析

### 1. ❌ 未修复：Upsert 操作覆盖 `__created_at`

**位置**: 
- `_upsert_nodes_sync` 第 425-426 行
- `_upsert_edges_sync` 第 624-625 行

**问题代码**:
```python
# _upsert_nodes_sync
record["__created_at"] = now
record["__updated_at"] = now

# _upsert_edges_sync
record: dict[str, Any] = {
    "__id": compute_deterministic_id([source_id, target_id]),
    "__from_id": source_id,
    "__to_id": target_id,
    "__created_at": now,
    "__updated_at": now,
}
```

**分析**: 使用 `INSERT OR REPLACE` 时，如果记录已存在，会完全替换整行数据。当前代码在每次 upsert 时都设置 `__created_at = now`，导致更新操作会覆盖原始创建时间。

**建议修复方案**:
1. 方案 A：使用 SQL 的 `COALESCE` 或 `IFNULL` 保留原值
   ```sql
   INSERT INTO table (id, __created_at, __updated_at, ...) 
   VALUES (?, ?, ?, ...)
   ON CONFLICT (id) DO UPDATE SET 
     __created_at = excluded.__created_at,  -- 保留原值
     __updated_at = excluded.__updated_at,
     ...
   ```
2. 方案 B：先查询现有记录，仅对新记录设置 `__created_at`

---

### 2. ✅ 已修复：Upsert 时旧索引条目未删除

**位置**: `_build_index_for_ids_sync` 第 696-721 行

**修复代码**:
```python
def _build_index_for_ids_sync(
    self,
    upserted_ids: dict[str, list[int]],
) -> dict[str, int]:
    """在事务内为变更的记录构建索引（增量更新）。

    先删除旧索引，再重建，确保 chunk 数量变化时旧索引被清理。
    """
    # 先删除所有旧索引
    for node_type, ids in upserted_ids.items():
        if not ids:
            continue
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            continue
        table_name = node_def.table
        placeholders = ", ".join(["?" for _ in ids])
        self.conn.execute(
            f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE source_table = ? AND source_id IN ({placeholders})",
            [table_name] + ids,
        )
    # ... 然后重建索引
```

**分析**: 代码已在构建新索引前删除旧索引条目，问题已修复。

---

### 3. ❌ 未修复：边表可能不存在

**位置**: 
- `_upsert_edges_sync` 第 600 行
- `_delete_edges_sync` 第 665 行

**问题代码**:
```python
# _upsert_edges_sync
table_name = f"edge_{edge_type}"
# 直接使用，未检查表是否存在

# _delete_edges_sync  
table_name = f"edge_{edge_type}"
# 同样未检查
```

**分析**: 如果边表尚未创建，直接执行 SQL 会抛出异常。虽然 `_delete_edges_for_nodes` 方法（第 507 行）已添加表存在性检查，但 `_upsert_edges_sync` 和 `_delete_edges_sync` 方法仍未添加。

**建议修复方案**:
```python
if not self._table_exists(table_name):
    # 对于 upsert：可能需要创建表或跳过
    # 对于 delete：直接返回 0
    return 0  # 或 raise 更明确的错误
```

---

### 4. ❌ 未修复：空内容返回非空列表

**位置**: `_chunk_text_sync` 第 801-817 行

**问题代码**:
```python
def _chunk_text_sync(self, text: str) -> list[str]:
    chunk_size = self.config.global_config.chunk_size
    if len(text) <= chunk_size:
        return [text]  # text 为空字符串时返回 [""]
    # ...
```

**分析**: 当 `text = ""` 时，`len(text) = 0 <= chunk_size`，返回 `[""]`。这会导致创建无意义的空索引条目。

**建议修复方案**:
```python
def _chunk_text_sync(self, text: str) -> list[str]:
    if not text:  # 添加空字符串检查
        return []
    chunk_size = self.config.global_config.chunk_size
    if len(text) <= chunk_size:
        return [text]
    # ...
```

---

### 5. ❌ 未修复：缓存表可能不存在

**位置**: 
- `_get_or_compute_fts_sync` 第 830-859 行
- `_get_or_compute_vector_sync` 第 861-881 行

**问题代码**:
```python
# 直接查询缓存表，未检查是否存在
row = self.conn.execute(
    f"SELECT fts_content FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
    [content_hash],
).fetchone()
```

**分析**: 如果缓存表尚未创建，会抛出异常。

**建议修复方案**: 在使用前检查并创建缓存表，或在初始化时确保表已创建。

---

### 6. ❌ 未修复：索引表可能不存在

**位置**: 
- `_build_index_for_ids_sync`
- `_delete_index_for_ids`

**分析**: 与缓存表问题类似，直接操作索引表而未检查存在性。

**建议修复方案**: 在初始化时确保索引表已创建，或在使用前检查。

---

### 7. ✅ 已修复：缺少导入锁

**位置**: 第 30-33 行，第 75 行

**修复代码**:
```python
def __init__(self, *args, **kwargs) -> None:
    """初始化导入 Mixin。"""
    super().__init__(*args, **kwargs)
    self._import_lock = asyncio.Lock()

async def import_knowledge_bundle(self, temp_file_path: str) -> dict[str, Any]:
    async with self._import_lock:  # 使用锁防止并发导入
        # ...
```

**分析**: 已使用 `asyncio.Lock()` 防止多个导入操作同时执行，问题已修复。

---

## 修复优先级建议

| 优先级 | 问题 | 影响 | 建议措施 |
|--------|------|------|---------|
| **P0** | `__created_at` 覆盖 | 数据完整性问题，创建时间丢失 | 使用 `ON CONFLICT DO UPDATE` 语法保留原值 |
| **P1** | 空内容返回非空列表 | 无意义索引条目，资源浪费 | 添加空字符串检查 |
| **P1** | 边表不存在 | 运行时异常 | 添加表存在性检查 |
| **P1** | 缓存表/索引表不存在 | 运行时异常 | 初始化时创建或使用前检查 |

---

## 下一步行动

需要修复的问题共 5 个：
1. **P0**: `__created_at` 覆盖问题
2. **P1**: 空内容检查
3. **P1**: 边表存在性检查
4. **P1**: 缓存表存在性检查
5. **P1**: 索引表存在性检查
