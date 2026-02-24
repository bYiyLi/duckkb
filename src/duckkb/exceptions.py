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


class ValidationError(DuckKBError):
    """验证相关异常。

    当数据验证失败时抛出，如文件格式错误、字段缺失等。
    """

    pass


class TableNotFoundError(DatabaseError):
    """表不存在异常。

    当尝试操作不存在的表时抛出。
    """

    def __init__(self, table_name: str):
        self.table_name = table_name
        super().__init__(f"Table '{table_name}' not found")


class RecordNotFoundError(DatabaseError):
    """记录不存在异常。

    当尝试删除或更新不存在的记录时抛出。
    """

    def __init__(self, table_name: str, record_ids: list[str]):
        self.table_name = table_name
        self.record_ids = record_ids
        super().__init__(f"Records {record_ids} not found in table '{table_name}'")


class InvalidTableNameError(ConfigurationError):
    """无效表名异常。

    当表名不符合命名规范时抛出。
    """

    def __init__(self, table_name: str, reason: str):
        self.table_name = table_name
        self.reason = reason
        super().__init__(f"Invalid table name '{table_name}': {reason}")
