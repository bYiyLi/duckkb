# DuckKB 核心引擎修复计划

## 需要修复的问题

### 1. 边表目录命名

**问题：**
- 设计要求：`/data/edges/{label_name}/{YYYYMMDD}/part_{NNN}.jsonl`
- 当前实现：`/data/edges/edge_{edge_name}/{YYYYMMDD}/part_{NNN}.jsonl`

**修复方案：**
```python
# storage.py - dump_edge()
# 修改前
table_name = f"edge_{edge_name}"
output_dir = self.config.storage.data_dir / "edges" / table_name

# 修改后
output_dir = self.config.storage.data_dir / "edges" / edge_name.lower()
```

---

### 2. __id 生成策略

**问题：**
- 当前使用 DuckDB 的 `hash()` 函数，可能跨版本不一致
- 设计要求使用确定性算法

**修复方案：**
```python
# storage.py - load_table()
# 修改前
identity_expr = " || '.-.' || ".join(identity_fields)
f"UPDATE {staging_table} SET __id = hash({identity_expr}) WHERE __id IS NULL"

# 修改后 - 在 Python 层计算确定性哈希
import hashlib

def _compute_deterministic_id(identity_values: list[str]) -> int:
    """计算确定性 ID。"""
    combined = "\x00".join(str(v) for v in identity_values)
    hash_hex = hashlib.sha256(combined.encode()).hexdigest()
    return int(hash_hex[:16], 16)
```

---

### 3. 事务边界

**问题：**
- 当前加载数据在事务中，但索引构建和导出不在同一事务
- 设计要求完整的原子同步协议

**修复方案：**
```python
# 新增 SyncMixin 或在 StorageMixin 中添加
async def sync_node(self, node_type: str) -> dict:
    """原子同步节点数据。
    
    流程：
    1. 加载数据（事务）
    2. 构建索引（同一事务）
    3. 导出数据
    4. 原子替换（可选）
    """
    self.conn.begin()
    try:
        loaded = await self.load_node(node_type)
        indexed = await self.rebuild_index(node_type)
        dumped = await self.dump_node(node_type)
        self.conn.commit()
        return {"loaded": loaded, "indexed": indexed, "dumped": dumped}
    except Exception:
        self.conn.rollback()
        raise
```

---

## 实施步骤

### Step 1: 修复边表目录命名
- 修改 `storage.py` 中的 `dump_edge()` 和 `load_edge()` 方法

### Step 2: 修复 __id 生成策略
- 在 `storage.py` 中添加确定性哈希函数
- 修改 `load_table()` 方法使用确定性 ID

### Step 3: 完善事务边界
- 在 `storage.py` 中添加 `sync_node()` 和 `sync_edge()` 方法
- 确保加载、索引构建、导出在同一事务中
