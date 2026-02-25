# DuckKB 项目分析报告

## 1. 项目概述

DuckKB 是一个基于 **DuckDB** 的 **MCP (Model Context Protocol) 知识库服务**，专为 AI Agent 提供持久化记忆层。项目采用 Python 3.12+ 开发，使用 uv 管理依赖，通过 MCP 协议为 AI 助手提供知识检索和管理的工具集。

### 核心设计哲学

- **一库一服 (Dedicated Mode)**：每个实例独占一个目录，通过环境变量 `KB_PATH` 锁定
- **文件驱动 (File-Driven)**：所有知识变更必须通过修改 `.jsonl` 事实文件完成
- **成本优先 (Cost Efficiency)**：内置向量缓存，避免对相同文本重复调用大模型 API

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         DuckKB MCP Server                        │
│                      (FastMCP + Typer CLI)                      │
└─────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  MCP Tools    │      │  Knowledge Base │      │   Backup        │
│  (Tools API) │      │   Manager       │      │   Manager       │
└───────────────┘      └─────────────────┘      └─────────────────┘
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Engine Layer                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ DataLoader  │  │ DataPersister│  │ SearchEngine│              │
│  │ (File→DB)   │  │ (DB→File)    │  │ (Hybrid)     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Ontology   │  │ Migration   │  │ Cache       │              │
│  │ Engine     │  │ Manager     │  │ Manager     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Data & Storage Layer                         │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │  DuckDB         │    │  File System    │                    │
│  │  (vss extension)│    │  (.jsonl files) │                    │
│  └─────────────────┘    └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                            │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │  OpenAI API     │    │  Git Repository │                    │
│  │  (Embedding)    │    │  (Audit Trail)  │                    │
│  └─────────────────┘    └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块说明

| 模块 | 路径 | 职责 |
|------|------|------|
| **main.py** | `src/duckkb/main.py` | CLI 入口，支持 `serve` 和 `version` 命令 |
| **MCP Server** | `src/duckkb/mcp/server.py` | MCP 协议实现，提供 9 个工具函数 |
| **Config** | `src/duckkb/config.py` | 配置管理，应用上下文单例 |
| **KnowledgeBaseManager** | `src/duckkb/database/engine/manager.py` | 知识库统一管理入口，协调加载/持久化 |
| **DataLoader** | `src/duckkb/database/engine/loader.py` | 文件 → 数据库同步，增量更新 |
| **DataPersister** | `src/duckkb/database/persister.py` | 数据库 → 文件持久化 |
| **SearchEngine** | `src/duckkb/database/engine/search.py` | 混合搜索（向量 + BM25） |
| **OntologyEngine** | `src/duckkb/database/engine/ontology/engine.py` | 本体定义解析与 DDL 生成 |
| **Embedding Utils** | `src/duckkb/utils/embedding.py` | 向量嵌入生成与缓存管理 |
| **BackupManager** | `src/duckkb/database/engine/backup.py` | 备份与恢复 |

---

## 3. 实现功能

### 3.1 MCP 工具集

| 工具名称 | 功能描述 |
|----------|----------|
| `check_health` | 健康检查，返回知识库状态信息 |
| `sync_knowledge_base` | 同步 JSONL 文件到数据库，支持增量更新 |
| `get_schema_info` | 获取数据库 Schema 和 ER 图 |
| `smart_search` | 混合检索（向量 + BM25），可配置权重 |
| `query_raw_sql` | 安全只读 SQL 查询 |
| `validate_and_import` | 验证并导入数据（upsert 语义） |
| `delete_records` | 删除指定记录 |
| `list_backups` | 列出所有备份 |
| `restore_backup` | 从备份恢复 |
| `create_backup` | 创建备份 |

### 3.2 核心功能特性

#### 1. 混合检索 (Hybrid Search)
- 结合 **向量搜索**（语义相似度）和 **BM25 全文搜索**
- 可配置权重 `alpha` 参数（0.0-1.0）
- 结果包含完整 `metadata`，便于 Agent 直接使用

#### 2. 向量缓存 (Embedding Cache)
- 基于内容哈希的持久化缓存
- 避免重复调用 Embedding API，**降低 80%+ 成本**
- 自动清理超过 30 天的过期缓存

#### 3. Git 可审计
- 所有知识变更存储在 `.jsonl` 文件中
- 可通过 Git 版本追踪变更历史
- 原子写入机制防止数据损坏

#### 4. 安全查询
- SQL 黑名单检测（禁止 INSERT/UPDATE/DELETE 等）
- 自动追加 LIMIT 限制
- 结果集大小限制（2MB）
- 只读连接模式

#### 5. 本体定义 (Ontology)
- 支持通过 `config.yaml` 定义数据模型
- JSON Schema 类型验证
- 向量字段自动识别
- DDL 自动生成

#### 6. 增量同步
- 基于文件 mtime 的增量检测
- 基于内容哈希的变更检测
- 避免不必要的重复处理

#### 7. 备份与恢复
- 完整备份（数据库 + 数据文件 + 配置）
- 自动清理旧备份（保留最新 5 个）

---

## 4. 数据流设计

### 4.1 启动流程 (File → DB)

```
JSONL Files ──▶ DataLoader ──▶ Diff Compute ──▶ DuckDB
                 │                  │
                 │                  ▼
                 │            Generate Embeddings
                 │                  │
                 │                  ▼
                 │            Update Cache
                 └──────────────────┘
```

### 4.2 写入流程 (Upsert)

```
MCP Tool ──▶ KnowledgeBaseManager ──▶ DB Transaction ──▶ Async Save
                   │                        │
                   │                        ▼
                   │                  JSONL Files
                   │                        │
                   └────────────────◀────────┘
```

### 4.3 搜索流程

```
User Query ──▶ Generate Embedding ──▶ Hybrid Search (CTE)
                   │                         │
                   │                         ▼
                   │                   BM25 + Vector
                   │                         │
                   ▼                         ▼
              Cache Hit? ──No──▶ OpenAI API ──┘
                   │
                  Yes
                   │
                   ▼
              Return Results
```

---

## 5. 数据库设计

### 5.1 系统表结构

#### `_sys_search` (全局搜索索引表)

```sql
CREATE TABLE _sys_search (
    ref_id VARCHAR,           -- 记录 ID
    source_table VARCHAR,     -- 源表名
    source_field VARCHAR,     -- 字段名
    segmented_text TEXT,      -- 分词后的文本 (BM25)
    embedding_id VARCHAR,     -- 向量 ID (哈希)
    embedding FLOAT[1536],    -- 向量嵌入
    metadata JSON,             -- 完整记录 JSON
    priority_weight FLOAT,    -- 优先级权重
    PRIMARY KEY (ref_id, source_table, source_field)
);
-- HNSW 索引用于向量搜索
CREATE INDEX idx_vec ON _sys_search USING HNSW (embedding) WITH (metric = 'cosine');
```

#### `_sys_cache` (向量缓存表)

```sql
CREATE TABLE _sys_cache (
    content_hash VARCHAR PRIMARY KEY,  -- 内容哈希
    embedding FLOAT[1536],            -- 向量嵌入
    last_used TIMESTAMP               -- 最后使用时间
);
```

### 5.2 目录结构

```
knowledge-bases/{kb_id}/
├── README.md              # 知识库说明
├── config.yaml            # 配置文件 (含本体定义)
├── user_dict.txt          # 中文分词自定义词典
├── schema.sql             # 传统 DDL 定义 (备选)
├── data/                  # 核心事实数据 (Git 跟踪)
│   ├── characters.jsonl
│   └── locations.jsonl
└── .build/                # 运行时产物 (Git 忽略)
    ├── knowledge.db       # DuckDB 数据库
    ├── sync_state.json   # 同步状态
    └── backups/          # 备份目录
```

---

## 6. 技术选型

### 6.1 核心技术栈

| 技术 | 用途 | 版本要求 |
|------|------|----------|
| **DuckDB** | 嵌入式分析数据库 | >= 1.4.4 |
| **FastMCP** | MCP 协议实现 | >= 3.0.2 |
| **OpenAI** | 向量嵌入生成 | >= 2.23.0 |
| **Pydantic** | 配置与数据验证 | >= 2.12.5 |
| **jieba** | 中文分词 | >= 0.42.1 |
| **orjson** | 高性能 JSON 处理 | >= 3.11.7 |
| **typer** | CLI 框架 | >= 0.24.1 |

### 6.2 异步架构

- 所有 I/O 操作均采用 **async/await**
- 同步数据库操作通过 `asyncio.to_thread` 封装
- 避免阻塞事件循环

---

## 7. 安全性设计

### 7.1 SQL 注入防护

- 表名验证：正则 `^[a-zA-Z_][a-zA-Z0-9_]*$`
- SQL 关键字黑名单检测
- 参数化查询

### 7.2 查询限流

- 默认 LIMIT 1000
- 结果集大小限制 2MB
- 只读连接模式

### 7.3 文件操作安全

- 原子写入：先写临时文件再重命名
- 路径验证：防止目录遍历攻击

---

## 8. 配置管理

### 8.1 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KB_PATH` | `./knowledge-bases/default` | 知识库路径 |
| `OPENAI_API_KEY` | - | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | - | API 基础 URL |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型 |
| `EMBEDDING_DIM` | `1536` | 向量维度 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

### 8.2 config.yaml 结构

```yaml
embedding:
  model: text-embedding-3-small
  dim: 1536

log_level: INFO

usage_instructions: |
  # 使用说明...

ontology:
  nodes:
    Character:
      table: characters
      identity: [id]
      schema:
        type: object
        properties:
          id: { type: string }
          name: { type: string, maxLength: 100 }
      vectors:
        description:
          dim: 1536
          model: text-embedding-3-small
```

---

## 9. 开发规范

### 9.1 代码规范

- **Python 3.12+**
- **PEP 8** 格式规范
- **Google Style** Docstring
- **ruff** 强制格式化
- **mypy** 类型检查

### 9.2 依赖管理

- 使用 **uv** 管理依赖
- 新增依赖必须写清用途与替代方案

---

## 10. 测试覆盖

项目包含完整的测试套件：

- `test_main.py` - 入口测试
- `test_searcher.py` - 搜索功能测试
- `test_indexer.py` - 索引功能测试
- `test_cache.py` - 缓存功能测试
- `test_backup.py` - 备份功能测试
- `test_ontology.py` - 本体引擎测试
- `test_sql_security.py` - SQL 安全测试
- `test_core_integration.py` - 核心集成测试

---

## 11. 总结

DuckKB 是一个设计精良的知识库管理系统，具有以下亮点：

1. **MCP 协议支持**：标准化 AI Agent 交互接口
2. **混合检索**：结合向量与全文搜索，兼顾语义和精确性
3. **成本优化**：向量缓存显著降低 API 调用成本
4. **Git 可审计**：便于版本追踪和变更管理
5. **安全可靠**：多重安全机制保护数据
6. **异步架构**：高效处理 I/O 密集型任务
7. **完整工具链**：备份、恢复、迁移一体化

该系统特别适合需要为 AI Agent 提供持久化记忆能力的应用场景。
