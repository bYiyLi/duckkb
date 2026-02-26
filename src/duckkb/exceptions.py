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


class FTSError(DuckKBError):
    """FTS 扩展不可用异常。

    当 FTS 索引不存在或 FTS 扩展未安装时抛出。
    """

    pass


class ValidationError(DuckKBError):
    """验证相关异常。

    当数据验证失败时抛出，如文件格式错误、字段缺失等。
    """

    pass


class InvalidTableNameError(ConfigurationError):
    """无效表名异常。

    当表名不符合命名规范时抛出。
    """

    def __init__(self, table_name: str, reason: str):
        self.table_name = table_name
        self.reason = reason
        super().__init__(f"Invalid table name '{table_name}': {reason}")


class GraphError(DuckKBError):
    """图谱操作异常基类。

    所有图谱相关异常的基类。
    """

    pass


class NodeNotFoundError(GraphError):
    """节点不存在异常。

    当查询的节点在数据库中不存在时抛出。
    """

    def __init__(self, node_type: str, node_id: int | str):
        self.node_type = node_type
        self.node_id = node_id
        super().__init__(f"Node not found: type={node_type}, id={node_id}")


class InvalidDirectionError(GraphError):
    """无效遍历方向异常。

    当遍历方向参数不是有效值时抛出。
    """

    def __init__(self, direction: str):
        self.direction = direction
        super().__init__(f"Invalid direction: {direction}. Must be one of: out, in, both")
