# 新旧核心引擎特性对比分析

## 概述

本文档分析旧核心引擎 (`src/duckkb/database/engine/`) 中存在但新引擎 (`src/duckkb/core/`) 尚未实现的特性。

---

## 一、数据模型差异

| 方面 | 旧引擎 | 新引擎 |
|------|--------|--------|
| 存储模型 | 统一 `_sys_search` 表 | 独立 Node/Edge 表 |
| 表结构 | `ref_id, source_table, source_field, segmented_text, embedding, metadata, priority_weight` | `__id, __updated_at, __date, ...业务字段` |
| 向量存储 | 每个字段单独存储向量 | 向量字段内嵌在表中 |

---

## 二、缺失特性清单

### 2.1 文档管理 (KnowledgeBaseManager)

**旧引擎方法：**
```python
# manager.py
async def add_documents(table_name, documents) -> dict
async def delete_documents(table_name, doc_ids) -> dict
```

**功能描述：**
- 添加/更新文档，支持 Upsert 语义
- 自动生成嵌入向量
- 事务性写入
- 异步保存（带防抖）

**新引擎状态：** ❌ 缺失

---

### 2.2 增量同步 (DataLoader)

**旧引擎方法：**
```python
# loader.py
async def sync_files_to_db() -> None
def _compute_diff(file_records, db_state, fields_to_embed) -> tuple
```

**功能描述：**
- 基于文件 mtime 的增量同步
- 同步状态持久化 (`sync_state.json`)
- Diff 计算（仅更新变更记录）
- FTS 索引自动创建
- 缓存清理集成

**新引擎状态：** ⚠️ 部分实现
- ✅ `load_table()` 支持批量加载
- ❌ 缺少增量同步逻辑
- ❌ 缺少 mtime 检查
- ❌ 缺少同步状态持久化

---

### 2.3 异步保存与防抖 (Debounce)

**旧引擎实现：**
```python
# manager.py
def _schedule_save(table_name) -> None
async def _delayed_save(table_name, delay=1.0) -> None
```

**功能描述：**
- 短时间内多次变更合并为一次保存
- 延迟 1 秒执行
- 任务取消和清理

**新引擎状态：** ❌ 缺失

---

### 2.4 备份与恢复 (BackupManager)

**旧引擎方法：**
```python
# backup.py
def create_backup(prefix="") -> Path | None
def restore_backup(backup_dir) -> bool
def list_backups() -> list[dict]
def delete_backup(backup_name) -> bool
def get_backup_info(backup_name) -> dict | None
```

**功能描述：**
- 完整备份（数据库 + 数据文件 + 配置）
- 自动清理旧备份（保留最新 5 个）
- 备份信息查询

**新引擎状态：** ❌ 缺失

---

### 2.5 迁移管理 (MigrationManager)

**旧引擎方法：**
```python
# migration.py
def parse_ontology_yaml(ontology_yaml) -> Ontology
def analyze_changes(new_ontology) -> dict
def migrate(ontology_yaml, force=False) -> MigrationResult
```

**功能描述：**
- Ontology 变更分析
- 自动备份
- 事务性迁移
- 失败自动回滚

**新引擎状态：** ❌ 缺失

---

### 2.6 嵌入向量管理 (embedding.py)

**旧引擎方法：**
```python
# utils/embedding.py
async def get_embeddings(texts) -> list[list[float]]
async def get_embedding(text) -> list[float]
```

**功能描述：**
- OpenAI API 集成
- 嵌入向量缓存 (`_sys_cache` 表)
- 批量处理优化
- 缓存命中统计

**新引擎状态：** ❌ 缺失

---

### 2.7 缓存管理 (cache.py)

**旧引擎方法：**
```python
# cache.py
async def clean_cache() -> None
```

**功能描述：**
- 清理过期缓存（30 天未使用）
- 防止缓存表无限增长

**新引擎状态：** ❌ 缺失

---

### 2.8 搜索功能增强

**旧引擎特性：**
```python
# search.py
async def smart_search(query, limit, table_filter, alpha) -> list[dict]
async def query_raw_sql(sql) -> list[dict]
```

**功能描述：**
| 特性 | 描述 |
|------|------|
| `table_filter` | 表过滤器，限制搜索范围 |
| `alpha` | 向量/全文权重配置 (0.0-1.0) |
| `query_raw_sql` | 安全执行原始 SQL |
| 降级策略 | 混合搜索失败时回退到向量搜索 |
| 结果限制 | 2MB 结果大小限制 |

**新引擎状态：** ⚠️ 部分实现
- ✅ RRF 混合检索
- ✅ 纯向量检索
- ✅ 纯全文检索
- ❌ 缺少表过滤器
- ❌ 缺少权重配置
- ❌ 缺少安全 SQL 查询
- ❌ 缺少降级策略

---

### 2.9 文本处理

**旧引擎功能：**
```python
# utils/text.py
def segment_text(text) -> str  # jieba 分词
def compute_text_hash(text) -> str  # 文本哈希
```

**功能描述：**
- 中文分词（jieba）
- 文本内容哈希（用于缓存键）

**新引擎状态：** ❌ 缺失

---

### 2.10 原子文件写入

**旧引擎实现：**
```python
# utils/file_ops.py
async def atomic_write_file(path, content) -> None
```

**功能描述：**
- 先写临时文件再重命名
- 保证写入原子性

**新引擎状态：** ⚠️ 未验证
- `dump_table()` 使用 DuckDB 的 `COPY` 命令
- 需要验证是否保证原子性

---

## 三、优先级建议

### 高优先级（核心功能）

| 特性 | 理由 |
|------|------|
| 嵌入向量管理 | 搜索功能依赖 |
| 文档管理 (add/delete) | 基础 CRUD 操作 |
| 增量同步 | 性能优化关键 |

### 中优先级（运维功能）

| 特性 | 理由 |
|------|------|
| 备份与恢复 | 数据安全 |
| 迁移管理 | Schema 演进 |
| 缓存管理 | 资源管理 |

### 低优先级（增强功能）

| 特性 | 理由 |
|------|------|
| 异步保存防抖 | 性能优化 |
| 安全 SQL 查询 | 调试工具 |
| 搜索权重配置 | 可选功能 |

---

## 四、实现建议

### 4.1 EmbeddingMixin

建议新增 Mixin 处理嵌入向量：

```python
class EmbeddingMixin(BaseEngine):
    async def embed(self, texts: list[str]) -> list[list[float]]
    async def embed_node(self, node_type: str, text_field: str) -> int
    async def clean_cache(self) -> None
```

### 4.2 DocumentMixin

建议新增 Mixin 处理文档操作：

```python
class DocumentMixin(BaseEngine):
    async def add_documents(self, node_type: str, documents: list[dict]) -> dict
    async def delete_documents(self, node_type: str, doc_ids: list[str]) -> dict
```

### 4.3 BackupMixin

建议新增 Mixin 处理备份：

```python
class BackupMixin(BaseEngine):
    def create_backup(self, prefix: str = "") -> Path | None
    def restore_backup(self, backup_dir: Path) -> bool
    def list_backups(self) -> list[dict]
```

### 4.4 MigrationMixin

建议新增 Mixin 处理迁移：

```python
class MigrationMixin(BaseEngine):
    def analyze_changes(self, new_ontology: Ontology) -> dict
    def migrate(self, ontology_yaml: str, force: bool = False) -> MigrationResult
```

---

## 五、架构兼容性

### 5.1 数据模型冲突

**问题：** 旧引擎使用统一 `_sys_search` 表，新引擎使用独立 Node/Edge 表。

**解决方案：**
1. 保持新引擎的独立表设计
2. 在 EmbeddingMixin 中实现向量字段管理
3. 搜索时直接查询 Node 表的向量字段

### 5.2 向量存储策略

**旧引擎：** 每个文本字段单独存储向量
**新引擎：** 向量字段内嵌在表中

**建议：** 新引擎设计更合理，保持现有设计。

---

## 六、总结

新引擎已完成核心架构重构，但缺少以下关键功能：

1. **嵌入向量生成** - 搜索功能依赖
2. **文档 CRUD** - 基础操作
3. **增量同步** - 性能优化
4. **备份恢复** - 数据安全
5. **迁移管理** - Schema 演进

建议按优先级逐步补充这些功能，每个功能作为独立的 Mixin 实现，保持架构的一致性。
