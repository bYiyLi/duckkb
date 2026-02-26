# 知识图谱检索功能规格说明

## 1. 概述

### 1.1 背景

DuckKB 目前支持向量检索、全文检索和 AI Agent SQL 查询，但缺少知识图谱检索能力。知识图谱检索可以基于实体间的关系进行图遍历，实现"语义+结构"的双重检索。

### 1.2 目标

为 DuckKB 添加知识图谱检索能力，包括：

* 邻居查询：获取节点的直接关联节点

* 多跳遍历：沿指定边类型进行 N 跳遍历

* 路径查询：查找两个节点之间的路径

* 子图提取：提取与指定节点相关的子图

* 图谱+向量融合检索：向量检索结果作为起点进行图遍历

### 1.3 技术约束

* 使用 DuckDB 递归 CTE 实现图遍历

* 与现有 Mixin 架构无缝集成

* 通过 MCP 暴露图检索工具

* 遵循项目代码规范（async/await、类型标注、中文注释）

***

## 2. 数据模型

### 2.1 边表结构

边表已在现有系统中定义，结构如下：

```sql
CREATE TABLE edge_{edge_name} (
    __id BIGINT PRIMARY KEY,
    __from_id BIGINT NOT NULL,   -- 起始节点 ID
    __to_id BIGINT NOT NULL,     -- 目标节点 ID
    __created_at TIMESTAMP,
    __updated_at TIMESTAMP,
    __date DATE GENERATED ALWAYS AS (CAST(__updated_at AS DATE)) VIRTUAL,
    -- 边属性根据 json_schema 定义
);
```

### 2.2 边索引

为优化图查询性能，需要为边表添加索引：

```sql
CREATE INDEX IF NOT EXISTS idx_edge_{edge_name}_from ON edge_{edge_name}(__from_id);
CREATE INDEX IF NOT EXISTS idx_edge_{edge_name}_to ON edge_{edge_name}(__to_id);
```

### 2.3 本体配置扩展

在 `EdgeType` 模型中添加索引配置：

```python
class EdgeIndexConfig(BaseModel):
    """边索引配置。
    
    Attributes:
        from_indexed: 是否为 __from_id 创建索引。
        to_indexed: 是否为 __to_id 创建索引。
    """
    from_indexed: bool = True
    to_indexed: bool = True


class EdgeType(BaseModel):
    """边类型定义。"""
    # 现有字段...
    index: EdgeIndexConfig | None = None  # 新增
```

***

## 3. API 规格

### 3.1 邻居查询 `get_neighbors`

#### 功能描述

获取节点的直接邻居节点，支持方向过滤和边类型过滤。

#### 方法签名

```python
async def get_neighbors(
    self,
    node_type: str,
    node_id: int | str,
    *,
    edge_types: list[str] | None = None,
    direction: str = "both",
    limit: int = 100,
) -> dict[str, Any]:
    """获取节点的邻居节点。

    Args:
        node_type: 起始节点类型名称。
        node_id: 起始节点 ID（__id）或 identity 字段值。
        edge_types: 边类型过滤列表，None 表示所有边类型。
        direction: 遍历方向，可选值：
            - "out": 仅出边（从起始节点指向目标节点）
            - "in": 仅入边（从目标节点指向起始节点）
            - "both": 双向（默认）
        limit: 每种边类型返回的最大邻居数。

    Returns:
        {
            "node": {
                "__id": 123,
                "name": "张三",
                ...  # 节点完整属性
            },
            "neighbors": [
                {
                    "edge_type": "located_at",
                    "direction": "out",
                    "edge": {
                        "__id": 456,
                        "since": "2024-01-01",
                        ...  # 边属性
                    },
                    "node": {
                        "__id": 789,
                        "name": "北京",
                        ...  # 邻居节点属性
                    }
                },
                ...
            ],
            "stats": {
                "total_count": 5,
                "by_edge_type": {
                    "located_at": 1,
                    "works_for": 1,
                    ...
                }
            }
        }

    Raises:
        ValueError: 节点类型不存在或节点 ID 无效。
    """
```

#### 实现逻辑

1. 解析节点类型，获取对应的表名和 identity 字段
2. 如果 `node_id` 是字符串，通过 identity 字段查找 `__id`
3. 根据 `edge_types` 参数确定要查询的边表
4. 根据 `direction` 参数构建出边/入边/双向查询 SQL
5. 执行查询并组装结果

#### SQL 示例

```sql
-- 出边查询
SELECT 
    e.__id as edge_id,
    'located_at' as edge_type,
    'out' as direction,
    e.*,
    n.* as neighbor
FROM edge_located_at e
JOIN locations n ON e.__to_id = n.__id
WHERE e.__from_id = ?
LIMIT ?

-- 入边查询
SELECT 
    e.__id as edge_id,
    'located_at' as edge_type,
    'in' as direction,
    e.*,
    n.* as neighbor
FROM edge_located_at e
JOIN characters n ON e.__from_id = n.__id
WHERE e.__to_id = ?
LIMIT ?
```

***

### 3.2 多跳遍历 `traverse`

#### 功能描述

沿指定边类型进行多跳遍历，返回所有可达节点及其路径信息。

#### 方法签名

```python
async def traverse(
    self,
    node_type: str,
    node_id: int | str,
    *,
    edge_types: list[str] | None = None,
    direction: str = "out",
    max_depth: int = 3,
    limit: int = 1000,
    return_paths: bool = True,
) -> list[dict[str, Any]]:
    """多跳图遍历。

    Args:
        node_type: 起始节点类型名称。
        node_id: 起始节点 ID 或 identity 字段值。
        edge_types: 允许的边类型列表，None 表示所有边类型。
        direction: 遍历方向，"out" | "in" | "both"。
        max_depth: 最大遍历深度，默认 3。
        limit: 返回结果数量限制，默认 1000。
        return_paths: 是否返回完整路径信息，默认 True。
            - True: 返回每条遍历路径的详细信息
            - False: 仅返回可达节点列表（去重）

    Returns:
        当 return_paths=True 时：
        [
            {
                "path": [
                    {"__id": 1, "name": "张三", ...},
                    {"edge_type": "friend_of", "edge_id": 100, ...},
                    {"__id": 2, "name": "李四", ...},
                    {"edge_type": "friend_of", "edge_id": 101, ...},
                    {"__id": 3, "name": "王五", ...}
                ],
                "depth": 2,
                "end_node": {"__id": 3, "name": "王五", ...}
            },
            ...
        ]

        当 return_paths=False 时：
        [
            {
                "node": {"__id": 2, "name": "李四", ...},
                "min_depth": 1,
                "paths_count": 2
            },
            ...
        ]

    Raises:
        ValueError: 参数无效时抛出。
    """
```

#### 实现逻辑

1. 解析起始节点 ID
2. 确定要遍历的边类型集合
3. 使用递归 CTE 进行广度优先遍历
4. 记录遍历路径，避免环路
5. 根据 `return_paths` 参数组装结果

#### SQL 示例（递归 CTE）

```sql
WITH RECURSIVE traverse AS (
    -- 基础情况：起始节点
    SELECT 
        n.__id as node_id,
        n.name as node_name,
        0 as depth,
        ARRAY[n.__id] as path_ids,
        ARRAY[]::BIGINT[] as edge_ids,
        ARRAY[]::VARCHAR[] as edge_types_arr
    FROM characters n
    WHERE n.__id = ?
    
    UNION ALL
    
    -- 递归情况：沿边扩展
    SELECT 
        e.__to_id as node_id,
        n.name as node_name,
        t.depth + 1,
        t.path_ids || ARRAY[e.__to_id],
        t.edge_ids || ARRAY[e.__id],
        t.edge_types_arr || ARRAY['friend_of']
    FROM traverse t
    JOIN edge_friend_of e ON e.__from_id = t.node_id
    JOIN characters n ON n.__id = e.__to_id
    WHERE t.depth < ?
      AND NOT (t.path_ids @> ARRAY[e.__to_id])  -- 避免环路
)
SELECT * FROM traverse WHERE depth > 0 ORDER BY depth LIMIT ?;
```

***

### 3.3 路径查询 `find_paths`

#### 功能描述

查找两个节点之间的所有路径（最短路径优先）。

#### 方法签名

```python
async def find_paths(
    self,
    from_node: tuple[str, int | str],
    to_node: tuple[str, int | str],
    *,
    edge_types: list[str] | None = None,
    max_depth: int = 5,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """查找两节点间的路径。

    Args:
        from_node: 起始节点 (类型名称, ID 或 identity 值)。
        to_node: 目标节点 (类型名称, ID 或 identity 值)。
        edge_types: 允许的边类型列表。
        max_depth: 最大路径长度（边数），默认 5。
        limit: 返回路径数量限制，默认 10。

    Returns:
        [
            {
                "path": [
                    {"type": "Character", "__id": 1, "name": "张三"},
                    {"edge_type": "friend_of", "edge": {...}},
                    {"type": "Character", "__id": 2, "name": "李四"},
                    {"edge_type": "works_for", "edge": {...}},
                    {"type": "Organization", "__id": 3, "name": "公司A"}
                ],
                "length": 2,
                "node_types": ["Character", "Character", "Organization"]
            },
            ...
        ]

    Raises:
        ValueError: 节点不存在或参数无效。
    """
```

#### 实现逻辑

1. 解析起始节点和目标节点的 ID
2. 使用双向 BFS 策略提高效率
3. 记录路径信息
4. 按路径长度排序返回结果

#### SQL 示例（双向 BFS）

```sql
WITH RECURSIVE
-- 正向遍历
forward AS (
    SELECT 
        __from_id,
        __to_id,
        ARRAY[(__from_id, 'Character')] as path,
        ARRAY[(__id, 'friend_of')] as edges,
        1 as depth
    FROM edge_friend_of
    WHERE __from_id = ?
    
    UNION ALL
    
    SELECT 
        e.__from_id,
        e.__to_id,
        f.path || ARRAY[(e.__to_id, 'Character')],
        f.edges || ARRAY[(e.__id, 'friend_of')],
        f.depth + 1
    FROM forward f
    JOIN edge_friend_of e ON e.__from_id = f.__to_id
    WHERE f.depth < ? 
      AND NOT EXISTS (SELECT 1 FROM unnest(f.path) p WHERE p = (e.__to_id, 'Character'))
),
-- 反向遍历
backward AS (
    SELECT 
        __from_id,
        __to_id,
        ARRAY[(__to_id, 'Character')] as path,
        ARRAY[(__id, 'friend_of')] as edges,
        1 as depth
    FROM edge_friend_of
    WHERE __to_id = ?
    
    UNION ALL
    
    SELECT 
        e.__from_id,
        e.__to_id,
        b.path || ARRAY[(e.__from_id, 'Character')],
        b.edges || ARRAY[(e.__id, 'friend_of')],
        b.depth + 1
    FROM backward b
    JOIN edge_friend_of e ON e.__to_id = b.__from_id
    WHERE b.depth < ?
      AND NOT EXISTS (SELECT 1 FROM unnest(b.path) p WHERE p = (e.__from_id, 'Character'))
)
SELECT * FROM forward WHERE __to_id = ?
UNION ALL
SELECT * FROM backward WHERE __from_id = ?
ORDER BY depth
LIMIT ?;
```

***

### 3.4 子图提取 `extract_subgraph`

#### 功能描述

以指定节点为中心，提取指定深度范围内的完整子图。

#### 方法签名

```python
async def extract_subgraph(
    self,
    node_type: str,
    node_id: int | str,
    *,
    edge_types: list[str] | None = None,
    max_depth: int = 2,
    node_limit: int = 100,
    edge_limit: int = 200,
) -> dict[str, Any]:
    """提取子图。

    Args:
        node_type: 中心节点类型名称。
        node_id: 中心节点 ID 或 identity 值。
        edge_types: 包含的边类型列表。
        max_depth: 扩展深度，默认 2。
        node_limit: 节点数量上限，默认 100。
        edge_limit: 边数量上限，默认 200。

    Returns:
        {
            "center_node": {
                "type": "Character",
                "__id": 1,
                "name": "张三",
                ...
            },
            "nodes": [
                {
                    "type": "Location",
                    "__id": 10,
                    "name": "北京",
                    ...
                },
                ...
            ],
            "edges": [
                {
                    "type": "located_at",
                    "__id": 100,
                    "__from_id": 1,
                    "__to_id": 10,
                    "since": "2024-01-01",
                    ...
                },
                ...
            ],
            "stats": {
                "node_count": 15,
                "edge_count": 20,
                "depth_reached": 2,
                "truncated": false
            }
        }

    Raises:
        ValueError: 参数无效时抛出。
    """
```

#### 实现逻辑

1. 使用 `traverse` 方法获取所有可达节点
2. 查询这些节点之间的所有边
3. 应用 `node_limit` 和 `edge_limit` 限制
4. 组装子图结果

***

### 3.5 图谱+向量融合检索 `graph_search`

#### 功能描述

向量检索结果作为种子节点，进行图遍历扩展，返回语义相关节点及其关联上下文。

#### 方法签名

```python
async def graph_search(
    self,
    query: str,
    *,
    node_type: str | None = None,
    edge_types: list[str] | None = None,
    direction: str = "both",
    traverse_depth: int = 1,
    search_limit: int = 5,
    neighbor_limit: int = 10,
    alpha: float = 0.5,
) -> list[dict[str, Any]]:
    """向量检索 + 图遍历融合检索。

    流程：
    1. 使用混合检索（向量+全文）找到语义相关的种子节点
    2. 对每个种子节点进行图遍历扩展
    3. 返回种子节点及其关联上下文

    Args:
        query: 查询文本。
        node_type: 种子节点类型过滤，None 表示所有类型。
        edge_types: 遍历边类型过滤，None 表示所有边类型。
        direction: 图遍历方向，"out" | "in" | "both"。
        traverse_depth: 图遍历深度，默认 1。
        search_limit: 向量检索返回的种子节点数，默认 5。
        neighbor_limit: 每个种子节点的邻居数限制，默认 10。
        alpha: 向量搜索权重（传递给混合检索）。

    Returns:
        [
            {
                "seed": {
                    "node_type": "Character",
                    "node": {"__id": 1, "name": "张三", ...},
                    "score": 0.85,
                    "source_field": "description",
                    "content": "张三是一位勇敢的战士..."
                },
                "context": [
                    {
                        "edge_type": "located_at",
                        "direction": "out",
                        "edge": {"since": "2024-01-01", ...},
                        "node_type": "Location",
                        "node": {"__id": 10, "name": "北京", ...}
                    },
                    {
                        "edge_type": "works_for",
                        "direction": "out",
                        "edge": {"position": "工程师", ...},
                        "node_type": "Organization",
                        "node": {"__id": 20, "name": "公司A", ...}
                    },
                    ...
                ]
            },
            ...
        ]

    Raises:
        ValueError: 参数无效时抛出。
    """
```

#### 实现逻辑

1. 调用现有的 `search` 方法进行混合检索，获取种子节点
2. 对每个种子节点调用 `get_neighbors` 获取邻居
3. 如果 `traverse_depth > 1`，递归获取邻居的邻居
4. 组装融合结果

***

## 4. 模块设计

### 4.1 文件结构

```
src/duckkb/core/
├── mixins/
│   ├── graph.py          # 新增：GraphMixin
│   └── ...
├── models/
│   └── ontology.py       # 修改：添加 EdgeIndexConfig
└── engine.py             # 修改：添加 GraphMixin
```

### 4.2 GraphMixin 类设计

```python
class GraphMixin(BaseEngine):
    """知识图谱检索 Mixin。

    提供基于边表的图遍历和查询能力。
    依赖 conn (DBMixin) 和 ontology (OntologyMixin)。

    Attributes:
        _node_id_cache: 节点 ID 缓存，用于 identity 到 __id 的映射。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化图谱 Mixin。"""
        super().__init__(*args, **kwargs)
        self._node_id_cache: dict[tuple[str, str], int] = {}

    async def get_neighbors(
        self,
        node_type: str,
        node_id: int | str,
        *,
        edge_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> dict[str, Any]:
        """获取节点的邻居节点。"""
        pass

    async def traverse(
        self,
        node_type: str,
        node_id: int | str,
        *,
        edge_types: list[str] | None = None,
        direction: str = "out",
        max_depth: int = 3,
        limit: int = 1000,
        return_paths: bool = True,
    ) -> list[dict[str, Any]]:
        """多跳图遍历。"""
        pass

    async def find_paths(
        self,
        from_node: tuple[str, int | str],
        to_node: tuple[str, int | str],
        *,
        edge_types: list[str] | None = None,
        max_depth: int = 5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """查找两节点间的路径。"""
        pass

    async def extract_subgraph(
        self,
        node_type: str,
        node_id: int | str,
        *,
        edge_types: list[str] | None = None,
        max_depth: int = 2,
        node_limit: int = 100,
        edge_limit: int = 200,
    ) -> dict[str, Any]:
        """提取子图。"""
        pass

    async def graph_search(
        self,
        query: str,
        *,
        node_type: str | None = None,
        edge_types: list[str] | None = None,
        direction: str = "both",
        traverse_depth: int = 1,
        search_limit: int = 5,
        neighbor_limit: int = 10,
        alpha: float = 0.5,
    ) -> list[dict[str, Any]]:
        """向量检索 + 图遍历融合检索。"""
        pass

    # 私有辅助方法
    async def _resolve_node_id(
        self,
        node_type: str,
        node_id: int | str,
    ) -> int:
        """解析节点 ID，支持 __id 或 identity 字段值。"""
        pass

    def _get_edges_for_node(
        self,
        node_type: str,
        direction: str,
    ) -> list[tuple[str, str, str]]:
        """获取与节点类型相关的边信息。

        Returns:
            [(edge_name, from_node_type, to_node_type), ...]
        """
        pass

    def _build_neighbor_query(
        self,
        edge_name: str,
        edge_def: EdgeType,
        node_id: int,
        direction: str,
        limit: int,
    ) -> tuple[str, list[Any]]:
        """构建邻居查询 SQL。"""
        pass
```

### 4.3 MCP 工具注册

```python
def _register_tools(self) -> None:
    # 现有工具...
    self._register_get_neighbors_tool()
    self._register_traverse_tool()
    self._register_find_paths_tool()
    self._register_extract_subgraph_tool()
    self._register_graph_search_tool()

def _register_get_neighbors_tool(self) -> None:
    @self.tool()
    async def get_neighbors(
        node_type: str,
        node_id: int | str,
        edge_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> str:
        """获取节点的邻居节点。

        查询指定节点的直接关联节点，支持按边类型和方向过滤。

        Args:
            node_type: 节点类型名称（如 "Character"）。
            node_id: 节点 ID 或 identity 字段值。
            edge_types: 边类型过滤列表，如 ["friend_of", "located_at"]。
            direction: 遍历方向，"out"（出边）、"in"（入边）、"both"（双向）。
            limit: 每种边类型返回的最大邻居数。

        Returns:
            JSON 格式的邻居信息，包含节点详情和边属性。
        """
        result = await self.get_neighbors(
            node_type=node_type,
            node_id=node_id,
            edge_types=edge_types,
            direction=direction,
            limit=limit,
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
```

***

## 5. 边索引配置

### 5.1 模型修改

在 `src/duckkb/core/models/ontology.py` 中添加：

```python
class EdgeIndexConfig(BaseModel):
    """边索引配置。

    Attributes:
        from_indexed: 是否为 __from_id 创建索引，默认 True。
        to_indexed: 是否为 __to_id 创建索引，默认 True。
    """

    from_indexed: bool = True
    to_indexed: bool = True


class EdgeType(BaseModel):
    """边类型定义。"""
    from_: str = Field(alias="from")
    to: str
    cardinality: str | None = None
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    index: EdgeIndexConfig | None = None  # 新增
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
```

### 5.2 DDL 生成修改

在 `src/duckkb/core/mixins/ontology.py` 中修改 `_generate_edge_ddl`：

```python
def _generate_edge_ddl(self, edge_name: str, edge_type: EdgeType) -> str:
    """生成边表 DDL。"""
    table_name = f"edge_{edge_name}"
    columns = [
        "    __id BIGINT PRIMARY KEY",
        "    __from_id BIGINT NOT NULL",
        "    __to_id BIGINT NOT NULL",
        "    __created_at TIMESTAMP",
        "    __updated_at TIMESTAMP",
        "    __date DATE GENERATED ALWAYS AS (CAST(__updated_at AS DATE)) VIRTUAL",
    ]

    schema = edge_type.json_schema
    if schema and "properties" in schema:
        for prop_name, prop_def in schema["properties"].items():
            col_type = self._json_type_to_duckdb(prop_def)
            columns.append(f"    {prop_name} {col_type}")

    columns_str = ",\n".join(columns)
    ddl = f"CREATE TABLE IF NOT EXISTS {table_name} (\n{columns_str}\n);"

    # 添加索引
    index_statements = []
    index_config = edge_type.index or EdgeIndexConfig()
    if index_config.from_indexed:
        index_statements.append(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_from ON {table_name}(__from_id);"
        )
    if index_config.to_indexed:
        index_statements.append(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_to ON {table_name}(__to_id);"
        )

    if index_statements:
        ddl = ddl + "\n" + "\n".join(index_statements)

    return ddl
```

***

## 6. 错误处理

### 6.1 异常类型

```python
class GraphError(DuckKBError):
    """图谱操作异常基类。"""
    pass


class NodeNotFoundError(GraphError):
    """节点不存在异常。"""
    pass


class EdgeNotFoundError(GraphError):
    """边不存在异常。"""
    pass


class InvalidDirectionError(GraphError):
    """无效遍历方向异常。"""
    pass
```

### 6.2 参数校验

```python
VALID_DIRECTIONS = {"out", "in", "both"}

def _validate_direction(direction: str) -> None:
    """校验遍历方向参数。"""
    if direction not in VALID_DIRECTIONS:
        raise InvalidDirectionError(
            f"Invalid direction: {direction}. Must be one of: {VALID_DIRECTIONS}"
        )
```

***

## 7. 测试用例

### 7.1 单元测试

```python
class TestGraphMixin:
    """GraphMixin 单元测试。"""

    async def test_get_neighbors_out_edges(self, engine):
        """测试出边邻居查询。"""
        result = await engine.get_neighbors(
            node_type="Character",
            node_id="char_001",
            direction="out",
        )
        assert "node" in result
        assert "neighbors" in result
        assert all(n["direction"] == "out" for n in result["neighbors"])

    async def test_get_neighbors_edge_type_filter(self, engine):
        """测试边类型过滤。"""
        result = await engine.get_neighbors(
            node_type="Character",
            node_id="char_001",
            edge_types=["located_at"],
        )
        assert all(n["edge_type"] == "located_at" for n in result["neighbors"])

    async def test_traverse_max_depth(self, engine):
        """测试遍历深度限制。"""
        result = await engine.traverse(
            node_type="Character",
            node_id="char_001",
            max_depth=2,
        )
        assert all(r["depth"] <= 2 for r in result)

    async def test_find_paths_no_path(self, engine):
        """测试无路径情况。"""
        result = await engine.find_paths(
            from_node=("Character", "char_001"),
            to_node=("Character", "char_999"),  # 不存在
            max_depth=3,
        )
        assert result == []

    async def test_graph_search_integration(self, engine):
        """测试向量+图谱融合检索。"""
        result = await engine.graph_search(
            query="勇敢的战士",
            traverse_depth=1,
            search_limit=3,
        )
        assert len(result) <= 3
        for item in result:
            assert "seed" in item
            assert "context" in item
```

### 7.2 集成测试

```python
class TestGraphSearchIntegration:
    """图谱检索集成测试。"""

    async def test_full_workflow(self, engine):
        """测试完整工作流：导入 -> 索引 -> 检索 -> 图遍历。"""
        # 1. 导入测试数据
        # 2. 构建索引
        # 3. 向量检索
        # 4. 图遍历扩展
        # 5. 验证结果
        pass
```

***

## 8. 性能考虑

### 8.1 索引优化

* 为所有边表的 `__from_id` 和 `__to_id` 创建索引

* 考虑复合索引 `(edge_type, __from_id)` 用于多边类型查询

### 8.2 查询优化

* 使用 `LIMIT` 限制遍历规模

* 使用 `EXPLAIN ANALYZE` 分析慢查询

* 对于深度遍历，考虑使用迭代式查询替代递归 CTE

### 8.3 缓存策略

* 缓存热门节点的邻居关系

* 缓存 identity 到 \_\_id 的映射

***

## 9. 文档更新

### 9.1 需要更新的文档

1. `README.md` - 添加图谱检索能力说明

### 9.2 示例代码

在 `get_info()` 中添加图谱检索示例：

````markdown
## 图谱检索

### 邻居查询
查询指定节点的直接关联节点：

```python
result = await engine.get_neighbors(
    node_type="Character",
    node_id="char_001",
    direction="out"
)
````

### 图谱+向量融合检索

语义检索 + 图遍历扩展：

```python
result = await engine.graph_search(
    query="勇敢的战士",
    traverse_depth=1
)
```

```
```

