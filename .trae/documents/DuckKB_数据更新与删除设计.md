# DuckKB 数据更新与删除设计（修订版）

## 一、设计思路

### 核心原则

1. **更新复用导入能力**：修改 `validate_and_import` 支持 upsert 模式
2. **删除支持多种键**：支持按 `id` 或业务唯一键删除

### 数据模型回顾

```python
# _sys_search 表结构
CREATE TABLE _sys_search (
    ref_id VARCHAR,           # 记录 ID（来自 JSONL 的 id 字段）
    source_table VARCHAR,     # 表名
    source_field VARCHAR,     # 字段名
    segmented_text TEXT,      # 分词文本
    embedding_id VARCHAR,     # 向量缓存 ID
    metadata JSON,            # 原始记录 JSON
    priority_weight FLOAT,    # 权重
    PRIMARY KEY (ref_id, source_table, source_field)
);
```

***

## 二、更新设计：复用导入能力

### 2.1 修改 validate\_and\_import 支持 upsert

**当前行为**：只能追加

```python
# 当前代码 (indexer.py)
final_content = b""
if target_path.exists():
    final_content = await asyncio.to_thread(target_path.read_bytes)
    if final_content and not final_content.endswith(b"\n"):
        final_content += b"\n"
new_content = await asyncio.to_thread(temp_file_path.read_bytes)
final_content += new_content  # 永远追加
```

**新行为**：支持 upsert 模式

```python
@mcp.tool()
async def validate_and_import(
    table_name: str, 
    temp_file_path: str,
    mode: str = "append"  # 新增参数：append | upsert
) -> str:
    """
    Validate temp file and import to data dir.
    
    Args:
        table_name: Target table name (without .jsonl)
        temp_file_path: Absolute path to temporary JSONL file
        mode: Import mode
            - "append": Always append (default, current behavior)
            - "upsert": Update existing records by id, append new ones
    
    Returns:
        Import result with counts
    """
```

### 2.2 upsert 模式实现

```python
# engine/indexer.py 修改

async def validate_and_import(
    table_name: str, 
    temp_file_path: Path,
    mode: str = "append"
) -> str:
    """Validate and import with optional upsert mode."""
    
    # ... 验证逻辑不变 ...
    
    if mode == "upsert":
        result = await _upsert_records(table_name, temp_file_path)
    else:
        result = await _append_records(table_name, temp_file_path)
    
    await sync_knowledge_base(kb_path)
    return result


async def _upsert_records(table_name: str, temp_file_path: Path) -> str:
    """Upsert records: update by id, append new ones."""
    kb_path = AppContext.get().kb_path
    target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"
    
    # 读取新记录
    new_content = await asyncio.to_thread(temp_file_path.read_bytes)
    new_lines = new_content.splitlines()
    new_records = {}
    for line in new_lines:
        if not line.strip():
            continue
        record = orjson.loads(line)
        record_id = str(record.get("id", ""))
        if record_id:
            new_records[record_id] = record
    
    # 读取现有记录
    existing_records = {}
    if target_path.exists():
        existing_content = await asyncio.to_thread(target_path.read_bytes)
        for line in existing_content.splitlines():
            if not line.strip():
                continue
            record = orjson.loads(line)
            record_id = str(record.get("id", ""))
            if record_id:
                existing_records[record_id] = record
    
    # 合并：新记录覆盖旧记录
    updated_count = 0
    appended_count = 0
    
    for record_id, record in new_records.items():
        if record_id in existing_records:
            updated_count += 1
        else:
            appended_count += 1
        existing_records[record_id] = record
    
    # 原子化写入
    final_lines = [orjson.dumps(r) for r in existing_records.values()]
    final_content = b"\n".join(final_lines) + b"\n"
    
    staging_path = target_path.with_suffix(".jsonl.staging")
    await asyncio.to_thread(staging_path.write_bytes, final_content)
    staging_path.replace(target_path)
    
    # 清理临时文件
    try:
        temp_file_path.unlink()
    except OSError:
        pass
    
    return f"Upserted {updated_count + appended_count} records (updated: {updated_count}, appended: {appended_count})"
```

***

## 三、删除设计：支持多种键

### 3.1 接口设计

```python
@mcp.tool()
async def delete_records(
    table_name: str,
    ids: list[str] | None = None,
    key_field: str | None = None,
    key_values: list[str] | None = None
) -> str:
    """
    Delete records from a table by id or business key.
    
    Args:
        table_name: Target table name (without .jsonl)
        ids: List of record IDs to delete (use 'id' field)
        key_field: Business key field name (e.g., 'sku', 'email')
        key_values: List of business key values to delete
        
    Note: Either 'ids' or ('key_field' + 'key_values') must be provided.
    
    Returns:
        JSON string with deletion count
        
    Examples:
        # Delete by id
        delete_records("products", ids=["p001", "p002"])
        
        # Delete by business key (sku)
        delete_records("products", key_field="sku", key_values=["SKU-001", "SKU-002"])
    """
```

### 3.2 实现代码

```python
# engine/indexer.py 新增

async def delete_records(
    table_name: str,
    ids: list[str] | None = None,
    key_field: str | None = None,
    key_values: list[str] | None = None
) -> dict:
    """
    Delete records by id or business key.
    """
    # 参数验证
    if ids is None and (key_field is None or key_values is None):
        raise ValueError("Either 'ids' or ('key_field' + 'key_values') must be provided")
    
    if ids is not None and key_field is not None:
        raise ValueError("Cannot use both 'ids' and 'key_field' at the same time")
    
    if ids is not None and len(ids) == 0:
        raise ValueError("ids cannot be empty")
    
    if key_values is not None and len(key_values) == 0:
        raise ValueError("key_values cannot be empty")
    
    if ids is not None and len(ids) > 100:
        raise ValueError("Maximum 100 records can be deleted per call")
    
    if key_values is not None and len(key_values) > 100:
        raise ValueError("Maximum 100 records can be deleted per call")
    
    kb_path = AppContext.get().kb_path
    file_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"
    
    if not file_path.exists():
        raise FileNotFoundError(f"Table '{table_name}' does not exist")
    
    # 确定要删除的键集合
    if ids is not None:
        delete_keys = set(str(id) for id in ids)
        delete_by_id = True
    else:
        delete_keys = set(str(v) for v in key_values)
        delete_by_id = False
        key_field = key_field  # type: ignore
    
    # 从索引和文件中删除
    deleted_count = await asyncio.to_thread(
        _delete_records_impl,
        table_name,
        file_path,
        delete_keys,
        delete_by_id,
        key_field if not delete_by_id else None
    )
    
    # 更新同步状态
    state_file = kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
    if state_file.exists():
        state = orjson.loads(state_file.read_bytes())
        if table_name in state:
            del state[table_name]
            state_file.write_bytes(orjson.dumps(state))
    
    return {"deleted_count": deleted_count, "status": "success"}


def _delete_records_impl(
    table_name: str,
    file_path: Path,
    delete_keys: set[str],
    delete_by_id: bool,
    key_field: str | None
) -> int:
    """Execute deletion from both index and file."""
    
    # 1. 从索引删除
    with get_db(read_only=False) as conn:
        if delete_by_id:
            placeholders = ",".join(["?"] * len(delete_keys))
            result = conn.execute(
                f"DELETE FROM {SYS_SEARCH_TABLE} "
                f"WHERE source_table = ? AND ref_id IN ({placeholders})",
                [table_name] + list(delete_keys)
            )
        else:
            # 按业务键删除：需要先查询匹配的 ref_id
            # 从 metadata JSON 中提取业务键值
            rows = conn.execute(
                f"SELECT ref_id, metadata FROM {SYS_SEARCH_TABLE} "
                f"WHERE source_table = ?",
                [table_name]
            ).fetchall()
            
            ref_ids_to_delete = []
            for ref_id, metadata_json in rows:
                try:
                    metadata = orjson.loads(metadata_json)
                    if str(metadata.get(key_field, "")) in delete_keys:
                        ref_ids_to_delete.append(ref_id)
                except (orjson.JSONDecodeError, TypeError):
                    continue
            
            if ref_ids_to_delete:
                placeholders = ",".join(["?"] * len(ref_ids_to_delete))
                result = conn.execute(
                    f"DELETE FROM {SYS_SEARCH_TABLE} "
                    f"WHERE source_table = ? AND ref_id IN ({placeholders})",
                    [table_name] + ref_ids_to_delete
                )
                delete_keys = set(ref_ids_to_delete)  # 更新用于文件删除
            else:
                return 0
        
        deleted_from_index = result.fetchone()[0] if hasattr(result, 'fetchone') else 0
    
    # 2. 从文件删除
    content = file_path.read_bytes()
    lines = content.splitlines()
    
    kept_lines = []
    deleted_from_file = 0
    
    for line in lines:
        if not line.strip():
            continue
        record = orjson.loads(line)
        
        if delete_by_id:
            should_delete = str(record.get("id", "")) in delete_keys
        else:
            should_delete = str(record.get(key_field, "")) in delete_keys
        
        if should_delete:
            deleted_from_file += 1
        else:
            kept_lines.append(line)
    
    # 原子化写入
    new_content = b"\n".join(kept_lines) + (b"\n" if kept_lines else b"")
    staging_path = file_path.with_suffix(".jsonl.staging")
    staging_path.write_bytes(new_content)
    staging_path.replace(file_path)
    
    return deleted_from_file
```

***

## 四、drop\_table 保持不变

```python
@mcp.tool()
async def drop_table(table_name: str) -> str:
    """
    Drop a table and all its indexed data.
    
    Args:
        table_name: Table name to drop (without .jsonl)
        
    Returns:
        JSON string with deleted record count
    """
```

***

## 五、MCP Server 集成

```python
# mcp/server.py 修改

@mcp.tool()
async def validate_and_import(
    table_name: str, 
    temp_file_path: str,
    mode: str = "append"
) -> str:
    """
    Validate temp file and import to data dir.
    
    Args:
        table_name: Target table name (without .jsonl)
        temp_file_path: Absolute path to temporary JSONL file
        mode: Import mode
            - "append": Always append (default)
            - "upsert": Update existing records by id, append new ones
    
    Returns:
        Import result message
    """
    return await _validate(table_name, Path(temp_file_path), mode)


@mcp.tool()
async def delete_records(
    table_name: str,
    ids: list[str] | None = None,
    key_field: str | None = None,
    key_values: list[str] | None = None
) -> str:
    """
    Delete records from a table by id or business key.
    
    Args:
        table_name: Target table name (without .jsonl)
        ids: List of record IDs to delete
        key_field: Business key field name (e.g., 'sku', 'email')
        key_values: List of business key values to delete
        
    Note: Either 'ids' or ('key_field' + 'key_values') must be provided.
    
    Returns:
        JSON string with deletion count
    """
    from duckkb.engine.indexer import delete_records as _delete
    result = await _delete(table_name, ids, key_field, key_values)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def drop_table(table_name: str) -> str:
    """
    Drop a table and all its indexed data.
    
    Args:
        table_name: Table name to drop (without .jsonl)
        
    Returns:
        JSON string with deleted record count
    """
    from duckkb.engine.indexer import drop_table as _drop
    result = await _drop(table_name)
    return json.dumps(result, ensure_ascii=False)
```

***

## 六、使用示例

### 更新（upsert 模式）

```python
# 导入时使用 upsert 模式
# 如果 id 已存在则更新，否则新增
await validate_and_import(
    table_name="products",
    temp_file_path="/tmp/new_products.jsonl",
    mode="upsert"
)

# new_products.jsonl 内容：
# {"id": "p001", "name": "Updated Product", "price": 99.99}  # 更新
# {"id": "p999", "name": "New Product", "price": 49.99}      # 新增
```

### 删除（按 id）

```python
# 按 id 删除
await delete_records(
    table_name="products",
    ids=["p001", "p002", "p003"]
)
```

### 删除（按业务键）

```python
# 按 sku 删除
await delete_records(
    table_name="products",
    key_field="sku",
    key_values=["SKU-001", "SKU-002"]
)

# 按 email 删除
await delete_records(
    table_name="users",
    key_field="email",
    key_values=["old@example.com", "deleted@example.com"]
)
```

### 删除整表

```python
# 删除整张表
await drop_table("products")
```

***

## 七、变更总结

| 变更项                   | 说明                                  |
| --------------------- | ----------------------------------- |
| `validate_and_import` | 新增 `mode` 参数，支持 `append` 和 `upsert` |
| `delete_records`      | 新增工具，支持按 id 或业务键删除                  |
| `drop_table`          | 新增工具，删除整张表                          |

**设计优势**：

1. 更新复用现有导入能力，代码复用度高
2. 删除支持多种键，灵活性更强
3. API 简洁，易于理解和使用

