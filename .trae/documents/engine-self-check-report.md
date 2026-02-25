# DuckKB 核心引擎自检报告

## 一、系统愿景对比

| 设计要求 | 实现状态 | 差距说明 |
|---------|---------|---------|
| **计算与存储解耦** | ❌ 未实现 | 当前使用持久化 `.db` 文件 (`duckdb.connect(str(self.db_path))`) |
| **真理源于文件** | ✅ 已实现 | JSONL 作为数据源，通过 `read_json_auto` 加载 |
| **确定性还原** | ⚠️ 部分实现 | `__id` 已持久化，但 ID 生成使用 `hash(identity)` 而非确定性算法 |

### 1.1 关键差距：内存模式

**设计要求：**
> DuckDB 仅作为高性能运行时计算层（Runtime），不产生持久化 .db 文件。

**当前实现：**
```python
# db.py:52
conn = duckdb.connect(str(self.db_path))  # 持久化到文件
```

**需要修改为：**
```python
conn = duckdb.connect()  # 内存模式
```

---

## 二、运行时数据布局对比

### 2.1 业务主表 (Node/Edge Tables)

| 设计要求 | 实现状态 |
|---------|---------|
| `__id BIGINT PRIMARY KEY` | ✅ 已实现 |
| `__created_at TIMESTAMP` | ✅ 已实现 |
| `__updated_at TIMESTAMP` | ✅ 已实现 |
| 业务字段 | ✅ 已实现 |
| `__date` (Generated Column) | ✅ 已实现（设计文档未提及，但合理） |

### 2.2 搜索索引表 (search_index)

| 设计字段 | 实现状态 | 说明 |
|---------|---------|------|
| `source_table` | ✅ 已实现 | |
| `source_id` | ✅ 已实现 | |
| `chunk_seq` | ✅ 已实现 | |
| `content` | ✅ 已实现 | |
| `fts_content` | ✅ 已实现 | |
| `vector` | ✅ 已实现 | |
| `content_hash` | ⚠️ 额外字段 | 设计文档未提及，但合理 |
| `created_at` | ⚠️ 额外字段 | 设计文档未提及，但合理 |
| `source_field` | ⚠️ 额外字段 | 设计文档未提及，用于区分同一记录的多个字段 |

### 2.3 搜索缓存表 (search_cache)

| 设计字段 | 实现状态 |
|---------|---------|
| `content_hash` | ✅ 已实现 |
| `fts_content` | ✅ 已实现 |
| `vector` | ✅ 已实现 |
| `last_used` | ⚠️ 额外字段 |
| `created_at` | ⚠️ 额外字段 |

---

## 三、核心工作流对比

### 3.1 原子同步协议 (Shadow Copy)

| 步骤 | 设计要求 | 实现状态 |
|-----|---------|---------|
| 1 | DB 事务写入 | ✅ 已实现 (`self.conn.begin()`, `commit()`) |
| 2 | 分词与切片 | ✅ 已实现 (`build_index`) |
| 3 | 影子导出 (JSONL) | ⚠️ 部分实现 |
| 4 | 影子导出 (Parquet) | ✅ 已实现 (`save_cache_to_parquet`) |
| 5 | 原子替换 (rename) | ❌ 未实现 |
| 6 | 确定性排序 (ORDER BY identity) | ❌ 未实现 |

**关键差距：确定性排序**

设计要求：
> 导出时 ORDER BY identity。这对于 Git 极为关键，它确保了数据更新时只有变动的行会产生 Diff。

当前实现：
```python
# storage.py:120
ORDER BY __id  # 按 __id 排序，而非 identity 字段
```

**需要修改为：**
```python
ORDER BY {identity_field}  # 按 identity 字段排序
```

### 3.2 启动构建协议 (Bootstrapping)

| 步骤 | 设计要求 | 实现状态 |
|-----|---------|---------|
| 1 | 全量重载 JSONL | ✅ 已实现 (`load_node`, `load_edge`) |
| 2 | 缓存唤醒 (Parquet) | ✅ 已实现 (`load_cache_from_parquet`) |
| 3 | 索引镜像还原 | ✅ 已实现 (`build_index`) |
| 4 | 缓存回填 | ✅ 已实现 (`_get_or_compute_fts`, `_get_or_compute_vector`) |

---

## 四、混合检索对比

| 设计要求 | 实现状态 |
|---------|---------|
| FTS 检索 | ✅ 已实现 |
| Vector 检索 | ✅ 已实现 |
| RRF 融合 | ✅ 已实现 |
| source_id 回捞业务表 | ✅ 已实现 (`get_source_record`) |
| 权重配置 (alpha) | ✅ 已实现 |

---

## 五、Git 持久化规范对比

### 5.1 目录结构

| 设计要求 | 实现状态 |
|---------|---------|
| `/data/nodes/{table_name}/{YYYYMMDD}/part_{NNN}.jsonl` | ⚠️ 部分匹配 |
| `/data/edges/{label_name}/{YYYYMMDD}/part_{NNN}.jsonl` | ⚠️ 部分匹配 |
| `/data/indices/search_cache.parquet` | ⚠️ 需要手动指定路径 |

**当前目录结构：**
```
/data/nodes/{table_name}/part_date={YYYYMMDD}/data_0.json
```

**设计要求目录结构：**
```
/data/nodes/{table_name}/{YYYYMMDD}/part_{NNN}.jsonl
```

**差距：**
- 分区格式不同：`part_date={YYYYMMDD}` vs `{YYYYMMDD}`
- 文件名不同：`data_0.json` vs `part_{NNN}.jsonl`

### 5.2 确定性排序

| 设计要求 | 实现状态 |
|---------|---------|
| 按 identity 排序 | ❌ 未实现（当前按 `__id` 排序） |

---

## 六、配置规范对比

| 设计要求 | 实现状态 |
|---------|---------|
| `global.chunk_size` | ⚠️ 通过参数传入，未从 config.yaml 读取 |
| `global.embedding_model` | ⚠️ 通过参数传入，未从 config.yaml 读取 |
| `global.tokenizer` | ⚠️ 通过参数传入，未从 config.yaml 读取 |
| `nodes.{name}.search.full_text` | ✅ 已实现 |
| `nodes.{name}.search.vectors` | ✅ 已实现 |

---

## 七、待修复清单

### P0 - 必须修复

| 问题 | 影响 | 修复方案 |
|------|------|---------|
| 内存模式 | 违反核心设计理念 | `duckdb.connect()` 无参数 |
| 确定性排序 | Git Diff 失效 | 导出时 `ORDER BY identity` |

### P1 - 应该修复

| 问题 | 影响 | 修复方案 |
|------|------|---------|
| 目录结构不匹配 | 与设计文档不一致 | 自定义分区格式 |
| 配置未从 YAML 读取 | 配置分散 | 从 config.yaml 读取全局配置 |

### P2 - 可选优化

| 问题 | 影响 | 修复方案 |
|------|------|---------|
| 原子替换 | 崩溃一致性 | 实现 Shadow Copy 协议 |

---

## 八、修复建议

### 8.1 内存模式

```python
# db.py
def _create_connection(self) -> duckdb.DuckDBPyConnection:
    """创建数据库连接（内存模式）。"""
    return duckdb.connect()  # 无参数 = 内存模式
```

### 8.2 确定性排序

```python
# storage.py
async def dump_table(
    self,
    table_name: str,
    output_dir: Path,
    identity_field: str,  # 新增参数
    partition_by_date: bool = True,
) -> int:
    sql = f"""
        COPY (
            SELECT *, strftime(__updated_at, '%Y%m%d') as part_date
            FROM {table_name}
            ORDER BY {identity_field}  # 按 identity 排序
        ) TO '{output_dir}' (FORMAT JSON, PARTITION_BY (part_date), OVERWRITE_OR_IGNORE)
    """
```

### 8.3 目录结构

需要研究 DuckDB 是否支持自定义分区目录格式，或通过后处理重命名。

### 8.4 配置读取

```python
# config.py
def _load_config(self) -> CoreConfig:
    with open(self.config_path) as f:
        data = yaml.safe_load(f)
    
    global_config = data.get("global", {})
    return CoreConfig(
        chunk_size=global_config.get("chunk_size", 800),
        embedding_model=global_config.get("embedding_model", "text-embedding-3-small"),
        tokenizer=global_config.get("tokenizer", "jieba"),
        ...
    )
```

---

## 九、总结

### 已完成 ✅

- Mixin 架构设计
- search_index 表（核心检索入口）
- search_cache 表（向量缓存）
- 文本切片 (Chunking)
- 中文分词 (jieba)
- 向量嵌入 (OpenAI API)
- RRF 混合检索
- Parquet 缓存导入/导出

### 核心差距 ❌

1. **内存模式** - 当前使用持久化 .db 文件
2. **确定性排序** - 当前按 `__id` 而非 `identity` 排序
3. **目录结构** - 分区格式与设计文档不一致
4. **配置读取** - 全局配置未从 config.yaml 读取

### 建议优先级

1. **P0**: 修复内存模式 + 确定性排序
2. **P1**: 统一目录结构 + 配置读取
3. **P2**: 实现原子替换协议
