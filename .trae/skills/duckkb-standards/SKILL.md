---
name: "duckkb-standards"
description: "固化 DuckKB 项目编码规范与质量门禁。实现/修改 sync、检索、SQL 接口、导入校验、文件写入或缓存逻辑前/后调用，用于生成方案、写代码与自检。"
---

# DuckKB Standards

本技能用于在实现 DuckKB（基于 DuckDB 的 MCP 知识库）时，持续应用项目级编码规范与工程约束，确保可审计、安全、幂等、可重建、低成本。调用本技能时，严格按本文件执行，不要引入未在仓库中确认存在的第三方依赖。

## 何时调用

在以下场景必须调用：

- 新增或修改 MCP 工具接口：`sync_knowledge_base`、`get_schema_info`、`smart_search`、`query_raw_sql`、`validate_and_import`
- 任何涉及 `data/*.jsonl` 的读写、合并、迁移、校验
- 任何涉及 DuckDB 连接、SQL 执行或结果集返回
- 任何涉及 embedding 生成、缓存、垃圾回收
- 对检索排序（BM25/向量融合、权重、metadata）做调整
- 提交前做一次“质量门禁自检”

## 设计不变量（必须满足）

- 一库一服：只允许访问 `KB_PATH` 指定的知识库目录；所有路径必须受 kb_root 约束，禁止路径穿越。
- 文件驱动：事实只允许通过修改 `data/*.jsonl` 变更；`.build/` 只存运行时产物，可删除可重建。
- 成本优先：embedding 必须走内容哈希缓存；命中不调用外部 API。
- 幂等可重建：`sync` 可重复执行且结果稳定；数据库与索引可从 jsonl 完全重建。
- 查询安全：`query_raw_sql` 只读；`SELECT` 必须有 `LIMIT`（无则追加）；结果集大小必须受控（目标 2MB 以内）。

## 模块边界（实现时的职责拆分）

按职责拆分代码，禁止在一个文件里混杂 I/O、SQL、校验与业务流程：

- kb_env：解析/校验 `KB_PATH`，提供安全路径 join
- fs_atomic：原子写入、jsonl 追加/替换、失败回滚、可选文件锁
- schema：管理 `schema.sql`，生成 schema 信息与 ER 图（Mermaid）
- duckdb_conn：统一 DuckDB 连接创建（只读/读写）、超时/内存/线程配置
- sync：从 `data/*.jsonl` 导入并构建 `_sys_search`；提取 metadata 快照；分词写入 `segmented_text`
- embedding_cache：内容哈希、缓存查取、写回、last_used 更新与 GC
- search：混合检索打分与排序，应用 `priority_weight`
- sql_api：`query_raw_sql` 的防护封装（只读、LIMIT、异常结构化、结果大小限制）
- import_validate：`validate_and_import` 的行级校验与错误反馈循环
- housekeeping：定期清理缓存、约束查询输出大小

## 编码规范（写代码时遵循）

### 类型与接口

- 公共函数/方法必须有完整类型标注（入参、返回值）。
- MCP 工具接口必须定义稳定的输入/输出结构；错误返回统一结构化格式。
- 禁止返回“随手 dict”；优先使用 `dataclasses`/`TypedDict` 等强结构。

### 错误处理（可修复）

- 对外返回错误必须结构化，包含 `code`、`message`、`details`（至少含可定位信息）。
- `validate_and_import` 的错误信息必须包含：行号、字段名、期望类型、实际值。
- 异常分层：Domain（校验失败）/ Infra（I/O、DB、网络）/ Bug（不应发生）。Domain 不输出堆栈，Bug 保留堆栈便于定位。

### 安全与隐私

- 所有路径输入必须约束在 kb_root 下。
- SQL 必须参数化；禁止字符串拼接用户输入进入 SQL（尤其是表名/字段名）。
- 禁止日志输出敏感信息与原始全文文本；embedding 相关仅允许输出长度与 hash 前缀。

### 文件与原子性

- 写 `data/*.jsonl` 必须原子：写临时文件 → fsync → rename 覆盖。
- 失败不得污染目标文件；支持中断恢复（至少保证“要么旧文件，要么新文件”，无半写）。
- `.build/` 仅存运行时文件且可清理；禁止把事实写到 `.build/` 作为最终态。

### SQL 与结果集控制

- `query_raw_sql`：
  - 只允许 `SELECT`（或显式白名单）；
  - 无 `LIMIT` 的 `SELECT` 必须自动追加 `LIMIT 1000`；
  - 返回值必须限制大小（目标 2MB 以内，超出需截断并提示）。

### 检索一致性

- 混合检索公式保持：`Final = (BM25*0.4 + Vector*0.6) * priority_weight`。
- `metadata` 必须是“行快照”：除被索引字段外的其它 KV 序列化保存，供 Agent 直接读取。

## 实现前检查（设计与风险）

实现任何功能前，先回答并落实：

- 这段逻辑是否会写入 `data/*.jsonl`？如果是，原子写入策略是什么？
- 是否引入了外部依赖？仓库是否已存在该依赖？如果不确定，先在仓库中确认。
- 是否有用户输入进入路径/SQL/文件名？对应的校验、约束、参数化在哪里？
- 是否可能导致高成本（重复 embedding）、大结果集（无 LIMIT）、高内存（全量读）？如何限制？

## 自检清单（提交前必须过）

- 事实变更仅通过 `data/*.jsonl`，且写入原子、可回滚。
- `.build/` 可删除可重建，不包含事实真源。
- `sync` 幂等、可重跑，且增量判断逻辑明确。
- `query_raw_sql` 只读、强制 LIMIT、结果集大小受控、异常结构化。
- embedding 走哈希缓存；命中不调用外部；last_used 更新；GC 有配置或常量集中管理。
- 日志不泄露敏感信息或 embedding 全文。
- 单元测试覆盖：原子写入、LIMIT 追加、只读拦截、导入校验行号定位、缓存命中/未命中。

## 输出要求（本技能的工作方式）

当你基于本技能产出代码或方案时：

- 先列出将遵守的不变量与风险点（简短即可），再给实现方案。
- 代码修改后必须做一次自检清单对照（只列“通过/不通过 + 原因”）。
