# 自增 ID 优化方案

## 需求确认

1. **从 JSONL 恢复**：保持原 ID
2. **导入新数据**：让数据库自增 ID
3. **环境处理**：确保 SEQUENCE 正确初始化

***

## 两个场景的处理方式

### 场景 1：从 JSONL 恢复（`load_table`）

**数据来源**：`data/nodes/{table}/**/*.jsonl`、`data/edges/{edge}/**/*.jsonl`

**处理逻辑**：

1. 数据可能已有 `__id`（从之前导出的 JSONL 恢复）
2. 如果有 `__id`，保持原值
3. 如果没有 `__id`，使用 SEQUENCE 生成
4. 导入后同步 SEQUENCE：`MAX(__id) + 1`

**当前实现**：✅ 已正确实现

### 场景 2：导入新数据（`import_knowledge_bundle`）

**数据来源**：用户通过 YAML 提交的新数据

**处理逻辑**：

1. 数据**没有** `__id`（用户不关心内部 ID）
2. 让数据库通过 SEQUENCE 自动生成 ID
3. **不需要**手动同步 SEQUENCE（SEQUENCE 会自动管理）
4. 使用 `RETURNING` 子句获取生成的 ID

**当前问题**：❌ 每次导入后都手动同步 SEQUENCE，这是不必要的

***

## 优化方案

### 修改 `import_.py`

```python
def _upsert_nodes_sync(self, conn, node_type, items):
    # ... 构建记录 ...

    # INSERT 时不指定 __id，让数据库自动生成
    columns = [c for c in records[0].keys() if c != "__id"]
    placeholders = ", ".join(["?" for _ in columns])
    batch_params = [[record[c] for c in columns] for record in records]

    # 使用 RETURNING 获取生成的 ID
    # DuckDB 支持 RETURNING，但与 executemany 不兼容
    # 改用单条 INSERT ... SELECT 或循环插入

    # 方案：不手动同步 SEQUENCE，让数据库管理
    conn.executemany(
        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({identity_cols}) DO UPDATE SET {update_set}",
        batch_params,
    )

    # 移除手动同步 SEQUENCE 的代码
    # SEQUENCE 会自动递增，不需要干预

    # 获取插入/更新记录的 ID
    identity_placeholders = " AND ".join(f"{f} = ?" for f in node_def.identity)
    record_ids = []
    for record in records:
        identity_values = [record.get(f) for f in node_def.identity]
        row = conn.execute(
            f"SELECT __id FROM {table_name} WHERE {identity_placeholders}",
            identity_values,
        ).fetchone()
        if row:
            record_ids.append(row[0])

    return record_ids, len(records)
```

### 保持 `storage.py` 不变

`load_table` 需要处理「从 JSONL 恢复时保持原 ID」的场景，当前实现正确。

***

## 环境初始化

### 表创建时 SEQUENCE 初始化

```sql
CREATE SEQUENCE IF NOT EXISTS table_name_id_seq START 1;
CREATE TABLE IF NOT EXISTS table_name (
    __id BIGINT PRIMARY KEY DEFAULT nextval('table_name_id_seq'),
    ...
);
```

### 从 JSONL 恢复后 SEQUENCE 同步

```python
# load_table 中
max_id = conn.execute(f"SELECT COALESCE(MAX(__id), 0) FROM {table_name}").fetchone()[0]
conn.execute(f"DROP SEQUENCE IF EXISTS {seq_name}")
conn.execute(f"CREATE SEQUENCE {seq_name} START {max_id + 1}")
```

***

## 需要修改的文件

| 文件           | 修改内容                                                              |
| ------------ | ----------------------------------------------------------------- |
| `import_.py` | 移除 `_upsert_nodes_sync` 和 `_upsert_edges_sync` 中的手动同步 SEQUENCE 代码 |
| `storage.py` | 保持不变（load\_table 需要同步 SEQUENCE）                                   |

***

## 实施步骤

1. 修改 `import_.py`：移除手动同步 SEQUENCE
2. 运行测试验证

