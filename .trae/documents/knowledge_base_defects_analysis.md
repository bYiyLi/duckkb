# 知识库实现缺陷分析计划

## 分析目标

分析 DuckKB 项目知识库实现的潜在缺陷，并制定修复方案。

***

## 已识别的缺陷

### 1. \[严重] SQL 注入风险 - search.py ✅ 已修复

**位置**: `src/duckkb/core/mixins/search.py`

**问题描述**:
在 `_execute_hybrid_search()`, `vector_search()`, `fts_search()` 等方法中，用户查询通过 f-string 直接拼接 SQL，仅做单引号转义，存在 SQL 注入风险。

**修复内容**:

* 将 `fts_match(fts_content, '{escaped_query}')` 改为参数化查询 `fts_match(fts_content, ?)`

* 在 `_execute_hybrid_search()` 和 `fts_search()` 中使用参数化查询

***

### 2. \[中等] 文本切片无重叠 - index.py/import\_.py ✅ 已修复

**位置**: `src/duckkb/core/mixins/index.py` 和 `import_.py`

**问题描述**:
`_chunk_text()` 方法使用简单的固定大小切片，没有重叠。这会导致边界处的重要信息被截断，降低检索召回率。

**修复内容**:

* 在 `IndexMixin._chunk_text()` 中优先使用 `ChunkingMixin.chunk_text()` 方法

* 在 `ImportMixin._chunk_text_sync()` 中实现滑动窗口切片逻辑

* 支持重叠切片以提高检索召回率

***

### 3. \[低] 向量计算失败静默处理 - index.py ✅ 已修复

**位置**: `src/duckkb/core/mixins/index.py`

**问题描述**:
向量计算失败时返回 None，搜索结果可能缺少向量，影响混合搜索质量。

**修复内容**:

* 在 `_get_or_compute_vector()` 中添加重试机制

* 默认最大重试次数为 3 次，重试间隔 1.0 秒

* 记录每次重试的警告日志

***

### 4. \[低] 向量维度类型推断风险 - search.py ✅ 已修复

**位置**: `src/duckkb/core/mixins/search.py`

**问题描述**:
搜索时从查询向量长度推断维度，如果实际向量维度不一致，可能导致类型转换错误。

**修复内容**:

* 在 `_get_query_vector()` 中添加向量维度校验

* 如果查询向量维度与配置的 `embedding_dim` 不匹配，记录错误并返回 None

***

### 5. \[低] FTS 搜索无索引优化 - 已评估

**位置**: `src/duckkb/core/mixins/index.py` 和 `search.py`

**评估结论**:

* 当前使用 DuckDB 的 `fts_match()` 直接在 VARCHAR 列上搜索

* 知识库场景数据量通常不会特别大，当前实现可接受

* 创建 FTS 索引会增加额外存储和维护成本

* 如数据量大可考虑后续优化

***

## 已排除的问题

### ~~节点删除时缓存未清理~~

**结论**: 不成立

**原因**:

* `search_cache` 使用 `content_hash`（文本 MD5）作为主键，是**内容级缓存**

* 不是记录级缓存，相同内容的 chunk 会复用缓存

* 删除节点不会导致缓存膨胀，因为缓存键与记录 ID 无关

* 有 `clean_cache()` 方法清理过期缓存

### ~~content 字段冗余~~

**结论**: 不成立

**原因**:

* 搜索结果需要返回 content 给用户查看匹配的文本内容

* 这是必要的返回数据，不是冗余

### ~~内存模式数据持久化风险~~

**结论**: 不成立

**原因**:

* CLI 和 MCP 只暴露 `import_knowledge_bundle` 作为数据导入入口

* 该方法有完整的原子同步流程：导入 → 索引 → 导出 JSONL

* `load_node/load_edge` 是内部方法，不对外暴露

***

## 修复完成汇总

| 优先级 | 缺陷          | 位置                   | 状态        |
| --- | ----------- | -------------------- | --------- |
| 严重  | SQL 注入风险    | search.py            | ✅ 已修复     |
| 中等  | 文本切片无重叠     | index.py/import\_.py | ✅ 已修复     |
| 低   | 向量计算失败静默处理  | index.py             | ✅ 已修复     |
| 低   | 向量维度类型推断风险  | search.py            | ✅ 已修复     |
| 低   | FTS 搜索无索引优化 | index.py/search.py   | 已评估，当前可接受 |

