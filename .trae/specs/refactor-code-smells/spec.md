# 代码坏味道重构与优化方案 Spec

## Why
当前项目代码中存在多个代码坏味道（Code Smells），主要包括函数过长、在异步函数中混用同步 I/O、硬编码值、以及重复的文件操作逻辑。这些问题降低了代码的可读性、可维护性，并可能影响系统在高并发场景下的性能（同步 I/O 阻塞事件循环）。本变更旨在通过重构解决这些问题，提升代码质量和运行效率。

## What Changes
- **提取公共文件操作逻辑**：创建 `src/duckkb/utils/file_ops.py`，统一封装基于 `aiofiles` 和 `asyncio.to_thread` 的异步文件读写操作。
- **重构过长函数**：
  - 拆分 `src/duckkb/engine/importer.py` 中的 `validate_and_import` 函数。
  - 拆分 `src/duckkb/engine/searcher.py` 中的 `smart_search` 函数。
  - 拆分 `src/duckkb/schema.py` 中的 `_parse_table_definitions` 函数。
- **异步化 I/O 操作**：
  - 将 `src/duckkb/engine/sync.py`、`src/duckkb/engine/importer.py`、`src/duckkb/mcp/server.py` 中的同步文件操作替换为异步操作。
  - 确保所有文件操作（尤其是 `pathlib.Path` 的同步方法如 `exists`, `glob` 等）在异步上下文中正确处理。
- **消除硬编码**：
  - 将 `src/duckkb/engine/searcher.py` 和 `src/duckkb/config.py` 中的魔术数字和字符串提取到常量定义或配置文件中。
- **完善文档字符串**：
  - 为所有公共方法（特别是 `searcher.py` 和 `sync.py` 中缺失文档的方法）补充符合 Google Style 的 docstrings。
- **优化异常处理**：
  - 将宽泛的 `except Exception` 替换为具体的异常捕获，或确保异常被正确记录和抛出。

## Impact
- **受影响的 specs**: 无直接关联的 feature specs，属于技术债偿还。
- **受影响的代码**:
  - `src/duckkb/engine/importer.py`
  - `src/duckkb/engine/searcher.py`
  - `src/duckkb/engine/sync.py`
  - `src/duckkb/engine/deleter.py`
  - `src/duckkb/mcp/server.py`
  - `src/duckkb/config.py`
  - `src/duckkb/schema.py`
  - `src/duckkb/utils/text.py`
- **新增文件**:
  - `src/duckkb/utils/file_ops.py`

## ADDED Requirements
### Requirement: 统一异步文件操作工具
系统 SHALL 提供一个统一的 `file_ops` 模块，封装常用的异步文件操作。

#### Scenario: 异步读取文件
- **WHEN** 开发者需要读取文件内容
- **THEN** 应调用 `file_ops.read_file_async` 等工具方法，而不是直接使用 `open()` 或同步 IO。

### Requirement: 严格的 Docstring 规范
所有公共函数和类必须包含完整的 Docstring，描述参数、返回值和异常。

## MODIFIED Requirements
### Requirement: 导入逻辑重构
`importer.py` 的导入逻辑将被拆分为验证、文件处理、数据库更新等独立步骤。

### Requirement: 搜索逻辑重构
`searcher.py` 的搜索逻辑将被拆分为查询构建、执行搜索、结果处理等独立步骤。

## REMOVED Requirements
无功能移除。
