# 标记历史代码废弃计划

## 一、需要标记废弃的文件

| 文件 | 替代方案 |
|------|----------|
| `src/duckkb/mcp/server.py` | `src/duckkb/mcp/duck_mcp.py` (DuckMCP) |
| `src/duckkb/main.py` | `src/duckkb/cli/duck_typer.py` (DuckTyper) |

## 二、废弃标记方式

### 2.1 添加 DeprecationWarning

在模块加载时发出警告：
```python
import warnings

warnings.warn(
    "duckkb.mcp.server 已废弃，请使用 duckkb.mcp.DuckMCP",
    DeprecationWarning,
    stacklevel=2,
)
```

### 2.2 更新文档字符串

在模块和关键函数的 docstring 中添加废弃说明：
```python
"""
模块说明。

.. deprecated:: 0.2.0
    请使用 duckkb.mcp.DuckMCP 替代。
    该模块将在 0.3.0 版本中移除。
"""
```

## 三、具体修改

### 3.1 `src/duckkb/mcp/server.py`

```python
"""DuckKB MCP 服务模块

.. deprecated:: 0.2.0
    请使用 duckkb.mcp.DuckMCP 替代。
    该模块将在 0.3.0 版本中移除。

    迁移示例：
    ```python
    # 旧方式
    from duckkb.mcp.server import mcp
    mcp.run()

    # 新方式
    from duckkb.mcp import DuckMCP
    DuckMCP("/path/to/kb").run()
    ```
"""

import warnings

warnings.warn(
    "duckkb.mcp.server 已废弃，请使用 duckkb.mcp.DuckMCP",
    DeprecationWarning,
    stacklevel=2,
)

# ... 其余代码保持不变
```

### 3.2 `src/duckkb/main.py`

```python
"""命令行入口模块。

.. deprecated:: 0.2.0
    请使用 duckkb.cli.DuckTyper 替代。
    该模块将在 0.3.0 版本中移除。

    迁移示例：
    ```python
    # 旧方式
    from duckkb.main import app
    app()

    # 新方式
    from duckkb.cli import DuckTyper
    DuckTyper("/path/to/kb")()
    ```
"""

import warnings

warnings.warn(
    "duckkb.main 已废弃，请使用 duckkb.cli.DuckTyper",
    DeprecationWarning,
    stacklevel=2,
)

# ... 其余代码保持不变
```

## 四、实现步骤

| 步骤 | 任务 | 文件 |
|------|------|------|
| 1 | 标记 mcp/server.py 废弃 | `mcp/server.py` |
| 2 | 标记 main.py 废弃 | `main.py` |
| 3 | 运行 ruff 格式化 | - |
