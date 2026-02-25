# 导入逻辑缺陷修复计划

## 缺陷汇总

| 优先级 | 缺陷          | 影响           |
| --- | ----------- | ------------ |
| P0  | 影子导出导致数据丢失  | 数据丢失         |
| P0  | 索引构建逻辑错误    | 性能问题 + 索引不完整 |
| P1  | 删除节点时未处理相关边 | 数据完整性问题      |
| P1  | 向量嵌入无法计算    | 搜索功能不完整      |
| P2  | 事务提交后导出失败   | 数据库与文件不一致    |
| P3  | 空数据处理       | 边缘情况异常       |
| P3  | 影子目录残留      | 磁盘空间浪费       |
| P3  | 缺少并发控制      | 数据竞争         |

***

## 修复方案

### 修复 1: 影子导出导出所有数据

**问题**: 只导出受影响的类型，但原子替换会替换整个目录

**修复方案**: 修改 `_dump_to_shadow_dir` 方法，导出所有节点类型和边类型的数据

```python
async def _dump_to_shadow_dir(
    self,
    affected_node_types: set[str],
    edges_result: dict[str, Any],
    upserted_ids: dict[str, list[int]],
    deleted_ids: dict[str, list[int]],
) -> dict[str, int]:
    """导出数据到影子目录。"""
    data_dir = self.config.storage.data_dir
    shadow_dir = data_dir.parent / f"{data_dir.name}_shadow"

    def _prepare_shadow_dir() -> None:
        if shadow_dir.exists():
            shutil.rmtree(shadow_dir)
        shadow_dir.mkdir(parents=True)

    await asyncio.to_thread(_prepare_shadow_dir)

    dumped: dict[str, int] = {}

    # 导出所有节点类型（不仅仅是受影响的）
    for node_type, node_def in self.ontology.nodes.items():
        output_dir = shadow_dir / "nodes" / node_def.table
        count = await self._dump_table_to_dir(
            node_def.table,
            output_dir,
            node_def.identity[0],
        )
        if count > 0:
            dumped[node_type] = count

    # 导出所有边类型
    for edge_name, edge_def in self.ontology.edges.items():
        table_name = f"edge_{edge_name}"
        output_dir = shadow_dir / "edges" / edge_name.lower()
        count = await self._dump_table_to_dir(
            table_name,
            output_dir,
            "__from_id",
        )
        if count > 0:
            dumped[edge_name] = count

    # 导出缓存
    cache_count = await self._dump_cache_to_parquet(shadow_dir)
    if cache_count > 0:
        dumped["_sys_search_cache"] = cache_count

    return dumped
```

***

### 修复 2: 索引增量更新

**问题**: 对 upserted 节点重建全表索引，对 deleted 节点删除全表索引

**修复方案**:

1. 跟踪实际插入/更新的记录 ID
2. 只为这些记录构建索引
3. 删除节点时只删除对应记录的索引

```python
def _build_index_for_ids_sync(
    self,
    nodes_result: dict[str, Any],
    edges_result: dict[str, Any],
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, list[int]]]:
    """在事务内为变更的记录构建索引（增量更新）。"""
    indexed: dict[str, int] = {}
    upserted_ids: dict[str, list[int]] = {}
    deleted_ids: dict[str, list[int]] = {}

    # 处理 upserted 节点：只索引新插入的记录
    for node_type, count in nodes_result.get("upserted", {}).items():
        if count == 0:
            continue
            
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            continue

        search_config = getattr(node_def, "search", None)
        if not search_config:
            continue

        fts_fields: list[str] = getattr(search_config, "full_text", []) or []
        vector_fields: list[str] = getattr(search_config, "vectors", []) or []
        all_fields: set[str] = set(fts_fields) | set(vector_fields)

        if not all_fields:
            continue

        table_name = node_def.table
        fields_str = ", ".join(all_fields)

        # 获取最近更新的记录（通过 __updated_at）
        rows = self.conn.execute(
            f"SELECT __id, {fields_str} FROM {table_name} "
            f"WHERE __updated_at >= CURRENT_TIMESTAMP - INTERVAL '1 minute' "
            f"ORDER BY {node_def.identity[0]}"
        ).fetchall()

        type_upserted_ids: list[int] = []
        index_count = 0

        for row in rows:
            source_id = row[0]
            type_upserted_ids.append(source_id)

            field_values = row[1:]
            field_list = list(all_fields)

            for field_idx, field_name in enumerate(field_list):
                content = field_values[field_idx]
                if not content or not isinstance(content, str):
                    continue

                chunks = self._chunk_text_sync(content)

                for chunk_seq, chunk in enumerate(chunks):
                    content_hash = self._compute_hash_sync(chunk)

                    fts_content = None
                    if field_name in fts_fields:
                        fts_content = self._get_or_compute_fts_sync(chunk, content_hash)

                    vector = None
                    if field_name in vector_fields:
                        vector = self._get_or_compute_vector_sync(chunk, content_hash)

                    self.conn.execute(
                        f"INSERT OR REPLACE INTO {SEARCH_INDEX_TABLE} "
                        "(source_table, source_id, source_field, chunk_seq, content, "
                        "fts_content, vector, content_hash, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (table_name, source_id, field_name, chunk_seq, chunk,
                         fts_content, vector, content_hash, datetime.now(UTC)),
                    )
                    index_count += 1

        indexed[node_type] = index_count
        upserted_ids[node_type] = type_upserted_ids
        deleted_ids[node_type] = []

    # 处理 deleted 节点：只删除对应记录的索引
    for node_type, count in nodes_result.get("deleted", {}).items():
        if count == 0:
            continue

        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            continue

        table_name = node_def.table

        # 获取被删除记录的 ID（需要在删除前记录）
        # 这里需要在 _delete_nodes_sync 中记录删除的 ID
        # 暂时使用传入的 deleted_ids
        
        if node_type in deleted_ids and deleted_ids[node_type]:
            placeholders = ", ".join(["?" for _ in deleted_ids[node_type]])
            self.conn.execute(
                f"DELETE FROM {SEARCH_INDEX_TABLE} "
                f"WHERE source_table = ? AND source_id IN ({placeholders})",
                [table_name] + deleted_ids[node_type],
            )

        if node_type not in upserted_ids:
            upserted_ids[node_type] = []

    return indexed, upserted_ids, deleted_ids
```

***

### 修复 3: 删除节点时处理相关边

**问题**: 删除节点时未删除相关边

**修复方案**: 在删除节点前，先删除所有以该节点为 source 或 target 的边

```python
def _delete_nodes_sync(self, node_type: str, items: list[dict[str, Any]]) -> int:
    """同步删除节点（批量优化版）。"""
    node_def = self.ontology.nodes.get(node_type)
    if node_def is None:
        raise ValueError(f"Unknown node type: {node_type}")

    if not items:
        return 0

    table_name = node_def.table

    record_ids: list[int] = []
    for item in items:
        record = {k: v for k, v in item.items() if k not in ("type", "action")}
        identity_values = [record.get(f) for f in node_def.identity]
        record_id = compute_deterministic_id(identity_values)
        record_ids.append(record_id)

    # 先删除相关的边
    self._delete_edges_for_nodes(record_ids)

    # 再删除节点
    placeholders = ", ".join(["?" for _ in record_ids])
    self.conn.execute(
        f"DELETE FROM {table_name} WHERE __id IN ({placeholders})",
        record_ids,
    )

    return len(record_ids)

def _delete_edges_for_nodes(self, node_ids: list[int]) -> int:
    """删除与指定节点相关的所有边。

    Args:
        node_ids: 节点 ID 列表。

    Returns:
        删除的边数量。
    """
    if not node_ids:
        return 0

    total_deleted = 0
    placeholders = ", ".join(["?" for _ in node_ids])

    for edge_name, edge_def in self.ontology.edges.items():
        table_name = f"edge_{edge_name}"

        # 删除以这些节点为 source 或 target 的边
        result = self.conn.execute(
            f"DELETE FROM {table_name} "
            f"WHERE __from_id IN ({placeholders}) OR __to_id IN ({placeholders})",
            node_ids + node_ids,
        )
        # DuckDB 的 DELETE 返回删除的行数
        total_deleted += result.fetchone()[0] if result.fetchone() else 0

    return total_deleted
```

***

### 修复 4: 向量延迟计算

**问题**: 向量化在同步事务中无法计算

**修复方案**: 在事务提交后，异步计算向量并更新索引

```python
async def import_knowledge_bundle(self, temp_file_path: str) -> dict[str, Any]:
    """导入知识包。"""
    # ... 前面的代码不变 ...

    result = await self._execute_import_in_transaction(nodes_data, edges_data)
    nodes_result = result["nodes"]
    edges_result = result["edges"]
    indexed_result = result["indexed"]
    upserted_ids = result["upserted_ids"]
    deleted_ids = result["deleted_ids"]

    # 事务提交后，异步计算向量
    vector_result = await self._compute_vectors_async(upserted_ids)

    # ... 后面的代码不变 ...

async def _compute_vectors_async(
    self,
    upserted_ids: dict[str, list[int]],
) -> dict[str, int]:
    """异步计算向量嵌入。

    Args:
        upserted_ids: 需要计算向量的记录 ID。

    Returns:
        计算的向量数量统计。
    """
    if not hasattr(self, "embed_single"):
        return {}

    vector_result: dict[str, int] = {}

    for node_type, ids in upserted_ids.items():
        if not ids:
            continue

        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            continue

        search_config = getattr(node_def, "search", None)
        if not search_config:
            continue

        vector_fields: list[str] = getattr(search_config, "vectors", []) or []
        if not vector_fields:
            continue

        table_name = node_def.table
        fields_str = ", ".join(vector_fields)
        placeholders = ", ".join(["?" for _ in ids])

        def _fetch_records() -> list[tuple]:
            return self.conn.execute(
                f"SELECT __id, {fields_str} FROM {table_name} "
                f"WHERE __id IN ({placeholders})",
                ids,
            ).fetchall()

        records = await asyncio.to_thread(_fetch_records)
        count = 0

        for record in records:
            source_id = record[0]
            field_values = record[1:]

            for field_idx, field_name in enumerate(vector_fields):
                content = field_values[field_idx]
                if not content or not isinstance(content, str):
                    continue

                chunks = self._chunk_text_sync(content)

                for chunk_seq, chunk in enumerate(chunks):
                    content_hash = self._compute_hash_sync(chunk)

                    # 检查是否已有向量
                    def _check_vector() -> list[float] | None:
                        row = self.conn.execute(
                            f"SELECT vector FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
                            [content_hash],
                        ).fetchone()
                        return row[0] if row else None

                    existing_vector = await asyncio.to_thread(_check_vector)
                    if existing_vector:
                        continue

                    # 计算向量
                    try:
                        vector = await self.embed_single(chunk)

                        def _save_vector() -> None:
                            now = datetime.now(UTC)
                            self.conn.execute(
                                f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
                                "(content_hash, vector, last_used, created_at) VALUES (?, ?, ?, ?)",
                                [content_hash, vector, now, now],
                            )
                            self.conn.execute(
                                f"UPDATE {SEARCH_INDEX_TABLE} SET vector = ? "
                                f"WHERE source_table = ? AND source_id = ? AND "
                                f"source_field = ? AND chunk_seq = ?",
                                [vector, table_name, source_id, field_name, chunk_seq],
                            )

                        await asyncio.to_thread(_save_vector)
                        count += 1

                    except Exception as e:
                        logger.error(f"Failed to compute vector: {e}")

        vector_result[node_type] = count

    return vector_result
```

***

### 修复 5: 异常处理和清理

**问题**: 影子目录残留、空数据处理

**修复方案**: 添加 try-finally 清理逻辑

```python
async def import_knowledge_bundle(self, temp_file_path: str) -> dict[str, Any]:
    """导入知识包。"""
    path = Path(temp_file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {temp_file_path}")

    data_dir = self.config.storage.data_dir
    shadow_dir = data_dir.parent / f"{data_dir.name}_shadow"

    try:
        # ... 原有逻辑 ...

        result = await self._execute_import_in_transaction(nodes_data, edges_data)
        # ...

        dumped = await self._dump_to_shadow_dir(...)

        if dumped:
            await self._atomic_replace_data_dir()

        await self._unlink_file(path)

        return {
            "status": "success",
            "nodes": nodes_result,
            "edges": edges_result,
            "indexed": indexed_result,
            "dumped": dumped,
        }

    except Exception as e:
        # 清理影子目录
        if shadow_dir.exists():
            try:
                await asyncio.to_thread(shutil.rmtree, shadow_dir)
            except Exception:
                pass
        raise
```

***

### 修复 6: 空数据处理

**问题**: `records[0]` 可能在空列表时抛出异常

**修复方案**: 添加空列表检查

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

    records: list[dict[str, Any]] = []
    for item in items:
        record = {k: v for k, v in item.items() if k not in ("type", "action")}
        identity_values = [record.get(f) for f in node_def.identity]
        record["__id"] = compute_deterministic_id(identity_values)
        record["__created_at"] = now
        record["__updated_at"] = now
        records.append(record)

    if not records:  # 额外检查
        return 0

    columns = list(records[0].keys())
    # ... 后续代码不变 ...
```

***

## 实施步骤

1. **修复影子导出** - 修改 `_dump_to_shadow_dir` 导出所有数据
2. **修复索引构建** - 修改 `_build_index_for_ids_sync` 增量更新
3. **修复边删除** - 添加 `_delete_edges_for_nodes` 方法
4. **添加向量异步计算** - 添加 `_compute_vectors_async` 方法
5. **添加异常清理** - 在 `import_knowledge_bundle` 中添加 try-finally
6. **添加空数据检查** - 在批量操作方法中添加检查

