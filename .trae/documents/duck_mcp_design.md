# DuckMCP 设计方案（简单版本）

## 一、架构设计

### 1.1 继承结构

```python
class DuckMCP(Engine, FastMCP):
    """DuckKB MCP 服务类。
    
    多重继承 Engine 和 FastMCP。
    使用 lifespan 管理生命周期。
    工具注册占位，后续扩展。
    """
```

### 1.2 设计目标

**使用方式：**

```python
DuckMCP("/path/to/kb").run()
```

## 二、类设计

### 2.1 DuckMCP 类定义

````python
"""DuckMCP - 将知识库引擎暴露为 MCP 工具。"""

from collections.abc import AsyncIterator
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from duckkb.core.engine import Engine
from duckkb.logger import logger


@lifespan
async def engine_lifespan(server: "DuckMCP") -> AsyncIterator[dict]:
    """Engine 生命周期管理。
    
    在 MCP 服务启动时初始化引擎，关闭时清理资源。
    
    Args:
        server: DuckMCP 实例。
    
    Yields:
        包含 engine 实例的上下文字典。
    """
    logger.info("Initializing knowledge base engine...")
    server.initialize()
    logger.info("Knowledge base engine initialized.")
    
    yield {"engine": server}
    
    logger.info("Closing knowledge base engine...")
    server.close()
    logger.info("Knowledge base engine closed.")


class DuckMCP(Engine, FastMCP):
    """DuckKB MCP 服务类。
    
    多重继承 Engine 和 FastMCP，将知识库能力暴露为 MCP 工具。
    
    通过继承 Engine 获得知识库操作能力：
    - 混合检索（向量 + 全文）
    - 索引构建与管理
    - 数据加载与导出
    - 本体管理
    
    通过继承 FastMCP 获得 MCP 服务能力：
    - 工具注册与暴露
    - 多种传输协议（stdio, http, sse）
    - 生命周期管理
    
    Attributes:
        kb_path: 知识库根目录（来自 Engine）。
        config: 配置对象（来自 Engine）。
        name: MCP 服务名称（来自 FastMCP）。
    
    Example:
        ```python
        # 开箱即用
        DuckMCP("/path/to/kb").run()
        
        # 自定义名称
        DuckMCP("/path/to/kb", name="MyKB").run()
        
        # HTTP 模式
        mcp = DuckMCP("/path/to/kb")
        mcp.run(transport="http", port=8000)
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
        **kwargs,
    ) -> None:
        """初始化 DuckMCP。
        
        创建 Engine 实例、FastMCP 实例，并注册工具。
        
        Args:
            kb_path: 知识库根目录路径。
            name: MCP 服务名称，默认 "DuckKB"。
            instructions: MCP 服务说明。
            config_path: 配置文件路径，默认为 kb_path/config.yaml。
            rrf_k: RRF 常数，默认 60。
            **kwargs: 传递给 FastMCP 的其他参数。
        """
        Engine.__init__(
            self,
            kb_path=kb_path,
            config_path=config_path,
            rrf_k=rrf_k,
        )
        FastMCP.__init__(
            self,
            name=name,
            instructions=instructions,
            lifespan=engine_lifespan,
            **kwargs,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        """注册 MCP 工具。
        
        TODO: 实现完整的工具注册。
        """
        pass
````

### 2.2 文件位置

```
src/duckkb/
├── core/
│   └── engine.py          # 现有引擎
├── mcp/
│   ├── __init__.py        # 导出 DuckMCP
│   ├── server.py          # 现有服务（保留兼容）
│   └── duck_mcp.py        # 新增：DuckMCP 类
```

## 三、使用示例

```python
from duckkb.mcp import DuckMCP

# 一行代码启动
DuckMCP("/path/to/kb").run()

# 自定义名称
DuckMCP("/path/to/kb", name="MyKB").run()

# HTTP 模式
mcp = DuckMCP("/path/to/kb")
mcp.run(transport="http", port=8000)
```

## 四、实现步骤

| 步骤 | 任务                      | 文件                |
| -- | ----------------------- | ----------------- |
| 1  | 创建 DuckMCP 类 + lifespan | `mcp/duck_mcp.py` |
| 2  | 更新 `__init__.py` 导出     | `mcp/__init__.py` |

