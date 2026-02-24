# DuckKB 项目优化计划

## 目标

提升 DuckKB 的性能（I/O 与 CPU）、灵活性（配置化）与安全性（SQL 检查）。

## 任务分解

### 1. 性能与异步化改造 (Performance & AsyncIO)

* [ ] **\[Task 1.1] 异步文件处理**：

  * 重构 `indexer.py`，使用 `asyncio.to_thread` 封装文件读取操作，避免阻塞 Event Loop。

* [ ] **\[Task 1.2] CPU 任务卸载**：

  * 将 `jieba` 分词操作通过 `asyncio.get_running_loop().run_in_executor` 提交到线程池执行。

* [ ] **\[Task 1.3] 异步批量 Embedding**：

  * 重构 `get_embedding` 为支持批量输入，利用 OpenAI API 批量接口减少网络开销。

### 2. MCP 功能增强 (MCP Enhancement)

* [ ] **\[Task 2.1] 动态检索权重**：

  * 修改 `searcher.py` 的 `smart_search` 方法，增加 `alpha` 参数 (0.0-1.0)。

* [ ] **\[Task 2.2] MCP 接口更新**：

  * 更新 `mcp/server.py`，暴露 `alpha` 参数给 Agent，使其能根据查询意图动态调整。

### 3. 安全增强 (Security)

* [ ] **\[Task 3.1] SQL 安全校验**：

  * 在 `query_raw_sql` 中增加对 `LIMIT` 和危险关键字的正则检查。

