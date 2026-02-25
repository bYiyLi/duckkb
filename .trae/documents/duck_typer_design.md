# DuckTyper 设计方案（多重继承）

## 一、架构设计

### 1.1 继承结构

```python
class DuckTyper(Engine, DuckMCP, typer.Typer):
    """DuckKB CLI 工具类。
    
    多重继承 Engine、DuckMCP 和 typer.Typer。
    将知识库能力和 MCP 服务暴露为 CLI 命令。
    """
```

### 1.2 MRO 分析

```
DuckTyper
→ Engine (及所有 Mixin)
→ DuckMCP
→ FastMCP (及父类)
→ typer.Typer
→ object
```

### 1.3 设计思路

由于 DuckTyper 同时继承 Engine、DuckMCP 和 typer.Typer：

1. Engine 提供知识库操作能力
2. DuckMCP 提供 MCP 服务能力（已继承 Engine）
3. typer.Typer 提供 CLI 框架
4. `serve` 命令直接调用 `self.run()`（来自 FastMCP）

**问题：DuckMCP 已经继承了 Engine**

如果 DuckTyper 继承 DuckMCP，就不需要再单独继承 Engine（DuckMCP 已经继承）。

**修正后的继承结构：**

```python
class DuckTyper(DuckMCP, typer.Typer):
    """DuckKB CLI 工具类。
    
    多重继承 DuckMCP 和 typer.Typer。
    DuckMCP 已经继承了 Engine。
    """
```

## 二、类设计

### 2.1 DuckTyper 类定义

````python
"""DuckTyper - 将知识库引擎暴露为 CLI 命令。"""

from pathlib import Path
from typing import Any, Self

import typer

from duckkb import __version__
from duckkb.mcp.duck_mcp import DuckMCP
from duckkb.logger import logger


class DuckTyper(DuckMCP, typer.Typer):
    """DuckKB CLI 工具类。

    多重继承 DuckMCP 和 typer.Typer，将知识库能力暴露为 CLI 命令。

    通过继承 DuckMCP（及其父类 Engine）获得：
    - 知识库操作能力（Engine）
    - MCP 服务能力（FastMCP）

    通过继承 typer.Typer 获得：
    - CLI 命令注册
    - 参数解析
    - 帮助信息生成

    自动注册的命令：
    - serve: 启动 MCP 服务器（调用 self.run()）
    - version: 显示版本信息

    Attributes:
        kb_path: 知识库根目录（来自 Engine）。
        name: MCP 服务名称（来自 FastMCP）。

    Example:
        ```python
        # 开箱即用
        app = DuckTyper("/path/to/kb")
        app()  # 运行 CLI

        # 或作为模块入口
        if __name__ == "__main__":
            DuckTyper("/path/to/kb")()
        ```
    """

    def __init__(
        self,
        kb_path: Path | str,
        *,
        name: str = "DuckKB",
        instructions: str | None = None,
        config_path: Path | str | None = None,
        rrf_k: int = 60,
        **kwargs: Any,
    ) -> None:
        """初始化 DuckTyper。

        创建 DuckMCP 实例和 typer.Typer 实例，并注册命令。

        Args:
            kb_path: 知识库根目录路径。
            name: MCP 服务名称，默认 "DuckKB"。
            instructions: MCP 服务说明。
            config_path: 配置文件路径。
            rrf_k: RRF 常数。
            **kwargs: 传递给 typer.Typer 的其他参数。
        """
        DuckMCP.__init__(
            self,
            kb_path=kb_path,
            name=name,
            instructions=instructions,
            config_path=config_path,
            rrf_k=rrf_k,
        )
        typer.Typer.__init__(
            self,
            name=name.lower(),
            **kwargs,
        )
        self._register_commands()

    def _register_commands(self) -> None:
        """注册 CLI 命令。"""
        self._register_serve_command()
        self._register_version_command()

    def _register_serve_command(self) -> None:
        """注册 serve 命令。"""

        @self.command()
        def serve() -> None:
            """启动 MCP 服务器。

            知识库初始化和关闭时的数据持久化由 FastMCP lifespan 管理。
            """
            logger.info(f"Starting MCP server for {self.kb_path}")
            self.run()

    def _register_version_command(self) -> None:
        """注册 version 命令。"""

        @self.command()
        def version() -> None:
            """显示版本信息。"""
            typer.echo(f"DuckKB v{__version__}")

    def __call__(self) -> None:
        """运行 CLI 应用。"""
        typer.Typer.__call__(self)
````

### 2.2 文件位置

```
src/duckkb/
├── cli/
│   ├── __init__.py        # 导出 DuckTyper
│   └── duck_typer.py      # DuckTyper 类
├── main.py                # 现有入口（保留兼容）
└── ...
```

## 三、使用示例

### 3.1 开箱即用

```python
from duckkb.cli import DuckTyper

app = DuckTyper("/path/to/kb")
app()  # 运行 CLI
```

### 3.2 命令行使用

```bash
# 启动 MCP 服务器
duckkb serve

# 显示版本
duckkb version
```

### 3.3 扩展命令

```python
app = DuckTyper("/path/to/kb")

@app.command()
def build_index(node_type: str | None = None) -> None:
    """构建搜索索引。"""
    import asyncio
    asyncio.run(app.build_index(node_type))

app()
```

## 四、继承关系图

```
                    ┌─────────────┐
                    │   Engine    │
                    │ (知识库能力) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   DuckMCP   │
                    │ (MCP 服务)   │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │  FastMCP    │   │  DuckTyper  │   │ typer.Typer │
  │ (MCP 框架)   │   │ (CLI 工具)   │   │ (CLI 框架)  │
  └─────────────┘   └─────────────┘   └─────────────┘
```

## 五、实现步骤

| 步骤 | 任务                  | 文件                  |
| -- | ------------------- | ------------------- |
| 1  | 创建 cli 目录           | `cli/`              |
| 2  | 创建 DuckTyper 类      | `cli/duck_typer.py` |
| 3  | 更新 `__init__.py` 导出 | `cli/__init__.py`   |

