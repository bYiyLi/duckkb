# MCP 工具集设计计划：更新与删除工具

## 背景

DuckKB 当前提供 6 个 MCP 工具：

* `check_health` - 健康检查

* `sync_knowledge_base` - 同步知识库

* `get_schema_info` - 获取模式信息

* `smart_search` - 智能搜索

* `query_raw_sql` - 执行只读 SQL

* `validate_and_import` - 验证并导入数据

缺少更新和删除能力，本计划设计这两个工具。

## 数据流分析

```
data/{table}.jsonl  ──sync──>  DuckDB (_sys_search, _sys_cache)
     ↑
     └── 源数据文件（JSONL 格式，每行一个 JSON 对象）
```

关键约束：

* 源数据存储在 `data/` 目录的 JSONL 文件中

* 每条记录必须有 `id` 字段作为唯一标识

* 数据库表 `_sys_search` 的主键是 `(ref_id, source_table, source_field)`

* 同步时会删除旧数据并重新插入

***

## 设计方案

### 核心思路

**更新能力**：复用 `validate_and_import`，改为 upsert 语义

* 表不存在 → 创建新表

* 表存在 + 相同 `id` → 更新记录

* 表存在 + 新 `id` → 新增记录

**删除能力**：新增独立的 `delete_records` 工具

***

### 1. 修改 `validate_and_import` 为 upsert 语义

**当前行为**：追加数据到现有文件末尾

**新行为**：基于 `id` 进行 upsert

**处理流程**：

1. 验证临时文件格式和必需字段（`id`）
2. 如果目标表不存在：

   * 直接移动临时文件到 `data/{table_name}.jsonl`
3. 如果目标表存在：

   * 读取现有数据，构建 `id → record` 映射

   * 合并新数据（相同 `id` 覆盖，新 `id` 追加）

   * 原子写入合并后的数据
4. 触发知识库同步
5. 返回操作结果

**返回值**：

```json
{
  "status": "success",
  "table_name": "articles",
  "total_records": 105,
  "updated_count": 3,
  "inserted_count": 2,
  "message": "Upserted 5 records to articles (3 updated, 2 inserted)"
}
```

***

### 2. 新增删除工具：`delete_records`

**功能**：删除指定表中的记录

**参数**：

| 参数           | 类型         | 必填 | 说明           |
| ------------ | ---------- | -- | ------------ |
| `table_name` | str        | 是  | 目标表名         |
| `record_ids` | list\[str] | 是  | 要删除的记录 ID 列表 |

**处理流程**：

1. 验证表是否存在
2. 读取现有数据，过滤掉要删除的记录
3. 原子写入更新后的数据
4. 从 `_sys_search` 表删除对应记录
5. 返回删除结果统计

**返回值**：

```json
{
  "status": "success",
  "deleted_count": 3,
  "not_found_ids": ["id1"],
  "remaining_count": 97,
  "message": "Deleted 3 records from articles"
}
```

**异常情况**：

* 表不存在 → 返回错误

* 删除后表为空 → 保留空文件（或可选删除文件）

***

## 实现方案

### 文件结构

```
src/duckkb/
├── engine/
│   ├── importer.py     # 修改：改为 upsert 语义
│   └── deleter.py      # 新增：删除逻辑
└── mcp/
    └── server.py       # 修改：添加删除工具
```

### 核心函数

#### `engine/importer.py`（修改）

```python
async def validate_and_import(table_name: str, temp_file_path: Path) -> str:
    """
    验证临时文件并将其导入到知识库数据目录（upsert 语义）。

    该函数执行完整的导入流程：
    1. 验证 JSONL 文件格式和必需字段
    2. 如果表存在，基于 id 进行 upsert（更新已存在，插入新记录）
    3. 如果表不存在，创建新表
    4. 使用原子写入确保数据完整性
    5. 触发知识库同步

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
        temp_file_path: 临时 JSONL 文件的路径。

    Returns:
        操作结果消息，包含更新/插入统计。
    """
```

#### `engine/deleter.py`（新增）

```python
async def delete_records(table_name: str, record_ids: list[str]) -> dict:
    """
    删除指定表中的记录。

    Args:
        table_name: 目标表名。
        record_ids: 要删除的记录 ID 列表。

    Returns:
        包含删除统计的字典。
    """
```

***

## 安全考虑

1. **参数验证**：所有输入必须严格验证
2. **原子操作**：文件写入使用临时文件 + 重命名模式
3. **事务保护**：数据库操作使用事务
4. **日志记录**：所有写操作记录日志

***

## 实现步骤

1. 修改 `engine/importer.py`，实现 upsert 语义
2. 创建 `engine/deleter.py`，实现 `delete_records` 函数
3. 在 `mcp/server.py` 中添加 `delete_records` 工具
4. 运行 ruff 格式化
5. 测试验证

