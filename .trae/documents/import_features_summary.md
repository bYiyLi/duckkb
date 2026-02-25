# DuckKB 知识导入功能增强计划

## 一、实现计划概览

| 阶段          | 功能              | 优先级 | 预计工作量  |
| ----------- | --------------- | --- | ------ |
| **Phase 1** | 边引用完整性检查（事务内校验） | P0  | 3 个方法  |
| **Phase 2** | 增量索引更新          | P1  | 4 个方法  |
| **Phase 3** | 批量操作优化          | P2  | 重构现有方法 |

***

## 二、Phase 1: 边引用完整性检查（事务内校验）

### 2.1 设计思路

**关键变更**：边引用完整性检查在数据入库后、事务提交前执行

```
原流程：
  Schema 校验 → 导入节点 → 导入边 → 索引重建 → 持久化导出

新流程：
  Schema 校验 → 开启事务 → 导入节点 → 导入边 → 验证边引用 → 提交/回滚 → 索引重建 → 持久化导出
```

**优势**：

1. 支持同一批次中先创建节点再创建边
2. 引用完整性失败时自动回滚，保证数据一致性

### 2.2 实现步骤

```
步骤 1: 在 ImportMixin 添加 _node_exists_in_transaction 方法
    └── 在事务内检查节点是否存在（包括未提交的数据）

步骤 2: 在 ImportMixin 添加 _validate_edge_references 方法
    └── 验证边的 source/target 节点是否存在

步骤 3: 重构 import_knowledge_bundle 主方法
    └── 使用单一事务包装所有数据库操作
```

### 2.3 代码修改

**文件**: `src/duckkb/core/mixins/import_.py`

**新增方法 1**: `_node_exists_in_transaction`

```python
def _node_exists_in_transaction(self, table_name: str, node_id: int) -> bool:
    """在事务内检查节点是否存在。

    包括已提交和未提交的数据。

    Args:
        table_name: 节点表名。
        node_id: 节点 ID。

    Returns:
        节点存在返回 True，否则返回 False。
    """
    result = self.conn.execute(
        f"SELECT 1 FROM {table_name} WHERE __id = ? LIMIT 1",
        [node_id]
    ).fetchone()
    return result is not None
```

**新增方法 2**: `_validate_edge_references`

```python
def _validate_edge_references(
    self,
    edge_type: str,
    items: list[dict[str, Any]],
) -> None:
    """验证边引用的节点是否存在。

    在事务内执行，检查 source/target 节点是否存在于数据库中
    （包括同一事务中刚插入的数据）。

    Args:
        edge_type: 边类型名称。
        items: 边数据列表。

    Raises:
        ValueError: 当引用的节点不存在时抛出。
    """
    edge_def = self.ontology.edges.get(edge_type)
    if edge_def is None:
        return

    source_node_def = self.ontology.nodes.get(edge_def.from_)
    target_node_def = self.ontology.nodes.get(edge_def.to)

    if source_node_def is None or target_node_def is None:
        return

    for idx, item in enumerate(items):
        source = item.get("source", {})
        target = item.get("target", {})

        source_identity = [source.get(f) for f in source_node_def.identity]
        source_id = compute_deterministic_id(source_identity)

        if not self._node_exists_in_transaction(source_node_def.table, source_id):
            raise ValueError(
                f"[{idx}] Cannot create '{edge_type}' relation: "
                f"Source '{edge_def.from_}' with identity {source} not found."
            )

        target_identity = [target.get(f) for f in target_node_def.identity]
        target_id = compute_deterministic_id(target_identity)

        if not self._node_exists_in_transaction(target_node_def.table, target_id):
            raise ValueError(
                f"[{idx}] Cannot create '{edge_type}' relation: "
                f"Target '{edge_def.to}' with identity {target} not found."
            )
```

**重构主方法**: `import_knowledge_bundle`

```python
async def import_knowledge_bundle(self, temp_file_path: str) -> dict[str, Any]:
    """导入知识包。"""
    path = Path(temp_file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {temp_file_path}")

    content = await self._read_file(path)
    data = yaml.safe_load(content)

    if not isinstance(data, list):
        raise ValueError("YAML file must contain an array at root level")

    get_bundle_schema = getattr(self, "get_bundle_schema", None)
    if get_bundle_schema is None:
        raise RuntimeError("get_bundle_schema method not available")
    bundle_schema = get_bundle_schema()
    full_schema = bundle_schema["full_bundle_schema"]

    try:
        validate(instance=data, schema=full_schema)
    except ValidationError as e:
        path_str = ".".join(str(p) for p in e.absolute_path)
        raise ValueError(f"Validation error at [{path_str}]: {e.message}") from e

    nodes_data: list[dict[str, Any]] = []
    edges_data: list[dict[str, Any]] = []

    for item in data:
        item_type = item.get("type")
        if item_type in self.ontology.nodes:
            nodes_data.append(item)
        elif item_type in self.ontology.edges:
            edges_data.append(item)

    # 使用单一事务包装所有数据库操作
    nodes_result, edges_result = await self._execute_import_in_transaction(
        nodes_data, edges_data
    )

    # 事务提交成功后，执行后处理
    affected_node_types = set(nodes_result.get("upserted", {}).keys())
    affected_node_types.update(nodes_result.get("deleted", {}).keys())

    indexed = {}
    for node_type in affected_node_types:
        if hasattr(self, "rebuild_index"):
            indexed[node_type] = await self.rebuild_index(node_type)

    dumped = {}
    for node_type in affected_node_types:
        if hasattr(self, "dump_node"):
            dumped[node_type] = await self.dump_node(node_type)

    for edge_name in edges_result.get("upserted", {}).keys():
        if hasattr(self, "dump_edge"):
            dumped[edge_name] = await self.dump_edge(edge_name)
    for edge_name in edges_result.get("deleted", {}).keys():
        if hasattr(self, "dump_edge"):
            dumped[edge_name] = await self.dump_edge(edge_name)

    await self._unlink_file(path)

    return {
        "status": "success",
        "nodes": nodes_result,
        "edges": edges_result,
        "indexed": indexed,
        "dumped": dumped,
    }

async def _execute_import_in_transaction(
    self,
    nodes_data: list[dict[str, Any]],
    edges_data: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """在单一事务中执行所有导入操作。

    流程：
    1. 开启事务
    2. 导入所有节点
    3. 导入所有边
    4. 验证边引用完整性
    5. 提交事务（失败则回滚）

    Args:
        nodes_data: 节点数据列表。
        edges_data: 边数据列表。

    Returns:
        (节点导入结果, 边导入结果)

    Raises:
        ValueError: 边引用验证失败时抛出（事务已回滚）。
    """
    def _execute() -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            self.conn.begin()

            # 1. 导入节点
            nodes_result = self._import_nodes_sync(nodes_data)

            # 2. 导入边
            edges_result = self._import_edges_sync(edges_data)

            # 3. 验证边引用完整性
            for edge_type, items in edges_data_by_type(edges_data).items():
                if items:
                    self._validate_edge_references(edge_type, items)

            # 4. 提交事务
            self.conn.commit()
            return nodes_result, edges_result

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    return await asyncio.to_thread(_execute)

def _import_nodes_sync(self, data: list[dict[str, Any]]) -> dict[str, Any]:
    """同步导入节点（在事务内执行）。"""
    upserted: dict[str, int] = {}
    deleted: dict[str, int] = {}

    grouped: dict[str, dict[str, list]] = {}
    for item in data:
        node_type = item.get("type")
        if node_type is None:
            continue
        action = item.get("action", "upsert")
        if action not in ("upsert", "delete"):
            action = "upsert"

        if node_type not in grouped:
            grouped[node_type] = {"upsert": [], "delete": []}
        grouped[node_type][action].append(item)

    for node_type, actions in grouped.items():
        if actions["upsert"]:
            count = self._upsert_nodes_sync(node_type, actions["upsert"])
            upserted[node_type] = count
        if actions["delete"]:
            count = self._delete_nodes_sync(node_type, actions["delete"])
            deleted[node_type] = count

    return {"upserted": upserted, "deleted": deleted}

def _import_edges_sync(self, data: list[dict[str, Any]]) -> dict[str, Any]:
    """同步导入边（在事务内执行）。"""
    upserted: dict[str, int] = {}
    deleted: dict[str, int] = {}

    grouped: dict[str, dict[str, list]] = {}
    for item in data:
        edge_type = item.get("type")
        if edge_type is None:
            continue
        action = item.get("action", "upsert")
        if action not in ("upsert", "delete"):
            action = "upsert"

        if edge_type not in grouped:
            grouped[edge_type] = {"upsert": [], "delete": []}
        grouped[edge_type][action].append(item)

    for edge_type, actions in grouped.items():
        if actions["upsert"]:
            count = self._upsert_edges_sync(edge_type, actions["upsert"])
            upserted[edge_type] = count
        if actions["delete"]:
            count = self._delete_edges_sync(edge_type, actions["delete"])
            deleted[edge_type] = count

    return {"upserted": upserted, "deleted": deleted}

def _upsert_nodes_sync(self, node_type: str, items: list[dict[str, Any]]) -> int:
    """同步 upsert 节点（在事务内执行）。"""
    node_def = self.ontology.nodes.get(node_type)
    if node_def is None:
        raise ValueError(f"Unknown node type: {node_type}")

    table_name = node_def.table
    now = datetime.now(UTC)
    count = 0

    for item in items:
        record = {k: v for k, v in item.items() if k not in ("type", "action")}
        identity_values = [record.get(f) for f in node_def.identity]
        record["__id"] = compute_deterministic_id(identity_values)
        record["__created_at"] = now
        record["__updated_at"] = now

        columns = list(record.keys())
        values = [record[c] for c in columns]
        placeholders = ", ".join(["?" for _ in columns])

        self.conn.execute(
            f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) "
            f"VALUES ({placeholders})",
            values
        )
        count += 1

    return count

def _delete_nodes_sync(self, node_type: str, items: list[dict[str, Any]]) -> int:
    """同步删除节点（在事务内执行）。"""
    node_def = self.ontology.nodes.get(node_type)
    if node_def is None:
        raise ValueError(f"Unknown node type: {node_type}")

    table_name = node_def.table
    count = 0

    for item in items:
        record = {k: v for k, v in item.items() if k not in ("type", "action")}
        identity_values = [record.get(f) for f in node_def.identity]
        record_id = compute_deterministic_id(identity_values)

        self.conn.execute(
            f"DELETE FROM {table_name} WHERE __id = ?",
            [record_id]
        )
        count += 1

    return count

def _upsert_edges_sync(self, edge_type: str, items: list[dict[str, Any]]) -> int:
    """同步 upsert 边（在事务内执行）。"""
    edge_def = self.ontology.edges.get(edge_type)
    if edge_def is None:
        raise ValueError(f"Unknown edge type: {edge_type}")

    table_name = f"edge_{edge_type}"
    source_node = self.ontology.nodes.get(edge_def.from_)
    target_node = self.ontology.nodes.get(edge_def.to)

    if source_node is None or target_node is None:
        raise ValueError(f"Invalid edge definition: {edge_type}")

    now = datetime.now(UTC)
    count = 0

    for item in items:
        source = item.get("source", {})
        target = item.get("target", {})

        source_identity = [source.get(f) for f in source_node.identity]
        target_identity = [target.get(f) for f in target_node.identity]

        source_id = compute_deterministic_id(source_identity)
        target_id = compute_deterministic_id(target_identity)

        record: dict[str, Any] = {
            "__id": compute_deterministic_id([source_id, target_id]),
            "__from_id": source_id,
            "__to_id": target_id,
            "__created_at": now,
            "__updated_at": now,
        }

        for k, v in item.items():
            if k not in ("type", "action", "source", "target"):
                record[k] = v

        columns = list(record.keys())
        values = [record[c] for c in columns]
        placeholders = ", ".join(["?" for _ in columns])

        self.conn.execute(
            f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) "
            f"VALUES ({placeholders})",
            values
        )
        count += 1

    return count

def _delete_edges_sync(self, edge_type: str, items: list[dict[str, Any]]) -> int:
    """同步删除边（在事务内执行）。"""
    edge_def = self.ontology.edges.get(edge_type)
    if edge_def is None:
        raise ValueError(f"Unknown edge type: {edge_type}")

    table_name = f"edge_{edge_type}"
    source_node = self.ontology.nodes.get(edge_def.from_)
    target_node = self.ontology.nodes.get(edge_def.to)

    if source_node is None or target_node is None:
        raise ValueError(f"Invalid edge definition: {edge_type}")

    count = 0

    for item in items:
        source = item.get("source", {})
        target = item.get("target", {})

        source_identity = [source.get(f) for f in source_node.identity]
        target_identity = [target.get(f) for f in target_node.identity]

        source_id = compute_deterministic_id(source_identity)
        target_id = compute_deterministic_id(target_identity)
        record_id = compute_deterministic_id([source_id, target_id])

        self.conn.execute(
            f"DELETE FROM {table_name} WHERE __id = ?",
            [record_id]
        )
        count += 1

    return count


def edges_data_by_type(data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按类型分组边数据。"""
    result: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        edge_type = item.get("type")
        if edge_type is None:
            continue
        action = item.get("action", "upsert")
        if action == "upsert":  # 只验证 upsert 操作
            if edge_type not in result:
                result[edge_type] = []
            result[edge_type].append(item)
    return result
```

***

## 三、Phase 2: 增量索引更新

### 3.1 设计思路

当前导入后重建整个节点类型的索引，改为只对变更的记录更新索引。

### 3.2 实现步骤

```
步骤 1: 修改同步导入方法返回 ID 列表
    └── _import_nodes_sync 返回 (结果, upserted_ids, deleted_ids)

步骤 2: 添加 _delete_index_entries 方法
    └── 删除指定记录的索引条目

步骤 3: 添加 _build_index_for_ids 方法
    └── 为指定 ID 的记录构建索引

步骤 4: 添加 _incremental_index_update 方法
    └── 增量更新索引入口

步骤 5: 修改主方法使用增量更新
    └── 替代 rebuild_index
```

### 3.3 代码修改

**新增方法**: `_incremental_index_update`

```python
async def _incremental_index_update(
    self,
    node_type: str,
    upserted_ids: list[int],
    deleted_ids: list[int],
) -> int:
    """增量更新索引。

    Args:
        node_type: 节点类型名称。
        upserted_ids: 新增/更新的记录 ID 列表。
        deleted_ids: 删除的记录 ID 列表。

    Returns:
        更新的索引条目数。
    """
    from duckkb.core.mixins.index import SEARCH_INDEX_TABLE

    node_def = self.ontology.nodes.get(node_type)
    if node_def is None:
        return 0

    table_name = node_def.table
    indexed = 0

    # 1. 删除已删除记录的索引
    if deleted_ids:
        def _delete_entries() -> None:
            placeholders = ", ".join(["?" for _ in deleted_ids])
            self.conn.execute(
                f"DELETE FROM {SEARCH_INDEX_TABLE} "
                f"WHERE source_table = ? AND source_id IN ({placeholders})",
                [table_name] + deleted_ids
            )
        await asyncio.to_thread(_delete_entries)

    # 2. 为新增/更新的记录构建索引
    if upserted_ids:
        indexed = await self._build_index_for_ids(node_type, upserted_ids)

    return indexed

async def _build_index_for_ids(
    self, node_type: str, record_ids: list[int]
) -> int:
    """为指定 ID 的记录构建索引。"""
    node_def = self.ontology.nodes.get(node_type)
    if node_def is None:
        return 0

    table_name = node_def.table

    search_config = getattr(node_def, "search", None)
    if not search_config:
        return 0

    fts_fields: list[str] = getattr(search_config, "full_text", []) or []
    vector_fields: list[str] = getattr(search_config, "vectors", []) or []
    all_fields: set[str] = set(fts_fields) | set(vector_fields)

    if not all_fields:
        return 0

    def _fetch_records() -> list[tuple]:
        placeholders = ", ".join(["?" for _ in record_ids])
        fields_str = ", ".join(all_fields)
        return self.conn.execute(
            f"SELECT __id, {fields_str} FROM {table_name} "
            f"WHERE __id IN ({placeholders})",
            record_ids
        ).fetchall()

    records = await asyncio.to_thread(_fetch_records)

    indexed = 0
    for record in records:
        entries = await self._process_record_for_index(
            record, table_name, all_fields, set(fts_fields), set(vector_fields)
        )
        if entries:
            await asyncio.to_thread(self._insert_index_entries, entries)
            indexed += len(entries)

    return indexed
```

***

## 四、Phase 3: 批量操作优化

### 4.1 设计思路

使用 `executemany` 替代逐条执行，减少数据库交互次数。

### 4.2 代码修改

**重构方法**: `_upsert_nodes_sync`

```python
def _upsert_nodes_sync(self, node_type: str, items: list[dict[str, Any]]) -> int:
    """同步 upsert 节点（批量优化版）。"""
    node_def = self.ontology.nodes.get(node_type)
    if node_def is None:
        raise ValueError(f"Unknown node type: {node_type}")

    if not items:
        return 0

    table_name = node_def.table
    now = datetime.now(UTC)

    # 准备批量数据
    records: list[dict[str, Any]] = []
    for item in items:
        record = {k: v for k, v in item.items() if k not in ("type", "action")}
        identity_values = [record.get(f) for f in node_def.identity]
        record["__id"] = compute_deterministic_id(identity_values)
        record["__created_at"] = now
        record["__updated_at"] = now
        records.append(record)

    # 获取列名
    columns = list(records[0].keys())
    placeholders = ", ".join(["?" for _ in columns])

    # 准备批量参数
    batch_params = [[record[c] for c in columns] for record in records]

    self.conn.executemany(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) "
        f"VALUES ({placeholders})",
        batch_params
    )

    return len(records)
```

***

## 五、测试计划

### 5.1 Phase 1 测试

```python
# tests/test_import.py

import pytest
import tempfile
from pathlib import Path

async def test_edge_reference_validation_in_transaction(engine):
    """测试边引用完整性检查在事务内执行。"""
    # 同一批次中先创建节点再创建边
    yaml_content = """
- type: Document
  doc_uri: "doc-001"
  content: "源文档"
- type: Document
  doc_uri: "doc-002"
  content: "目标文档"
- type: REFERENCES
  source: { doc_uri: "doc-001" }
  target: { doc_uri: "doc-002" }
"""
    # 应该成功，因为节点和边在同一事务中
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        result = await engine.import_knowledge_bundle(temp_path)
        assert result["status"] == "success"
        assert result["nodes"]["upserted"]["Document"] == 2
        assert result["edges"]["upserted"]["REFERENCES"] == 1
    finally:
        Path(temp_path).unlink(missing_ok=True)


async def test_edge_reference_validation_rollback(engine):
    """测试边引用验证失败时回滚事务。"""
    # 尝试创建指向不存在节点的边
    yaml_content = """
- type: Document
  doc_uri: "doc-001"
  content: "源文档"
- type: REFERENCES
  source: { doc_uri: "doc-001" }
  target: { doc_uri: "non-existent" }
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Target.*not found"):
            await engine.import_knowledge_bundle(temp_path)

        # 验证事务已回滚：节点也不应该存在
        # ... 检查数据库 ...
    finally:
        Path(temp_path).unlink(missing_ok=True)
```

***

## 六、实施时间表

| 阶段        | 任务                                  | 文件              |
| --------- | ----------------------------------- | --------------- |
| Phase 1.1 | 添加 `_node_exists_in_transaction` 方法 | import\_.py     |
| Phase 1.2 | 添加 `_validate_edge_references` 方法   | import\_.py     |
| Phase 1.3 | 添加同步导入方法                            | import\_.py     |
| Phase 1.4 | 重构主方法使用单一事务                         | import\_.py     |
| Phase 1.5 | 添加测试用例                              | test\_import.py |
| Phase 2.1 | 添加 `_delete_index_entries` 方法       | import\_.py     |
| Phase 2.2 | 添加 `_build_index_for_ids` 方法        | import\_.py     |
| Phase 2.3 | 添加 `_incremental_index_update` 方法   | import\_.py     |
| Phase 2.4 | 修改主方法使用增量更新                         | import\_.py     |
| Phase 3.1 | 重构批量 upsert 方法                      | import\_.py     |
| Phase 3.2 | 重构批量 delete 方法                      | import\_.py     |

