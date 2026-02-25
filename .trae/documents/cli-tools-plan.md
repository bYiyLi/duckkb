# 计划：将 MCP 工具暴露为 CLI 命令

## 背景

当前 `DuckMCP` 类通过继承 `Engine` 和 `FastMCP`，将知识库能力暴露为 MCP 工具。用户希望在 `DuckTyper` CLI 中也提供相同的工具命令。

## 需要暴露的工具

| 工具名 | 方法来源 | 是否异步 | 说明 |
|--------|----------|----------|------|
| `get-knowledge-schema` | `OntologyMixin.get_bundle_schema()` | 否 | 获取知识库校验 Schema |
| `import-knowledge-bundle` | `ImportMixin.import_knowledge_bundle()` | 是 | 导入知识包 |
| `search` | `SearchMixin.search()` | 是 | 混合检索（RRF 融合） |
| `vector-search` | `SearchMixin.vector_search()` | 是 | 向量语义检索 |
| `fts-search` | `SearchMixin.fts_search()` | 是 | 全文关键词检索 |
| `get-source-record` | `SearchMixin.get_source_record()` | 是 | 回捞原始业务记录 |

## 实现方案

### 核心思路

1. **复用 Engine 实例**：`DuckTyper` 已有 `create_mcp()` 方法创建 `DuckMCP` 实例，可直接使用 `Engine` 的能力
2. **异步转同步**：CLI 命令是同步的，使用 `asyncio.run()` 包装异步方法
3. **生命周期管理**：每个命令独立创建 Engine 实例，使用上下文管理器自动初始化和关闭
4. **输出格式**：统一使用 JSON 格式输出，保持与 MCP 工具一致

### 实现步骤

1. **添加异步运行辅助函数**
   - 创建 `_run_async()` 函数，封装 `asyncio.run()` 调用

2. **注册 CLI 命令**
   - 在 `_register_commands()` 中调用新的注册方法
   - 添加 `_register_search_commands()` 方法注册所有搜索相关命令

3. **实现各命令**

   **`get-knowledge-schema` 命令**：
   ```python
   @self.command("get-knowledge-schema")
   def get_knowledge_schema() -> None:
       with Engine(self.kb_path) as engine:
           result = engine.get_bundle_schema()
           typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
   ```

   **`import-knowledge-bundle` 命令**：
   ```python
   @self.command("import-knowledge-bundle")
   def import_knowledge_bundle(temp_file_path: Path) -> None:
       async def _import():
           with Engine(self.kb_path) as engine:
               return await engine.import_knowledge_bundle(str(temp_file_path))
       result = _run_async(_import())
       typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
   ```

   **`search` 命令**：
   ```python
   @self.command()
   def search(
       query: str,
       node_type: str | None = None,
       limit: int = 10,
       alpha: float = 0.5,
   ) -> None:
       async def _search():
           with Engine(self.kb_path) as engine:
               return await engine.search(query, node_type=node_type, limit=limit, alpha=alpha)
       result = _run_async(_search())
       typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
   ```

   **`vector-search` 命令**、**`fts-search` 命令**、**`get-source-record` 命令**：类似模式

4. **命令命名约定**
   - 多词命令使用 kebab-case（如 `get-knowledge-schema`）
   - 保持与 MCP 工具命名语义一致

## 文件变更

- `/Users/yi/Code/duckkb/src/duckkb/cli/duck_typer.py`
  - 添加 `import asyncio` 和 `import json`
  - 添加 `_run_async()` 辅助函数
  - 添加 `_register_search_commands()` 方法
  - 修改 `_register_commands()` 调用新方法

## 使用示例

```bash
# 获取 Schema
duckkb -k /path/to/kb get-knowledge-schema

# 导入知识包
duckkb -k /path/to/kb import-knowledge-bundle /tmp/bundle.yaml

# 混合搜索
duckkb -k /path/to/kb search "查询文本" --node-type Document --limit 10

# 向量搜索
duckkb -k /path/to/kb vector-search "语义查询"

# 全文搜索
duckkb -k /path/to/kb fts-search "关键词"

# 回捞原始记录
duckkb -k /path/to/kb get-source-record --source-table Document --source-id 1
```

## 注意事项

1. 每个命令独立创建 Engine 实例，确保资源正确释放
2. 异步方法通过 `asyncio.run()` 在同步 CLI 环境中执行
3. 输出格式与 MCP 工具保持一致（JSON）
4. 错误通过 typer.Exit() 优雅退出
