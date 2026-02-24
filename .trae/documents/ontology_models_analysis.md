# Ontology `_models.py` 问题分析报告

## 概述

本报告分析 `/Users/yi/Code/duckkb/src/duckkb/ontology/_models.py` 文件中存在的问题，包括设计缺陷、未实现功能和潜在风险。

**已确认**：

* `structs` 字段将被移除，不需要实现复用功能

* `json_schema` 字段需要添加 `field_validator` 来校验其是否符合 JSON Schema Draft 7 规范

***

## 一、严重问题

### 1.1 `EdgeType` 模型完全未被使用

**问题描述**：

* `EdgeType` 类定义了边类型（实体间关系），但在整个代码库中**没有任何地方实际使用它**

* `OntologyEngine` 只处理 `nodes`，完全忽略了 `edges`

* 没有生成边表的 DDL 语句

**证据**：

```python
# engine.py 中只有节点相关方法
def generate_node_ddl(node_name: str, node_type: NodeType) -> str: ...
def generate_nodes_ddl(ontology: Ontology) -> str: ...
# 没有 generate_edge_ddl 或类似方法
```

**影响**：

* 设计文档中定义的 `edges` 功能无法工作

* 用户配置的边关系会被静默忽略

* 无法实现实体间关系的存储和查询

**建议修复**：

1. 在 `engine.py` 中实现 `generate_edge_ddl()` 函数
2. 边表设计：存储 `from_id`, `to_id`, `from_type`, `to_type` 及边属性
3. 在 `OntologyEngine` 中添加边相关方法

***

### 1.2 `json_schema` 字段未校验 schema 有效性

**问题描述**：

* `NodeType.json_schema` 和 `EdgeType.json_schema` 字段存储用户定义的 JSON Schema

* 但**没有校验该 schema 是否符合 JSON Schema Draft 7 规范**

* 如果用户传入无效 schema（如 `{"type": "invalid_type"}`），不会被检测到

**证据**：

```python
# _models.py 中 json_schema 字段定义
json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
# 没有 field_validator 来校验 schema 有效性

# _validator.py 中已有校验函数
def _validate_schema_structure(schema: dict[str, object], path: str) -> None:
    """校验 Schema 结构的合法性。"""
    ...
# 但该函数未被用于校验 json_schema 字段
```

**影响**：

* 无效的 schema 定义会被静默接受

* 后续使用 schema 时可能产生难以预期的错误

* 数据完整性无法保障

**建议修复**：
在 `NodeType` 和 `EdgeType` 中添加 `field_validator`：

```python
from duckkb.ontology._validator import _validate_schema_structure

@field_validator("json_schema")
@classmethod
def validate_json_schema(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is not None:
        _validate_schema_structure(v, "schema")
    return v
```

***

## 二、设计缺陷

### 2.1 `NodeType.identity` 默认值与验证器冲突

**问题描述**：

```python
identity: list[str] = Field(default_factory=list)  # 默认空列表

@field_validator("identity")
@classmethod
def validate_identity(cls, v: list[str]) -> list[str]:
    if not v:  # 空列表会触发错误
        raise ValueError("identity required")
    return v
```

**影响**：

* `NodeType()` 不带参数会创建空列表，然后验证失败

* 错误信息不够清晰

**建议修复**：

```python
identity: list[str] = Field(...)  # 移除默认值，强制必填
```

***

### 2.2 缺少跨模型引用验证

**问题描述**：

* `EdgeType.from_` 和 `EdgeType.to` 引用节点类型名称

* 但没有验证这些节点类型是否存在于 `Ontology.nodes` 中

**示例**：

```yaml
edges:
  located_at:
    from: Character
    to: Location  # 如果 Location 未在 nodes 中定义，应该报错
```

**建议修复**：
在 `Ontology` 模型中添加 `@model_validator`：

```python
@model_validator(mode="after")
def validate_edge_references(self) -> "Ontology":
    for edge_name, edge in self.edges.items():
        if edge.from_ not in self.nodes:
            raise ValueError(f"Edge '{edge_name}' references unknown node type '{edge.from_}'")
        if edge.to not in self.nodes:
            raise ValueError(f"Edge '{edge_name}' references unknown node type '{edge.to}'")
    return self
```

***

### 2.3 缺少向量字段与 schema 的一致性验证

**问题描述**：

* `NodeType.vectors` 定义了向量字段名（如 `description_embedding`）

* 但没有验证该字段是否在 `json_schema.properties` 中存在

**建议**：
明确向量字段是否需要在 schema 中声明，如果需要则添加验证。

***

## 三、待移除项

### 3.1 `structs` 字段

**决定**：移除 `Ontology.structs` 字段，不实现复用功能。

**涉及修改**：

1. `_models.py`：移除 `structs` 字段
2. `_schema.py`：移除 `ONTOLOGY_META_SCHEMA` 中的 `structs` 定义
3. `test_ontology.py`：移除 `assert ontology.structs == {}` 相关断言
4. `test_config.py`：移除 `assert ontology.structs == {}` 相关断言

***

## 四、潜在风险

### 4.1 字段别名可能导致混淆

**问题描述**：

```python
# NodeType
json_schema: dict[str, Any] | None = Field(default=None, alias="schema")

# EdgeType
from_: str = Field(alias="from")
json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
```

**影响**：

* YAML/JSON 中使用 `schema` 和 `from`

* Python 代码中使用 `json_schema` 和 `from_`

* 可能导致使用时的混淆

**建议**：
在文档中明确说明别名映射关系。

***

## 五、测试覆盖不足

### 5.1 缺少 EdgeType 测试

`test_ontology.py` 中没有 `TestEdgeType` 类。

### 5.2 缺少 schema 校验测试

没有测试：

* 无效的 JSON Schema 类型（如 `{"type": "invalid"}`）

* 无效的 schema 结构

### 5.3 缺少跨模型验证测试

没有测试：

* 边引用不存在的节点类型

* 向量字段与 schema 的一致性

***

## 六、总结与优先级

| 优先级    | 问题                 | 影响              |
| ------ | ------------------ | --------------- |
| **P0** | EdgeType 未实现       | 核心功能缺失          |
| **P0** | json\_schema 字段未校验 | 无效 schema 被静默接受 |
| **P1** | identity 默认值问题     | 用户体验差           |
| **P1** | 缺少跨模型验证            | 运行时错误风险         |
| **P2** | 向量字段一致性            | 数据完整性风险         |
| **P2** | 测试覆盖不足             | 质量保障风险          |
| **P2** | 移除 structs         | 代码清理            |

***

## 七、建议的修复方案

### 阶段一：代码清理

1. 移除 `Ontology.structs` 字段及相关代码
2. 更新测试文件

### 阶段二：添加 schema 校验

1. 在 `NodeType` 和 `EdgeType` 中添加 `field_validator` 校验 `json_schema` 字段
2. 复用 `_validator.py` 中的 `_validate_schema_structure()` 函数
3. 添加相关测试

### 阶段三：修复现有问题

1. 修复 `identity` 默认值问题
2. 添加 `EdgeType` 测试
3. 添加跨模型引用验证

### 阶段四：实现缺失功能

1. 实现 `generate_edge_ddl()` 和边表存储
2. 完善向量字段验证

### 阶段五：完善文档

1. 明确字段别名映射
2. 补充使用示例

