# DuckKB 核心功能实现计划

## 概述

本计划旨在基于 `设计文档.md` 实现 DuckKB 的核心功能。系统是一个基于 DuckDB 的智能体知识引擎，具备混合检索、向量缓存和文件驱动的数据管理能力。

## 实施阶段

### 阶段 1: 环境与配置

* [ ] **依赖检查**: 确认安装 `duckdb`, `fastmcp`, `openai`, `jieba`, `typer`, `watchfiles`, `rich`, `orjson`, `pydantic-settings`。

* [ ] **配置增强**: 更新 `src/duckkb/config.py` 以完整支持 `KB_PATH` 等配置。

* [ ] **日志设置**: 在 `src/duckkb/logger.py` 中设置结构化日志。

### 阶段 2: 数据库层与 Schema

* [ ] **Schema 定义**: 定义 `_sys_search` 和 `_sys_cache` 表结构。

* [ ] **DB 初始化**: 在 `src/duckkb/db.py` 中实现数据库及表的初始化逻辑。

* [ ] **Schema 管理**: 实现从 KB 目录读取并应用 `schema.sql` 到数据库的逻辑。

### 阶段 3: 向量服务与缓存 (成本优先)

* [ ] **向量缓存表**: 确保 `_sys_cache` 表已创建。

* [ ] **Embedding 逻辑**: 实现 `src/duckkb/utils/embedding.py`:

  * 计算内容哈希 (MD5/SHA256)。

  * 查询 DuckDB 缓存。

  * 若未命中，调用 OpenAI API。

  * 存入缓存并返回向量。

### 阶段 4: 索引引擎 (文件驱动同步)

* [ ] **文本分词**: 在 `src/duckkb/utils/text.py` 中使用 `jieba` 实现中文分词。

* [ ] **同步逻辑**: 在 `src/duckkb/engine/indexer.py` 中实现 `sync_knowledge_base`:

  * 扫描 `data/*.jsonl` 文件。

  * 实现增量更新逻辑（检查文件修改时间）。

  * 处理记录：提取文本 -> 生成向量 -> 提取元数据 -> Upsert 到 `_sys_search`。

* [ ] **原子写入**: 确保文件操作采用“先写临时文件再重命名”模式。

### 阶段 5: 搜索引擎 (混合检索)

* [ ] **混合搜索**: 在 `src/duckkb/engine/searcher.py` 中实现 `smart_search`:

  * 生成查询向量。

  * 构建 SQL 查询以实现 BM25 + 向量相似度混合检索。

  * 执行查询并格式化结果。

* [ ] **安全 SQL 执行**: 在 `src/duckkb/engine/searcher.py` 中实现 `query_raw_sql`:

  * 强制只读连接。

  * 自动追加 `LIMIT`（如果缺失）。

  * 错误处理。

### 阶段 6: 数据导入与验证

* [ ] **验证逻辑**: 在 `src/duckkb/engine/indexer.py` 中实现 `validate_and_import`:

  * 验证 JSONL 格式。

  * 提供具体的错误反馈（行号、字段）。

  * 将有效文件从 `.build/temp` 移动到 `data/`。

### 阶段 7: MCP 服务集成

* [ ] **工具暴露**: 实现 `src/duckkb/mcp/server.py`:

  * 注册 `sync_knowledge_base`, `get_schema_info`, `smart_search`, `query_raw_sql`, `validate_and_import` 工具。

  * 将工具连接到引擎函数。

### 阶段 8: 测试与验证

* [ ] **单元测试**: 添加针对向量缓存、SQL 安全性和同步逻辑的测试。

* [ ] **集成测试**: 使用示例知识库验证完整流程。

