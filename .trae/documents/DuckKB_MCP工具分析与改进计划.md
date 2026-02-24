# DuckKB MCP 工具分析与改进计划

## 一、当前工具清单

| 工具名称                    | 功能           | 生命周期阶段 |
| ----------------------- | ------------ | ------ |
| `check_health()`        | 健康检查         | 维护     |
| `sync_knowledge_base()` | 同步知识库        | 索引     |
| `get_schema_info()`     | 获取 Schema 信息 | 查询     |
| `smart_search()`        | 混合搜索         | 查询     |
| `query_raw_sql()`       | 原始 SQL 查询    | 查询     |
| `validate_and_import()` | 验证并导入        | 导入     |

***

## 二、AI Agent 知识库生命周期分析

### 完整生命周期阶段

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AI Agent 知识库生命周期                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ 1.初始化  │──▶│ 2.导入    │──▶│ 3.索引    │──▶│ 4.查询    │            │
│  │ 创建KB   │   │ 数据导入  │   │ 向量化   │   │ 搜索检索  │            │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘            │
│       │              │              │              │                   │
│       │              │              │              │                   │
│       ▼              ▼              ▼              ▼                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ 8.销毁    │◀──│ 7.备份    │◀──│ 6.维护    │◀──│ 5.更新    │            │
│  │ 删除KB   │   │ 备份恢复  │   │ 监控清理  │   │ 增删改   │            │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 各阶段详细需求

| 阶段         | 需求描述       | 当前支持  | 缺失能力                             |
| ---------- | ---------- | ----- | -------------------------------- |
| **1. 初始化** | 创建知识库、配置设置 | ❌     | `init_kb`, `configure`           |
| **2. 导入**  | 数据导入、格式验证  | ✅     | -                                |
| **3. 索引**  | 向量化、建立索引   | ✅     | -                                |
| **4. 查询**  | 搜索、检索      | ✅     | -                                |
| **5. 更新**  | 数据更新、增量同步  | ⚠️ 部分 | `update_record`, `delete_record` |
| **6. 维护**  | 缓存清理、状态监控  | ⚠️ 部分 | `get_stats`, `get_sync_status`   |
| **7. 备份**  | 数据备份、恢复    | ❌     | `export_data`, `import_backup`   |
| **8. 销毁**  | 删除表、删除知识库  | ❌     | `drop_table`, `clear_cache`      |

***

## 三、缺陷详细分析

### 3.1 初始化阶段缺陷

**问题**：没有知识库初始化工具

```python
# 当前状态：AppContext 需要预先初始化
# server.py 启动时依赖外部初始化
try:
    asyncio.run(init_schema())
except Exception as e:
    logger.error(f"Failed to initialize schema: {e}")
```

**影响**：

* Agent 无法动态创建新的知识库实例

* 无法切换不同的知识库路径

* 初始化失败时无法从 Agent 侧恢复

**建议新增工具**：

```python
@mcp.tool()
async def init_knowledge_base(kb_path: str) -> str:
    """Initialize or switch to a knowledge base."""
    
@mcp.tool()
async def get_config() -> str:
    """Get current knowledge base configuration."""
```

***

### 3.2 更新阶段缺陷

**问题**：只有追加式导入，缺少更新和删除能力

```python
# validate_and_import 只能追加
final_content += new_content  # 永远是追加操作
```

**影响**：

* 无法更新已存在的记录

* 无法删除过期或错误的数据

* 数据只能无限增长

**建议新增工具**：

```python
@mcp.tool()
async def delete_records(table_name: str, ref_ids: list[str]) -> str:
    """Delete specific records from a table."""
    
@mcp.tool()
async def drop_table(table_name: str) -> str:
    """Drop a table and all its data."""
    
@mcp.tool()
async def update_record(table_name: str, ref_id: str, record: dict) -> str:
    """Update a specific record."""
```

***

### 3.3 维护阶段缺陷

**问题**：`check_health()` 信息不够详细，缺少统计信息

```python
# 当前 check_health 返回的信息
status = {
    "status": "healthy",
    "kb_path": str(settings.KB_PATH),
    "db_exists": db_path.exists(),
    "data_files_count": len(data_files),
    "data_files": [f.stem for f in data_files],
}
```

**缺失信息**：

* 总记录数

* 向量缓存大小

* 最后同步时间

* 索引状态

* 磁盘使用情况

**建议改进**：

```python
@mcp.tool()
async def get_stats() -> str:
    """Get detailed knowledge base statistics."""
    # 返回：记录数、缓存大小、索引状态、磁盘使用等
    
@mcp.tool()
async def get_sync_status() -> str:
    """Get synchronization status for all tables."""
    # 返回：各表的同步状态、最后修改时间等
```

***

### 3.4 查询阶段缺陷

**问题**：缺少运行时统计信息和快速表列表查询

**说明**：

* `get_schema_info()` 已提供表结构元数据（Schema 定义、ER 图）

* 但缺少运行时统计信息（记录数、缓存大小、磁盘使用等）

* 缺少快速获取表列表和记录数的便捷方法

**缺失信息**：

* 各表的记录数（运行时统计）

* 向量缓存大小和使用情况

* 最后同步时间

* 磁盘使用情况

**建议新增工具**：

```python
@mcp.tool()
async def list_tables() -> str:
    """List all tables with record counts (runtime stats)."""
    # 快速获取表列表和记录数，无需解析完整 schema
    
@mcp.tool()
async def get_stats() -> str:
    """Get detailed runtime statistics."""
    # 返回：记录数、缓存大小、索引状态、磁盘使用等
    
@mcp.tool()
async def get_sync_status() -> str:
    """Get synchronization status for all tables."""
    # 返回：各表的同步状态、最后修改时间等
```

***

### 3.5 错误处理缺陷

**问题**：错误信息不够结构化

```python
# 当前错误返回方式
return json.dumps(results, ensure_ascii=False, default=str)
# 或直接抛出异常
```

**建议改进**：

```python
# 定义标准错误响应格式
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Missing required field 'id'",
        "details": {...}
    }
}
```

***

### 3.6 安全性缺陷

**问题**：`query_raw_sql` 存在潜在风险

```python
# 当前禁止关键字列表
forbidden = ["ATTACH", "DETACH", "PRAGMA", "DELETE", ...]
```

**潜在风险**：

* SQL 注入（虽然禁止了关键字，但复杂的注入可能绕过）

* 信息泄露（可以查询系统表）

* 资源耗尽（复杂查询可能导致内存溢出）

**建议改进**：

```python
# 添加查询超时
@mcp.tool()
async def query_raw_sql(sql: str, timeout: int = 30) -> str:
    """Execute raw SQL with timeout."""
    
# 添加查询白名单模式
@mcp.tool()
async def query_safe(table_name: str, filters: dict, limit: int) -> str:
    """Safe query with structured filters."""
```

***

## 四、AI Agent 使用用例分析

### 用例 1：新建知识库并导入数据

```
Agent 操作流程：
1. init_knowledge_base(kb_path)     ❌ 缺失
2. configure(embedding_model)       ❌ 缺失
3. validate_and_import(table, file) ✅ 已有
4. sync_knowledge_base()            ✅ 已有
5. check_health()                   ✅ 已有
```

### 用例 2：查询知识库

```
Agent 操作流程：
1. get_schema_info()                ✅ 已有（表结构、ER图）
2. smart_search(query)              ✅ 已有
3. query_raw_sql(sql)               ✅ 已有
4. list_tables()                    ⚠️ 可通过 get_schema_info 间接获取
5. get_stats()                      ❌ 缺失（运行时统计）
```

### 用例 3：更新知识库

```
Agent 操作流程：
1. get_sync_status()                ❌ 缺失
2. validate_and_import(table, file) ✅ 已有（仅追加）
3. delete_records(table, ids)       ❌ 缺失
4. update_record(table, id, data)   ❌ 缺失
5. sync_knowledge_base()            ✅ 已有
```

### 用例 4：维护知识库

```
Agent 操作流程：
1. get_stats()                      ❌ 缺失
2. check_health()                   ✅ 已有
3. clean_cache()                    ❌ 缺失（内部函数）
4. get_sync_status()                ❌ 缺失
```

### 用例 5：删除数据

```
Agent 操作流程：
1. get_schema_info()                ✅ 已有（获取表信息）
2. delete_records(table, ids)       ❌ 缺失
3. drop_table(table_name)           ❌ 缺失
```

***

## 五、改进建议汇总

### 高优先级（核心功能缺失）

| 工具                  | 功能      | 理由                |
| ------------------- | ------- | ----------------- |
| `get_stats()`       | 获取运行时统计 | Agent 需要了解知识库运行状态 |
| `delete_records()`  | 删除记录    | 数据生命周期管理必需        |
| `drop_table()`      | 删除表     | 数据生命周期管理必需        |
| `get_sync_status()` | 同步状态    | 监控数据新鲜度           |

### 中优先级（增强功能）

| 工具                | 功能        | 理由                 |
| ----------------- | --------- | ------------------ |
| `list_tables()`   | 快速列出表和记录数 | 便捷方法，避免解析完整 schema |
| `update_record()` | 更新记录      | 支持数据修正             |
| `query_safe()`    | 安全查询      | 替代 raw SQL，更安全     |

### 低优先级（可选功能）

| 工具                      | 功能     | 理由         |
| ----------------------- | ------ | ---------- |
| `init_knowledge_base()` | 初始化 KB | 通常由系统管理员完成 |
| `export_data()`         | 导出数据   | 备份需求       |
| `configure()`           | 配置管理   | 通常不需要动态修改  |

***

## 六、建议的工具接口设计

### 6.1 list\_tables

```python
@mcp.tool()
async def list_tables() -> str:
    """
    List all tables in the knowledge base.
    
    Returns:
        JSON string containing:
        - tables: List of table names with record counts
        - total_records: Total number of records
        - last_sync: Last synchronization timestamp
    """
```

### 6.2 get\_stats

```python
@mcp.tool()
async def get_stats() -> str:
    """
    Get detailed knowledge base statistics.
    
    Returns:
        JSON string containing:
        - tables: Table-level statistics
        - cache: Cache statistics (size, hit rate)
        - storage: Disk usage
        - index: Index status
    """
```

### 6.3 delete\_records

```python
@mcp.tool()
async def delete_records(table_name: str, ref_ids: list[str]) -> str:
    """
    Delete specific records from a table.
    
    Args:
        table_name: Target table name
        ref_ids: List of record IDs to delete
        
    Returns:
        Number of records deleted
    """
```

### 6.4 drop\_table

```python
@mcp.tool()
async def drop_table(table_name: str) -> str:
    """
    Drop a table and all its indexed data.
    
    Args:
        table_name: Table name to drop
        
    Returns:
        Confirmation message
    """
```

### 6.5 describe\_table

```python
@mcp.tool()
async def describe_table(table_name: str, sample_size: int = 3) -> str:
    """
    Get table structure and sample data.
    
    Args:
        table_name: Table name to describe
        sample_size: Number of sample records to return
        
    Returns:
        JSON with columns, types, and sample records
    """
```

***

## 七、实施计划

### Phase 1: 数据更新与删除能力（核心需求）

#### 1.1 delete\_records 工具

**功能**：删除指定表中的特定记录

**实现要点**：

1. 从 `_sys_search` 表中删除对应的索引记录
2. 从源 JSONL 文件中移除对应记录
3. 触发增量同步更新索引

```python
@mcp.tool()
async def delete_records(table_name: str, ref_ids: list[str]) -> str:
    """
    Delete specific records from a table.
    
    Args:
        table_name: Target table name (without .jsonl)
        ref_ids: List of record IDs to delete
        
    Returns:
        JSON string with deletion count and status
    """
```

**实现细节**：

* 读取源 JSONL 文件，过滤掉要删除的记录

* 原子化写入（staging + rename）

* 从 `_sys_search` 表删除对应索引

* 更新 `sync_state.json`

#### 1.2 drop\_table 工具

**功能**：删除整个表及其所有数据

**实现要点**：

1. 删除源 JSONL 文件
2. 从 `_sys_search` 表删除所有该表的索引
3. 更新同步状态

```python
@mcp.tool()
async def drop_table(table_name: str) -> str:
    """
    Drop a table and all its indexed data.
    
    Args:
        table_name: Table name to drop (without .jsonl)
        
    Returns:
        Confirmation message with deleted record count
    """
```

#### 1.3 update\_records 工具（可选）

**功能**：更新指定记录

**实现方式**：

* 方案 A：先删除再重新导入

* 方案 B：直接更新 JSONL 文件中的记录并重新索引

```python
@mcp.tool()
async def update_records(table_name: str, records: list[dict]) -> str:
    """
    Update specific records in a table.
    
    Args:
        table_name: Target table name
        records: List of records with 'id' field to update
        
    Returns:
        JSON string with update count and status
    """
```

### Phase 2: 运行时统计（增强功能）

1. `get_stats()` - 获取详细统计信息
2. `get_sync_status()` - 同步状态监控

***

## 八、总结

### 当前工具覆盖度评估

| 生命周期阶段 | 覆盖度  | 说明                                                  |
| ------ | ---- | --------------------------------------------------- |
| 初始化    | 0%   | 完全缺失（通常由系统管理员完成）                                    |
| 导入     | 100% | validate\_and\_import 完整                            |
| 索引     | 100% | sync\_knowledge\_base 完整                            |
| 查询     | 100% | get\_schema\_info + smart\_search + query\_raw\_sql |
| 更新     | 0%   | **核心缺失**：无更新/删除能力                                   |
| 维护     | 50%  | check\_health + get\_schema\_info                   |
| 备份     | 0%   | 完全缺失                                                |
| 销毁     | 0%   | **核心缺失**：无删除表能力                                     |

**总体评估**：当前工具集覆盖了约 **55%** 的知识库生命周期需求。导入和查询阶段完整，但**更新和删除能力完全缺失**，这是最关键的问题。

### 核心问题

**数据生命周期管理缺失**：只能添加数据，无法更新或删除

当前 `validate_and_import` 只能追加数据：

```python
# indexer.py 第 304-311 行
final_content = b""
if target_path.exists():
    final_content = await asyncio.to_thread(target_path.read_bytes)
    if final_content and not final_content.endswith(b"\n"):
        final_content += b"\n"
new_content = await asyncio.to_thread(temp_file_path.read_bytes)
final_content += new_content  # 永远是追加操作
```

### 优先实施方案

**Phase 1: 数据更新与删除能力（核心需求）**

1. `delete_records(table_name, ref_ids)` - 删除指定记录
2. `drop_table(table_name)` - 删除整个表
3. `update_records(table_name, records)` - 更新记录（可选，可通过删除+重新导入实现）

**Phase 2: 运行时统计（增强功能）**

1. `get_stats()` - 获取详细统计信息
2. `get_sync_status()` - 同步状态监控

