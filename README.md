# DuckKB

基于 DuckDB 的 MCP 知识库服务，为 AI Agent 提供持久化记忆层。

## 特性

- **混合检索**：向量搜索 + 全文检索，RRF 算法融合
- **向量缓存**：基于内容哈希缓存 embedding，降低 API 成本
- **本体驱动**：通过 `config.yaml` 定义知识结构，DDL 自动生成
- **原子导入**：事务包装 + 影子导出，确保数据一致性
- **安全查询**：SQL 黑名单、自动 LIMIT、结果集大小限制
- **多端支持**：CLI 命令行 + MCP 服务（stdio/http/sse）

## 快速开始

### 安装

```bash
uv sync
```

### 配置

创建 `config.yaml` 定义知识库本体：

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
usage_instructions: "可选的使用说明，传递给 AI Agent"
```

设置环境变量（仅敏感信息）：

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.openai.com/v1
```

### 启动 MCP 服务

```bash
uv run duckkb serve
```

## 目录结构

```
knowledge-bases/{kb_id}/
├── config.yaml           # 知识库配置（本体定义 + 嵌入配置）
├── data/                 # 数据目录（Git 跟踪）
│   ├── nodes/            # 节点数据
│   │   └── characters/
│   │       └── part_0.jsonl
│   ├── edges/            # 边数据
│   │   └── knows/
│   │       └── part_0.jsonl
│   └── cache/            # 搜索缓存
│       └── search_cache.parquet
```

**说明：**
- 数据库使用内存模式，不持久化 `.db` 文件
- DDL 根据 `config.yaml` 中的 ontology 动态生成
- 数据导出为 JSONL 格式，便于 Git 版本追踪

## 配置文件

### config.yaml 结构

```yaml
embedding:
  model: text-embedding-3-small  # 嵌入模型
  dim: 1536                      # 向量维度（1536 或 3072）
log_level: INFO                  # 日志级别
ontology:
  nodes:
    {node_type}:
      table: {table_name}        # 数据库表名
      identity: [field1, ...]    # 标识字段（主键）
      schema:                    # JSON Schema Draft 7
        type: object
        properties:
          field1: {type: string}
  edges:
    {edge_type}:
      from: {source_node_type}   # 起始节点类型
      to: {target_node_type}     # 目标节点类型
      schema:                    # 边属性 Schema（可选）
        type: object
        properties:
          weight: {type: number}
usage_instructions: "..."        # 传递给 AI Agent 的使用说明
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | API 基础 URL（支持兼容接口） |

## 数据导入

### YAML 知识包格式

使用 `import_knowledge_bundle` 导入数据，文件格式为 YAML 数组：

```yaml
- type: Character        # 节点类型
  action: upsert         # 操作类型：upsert 或 delete
  name: Alice            # 标识字段
  bio: Alice is a software engineer.

- type: Character
  action: delete
  name: Bob

- type: knows            # 边类型
  source: {name: Alice}  # 起始节点标识
  target: {name: Bob}    # 目标节点标识
```

### 导入流程

1. 调用 `get_knowledge_schema` 获取校验规则
2. 准备 YAML 文件
3. 调用 `import_knowledge_bundle` 导入
4. 系统自动执行：
   - Schema 校验
   - 事务导入（节点 + 边）
   - 引用完整性检查
   - 索引构建
   - 向量计算
   - 数据持久化

## CLI 命令

```bash
duckkb serve                           # 启动 MCP 服务器
duckkb version                         # 显示版本信息
duckkb get-knowledge-schema            # 获取知识库校验 Schema
duckkb import-knowledge-bundle <file>  # 导入知识包
duckkb search <query> [options]        # 混合搜索
duckkb vector-search <query> [options] # 向量搜索
duckkb fts-search <query> [options]    # 全文搜索
duckkb get-source-record -t <table> -i <id>  # 获取原始记录
```

### 全局选项

```bash
--kb-path, -k <path>   # 知识库目录路径，默认 ./knowledge-bases/default
```

### 搜索选项

```bash
--node-type, -t <type>  # 节点类型过滤器
--limit, -l <n>         # 返回结果数量，默认 10
--alpha, -a <float>     # 向量权重（仅 search），默认 0.5
```

## MCP 工具

| 工具 | 说明 |
|------|------|
| `get_knowledge_schema` | 获取知识库校验 Schema（JSON Schema Draft 7） |
| `import_knowledge_bundle` | 从 YAML 文件导入知识包 |
| `search` | 智能混合搜索（RRF 融合向量 + 全文） |
| `vector_search` | 纯向量语义检索 |
| `fts_search` | 纯全文关键词检索 |
| `get_source_record` | 根据搜索结果回捞原始业务记录 |

### search 参数

```python
search(
    query: str,                    # 搜索查询文本
    node_type: str | None = None,  # 节点类型过滤器
    limit: int = 10,               # 返回结果数量
    alpha: float = 0.5,            # 向量权重 (0.0-1.0)
)
```

### 搜索结果结构

```json
{
  "source_table": "characters",
  "source_id": 123456789,
  "source_field": "bio",
  "chunk_seq": 0,
  "content": "匹配的文本内容",
  "score": 0.85
}
```

## 开发

```bash
uv run pytest
uv run ruff format .
uv run ruff check .
uv run mypy src
```

## License

MIT
