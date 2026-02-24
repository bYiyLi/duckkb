# DuckKB 功能补全实施计划

根据对现有代码库的分析与设计文档 ([设计文档.md](file:///c:/Users/baiyihuan/code/duckkb/设计文档.md)) 的对比，发现以下功能尚未实现或仅部分实现。本计划旨在补全这些缺失的能力。

## 1. 现状与差距分析

| 功能模块     | 设计要求                                            | 当前状态            | 差距                     |
| :------- | :---------------------------------------------- | :-------------- | :--------------------- |
| **混合搜索** | `(BM25 * 0.4 + Vector * 0.6) * priority_weight` | 仅向量搜索           | 缺失 BM25 文本检索与加权融合逻辑    |
| **垃圾回收** | 定期清理 `_sys_cache` (>30天未用)                      | 仅记录 `last_used` | 缺失清理逻辑 (`clean_cache`) |
| **查询限制** | 结果集 < 2MB; 自动 Limit                             | 已实现自动 Limit     | 缺失结果集大小 (2MB) 限制       |

## 2. 实施步骤

### Step 1: 实现混合搜索 (Hybrid Search)

**目标**: 在 `smart_search` 中引入关键词检索，并与向量检索结果进行加权融合。

* **文件**: `src/duckkb/engine/searcher.py`

* **方案**:

  1. 利用 DuckDB 的 `fts` (Full Text Search) 扩展或 `score()` 函数（如果可用）。
  2. 如果 FTS 不可用，使用 `LIKE` 进行简单的文本匹配作为降级方案，或者手动实现简化版 TF-IDF/BM25 SQL。
  3. **优先方案**: 尝试使用 DuckDB 的 `fts` 宏构建索引，并在查询时使用 `fts_main_xxxx.match_bm25`。
  4. **调整 SQL**:

     ```sql
     SELECT
         ...,
         (fts_score * 0.4 + vector_score * 0.6) * priority_weight AS final_score
     FROM ...
     ORDER BY final_score DESC
     ```

### Step 2: 实现自动垃圾回收 (Auto GC)

**目标**: 清理长期未使用的向量缓存，释放空间。

* **文件**: `src/duckkb/engine/indexer.py` (新增 `clean_cache` 方法)

* **逻辑**:

  1. 定义 `GC_THRESHOLD_DAYS = 30`。
  2. SQL: `DELETE FROM _sys_cache WHERE last_used < current_timestamp - INTERVAL '30 days'`.
  3. **触发时机**: 在每次 `sync_knowledge_base` 执行结束时自动触发。

### Step 3: 增强查询结果限制 (Result Size Limit)

**目标**: 防止大结果集阻塞 MCP 通道。

* **文件**: `src/duckkb/engine/searcher.py`

* **逻辑**:

  1. 在 `query_raw_sql` 获取结果后，计算结果集的字节大小。
  2. 如果 `sys.getsizeof(results) > 2 * 1024 * 1024` (2MB)，则截断结果或抛出友好的错误提示。
  3. 保留现有的 `LIMIT` 注入逻辑。

## 3. 验证计划

1. **混合搜索验证**:

   * 插入包含特定关键词的记录。

   * 执行搜索，确认文本匹配能提升排名。
2. **GC 验证**:

   * 手动修改 `_sys_cache` 中某条记录的 `last_used` 为 31 天前。

   * 运行 `sync`，确认该记录被删除。
3. **限流验证**:

   * 构造一个返回大量文本的 SQL 查询。

   * 确认工具返回错误或截断后的结果。

## 4. 任务列表

* [ ] (Step 1) 研究 DuckDB FTS 在当前环境的可用性，并实现混合搜索 SQL。

* [ ] (Step 2) 在 `indexer.py` 中实现 `clean_cache` 并集成到 `sync` 流程。

* [ ] (Step 3) 在 `searcher.py` 中添加结果集大小检查逻辑。

