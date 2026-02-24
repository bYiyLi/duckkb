"""日志配置模块。

本模块提供统一的日志配置功能，使用 Rich 库实现美观的控制台输出。
"""

import logging

from rich.logging import RichHandler


def setup_logging(level: str = "INFO"):
    """配置应用程序日志。

    使用 RichHandler 实现带格式的控制台输出，并降低第三方库的日志级别以减少噪音。

    Args:
        level: 日志级别，默认为 INFO。可选值：DEBUG、INFO、WARNING、ERROR、CRITICAL。
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


logger = logging.getLogger("duckkb")
