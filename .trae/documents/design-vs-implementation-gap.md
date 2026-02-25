# DuckKB 核心引擎设计文档 vs 实现对比分析

## 一、设计文档核心要求

### 1.1 系统愿景

| 设计要求 | 实现状态 | 说明 |
|---------|---------|------|
| 计算与存储解耦 | ❌ 未实现 | 当前使用持久化 `.db` 文件 |
| 真理源于文件 | ✅ 部分实现 | JSONL 作为数据源，但未实现"全量重载" |
| 确定性还原 | ⚠️ 部分实现 | `__id` 已持久化，但 ID 生成逻辑不同 |

### 1.2 运行时数据布局

| 表类型 | 设计要求 | 实现状态 |
|-------|---------|---------|
| 业务主表 (Node/Edge) | `__id`, `__created_at`, `__updated_at`, 业务字段 | ⚠️ 缺少 `__created_at` |
| 搜索索引表 (search_index) | `source_table`, `source_id`, `chunk_seq`, `content`, `fts_content`, `vector` | ❌ 完全缺失 |
| 搜索缓存表 (search_cache) | `content_hash`, `fts_content`, `vector` | ❌ 完全缺失 |

---

## 二、详细差距分析

### 2.1 数据库模式

**设计要求：**
```sql
-- 业务主表
CREATE TABLE {table} (
    __id BIGINT PRIMARY KEY,
    __created_at TIMESTAMP,
    __updated_at TIMESTAMP,
    -- 业务字段
);

-- 搜索索引表
CREATE TABLE search_index (
    source_table VARCHAR,
    source_id BIGINT,
    chunk_seq INTEGER,
    content VARCHAR,
    fts_content VARCHAR,
    vector FLOAT[]
);

-- 搜索缓存表
CREATE TABLE search_cache (
    content_hash VARCHAR PRIMARY KEY,
    fts_content VARCHAR,
    vector FLOAT[]
);
```

**当前实现：**
```sql
-- 业务主表
CREATE TABLE {table} (
    __id BIGINT PRIMARY KEY,
    __updated_at TIMESTAMP,
    __date DATE GENERATED ALWAYS AS (CAST(__updated_at AS DATE)) STORED,
    -- 业务字段
);

-- 缺失: search_index 表
-- 缺失: search_cache 表
```

**差距：**
- ❌ 缺少 `__created_at` 字段
- ❌ 缺少 `search_index` 表（核心搜索入口）
- ❌ 缺少 `search_cache` 表（向量缓存）

---

### 2.2 文本切片 (Chunking)

**设计要求：**
- 全局配置 `chunk_size: 800`
- 长文本自动切片
- 每个切片独立向量化
- `chunk_seq` 记录切片序号

**当前实现：**
- ❌ 完全缺失

**需要实现：**
```python
class ChunkingMixin(BaseEngine):
    def chunk_text(self, text: str, chunk_size: int = 800) -> list[str]:
        """将长文本切分为多个片段。"""
        
    async def build_search_index(self, node_type: str) -> int:
        """为节点构建搜索索引（切片 + 分词 + 向量化）。"""
```

---

### 2.3 搜索索引构建

**设计要求：**
```
启动构建协议 (Bootstrapping):
1. 全量重载 JSONL 到 DuckDB 内存
2. 从 Parquet 加载 search_cache
3. 索引镜像还原：
   - 扫描业务表需要索引的字段
   - 进行 Chunking
   - 通过 content_hash 从缓存回填 fts_content 和 vector
```

**当前实现：**
- ❌ 完全缺失

**需要实现：**
```python
class IndexMixin(BaseEngine):
    async def build_index(self) -> None:
        """构建搜索索引。"""
        
    async def rebuild_index(self, node_type: str) -> None:
        """重建指定节点的索引。"""
        
    async def load_cache(self) -> None:
        """从 Parquet 加载搜索缓存。"""
        
    async def save_cache(self) -> None:
        """保存搜索缓存到 Parquet。"""
```

---

### 2.4 中文分词

**设计要求：**
- 全局配置 `tokenizer: jieba`
- `fts_content` 存储预分词结果
- 分词结果用空格分隔

**当前实现：**
- ❌ SearchMixin 直接使用 `fts_match()`，未预处理分词

**需要实现：**
```python
class TokenizerMixin(BaseEngine):
    def segment(self, text: str) -> str:
        """中文分词，返回空格分隔的字符串。"""
```

---

### 2.5 原子同步协议

**设计要求：**
```
Shadow Copy 协议:
1. DB 事务写入
2. 分词与切片
3. 影子导出（业务数据 JSONL + 缓存 Parquet）
4. 原子替换（rename）
5. 提交
```

**当前实现：**
- ⚠️ 有事务写入
- ⚠️ 有导出功能
- ❌ 缺少影子导出和原子替换

---

### 2.6 混合检索

**设计要求：**
- 两路并发：FTS + Vector
- RRF 融合排序
- 通过 `source_id` 回捞业务主表

**当前实现：**
- ✅ RRF 融合已实现
- ⚠️ 直接查询业务表，未使用 `search_index`
- ❌ 缺少 `source_id` 回捞逻辑

---

### 2.7 Git 持久化规范

**设计要求：**
```
/data
  /nodes/{table_name}/{YYYYMMDD}/part_{NNN}.jsonl
  /edges/{label_name}/{YYYYMMDD}/part_{NNN}.jsonl
  /indices/search_cache.parquet  <-- Git LFS
```

**当前实现：**
- ✅ 按日期分区导出
- ❌ 目录结构不完全匹配
- ❌ 缺少 `search_cache.parquet`

---

## 三、实现优先级

### P0 - 核心缺失（必须实现）

| 功能 | 说明 | 工作量 |
|------|------|--------|
| search_index 表 | 搜索索引表 | 高 |
| search_cache 表 | 向量缓存表 | 中 |
| Chunking | 文本切片 | 中 |
| 分词预处理 | 中文分词 | 低 |
| 索引构建 | build_index | 高 |

### P1 - 重要功能

| 功能 | 说明 | 工作量 |
|------|------|--------|
| __created_at | 创建时间字段 | 低 |
| Parquet 缓存 | Git LFS 托管 | 中 |
| 原子替换 | Shadow Copy | 中 |

### P2 - 优化功能

| 功能 | 说明 | 工作量 |
|------|------|--------|
| 内存模式 | 无 .db 文件 | 高 |
| 全量重载 | 启动构建协议 | 中 |

---

## 四、建议的 Mixin 扩展

### 4.1 IndexMixin（搜索索引）

```python
class IndexMixin(BaseEngine):
    """搜索索引管理 Mixin。"""
    
    async def build_index(self, node_type: str | None = None) -> int:
        """构建搜索索引。"""
        
    async def rebuild_index(self, node_type: str) -> int:
        """重建索引。"""
        
    def _create_search_index_table(self) -> None:
        """创建 search_index 表。"""
        
    def _create_search_cache_table(self) -> None:
        """创建 search_cache 表。"""
```

### 4.2 ChunkingMixin（文本切片）

```python
class ChunkingMixin(BaseEngine):
    """文本切片 Mixin。"""
    
    def chunk_text(self, text: str) -> list[str]:
        """切分文本。"""
        
    def get_chunk_size(self) -> int:
        """获取配置的切片大小。"""
```

### 4.3 TokenizerMixin（分词）

```python
class TokenizerMixin(BaseEngine):
    """分词 Mixin。"""
    
    def segment(self, text: str) -> str:
        """中文分词。"""
        
    def init_tokenizer(self) -> None:
        """初始化分词器。"""
```

---

## 五、总结

### 已实现 ✅

- Mixin 架构设计
- 配置管理 (ConfigMixin)
- 数据库连接 (DBMixin)
- 本体管理 (OntologyMixin)
- 数据加载/导出 (StorageMixin)
- RRF 混合检索框架 (SearchMixin)

### 核心缺失 ❌

1. **search_index 表** - 设计文档的核心搜索入口
2. **search_cache 表** - 向量缓存，Git LFS 托管
3. **文本切片 (Chunking)** - 长文本处理
4. **分词预处理** - 中文分词
5. **索引构建协议** - 启动时全量构建

### 架构差异

| 方面 | 设计文档 | 当前实现 |
|------|---------|---------|
| 搜索入口 | `search_index` 表 | 直接查业务表 |
| 向量存储 | 独立索引表 | 内嵌在业务表 |
| 缓存策略 | Parquet + Git LFS | 无 |
| 数据库模式 | 内存模式 | 持久化 .db |

**结论：** 当前实现完成了基础架构，但与设计文档的核心要求（search_index 表、Chunking、索引构建）存在较大差距。建议按 P0 优先级逐步补充。
