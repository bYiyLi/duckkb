# DuckKB 核心引擎详细差距分析

## 一、已完全符合的设计要求

### 1.1 系统愿景 ✅

| 设计要求    | 实现状态 | 验证代码                        |
| ------- | ---- | --------------------------- |
| 计算与存储解耦 | ✅    | `duckdb.connect()` 无参数      |
| 真理源于文件  | ✅    | `read_json_auto()` 加载 JSONL |
| 确定性还原   | ✅    | `ORDER BY {identity_field}` |

### 1.2 运行时数据布局 ✅

| 表类型   | 设计字段                                                                         | 实现状态 |
| ----- | ---------------------------------------------------------------------------- | ---- |
| 业务主表  | `__id`, `__created_at`, `__updated_at`                                       | ✅    |
| 搜索索引表 | `source_table`, `source_id`, `chunk_seq`, `content`, `fts_content`, `vector` | ✅    |
| 搜索缓存表 | `content_hash`, `fts_content`, `vector`                                      | ✅    |

### 1.3 混合检索 ✅

| 设计要求          | 实现状态                    |
| ------------- | ----------------------- |
| FTS 检索        | ✅ `fts_search()`        |
| Vector 检索     | ✅ `vector_search()`     |
| RRF 融合        | ✅ `search()`            |
| source\_id 回捞 | ✅ `get_source_record()` |

***

## 二、潜在差距分析

### 2.1 FTS 索引创建 ⚠️

**设计要求：**

> FTS 索引自动创建

**当前实现：**

* 使用 `fts_match(fts_content, 'query')` 进行全文检索

* 未显式创建 DuckDB FTS 索引

**差距说明：**
DuckDB 的 `fts_match` 函数需要预先创建 FTS 索引才能使用。当前代码直接调用 `fts_match` 可能会失败。

**需要补充：**

```python
# 在 IndexMixin 中添加
def _create_fts_index(self) -> None:
    """创建全文检索索引。"""
    self.conn.execute(f"""
        PRAGMA create_fts_index(
            '{SEARCH_INDEX_TABLE}', 
            'source_table', 
            'fts_content'
        )
    """)
```

**影响程度：** 中等 - 可能导致全文检索失败

***

### 2.2 边表目录命名 ⚠️

**设计要求：**

```
/data/edges/{label_name}/{YYYYMMDD}/part_{NNN}.jsonl
```

**当前实现：**

```python
# storage.py:268
table_name = f"edge_{edge_name}"  # 例如: edge_REFERENCES
output_dir = self.config.storage.data_dir / "edges" / table_name
# 实际目录: /data/edges/edge_REFERENCES/...
```

**差距：**

* 设计要求：`/data/edges/references/...`

* 当前实现：`/data/edges/edge_REFERENCES/...`

**需要修改：**

```python
# storage.py
output_dir = self.config.storage.data_dir / "edges" / edge_name.lower()
```

**影响程度：** 低 - 目录命名不一致，不影响功能

***

### 2.3 复合主键 Join 策略 ⚠️

**设计要求：**

> 运行时利用 identity 列拼接生成的唯一哈希进行高效 JOIN

**当前实现：**

```python
# storage.py:74
identity_expr = " || '.-.' || ".join(identity_fields)
f"UPDATE {staging_table} SET __id = hash({identity_expr}) WHERE __id IS NULL"
```

**差距：**

* 设计文档建议使用 identity 字段拼接生成哈希

* 当前实现使用 `hash()` 函数，但拼接格式可能不一致

**潜在问题：**
如果 identity 字段包含 `.-.` 分隔符，可能导致哈希冲突。

**建议改进：**

```python
# 使用更安全的分隔符
identity_expr = " || '\x00' || ".join(identity_fields)
```

**影响程度：** 低 - 边缘情况，实际影响小

***

### 2.4 JSONL 格式细节 ⚠️

**设计要求：**

> 导出时 ORDER BY identity。这对于 Git 极为关键

**当前实现：**

```python
# storage.py:171
f"ORDER BY {identity_field}"
```

**验证：**

* ✅ 按 identity 字段排序

* ⚠️ 文件格式是 JSON（单行），不是 JSONL（每行一个 JSON 对象）

**差距说明：**
DuckDB 的 `FORMAT JSON` 输出的是 JSON 数组格式：

```json
[{"__id": 1, ...}, {"__id": 2, ...}]
```

而 JSONL 格式应该是：

```jsonl
{"__id": 1, ...}
{"__id": 2, ...}
```

**需要修改：**

```python
# 使用 FORMAT JSONL（如果 DuckDB 支持）
f") TO '{temp_file}' (FORMAT JSONL)"
```

**验证 DuckDB 是否支持 JSONL：**
DuckDB 的 `COPY` 命令支持 `FORMAT JSON`，输出的是换行分隔的 JSON（实际是 JSONL 格式）。

**实际验证：**
需要测试 DuckDB 的 `FORMAT JSON` 输出格式。

**影响程度：** 中等 - 可能影响 Git Diff 效果

***

### 2.5 \_\_id 持久化验证 ⚠️

**设计要求：**

> 通过物理 ID (\_\_id) 的持久化，确保系统在每次启动后，派生的搜索索引能精准回溯到原始数据

**当前实现：**

```python
# storage.py:75-76
f"UPDATE {staging_table} SET __id = hash({identity_expr}) WHERE __id IS NULL"
```

**验证点：**

1. ✅ 如果 JSONL 文件中已有 `__id`，则保留
2. ✅ 如果 `__id` 为 NULL，则根据 identity 生成
3. ⚠️ 生成的 `__id` 是否确定性？

**潜在问题：**
DuckDB 的 `hash()` 函数是否确定性？不同版本的 DuckDB 可能产生不同的哈希值。

**建议改进：**
使用确定性的哈希算法：

```python
# 在 Python 层计算确定性哈希
import hashlib
def compute_deterministic_id(identity_values: list[str]) -> int:
    combined = "\x00".join(identity_values)
    return int(hashlib.sha256(combined.encode()).hexdigest()[:16], 16)
```

**影响程度：** 中等 - 可能影响跨版本兼容性

***

### 2.6 向量维度验证 ⚠️

**设计要求：**

> embedding\_dim 从 config 读取

**当前实现：**

```python
# config.py
embedding_dim=kb_config.embedding.dim
```

**验证点：**

* ✅ 从配置读取维度

* ⚠️ 向量存储时是否验证维度？

**潜在问题：**
如果 OpenAI 返回的向量维度与配置不一致，可能导致存储错误。

**建议添加验证：**

```python
# embedding.py
async def embed(self, texts: list[str]) -> list[list[float]]:
    embeddings = await self.openai_client.embeddings.create(...)
    for emb in embeddings:
        if len(emb) != self.embedding_dim:
            raise ValueError(f"Embedding dimension mismatch: expected {self.embedding_dim}, got {len(emb)}")
    return embeddings
```

**影响程度：** 低 - 配置错误时才触发

***

### 2.7 事务边界 ⚠️

**设计要求：**

> 原子同步协议：DB 事务写入 -> 分词与切片 -> 影子导出 -> 原子替换 -> 提交

**当前实现：**

```python
# storage.py:55-85
self.conn.begin()
# ... 加载数据 ...
self.conn.commit()
```

**差距：**

* ✅ 加载数据在事务中

* ❌ 索引构建不在同一事务中

* ❌ 导出不在同一事务中

**完整流程应该是：**

```python
async def sync_all(self) -> None:
    self.conn.begin()
    try:
        await self.load_all_nodes()
        await self.build_index()
        await self.dump_all_data()
        self._atomic_replace()  # 原子替换
        self.conn.commit()
    except:
        self.conn.rollback()
        raise
```

**影响程度：** 中等 - 崩溃时可能导致数据不一致

***

## 三、差距优先级排序

### P1 - 应该修复

| 问题         | 影响          | 工作量 |
| ---------- | ----------- | --- |
| FTS 索引创建   | 全文检索可能失败    | 低   |
| JSONL 格式验证 | Git Diff 效果 | 低   |
| 事务边界       | 崩溃一致性       | 中   |

### P2 - 可选优化

| 问题         | 影响      | 工作量 |
| ---------- | ------- | --- |
| 边表目录命名     | 目录结构一致性 | 低   |
| \_\_id 确定性 | 跨版本兼容   | 低   |
| 向量维度验证     | 配置错误处理  | 低   |
| 复合主键分隔符    | 边缘情况    | 低   |

***

## 四、总结

### 完全符合设计 ✅

* 系统愿景（内存模式、真理源于文件、确定性还原）

* 运行时数据布局（三张表结构）

* 混合检索（FTS + Vector + RRF）

* 全局配置读取

* 确定性排序

### 需要补充 ⚠️

1. **FTS 索引创建** - 可能导致全文检索失败
2. **JSONL 格式验证** - 需要确认 DuckDB 输出格式
3. **事务边界** - 当前实现不够完整

### 设计差异（可接受）

1. **边表目录命名** - `edge_{name}` vs `{label_name}`
2. **\_\_id 生成策略** - 使用 `hash()` 而非确定性算法

### 唯一缺失

* **原子替换协议** - P2 优先级

