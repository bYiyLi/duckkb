# DuckKB MCP 程序生命周期分析

## 概述

DuckKB 是一个基于 FastMCP 框架的知识库服务，提供向量搜索和数据管理功能。本文档分析其完整的生命周期流程。

***

## 生命周期阶段

### 1. 启动阶段 (Initialization)

#### 1.1 CLI 入口

```
用户执行: duckkb serve --kb-path <path>
```

入口点位于 [main.py](file:///Users/yi/Code/duckkb/src/duckkb/main.py)，使用 `typer` 框架处理命令行参数。

#### 1.2 应用上下文初始化

```python
# main.py:39-42
if not kb_path.exists():
    kb_path.mkdir(parents=True, exist_ok=True)
ctx = AppContext.init(kb_path)
setup_logging(ctx.kb_config.LOG_LEVEL)
```

**关键操作：**

1. 创建知识库目录（如不存在）
2. 初始化 `AppContext` 单例
3. 加载 `config.yaml` 配置
4. 配置日志级别

#### 1.3 AppContext 单例结构

```
AppContext (单例)
├── kb_path: Path              # 知识库根目录
├── kb_config: KBConfig        # 知识库配置
│   ├── embedding: EmbeddingConfig
│   │   ├── model: str        # 嵌入模型名称
│   │   └── dim: int          # 向量维度
│   ├── log_level: str
│   └── ontology: Ontology     # 本体定义
├── global_config: GlobalConfig
│   ├── OPENAI_API_KEY
│   └── OPENAI_BASE_URL
├── _openai_client: AsyncOpenAI (懒加载)
└── _jieba_initialized: bool
```

#### 1.4 启动初始化任务

```python
# main.py:45-55
async def _startup():
    await init_schema()                    # 初始化数据库模式
    await sync_knowledge_base(kb_path)     # 同步知识库
```

**init\_schema() 流程：**

1. 创建系统表 `_sys_search`（搜索索引表）
2. 创建系统表 `_sys_cache`（嵌入缓存表）
3. 创建 HNSW 向量索引
4. 根据本体定义创建用户表

**sync\_knowledge\_base() 流程：**

1. 扫描 `data/` 目录下的 `.jsonl` 文件
2. 对比文件修改时间与同步状态
3. 增量同步变更的记录
4. 生成向量嵌入（调用 OpenAI API）
5. 更新搜索索引
6. 清理过期缓存

***

### 2. 运行阶段 (Runtime)

#### 2.1 MCP 服务启动

```python
# main.py:64-65
asyncio.run(_startup())
mcp.run()  # FastMCP 服务启动
```

FastMCP 服务通过 stdio 传输协议与 MCP 客户端通信。

#### 2.2 提供的 MCP 工具

| 工具名称                  | 功能     | 关键依赖                      |
| --------------------- | ------ | ------------------------- |
| `check_health`        | 健康检查   | AppContext                |
| `sync_knowledge_base` | 同步知识库  | sync.py                   |
| `get_schema_info`     | 获取模式信息 | schema.py                 |
| `smart_search`        | 混合搜索   | searcher.py, embedding.py |
| `query_raw_sql`       | SQL 查询 | searcher.py               |
| `validate_and_import` | 导入数据   | crud.py                   |
| `delete_records`      | 删除记录   | crud.py                   |

#### 2.3 核心数据流

```
┌─────────────────┐
│  JSONL 文件      │  data/*.jsonl
│  (数据源)        │
└────────┬────────┘
         │ sync_knowledge_base()
         ▼
┌─────────────────┐
│    DuckDB       │  .build/knowledge.db
│  ┌───────────┐  │
│  │_sys_search│  │  搜索索引表
│  │_sys_cache │  │  嵌入缓存表
│  └───────────┘  │
└────────┬────────┘
         │ smart_search() / query_raw_sql()
         ▼
┌─────────────────┐
│   MCP 工具响应   │
└─────────────────┘
```

***

### 3. 关键组件生命周期

#### 3.1 数据库连接管理

```python
# db.py
@asynccontextmanager
async def get_async_db(read_only: bool = True):
    manager = get_db_manager()
    conn = await asyncio.to_thread(manager.get_connection, read_only)
    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)
```

**特点：**

* 使用上下文管理器确保连接释放

* 通过 `asyncio.to_thread` 封装同步操作

* 支持只读/读写模式

#### 3.2 OpenAI 客户端（懒加载）

```python
# config.py:190-201
@property
def openai_client(self) -> AsyncOpenAI:
    if self._openai_client is None:
        self._openai_client = AsyncOpenAI(
            api_key=self.global_config.OPENAI_API_KEY,
            base_url=self.global_config.OPENAI_BASE_URL,
        )
    return self._openai_client
```

#### 3.3 嵌入向量缓存机制

```
请求嵌入向量
     │
     ▼
┌─────────────────┐
│ 计算文本 Hash    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     命中
│ 查询 _sys_cache │──────────▶ 返回缓存向量
└────────┬────────┘
         │ 未命中
         ▼
┌─────────────────┐
│ 调用 OpenAI API │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 存入缓存表       │
└────────┬────────┘
         │
         ▼
     返回向量
```

***

### 4. 同步机制详解

#### 4.1 增量同步策略

```python
# sync.py:83-85
if sync_state.get(table_name) == mtime:
    logger.debug(f"Skipping {table_name}, up to date (mtime check).")
    continue
```

**同步状态文件：** `.build/sync_state.json`

```json
{
  "table1": 1709012345.678,  // 文件修改时间戳
  "table2": 1709012346.789
}
```

#### 4.2 记录级 Diff

```python
# sync.py:214-231
to_delete_ids = set(db_state.keys()) - set(file_map.keys())
to_upsert_records = []

for ref_id, record in file_map.items():
    if ref_id not in db_state:
        to_upsert_records.append(record)
    else:
        # 检查内容哈希是否变更
        current_hashes = {compute_text_hash(v) for v in record.values() if isinstance(v, str)}
        db_hashes = set(db_state[ref_id].values())
        if current_hashes != db_hashes:
            to_upsert_records.append(record)
            to_delete_ids.add(ref_id)
```

***

### 5. 关闭阶段 (Shutdown)

当前实现中，MCP 服务通过 FastMCP 框架处理关闭信号。主要清理工作：

1. 数据库连接自动关闭（通过上下文管理器）
2. 无显式的资源清理钩子

**潜在改进点：**

* 添加优雅关闭钩子

* 确保所有异步任务完成

* 刷新未写入的数据

***

## 目录结构

```
knowledge-bases/default/
├── config.yaml           # 知识库配置
├── README.md             # 知识库说明
├── schema.sql            # 可选：自定义模式
├── data/                 # 数据文件目录
│   ├── table1.jsonl
│   └── table2.jsonl
└── .build/               # 构建产物（不提交）
    ├── knowledge.db      # DuckDB 数据库
    └── sync_state.json   # 同步状态
```

***

## 依赖关系图

```
main.py
├── config.py (AppContext, KBConfig)
├── schema.py (init_schema)
├── engine/sync.py (sync_knowledge_base)
│   ├── db.py (get_db)
│   ├── utils/embedding.py (get_embeddings)
│   └── utils/text.py (segment_text, compute_text_hash)
└── mcp/server.py (FastMCP tools)
    ├── engine/searcher.py (smart_search, query_raw_sql)
    ├── engine/crud.py (add_documents, delete_documents)
    └── schema.py (get_schema_info)
```

***

## 总结

DuckKB MCP 程序的生命周期遵循以下模式：

1. **初始化** → CLI 解析 → 上下文初始化 → 数据库模式创建 → 数据同步
2. **运行** → FastMCP 服务监听 → 工具调用处理 → 数据库查询/更新
3. **关闭** → 信号处理 → 资源释放

关键设计特点：

* 单例模式管理全局状态

* 懒加载优化资源使用

* 增量同步减少不必要的计算

* 嵌入缓存降低 API 成本

* 异步架构避免阻塞操作

