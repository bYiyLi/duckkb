# FTS Index 不可用时直接报错退出的优化计划

## 问题分析

当前代码在 FTS 索引不可用时有以下处理方式：

1. **`_execute_hybrid_search`** ([search.py:184-189](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/search.py#L184-L189))：
   - 当混合检索遇到 FTS 相关错误时，会 fallback 到纯向量搜索
   - 用户期望：直接报错退出

2. **`fts_search`** ([search.py:287-292](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/search.py#L287-L292))：
   - 当 FTS 搜索失败时抛出 DatabaseError，这是正确的行为

3. **`_try_create_fts_index`** ([index.py:91-107](file:///Users/yi/Code/duckkb/src/duckkb/core/mixins/index.py#L91-L107))：
   - 创建 FTS 索引失败时只是 warning，应该更明确地报告错误

## 修改方案

### 1. 新增 FTS 相关异常类

在 `exceptions.py` 中添加：
```python
class FTSError(DuckKBError):
    """FTS 扩展不可用异常。
    
    当 FTS 索引不存在或 FTS 扩展未安装时抛出。
    """
    pass
```

### 2. 修改 `_execute_hybrid_search` 方法

**文件**: `src/duckkb/core/mixins/search.py`

**修改前** (第 184-189 行):
```python
except Exception as e:
    if "match_bm25" in str(e).lower() or "fts" in str(e).lower():
        logger.warning("FTS index not available, falling back to vector search")
        return await self.vector_search(query, node_type=node_type, limit=limit)
    logger.error(f"Hybrid search failed: {e}")
    raise DatabaseError(f"Hybrid search failed: {e}") from e
```

**修改后**:
```python
except Exception as e:
    if "match_bm25" in str(e).lower() or "fts" in str(e).lower():
        raise FTSError("FTS index not available. Please ensure FTS extension is installed and index is created.") from e
    logger.error(f"Hybrid search failed: {e}")
    raise DatabaseError(f"Hybrid search failed: {e}") from e
```

### 3. 修改 `fts_search` 方法

**文件**: `src/duckkb/core/mixins/search.py`

**修改前** (第 287-292 行):
```python
except Exception as e:
    logger.error(f"FTS search failed: {e}")
    raise DatabaseError(f"FTS search failed: {e}") from e
```

**修改后**:
```python
except Exception as e:
    if "match_bm25" in str(e).lower() or "fts" in str(e).lower():
        raise FTSError("FTS index not available. Please ensure FTS extension is installed and index is created.") from e
    logger.error(f"FTS search failed: {e}")
    raise DatabaseError(f"FTS search failed: {e}") from e
```

### 4. 修改 `_try_create_fts_index` 方法

**文件**: `src/duckkb/core/mixins/index.py`

**修改前** (第 91-107 行):
```python
def _try_create_fts_index(self) -> None:
    try:
        result = self.execute_read(
            f"SELECT COUNT(*) FROM {SEARCH_INDEX_TABLE} WHERE fts_content IS NOT NULL"
        )
        count = result[0][0] if result else 0
        if count > 0:
            self._create_fts_index()
            logger.info(f"FTS index created for {count} documents")
        else:
            logger.debug("No fts_content in search index, skipping FTS index creation")
    except Exception as e:
        logger.warning(f"Failed to create FTS index: {e}")
```

**修改后**:
```python
def _try_create_fts_index(self) -> None:
    try:
        result = self.execute_read(
            f"SELECT COUNT(*) FROM {SEARCH_INDEX_TABLE} WHERE fts_content IS NOT NULL"
        )
        count = result[0][0] if result else 0
        if count > 0:
            self._create_fts_index()
            logger.info(f"FTS index created for {count} documents")
        else:
            logger.debug("No fts_content in search index, skipping FTS index creation")
    except Exception as e:
        raise FTSError(f"Failed to create FTS index: {e}") from e
```

### 5. 更新测试用例

**文件**: `tests/test_search.py` 和 `tests/test_real_functional.py`

将 `pytest.skip("FTS extension not available")` 改为捕获 `FTSError` 异常：
```python
from duckkb.exceptions import FTSError

try:
    results = await async_engine.fts_search("测试", limit=5)
except FTSError:
    pytest.skip("FTS extension not available")
```

## 影响范围

| 文件 | 修改内容 |
|------|----------|
| `src/duckkb/exceptions.py` | 新增 `FTSError` 异常类 |
| `src/duckkb/core/mixins/search.py` | `_execute_hybrid_search` 和 `fts_search` 方法 |
| `src/duckkb/core/mixins/index.py` | `_try_create_fts_index` 方法 |
| `tests/test_search.py` | 更新异常捕获 |
| `tests/test_real_functional.py` | 更新异常捕获 |

## 验证方式

1. 运行现有测试确保无回归
2. 手动测试 FTS 不可用时的错误抛出行为
