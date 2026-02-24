# 添加中文注释规范

## Why
项目代码目前缺少中文注释，影响代码可读性和维护性。需要为所有核心模块添加规范的中文简体注释，包括模块文档、类文档、函数文档和关键逻辑注释。同时需要将注释规则纳入项目规范文件，确保后续开发遵循统一标准。

## What Changes
- 更新 `.trae/rules/project_rules.md`，添加注释规则章节
- 为所有 Python 模块添加模块级文档字符串
- 为所有类添加类文档字符串，说明职责和用法
- 为所有公共函数/方法添加文档字符串，包含参数、返回值和异常说明
- 为关键业务逻辑添加行内注释，解释复杂算法和设计决策
- 保持现有英文注释的语义一致性，翻译为中文

## Impact
- Affected specs: 无
- Affected code: 
  - `.trae/rules/project_rules.md`
  - `src/duckkb/__init__.py`
  - `src/duckkb/config.py`
  - `src/duckkb/constants.py`
  - `src/duckkb/db.py`
  - `src/duckkb/exceptions.py`
  - `src/duckkb/logger.py`
  - `src/duckkb/main.py`
  - `src/duckkb/schema.py`
  - `src/duckkb/engine/indexer.py`
  - `src/duckkb/engine/searcher.py`
  - `src/duckkb/mcp/server.py`
  - `src/duckkb/utils/embedding.py`
  - `src/duckkb/utils/text.py`

## ADDED Requirements

### Requirement: 项目规范更新
`project_rules.md` SHALL 新增"注释规范"章节，定义统一的注释标准。

#### Scenario: 规范文件更新
- **WHEN** 查看 `.trae/rules/project_rules.md`
- **THEN** 存在"注释规范"章节，包含模块、类、函数文档和行内注释规则

### Requirement: 模块文档
每个 Python 模块 SHALL 在文件顶部包含模块级文档字符串，说明模块职责和主要功能。

#### Scenario: 模块文档完整性
- **WHEN** 打开任意 Python 模块
- **THEN** 文件顶部存在三引号包裹的中文文档字符串

### Requirement: 类文档
所有公共类 SHALL 包含类文档字符串，说明类的职责、属性和典型用法。

#### Scenario: 类文档完整性
- **WHEN** 查看类定义
- **THEN** 类声明下方存在中文文档字符串，说明职责和用法

### Requirement: 函数文档
所有公共函数和方法 SHALL 包含文档字符串，包含：
- 功能描述
- Args: 参数说明
- Returns: 返回值说明
- Raises: 可能抛出的异常（如有）

#### Scenario: 函数文档完整性
- **WHEN** 查看公共函数定义
- **THEN** 函数声明下方存在规范的中文文档字符串

### Requirement: 关键逻辑注释
复杂业务逻辑、算法实现、设计决策 SHALL 添加行内注释说明。

#### Scenario: 关键逻辑可理解性
- **WHEN** 阅读复杂逻辑代码
- **THEN** 关键步骤有中文注释说明意图和原因

### Requirement: 注释风格一致性
所有注释 SHALL 遵循统一的格式规范：
- 使用中文简体
- 使用规范的标点符号
- 保持与代码缩进一致
- 避免冗余注释

#### Scenario: 注释风格统一
- **WHEN** 检查任意模块的注释
- **THEN** 注释风格与其他模块保持一致
