# 重构索引管理代码结构 Spec

## Why
`_rebuild_index_from_cache()` 方法定义在 `import_.py` 中，但它在启动时被调用，这属于"索引管理"而不是"知识导入"。代码职责划分不清晰，导致难以维护和理解。

## What Changes
- 将 `_rebuild_index_from_cache()` 从 `import_.py` 移动到 `index.py`
- 将 `import_.py` 中索引相关的辅助方法移动到 `index.py`
- 更新 `engine.py` 中的调用

## Impact
- Affected code:
  - `src/duckkb/core/mixins/import_.py` - 移除索引重建方法
  - `src/duckkb/core/mixins/index.py` - 添加索引重建方法
  - `src/duckkb/core/engine.py` - 无需修改（通过 Mixin 继承调用）

## ADDED Requirements

### Requirement: 索引管理职责归一
索引相关的所有方法应集中在 `IndexMixin` 中，包括：
- 索引表创建
- 索引构建
- 索引重建
- 缓存管理
- FTS 索引管理

#### Scenario: 启动时重建索引
- **WHEN** 引擎启动时调用 `_rebuild_index_from_cache()`
- **THEN** 该方法应在 `IndexMixin` 中定义，而非 `ImportMixin`

### Requirement: 导入职责单一
`ImportMixin` 应只负责知识导入相关逻辑，包括：
- YAML 文件解析
- Schema 校验
- 节点/边数据导入
- 事务管理
- 影子导出

#### Scenario: 导入知识包
- **WHEN** 用户调用 `import_knowledge_bundle()`
- **THEN** 该方法应调用 `IndexMixin` 提供的索引构建方法，而非自己实现

## MODIFIED Requirements

### Requirement: IndexMixin 方法列表
`IndexMixin` 应包含以下方法：

| 方法 | 作用 |
|------|------|
| `create_index_tables` | 创建索引表和缓存表 |
| `build_index` | 构建搜索索引 |
| `rebuild_index` | 重建指定节点类型的索引 |
| `rebuild_index_from_cache` | **新增** 从缓存重建索引 |
| `load_cache_from_parquet` | 从 Parquet 加载缓存 |
| `save_cache_to_parquet` | 保存缓存到 Parquet |
| `_try_create_fts_index` | 创建 FTS 索引 |

### Requirement: ImportMixin 方法列表
`ImportMixin` 应移除以下方法：

| 方法 | 移动到 |
|------|--------|
| `_rebuild_index_from_cache` | IndexMixin |
| `_chunk_text_sync` | IndexMixin（重命名为 `_chunk_text`） |
| `_compute_hash_sync` | IndexMixin（重命名为 `_compute_hash`） |

## REMOVED Requirements

### Requirement: ImportMixin 中的索引重建
**Reason**: 职责划分不清晰，索引管理应集中在 IndexMixin
**Migration**: 将方法移动到 IndexMixin，通过 Mixin 继承保持调用兼容
