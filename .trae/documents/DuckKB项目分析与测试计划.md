# DuckKB 项目分析与测试计划

## 一、项目概述

DuckKB 是一个基于 DuckDB 的知识库引擎，采用 Mixin 组合模式设计，主要功能包括：
- 知识图谱存储（节点和边）
- 混合检索（向量 + 全文）
- 知识导入导出
- MCP 服务接口

## 二、代码质量分析

### 2.1 测试覆盖率分析

| 模块 | 覆盖率 | 风险等级 | 说明 |
|------|--------|----------|------|
| `core/mixins/index.py` | 28% | 高 | 索引构建逻辑复杂，缺少测试 |
| `core/mixins/search.py` | 58% | 中 | 搜索核心功能，需要更多边界测试 |
| `core/mixins/graph.py` | 67% | 中 | 图遍历逻辑复杂，递归深度问题 |
| `core/mixins/import_.py` | 85% | 低 | 事务处理逻辑已覆盖 |
| `core/mixins/embedding.py` | 70% | 中 | 缓存逻辑需要并发测试 |

### 2.2 发现的潜在问题

#### 问题 1：IndexMixin.build_index 缺少错误处理

**位置**: `src/duckkb/core/mixins/index.py:109-144`

**问题描述**: `build_index` 方法在处理节点类型时，如果节点没有 search 配置，只是打印警告并返回 0，但没有抛出异常。这可能导致用户误以为索引构建成功。

```python
search_config = getattr(node_def, "search", None)
if not search_config:
    logger.warning(f"No search config for node type: {node_type}")
    return 0  # 应该考虑是否需要抛出异常或返回更明确的状态
```

**建议**: 考虑返回更详细的状态信息，或在文档中明确说明行为。

#### 问题 2：GraphMixin._get_context_recursive 深度限制不明确

**位置**: `src/duckkb/core/mixins/graph.py:457-524`

**问题描述**: 递归获取上下文时，虽然检查了 `depth <= 0`，但没有设置最大递归深度保护，可能导致栈溢出。

```python
async def _get_context_recursive(
    self,
    node_type: str,
    node_id: int,
    edge_types: list[str] | None,
    direction: str,
    depth: int,
    neighbor_limit: int,
    visited: set[int] | None,
) -> list[dict[str, Any]]:
    if depth <= 0:
        return []
    # ... 递归调用没有额外的深度保护
```

**建议**: 添加硬编码的最大深度限制（如 10 层）作为安全保护。

#### 问题 3：SearchMixin._execute_hybrid_search SQL 注入风险

**位置**: `src/duckkb/core/mixins/search.py:104-186`

**问题描述**: 混合搜索 SQL 中直接拼接了 `vector_dim` 和 `prefetch_limit`，虽然这些是内部计算的值，但应该使用参数化查询。

```python
sql = f"""
...
array_cosine_similarity(vector::DOUBLE[{vector_dim}], {vector_literal}) as score,
...
LIMIT {prefetch_limit}
"""
```

**建议**: 确保所有外部输入都经过验证，考虑使用参数化查询。

#### 问题 4：ImportMixin 导入锁可能导致死锁

**位置**: `src/duckkb/core/mixins/import_.py:34-35`

**问题描述**: 使用 `asyncio.Lock()` 作为导入锁，但在某些错误路径中可能没有正确释放。

```python
def __init__(self, *args, **kwargs) -> None:
    super().__init__(*args, **kwargs)
    self._import_lock = asyncio.Lock()
```

**当前状态**: 代码使用了 `async with` 上下文管理器，锁应该能正确释放。但需要测试异常情况。

#### 问题 5：StorageMixin.compute_deterministic_id 可能产生负数 ID

**位置**: `src/duckkb/core/mixins/storage.py:13-27`

**问题描述**: 使用模运算生成 ID，可能产生负数（虽然概率很低）。

```python
def compute_deterministic_id(identity_values: list) -> int:
    combined = "\x00".join(str(v) for v in identity_values)
    hash_hex = hashlib.sha256(combined.encode()).hexdigest()
    max_int64 = (1 << 63) - 1
    return int(hash_hex[:16], 16) % max_int64
```

**建议**: 确保返回值为正数，或使用 `abs()` 处理。

#### 问题 6：FTS 索引创建失败时的处理不完整

**位置**: `src/duckkb/core/mixins/index.py:70-82`

**问题描述**: 创建 FTS 索引时，先尝试删除旧索引，如果删除失败会忽略错误继续创建。这可能导致索引状态不一致。

```python
def _create_fts_index(self) -> None:
    try:
        self.execute_write(f"PRAGMA drop_fts_index('{SEARCH_INDEX_TABLE}')")
    except Exception:
        pass  # 忽略删除失败

    self.execute_write(f"PRAGMA create_fts_index('{SEARCH_INDEX_TABLE}', 'id', 'fts_content')")
```

**建议**: 记录删除失败的原因，或在创建失败时抛出更明确的异常。

#### 问题 7：ConfigMixin 配置加载缺少验证

**位置**: `src/duckkb/core/mixins/config.py:59-92`

**问题描述**: 加载配置时，如果 `data_dir` 路径不存在或不可写，不会立即报错，可能导致后续操作失败。

```python
if storage_config and "data_dir" in storage_config:
    data_dir = Path(storage_config["data_dir"])  # 没有验证路径是否存在或可写
```

**建议**: 在初始化时验证数据目录的可访问性。

### 2.3 并发安全问题

#### 问题 8：EmbeddingMixin 缓存更新竞态条件

**位置**: `src/duckkb/core/mixins/embedding.py:126-155`

**问题描述**: 批量查询缓存后，单独更新每个条目的 `last_used` 时间，可能导致多次写入操作。

```python
def _get_cached_embeddings_batch(self, hashes: list[str]) -> dict[str, list[float]]:
    # ...
    for h, _ in rows:
        self.execute_write(  # 多次单独写入
            f"UPDATE {SEARCH_CACHE_TABLE} SET last_used = ? WHERE content_hash = ?",
            [now, h],
        )
```

**建议**: 使用批量更新语句。

#### 问题 9：FairReadWriteLock 与异步代码的兼容性

**位置**: `src/duckkb/utils/rwlock.py`

**问题描述**: `FairReadWriteLock` 是同步锁，但在异步环境中使用 `asyncio.to_thread` 调用。这可能导致线程池耗尽。

**建议**: 考虑实现异步版本的读写锁。

### 2.4 边界条件问题

#### 问题 10：ChunkingMixin.chunk_text 最后一个块的处理

**位置**: `src/duckkb/core/mixins/chunking.py:36-68`

**问题描述**: 当最后一个块小于 `chunk_size // 2` 时，会合并到前一个块，但可能导致前一个块超过 `chunk_size`。

```python
if len(chunk) < self.chunk_size // 2 and chunks:
    chunks[-1] += chunk  # 可能导致前一个块超过 chunk_size
else:
    chunks.append(chunk)
```

**建议**: 添加长度检查或调整合并策略。

## 三、测试计划

### 3.1 单元测试补充

#### 3.1.1 IndexMixin 测试（优先级：高）

```python
# 测试用例设计
class TestIndexMixin:
    """索引构建测试"""

    async def test_build_index_empty_table(self, async_engine):
        """测试空表索引构建"""

    async def test_build_index_no_search_config(self, async_engine):
        """测试无搜索配置的节点类型"""

    async def test_build_index_with_fts_only(self, async_engine):
        """测试仅全文索引"""

    async def test_build_index_with_vector_only(self, async_engine):
        """测试仅向量索引"""

    async def test_build_index_batch_processing(self, async_engine):
        """测试批量处理"""

    async def test_rebuild_index_removes_old_entries(self, async_engine):
        """测试重建索引删除旧条目"""

    async def test_cache_persistence(self, async_engine):
        """测试缓存持久化"""

    async def test_fts_index_creation_failure(self, async_engine):
        """测试 FTS 索引创建失败处理"""
```

#### 3.1.2 SearchMixin 测试（优先级：高）

```python
class TestSearchMixin:
    """搜索功能测试"""

    async def test_search_with_empty_index(self, async_engine):
        """测试空索引搜索"""

    async def test_search_vector_dimension_mismatch(self, async_engine):
        """测试向量维度不匹配"""

    async def test_search_with_invalid_alpha(self, async_engine):
        """测试无效 alpha 参数"""

    async def test_fts_search_without_fts_index(self, async_engine):
        """测试无 FTS 索引时的全文搜索"""

    async def test_search_result_limit(self, async_engine):
        """测试搜索结果限制"""

    async def test_search_node_type_filter(self, async_engine):
        """测试节点类型过滤"""

    async def test_query_raw_sql_injection_attempt(self, async_engine):
        """测试 SQL 注入防护"""
```

#### 3.1.3 GraphMixin 测试（优先级：中）

```python
class TestGraphMixin:
    """图谱功能测试"""

    async def test_get_neighbors_empty_graph(self, async_engine):
        """测试空图邻居查询"""

    async def test_traverse_max_depth_limit(self, async_engine):
        """测试遍历深度限制"""

    async def test_find_paths_no_path_exists(self, async_engine):
        """测试不存在路径的情况"""

    async def test_extract_subgraph_cycle_detection(self, async_engine):
        """测试子图提取中的循环检测"""

    async def test_graph_search_with_empty_results(self, async_engine):
        """测试空结果的图谱搜索"""

    async def test_traverse_recursive_depth_protection(self, async_engine):
        """测试递归深度保护"""
```

### 3.2 集成测试

#### 3.2.1 并发测试

```python
class TestConcurrency:
    """并发测试"""

    async def test_concurrent_imports(self, async_engine, tmp_path):
        """测试并发导入"""

    async def test_concurrent_read_write(self, async_engine):
        """测试并发读写"""

    async def test_import_lock_timeout(self, async_engine):
        """测试导入锁超时"""

    async def test_embedding_cache_race_condition(self, async_engine):
        """测试嵌入缓存竞态条件"""
```

#### 3.2.2 错误恢复测试

```python
class TestErrorRecovery:
    """错误恢复测试"""

    async def test_import_rollback_on_error(self, async_engine, tmp_path):
        """测试导入错误回滚"""

    async def test_partial_import_recovery(self, async_engine, tmp_path):
        """测试部分导入恢复"""

    async def test_shadow_dir_cleanup(self, async_engine, tmp_path):
        """测试影子目录清理"""
```

### 3.3 性能测试

```python
class TestPerformance:
    """性能测试"""

    async def test_large_batch_import(self, async_engine, tmp_path):
        """测试大批量导入"""

    async def test_search_performance_with_large_index(self, async_engine):
        """测试大索引搜索性能"""

    async def test_graph_traverse_performance(self, async_engine):
        """测试图遍历性能"""
```

### 3.4 边界条件测试

```python
class TestEdgeCases:
    """边界条件测试"""

    def test_deterministic_id_collision(self):
        """测试 ID 碰撞"""

    def test_chunk_text_edge_cases(self, engine):
        """测试文本切片边界"""

    async def test_unicode_handling(self, async_engine, tmp_path):
        """测试 Unicode 处理"""

    async def test_special_characters_in_search(self, async_engine):
        """测试搜索中的特殊字符"""
```

## 四、执行计划

### 第一阶段：核心功能测试（预计 2 小时）

1. 补充 IndexMixin 测试用例
2. 补充 SearchMixin 测试用例
3. 运行测试并修复发现的问题

### 第二阶段：并发和错误恢复测试（预计 1.5 小时）

1. 编写并发测试用例
2. 编写错误恢复测试用例
3. 验证锁机制和事务处理

### 第三阶段：边界条件和性能测试（预计 1 小时）

1. 编写边界条件测试
2. 编写性能基准测试
3. 整理测试报告

## 五、预期产出

1. 测试覆盖率提升至 80% 以上
2. 发现并修复 3-5 个潜在 bug
3. 完善错误处理和边界条件处理
4. 输出详细的测试报告
