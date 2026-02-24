# DuckKB 知识库生命周期优化方案

## 背景

当前 DuckKB 的知识库初始化在 MCP 服务启动前通过 `asyncio.run(_startup())` 完成，存在以下问题：

1. **生命周期分离**：知识库初始化与 MCP 生命周期独立，无法利用 FastMCP 的生命周期管理
2. **缺少关闭钩子**：服务关闭时没有数据持久化机制
3. **同步工具功能单一**：`sync_knowledge_base` 工具仅做文件到数据库的同步，不支持 ontology 变更和数据迁移

## 优化目标

1. 将知识库生命周期与 MCP 生命周期整合
2. 在 MCP 关闭时自动将数据库数据写入本地磁盘
3. 增强 `sync_knowledge_base` 工具，支持 ontology 配置变更和数据迁移

***

## 一、生命周期整合方案

### 1.1 FastMCP Lifespan 机制

FastMCP 提供了可组合的生命周期装饰器 `@lifespan`，支持通过 `|` 操作符组合多个生命周期：

```python
from fastmcp.server.lifespan import lifespan

@lifespan
async def kb_lifespan(server):
    # 启动时初始化
    await init_knowledge_base()
    yield {"kb": knowledge_base}
    # 关闭时清理
    await persist_to_disk()
```

### 1.2 新架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    FastMCP Lifespan                         │
├─────────────────────────────────────────────────────────────┤
│  启动阶段 (Startup)                                          │
│  ├── 加载配置 (config.yaml)                                  │
│  ├── 初始化数据库模式 (init_schema)                          │
│  ├── 同步知识库 (sync_knowledge_base)                        │
│  └── 预热资源 (jieba 分词器等)                               │
├─────────────────────────────────────────────────────────────┤
│  运行阶段 (Runtime)                                          │
│  └── MCP 工具调用处理                                        │
├─────────────────────────────────────────────────────────────┤
│  关闭阶段 (Shutdown)                                         │
│  ├── 将数据库数据回写到 JSONL 文件                           │
│  ├── 保存同步状态                                            │
│  └── 清理资源                                                │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 代码变更

#### main.py 重构

```python
from contextlib import asynccontextmanager
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

@lifespan
async def kb_lifespan(server: FastMCP):
    """知识库生命周期管理。"""
    ctx = AppContext.get()
    
    # 启动时初始化
    logger.info("Initializing knowledge base...")
    await init_schema()
    await sync_knowledge_base(ctx.kb_path)
    logger.info("Knowledge base initialized.")
    
    yield {"kb_path": ctx.kb_path}
    
    # 关闭时持久化
    logger.info("Persisting knowledge base to disk...")
    await persist_all_tables()
    logger.info("Knowledge base persisted.")

mcp = FastMCP("DuckKB", lifespan=kb_lifespan)
```

#### 新增 persist\_all\_tables 函数

```python
async def persist_all_tables() -> None:
    """将所有数据库表持久化到 JSONL 文件。"""
    ctx = AppContext.get()
    data_dir = ctx.kb_path / DATA_DIR_NAME
    
    # 获取所有表名
    tables = await _get_all_table_names()
    
    for table_name in tables:
        await sync_db_to_file(table_name, ctx.kb_path)
```

***

## 二、sync\_knowledge\_base 工具增强

### 2.1 新增功能

1. **支持传入新的 ontology 配置**
2. **Ontology 变更时的数据迁移**
3. **事务性操作与回滚机制**

### 2.2 接口设计

````python
@mcp.tool()
async def sync_knowledge_base(
    ontology_yaml: str | None = None,
    force: bool = False
) -> str:
    """
    同步知识库，支持 ontology 配置变更和数据迁移。

    Args:
        ontology_yaml: 可选的新 ontology 配置（YAML 格式字符串）。
                      如果提供，将进行：
            - YAML 解析与配置校验
            - 数据库模式迁移
            - 数据迁移（如需要）
            - 失败时自动回滚
                      
                      示例：
                      ```yaml
                      nodes:
                        documents:
                          table: documents
                          identity: [id]
                          schema:
                            type: object
                            properties:
                              id:
                                type: string
                              title:
                                type: string
                              content:
                                type: string
                            required: [id]
                          vectors:
                            content:
                              dim: 1536
                              model: text-embedding-3-small
                      ```
        force: 是否强制重新同步所有数据（忽略增量检测）。

    Returns:
        str: JSON 格式的操作结果，包含迁移统计和状态。
    """
````

### 2.3 Ontology 变更处理流程

```
┌─────────────────────────────────────────────────────────────┐
│              Ontology 变更处理流程                           │
├─────────────────────────────────────────────────────────────┤
│  1. 验证新 Ontology 配置                                     │
│     ├── JSON Schema 校验                                     │
│     └── 兼容性检查                                           │
├─────────────────────────────────────────────────────────────┤
│  2. 创建备份                                                 │
│     ├── 备份当前数据库文件                                   │
│     └── 备份当前 JSONL 文件                                  │
├─────────────────────────────────────────────────────────────┤
│  3. 执行迁移                                                 │
│     ├── 分析变更类型                                         │
│     │   ├── 新增表：创建新表                                 │
│     │   ├── 删除表：删除表（需确认）                         │
│     │   ├── 新增字段：添加列                                 │
│     │   ├── 删除字段：保留数据，仅从索引移除                 │
│     │   └── 字段类型变更：尝试转换或报错                     │
│     └── 更新搜索索引                                         │
├─────────────────────────────────────────────────────────────┤
│  4. 验证迁移结果                                             │
│     ├── 数据完整性检查                                       │
│     └── 索引有效性检查                                       │
├─────────────────────────────────────────────────────────────┤
│  5. 提交或回滚                                               │
│     ├── 成功：删除备份，更新配置                             │
│     └── 失败：恢复备份，报告错误                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 变更类型与处理策略

| 变更类型   | 处理策略          | 数据风险 |
| ------ | ------------- | ---- |
| 新增表    | 创建新表，无需迁移     | 无    |
| 删除表    | 需要用户确认，删除表和索引 | 高    |
| 新增字段   | 添加列，重新索引相关数据  | 低    |
| 删除字段   | 从索引移除，保留原始数据  | 低    |
| 字段类型变更 | 尝试类型转换，失败则报错  | 中    |
| 向量维度变更 | 需要重新生成所有嵌入    | 中    |

### 2.5 备份与回滚机制

```python
class MigrationManager:
    """数据库迁移管理器。"""
    
    async def create_backup(self) -> Path:
        """创建备份。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.kb_path / BUILD_DIR_NAME / "backups" / timestamp
        
        # 备份数据库
        shutil.copy2(self.db_path, backup_dir / DB_FILE_NAME)
        
        # 备份 JSONL 文件
        shutil.copytree(self.data_dir, backup_dir / DATA_DIR_NAME)
        
        # 备份配置
        shutil.copy2(self.kb_path / "config.yaml", backup_dir / "config.yaml")
        
        return backup_dir
    
    async def rollback(self, backup_dir: Path) -> None:
        """从备份回滚。"""
        # 恢复数据库
        shutil.copy2(backup_dir / DB_FILE_NAME, self.db_path)
        
        # 恢复 JSONL 文件
        shutil.rmtree(self.data_dir)
        shutil.copytree(backup_dir / DATA_DIR_NAME, self.data_dir)
        
        # 恢复配置
        shutil.copy2(backup_dir / "config.yaml", self.kb_path / "config.yaml")
```

***

## 三、实现计划

### 3.1 文件变更清单

| 文件                    | 变更类型 | 说明                          |
| --------------------- | ---- | --------------------------- |
| `main.py`             | 重构   | 使用 FastMCP lifespan         |
| `mcp/server.py`       | 修改   | 增强 sync\_knowledge\_base 工具 |
| `engine/sync.py`      | 扩展   | 添加迁移逻辑                      |
| `engine/migration.py` | 新增   | 迁移管理器                       |
| `engine/backup.py`    | 新增   | 备份与恢复                       |
| `config.py`           | 扩展   | 支持运行时 ontology 更新           |

### 3.2 实现步骤

1. **Phase 1: 生命周期整合**

   * 创建 `kb_lifespan` 生命周期管理器

   * 实现 `persist_all_tables` 函数

   * 重构 `main.py` 使用 FastMCP lifespan

2. **Phase 2: 备份与恢复**

   * 实现 `BackupManager` 类

   * 支持数据库和配置文件的备份/恢复

   * 添加备份清理策略

3. **Phase 3: 迁移机制**

   * 实现 `MigrationManager` 类

   * 支持各种变更类型的检测和处理

   * 实现事务性迁移和自动回滚

4. **Phase 4: 工具增强**

   * 扩展 `sync_knowledge_base` 工具接口

   * 添加 ontology 参数支持

   * 完善错误处理和用户反馈

***

## 四、风险与缓解措施

| 风险            | 影响    | 缓解措施           |
| ------------- | ----- | -------------- |
| 迁移过程中断        | 数据不一致 | 事务性操作 + 自动回滚   |
| 磁盘空间不足        | 备份失败  | 迁移前检查空间，提供清理建议 |
| Ontology 配置错误 | 迁移失败  | 严格校验 + 兼容性检查   |
| 向量维度变更        | 嵌入失效  | 提示用户，提供重新生成选项  |

***

## 五、测试计划

1. **单元测试**

   * 生命周期钩子测试

   * 备份/恢复测试

   * 迁移逻辑测试

2. **集成测试**

   * 完整迁移流程测试

   * 回滚场景测试

   * 并发操作测试

3. **端到端测试**

   * MCP 客户端调用测试

   * 大数据量迁移测试

   * 异常中断恢复测试

