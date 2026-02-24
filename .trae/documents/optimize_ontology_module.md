# 优化 duckkb.ontology 模块设计方案

## 1. 概述
本计划旨在优化 `duckkb.ontology` 模块的设计，解决当前存在的数据验证缺失、类型映射硬编码及接口冗余等问题。通过本次优化，将显著提升系统的健壮性和代码的可维护性。

## 2. 任务分解

### 任务 1: 集成数据验证 (High Priority)
**目标**: 在数据导入流程中强制执行 Schema 验证，防止非法数据入库。

**步骤**:
1.  修改 `src/duckkb/mcp/server.py` 中的 `validate_and_import` 函数。
2.  在函数内部，通过 `AppContext` 获取当前的 `Ontology` 配置。
3.  根据传入的 `table_name` 查找对应的 `NodeType` 定义。
4.  如果 `NodeType` 定义了 `json_schema`，则对每一条待导入记录调用 `validate_json_by_schema` 进行校验。
5.  如果校验失败，记录详细错误信息并终止导入或跳过错误记录（根据策略决定，建议全量校验通过后再导入，或者记录所有错误）。

**涉及文件**:
- `src/duckkb/mcp/server.py`
- `src/duckkb/ontology/_validator.py` (确保接口易用)

### 任务 2: 重构类型映射 (Medium Priority)
**目标**: 消除 `json_type_to_duckdb` 函数中的硬编码逻辑，提高扩展性。

**步骤**:
1.  在 `src/duckkb/ontology/engine.py` 中定义一个模块级常量字典 `JSON_TO_DUCKDB_TYPE_MAP`。
2.  修改 `json_type_to_duckdb` 函数，使其优先查表，未命中则使用默认值。
3.  保留对 `format` 字段（如 `date-time`）的特殊处理逻辑，但这部分也可以考虑提取为独立的映射或策略。

**涉及文件**:
- `src/duckkb/ontology/engine.py`

### 任务 3: 清理冗余接口 (Low Priority)
**目标**: 明确模块的公共 API，减少混淆。

**步骤**:
1.  鉴于 `OntologyEngine` 类目前仅在测试中被引用，且其功能与 `generate_nodes_ddl` 等函数完全重叠，建议将其标记为 `Deprecated`，或直接移除（如果是内部项目且无外部依赖）。
2.  为了保持代码整洁，建议保留函数式接口 `generate_nodes_ddl` 和 `generate_node_ddl` 作为主要使用方式。
3.  更新 `__init__.py`，明确导出的 API。

**涉及文件**:
- `src/duckkb/ontology/engine.py`
- `src/duckkb/ontology/__init__.py`

### 任务 4: 增强测试 (Required)
**目标**: 验证优化后的逻辑正确性。

**步骤**:
1.  在 `tests/test_mcp_server.py` (如果存在) 或新建测试文件中，添加针对 `validate_and_import` 的测试用例。
    - 测试导入符合 Schema 的数据（应成功）。
    - 测试导入缺失必填字段的数据（应失败）。
    - 测试导入类型错误的数据（应失败）。
2.  验证 `json_type_to_duckdb` 重构后的行为与之前一致。

## 3. 验证计划
- 运行所有单元测试，确保无回归。
- 手动构造一个不符合 Schema 的 JSONL 文件，尝试通过 MCP 工具导入，确认系统能正确拦截并报错。
