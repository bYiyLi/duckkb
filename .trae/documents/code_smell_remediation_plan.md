# 代码坏味道处理计划

## 1. 自动化修复 (Linting)
- [ ] 运行 `ruff check --fix .` 修复导入排序和未使用的导入等问题。
- [ ] 重点检查 `tests/test_backup.py` 中的 lint 错误。

## 2. 代码清理 (Clean up)
- [ ] **tests/test_backup.py**:
    - 清理 `test_cleanup_old_backups` 方法中遗留的注释代码（思考过程）。
    - 确保测试逻辑清晰且无冗余。

## 3. 重构 (Refactoring)
- [ ] **src/duckkb/ontology/engine.py**:
    - 将 `json_type_to_duckdb`、`generate_node_ddl`、`generate_nodes_ddl` 等独立函数重构为 `OntologyEngine` 类的私有方法或静态方法，以提高内聚性。
    - 统一代码风格。

## 4. 复杂性分析与优化 (Complexity Analysis & Optimization)
- [ ] **src/duckkb/mcp/server.py** (13K):
    - 阅读并分析代码结构。
    - 识别是否包含过长函数或混合了过多职责。
    - 如果有，提取逻辑到独立的 handler 或 helper 模块中。
- [ ] **src/duckkb/engine/sync.py** (13K):
    - 阅读并分析代码结构。
    - 检查是否存在大函数或重复逻辑。
    - 尝试提取公共逻辑或拆分模块。

## 5. 验证
- [ ] 运行所有测试 `pytest` 确保重构未破坏现有功能。
- [ ] 再次运行 `ruff check .` 确保无新增 lint 错误。
