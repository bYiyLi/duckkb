# DuckKB 知识库结构与运行机制分析

## 1. 项目概览

DuckKB 是一个基于 DuckDB 的本地知识库引擎，专为 Agent 设计，采用 **Model Context Protocol (MCP)** 架构。其核心理念是"文件驱动"（File-Driven），即以 `.jsonl` 文件作为数据的单一事实来源（Source of Truth），DuckDB 仅作为高性能运行时索引。

## 2. 目录结构分析

项目的核心代码位于 `src/duckkb/` 目录下，主要结构如下：

*   **`src/duckkb/`**: 核心源码目录
    *   **`main.py`**: CLI 命令行入口，负责启动应用和 MCP 服务。
    *   **`config.py`**: 配置管理模块，定义了 `GlobalConfig`（API Key 等）和 `KBConfig`（知识库特定配置）。
    *   **`mcp/`**: MCP 协议实现层
        *   `server.py`: 定义了 MCP 服务器及其暴露的工具（如 `smart_search`, `sync_knowledge_base`）。
    *   **`engine/`**: 核心业务逻辑引擎
        *   `sync.py`: 负责将 `.jsonl` 文件同步到 DuckDB，处理增量更新和向量化。
        *   `searcher.py`: 实现混合检索逻辑（Vector + BM25）。
        *   `importer.py`, `deleter.py`: 数据导入与删除逻辑。
        *   `cache.py`: 向量缓存管理，减少 API 调用成本。
    *   **`ontology/`**: 本体定义模块，负责解析 `config.yaml` 中的 Schema 定义。
    *   **`utils/`**: 通用工具（文本分词、文件操作、Embedding 调用等）。

## 3. 核心组件

### 3.1 CLI 与入口点
*   **入口文件**: `src/duckkb/main.py`
*   **功能**: 使用 `typer` 构建命令行接口。
*   **主要命令**:
    *   `duckkb serve`: 启动 MCP 服务器，供 Claude 或其他 Agent 客户端连接。
    *   `duckkb --kb-path <PATH>`: 指定知识库路径（默认为 `./knowledge-bases/default`）。

### 3.2 配置管理
*   **配置文件**: `knowledge-bases/{kb_id}/config.yaml`
*   **内容**: 定义实体（Nodes）、关系（Edges）和向量字段等 Schema 信息。

### 3.3 MCP Server
*   **实现**: `src/duckkb/mcp/server.py`
*   **暴露工具**:
    *   `sync_knowledge_base`: 触发文件到数据库的同步。
    *   `smart_search`: 执行智能混合搜索。
    *   `query_raw_sql`: 执行只读 SQL 查询。
    *   `validate_and_import`: 验证并导入数据。

### 3.4 知识引擎
*   **同步引擎**: `engine/sync.py` 负责将文件变更同步到数据库。
*   **搜索引擎**: `engine/searcher.py` 实现向量与全文的混合检索。

## 4. 数据流分析 (Data Flow)

数据流遵循 **File -> DB -> Search** 的单向流动原则：

1.  **定义 (Ontology)**: 用户在 `config.yaml` 中定义数据结构。
2.  **输入 (Ingestion)**: 数据以 `.jsonl` 格式存储在 `knowledge-bases/{kb_id}/data/` 目录下。
3.  **同步 (Synchronization)**:
    *   系统读取 `.jsonl` 文件，计算内容哈希。
    *   仅对变更记录调用 Embedding API 生成向量。
    *   数据写入 DuckDB 的 `_sys_search` 表（包含分词文本、向量、元数据）。
4.  **检索 (Retrieval)**:
    *   混合搜索：同时执行 **向量搜索 (Cosine Similarity)** 和 **全文搜索 (BM25)**。
    *   加权融合：`Final_Score = (BM25 * (1-alpha) + Vector * alpha) * priority_weight`。

## 5. 运行机制

1.  **启动**: 运行 `duckkb serve`，系统初始化 `AppContext`，加载配置。
2.  **初始化**: 通过 `lifespan` 事件自动执行 `init_schema` 和 `sync_knowledge_base`，确保数据库处于最新状态。
3.  **运行时**: MCP Server 监听请求，处理搜索、导入等操作。
4.  **持久化**: 所有有效数据始终以 `.jsonl` 文件形式存在于磁盘，DuckDB (`.build/knowledge.db`) 仅作为运行时的高性能索引缓存，可随时重建。

## 6. 总结

DuckKB 通过将文件系统作为数据源，结合 DuckDB 的高性能分析能力，构建了一个既适合版本控制又具备强大检索能力的本地知识库系统。其模块化设计使得扩展新的数据源或检索引擎变得容易。
