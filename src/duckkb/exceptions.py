"""异常定义模块。

本模块定义了 DuckKB 项目中使用的所有自定义异常类，
采用层级化设计便于异常捕获和处理。
"""


class DuckKBError(Exception):
    """DuckKB 基础异常类。

    所有 DuckKB 自定义异常的基类，可用于统一捕获所有项目异常。
    """

    pass


class ConfigurationError(DuckKBError):
    """配置相关异常。

    当配置项缺失、格式错误或验证失败时抛出。
    """

    pass


class DatabaseError(DuckKBError):
    """数据库相关异常。

    当数据库操作失败、连接错误或查询执行异常时抛出。
    """

    pass


class SyncError(DuckKBError):
    """同步相关异常。

    当数据同步过程中发生错误时抛出。
    """

    pass
