# 方案分析：搜索索引表优化

## 用户提议

1. 给 `_sys_search_index` 表添加一个自增 ID 列
2. 使用 `fts_content`（分词后的内容）建立全文索引，而不是 `content`

***

## 问题一：为什么应该用 `fts_content` 建立全文索引？

### content vs fts\_content 的区别

```
原始文本 (content):
"人工智能在医疗领域的应用研究"

分词后 (fts_content):
"人工智能 在 医疗 领域 的 应用 研究"
```

### DuckDB FTS 的分词机制

DuckDB FTS 默认按**空格**分词：

```
用 content 建索引：
- 整句 "人工智能在医疗领域的应用研究" 被当作一个词
- 搜索 "人工智能" → 匹配失败！（不是完整匹配）
- 搜索 "人工智能在医疗领域的应用研究" → 匹配成功

用 fts_content 建索引：
- 分成多个词："人工智能", "在", "医疗", "领域", ...
- 搜索 "人工智能" → 匹配成功！
- 搜索 "医疗" → 匹配成功！
```

### 结论

**必须用** **`fts_content`** **建立全文索引**，否则中文搜索基本不可用。

***

## 问题二：为什么需要添加 ID 列？

***

## 两种方案对比

### 方案 A：当前设计（使用视图/表）

```sql
-- 主表（复合主键）
CREATE TABLE _sys_search_index (
    source_table VARCHAR NOT NULL,
    source_id BIGINT NOT NULL,
    source_field VARCHAR NOT NULL,
    chunk_seq INTEGER NOT NULL,
    content VARCHAR,
    ...
    PRIMARY KEY (source_table, source_id, source_field, chunk_seq)
)

-- FTS 表（合成单一 ID）
CREATE TABLE _sys_search_index_fts AS
SELECT 
    source_table || '_' || source_id || '_' || source_field || '_' || chunk_seq as doc_id,
    content
FROM _sys_search_index
```

### 方案 B：添加自增 ID 列

```sql
-- 主表（添加 ID 列）
CREATE TABLE _sys_search_index (
    id BIGINT PRIMARY KEY,  -- 新增：自增 ID
    source_table VARCHAR NOT NULL,
    source_id BIGINT NOT NULL,
    source_field VARCHAR NOT NULL,
    chunk_seq INTEGER NOT NULL,
    content VARCHAR,
    ...
    UNIQUE (source_table, source_id, source_field, chunk_seq)  -- 改为 UNIQUE 约束
)

-- 直接在主表创建 FTS 索引
PRAGMA create_fts_index('_sys_search_index', 'id', 'content')
```

***

## 详细对比分析

| 维度           | 方案 A（当前）                 | 方案 B（添加 ID）      |
| ------------ | ------------------------ | ---------------- |
| **表结构**      | 复合主键                     | 单列主键 + UNIQUE 约束 |
| **FTS 索引**   | 需要额外表/视图                 | 直接在主表上           |
| **存储空间**     | 需要额外存储 doc\_id 和 content | 无额外存储            |
| **数据同步**     | 需要重建 FTS 表               | 自动同步             |
| **JOIN 复杂度** | 需要字符串拼接匹配                | 直接用 ID 匹配        |
| **查询性能**     | 略慢（字符串拼接）                | 更快（整数匹配）         |

***

## 方案 B 的代码修改范围

### 1. 表结构修改

**文件**: `src/duckkb/core/mixins/index.py`

```python
# 修改 _create_search_index_table()
def _create_search_index_table(self) -> None:
    self.execute_write(f"""
        CREATE TABLE IF NOT EXISTS {SEARCH_INDEX_TABLE} (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            source_table VARCHAR NOT NULL,
            source_id BIGINT NOT NULL,
            source_field VARCHAR NOT NULL,
            chunk_seq INTEGER NOT NULL DEFAULT 0,
            content VARCHAR,
            fts_content VARCHAR,
            vector FLOAT[],
            content_hash VARCHAR,
            created_at TIMESTAMP,
            UNIQUE (source_table, source_id, source_field, chunk_seq)
        )
    """)
```

### 2. FTS 索引创建

**文件**: `src/duckkb/core/mixins/index.py`

```python
# 修改 _create_fts_index()
def _create_fts_index(self) -> None:
    """创建 FTS 索引，使用分词后的内容。"""
    try:
        self.execute_write(f"PRAGMA drop_fts_index('{SEARCH_INDEX_TABLE}')")
    except Exception:
        pass
    
    # 注意：使用 fts_content（分词后的内容）而不是 content
    # 这样中文搜索才能正常工作
    self.execute_write(
        f"PRAGMA create_fts_index('{SEARCH_INDEX_TABLE}', 'id', 'fts_content')"
    )
    logger.info("FTS index created successfully")
```

**重要**：必须使用 `fts_content` 而不是 `content`，原因：

* DuckDB FTS 按空格分词

* 中文没有空格，需要先分词

* `fts_content` 存储的是分词后的内容（空格分隔）

### 3. 插入逻辑修改

**文件**: `src/duckkb/core/mixins/index.py`

```python
# 修改 _insert_index_entries()
# 不再需要手动生成 doc_id，ID 自动生成
```

**文件**: `src/duckkb/core/mixins/import_.py`

```python
# 修改增量索引构建逻辑
# 移除 doc_id 相关代码
```

### 4. 搜索查询修改

**文件**: `src/duckkb/core/mixins/search.py`

```python
# fts_search CTE 修改：
fts_search AS (
    SELECT 
        id,
        source_table,
        source_id,
        source_field,
        chunk_seq,
        fts_main__sys_search_index.match_bm25(id, ?) as score,
        rank() OVER (ORDER BY fts_main__sys_search_index.match_bm25(id, ?) DESC) as rnk
    FROM _sys_search_index
    WHERE fts_main__sys_search_index.match_bm25(id, ?) IS NOT NULL
      AND fts_content IS NOT NULL  -- 只搜索有分词内容的记录
    {table_filter}
    ORDER BY score DESC
    LIMIT {prefetch_limit}
)

# RRF JOIN 简化为：
FULL OUTER JOIN fts_search f 
  ON v.id = f.id
```

**注意**：查询时需要确保 `fts_content IS NOT NULL`，因为只有配置了 `full_text` 的字段才会有分词内容。

### 5. 常量清理

**文件**: `src/duckkb/core/mixins/index.py`

```python
# 移除
# FTS_INDEX_VIEW = "_sys_search_index_fts"
```

***

## 迁移影响

### 数据迁移

如果已有数据库，需要迁移脚本：

```sql
-- 1. 创建新表
CREATE TABLE _sys_search_index_new (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    source_table VARCHAR NOT NULL,
    ...
    UNIQUE (source_table, source_id, source_field, chunk_seq)
);

-- 2. 迁移数据
INSERT INTO _sys_search_index_new 
SELECT * FROM _sys_search_index;

-- 3. 替换表
DROP TABLE _sys_search_index;
ALTER TABLE _sys_search_index_new RENAME TO _sys_search_index;

-- 4. 删除旧的 FTS 表
DROP TABLE IF EXISTS _sys_search_index_fts;
```

***

## 建议

**推荐采用方案 B**，理由：

1. **更简洁**：减少一个表/视图，降低系统复杂度
2. **性能更好**：整数 ID 匹配比字符串拼接快
3. **维护更简单**：不需要同步两个表
4. **符合惯例**：大多数搜索系统都用单一 ID

**但需要注意**：

* 这是一个**破坏性变更**，需要数据迁移

* 需要修改多个文件，测试覆盖要充分

* 建议在版本升级时一起发布

***

## 实施步骤

1. 修改 `_create_search_index_table()` 添加 ID 列
2. 修改 `_create_fts_index()` 使用 `fts_content` 建立索引
3. 修改 `_insert_index_entries()` 移除 doc\_id 相关逻辑
4. 修改 `search.py` 中的 FTS 查询，使用 ID 匹配
5. 清理 `FTS_INDEX_VIEW` 常量
6. 修改 `import_.py` 中的增量索引构建逻辑
7. 编写数据迁移脚本（如有现有数据）
8. 更新测试用例

