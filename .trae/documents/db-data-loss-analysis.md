# DuckKB 数据库设计数据丢失风险分析

## 一、项目架构概述

### 1.1 数据存储架构

```
┌─────────────────────────────────────────────────────────────┐
│                 DuckDB (临时文件模式)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ 业务表(节点) │  │ 业务表(边)  │  │ _sys_search_index    │ │
│  └─────────────┘  └─────────────┘  │ _sys_search_cache    │ │
│                                     └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ 导入时写入 / 启动时加载
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      文件系统 (真理源)                        │
│  data/                                                       │
│  ├── nodes/{table_name}/**/*.jsonl                          │
│  ├── edges/{edge_name}/**/*.jsonl                           │
│  └── cache/search_cache.parquet                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 数据流分析

```
启动流程:
  Engine.async_initialize()
    → sync_schema()           # 同步表结构
    → create_index_tables()   # 创建索引表
    → _load_existing_data()   # 加载已有数据
        → load_node()         # 加载节点 JSONL
        → load_edge()         # 加载边 JSONL
        → load_cache_from_parquet()  # 加载缓存

导入流程:
  import_knowledge_bundle()
    → YAML 解析 + Schema 校验
    → 开启事务
        → 导入节点 (业务表)
        → 导入边 (业务表)
        → 验证边引用完整性
        → 构建索引 (search_index)
        → 提交事务
    → 异步计算向量嵌入
    → 影子导出 (data_shadow/)
    → 原子替换 data/ 目录
```

***

## 二、已修复的问题（对比历史分析）

### ✅ 问题 1：引擎初始化不加载数据（已修复）

**历史状态**: `initialize()` 只同步表结构，不加载数据

**当前状态**: 已添加 `async_initialize()` 方法

**代码位置**: [engine.py:116-127](file:///Users/yi/Code/duckkb/src/duckkb/core/engine.py#L116-L127)

```python
async def async_initialize(self) -> Self:
    self.sync_schema()
    self.create_index_tables()
    await self._load_existing_data()  # ✅ 加载已有数据
    return self
```

**MCP 服务已使用异步初始化**: [duck\_mcp.py:29](file:///Users/yi/Code/duckkb/src/duckkb/mcp/duck_mcp.py#L29)

```python
await duck_mcp.async_initialize()  # ✅ 使用异步初始化
```

***

### ✅ 问题 2：缓存不恢复（已修复）

**历史状态**: 导出缓存但不恢复

**当前状态**: `_load_existing_data()` 会加载缓存

**代码位置**: [engine.py:167-173](file:///Users/yi/Code/duckkb/src/duckkb/core/engine.py#L167-L173)

```python
cache_path = data_dir / "cache" / "search_cache.parquet"
if cache_path.exists():
    cache_count = await self.load_cache_from_parquet(cache_path)
```

***

## 三、当前存在的数据丢失风险

### 🔴 风险 1：同步初始化方法不加载数据（严重）

**位置**: [engine.py:103-114](file:///Users/yi/Code/duckkb/src/duckkb/core/engine.py#L103-L114)

```python
def initialize(self) -> Self:
    """初始化引擎。
    注意：此方法不加载数据，需要异步加载请使用 async_initialize()。
    """
    self.sync_schema()
    self.create_index_tables()
    return self  # ❌ 不加载数据
```

**影响**:

* 使用同步上下文管理器 `with Engine(...) as e:` 时数据不会加载

* CLI 工具如果使用同步初始化，数据不可访问

**复现路径**:

```python
with Engine("/path/to/kb") as engine:  # 调用 initialize()
    results = await engine.search("query")  # 返回空结果
```

**修复建议**:

1. 在 `initialize()` 中添加警告日志
2. 或在 `__enter__` 中调用异步初始化（需要重构）

***

### 🟡 风险 2：向量计算在事务外异步执行（中等）

**位置**: [import\_.py:120](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/import_.py#L120)

```python
result = await self._execute_import_in_transaction(nodes_data, edges_data)
# 事务已提交
vector_result = await self._compute_vectors_async(upserted_ids)  # ⚠️ 事务外
```

**影响**:

* 事务提交后、向量计算完成前崩溃

* 数据已持久化到 JSONL

* 但 `search_index.vector` 字段为 NULL

* 向量搜索功能降级（非数据丢失）

**恢复方案**: 重建向量索引

***

### 🟡 风险 3：临时数据库文件清理策略（中等）

**位置**: [db.py:156-179](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/db.py#L156-L179)

```python
def _cleanup_on_exit(self) -> None:
    """程序退出时清理临时文件。"""
    if self._cleaned_up:
        return
    self._cleanup_temp_files()  # 可能删除未持久化的数据
```

**影响**:

* 如果导入流程在"影子导出"前崩溃

* 临时数据库文件被清理

* 未持久化的数据丢失

**缓解措施**:

* 导入流程使用 `_import_lock` 互斥

* 影子导出 + 原子替换确保一致性

***

### 🟢 风险 4：边引用完整性验证时机（已正确处理）

**位置**: [import\_.py:195-244](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/import_.py#L195-L244)

```python
def _validate_edge_references(self, conn, edge_type, items):
    # 在事务内验证 source/target 节点是否存在
    # 包括同一事务中刚插入的数据
```

**评估**: 在事务内执行，验证失败会回滚，无数据丢失风险

***

### 🟢 风险 5：删除节点时边的级联删除（已正确处理）

**位置**: [import\_.py:458-503](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/import_.py#L458-L503)

```python
def _delete_nodes_sync(self, conn, node_type, items):
    # ...
    self._delete_edges_for_nodes(conn, record_ids)  # ✅ 先删除相关边
    self._delete_index_for_ids(table_name, record_ids)  # ✅ 再删除索引
    # 最后删除节点
```

**评估**: 在事务内级联删除，无数据丢失风险

***

### 🟢 风险 6：原子替换 data/ 目录（已正确处理）

**位置**: [import\_.py:1282-1305](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/import_.py#L1282-L1305)

```python
async def _atomic_replace_data_dir(self):
    # 使用操作系统级别的 rename 操作
    # 使用时间戳 + UUID 命名 backup 目录
    os.rename(str(data_dir), str(backup_dir))  # 原子操作
    os.rename(str(shadow_dir), str(data_dir))  # 原子操作
```

**评估**: 影子目录模式确保原子性，无数据丢失风险

***

## 四、潜在改进点

### 4.1 同步初始化方法警告

**建议**: 在 `initialize()` 中添加警告日志

```python
def initialize(self) -> Self:
    self.sync_schema()
    self.create_index_tables()
    logger.warning(
        "initialize() does not load existing data. "
        "Use async_initialize() for full initialization."
    )
    return self
```

### 4.2 向量计算失败补偿

**建议**: 添加向量计算失败标记和重试机制

```python
# 在 _compute_vectors_async 失败时
except Exception as e:
    await self._mark_vectors_pending(upserted_ids)
    logger.warning(f"Vector computation failed, marked for retry: {e}")
```

### 4.3 数据一致性检查工具

**建议**: 添加启动时的数据一致性检查

```python
async def verify_data_integrity(self) -> dict[str, Any]:
    """验证数据库与文件系统数据一致性。"""
    # 检查 JSONL 文件与数据库记录数是否匹配
    # 检查索引完整性
    # 检查向量覆盖率
```

***

## 五、总结

### 5.1 风险矩阵

| 风险         | 严重程度  | 状态  | 说明               |
| ---------- | ----- | --- | ---------------- |
| 同步初始化不加载数据 | 🔴 严重 | 存在  | 使用同步 API 时数据不可访问 |
| 向量计算事务外    | 🟡 中等 | 存在  | 功能降级，非数据丢失       |
| 临时文件清理     | 🟡 中等 | 缓解  | 导入崩溃可能丢失未持久化数据   |
| 边引用完整性     | 🟢 低  | 已处理 | 事务内验证            |
| 级联删除       | 🟢 低  | 已处理 | 事务内执行            |
| 原子替换       | 🟢 低  | 已处理 | 影子目录模式           |

### 5.2 结论

**当前数据库设计总体安全**，主要的数据丢失风险已在历史版本中修复：

1. ✅ 引擎异步初始化会加载已有数据
2. ✅ MCP 服务使用异步初始化
3. ✅ 缓存会在启动时恢复
4. ✅ 导入流程使用事务保证原子性
5. ✅ 影子目录模式确保持久化一致性

**剩余风险**：

1. **同步初始化 API 不加载数据** - 需要文档说明或 API 重构
2. **向量计算失败** - 功能降级，需要重试机制

### 5.3 建议

1. **短期**: 在 `initialize()` 添加警告日志，提醒用户使用 `async_initialize()`
2. **中期**: 添加向量计算失败的补偿机制
3. **长期**: 添加数据一致性检查工具

