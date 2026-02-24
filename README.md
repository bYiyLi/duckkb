# DuckKB

基于 DuckDB 的 MCP 知识库服务，为 AI Agent 提供持久化记忆层。

## 特性

- **混合检索**：向量搜索 + BM25 全文搜索，可配置权重
- **向量缓存**：基于内容哈希缓存 embedding，降低 80%+ API 成本
- **Git 可审计**：所有知识变更通过 `.jsonl` 文件管理，便于版本追踪
- **安全查询**：SQL 黑名单、自动 LIMIT、结果集大小限制
- **原子写入**：文件操作采用"先写临时文件再重命名"策略

## 快速开始

### 安装

```bash
uv sync
```

### 配置

创建 `.env` 文件：

```env
KB_PATH=./knowledge-bases/default
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
LOG_LEVEL=INFO
```

### 启动 MCP 服务

```bash
uv run duckkb serve
```

## 目录结构

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

### 数据文件格式

JSONL 格式，每行一个 JSON 对象，必须包含 `id` 字段：

```jsonl
{"id": "1", "name": "Alice", "bio": "Alice is a software engineer."}
{"id": "2", "name": "Bob", "bio": "Bob likes pizza."}
```

## MCP 工具

| 工具 | 说明 |
|------|------|
| `check_health` | 健康检查 |
| `sync_knowledge_base` | 同步 JSONL 文件到数据库 |
| `get_schema_info` | 获取 Schema 定义信息 |
| `smart_search` | 混合检索（向量 + BM25） |
| `query_raw_sql` | 安全 SQL 查询（只读） |
| `validate_and_import` | 验证并导入数据 |

### smart_search 参数

```python
smart_search(
    query: str,           # 搜索查询
    limit: int = 10,      # 返回数量
    table_filter: str | None = None,  # 表名过滤
    alpha: float = 0.5    # 向量搜索权重 (0.0-1.0)
)
```

## 开发

```bash
# 运行测试
uv run pytest

# 代码格式化
uv run ruff format .
uv run ruff check .

# 类型检查
uv run mypy src
```

## 配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KB_PATH` | `./knowledge-bases/default` | 知识库路径 |
| `OPENAI_API_KEY` | - | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | - | API 基础 URL（支持兼容接口） |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 模型 |
| `EMBEDDING_DIM` | `1536` | 向量维度 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DUCKDB_CONFIG` | `{"memory_limit": "2GB", "threads": "4"}` | DuckDB 配置 |

## License

MIT
