# [Project Structure] 规范

## 为什么 (Why)
当前项目缺乏定义的目录结构。为了确保可维护性、可扩展性，并遵循设计文档中 outlined 的“专用模式”和“文件驱动”理念，需要建立清晰、模块化的结构。

## 变更内容 (What Changes)
- 在 `src/duckkb` 下创建标准的 Python 项目结构。
- 将关注点分离为不同的模块：
  - `config`: 配置管理。
  - `db`: 数据库连接和会话管理。
  - `schema`: 数据库模式定义和初始化。
  - `engine`: 核心业务逻辑包（索引、搜索）。
  - `mcp`: MCP 服务器实现。
  - `utils`: 辅助函数（文本处理、Embedding、I/O）。
  - `logger`: 集中式日志配置。
- 建立与源代码结构镜像的 `tests` 目录。

## 影响 (Impact)
- **受影响的规范**: 无（初始结构）。
- **受影响的代码**: `src/duckkb/`（新文件）。

## 新增需求 (ADDED Requirements)
### Requirement: 目录结构
系统应遵循建议的目录结构：
```
src/duckkb/
├── __init__.py
├── main.py              # 入口点 (CLI & Server)
├── config.py            # 设置 (pydantic-settings)
├── constants.py         # 全局常量
├── logger.py            # 日志配置 (rich)
├── db.py                # DuckDB 连接管理器
├── schema.py            # SQL 模式管理
├── engine/              # 核心逻辑包
│   ├── __init__.py
│   ├── indexer.py       # 同步逻辑 & 向量生成
│   └── searcher.py      # 混合搜索实现
├── exceptions.py        # 自定义异常
├── mcp/                 # MCP 协议实现
│   ├── __init__.py
│   ├── server.py
│   └── tools.py
└── utils/               # 工具集
    ├── __init__.py
    ├── embedding.py     # OpenAI embedding 封装
    ├── text.py          # Jieba 分词封装
    └── io.py            # 原子文件操作
```

### Requirement: 入口点
系统应提供一个 `main.py`，作为 CLI 和 MCP 服务器的入口点，使用 `typer`。

### Requirement: 配置
系统应在 `config.py` 中使用 `pydantic-settings` 来管理配置，特别是 `KB_PATH` 环境变量。
