# Tasks

- [x] Task 0: 更新项目规范文件
  - [x] SubTask 0.1: 在 `project_rules.md` 中添加"注释规范"章节

- [x] Task 1: 为核心模块添加中文注释
  - [x] SubTask 1.1: 为 `__init__.py` 添加模块文档
  - [x] SubTask 1.2: 为 `config.py` 添加模块、类、方法文档
  - [x] SubTask 1.3: 为 `constants.py` 添加模块文档和常量注释
  - [x] SubTask 1.4: 为 `db.py` 添加模块、类、函数文档
  - [x] SubTask 1.5: 为 `exceptions.py` 添加模块和类文档
  - [x] SubTask 1.6: 为 `logger.py` 添加模块和函数文档
  - [x] SubTask 1.7: 为 `main.py` 添加模块和函数文档
  - [x] SubTask 1.8: 为 `schema.py` 添加模块和函数文档

- [x] Task 2: 为引擎模块添加中文注释
  - [x] SubTask 2.1: 为 `engine/indexer.py` 添加完整文档和逻辑注释
  - [x] SubTask 2.2: 为 `engine/searcher.py` 添加完整文档和逻辑注释

- [x] Task 3: 为 MCP 服务模块添加中文注释
  - [x] SubTask 3.1: 为 `mcp/server.py` 添加模块和工具函数文档

- [x] Task 4: 为工具模块添加中文注释
  - [x] SubTask 4.1: 为 `utils/embedding.py` 添加模块、函数文档和逻辑注释
  - [x] SubTask 4.2: 为 `utils/text.py` 添加模块和函数文档

- [x] Task 5: 验证注释完整性
  - [x] SubTask 5.1: 运行 ruff 格式化检查
  - [x] SubTask 5.2: 运行测试确保功能不受影响

# Task Dependencies
- Task 0 应首先完成，为后续任务提供规范依据
- Task 5 依赖 Task 0-4 完成
