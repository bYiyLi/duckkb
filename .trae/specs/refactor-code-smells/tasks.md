# Tasks

- [x] Task 1: 创建异步文件操作工具模块
  - [x] SubTask 1.1: 创建 `src/duckkb/utils/file_ops.py`，实现 `read_file_async`, `write_file_async`, `file_exists_async`, `list_files_async` 等基础函数，封装 `aiofiles` 和 `asyncio.to_thread`。
  - [x] SubTask 1.2: 编写 `tests/test_file_ops.py` 验证工具函数的正确性。

- [x] Task 2: 重构 `importer.py`
  - [x] SubTask 2.1: 将 `validate_and_import` 函数拆分为 `_validate_input`, `_process_file`, `_update_db` 等独立函数。
  - [x] SubTask 2.2: 使用 `file_ops` 模块替换其中的同步文件操作。
  - [x] SubTask 2.3: 修复宽泛的异常捕获。

- [x] Task 3: 重构 `searcher.py`
  - [x] SubTask 3.1: 将 `smart_search` 函数拆分为 SQL 构建、参数处理、执行查询等步骤。
  - [x] SubTask 3.2: 提取魔术数字（如 limit * 2）到常量定义。
  - [x] SubTask 3.3: 补充缺失的 docstrings。

- [x] Task 4: 重构 `sync.py`
  - [x] SubTask 4.1: 使用 `file_ops` 模块替换 `sync_knowledge_base` 中的同步文件操作（如 `glob`, `exists`）。
  - [x] SubTask 4.2: 优化 `_process_file` 函数逻辑，拆分过长代码块。
  - [x] SubTask 4.3: 补充缺失的 docstrings。

- [x] Task 5: 重构其他模块的文件操作
  - [x] SubTask 5.1: 更新 `deleter.py` 使用 `file_ops` 模块，并消除与 `sync.py` 的重复逻辑。
  - [x] SubTask 5.2: 更新 `mcp/server.py` 中的 `check_health` 使用异步文件检查。
  - [x] SubTask 5.3: 更新 `config.py` 中的 `KBConfig.from_yaml` 使用异步读取（注意该方法可能是同步调用的入口，需仔细处理）。
  - [x] SubTask 5.4: 优化 `utils/text.py` 中的 `jieba` 词典加载逻辑，避免阻塞。

- [x] Task 6: 清理硬编码与文档完善
  - [x] SubTask 6.1: 扫描并提取 `src/duckkb/config.py` 和 `src/duckkb/ontology/_models.py` 中的硬编码值。
  - [x] SubTask 6.2: 检查并补充剩余公共方法的 docstrings。

- [x] Task 7: 最终验证
  - [x] SubTask 7.1: 运行所有单元测试，确保重构未引入回归。
  - [x] SubTask 7.2: 运行 ruff 检查代码规范。

# Task Dependencies
- [Task 2], [Task 4], [Task 5] depends on [Task 1]
- [Task 7] depends on [Task 2], [Task 3], [Task 4], [Task 5], [Task 6]
