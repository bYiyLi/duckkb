# DuckKB MCP 知识导入工具集设计方案

## 一、设计理念：双重契约模式

系统采用"双重契约"模式确保数据一致性：

1. **契约一**：Agent 调用 `get_knowledge_schema()` 获取校验规则
2. **契约二**：Agent 提交符合该 Schema 的数据包

## 二、工具一：get\_knowledge\_schema（模式发现）

### 2.1 功能定位

动态生成并返回当前知识库的**完整校验规则**（Full Validation Schema）。

定义整个 YAML 文件的合法结构：一个包含多种知识条目的数组。

### 2.2 输出结构

```json
{
  "full_bundle_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "DuckKB Knowledge Bundle Schema",
    "type": "array",
    "items": {
      "oneOf": [
        // 节点类型 Schema...
        // 边类型 Schema...
      ]
    }
  },
  "example_yaml": "- type: Document\n  doc_uri: \"...\"\n  content: | ..."
}
```

### 2.3 Schema 设计要点

**根级约束**：

* `type: array`：限制 Agent 必须提交列表

**元素分发（oneOf）**：

* 利用 `oneOf` 关键字组合不同本体类型的校验规则

* 每个元素必须包含 `type` 和 `action`

**必填字段**：

* 节点：根据 `identity` 自动设置必填字段

* 边：强制要求 `source` 和 `target` 对象

### 2.4 输出示例

```json
{
  "full_bundle_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "DuckKB Knowledge Bundle Schema",
    "type": "array",
    "items": {
      "oneOf": [
        {
          "title": "Document Node",
          "type": "object",
          "required": ["type", "doc_uri", "content"],
          "properties": {
            "type": { "const": "Document" },
            "action": { 
              "type": "string", 
              "enum": ["upsert", "delete"], 
              "default": "upsert" 
            },
            "doc_uri": { "type": "string", "description": "唯一标识" },
            "content": { "type": "string", "description": "长文本" }
          },
          "additionalProperties": false
        },
        {
          "title": "EMPLOYED_BY Edge",
          "type": "object",
          "required": ["type", "source", "target"],
          "properties": {
            "type": { "const": "EMPLOYED_BY" },
            "action": { 
              "type": "string", 
              "enum": ["upsert", "delete"], 
              "default": "upsert" 
            },
            "source": {
              "type": "object",
              "required": ["email"],
              "properties": { "email": { "type": "string" } }
            },
            "target": {
              "type": "object",
              "required": ["org_code"],
              "properties": { "org_code": { "type": "string" } }
            },
            "position": { "type": "string" }
          },
          "additionalProperties": false
        }
      ]
    }
  },
  "example_yaml": "- type: Document\n  doc_uri: \"...\"\n  content: | ...\n- type: EMPLOYED_BY\n  source: { email: \"...\" }\n  target: { org_code: \"...\" }"
}
```

### 2.5 Engine 方法

```python
# 在 OntologyMixin 中添加
def get_bundle_schema(self) -> dict:
    """生成知识包的完整校验 Schema。

    根据当前本体定义，动态生成 JSON Schema Draft 7 格式的校验规则。

    Returns:
        包含 full_bundle_schema 和 example_yaml 的字典。
    """
```

### 2.6 MCP 工具注册

```python
@self.tool()
def get_knowledge_schema(self) -> str:
    """获取知识库校验 Schema。

    返回当前知识库的完整校验规则（JSON Schema Draft 7），
    用于验证 import_knowledge_bundle 的输入数据。

    Returns:
        JSON 格式的 Schema 定义。
    """
    return json.dumps(self.get_bundle_schema(), ensure_ascii=False, indent=2)
```

## 三、工具二：import\_knowledge\_bundle（校验与执行）

### 3.1 功能定位

接收 Agent 编写的 YAML 文件，使用数组级 Schema 进行一次性整体校验。

### 3.2 YAML 文件格式

```yaml
- type: Document
  doc_uri: "doc-001"
  content: "DuckDB 是一个嵌入式分析数据库..."

- type: Document
  action: delete
  doc_uri: "doc-old"

- type: REFERENCES
  source: { doc_uri: "doc-001" }
  target: { doc_uri: "doc-002" }
  ref_type: "citation"
```

### 3.3 核心校验流程

```
┌─────────────────────────────────────────────────────────────────┐
│                  import_knowledge_bundle 流程                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 验证文件存在                                                 │
│     └── 检查 temp_file_path 是否存在                             │
│                                                                 │
│  2. 解析 YAML 文件                                               │
│     └── yaml.safe_load 加载为 Python 列表                        │
│                                                                 │
│  3. 数组级校验 (Array-level Validation)                          │
│     ├── 调用 jsonschema.validate(data, full_bundle_schema)       │
│     └── 校验失败返回精确路径：[4].doc_uri: is required            │
│                                                                 │
│  4. 语义对齐                                                     │
│     ├── 节点：从 identity 字段生成 __id                           │
│     └── 边：解析 source/target，查找对应 __id                     │
│                                                                 │
│  5. 批量操作（事务内执行）                                        │
│     ├── upsert: INSERT OR REPLACE                               │
│     └── delete: DELETE WHERE __id = ?                           │
│                                                                 │
│  6. 分词与向量化                                                 │
│     └── 对受影响的节点类型调用 rebuild_index                       │
│                                                                 │
│  7. 影子导出                                                     │
│     ├── 节点：调用 dump_node                                     │
│     └── 边：调用 dump_edge                                       │
│                                                                 │
│  8. 清理临时文件                                                 │
│     └── 删除 temp_file_path                                      │
│                                                                 │
│  9. 返回结果                                                     │
│     └── {"status": "success", "stats": {...}}                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 校验错误示例

如果数组中第 5 个元素（Index 4）不符合约束：

```
Validation error at [4].doc_uri: "doc_uri" is required
```

### 3.5 Engine 方法

```python
# 新增 ImportMixin
class ImportMixin(BaseEngine):
    """知识导入能力 Mixin。"""

    async def import_knowledge_bundle(self, temp_file_path: str) -> dict:
        """导入知识包。

        从 YAML 文件导入数据到知识库，执行完整的校验和 AKF 协议处理。

        Args:
            temp_file_path: 临时 YAML 文件的绝对路径。

        Returns:
            导入结果统计。

        Raises:
            ValidationError: Schema 校验失败时抛出。
            FileNotFoundError: 临时文件不存在时抛出。
        """
```

### 3.6 MCP 工具注册

```python
@self.tool()
async def import_knowledge_bundle(self, temp_file_path: str) -> str:
    """导入知识包。

    从 YAML 文件导入数据到知识库。文件格式为数组，每个元素包含：
    - type: 实体类型（节点类型或边类型名称）
    - action: 操作类型（upsert/delete），默认 upsert
    - 节点：identity 字段
    - 边：source 和 target 对象

    导入前会使用 get_knowledge_schema 返回的 Schema 进行完整校验。

    Args:
        temp_file_path: 临时 YAML 文件的绝对路径。

    Returns:
        JSON 格式的操作结果。
    """
    result = await self.import_knowledge_bundle(temp_file_path)
    return json.dumps(result, ensure_ascii=False)
```

## 四、Schema 生成逻辑

### 4.1 节点 Schema 生成

```python
def _generate_node_schema(self, node_name: str, node_def: NodeType) -> dict:
    """生成节点类型的 JSON Schema。

    Args:
        node_name: 节点类型名称。
        node_def: 节点定义。

    Returns:
        JSON Schema 字典。
    """
    required = ["type"] + node_def.identity
    properties = {
        "type": {"const": node_name},
        "action": {
            "type": "string",
            "enum": ["upsert", "delete"],
            "default": "upsert"
        }
    }

    # 从 json_schema 提取属性定义
    if node_def.json_schema and "properties" in node_def.json_schema:
        for prop_name, prop_def in node_def.json_schema["properties"].items():
            properties[prop_name] = self._prop_to_schema(prop_def)

    return {
        "title": f"{node_name} Node",
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False
    }
```

### 4.2 边 Schema 生成

```python
def _generate_edge_schema(self, edge_name: str, edge_def: EdgeType) -> dict:
    """生成边类型的 JSON Schema。

    Args:
        edge_name: 边类型名称。
        edge_def: 边定义。

    Returns:
        JSON Schema 字典。
    """
    # 获取源节点和目标节点的 identity 字段
    source_node = self.ontology.nodes[edge_def.from_]
    target_node = self.ontology.nodes[edge_def.to_]

    source_props = {
        f: {"type": "string"}
        for f in source_node.identity
    }
    target_props = {
        f: {"type": "string"}
        for f in target_node.identity
    }

    properties = {
        "type": {"const": edge_name},
        "action": {
            "type": "string",
            "enum": ["upsert", "delete"],
            "default": "upsert"
        },
        "source": {
            "type": "object",
            "required": list(source_props.keys()),
            "properties": source_props
        },
        "target": {
            "type": "object",
            "required": list(target_props.keys()),
            "properties": target_props
        }
    }

    # 添加边的属性
    if edge_def.json_schema and "properties" in edge_def.json_schema:
        for prop_name, prop_def in edge_def.json_schema["properties"].items():
            properties[prop_name] = self._prop_to_schema(prop_def)

    return {
        "title": f"{edge_name} Edge",
        "type": "object",
        "required": ["type", "source", "target"],
        "properties": properties,
        "additionalProperties": False
    }
```

## 五、异常反馈机制

### 5.1 校验错误格式

```python
try:
    validate(instance=data, schema=full_bundle_schema)
except ValidationError as e:
    # 返回精确的错误路径
    path = ".".join(str(p) for p in e.absolute_path)
    raise ValueError(f"Validation error at [{path}]: {e.message}")
```

### 5.2 语义错误示例

| 错误类型  | 反馈示例                                                                                                   |
| ----- | ------------------------------------------------------------------------------------------------------ |
| 类型不存在 | `Entity type 'Human' is not defined. Did you mean 'Person'?`                                           |
| 主键缺失  | `Validation error at [2].doc_uri: "doc_uri" is required`                                               |
| 关系孤儿  | `Cannot create 'REFERENCES' relation: Target 'Document' with identity {doc_uri: "doc-001"} not found.` |

## 六、实现步骤

| 步骤 | 任务                                          | 文件                      |
| -- | ------------------------------------------- | ----------------------- |
| 1  | 在 OntologyMixin 添加 `get_bundle_schema` 方法   | core/mixins/ontology.py |
| 2  | 创建 ImportMixin，实现 `import_knowledge_bundle` | core/mixins/import.py   |
| 3  | 将 ImportMixin 加入 Engine 继承链                 | core/engine.py          |
| 4  | 在 DuckMCP 注册 `get_knowledge_schema` 工具      | mcp/duck\_mcp.py        |
| 5  | 在 DuckMCP 注册 `import_knowledge_bundle` 工具   | mcp/duck\_mcp.py        |
| 6  | 运行测试验证                                      | -                       |

## 七、标准操作流程

```
第一步：发现 (Discovery)
    Agent 调用 get_knowledge_schema()
    获得描述"数组中每种可能对象"的总 Schema
    ↓
第二步：生成 (Generation)
    Agent 生成符合该列表结构的 YAML 文件
    ↓
第三步：执行 (Execution)
    Agent 调用 import_knowledge_bundle
    系统对整个数组进行合法性扫描
    ↓
第四步：反馈 (Feedback)
    成功：返回统计信息
    失败：返回精确的错误位置，Agent 修复后重试
```

## 八、优势

1. **一次性准入**：整个文件作为原子单元校验，无需逐条校验
2. **精准定位**：JSON Schema 数组校验给出具体索引位置，Agent 修复方便
3. **高度扩展**：新增本体类型只需在 `oneOf` 数组中增加一项
4. **标准兼容**：使用 JSON Schema Draft 7 标准，Agent 可使用标准库校验

