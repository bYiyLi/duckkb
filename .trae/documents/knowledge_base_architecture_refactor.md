# 知识库架构分层与数据流重构计划

## 1. 核心设计理念

响应您的要求，我们将知识库架构明确划分为**持久层**和**运行时层**，确立"本地文件为唯一事实来源（Single Source of Truth）"的原则，并规范数据流向。

### 1.1 架构分层

*   **持久层 (Persistence Layer)**:
    *   **核心组件**: 本地 `.jsonl` 文件系统。
    *   **职责**: 数据的长期存储、版本控制（Git）、人工查阅与编辑。
    *   **地位**: **唯一数据源**。任何时刻，系统重启后的状态都应完全由文件内容决定。

*   **运行时层 (Runtime Layer)**:
    *   **核心组件**: DuckDB (`_sys_search` 表)。
    *   **职责**: 高性能检索（Vector/FTS）、数据的增删改操作（CRUD）。
    *   **地位**: **操作缓存**。所有运行时的查询和修改都**必须**在此层进行，随后异步或同步地持久化回文件。

### 1.2 标准数据流

1.  **初始化/加载 (Load)**:
    *   **触发**: 系统启动、显式重载。
    *   **流向**: `File -> DB`。
    *   **逻辑**: 读取 `.jsonl`，计算 Hash，增量同步到 DuckDB。

2.  **变更操作 (Mutation)**:
    *   **触发**: 导入数据、删除记录、更新元数据。
    *   **流向**: `Request -> DB (Modify) -> Return Success -> [Async] File (Persist)`。
    *   **逻辑**:
        1.  **Validate**: 校验请求合法性。
        2.  **Execute**: 在 DuckDB 中执行事务性修改（Insert/Delete）。
        3.  **Return**: **立即返回成功**。
        4.  **Async Persist**: 触发异步任务（带防抖机制），将变更后的数据回写到 `.jsonl`。

## 2. 现状分析与差距

经过代码审查，当前实现基本符合架构分层，但存在同步阻塞问题：

*   **同步阻塞**: 目前的 `importer.py` 和 `deleter.py` 在操作完 DB 后，会**同步等待** `sync_db_to_file` 完成才返回。对于大文件回写，这会显著增加 API 延迟。
*   **`sync.py`**: 混合了 "File -> DB" (启动同步) 和 "DB -> File" (回写) 的逻辑，职责过重。
*   **缺乏原子性保障**: 虽然使用了 `atomic_write_file`，但"写库"与"写文件"是两个独立步骤。

## 3. 重构方案

### 3.1 引入 `KnowledgeBaseManager`与异步持久化

创建一个统一的管理类 `KnowledgeBaseManager`，封装所有对知识库的读写操作，并引入**异步防抖机制**。

```python
class KnowledgeBaseManager:
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path
        self.loader = DataLoader(kb_path)
        self.persister = DataPersister(kb_path)
        self._save_tasks = {}  # table_name -> asyncio.Task

    async def load_all(self):
        """启动时调用：File -> DB"""
        await self.loader.sync_files_to_db()

    async def add_documents(self, table_name: str, documents: list[dict]):
        """导入数据：Write DB -> Return -> Async Save"""
        async with get_db_transaction() as conn:
            # 1. 写入 DB (同步/原子操作)
            await self._insert_to_db(conn, table_name, documents)
        
        # 2. 触发异步保存 (Fire and Forget / Debounced)
        self._schedule_save(table_name)

    async def delete_documents(self, table_name: str, doc_ids: list[str]):
        """删除数据：Write DB -> Return -> Async Save"""
        async with get_db_transaction() as conn:
            # 1. 从 DB 删除
            await self._delete_from_db(conn, table_name, doc_ids)
        
        # 2. 触发异步保存
        self._schedule_save(table_name)

    def _schedule_save(self, table_name: str):
        """调度保存任务，支持简单的防抖 (Debounce)"""
        if table_name in self._save_tasks:
            self._save_tasks[table_name].cancel()
        
        # 创建新任务，延迟执行以合并短时间内的多次变更
        self._save_tasks[table_name] = asyncio.create_task(
            self._delayed_save(table_name, delay=1.0)
        )

    async def _delayed_save(self, table_name: str, delay: float):
        await asyncio.sleep(delay)
        try:
            await self.persister.dump_table_to_file(table_name)
        except Exception as e:
            logger.error(f"Async save failed for {table_name}: {e}")
        finally:
            self._save_tasks.pop(table_name, None)
```

### 3.2 拆分 `sync.py`

将 `src/duckkb/engine/sync.py` 拆分为：
1.  **`loader.py`**: 负责 `File -> DB` 的增量同步。
2.  **`persister.py`**: 负责 `DB -> File` 的全量转储。

### 3.3 优化点

*   **性能提升**: API 响应时间不再受磁盘 IO 写入速度影响。
*   **防抖 (Debounce)**: 避免频繁的小幅变更导致频繁的全量文件重写。
*   **错误处理**: 异步任务失败需要有日志记录，并在下次操作或启动时能自动恢复（通过 File -> DB 的重新同步）。

## 4. 执行步骤

1.  **重构文件结构**: 创建 `src/duckkb/engine/core/` 目录，存放 `manager.py`, `loader.py`, `persister.py`。
2.  **迁移逻辑**:
    *   将 `sync_knowledge_base` 逻辑迁移至 `loader.py`。
    *   将 `sync_db_to_file` 逻辑迁移至 `persister.py`。
3.  **统一入口**: 修改 `main.py` 和 `server.py`，不再直接调用 `importer/deleter`，而是通过 `KnowledgeBaseManager` 进行操作。
4.  **清理旧代码**: 移除独立的 `importer.py`, `deleter.py`，将其逻辑合并入 Manager 或作为 Manager 的辅助策略。

这个计划确立了清晰的读写分离和分层治理，符合您期望的架构方向。
