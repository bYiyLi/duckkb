"""CLI 工具模块。

提供基于 typer 的命令行工具实现，
将知识库能力暴露为 CLI 命令。

使用方式：
    ```bash
    # 启动 MCP 服务器
    duckkb --kb-path /path/to/kb serve

    # 显示版本
    duckkb version

    # 使用默认路径
    duckkb serve
    ```
"""

from duckkb.cli.duck_typer import DuckTyper

__all__ = ["DuckTyper", "app", "main"]

app = DuckTyper()


def main() -> None:
    """CLI 入口函数。

    用于 pyproject.toml 中的 project.scripts 注册。
    """
    app()
