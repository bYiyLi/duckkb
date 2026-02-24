# DuckKB 代码目录与模块划分规划

根据“一库一服”与“文件驱动”的核心架构，以下是项目的代码目录结构与模块职责划分。

## 1. 项目根目录结构

```
/
├── .trae/               # Trae IDE 配置与规则
├── data/                # (示例) 本地开发用的知识库数据目录
├── src/
│   └── duckkb/          # 源码主包
├── tests/               # 测试代码
├── pyproject.toml       # 项目配置与依赖
└── README.md            # 项目说明
```

## 2. 源码目录结构 (`src/duckkb/`)

核心逻辑分为：**配置层**、**引擎层**、**服务层**、**工具层**。

```
src/duckkb/
├── __init__.py
├── main.py              # [入口] CLI 与 Server 的启动入口
├── config.py            # [配置] Pydantic Settings 管理环境变量 (KB_PATH, API_KEY)
├── constants.py         # [常量] 系统表名、默认参数
├── exceptions.py        # [异常] 定义 DuckKBError 及其子类
│
├── engine/              # [核心引擎] 负责数据库交互与业务逻辑
│   ├── __init__.py
│   ├── db.py            # DuckDB 连接管理、Schema 初始化、安全 SQL 执行
│   ├── indexer.py       # 索引器：负责 JSONL -> DuckDB 的增量同步
│   ├── search.py        # 检索器：混合检索 (BM25+Vector) 逻辑实现
│   └── vector.py        # 向量层：Embedding 生成与 Hash 缓存 (_sys_cache) 管理
│
├── mcp/                 # [MCP 协议] 适配 FastMCP
│   ├── __init__.py
│   └── server.py        # 定义 MCP 工具 (Tools) 与资源 (Resources)
│
└── utils/               # [通用工具] 无业务逻辑的底层函数
    ├── __init__.py
    ├── file.py          # 原子写文件、路径检查
    ├── hash.py          # 文本 Hash 计算 (MD5/SHA256)
    ├── log.py           # 日志配置 (Rich)
    └── text.py          # 文本分词 (Jieba)
```

## 3. 测试目录结构 (`tests/`)

```
tests/
├── conftest.py          # Pytest Fixtures (Mock DB, Temp Dir)
├── test_config.py       # 配置加载测试
├── engine/
│   ├── test_db.py       # 数据库连接与 SQL 安全测试
│   ├── test_vector.py   # 向量缓存命中测试
│   └── test_search.py   # 混合检索准确性测试
└── utils/
    └── test_text.py     # 分词工具测试
```

## 4. 模块依赖关系

*   **`main.py`** 依赖 `mcp.server` 和 `config`。
*   **`mcp.server`** 依赖 `engine` 各子模块暴露的业务接口。
*   **`engine`** 内部：
    *   `indexer` 依赖 `vector` (生成向量) 和 `db` (写入数据)。
    *   `search` 依赖 `vector` (查询向量) 和 `db` (执行 SQL)。
*   **`utils`** 被所有上层模块依赖。

此结构实现了**业务逻辑 (`engine`)** 与 **接口协议 (`mcp`)** 的解耦，方便后续扩展 CLI 或 API 服务。
