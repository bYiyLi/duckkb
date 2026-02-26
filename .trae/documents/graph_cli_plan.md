# 知识图谱检索 CLI 命令添加计划

## 1. 概述

将知识图谱检索功能完整添加到 CLI 中，提供 5 个新命令：

* `get-neighbors`：获取节点的邻居节点

* `traverse`：多跳图遍历

* `find-paths`：查找两节点间的路径

* `extract-subgraph`：提取子图

* `graph-search`：向量检索 + 图遍历融合检索

## 2. 现有实现状态

### 2.1 已实现的 API（P0）

| API             | 状态    | CLI 命令 |
| --------------- | ----- | ------ |
| `get_neighbors` | ✅ 已实现 | 待添加    |
| `graph_search`  | ✅ 已实现 | 待添加    |

### 2.2 待实现的 API（P1/P2）

| API                | 优先级 | CLI 命令 |
| ------------------ | --- | ------ |
| `traverse`         | P1  | 待实现    |
| `extract_subgraph` | P1  | 待实现    |
| `find_paths`       | P2  | 待实现    |

## 3. 实现计划

### 阶段一：为已实现的 API 添加 CLI 命令

#### 3.1 get-neighbors 命令

**命令签名**：

```bash
duckkb get-neighbors <node_type> <node_id> [OPTIONS]
```

**参数**：

| 参数             | 类型      | 必需 | 默认值  | 说明                 |
| -------------- | ------- | -- | ---- | ------------------ |
| `node_type`    | str     | ✅  | -    | 节点类型名称             |
| `node_id`      | int/str | ✅  | -    | 节点 ID 或 identity 值 |
| `--edge-types` | str     | ❌  | None | 边类型过滤，逗号分隔         |
| `--direction`  | str     | ❌  | both | 遍历方向：out/in/both   |
| `--limit`      | int     | ❌  | 100  | 返回数量限制             |

**示例**：

```bash
duckkb get-neighbors Character char_001 --direction out
duckkb get-neighbors Character char_001 --edge-types friend_of,located_at
```

#### 3.2 graph-search 命令

**命令签名**：

```bash
duckkb graph-search <query> [OPTIONS]
```

**参数**：

| 参数                 | 类型    | 必需 | 默认值  | 说明         |
| ------------------ | ----- | -- | ---- | ---------- |
| `query`            | str   | ✅  | -    | 查询文本       |
| `--node-type`      | str   | ❌  | None | 种子节点类型过滤   |
| `--edge-types`     | str   | ❌  | None | 边类型过滤，逗号分隔 |
| `--direction`      | str   | ❌  | both | 遍历方向       |
| `--traverse-depth` | int   | ❌  | 1    | 图遍历深度      |
| `--search-limit`   | int   | ❌  | 5    | 种子节点数      |
| `--neighbor-limit` | int   | ❌  | 10   | 邻居数限制      |
| `--alpha`          | float | ❌  | 0.5  | 向量搜索权重     |

**示例**：

```bash
duckkb graph-search "勇敢的战士"
duckkb graph-search "勇敢的战士" --traverse-depth 2 --alpha 0.7
```

### 阶段二：实现剩余 API 并添加 CLI 命令

#### 3.3 traverse 命令（P1）

**功能**：沿指定边类型进行多跳遍历

**命令签名**：

```bash
duckkb traverse <node_type> <node_id> [OPTIONS]
```

**参数**：

| 参数             | 类型      | 必需 | 默认值   | 说明             |
| -------------- | ------- | -- | ----- | -------------- |
| `node_type`    | str     | ✅  | -     | 起始节点类型         |
| `node_id`      | int/str | ✅  | -     | 起始节点 ID        |
| `--edge-types` | str     | ❌  | None  | 允许的边类型         |
| `--direction`  | str     | ❌  | out   | 遍历方向           |
| `--max-depth`  | int     | ❌  | 3     | 最大遍历深度         |
| `--limit`      | int     | ❌  | 1000  | 返回结果限制         |
| `--no-paths`   | bool    | ❌  | False | 仅返回节点列表（不返回路径） |

**示例**：

```bash
# 查询角色的朋友的朋友
duckkb traverse Character char_001 --edge-types friend_of --max-depth 2

# 仅返回可达节点列表
duckkb traverse Character char_001 --max-depth 3 --no-paths
```

#### 3.4 extract-subgraph 命令（P1）

**功能**：以指定节点为中心提取子图

**命令签名**：

```bash
duckkb extract-subgraph <node_type> <node_id> [OPTIONS]
```

**参数**：

| 参数             | 类型      | 必需 | 默认值  | 说明      |
| -------------- | ------- | -- | ---- | ------- |
| `node_type`    | str     | ✅  | -    | 中心节点类型  |
| `node_id`      | int/str | ✅  | -    | 中心节点 ID |
| `--edge-types` | str     | ❌  | None | 包含的边类型  |
| `--max-depth`  | int     | ❌  | 2    | 扩展深度    |
| `--node-limit` | int     | ❌  | 100  | 节点数量上限  |
| `--edge-limit` | int     | ❌  | 200  | 边数量上限   |

**示例**：

```bash
# 提取角色相关的子图
duckkb extract-subgraph Character char_001 --max-depth 2

# 限制子图大小
duckkb extract-subgraph Character char_001 --node-limit 50 --edge-limit 100
```

#### 3.5 find-paths 命令（P2）

**功能**：查找两个节点之间的路径

**命令签名**：

```bash
duckkb find-paths <from_type> <from_id> <to_type> <to_id> [OPTIONS]
```

**参数**：

| 参数             | 类型      | 必需 | 默认值  | 说明      |
| -------------- | ------- | -- | ---- | ------- |
| `from_type`    | str     | ✅  | -    | 起始节点类型  |
| `from_id`      | int/str | ✅  | -    | 起始节点 ID |
| `to_type`      | str     | ✅  | -    | 目标节点类型  |
| `to_id`        | int/str | ✅  | -    | 目标节点 ID |
| `--edge-types` | str     | ❌  | None | 允许的边类型  |
| `--max-depth`  | int     | ❌  | 5    | 最大路径长度  |
| `--limit`      | int     | ❌  | 10   | 返回路径数量  |

**示例**：

```bash
# 查找两个角色之间的关系路径
duckkb find-paths Character char_001 Character char_002

# 限制路径长度
duckkb find-paths Character char_001 Character char_002 --max-depth 3
```

## 4. 实现步骤

### 步骤 1：修改 `_register_commands` 方法

```python
def _register_commands(self) -> None:
    """注册 CLI 命令。"""
    self._register_serve_command()
    self._register_version_command()
    self._register_info_command()
    self._register_import_command()
    self._register_search_commands()
    self._register_query_raw_sql_command()
    self._register_graph_commands()  # 新增
```

### 步骤 2：实现 `_register_graph_commands` 方法

```python
def _register_graph_commands(self) -> None:
    """注册图谱检索相关命令。"""
    self._register_get_neighbors_command()
    self._register_graph_search_command()
    self._register_traverse_command()
    self._register_extract_subgraph_command()
    self._register_find_paths_command()
```

### 步骤 3：实现各命令方法

按照现有 CLI 命令模式实现：

* `_register_get_neighbors_command`

* `_register_graph_search_command`

* `_register_traverse_command`

* `_register_extract_subgraph_command`

* `_register_find_paths_command`

### 步骤 4：在 GraphMixin 中实现剩余 API

在 `src/duckkb/core/mixins/graph.py` 中添加：

* `traverse` 方法

* `extract_subgraph` 方法

* `find_paths` 方法

### 步骤 5：在 MCP 中注册剩余工具

在 `src/duckkb/mcp/duck_mcp.py` 中添加：

* `_register_traverse_tool`

* `_register_extract_subgraph_tool`

* `_register_find_paths_tool`

## 5. 文件修改清单

### 5.1 新增/修改文件

| 文件                                | 修改内容                                             |
| --------------------------------- | ------------------------------------------------ |
| `src/duckkb/core/mixins/graph.py` | 添加 `traverse`、`extract_subgraph`、`find_paths` 方法 |
| `src/duckkb/mcp/duck_mcp.py`      | 添加 3 个 MCP 工具注册方法                                |
| `src/duckkb/cli/duck_typer.py`    | 添加 5 个 CLI 命令注册方法                                |

### 5.2 详细修改

**duck\_typer.py**：

* [ ] 修改 `_register_commands` 方法

* [ ] 添加 `_register_graph_commands` 方法

* [ ] 添加 `_register_get_neighbors_command` 方法

* [ ] 添加 `_register_graph_search_command` 方法

* [ ] 添加 `_register_traverse_command` 方法

* [ ] 添加 `_register_extract_subgraph_command` 方法

* [ ] 添加 `_register_find_paths_command` 方法

**graph.py**：

* [ ] 添加 `traverse` 方法

* [ ] 添加 `extract_subgraph` 方法

* [ ] 添加 `find_paths` 方法

**duck\_mcp.py**：

* [ ] 添加 `_register_traverse_tool` 方法

* [ ] 添加 `_register_extract_subgraph_tool` 方法

* [ ] 添加 `_register_find_paths_tool` 方法

## 6. 命令汇总

| CLI 命令             | API 方法             | MCP 工具             | 优先级 |
| ------------------ | ------------------ | ------------------ | --- |
| `get-neighbors`    | `get_neighbors`    | `get_neighbors`    | P0  |
| `graph-search`     | `graph_search`     | `graph_search`     | P0  |
| `traverse`         | `traverse`         | `traverse`         | P1  |
| `extract-subgraph` | `extract_subgraph` | `extract_subgraph` | P1  |
| `find-paths`       | `find_paths`       | `find_paths`       | P2  |

## 7. 测试计划

### 7.1 基础功能测试

```bash
# get-neighbors
duckkb get-neighbors Character char_001 --direction out
duckkb get-neighbors Character char_001 --edge-types friend_of,located_at

# graph-search
duckkb graph-search "勇敢的战士"
duckkb graph-search "勇敢的战士" --traverse-depth 2

# traverse
duckkb traverse Character char_001 --max-depth 2
duckkb traverse Character char_001 --edge-types friend_of --no-paths

# extract-subgraph
duckkb extract-subgraph Character char_001 --max-depth 2
duckkb extract-subgraph Character char_001 --node-limit 50

# find-paths
duckkb find-paths Character char_001 Character char_002
duckkb find-paths Character char_001 Character char_002 --max-depth 3
```

### 7.2 错误处理测试

```bash
# 无效方向参数
duckkb get-neighbors Character char_001 --direction invalid

# 无效节点类型
duckkb get-neighbors InvalidType char_001

# 不存在的节点
duckkb get-neighbors Character nonexistent_id
```

## 8. 代码规范检查

* [ ] 所有新增方法包含中文 Docstring

* [ ] Docstring 包含 Args 和 Returns 部分

* [ ] 使用 `asyncio.run` 运行异步函数

* [ ] 使用 `typer.Argument` 定义必需参数

* [ ] 使用 `typer.Option` 定义可选参数

* [ ] 使用 `json.dumps` 格式化输出结果

* [ ] 使用 `default=str` 处理特殊类型（datetime 等）

* [ ] 通过 `ruff check` 检查

* [ ] 通过 `ruff format` 格式化

