# DuckTyper CLI 参数设计修正

## 一、问题分析

**当前错误设计：**

```python
app = DuckTyper("/path/to/kb")  # 硬编码路径
app()
```

**正确设计：**

```bash
duckkb --kb-path /path/to/kb serve
duckkb -k /path/to/kb version
```

## 二、参考现有实现

现有 main.py 使用 `@app.callback()` 定义全局选项：

```python
@app.callback()
def main(
    kb_path: Path = typer.Option(
        DEFAULT_KB_PATH,
        "--kb-path",
        "-k",
        help="Path to knowledge base directory",
    ),
):
    """初始化应用上下文并配置日志。"""
    if not kb_path.exists():
        kb_path.mkdir(parents=True, exist_ok=True)
    ctx = AppContext.init(kb_path)
    setup_logging(ctx.kb_config.LOG_LEVEL)
```

## 三、修正方案

### 3.1 DuckTyper 类设计

```python
class DuckTyper(typer.Typer):
    """DuckKB CLI 工具类。"""
    
    def __init__(self, **kwargs: Any) -> None:
        """初始化 DuckTyper。
        
        不接受 kb_path 参数，通过 CLI 选项传入。
        """
        super().__init__(**kwargs)
        self._kb_path: Path | None = None
        self._register_callback()
        self._register_commands()
    
    @property
    def kb_path(self) -> Path:
        """知识库根目录。"""
        if self._kb_path is None:
            raise RuntimeError("kb_path not initialized, call callback first")
        return self._kb_path
    
    def _register_callback(self) -> None:
        """注册全局回调（处理 kb_path 选项）。"""
        
        @self.callback()
        def main(
            kb_path: Path = typer.Option(
                Path("./knowledge-bases/default"),
                "--kb-path",
                "-k",
                help="知识库目录路径",
            ),
        ) -> None:
            """DuckKB CLI 和 MCP 服务器入口。"""
            if not kb_path.exists():
                kb_path.mkdir(parents=True, exist_ok=True)
            self._kb_path = kb_path.resolve()
            
            # 初始化应用上下文
            from duckkb.config import AppContext
            from duckkb.logger import setup_logging
            ctx = AppContext.init(kb_path)
            setup_logging(ctx.kb_config.LOG_LEVEL)
    
    def _register_serve_command(self) -> None:
        """注册 serve 命令。"""
        
        @self.command()
        def serve() -> None:
            """启动 MCP 服务器。"""
            mcp = DuckMCP(self.kb_path)
            mcp.run()
```

### 3.2 使用方式

```python
# 入口文件
from duckkb.cli import DuckTyper

app = DuckTyper()

if __name__ == "__main__":
    app()
```

```bash
# 命令行使用
duckkb --kb-path /path/to/kb serve
duckkb -k /path/to/kb version
duckkb version  # 使用默认路径
```

## 四、实现步骤

| 步骤 | 任务                                               |
| -- | ------------------------------------------------ |
| 1  | 移除 `__init__` 的 `kb_path` 参数                     |
| 2  | 添加 `_kb_path` 属性和 `kb_path` property             |
| 3  | 实现 `_register_callback()` 方法                     |
| 4  | 更新 `_register_serve_command()` 使用 `self.kb_path` |
| 5  | 更新废弃的 main.py 中的迁移示例                             |

