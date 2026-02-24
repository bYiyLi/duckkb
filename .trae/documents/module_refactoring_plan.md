# 模块重构分析与计划

## 现状分析

当前 `duckkb` 的项目结构如下：

```text
duckkb/
├── config.py           # 配置管理
├── constants.py        # 常量定义
├── db.py               # 数据库连接管理
├── exceptions.py       # 异常定义
├── logger.py           # 日志配置
├── main.py             # CLI 入口
├── schema.py           # 数据库模式定义与 DDL 生成
├── engine/             # 核心引擎
│   ├── core/           # 核心组件
│   │   ├── loader.py   # 数据加载 (File -> DB)
│   │   ├── manager.py  # 知识库管理入口
│   │   └── persister.py# 数据持久化 (DB -> File)
│   ├── backup.py       # 备份管理
│   ├── searcher.py     # 搜索逻辑
│   └── ...
├── mcp/                # MCP 协议实现
├── ontology/           # 本体定义与处理
└── utils/              # 工具函数
```

### 存在的问题

1.  **数据库逻辑分散**:
    - `db.py` 负责连接。
    - `schema.py` 负责 DDL 和 ER 图，位于根目录，显得杂乱。
    - `engine/core/persister.py` 负责数据落盘，但它更多是数据库与文件系统之间的桥梁，属于基础设施层，放在 `engine/core` 略显不当。

2.  **Engine 结构嵌套过深**:
    - `engine` 下又有 `core` 子包，包含 `manager`, `loader`, `persister`。
    - 而 `searcher.py`, `backup.py` 等又直接在 `engine` 下。
    - 这种混合结构使得层级不清晰，且 `core` 这个名字比较宽泛。

3.  **代码重复**:
    - `manager.py` 和 `loader.py` 中存在高度相似的 `_prepare_rows_for_insert` 逻辑 (数据向量化与行构建)，违反 DRY 原则。

4.  **命名不一致**:
    - `searcher.py` vs `backup.py` (动词+er vs 名词)。建议统一为功能名词，如 `search.py`。

## 重构计划

我们建议通过以下步骤优化模块结构，提高内聚性，降低耦合度。

### 1. 建立 Database 子包

将分散的数据库相关逻辑整合到 `duckkb.database` 包中。

-   **新建** `duckkb/database/` 目录。
-   **移动** `duckkb/db.py` -> `duckkb/database/connection.py`: 专注于连接管理。
-   **移动** `duckkb/schema.py` -> `duckkb/database/schema.py`: 专注于模式定义与 DDL。
-   **移动** `duckkb/engine/core/persister.py` -> `duckkb/database/persister.py`: 专注于数据持久化。

### 2. 扁平化 Engine 结构

简化 `engine` 目录结构，去除 `core` 中间层。

-   **移动** `duckkb/engine/core/manager.py` -> `duckkb/engine/manager.py`: 核心管理类。
-   **移动** `duckkb/engine/core/loader.py` -> `duckkb/engine/loader.py`: 数据加载逻辑。
-   **重命名** `duckkb/engine/searcher.py` -> `duckkb/engine/search.py`: 保持命名风格一致。
-   **删除** `duckkb/engine/core/` 目录。

### 3. (可选) 逻辑去重

提取 `manager.py` 和 `loader.py` 中的公共逻辑。

-   建议在 `duckkb/engine/ingestion.py` 或 `duckkb/utils/vector.py` 中提取 `prepare_search_rows` 函数，统一处理文本分词与向量化。

## 预期结构

```text
duckkb/
├── ... (根目录配置文件保持不变)
├── database/              # [NEW] 统一数据库层
│   ├── __init__.py
│   ├── connection.py      # 原 db.py
│   ├── schema.py          # 原 schema.py
│   └── persister.py       # 原 engine/core/persister.py
├── engine/                # [UPDATED] 扁平化引擎层
│   ├── manager.py         # 原 core/manager.py
│   ├── loader.py          # 原 core/loader.py
│   ├── search.py          # 原 searcher.py
│   ├── backup.py
│   ├── cache.py
│   └── migration.py
├── mcp/
└── ...
```

## 执行步骤

1.  创建新目录结构。
2.  移动文件并重命名。
3.  **关键**: 使用 Search/Replace 工具批量更新项目中的 import 路径。
    -   `from duckkb.db import ...` -> `from duckkb.database.connection import ...`
    -   `from duckkb.schema import ...` -> `from duckkb.database.schema import ...`
    -   `from duckkb.engine.core.manager import ...` -> `from duckkb.engine.manager import ...`
    -   等...
4.  运行测试/启动服务验证重构未破坏功能。
