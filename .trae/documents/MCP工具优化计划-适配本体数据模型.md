# MCP 工具优化计划 - 适配本体数据模型

## 背景

根据《知识库数据模型定义优化方案》，项目正在实施新的本体（Ontology）数据模型。本计划针对 MCP 服务层进行优化，使其能够充分利用新的数据模型能力。

## 当前状态分析

### 已实现的模块
- `ontology/_models.py`: Pydantic 模型定义（NodeType, EdgeType, Ontology, VectorConfig）
- `ontology/_schema.py`: JSON Schema 元模式定义
- `ontology/__init__.py`: 导出接口（但 engine.py 尚未实现）

### 待实现的模块
- `ontology/engine.py`: DDL 生成引擎（缺失）
- `config.py` 中的 ontology 配置解析（未集成）
- `schema.py` 中的 ontology DDL 生成（未集成）

### MCP 当前工具
| 工具 | 功能 | 优化需求 |
|------|------|----------|
| `check_health` | 健康检查 | 增加 ontology 状态信息 |
| `sync_knowledge_base` | 同步知识库 | 适配 ontology 向量配置 |
| `get_schema_info` | 获取模式信息 | 整合 ontology 定义 |
| `smart_search` | 智能搜索 | 支持节点类型过滤 |
| `query_raw_sql` | SQL 查询 | 无需修改 |
| `validate_and_import` | 导入数据 | 使用 ontology schema 验证 |
| `delete_records` | 删除记录 | 无需修改 |

## 优化方案

### 1. 新增 MCP 工具

#### 1.1 `get_ontology_info` - 获取本体定义

**功能**：返回知识库的本体定义，包括节点类型、边类型和向量配置。

**返回内容**：
```json
{
  "nodes": {
    "Character": {
      "table": "characters",
      "identity": ["id"],
      "properties": ["id", "name", "description", "level", "faction"],
      "vectors": {
        "description_embedding": {
          "dim": 1536,
          "model": "text-embedding-3-small",
          "metric": "cosine"
        }
      }
    }
  },
  "edges": {
    "located_at": {
      "from": "Character",
      "to": "Location",
      "cardinality": "N:1"
    }
  }
}
```

**实现位置**：`src/duckkb/mcp/server.py`

#### 1.2 `validate_record` - 验证记录

**功能**：根据 ontology 的 JSON Schema 验证记录是否符合定义。

**参数**：
- `node_type`: 节点类型名称
- `record`: 待验证的记录（JSON 对象）

**返回**：
```json
{
  "valid": true,
  "errors": []
}
```

或

```json
{
  "valid": false,
  "errors": [
    {"field": "name", "message": "required field missing"},
    {"field": "level", "message": "must be >= 1"}
  ]
}
```

### 2. 更新现有工具

#### 2.1 `check_health` 增强

**新增返回字段**：
```json
{
  "status": "healthy",
  "kb_path": "/path/to/kb",
  "db_exists": true,
  "data_files_count": 2,
  "data_files": ["characters", "locations"],
  "ontology": {
    "defined": true,
    "node_types": ["Character", "Location"],
    "edge_types": ["located_at"]
  }
}
```

#### 2.2 `get_schema_info` 增强

**整合内容**：
1. 原有的 schema.sql 内容（向后兼容）
2. 新增 ontology 定义的可读格式
3. 基于 ontology 生成的 ER 图（包含边关系）

#### 2.3 `smart_search` 增强

**新增参数**：
- `node_type`: 可选，按节点类型过滤（替代 table_filter，语义更清晰）

**向后兼容**：保留 `table_filter` 参数，内部映射到 `node_type`

#### 2.4 `validate_and_import` 增强

**验证流程**：
1. 检查 ontology 是否定义了该节点类型
2. 如果定义了 JSON Schema，进行严格验证
3. 如果定义了向量字段，验证源字段存在
4. 返回详细的验证错误信息

### 3. 代码结构变更

#### 3.1 新增文件

```
src/duckkb/ontology/
└── engine.py          # 新增：DDL 生成引擎（其他智能体实现）
```

#### 3.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `config.py` | KBConfig 增加 ontology 字段，from_yaml 解析 ontology |
| `schema.py` | init_schema 使用 ontology 生成 DDL |
| `engine/sync.py` | 适配 ontology 向量配置 |
| `engine/importer.py` | 使用 ontology schema 验证 |
| `mcp/server.py` | 新增工具 + 更新现有工具 |

### 4. 依赖关系

```
ontology/engine.py (待实现)
       ↓
config.py (增加 ontology 解析)
       ↓
schema.py (使用 ontology 生成 DDL)
       ↓
engine/sync.py (适配向量配置)
engine/importer.py (schema 验证)
       ↓
mcp/server.py (MCP 工具优化)
```

## 实施步骤

### Phase 1: 基础设施准备（依赖其他智能体）

1. 等待 `ontology/engine.py` 实现
2. 等待 `config.py` 集成 ontology 解析
3. 等待 `schema.py` 使用 ontology 生成 DDL

### Phase 2: MCP 工具实现

1. **新增 `get_ontology_info` 工具**
   - 从 AppContext 获取 ontology 配置
   - 格式化返回节点和边信息

2. **新增 `validate_record` 工具**
   - 使用 jsonschema 库验证记录
   - 返回详细的验证结果

3. **更新 `check_health` 工具**
   - 增加 ontology 状态检测
   - 返回节点和边类型列表

4. **更新 `get_schema_info` 工具**
   - 整合 ontology 定义
   - 生成包含边关系的 ER 图

5. **更新 `smart_search` 工具**
   - 新增 `node_type` 参数
   - 保持向后兼容

6. **更新 `validate_and_import` 工具**
   - 集成 ontology schema 验证
   - 返回详细错误信息

### Phase 3: 测试与验证

1. 更新测试用例
2. 验证向后兼容性
3. 更新文档

## API 设计详情

### `get_ontology_info`

```python
@mcp.tool()
async def get_ontology_info() -> str:
    """
    获取知识库的本体定义信息。

    返回节点类型、边类型和向量配置的完整定义，
    帮助用户了解知识库的数据模型结构。

    Returns:
        str: JSON 格式的本体定义，包含 nodes、edges 和 structs。
    """
```

### `validate_record`

```python
@mcp.tool()
async def validate_record(node_type: str, record: dict) -> str:
    """
    根据本体定义验证记录。

    使用节点类型的 JSON Schema 验证记录是否符合定义，
    包括必需字段、类型约束和格式约束。

    Args:
        node_type: 节点类型名称（如 "Character"）。
        record: 待验证的记录对象。

    Returns:
        str: JSON 格式的验证结果，包含 valid 和 errors 字段。
    """
```

### 更新后的 `check_health`

```python
@mcp.tool()
async def check_health() -> str:
    """
    检查服务健康状态。

    返回知识库的详细状态信息，包括路径、数据库状态、
    数据文件和本体定义信息。

    Returns:
        str: JSON 格式的状态信息。
    """
```

### 更新后的 `smart_search`

```python
@mcp.tool()
async def smart_search(
    query: str,
    limit: int = 10,
    node_type: str | None = None,
    table_filter: str | None = None,
    alpha: float = 0.5,
) -> str:
    """
    执行智能混合搜索（向量 + 元数据）。

    结合向量相似度搜索和元数据匹配，提供更精准的搜索结果。

    Args:
        query: 搜索查询字符串。
        limit: 返回结果的最大数量，默认为 10。
        node_type: 节点类型过滤器，限定搜索范围到指定节点类型。
        table_filter: （已弃用）表名过滤器，建议使用 node_type。
        alpha: 向量搜索的权重系数，取值范围 0.0 到 1.0。

    Returns:
        str: JSON 格式的搜索结果列表。
    """
```

## 向后兼容性

1. **配置文件**：如果 `config.yaml` 没有 `ontology` 段，系统继续使用 `schema.sql`
2. **MCP 工具**：`table_filter` 参数保留，映射到 `node_type`
3. **数据文件**：现有 JSONL 文件无需修改

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| ontology 模块未完成 | 分阶段实施，先实现不依赖 engine 的工具 |
| JSON Schema 验证性能 | 批量验证时使用异步处理 |
| 向后兼容性破坏 | 保留所有现有参数，新增可选参数 |

## 预期收益

1. **更丰富的元信息**：AI 助手可以了解知识库的数据模型
2. **更强的验证能力**：导入数据前进行严格验证
3. **更精确的搜索**：按节点类型过滤搜索结果
4. **更好的可维护性**：统一的 ontology 定义管理
