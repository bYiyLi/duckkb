# validate\_and\_import 工具设计（数据驱动版）

## 一、需求分析

这是知识库的修改工具，需要：

1. **文件格式设计**：数据本身包含表名信息
2. **自动路由**：根据数据内容判断入库哪个表
3. **支持多表**：一个文件可以包含多个表的数据
4. **原子操作**：验证通过后批量导入

## 二、文件格式设计

### 2.1 JSONL 文件格式

每行是一个 JSON 对象，包含元数据字段：

```jsonl
{"__table": "documents", "__op": "upsert", "id": "doc-001", "title": "文档标题", "content": "内容..."}
{"__table": "documents", "__op": "upsert", "id": "doc-002", "title": "文档标题2", "content": "内容..."}
{"__table": "chunks", "__op": "upsert", "id": "chunk-001", "doc_id": "doc-001", "text": "片段..."}
{"__table": "documents", "__op": "delete", "id": "doc-003"}
```

### 2.2 元数据字段

| 字段        | 类型     | 必填 | 说明                         |
| --------- | ------ | -- | -------------------------- |
| `__table` | string | 是  | 目标表名（节点类型对应的表名）            |
| `__op`    | string | 否  | 操作类型：`upsert`（默认）、`delete` |
| `__id`    | int    | 否  | 记录 ID（缺失时自动生成）             |

### 2.3 操作类型

| 操作       | 说明        | 必需字段        |
| -------- | --------- | ----------- |
| `upsert` | 插入或更新（默认） | identity 字段 |
| `delete` | 删除记录      | identity 字段 |

## 三、导入逻辑设计

### 3.1 处理流程

```
┌─────────────────────────────────────────────────────────────┐
│                  validate_and_import 流程                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 验证文件存在                                             │
│     └── 检查 temp_file_path 是否存在                         │
│                                                             │
│  2. 解析 JSONL 文件                                          │
│     └── 逐行读取，解析为记录列表                               │
│                                                             │
│  3. 分组记录                                                 │
│     └── 按 (__table, __op) 分组                              │
│                                                             │
│  4. 验证每组记录                                             │
│     ├── 检查 __table 是否在 ontology 中定义                   │
│     ├── 检查 identity 字段是否存在                            │
│     └── 检查 required 字段是否存在                            │
│                                                             │
│  5. 批量操作（按表分组）                                       │
│     ├── upsert: INSERT OR REPLACE                           │
│     └── delete: DELETE WHERE identity = ?                   │
│                                                             │
│  6. 触发索引构建（受影响的表）                                  │
│     └── 对每个受影响的 node_type 调用 rebuild_index           │
│                                                             │
│  7. 持久化导出（受影响的表）                                    │
│     └── 对每个受影响的 node_type 调用 dump_node               │
│                                                             │
│  8. 清理临时文件                                             │
│     └── 删除 temp_file_path                                  │
│                                                             │
│  9. 返回结果                                                 │
│     └── {"status": "success", "tables": {...}, ...}         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 函数签名

````python
@mcp.tool()
async def validate_and_import(temp_file_path: str) -> str:
    """验证并导入数据文件。

    从临时 JSONL 文件导入数据到知识库。文件格式：
    - 每行一个 JSON 对象
    - 必须包含 __table 字段指定目标表
    - 可选 __op 字段指定操作类型（upsert/delete）

    支持的操作：
    - upsert: 插入或更新（默认）
    - delete: 删除记录

    导入后自动触发索引构建和数据持久化。

    Args:
        temp_file_path: 临时 JSONL 文件的绝对路径。

    Returns:
        JSON 格式的操作结果，包含每个表的导入统计。

    Raises:
        ValueError: 验证失败时抛出。
        FileNotFoundError: 临时文件不存在时抛出。

    Example:
        文件内容：
        ```jsonl
        {"__table": "documents", "id": "doc-001", "title": "标题", "content": "内容"}
        {"__table": "documents", "__op": "delete", "id": "doc-002"}
        ```
    """
````

### 3.3 核心实现

```python
@mcp.tool()
async def validate_and_import(temp_file_path: str) -> str:
    """验证并导入数据文件。"""
    import json
    import orjson
    from pathlib import Path
    from collections import defaultdict
    from duckkb.constants import MAX_ERROR_FEEDBACK
    from duckkb.utils.file_ops import read_file_lines, unlink
    
    path = Path(temp_file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {temp_file_path}")
    
    # 解析 JSONL 文件
    errors = []
    records_by_table: dict[str, dict[str, list]] = defaultdict(
        lambda: {"upsert": [], "delete": []}
    )
    
    line_num = 0
    async for line in read_file_lines(path):
        line_num += 1
        if not line.strip():
            continue
        
        try:
            record = orjson.loads(line)
            
            if not isinstance(record, dict):
                errors.append(f"Line {line_num}: Record must be a JSON object")
                continue
            
            # 检查 __table 字段
            table_name = record.get("__table")
            if not table_name:
                errors.append(f"Line {line_num}: Missing __table field")
                continue
            
            # 检查表是否在 ontology 中定义
            node_type = self._get_node_type_by_table(table_name)
            if node_type is None:
                errors.append(f"Line {line_num}: Unknown table: {table_name}")
                continue
            
            # 获取操作类型
            op = record.pop("__op", "upsert")
            if op not in ("upsert", "delete"):
                errors.append(f"Line {line_num}: Invalid __op: {op}")
                continue
            
            # 移除元数据字段
            record.pop("__table", None)
            
            # 验证 identity 字段
            node_def = self.ontology.nodes[node_type]
            for field in node_def.identity:
                if field not in record:
                    errors.append(f"Line {line_num}: Missing identity field: {field}")
            
            if len(errors) >= MAX_ERROR_FEEDBACK:
                break
            
            records_by_table[table_name][op].append((node_type, record))
            
        except orjson.JSONDecodeError as e:
            errors.append(f"Line {line_num}: Invalid JSON: {e}")
    
    if errors:
        raise ValueError(
            f"Validation failed with {len(errors)} errors:\n" +
            "\n".join(errors[:MAX_ERROR_FEEDBACK])
        )
    
    # 批量操作
    results = {}
    affected_node_types = set()
    
    for table_name, ops in records_by_table.items():
        table_results = {"upserted": 0, "deleted": 0}
        
        # Upsert 操作
        if ops["upsert"]:
            for node_type, record in ops["upsert"]:
                affected_node_types.add(node_type)
            upserted = await self._upsert_records(table_name, ops["upsert"])
            table_results["upserted"] = upserted
        
        # Delete 操作
        if ops["delete"]:
            for node_type, record in ops["delete"]:
                affected_node_types.add(node_type)
            deleted = await self._delete_records(table_name, ops["delete"])
            table_results["deleted"] = deleted
        
        results[table_name] = table_results
    
    # 触发索引构建
    indexed = {}
    for node_type in affected_node_types:
        indexed[node_type] = await self.rebuild_index(node_type)
    
    # 持久化导出
    dumped = {}
    for node_type in affected_node_types:
        dumped[node_type] = await self.dump_node(node_type)
    
    # 清理临时文件
    await unlink(path)
    
    return json.dumps({
        "status": "success",
        "tables": results,
        "indexed": indexed,
        "dumped": dumped,
    }, ensure_ascii=False)

def _get_node_type_by_table(self, table_name: str) -> str | None:
    """根据表名获取节点类型。
    
    Args:
        table_name: 表名。
    
    Returns:
        节点类型名称，未找到时返回 None。
    """
    for node_type, node_def in self.ontology.nodes.items():
        if node_def.table == table_name:
            return node_type
    return None

async def _upsert_records(
    self,
    table_name: str,
    records: list[tuple[str, dict]],
) -> int:
    """批量 upsert 记录。
    
    Args:
        table_name: 目标表名。
        records: 记录列表，每项为 (node_type, record)。
    
    Returns:
        导入的记录数。
    """
    import asyncio
    from datetime import datetime
    from duckkb.core.mixins.storage import compute_deterministic_id
    
    def _execute() -> int:
        try:
            self.conn.begin()
            
            now = datetime.now()
            count = 0
            
            for node_type, record in records:
                node_def = self.ontology.nodes[node_type]
                
                # 生成确定性 ID
                if "__id" not in record:
                    identity_values = [record.get(f) for f in node_def.identity]
                    record["__id"] = compute_deterministic_id(identity_values)
                
                # 设置时间戳
                if "__created_at" not in record:
                    record["__created_at"] = now
                record["__updated_at"] = now
                
                # 构建插入语句
                columns = list(record.keys())
                values = [record[c] for c in columns]
                placeholders = ", ".join(["?" for _ in columns])
                
                self.conn.execute(
                    f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) "
                    f"VALUES ({placeholders})",
                    values
                )
                count += 1
            
            self.conn.commit()
            return count
            
        except Exception as e:
            self.conn.rollback()
            raise
    
    return await asyncio.to_thread(_execute)

async def _delete_records(
    self,
    table_name: str,
    records: list[tuple[str, dict]],
) -> int:
    """批量删除记录。
    
    Args:
        table_name: 目标表名。
        records: 记录列表，每项为 (node_type, record)。
    
    Returns:
        删除的记录数。
    """
    import asyncio
    from duckkb.core.mixins.storage import compute_deterministic_id
    
    def _execute() -> int:
        try:
            self.conn.begin()
            count = 0
            
            for node_type, record in records:
                node_def = self.ontology.nodes[node_type]
                
                # 计算 ID
                identity_values = [record.get(f) for f in node_def.identity]
                record_id = compute_deterministic_id(identity_values)
                
                self.conn.execute(
                    f"DELETE FROM {table_name} WHERE __id = ?",
                    [record_id]
                )
                count += 1
            
            self.conn.commit()
            return count
            
        except Exception as e:
            self.conn.rollback()
            raise
    
    return await asyncio.to_thread(_execute)
```

## 四、使用示例

### 4.1 文件内容示例

```jsonl
{"__table": "documents", "id": "doc-001", "title": "DuckDB 入门", "content": "DuckDB 是一个嵌入式分析数据库..."}
{"__table": "documents", "id": "doc-002", "title": "向量检索原理", "content": "向量检索基于相似度计算..."}
{"__table": "documents", "__op": "delete", "id": "doc-old"}
{"__table": "chunks", "id": "chunk-001", "doc_id": "doc-001", "text": "DuckDB 是一个嵌入式分析数据库"}
```

### 4.2 返回结果示例

```json
{
  "status": "success",
  "tables": {
    "documents": {"upserted": 2, "deleted": 1},
    "chunks": {"upserted": 1, "deleted": 0}
  },
  "indexed": {"Document": 3, "Chunk": 1},
  "dumped": {"Document": 2, "Chunk": 1}
}
```

## 五、实现步骤

| 步骤 | 任务                                         |
| -- | ------------------------------------------ |
| 1  | 在 DuckMCP 中添加 `_get_node_type_by_table` 方法 |
| 2  | 在 DuckMCP 中添加 `_upsert_records` 方法         |
| 3  | 在 DuckMCP 中添加 `_delete_records` 方法         |
| 4  | 在 DuckMCP 中添加 `validate_and_import` 工具     |
| 5  | 运行测试验证                                     |

