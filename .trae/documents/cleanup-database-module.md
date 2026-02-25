# 清理历史知识库实现计划

## 背景

项目中存在两套知识库实现：
- **历史实现**：`/src/duckkb/database/` - 基于持久化 DuckDB 文件
- **最新实现**：`/src/duckkb/core/` - 基于内存 DuckDB 模式

需要清理历史实现，保留最新实现。

## 依赖分析

### database 模块结构

```
database/
├── __init__.py          (空文件)
├── connection.py        - 数据库连接管理（持久化模式）
├── persister.py         - DB -> 文件持久化
├── schema.py            - Schema 管理
└── engine/
    ├── loader.py        - 文件 -> DB 同步
    ├── manager.py       - KnowledgeBaseManager
    ├── migration.py     - 迁移管理
    ├── backup.py        - 备份管理
    ├── cache.py         - 缓存管理
    ├── search.py        - 搜索功能
    └── ontology/
        ├── __init__.py
        ├── _models.py   - Ontology 模型定义 ⚠️ 被引用
        ├── _schema.py
        ├── _validator.py
        └── engine.py
```

### 关键依赖关系

| 引用方 | 被引用模块 | 说明 |
|--------|-----------|------|
| `core/mixins/ontology.py` | `database.engine.ontology` | 导入 NodeType, EdgeType, Ontology |
| `config.py` | `database.engine.ontology` | 导入 Ontology |
| `mcp/server.py` | 多个 database 模块 | 已标记废弃，依赖大量 database 组件 |
| `utils/embedding.py` | `database.connection` | 使用 get_db() |
| `tests/conftest.py` | `database.engine.manager` | 测试夹具 |

### core 模块已有替代

| database 模块 | core 替代 |
|--------------|----------|
| `connection.py` | `core/mixins/db.py` (内存模式) |
| `engine/search.py` | `core/mixins/search.py` |
| `persister.py` + `loader.py` | `core/mixins/storage.py` |
| `engine/ontology/engine.py` | `core/mixins/ontology.py` |

## 执行步骤

### 阶段一：迁移 Ontology 模型

Ontology 模型（NodeType, EdgeType, Ontology, VectorConfig）是核心数据结构，需要保留但迁移位置。

1. **创建 `core/models/ontology.py`**
   - 将 `database/engine/ontology/_models.py` 内容迁移至此
   - 将 `_validator.py` 的验证逻辑合并或保留引用

2. **更新导入路径**
   - `core/mixins/ontology.py`
   - `config.py`
   - `database/engine/ontology/__init__.py` (临时保留，重导出)

### 阶段二：处理 MCP Server

`mcp/server.py` 已标记废弃（见文件头部注释），有两个选择：

**方案 A**：删除废弃的 `mcp/server.py`
- 同时删除相关测试

**方案 B**：保留但更新依赖
- 需要大量重构以使用 core 模块

建议采用 **方案 A**，因为：
1. 文件已明确标记废弃
2. 有新的替代实现 `duckkb.mcp.DuckMCP`

### 阶段三：处理 utils/embedding.py

`utils/embedding.py` 依赖 `database/connection.py` 的 `get_db()`。

选项：
1. 迁移到 core 模块
2. 创建独立的连接管理

建议：将 embedding 功能整合到 `core/mixins/embedding.py`。

### 阶段四：删除 database 目录

确认无引用后，删除整个 `database/` 目录。

### 阶段五：清理测试

删除依赖 database 模块的测试文件：
- `tests/test_ontology.py` (更新导入)
- `tests/test_config.py` (更新导入)
- `tests/test_validator.py`
- `tests/test_sql_security.py`
- `tests/test_searcher.py`
- `tests/test_core_integration.py`
- `tests/test_cache.py`
- `tests/test_backup.py`
- `tests/test_schema.py`
- `tests/test_indexer.py`
- `tests/conftest.py` (更新)

## 文件变更清单

### 新建文件
- `src/duckkb/core/models/__init__.py`
- `src/duckkb/core/models/ontology.py`

### 修改文件
- `src/duckkb/core/mixins/ontology.py` - 更新导入
- `src/duckkb/config.py` - 更新导入
- `tests/conftest.py` - 更新导入

### 删除文件
- `src/duckkb/database/` (整个目录)
- `src/duckkb/mcp/server.py` (废弃文件)
- 部分测试文件

## 风险评估

1. **Ontology 模型兼容性**：需确保迁移后模型行为一致
2. **测试覆盖**：需更新或重写测试
3. **外部依赖**：检查是否有外部代码依赖 database 模块

## 验证步骤

1. 运行 `ruff check` 确保无导入错误
2. 运行测试确保功能正常
3. 手动验证核心功能

## 执行顺序

1. 创建 `core/models/ontology.py`，迁移模型
2. 更新 `core/mixins/ontology.py` 导入
3. 更新 `config.py` 导入
4. 删除 `mcp/server.py`
5. 删除 `database/` 目录
6. 清理测试文件
7. 运行验证
