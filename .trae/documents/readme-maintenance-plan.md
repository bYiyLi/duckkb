# README.md 维护计划

## 概述

根据代码实际实现，README.md 存在多处与当前实现不一致的地方，需要进行全面更新。

## 发现的差异

### 1. 目录结构（重大差异）

**README 描述：**

```
knowledge-bases/{kb_id}/
├── README.md           # 知识库说明
├── schema.sql          # 数据库 DDL 定义
├── user_dict.txt       # 中文分词自定义词典
├── data/               # 核心事实数据 (Git 跟踪)
│   ├── characters.jsonl
│   └── locations.jsonl
└── .build/             # 运行时产物 (Git 忽略)
    ├── knowledge.db    # DuckDB 数据库文件
    └── sync_state.json # 同步状态记录
```

**实际实现：**

* 没有 `schema.sql` 文件，DDL 根据 `config.yaml` 中的 ontology 动态生成

* 数据目录结构为：

  * `data/nodes/{table_name}/part_0.jsonl` - 节点数据

  * `data/edges/{edge_name}/part_0.jsonl` - 边数据

  * `data/cache/search_cache.parquet` - 搜索缓存

* 配置文件为 `config.yaml`，包含 ontology 定义

* 数据库使用内存模式，不持久化到文件

### 2. 配置方式（重大差异）

**README 描述：** 使用 `.env` 文件

**实际实现：**

* 使用 `config.yaml` 配置文件定义 ontology 和知识库配置

* 环境变量仅用于敏感信息（`OPENAI_API_KEY`, `OPENAI_BASE_URL`）

### 3. MCP 工具（重大差异）

**README 列出的工具：**

| 工具                    | 说明              |
| --------------------- | --------------- |
| `check_health`        | 健康检查            |
| `sync_knowledge_base` | 同步 JSONL 文件到数据库 |
| `get_schema_info`     | 获取 Schema 定义信息  |
| `smart_search`        | 混合检索（向量 + BM25） |
| `query_raw_sql`       | 安全 SQL 查询（只读）   |
| `validate_and_import` | 验证并导入数据         |

**实际注册的工具：**

| 工具                        | 说明                                  |
| ------------------------- | ----------------------------------- |
| `get_knowledge_schema`    | 获取知识库校验 Schema（JSON Schema Draft 7） |
| `import_knowledge_bundle` | 从 YAML 文件导入知识包                      |
| `search`                  | 智能混合搜索（RRF 融合）                      |
| `vector_search`           | 纯向量语义检索                             |
| `fts_search`              | 纯全文关键词检索                            |
| `get_source_record`       | 根据搜索结果回捞原始业务记录                      |

**注意：** `query_raw_sql` 在代码中定义但未注册到 MCP

### 4. CLI 命令（缺失内容）

**README 未描述 CLI 命令**

**实际 CLI 命令：**

```bash
duckkb serve                           # 启动 MCP 服务器
duckkb version                         # 显示版本信息
duckkb get-knowledge-schema            # 获取知识库校验 Schema
duckkb import-knowledge-bundle <file>  # 导入知识包
duckkb search <query>                  # 混合搜索
duckkb vector-search <query>           # 向量搜索
duckkb fts-search <query>              # 全文搜索
duckkb get-source-record -t <table> -i <id>  # 获取原始记录
```

### 5. 搜索参数（差异）

**README 的** **`smart_search`** **参数：**

```python
smart_search(
    query: str,
    limit: int = 10,
    table_filter: str | None = None,  # 表名过滤
    alpha: float = 0.5
)
```

**实际的** **`search`** **参数：**

```python
search(
    query: str,
    node_type: str | None = None,  # 节点类型过滤器
    limit: int = 10,
    alpha: float = 0.5,
)
```

### 6. 数据导入格式（重大差异）

**README 描述：** 简单 JSONL 格式

```jsonl
{"id": "1", "name": "Alice", "bio": "Alice is a software engineer."}
```

**实际实现：** YAML 数组格式

```yaml
- type: Character        # 节点类型
  action: upsert         # 操作类型（upsert/delete）
  name: Alice
  bio: Alice is a software engineer.
- type: knows            # 边类型
  source: {name: Alice}
  target: {name: Bob}
```

### 7. 配置项（差异）

**README 配置项：**

| 变量                | 默认值                         | 说明            |
| ----------------- | --------------------------- | ------------- |
| `KB_PATH`         | `./knowledge-bases/default` | 知识库路径         |
| `OPENAI_API_KEY`  | -                           | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | -                           | API 基础 URL    |
| `EMBEDDING_MODEL` | `text-embedding-3-small`    | Embedding 模型  |
| `EMBEDDING_DIM`   | `1536`                      | 向量维度          |
| `LOG_LEVEL`       | `INFO`                      | 日志级别          |
| `DUCKDB_CONFIG`   | `{...}`                     | DuckDB 配置     |

**实际配置：**

* `config.yaml`:

  ```yaml
  embedding:
    model: text-embedding-3-small
    dim: 1536
  log_level: INFO
  ontology:
    nodes:
      Character:
        table: characters
        identity: [name]
        schema:
          type: object
          properties:
            name: {type: string}
            bio: {type: string}
    edges:
      knows:
        from: Character
        to: Character
  usage_instructions: "可选的使用说明"
  ```

* 环境变量：`OPENAI_API_KEY`, `OPENAI_BASE_URL`

## 更新计划

### 需要修改的部分

1. **目录结构** - 完全重写，反映实际的 config.yaml + data/ 结构
2. **配置** - 改为 config.yaml + 环境变量的混合模式
3. **MCP 工具** - 更新工具列表和说明
4. **CLI 命令** - 新增 CLI 命令章节
5. **数据文件格式** - 改为 YAML 知识包格式
6. **搜索参数** - 更新参数名称和说明
7. **配置项表格** - 更新为实际配置结构

### 保持不变的部分

1. **特性列表** - 基本准确，可微调
2. **安装说明** - `uv sync` 正确
3. **开发命令** - pytest/ruff/mypy 正确
4. **License** - MIT 正确

## 建议的新 README 结构

```markdown
# DuckKB

基于 DuckDB 的 MCP 知识库服务，为 AI Agent 提供持久化记忆层。

## 特性
（保持现有内容，微调）

## 快速开始

### 安装
（保持现有内容）

### 配置
（重写：config.yaml + 环境变量）

### 启动 MCP 服务
（保持现有内容）

## 目录结构
（完全重写）

## 配置文件
（新增章节：config.yaml 结构说明）

## 数据导入
（重写：YAML 知识包格式）

## CLI 命令
（新增章节）

## MCP 工具
（更新工具列表）

## 开发
（保持现有内容）

## License
（保持现有内容）
```

